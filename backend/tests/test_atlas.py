"""RUN_ATLAS_TESTS=1 pytest -m atlas: real database tests, no simulator claims."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from pymongo.errors import DuplicateKeyError, OperationFailure

from app.config import Settings
from app.db import CaseStore, create_client, get_database, utcnow
from app.hashing import proposal_hash
from app.models import Stage

pytestmark = [
    pytest.mark.atlas,
    pytest.mark.skipif(
        os.getenv("RUN_ATLAS_TESTS") != "1", reason="Set RUN_ATLAS_TESTS=1 for real Atlas checks"
    ),
]


@pytest.fixture(scope="module")
def database():
    settings = Settings()
    with create_client(settings) as client:
        db = get_database(client, settings)
        db.command("ping")
        yield db


@pytest.fixture
def case(database):
    store = CaseStore(database)
    doc = store.create_case("SI-" + str(uuid4().int))
    try:
        yield store, doc
    finally:
        database.cases.delete_one(
            {"caseId": doc["caseId"], "runId": doc["runId"], "synthetic": True}
        )


def advance(store, doc, target, **fields):
    return store.cas_update(
        doc["caseId"],
        doc["stage"],
        doc["version"],
        target,
        run_id=doc["runId"],
        actor="integration-test",
        event_type="TEST_TRANSITION",
        detail="Synthetic isolated test",
        fields=fields,
    )


def approved(store, doc):
    doc = advance(store, doc, Stage.INVESTIGATING)
    proposal = {
        "caseId": doc["caseId"],
        "instructionId": doc["caseId"],
        "runId": doc["runId"],
        "tradeId": doc["tradeId"],
        "portfolioId": doc["portfolioId"],
        "expectedRevision": 1,
        "oldAccount": "SAFE-100",
        "newAccount": "SAFE-401",
        "mutation": "AMEND_SAFEKEEPING_ACCOUNT",
        "policyVersion": "v1",
    }
    digest = proposal_hash(proposal)
    doc = advance(store, doc, Stage.AWAITING_APPROVAL, proposal=proposal, proposalHash=digest)
    return advance(
        store,
        doc,
        Stage.APPROVED,
        executionRequested=True,
        approval={
            "approvedProposalHash": digest,
            "reviewerId": "demo-reviewer",
            "role": "SETTLEMENT_APPROVER",
            "approvedAt": utcnow(),
            "policyVersion": "v1",
            "authMethod": "DEMO_TOKEN",
        },
    )


def test_concurrent_actions_advance_only_once(case):
    store, doc = case
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: advance(store, doc, Stage.INVESTIGATING), range(2)))
    assert sum(r is not None for r in results) == 1
    assert store.get(doc["caseId"])["version"] == doc["version"] + 1


def test_checkpoint_survives_new_python_process_with_same_operation(case):
    store, doc = case
    doc = approved(store, doc)
    persisted = store.persist_intent(doc, "test-worker-before-restart")
    assert persisted["stage"] == Stage.AWAITING_VERIFICATION
    assert persisted["checkpoint"]["writeConcern"] == "majority"
    assert store.persist_intent(doc, "competing-worker") is None
    code = """
import json,sys
from app.config import Settings
from app.db import create_client,get_database,CaseStore
s=Settings()
with create_client(s) as c:
 d=CaseStore(get_database(c,s)).get(sys.argv[1])
 print(json.dumps({'stage':d['stage'],'operation':d['operation']}))
"""
    output = subprocess.check_output([sys.executable, "-c", code, doc["caseId"]], text=True)
    recovered = json.loads(output)
    assert recovered["stage"] == Stage.AWAITING_VERIFICATION
    assert recovered["operation"] == persisted["operation"]
    assert any(c["caseId"] == doc["caseId"] for c in store.list_resumable())


def test_changed_proposal_or_unauthorized_reviewer_cannot_persist_intent(case):
    store, doc = case
    doc = approved(store, doc)
    doc["proposal"]["newAccount"] = "SAFE-402"
    with pytest.raises(ValueError, match="exact-proposal"):
        store.persist_intent(doc, "worker")
    doc = store.get(doc["caseId"])
    doc["approval"]["reviewerId"] = "not-a-reviewer"
    with pytest.raises(ValueError, match="exact-proposal"):
        store.persist_intent(doc, "worker")
    assert "operation" not in store.get(doc["caseId"])


def test_validator_rejects_invalid_stage_and_string_version(case):
    store, doc = case
    for field, value in (("stage", "BAD_STAGE"), ("version", "2")):
        with pytest.raises(OperationFailure) as exc:
            store.cases.update_one({"caseId": doc["caseId"]}, {"$set": {field: value}})
        assert exc.value.code == 121


def test_unique_operation_index_and_partial_filter(case):
    store, doc = case
    other = store.create_case("SI-" + str(uuid4().int))
    try:
        doc = store.persist_intent(approved(store, doc), "worker")
        with pytest.raises(DuplicateKeyError):
            store.cases.update_one(
                {"caseId": other["caseId"]}, {"$set": {"operation": doc["operation"]}}
            )
        # Both started without operation fields, proving the partial index permits it.
        assert "operation" not in store.get(other["caseId"])
    finally:
        store.cases.delete_one(
            {"caseId": other["caseId"], "runId": other["runId"], "synthetic": True}
        )


def test_event_timeline_is_bounded_and_utc(case):
    store, doc = case
    event = doc["events"][0]
    store.cases.update_one(
        {"caseId": doc["caseId"]},
        {"$set": {"events": [{**event, "detail": str(i)} for i in range(100)]}},
    )
    updated = advance(store, doc, Stage.INVESTIGATING)
    assert len(updated["events"]) == 100
    assert updated["events"][0]["detail"] == "1"
    assert updated["updatedAt"].utcoffset().total_seconds() == 0


def test_wrong_run_cannot_modify_fresh_case_and_setup_preserves_existing(case):
    store, doc = case
    assert (
        store.cas_update(
            doc["caseId"],
            Stage.NEW,
            1,
            Stage.INVESTIGATING,
            run_id="previous-demo-run",
            actor="old-worker",
            event_type="TEST",
            detail="stale reset worker",
        )
        is None
    )
    progressed = advance(store, doc, Stage.INVESTIGATING)
    seeded = store.create_case(doc["caseId"])
    assert seeded["runId"] == doc["runId"]
    assert seeded["version"] == progressed["version"]
    assert seeded["stage"] == Stage.INVESTIGATING


def test_runtime_user_cannot_read_unrelated_database(database):
    with pytest.raises(OperationFailure):
        database.client["tradeops_unrelated_access_probe"].list_collection_names()
