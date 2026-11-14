"""Reset the single active demo safely, preserving previous runs and imported market data."""

from uuid import uuid4

from app.db import CaseStore, utcnow
from app.errors import ApiError
from app.models import CaseDocument
from app.scenarios import scenarios
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
        fresh = []
        batch_id = uuid4().hex
        for case_id, trade_id, title, kind in scenarios(settings):
            old = store.get(case_id)
            if old:
                db.case_runs.update_one(
                    {"caseId": old["caseId"], "runId": old["runId"]},
                    {"$setOnInsert": old},
                    upsert=True,
                )
            now = utcnow()
            case = CaseDocument(
                caseId=case_id, tradeId=trade_id, portfolioId="P-17", createdAt=now, updatedAt=now
            ).to_bson()
            case.update(
                demoOwner=settings.demo_case_id,
                demoBatchId=batch_id,
                title=title,
                scenarioKind=kind,
            )
            case["demo"] = {
                "pauseDirectoryRead": case_id == settings.demo_case_id,
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
                    "detail": "Synthetic work queue case opened; public data preserved",
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
            fresh.append(case)
        case = fresh[0]
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
