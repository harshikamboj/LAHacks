"""Opt in: RUN_ATLAS_TESTS=1 RUN_WORKFLOW_TESTS=1 pytest -m workflow.

Real API, simulators and restartable worker processes; unique test case and SQLite stores.
The imported market collection is read-only throughout these tests.
"""

import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.config import Settings
from app.db import create_client, get_database

pytestmark = [
    pytest.mark.atlas,
    pytest.mark.workflow,
    pytest.mark.skipif(
        os.getenv("RUN_WORKFLOW_TESTS") != "1" or os.getenv("RUN_ATLAS_TESTS") != "1",
        reason="Set both RUN_WORKFLOW_TESTS=1 and RUN_ATLAS_TESTS=1",
    ),
]
BACKEND = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Stack:
    def __init__(self, tmp):
        self.tmp, self.processes, self.logs, self.worker = tmp, [], [], None
        self.case_id, self.trade_id = "SI-" + str(uuid4().int), "TR-" + str(uuid4().int)
        self.ports = [free_port() for _ in range(4)]
        s = Settings()
        self.env = {
            **os.environ,
            "MONGODB_URI": s.connection_uri(),
            "DEMO_CASE_ID": self.case_id,
            "DEMO_TRADE_ID": self.trade_id,
            "SIM_DATA_DIR": str(tmp),
            "SIM_ADMIN_TOKEN": "workflow-test-admin",
            "DEMO_REVIEWER_TOKEN": "workflow-test-reviewer",
            "DEMO_MODE": "true",
            "BROKER_URL": f"http://127.0.0.1:{self.ports[0]}",
            "DIRECTORY_URL": f"http://127.0.0.1:{self.ports[1]}",
            "CUSTODIAN_URL": f"http://127.0.0.1:{self.ports[2]}",
            "WORKER_POLL_SECONDS": "0.08",
            "CUSTODIAN_TIMEOUT_SECONDS": "0.5",
            "LOST_RESPONSE_DELAY_SECONDS": "2",
            "WORKER_PID_FILE": str(tmp / "worker.pid"),
        }
        self.client = httpx.Client(
            base_url=f"http://127.0.0.1:{self.ports[3]}",
            timeout=15,
            headers={"X-Reviewer-Token": "workflow-test-reviewer"},
        )
        self.mongo = create_client(s)
        self.db = get_database(self.mongo, s)

    def spawn(self, name, args):
        log = (self.tmp / f"{name}-{len(self.logs)}.log").open("w+")
        self.logs.append(log)
        process = subprocess.Popen(
            [sys.executable, *args], cwd=BACKEND, env=self.env, stdout=log, stderr=subprocess.STDOUT
        )
        self.processes.append(process)
        return process

    def start_servers(self):
        targets = [
            "simulators.broker:create_app",
            "simulators.directory:create_app",
            "simulators.custodian:create_app",
            "app.main:app",
        ]
        for index, (port, target) in enumerate(zip(self.ports, targets, strict=True)):
            args = ["-m", "uvicorn", target, "--host", "127.0.0.1", "--port", str(port)]
            if index < 3:
                args.append("--factory")
            self.spawn(f"server-{index}", args)
            for _ in range(80):
                try:
                    if (
                        httpx.get(f"http://127.0.0.1:{port}/openapi.json", timeout=1).status_code
                        == 200
                    ):
                        break
                except httpx.RequestError:
                    pass
                time.sleep(0.1)
            else:
                raise AssertionError("Server startup failed: " + self.log_tail())

    def log_tail(self):
        out = []
        for log in self.logs:
            log.flush()
            out.append(Path(log.name).read_text()[-1500:])
        return "\n".join(out)

    def stop_worker(self):
        if self.worker and self.worker.poll() is None:
            self.worker.terminate()
            self.worker.wait(timeout=20)
        self.worker = None

    def start_worker(self):
        self.worker = self.spawn("worker", ["-m", "app.worker"])
        return self.worker

    def reset(self, pause=False):
        self.stop_worker()
        r = self.client.post("/api/demo/reset", json={"confirm": "RESET"})
        assert r.status_code == 200, r.text
        self.faults(pauseDirectoryRead=pause)

    def faults(self, **fields):
        for _ in range(15):
            r = self.client.post("/api/demo/faults", json=fields)
            if r.status_code != 409:
                assert r.status_code == 200, r.text
                return
        raise AssertionError("Fault configuration kept conflicting")

    def case(self):
        r = self.client.get(f"/api/cases/{self.case_id}")
        assert r.status_code == 200, r.text
        return r.json()

    def wait(self, stage, timeout=45):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            case = self.case()
            if case["stage"] == stage:
                return case
            if self.worker and self.worker.poll() is not None:
                raise AssertionError(f"Worker exited {self.worker.returncode}: {self.log_tail()}")
            time.sleep(0.12)
        raise AssertionError(f"Expected {stage}; got {self.case()}: {self.log_tail()}")

    def start(self):
        self.start_worker()
        case = self.case()
        r = self.client.post(f"/api/cases/{self.case_id}/start", json={"version": case["version"]})
        assert r.status_code == 200, r.text

    def approve(self):
        case = self.wait("AWAITING_APPROVAL")
        r = self.client.post(
            f"/api/cases/{self.case_id}/decision",
            json={
                "version": case["version"],
                "proposalHash": case["proposalHash"],
                "decision": "APPROVE",
            },
        )
        assert r.status_code == 200, r.text
        return r.json()

    def execute(self):
        case = self.case()
        r = self.client.post(
            f"/api/cases/{self.case_id}/execute", json={"version": case["version"]}
        )
        assert r.status_code == 200, r.text

    def proof(self):
        return self.client.get("/api/demo/custodian-proof").json()

    def sql(self, name, statement):
        with sqlite3.connect(self.tmp / f"{name}.db") as c:
            c.execute(statement)

    def close(self):
        self.stop_worker()
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=20)
        self.db.cases.delete_one({"caseId": self.case_id, "synthetic": True})
        self.db.case_runs.delete_many({"caseId": self.case_id, "synthetic": True})
        self.db.incidents.delete_many({"learningScope": self.case_id, "synthetic": True})
        self.db.workers.delete_one({"_id": f"worker-{self.case_id}"})
        self.client.close()
        self.mongo.close()
        for log in self.logs:
            log.close()


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    s = Stack(tmp_path_factory.mktemp("proofstep"))
    try:
        s.start_servers()
        yield s
    finally:
        s.close()


