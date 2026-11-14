"""ProofStep's durable state machine and allowlisted read-only investigator.

The agent's tool order is explicit and observable; no LLM may approve or mutate.
Only this worker-side module calls the custodian amendment client.
"""

import os
import time
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

from app.db import CaseStore, utcnow
from app.hashing import proposal_hash
from app.market import market_context
from app.models import Proposal, Stage
from app.services.memory import EmbeddingUnavailable, IncidentMemory
from app.services.simulator_clients import (
    BrokerClient,
    CustodianClient,
    DirectoryClient,
    SimulatorHttpError,
    SimulatorTimeout,
    SimulatorUnavailable,
)

CONTRACT_PATHS = {1: "settlementAccount", 2: "delivery.safekeepingAccount"}
IDENTITY_FIELDS = (
    "tradeId",
    "portfolioId",
    "cusip",
    "security",
    "quantity",
    "side",
    "settlementDate",
)


class UnsafeEvidence(ValueError):
    pass


def parse_directory(raw: dict, version: int, portfolio: str) -> dict:
    try:
        if version == 1:
            account, status, actual_portfolio = (
                raw["settlementAccount"],
                raw["accountStatus"],
                raw["portfolioId"],
            )
            if raw.get("schemaVersion", 1) != 1:
                raise ValueError("Contradictory schema version")
        elif version == 2:
            account, status, actual_portfolio = (
                raw["delivery"]["safekeepingAccount"],
                raw["delivery"]["status"],
                raw["portfolio"]["id"],
            )
            if raw.get("schemaVersion") != 2:
                raise ValueError("Contradictory schema version")
        else:
            raise ValueError("Unknown contract")
        revision = raw["mappingRevision"]
        if (
            not isinstance(account, str)
            or status != "ACTIVE"
            or actual_portfolio != portfolio
            or type(revision) is not int
            or revision < 1
        ):
            raise ValueError("Invalid account, scope or mapping revision")
        # Never select between contradictory account paths.
        other = (
            raw.get("delivery", {}).get("safekeepingAccount")
            if version == 1
            else raw.get("settlementAccount")
        )
        if other and other != account:
            raise ValueError("Conflicting account paths")
        return {
            "activeAccount": account,
            "portfolioId": portfolio,
            "mappingRevision": revision,
            "contractVersion": version,
            "adapter": f"v{version}",
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise UnsafeEvidence("Directory response violates the supported contract") from exc


class Workflow:
    def __init__(self, db, settings, worker_id: str, *, owns_lease=lambda: True, exit_fn=os._exit):
        self.db, self.settings, self.worker_id = db, settings, worker_id
        self.store = CaseStore(db)
        self.broker = BrokerClient(settings.broker_url)
        self.directory = DirectoryClient(settings.directory_url)
        self.custodian = CustodianClient(settings.custodian_url)
        self.memory = IncidentMemory(db, settings)
        self.owns_lease, self.exit_fn = owns_lease, exit_fn
        self.phase_started = time.perf_counter()

    def save(self, case, event, fields=None, stage=None, detail=None, unset=()):
        return self.store.cas_update(
            case["caseId"],
            case["stage"],
            case["version"],
            stage or case["stage"],
            run_id=case["runId"],
            actor=f"workflow-worker:{self.worker_id}",
            event_type=event,
            detail=detail or event.replace("_", " ").capitalize(),
            fields=fields,
            unset=unset,
        )

    def manual(self, case, code, detail):
        return self.save(
            case,
            "MANUAL_REVIEW",
            {"manualReview": {"code": code, "detail": detail}},
            Stage.MANUAL_REVIEW,
            detail,
        )

    def record(
        self,
        case,
        tool,
        request,
        data,
        phase,
        *,
        evidence_key=None,
        ok=True,
        summary=None,
        guided_by=None,
        extra=None,
    ):
        inv = deepcopy(case.get("investigation", {"steps": [], "precedents": []}))
        evidence = deepcopy(case.get("evidence", {}))
        evidence_id = "EV-" + uuid4().hex[:12]
        if evidence_key:
            evidence[evidence_key] = {**data, "evidenceId": evidence_id, "fetchedAt": utcnow()}
        inv.setdefault("steps", []).append(
            {
                "n": len(inv.get("steps", [])) + 1,
                "tool": tool,
                "actor": "investigator",
                "request": request,
                "ok": ok,
                "summary": summary or tool.replace("_", " "),
                "guidedBy": guided_by,
                "evidenceId": evidence_id,
                "at": utcnow(),
                "ms": round((time.perf_counter() - self.phase_started) * 1000),
            }
        )
        inv["phase"] = phase
        inv.update(extra or {})
        return self.store.cas_update(
            case["caseId"],
            case["stage"],
            case["version"],
            case["stage"],
            run_id=case["runId"],
            actor="investigator",
            event_type="TOOL_CALLED",
            detail=summary or tool,
            fields={"evidence": evidence, "investigation": inv},
        )

    def step(self, case):
        self.phase_started = time.perf_counter()
        try:
            if (
                case["stage"] == Stage.VERIFIED
                and case.get("learning", {}).get("status") == "PENDING"
            ):
                if case["learning"].get("nextAttemptAt", utcnow()) > utcnow():
                    return None
                attempts = case["learning"].get("attempts", 0) + 1
                try:
                    learned = self.memory.learn_verified(case)
                    return self.save(
                        case,
                        "EXPERIENCE_SAVED",
                        {"learning": {**learned, "attempts": attempts}},
                        detail="Independently verified correction saved as reusable experience",
                    )
                except EmbeddingUnavailable as exc:
                    return self.save(
                        case,
                        "EXPERIENCE_PENDING",
                        {
                            "learning": {
                                "status": "PENDING",
                                "attempts": attempts,
                                "reason": str(exc),
                                "nextAttemptAt": utcnow() + timedelta(seconds=60),
                            }
                        },
                        detail="Correction verified; experience publication is pending",
                    )
            if case["stage"] == Stage.INVESTIGATING:
                return self.investigate(case)
            if case["stage"] == Stage.APPROVED and case.get("executionRequested"):
                return self.prepare(case)
            if case["stage"] == Stage.AWAITING_VERIFICATION:
                return self.verify(case)
        except (SimulatorUnavailable, SimulatorTimeout):
            key = (
                "verification.deferrals"
                if case["stage"] == Stage.AWAITING_VERIFICATION
                else "readFailures"
            )
            count = (
                case.get("verification", {}).get("deferrals", 0)
                if key.startswith("verification")
                else case.get("readFailures", 0)
            ) + 1
            if count >= 5:
                return self.manual(
                    case,
                    "SOURCE_UNAVAILABLE",
                    "Five read deferrals; no blind resend",
                )
            return self.save(
                case,
                "VERIFICATION_DEFERRED",
                {key: count},
                detail="Source temporarily unavailable; outcome remains pending",
            )
        except (UnsafeEvidence, SimulatorHttpError, KeyError, TypeError, ValueError) as exc:
            return self.manual(case, "UNSAFE_OR_CONFLICTING_EVIDENCE", str(exc)[:300])

    def investigate(self, case):
        inv, evidence = case.get("investigation", {}), case.get("evidence", {})
        phase = inv.get("phase", 0)
        if phase == 0:
            instruction = self.custodian.get_instruction(case["caseId"])
            if instruction["status"] == "ACCEPTED":
                return self.save(
                    case,
                    "NO_ACTION",
                    {"evidence.custodianBaseline": instruction},
                    Stage.NO_ACTION,
                    "Instruction already accepted; zero amendments",
                )
            if (
                instruction["status"] != "REJECTED"
                or instruction["instructionId"] != case["caseId"]
            ):
                raise UnsafeEvidence("Instruction is not this rejected instruction")
            return self.record(
                case,
                "get_custodian_instruction",
                f"GET /instructions/{case['caseId']}",
                instruction,
                1,
                evidence_key="custodianBaseline",
            )
        if phase == 1:
            trade = self.broker.get_trade(case["tradeId"])
            return self.record(
                case,
                "get_broker_trade",
                f"GET /trades/{case['tradeId']}",
                trade,
                2,
                evidence_key="broker",
            )
        if phase == 2:
            trade, instruction = evidence["broker"], evidence["custodianBaseline"]
            if (
                any(trade.get(k) != instruction.get(k) for k in IDENTITY_FIELDS)
                or trade["tradeId"] != case["tradeId"]
                or trade["portfolioId"] != case["portfolioId"]
                or trade["status"] != "EXECUTED"
                or type(trade["quantity"]) is not int
                or trade["quantity"] <= 0
            ):
                raise UnsafeEvidence("TRADE_MISMATCH: broker and custodian trade facts disagree")
            context = market_context(self.db, trade["cusip"], trade["settlementDate"])
            next_inv = {**inv, "phase": 3}
            return self.save(
                case,
                "MARKET_CONTEXT_READ",
                {
                    "marketContext": context,
                    "marketContextId": context["observationId"],
                    "investigation": next_inv,
                },
                detail="CUSIP/date lookup: "
                + (context["observationId"] or "No reported observation"),
            )
        if phase == 3:
            old = evidence["custodianBaseline"]["safekeepingAccount"]
            status = self.directory.get_account_status(old)
            if status["status"] != "RETIRED" or status["portfolioId"] != case["portfolioId"]:
                raise UnsafeEvidence("Old account is not retired for portfolio")
            return self.record(
                case,
                "get_account_status",
                f"GET /account-status/{old}",
                status,
                4,
                evidence_key="retiredAccount",
                summary=f"{old} is retired",
            )
        if phase == 4:
            if case.get("demo", {}).get("pauseDirectoryRead"):
                if not case.get("demo", {}).get("directoryPaused"):
                    return self.save(
                        case,
                        "DIRECTORY_READ_PAUSED",
                        {"demo.directoryPaused": True},
                        detail="Paused before directory read; switch to v2 and continue",
                    )
                return None
            if not inv.get("experienceChecked"):
                if inv.get("experienceRetryAt", utcnow()) > utcnow():
                    return None
                eligible = self.db.incidents.count_documents(
                    {
                        "learningScope": self.settings.demo_case_id,
                        "portfolioId": case["portfolioId"],
                        "learnedFromRunId": {"$ne": case["runId"]},
                        "disposition": "VERIFIED",
                        "embeddingModel": self.settings.voyage_model,
                        "embedding": {"$exists": True},
                    }
                )
                if eligible:
                    result = self.memory.retrieve(
                        "retired receiving account invalid safekeeping account "
                        "current receiving account mapping requires validation",
                        source="directory:" + self.settings.demo_case_id,
                        limit=10,
                    )
                    learned = max(
                        (
                            m
                            for m in result["matches"]
                            if m.get("learningScope") == self.settings.demo_case_id
                            and m.get("portfolioId") == case["portfolioId"]
                            and m.get("learnedFromRunId") != case["runId"]
                            and m.get("score", 0) >= 0.70
                            and m.get("suggestedNextCheck") == "GET_DIRECTORY_CONTRACT"
                        ),
                        key=lambda match: match["createdAt"],
                        default=None,
                    )
                    if learned:
                        next_inv = {
                            **inv,
                            "experienceChecked": True,
                            "experienceWaiting": False,
                            "phase": 6,
                            "precedents": [
                                {"query": result["query"], "status": result["status"], **learned}
                            ],
                            "retrieval": result,
                            "reusedExperience": learned,
                        }
                        return self.save(
                            case,
                            "EXPERIENCE_REUSED",
                            {"investigation": next_inv},
                            detail="Verified case "
                            + learned["learnedFromCaseId"]
                            + " guided a proactive live contract check",
                        )
                    attempts = inv.get("experienceAttempts", 0) + 1
                    if attempts < 3 and result["status"] in {"PENDING", "NONE"}:
                        delay = (
                            60
                            if "429" in str(result["reason"])
                            or "RATE_LIMIT" in str(result["reason"])
                            else 3
                        )
                        return self.save(
                            case,
                            "EXPERIENCE_LOOKUP_PENDING",
                            {
                                "investigation": {
                                    **inv,
                                    "experienceAttempts": attempts,
                                    "experienceRetryAt": utcnow() + timedelta(seconds=delay),
                                    "experienceWaiting": True,
                                }
                            },
                            detail="Waiting for verified experience retrieval; no amendment sent",
                        )
                return self.save(
                    case,
                    "EXPERIENCE_CHECKED",
                    {
                        "investigation": {
                            **inv,
                            "experienceChecked": True,
                            "experienceWaiting": False,
                        }
                    },
                    detail="No reusable learned procedure retrieved yet; inspect current records",
                )
            raw = self.directory.get_accounts_raw(case["portfolioId"])
            try:
                account = parse_directory(raw, 1, case["portfolioId"])
                return self.record(
                    case,
                    "get_directory_account",
                    f"GET /accounts/{case['portfolioId']}",
                    account,
                    8,
                    evidence_key="directory",
                    summary="Validated v1 receiving-account response",
                )
            except UnsafeEvidence:
                return self.record(
                    case,
                    "get_directory_account",
                    f"GET /accounts/{case['portfolioId']}",
                    raw,
                    5,
                    ok=False,
                    summary="v1 field settlementAccount missing or changed; investigate contract",
                    extra={
                        "directoryMismatch": "directory payload moved the account field; "
                        "settlementAccount missing; observed keys: " + ", ".join(sorted(raw))
                    },
                )
        if phase == 5:
            result = self.memory.retrieve(inv["directoryMismatch"], source="directory")
            first = result["matches"][0] if result["matches"] else {}
            precedent = {
                "query": result["query"],
                "status": result["status"],
                "reason": result["reason"],
                **first,
            }
            next_inv = {**inv, "phase": 6, "precedents": [precedent], "retrieval": result}
            return self.save(
                case,
                "PRECEDENT_RETRIEVED" if first else "RETRIEVAL_PENDING",
                {"investigation": next_inv},
                detail=(
                    f"Atlas {first['incidentId']}: {first['suggestedNextCheck']}"
                    if first
                    else f"Memory {result['status']}: {result['reason']}; inspect live contract"
                ),
            )
        if phase == 6:
            contract = self.directory.get_contract()
            version = contract["version"]
            if version not in CONTRACT_PATHS or contract["accountPath"] != CONTRACT_PATHS[version]:
                return self.manual(
                    case, "UNKNOWN_DIRECTORY_CONTRACT", "Live contract has no allowlisted adapter"
                )
            precedent = next(iter(inv.get("precedents", [])), {})
            guided_by = (
                precedent.get("incidentId")
                if precedent.get("suggestedNextCheck") == "GET_DIRECTORY_CONTRACT"
                else None
            )
            return self.record(
                case,
                "get_directory_contract",
                "GET /contract",
                contract,
                7,
                evidence_key="directoryContract",
                summary=f"Live contract selects validated v{version} adapter",
                guided_by=guided_by,
                extra={"adapterVersion": version},
            )
        if phase == 7:
            raw = self.directory.get_accounts_raw(case["portfolioId"])
            account = parse_directory(raw, inv["adapterVersion"], case["portfolioId"])
            return self.record(
                case,
                "get_directory_account",
                f"GET /accounts/{case['portfolioId']}",
                account,
                8,
                evidence_key="directory",
                summary=f"v{inv['adapterVersion']} validates {account['activeAccount']}",
            )
        if phase == 8:
            account = evidence["directory"]["activeAccount"]
            status = self.directory.get_account_status(account)
            if (
                status["status"] != "ACTIVE"
                or status["authorized"] is not True
                or status["portfolioId"] != case["portfolioId"]
            ):
                raise UnsafeEvidence("Active account status or portfolio authorization conflicts")
            return self.record(
                case,
                "get_account_status",
                f"GET /account-status/{account}",
                status,
                9,
                evidence_key="activeAccount",
            )
        policy = self.policy(case)
        baseline, directory = evidence["custodianBaseline"], evidence["directory"]
        proposal = Proposal(
            caseId=case["caseId"],
            runId=case["runId"],
            instructionId=case["caseId"],
            tradeId=case["tradeId"],
            portfolioId=case["portfolioId"],
            expectedRevision=baseline["revision"],
            oldAccount=baseline["safekeepingAccount"],
            newAccount=directory["activeAccount"],
            mappingRevision=directory["mappingRevision"],
            policyVersion=policy["version"],
        ).model_dump()
        next_inv = {
            **inv,
            "diagnosis": "Retired receiving account verified across independent systems; "
            "propose one account amendment. Market observation is historical context only.",
        }
        return self.save(
            case,
            "PROPOSAL_CREATED",
            {
                "proposal": proposal,
                "proposalHash": proposal_hash(proposal),
                "investigation": next_inv,
            },
            Stage.AWAITING_APPROVAL,
        )

    def policy(self, case):
        policy = self.db.policies.find_one({"policyId": "settlement-amendment", "synthetic": True})
        if (
            not policy
            or not policy.get("enabled", True)
            or policy.get("permittedPortfolio", "P-17") != case["portfolioId"]
        ):
            raise UnsafeEvidence("Policy does not authorize this portfolio/action")
        return policy

    def recheck(self, case, instruction=None):
        proposal, approval = case["proposal"], case["approval"]
        policy = self.policy(case)
        digest = proposal_hash(proposal)
        if (
            digest != case["proposalHash"]
            or digest != approval["approvedProposalHash"]
            or policy["version"] != proposal["policyVersion"]
            or approval.get("decision", "APPROVE") != "APPROVE"
            or approval.get("policyVersion") != policy["version"]
            or proposal["mutation"] != policy["allowedMutation"]
            or not any(
                r["reviewerId"] == approval["reviewerId"]
                and r["role"] == approval["role"] == policy["requiredRole"]
                for r in policy["reviewers"]
            )
        ):
            raise UnsafeEvidence("Approval or current policy no longer authorizes the payload")
        current = instruction or self.custodian.get_instruction(case["caseId"])
        baseline = case["evidence"]["custodianBaseline"]
        if (
            current["revision"] != proposal["expectedRevision"]
            or current["status"] != "REJECTED"
            or current["safekeepingAccount"] != proposal["oldAccount"]
            or any(current.get(k) != baseline.get(k) for k in IDENTITY_FIELDS)
        ):
            raise UnsafeEvidence("Custodian baseline changed")
        contract = self.directory.get_contract()
        if (
            contract["version"] not in CONTRACT_PATHS
            or contract["accountPath"] != CONTRACT_PATHS[contract["version"]]
        ):
            raise UnsafeEvidence("Unsupported live directory contract")
        account = parse_directory(
            self.directory.get_accounts_raw(case["portfolioId"]),
            contract["version"],
            case["portfolioId"],
        )
        status = self.directory.get_account_status(account["activeAccount"])
        if (
            account["activeAccount"] != proposal["newAccount"]
            or account["mappingRevision"] != proposal["mappingRevision"]
            or status["status"] != "ACTIVE"
            or status["authorized"] is not True
            or status["portfolioId"] != case["portfolioId"]
        ):
            raise UnsafeEvidence("Directory mapping or authorization changed since approval")

    def prepare(self, case):
        try:
            self.recheck(case)
        except UnsafeEvidence as exc:
            return self.save(
                case,
                "APPROVAL_INVALIDATED",
                {"investigation": {"phase": 0}, "evidence": {}, "executionRequested": False},
                Stage.INVESTIGATING,
                str(exc),
                unset=("proposal", "proposalHash", "approval"),
            )
        if not self.owns_lease():
            return None
        intent = self.store.persist_intent(case, self.worker_id)
        if intent:
            if intent.get("demo", {}).get("crashBeforeSend"):
                print("Intent persisted; deliberate exit BEFORE PATCH", flush=True)
                self.exit_fn(137)
                return None
            return self.send(intent)

    def send(self, case):
        if not self.owns_lease():
            return None
        dispatched = self.save(
            case,
            "PATCH_SENT",
            {"operation.lastSentAt": utcnow()},
            detail="Worker dispatching approved PATCH with the persisted idempotency key",
        )
        if not dispatched:
            return None
        operation = dispatched["operation"]
        try:
            self.custodian.amend_instruction(
                case["caseId"],
                expected_revision=operation["payload"]["expectedRevision"],
                new_account=operation["payload"]["newAccount"],
                operation_id=operation["operationId"],
                timeout=self.settings.custodian_timeout_seconds,
            )
            return self.save(
                dispatched,
                "ACK_RECEIVED",
                {"operation.lastOutcome": "ACK"},
                detail="Reply received; independent read-back still required",
            )
        except (SimulatorTimeout, SimulatorUnavailable):
            if dispatched.get("demo", {}).get("crashWorkerOnUnknown"):
                print("Custodian outcome UNKNOWN; deliberate real worker exit 137", flush=True)
                self.exit_fn(137)
                return None
            return self.save(
                dispatched,
                "OUTCOME_UNKNOWN",
                {"operation.lastOutcome": "UNKNOWN"},
                detail="Reply unavailable; verify before any retry",
            )

    def verify(self, case):
        operation = case["operation"]
        if (
            case.get("checkpoint", {}).get("savedByWorkerId") != self.worker_id
            and case.get("verification", {}).get("resumedByWorkerId") != self.worker_id
        ):
            return self.save(
                case,
                "RESUMED_FROM_CHECKPOINT",
                {"verification.resumedByWorkerId": self.worker_id},
                detail=(
                    "Restart loaded saved stage and original operation " + operation["operationId"]
                ),
            )
        receipt = self.custodian.lookup_operation(operation["operationId"])
        instruction = self.custodian.get_instruction(case["caseId"])
        if receipt is not None:
            baseline = case["evidence"]["custodianBaseline"]
            matches = (
                receipt.get("operationId") == operation["operationId"]
                and receipt.get("instructionId")
                == instruction.get("instructionId")
                == case["caseId"]
                and receipt.get("account")
                == instruction.get("safekeepingAccount")
                == operation["payload"]["newAccount"]
                and receipt.get("resultRevision")
                == instruction.get("revision")
                == operation["payload"]["expectedRevision"] + 1
                and receipt.get("status") == instruction.get("status") == "ACCEPTED"
                and receipt.get("payloadHash") == operation["payloadHash"]
                and instruction.get("latestOperationId") == operation["operationId"]
                and bool(receipt.get("receiptId"))
                and all(instruction.get(k) == baseline.get(k) for k in IDENTITY_FIELDS)
            )
            if not matches:
                return self.manual(
                    case,
                    "CONFLICTING_CUSTODIAN_EVIDENCE",
                    "Receipt and instruction do not match saved intent",
                )
            verification = {
                **case.get("verification", {}),
                "receiptId": receipt["receiptId"],
                "verifiedAt": utcnow(),
                "receipt": receipt,
                "instruction": instruction,
                "reads": [
                    f"GET /operations/{operation['operationId']}",
                    f"GET /instructions/{case['caseId']}",
                ],
                "account": instruction["safekeepingAccount"],
                "revision": instruction["revision"],
                "status": instruction["status"],
                "verifiedByWorkerId": self.worker_id,
            }
            return self.save(
                case,
                "VERIFIED",
                {"verification": verification, "learning": {"status": "PENDING", "attempts": 0}},
                Stage.VERIFIED,
                "Receipt and instruction prove the approved effect",
            )
        self.recheck(case, instruction)
        if operation["attemptCount"] >= operation["maxAttempts"]:
            return self.manual(
                case, "RETRY_BUDGET_EXHAUSTED", "Confirmed absent; no retry budget remains"
            )
        retry = self.save(
            case,
            "RETRY_SAME_KEY",
            {
                "operation.attemptCount": operation["attemptCount"] + 1,
                "operation.retryCount": operation.get("retryCount", 0) + 1,
            },
            detail="Confirmed absent; approval and live inputs rechecked; original key only",
        )
        if retry:
            return self.send(retry)
