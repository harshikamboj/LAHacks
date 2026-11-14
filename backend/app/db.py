"""PyMongo durability primitives. No custodian HTTP mutation happens in this module."""

from copy import deepcopy
from datetime import datetime, timezone

from pymongo import MongoClient, ReturnDocument
from pymongo.database import Database
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from app.config import Settings
from app.hashing import proposal_hash
from app.models import CaseDocument, Proposal, Stage

TRANSITIONS = {
    Stage.NEW: {Stage.INVESTIGATING},
    Stage.INVESTIGATING: {Stage.AWAITING_APPROVAL, Stage.MANUAL_REVIEW, Stage.NO_ACTION},
    Stage.AWAITING_APPROVAL: {
        Stage.APPROVED,
        Stage.DENIED,
        Stage.INVESTIGATING,
        Stage.MANUAL_REVIEW,
    },
    Stage.APPROVED: {Stage.INVESTIGATING, Stage.AWAITING_VERIFICATION, Stage.MANUAL_REVIEW},
    Stage.AWAITING_VERIFICATION: {Stage.VERIFIED, Stage.MANUAL_REVIEW},
    Stage.VERIFIED: set(),
    Stage.MANUAL_REVIEW: set(),
    Stage.DENIED: set(),
    Stage.NO_ACTION: set(),
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_client(settings: Settings, *, setup: bool = False) -> MongoClient:
    return MongoClient(
        settings.connection_uri(setup=setup),
        appname="TradeOps-setup" if setup else "TradeOps",
        tz_aware=True,
        serverSelectionTimeoutMS=settings.mongodb_timeout_ms,
        connectTimeoutMS=settings.mongodb_timeout_ms,
        socketTimeoutMS=settings.mongodb_timeout_ms,
    )


def get_database(client: MongoClient, settings: Settings) -> Database:
    # A bounded wtimeout prevents a worker hanging indefinitely before an external action.
    return client.get_database(
        settings.mongodb_db,
        write_concern=WriteConcern("majority", j=True, wtimeout=10000),
        read_concern=ReadConcern("majority"),
    )


class CaseStore:
    def __init__(self, db: Database):
        self.db = db
        self.cases = db.cases

    def create_case(self, case_id="SI-2041", trade_id="TR-2041", portfolio_id="P-17") -> dict:
        now = utcnow()
        doc = CaseDocument(
            caseId=case_id, tradeId=trade_id, portfolioId=portfolio_id, createdAt=now, updatedAt=now
        ).to_bson()
        doc["events"] = [
            {
                "at": now,
                "type": "CASE_OPENED",
                "stage": "NEW",
                "actor": "setup",
                "detail": "Synthetic rejected instruction opened",
                "data": {},
            }
        ]
        # setup is rerunnable: never reset a live checkpoint, approval or runId.
        self.cases.update_one(
            {"caseId": case_id, "synthetic": True}, {"$setOnInsert": doc}, upsert=True
        )
        return self.get(case_id)

    def get(self, case_id: str) -> dict | None:
        return self.cases.find_one({"caseId": case_id, "synthetic": True}, {"_id": 0})

    def cas_update(
        self,
        case_id: str,
        from_stage: Stage,
        expected_version: int,
        to_stage: Stage,
        *,
        run_id: str,
        actor: str,
        event_type: str,
        detail: str,
        fields: dict | None = None,
        unset: tuple[str, ...] = (),
        guards: dict | None = None,
    ) -> dict | None:
        """Atomically checkpoint one expected case version; None means a stale action.

        runId prevents a stale worker from changing a fresh demo run after reset.
        A same-stage update records events/flags without moving the workflow backwards.
        Trusted approval/workflow services own business checks before calling this primitive.
        """
        from_stage, to_stage = Stage(from_stage), Stage(to_stage)
        if from_stage != to_stage and to_stage not in TRANSITIONS[from_stage]:
            raise ValueError(f"Illegal stage transition: {from_stage} -> {to_stage}")
        reserved = {
            "_id",
            "caseId",
            "runId",
            "synthetic",
            "tradeId",
            "portfolioId",
            "version",
            "stage",
            "events",
            "createdAt",
            "updatedAt",
        }
        for key in [*(fields or {}), *unset]:
            if key.startswith("$") or key.split(".")[0] in reserved:
                raise ValueError(f"Cannot override case identity or transition metadata: {key}")
        identity = {
            "caseId": case_id,
            "synthetic": True,
            "runId": run_id,
            "stage": from_stage.value,
            "version": expected_version,
        }
        query = {"$and": [identity, guards]} if guards else identity
        now = utcnow()
        event = {
            "at": now,
            "type": event_type,
            "stage": to_stage.value,
            "actor": actor,
            "detail": detail,
            "data": {},
        }
        update = {
            "$set": {**(fields or {}), "stage": to_stage.value, "updatedAt": now},
            "$inc": {"version": 1},
            "$push": {"events": {"$each": [event], "$slice": -100}},
        }
        if unset:
            update["$unset"] = dict.fromkeys(unset, "")
        return self.cases.find_one_and_update(
            query,
            update,
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )

    def persist_intent(self, case: dict, worker_id: str) -> dict | None:
        """Call ONLY after trusted worker rechecks live custodian/directory evidence.

        Return the acknowledged durable document before sending anything. A DB exception
        (including ambiguous write timeout) MUST stop sending; recover by reading Atlas.
        The worker must reuse the returned operation and payload verbatim on recovery.
        """
        proposal = Proposal.model_validate(case["proposal"]).model_dump()
        # Preserve hashes of older proposals that predate the explicit mappingRevision field.
        digest = proposal_hash(case["proposal"])
        approval = case.get("approval", {})
        policy = self.db.policies.find_one({"policyId": "settlement-amendment", "synthetic": True})
        scope = ("caseId", "runId", "tradeId", "portfolioId")
        if (
            case["stage"] != Stage.APPROVED
            or not case.get("executionRequested")
            or any(proposal[k] != case[k] for k in scope)
            or digest != case.get("proposalHash")
            or digest != approval.get("approvedProposalHash")
            or not policy
            or policy["version"] != proposal["policyVersion"]
            or approval.get("policyVersion") != policy["version"]
            or proposal["mutation"] != policy["allowedMutation"]
            or approval.get("role") != policy["requiredRole"]
            or not any(
                r["reviewerId"] == approval.get("reviewerId")
                and r["role"] == policy["requiredRole"]
                for r in policy["reviewers"]
            )
        ):
            raise ValueError("An authorized, current, exact-proposal approval is required")
        if case.get("operation"):
            raise ValueError("An existing operation intent cannot be replaced")
        operation_id = f"OP-{case['caseId']}-{digest.removeprefix('sha256:')[:8]}"
        payload = {
            "operationId": operation_id,
            "expectedRevision": proposal["expectedRevision"],
            "newAccount": proposal["newAccount"],
        }
        now = utcnow()
        operation = {
            "operationId": operation_id,
            "idempotencyKey": operation_id,
            "payload": payload,
            "attemptCount": 1,
            "maxAttempts": policy["maxAttempts"],
            "retryCount": 0,
            "requestBody": {
                "expectedRevision": proposal["expectedRevision"],
                "accountId": proposal["newAccount"],
            },
            "payloadHash": proposal_hash(
                {
                    "instructionId": proposal["instructionId"],
                    "expectedRevision": proposal["expectedRevision"],
                    "accountId": proposal["newAccount"],
                }
            ),
        }
        checkpoint = {
            "stage": Stage.AWAITING_VERIFICATION.value,
            "operationId": operation_id,
            "savedAt": now,
            "savedByWorkerId": worker_id,
            "writeConcern": "majority",
        }
        # Do not allow a caller-created Database with weak write concern to weaken the intent.
        durable = self.db.with_options(
            write_concern=WriteConcern("majority", j=True, wtimeout=10000)
        )
        return CaseStore(durable).cas_update(
            case["caseId"],
            Stage.APPROVED,
            case["version"],
            Stage.AWAITING_VERIFICATION,
            run_id=case["runId"],
            actor=f"worker:{worker_id}",
            event_type="INTENT_PERSISTED",
            detail="Approved operation checkpoint saved before any custodian PATCH",
            fields={"operation": operation, "checkpoint": checkpoint},
            guards={
                "proposalHash": digest,
                "approval.approvedProposalHash": digest,
                "executionRequested": True,
                "operation": {"$exists": False},
            },
        )

    def list_resumable(self) -> list[dict]:
        return list(
            self.cases.find(
                {
                    "synthetic": True,
                    "stage": {"$in": [Stage.APPROVED.value, Stage.AWAITING_VERIFICATION.value]},
                },
                {"_id": 0},
            ).sort("updatedAt", 1)
        )

    def heartbeat(self, worker_id: str, pid: int) -> None:
        self.db.workers.update_one(
            {"_id": "workflow-worker"},
            {
                "$set": {
                    "workerId": worker_id,
                    "pid": pid,
                    "heartbeatAt": utcnow(),
                    "synthetic": True,
                }
            },
            upsert=True,
        )

    def copy_operation(self, case_id: str) -> dict:
        case = self.get(case_id)
        if not case or case["stage"] != Stage.AWAITING_VERIFICATION:
            raise ValueError("No pending verification checkpoint")
        return deepcopy(case["operation"])
