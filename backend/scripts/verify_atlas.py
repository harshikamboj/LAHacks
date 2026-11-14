"""Real Atlas checks, with exact cleanup of only this invocation's synthetic probes."""

import argparse
import json
from uuid import uuid4

from pymongo.errors import DuplicateKeyError, OperationFailure, PyMongoError

from app.config import Settings
from app.db import CaseStore, create_client, get_database, utcnow
from app.models import Stage
from app.services.memory import IncidentMemory


def verify(db, settings, *, require_memory=False):
    probe_id = "tradeops-probe-" + uuid4().hex
    case_id = "SI-" + str(uuid4().int)
    store = CaseStore(db)
    checks = {}
    try:
        # db has majority+j write concern; a failure raises and prevents a passing report.
        db.healthcheck.insert_one({"_id": probe_id, "synthetic": True, "at": utcnow()})
        checks["majorityJournaledWriteRead"] = bool(db.healthcheck.find_one({"_id": probe_id}))
        case = store.create_case(case_id)
        args = (case_id, Stage.NEW, case["version"], Stage.INVESTIGATING)
        kwargs = {
            "run_id": case["runId"],
            "actor": "atlas-probe",
            "event_type": "INVESTIGATION_REQUESTED",
            "detail": "Isolated database probe",
        }
        checks["conditionalUpdate"] = store.cas_update(*args, **kwargs) is not None
        checks["staleUpdateRejected"] = store.cas_update(*args, **kwargs) is None
        try:
            db.cases.insert_one({k: v for k, v in case.items() if k != "_id"})
            checks["duplicateCaseRejected"] = False
        except DuplicateKeyError:
            checks["duplicateCaseRejected"] = True
        try:
            db.cases.update_one(
                {"caseId": case_id, "runId": case["runId"]},
                {"$set": {"stage": "NOT_A_VALID_STAGE"}},
            )
            checks["invalidStageRejected"] = False
        except OperationFailure as exc:
            checks["invalidStageRejected"] = exc.code == 121
        memory = IncidentMemory(db, settings)
        result = memory.retrieve("directory payload moved the account field")
        checks["memory"] = result
        checks["memoryExpectedFirstHit"] = (
            result["status"] == "FOUND" and result["matches"][0]["incidentId"] == "INC-004"
        )
        core = all(v for k, v in checks.items() if k not in {"memory", "memoryExpectedFirstHit"})
        passed = core and (checks["memoryExpectedFirstHit"] or not require_memory)
        return {"corePassed": core, "passed": passed, "checks": checks}
    finally:
        db.healthcheck.delete_one({"_id": probe_id, "synthetic": True})
        db.cases.delete_one({"caseId": case_id, "synthetic": True})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-memory", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    try:
        with create_client(settings) as client:
            report = verify(
                get_database(client, settings), settings, require_memory=args.require_memory
            )
        print(json.dumps(report, indent=2))
        return 0 if report["passed"] else 1
    except (PyMongoError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "errorType": type(exc).__name__,
                    "errorCode": getattr(exc, "code", None),
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
