"""Run one leased workflow worker. Restarting this process resumes Atlas checkpoints."""

import os
import signal
import threading
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.config import REPO_ROOT, Settings
from app.db import create_client, get_database, utcnow
from app.services.workflow import Workflow


def claim_lease(db, key, worker_id, pid):
    now = utcnow()
    try:
        return db.workers.find_one_and_update(
            {
                "_id": key,
                "$or": [{"leaseUntil": {"$lte": now}}, {"leaseUntil": {"$exists": False}}],
            },
            {
                "$set": {
                    "workerId": worker_id,
                    "pid": pid,
                    "heartbeatAt": now,
                    "leaseUntil": now + timedelta(seconds=5),
                    "synthetic": True,
                },
                "$unset": {"stoppedAt": ""},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        return None


def main():
    settings = Settings()
    worker_id = f"worker-{os.getpid()}-{uuid4().hex[:6]}"
    stop, lease_lost = threading.Event(), threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    pid_file = Path(os.getenv("WORKER_PID_FILE", REPO_ROOT / "backend/.runtime/worker.pid"))
    with create_client(settings) as client:
        db = get_database(client, settings)
        for _ in range(12):
            if claim_lease(db, settings.worker_record_id, worker_id, os.getpid()):
                break
            if stop.wait(1):
                return 0
        else:
            print(
                "Another worker/reset owns this case's lease; refusing a second worker", flush=True
            )
            return 2
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()))

        def owns_lease():
            return not lease_lost.is_set() and bool(
                db.workers.find_one(
                    {
                        "_id": settings.worker_record_id,
                        "workerId": worker_id,
                        "leaseUntil": {"$gt": utcnow()},
                    }
                )
            )

        def heartbeat():
            while not stop.wait(1):
                try:
                    now = utcnow()
                    updated = db.workers.update_one(
                        {"_id": settings.worker_record_id, "workerId": worker_id},
                        {"$set": {"heartbeatAt": now, "leaseUntil": now + timedelta(seconds=5)}},
                    )
                    if not updated.matched_count:
                        lease_lost.set()
                        stop.set()
                except PyMongoError:
                    lease_lost.set()
                    stop.set()

        beat = threading.Thread(target=heartbeat, daemon=True)
        beat.start()
        engine = Workflow(db, settings, worker_id, owns_lease=owns_lease)
        print(f"{worker_id}: online; resuming saved case stages (no history replay)", flush=True)
        try:
            while not stop.is_set():
                case = db.cases.find_one(
                    {
                        "caseId": settings.demo_case_id,
                        "synthetic": True,
                        "stage": {"$in": ["INVESTIGATING", "APPROVED", "AWAITING_VERIFICATION"]},
                    },
                    {"_id": 0},
                )
                if case and owns_lease():
                    updated = engine.step(case)
                    if updated:
                        print(
                            f"{worker_id}: {updated['stage']} v{updated['version']} "
                            f"{updated['events'][-1]['type']}",
                            flush=True,
                        )
                stop.wait(settings.worker_poll_seconds)
        except PyMongoError as exc:
            print(
                f"Worker stopped on database error ({type(exc).__name__}); no new send", flush=True
            )
            return 3
        finally:
            stop.set()
            beat.join(timeout=12)
            db.workers.update_one(
                {"_id": settings.worker_record_id, "workerId": worker_id},
                {"$set": {"leaseUntil": utcnow(), "stoppedAt": utcnow()}},
            )
            if pid_file.exists() and pid_file.read_text().strip() == str(os.getpid()):
                pid_file.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