def test_live_happy_path_and_market_anchor(stack):
    stack.reset()
    stack.start()
    case = stack.wait("AWAITING_APPROVAL")
    obs = case["marketContext"]["observation"]
    assert obs["outstanding_fail_quantity"] == 1277 and obs["prior_close_price"] == "91.14"
    assert case["marketContextId"] == "F92124100:2026-09-15"
    stack.approve()
    stack.execute()
    case = stack.wait("VERIFIED")
    assert case["verification"]["receipt"]["payloadHash"] == case["operation"]["payloadHash"]
    assert (stack.proof()["receiptCount"], stack.proof()["patchRequestCount"]) == (1, 1)


@pytest.mark.parametrize("fault", ["crashWorkerOnUnknown", "crashBeforeSend"])
def test_real_worker_crash_and_restart_without_duplicate_patch(stack, fault):
    stack.reset()
    stack.start()
    stack.approve()
    stack.faults(**{fault: True, "lostResponse": fault == "crashWorkerOnUnknown"})
    stack.execute()
    process = stack.worker
    assert process.wait(timeout=30) == 137, stack.log_tail()
    saved = stack.case()
    assert saved["stage"] == "AWAITING_VERIFICATION"
    op = saved["operation"]["operationId"]
    assert stack.proof()["patchRequestCount"] == (0 if fault == "crashBeforeSend" else 1)
    stack.start_worker()
    recovered = stack.wait("VERIFIED")
    assert recovered["operation"]["operationId"] == op
    assert (
        recovered["verification"]["resumedByWorkerId"] != recovered["checkpoint"]["savedByWorkerId"]
    )
    proof = stack.proof()
    assert (proof["receiptCount"], proof["patchRequestCount"], proof["currentRevision"]) == (
        1,
        1,
        2,
    )


def test_denial_auth_hash_and_stale_guards_make_zero_writes(stack):
    stack.reset()
    stack.start()
    case = stack.wait("AWAITING_APPROVAL")
    url = f"/api/cases/{stack.case_id}/decision"
    payload = {
        "version": case["version"],
        "proposalHash": case["proposalHash"],
        "decision": "APPROVE",
    }
    assert httpx.post(str(stack.client.base_url).rstrip("/") + url, json=payload).status_code == 401
    assert stack.client.post(url, json={**payload, "proposalHash": "wrong"}).status_code == 409
    assert stack.client.post(url, json={**payload, "version": 1}).status_code == 409
    assert stack.client.post(url, json={**payload, "decision": "DENY"}).status_code == 200
    assert stack.case()["stage"] == "DENIED" and stack.proof()["patchRequestCount"] == 0


