"""Reset the single active demo safely, preserving previous runs and imported market data."""

from uuid import uuid4

from app.db import CaseStore, utcnow
from app.errors import ApiError
from app.models import CaseDocument
from app.worker import claim_lease


def reset_demo(db, settings, broker, directory, custodian):
    reset_id = "reset-" + uuid4().hex
    if not claim_lease(db, settings.worker_record_id, reset_id, 0):
        raise ApiError(409, "WORKER_RUNNING", "Stop the worker before resetting the demo")
    try:
        results = {
            "broker": broker.reset(),
            "directory": directory.reset(),
            "custodian": custodian.reset(),
        }
        store = CaseStore(db)
        old = store.get(settings.demo_case_id)
        if old:
            db.case_runs.update_one(
                {"caseId": old["caseId"], "runId": old["runId"]}, {"$setOnInsert": old}, upsert=True
            )
        now = utcnow()
        case = CaseDocument(
            caseId=settings.demo_case_id,
            tradeId=settings.demo_trade_id,
            portfolioId="P-17",
            createdAt=now,
            updatedAt=now,
        ).to_bson()
        case["demo"] = {
            "pauseDirectoryRead": True,
            "directoryPaused": False,
            "crashWorkerOnUnknown": False,
            "crashBeforeSend": False,
        }
        case["events"] = [
            {
                "at": now,
                "type": "CASE_OPENED",
                "stage": "NEW",
                "actor": "reviewer",
                "detail": "Fresh synthetic TTE demo run; public market data preserved",
            }
        ]
        if old:
            result = db.cases.replace_one(
                {"caseId": old["caseId"], "runId": old["runId"], "synthetic": True}, case
            )
            if not result.matched_count:
                raise ApiError(409, "RESET_CONFLICT", "Case changed while resetting")
        else:
            db.cases.insert_one(case)
        return {
            "simulators": results,
            "atlasCase": {
                "applied": True,
                "caseId": case["caseId"],
                "runId": case["runId"],
                "stage": "NEW",
            },
        }
    finally:
        db.workers.update_one(
            {"_id": settings.worker_record_id, "workerId": reset_id},
            {"$set": {"leaseUntil": utcnow(), "stoppedAt": utcnow()}},
        )
