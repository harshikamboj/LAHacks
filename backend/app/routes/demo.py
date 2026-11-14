"""Demo-mode controls (failure lab, reset, proof). All routes return 403 unless DEMO_MODE=true.

These only touch the synthetic simulators (and, once the case engine exists, the synthetic demo case).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import get_settings
from app.errors import ApiError
from app.services import simulator_clients as sims


def require_demo_mode() -> None:
    if not get_settings().demo_mode:
        raise ApiError(403, "DEMO_MODE_DISABLED", "Demo controls are disabled (set DEMO_MODE=true locally)")


router = APIRouter(prefix="/demo", dependencies=[Depends(require_demo_mode)])

CASE_ENGINE_PENDING = {
    "applied": False,
    "reason": "Needs the workflow worker and the Atlas case store, which are not built yet",
}


class ResetBody(BaseModel):
    confirm: str


class FaultsBody(BaseModel):
    lostResponse: bool | None = None
    operationsUnavailable: bool | None = None
    crashWorkerOnUnknown: bool | None = None


class DirectoryVersionBody(BaseModel):
    version: Literal[1, 2, 3]


@router.post("/reset")
def reset(body: ResetBody):
    if body.confirm != "RESET":
        raise ApiError(400, "CONFIRMATION_REQUIRED", 'Send {"confirm": "RESET"} to reset synthetic demo data')
    return {
        "simulators": {
            "broker": sims.broker().reset(),
            "directory": sims.directory().reset(),
            "custodian": sims.custodian().reset(),
        },
        "atlasCase": CASE_ENGINE_PENDING,
    }


@router.get("/state")
def state():
    return {
        "faults": sims.custodian().get_faults(),
        "directoryContractVersion": sims.directory().get_contract()["version"],
        "crashWorkerOnUnknown": None,  # stored on the Atlas case once the case engine exists
    }


@router.post("/faults")
def faults(body: FaultsBody):
    custodian_faults = sims.custodian().set_faults(
        lost_response=body.lostResponse, operations_unavailable=body.operationsUnavailable)
    result = {"custodian": custodian_faults}
    if body.crashWorkerOnUnknown is not None:
        result["crashWorkerOnUnknown"] = CASE_ENGINE_PENDING
    return result


@router.post("/directory-version")
def directory_version(body: DirectoryVersionBody):
    return sims.directory().set_contract(body.version)


@router.get("/custodian-proof")
def custodian_proof():
    return sims.custodian().proof(get_settings().demo_case_id)