def test_mapping_revision_change_invalidates_approval(stack):
    stack.reset()
    stack.start()
    stack.approve()
    stack.sql("directory", "UPDATE settings SET value='8' WHERE key='mapping_revision'")
    stack.execute()
    case = stack.wait("AWAITING_APPROVAL")
    assert case["proposal"]["mappingRevision"] == 8 and "approval" not in case
    assert stack.proof()["patchRequestCount"] == 0


def test_actual_midrun_v2_change_is_guided_by_vector_memory(stack):
    stack.reset(pause=True)
    stack.start()
    end = time.monotonic() + 30
    while not stack.case().get("demo", {}).get("directoryPaused"):
        assert time.monotonic() < end
        time.sleep(0.1)
    assert stack.client.post("/api/demo/directory-version", json={"version": 2}).status_code == 200
    stack.faults(pauseDirectoryRead=False)
    case = stack.wait("AWAITING_APPROVAL", timeout=60)
    precedent = case["investigation"]["precedents"][0]
    assert (
        precedent["status"] == "FOUND"
        and precedent["suggestedNextCheck"] == "GET_DIRECTORY_CONTRACT"
    )
    assert any(
        s["tool"] == "get_directory_contract" and s["guidedBy"] == precedent["incidentId"]
        for s in case["investigation"]["steps"]
    )
    assert case["evidence"]["directory"]["contractVersion"] == 2


def test_unknown_contract_and_trade_mismatch_make_zero_writes(stack):
    for scenario in ["unknown", "mismatch"]:
        stack.reset()
        if scenario == "unknown":
            stack.client.post("/api/demo/directory-version", json={"version": 3})
        else:
            stack.sql("broker", "UPDATE trades SET quantity=101")
        stack.start()
        stack.wait("MANUAL_REVIEW", timeout=60)
        assert stack.proof()["patchRequestCount"] == 0


def test_accepted_instruction_no_action_and_unavailable_receipt_no_retry(stack):
    stack.reset()
    stack.sql("custodian", "UPDATE instructions SET status='ACCEPTED'")
    stack.start()
    stack.wait("NO_ACTION")
    assert stack.proof()["patchRequestCount"] == 0
    stack.reset()
    stack.start()
    stack.approve()
    stack.faults(operationsUnavailable=True)
    stack.execute()
    stack.wait("MANUAL_REVIEW")
    assert (stack.proof()["patchRequestCount"], stack.proof()["receiptCount"]) == (1, 1)


def test_reset_requires_worker_stopped_and_preserves_market_and_memory(stack):
    stack.reset()
    stack.start_worker()
    end = time.monotonic() + 20
    while not stack.client.get("/api/health").json()["worker"]["online"]:
        assert time.monotonic() < end
        time.sleep(0.2)
    r = stack.client.post("/api/demo/reset", json={"confirm": "RESET"})
    assert r.status_code == 409
    stack.reset()
    assert stack.db.market_fail_observations.count_documents({}) == 66693
    assert (
        stack.db.incidents.count_documents(
            {"disposition": "VERIFIED", "learnedFromCaseId": {"$exists": False}}
        )
        == 9
    )


