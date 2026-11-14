"""Case control API: records intent; never sends a custodian amendment."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth import reviewer
from app.config import get_settings
from app.db import CaseStore, utcnow
from app.errors import ApiError
from app.hashing import proposal_hash
from app.models import Stage, bson_public
from app.routes.health import worker_status
from app.runtime import database
from app.scenarios import scope_filter

router = APIRouter(prefix="/cases")


def get_case(case_id: str) -> dict:
    case = CaseStore(database()).get(case_id)
    if not case or (
        case["caseId"] != get_settings().demo_case_id
        and case.get("demoOwner") != get_settings().demo_case_id
    ):
        raise ApiError(404, "CASE_NOT_FOUND", "Initialize or reset the demo first")
    return case


def public_case(case: dict) -> dict:
    return bson_public(
        {
            **case,
            "demoRunId": case["runId"],
            "instructionId": case["caseId"],
            "intent": case.get("operation"),
            "timeline": case.get("events", []),
            "worker": worker_status(database()),
        }
    )


class VersionBody(BaseModel):
    version: int = Field(ge=1, strict=True)


class DecisionBody(VersionBody):
    proposalHash: str
    decision: Literal["APPROVE", "DENY"] = "APPROVE"


def transition(case, body, stage, event, actor, fields=None):
    updated = CaseStore(database()).cas_update(
        case["caseId"],
        case["stage"],
        body.version,
        stage,
        run_id=case["runId"],
        actor=actor,
        event_type=event,
        detail=event.replace("_", " ").capitalize(),
        fields=fields,
    )
    if not updated:
        raise ApiError(409, "STAGE_CONFLICT", "Case changed; refresh before acting")
    return public_case(updated)


@router.get("")
def list_cases():
    return bson_public(
        list(
            database()
            .cases.find({"synthetic": True, **scope_filter(get_settings())}, {"_id": 0})
            .sort("caseId", 1)
        )
    )


@router.get("/{case_id}")
def detail(case_id: str):
    return public_case(get_case(case_id))


@router.get("/{case_id}/timeline")
def timeline(case_id: str):
    return {"events": bson_public(get_case(case_id).get("events", []))}


@router.post("/{case_id}/start")
@router.post("/{case_id}/investigate")
def start(case_id: str, body: VersionBody, actor=Depends(reviewer)):
    case = get_case(case_id)
    if case.get("scenarioKind") == "similar_exception":
        previous = CaseStore(database()).get(get_settings().demo_case_id) or {}
        if (
            previous.get("stage") != Stage.VERIFIED
            or previous.get("learning", {}).get("status") != "STORED"
        ):
            raise ApiError(
                409,
                "EXPERIENCE_NOT_READY",
                "Complete the first correction and wait for verified experience to save",
            )
    if case["stage"] != Stage.NEW:
        raise ApiError(409, "STAGE_CONFLICT", "Investigation already started")
    return transition(
        case,
        body,
        Stage.INVESTIGATING,
        "INVESTIGATION_REQUESTED",
        "reviewer:" + actor["reviewerId"],
    )


@router.post("/{case_id}/decision")
@router.post("/{case_id}/approve")
def decide(case_id: str, body: DecisionBody, actor=Depends(reviewer)):
    case = get_case(case_id)
    if case["stage"] != Stage.AWAITING_APPROVAL:
        raise ApiError(409, "STAGE_CONFLICT", "No proposal awaiting approval")
    if body.proposalHash != case.get("proposalHash") or body.proposalHash != proposal_hash(
        case.get("proposal", {})
    ):
        raise ApiError(409, "PROPOSAL_HASH_MISMATCH", "Approve the current exact proposal")
    policy = database().policies.find_one({"policyId": "settlement-amendment", "synthetic": True})
    if not policy or case["proposal"]["policyVersion"] != policy["version"]:
        raise ApiError(409, "POLICY_VERSION_MISMATCH", "Policy changed; a new proposal is required")
    approval = {
        **actor,
        "approvedAt": utcnow(),
        "decision": body.decision,
        "approvedProposalHash": body.proposalHash,
        "policyVersion": policy["version"],
    }
    denied = body.decision == "DENY"
    return transition(
        case,
        body,
        Stage.DENIED if denied else Stage.APPROVED,
        "DENIED" if denied else "APPROVED",
        "reviewer:" + actor["reviewerId"],
        {"approval": approval, "executionRequested": False},
    )


@router.post("/{case_id}/execute")
def execute(case_id: str, body: VersionBody, actor=Depends(reviewer)):
    case = get_case(case_id)
    if case["stage"] != Stage.APPROVED or case.get("executionRequested"):
        raise ApiError(409, "STAGE_CONFLICT", "The current case is not ready to execute")
    return transition(
        case,
        body,
        Stage.APPROVED,
        "EXECUTION_REQUESTED",
        "reviewer:" + actor["reviewerId"],
        {"executionRequested": True},
    )


@router.post("/{case_id}/learning/retry")
def retry_learning(case_id: str, body: VersionBody, actor=Depends(reviewer)):
    case = get_case(case_id)
    if (
        case["stage"] != Stage.VERIFIED
        or case.get("learning", {}).get("status") != "PENDING"
        or case.get("learning", {}).get("attempts", 0) < 3
    ):
        raise ApiError(
            409, "STAGE_CONFLICT", "Experience is already saved or still being processed"
        )
    return transition(
        case,
        body,
        Stage.VERIFIED,
        "EXPERIENCE_RETRY_REQUESTED",
        "reviewer:" + actor["reviewerId"],
        {"learning": {"status": "PENDING", "attempts": 0}},
    )
