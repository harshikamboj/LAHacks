"""Demo-mode controls (failure lab, reset, proof). All routes return 403 unless DEMO_MODE=true.

These only touch the synthetic simulators and the active synthetic demo case.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import reviewer
from app.config import get_settings
from app.db import CaseStore
from app.errors import ApiError
from app.lifecycle import reset_demo
from app.routes.cases import get_case
from app.runtime import database
from app.services import simulator_clients as sims


def require_demo_mode() -> None:
    if not get_settings().demo_mode:
        raise ApiError(
            403, "DEMO_MODE_DISABLED", "Demo controls are disabled (set DEMO_MODE=true locally)"
        )


router = APIRouter(prefix="/demo", dependencies=[Depends(require_demo_mode)])


class ResetBody(BaseModel):
    confirm: str


class FaultsBody(BaseModel):
    caseId: str | None = None
    lostResponse: bool | None = None
    operationsUnavailable: bool | None = None
    crashWorkerOnUnknown: bool | None = None
    pauseDirectoryRead: bool | None = None
    crashBeforeSend: bool | None = None


class DirectoryVersionBody(BaseModel):
    version: Literal[1, 2, 3]


@router.post("/reset")
def reset(body: ResetBody, actor=Depends(reviewer)):
    if body.confirm != "RESET":
        raise ApiError(
            400, "CONFIRMATION_REQUIRED", 'Send {"confirm": "RESET"} to reset synthetic demo data'
        )
    return reset_demo(database(), get_settings(), sims.broker(), sims.directory(), sims.custodian())


@router.get("/state")
def state(caseId: str | None = None):
    case = get_case(caseId or get_settings().demo_case_id)
    return {
        "faults": sims.custodian().get_faults(),
        "directoryContractVersion": sims.directory().get_contract()["version"],
        **{
            name: case.get("demo", {}).get(name, False)
            for name in (
                "crashWorkerOnUnknown",
                "pauseDirectoryRead",
                "directoryPaused",
                "crashBeforeSend",
            )
        },
    }


@router.post("/faults")
def faults(body: FaultsBody, actor=Depends(reviewer)):
    store = CaseStore(database())
    case = get_case(body.caseId or get_settings().demo_case_id)
    if not case:
        raise ApiError(404, "CASE_NOT_FOUND", "Reset demo first")
    flags = {
        f"demo.{key}": value
        for key, value in body.model_dump().items()
        if key in {"crashWorkerOnUnknown", "pauseDirectoryRead", "crashBeforeSend"}
        and value is not None
    }
    if body.pauseDirectoryRead is False:
        flags["demo.directoryPaused"] = False
    updated = store.cas_update(
        case["caseId"],
        case["stage"],
        case["version"],
        case["stage"],
        run_id=case["runId"],
        actor="reviewer:" + actor["reviewerId"],
        event_type="FAULT_CONFIGURED",
        detail="Demo faults configured",
        fields=flags,
    )
    if not updated:
        raise ApiError(409, "STAGE_CONFLICT", "Case changed; retry the control")
    custodian_faults = sims.custodian().set_faults(
        lost_response=body.lostResponse, operations_unavailable=body.operationsUnavailable
    )
    result = {"custodian": custodian_faults}
    result["demo"] = updated.get("demo", {})
    return result


@router.post("/directory-version")
def directory_version(body: DirectoryVersionBody, actor=Depends(reviewer)):
    return sims.directory().set_contract(body.version)


@router.get("/custodian-proof")
def custodian_proof(caseId: str | None = None):
    case = get_case(caseId or get_settings().demo_case_id)
    return sims.custodian().proof(case["caseId"])