def test_verified_result_becomes_real_memory_for_a_distinct_case(stack):
    from app.db import CaseStore

    stack.reset()
    stack.start()
    stack.approve()
    stack.execute()
    stack.wait("VERIFIED")
    end = time.monotonic() + 150
    while stack.case().get("learning", {}).get("status") != "STORED":
        assert time.monotonic() < end, {
            "learning": stack.case().get("learning"),
            "logs": stack.log_tail(),
        }
        time.sleep(0.2)
    stored_case = stack.case()
    retry_url = f"/api/cases/{stack.case_id}/learning/retry"
    assert stack.client.post(retry_url, json={"version": stored_case["version"]}).status_code == 409
    # Exhausted publication may be retried without executing another custodian amendment.
    stack.stop_worker()
    stack.db.cases.update_one(
        {"caseId": stack.case_id},
        {"$set": {"learning": {"status": "PENDING", "attempts": 3, "reason": "VOYAGE_HTTP_429"}}},
    )
    retried = stack.client.post(retry_url, json={"version": stored_case["version"]})
    assert retried.status_code == 200 and retried.json()["learning"]["attempts"] == 0
    assert stack.proof()["patchRequestCount"] == 1
    stack.db.cases.update_one(
        {"caseId": stack.case_id}, {"$set": {"learning": stored_case["learning"]}}
    )
    stack.start_worker()
    incident_id = stack.case()["learning"]["incidentId"]
    incident = stack.db.incidents.find_one({"incidentId": incident_id})
    assert incident["verifiedReceiptId"] == stack.case()["verification"]["receiptId"]
    assert len(incident["embedding"]) == 1024
    # Wait for actual Vector Search indexing, never replace it with an exact lookup/fake score.
    from app.services.memory import IncidentMemory

    memory = IncidentMemory(stack.db, Settings())
    while True:
        result = memory.retrieve(
            "retired receiving account invalid safekeeping account "
            "current receiving account mapping requires validation",
            source="directory:" + stack.case_id,
            limit=10,
        )
        if any(m["incidentId"] == incident_id for m in result["matches"]):
            break
        assert time.monotonic() < end, result
        time.sleep(0.5)
    other_case, other_trade = "SI-" + str(uuid4().int), "TR-" + str(uuid4().int)
    stack.sql(
        "broker",
        f"INSERT INTO trades SELECT '{other_trade}',portfolio_id,side,security,150,price,"
        "currency,status,executed_at,cusip,settlement_date FROM trades "
        f"WHERE trade_id='{stack.trade_id}'",
    )
    stack.sql(
        "custodian",
        f"INSERT INTO instructions SELECT '{other_case}','{other_trade}',portfolio_id,"
        "side,security,150,1,'SAFE-100','REJECTED','INVALID_SAFEKEEPING_ACCOUNT',"
        "rejection_note,NULL,updated_at,cusip,settlement_date FROM instructions "
        f"WHERE instruction_id='{stack.case_id}'",
    )
    CaseStore(stack.db).create_case(other_case, other_trade)
    stack.db.cases.update_one(
        {"caseId": other_case},
        {"$set": {"demoOwner": stack.case_id, "scenarioKind": "similar_exception"}},
    )
    try:
        stack.client.post("/api/demo/directory-version", json={"version": 2}).raise_for_status()
        response = stack.client.post(f"/api/cases/{other_case}/start", json={"version": 1})
        assert response.status_code == 200, response.text
        while True:
            second = stack.client.get(f"/api/cases/{other_case}").json()
            if second["stage"] == "AWAITING_APPROVAL":
                break
            assert time.monotonic() < end + 150, second
            time.sleep(0.2)
        reused = second["investigation"]["reusedExperience"]
        assert reused["incidentId"] == incident_id
        assert reused["learnedFromCaseId"] == stack.case_id and reused["score"] >= 0.7
        steps = second["investigation"]["steps"]
        contract = next(i for i, s in enumerate(steps) if s["tool"] == "get_directory_contract")
        account = next(i for i, s in enumerate(steps) if s["tool"] == "get_directory_account")
        assert contract < account and steps[contract]["guidedBy"] == incident_id
        assert second["proposal"]["caseId"] == other_case and "approval" not in second
        proof = stack.client.get("/api/demo/custodian-proof", params={"caseId": other_case}).json()
        assert proof["patchRequestCount"] == 0  # remembered procedure cannot approve or execute
        assert not stack.db.incidents.find_one({"learnedFromCaseId": other_case})
        approved = stack.client.post(
            f"/api/cases/{other_case}/decision",
            json={
                "version": second["version"],
                "proposalHash": second["proposalHash"],
                "decision": "APPROVE",
            },
        )
        assert approved.status_code == 200, approved.text
        applied = stack.client.post(
            f"/api/cases/{other_case}/execute", json={"version": approved.json()["version"]}
        )
        assert applied.status_code == 200, applied.text
        while True:
            completed = stack.client.get(f"/api/cases/{other_case}").json()
            if completed["stage"] == "VERIFIED":
                break
            assert time.monotonic() < end + 150, completed
            time.sleep(0.2)
        assert completed["operation"]["operationId"] != stored_case["operation"]["operationId"]
        proof = stack.client.get("/api/demo/custodian-proof", params={"caseId": other_case}).json()
        assert (proof["receiptCount"], proof["patchRequestCount"]) == (1, 1)
        assert proof["receipts"][0]["receiptId"] != stored_case["verification"]["receiptId"]
        assert stack.proof()["patchRequestCount"] == 1  # first case was not executed again
    finally:
        stack.db.cases.delete_one({"caseId": other_case})
