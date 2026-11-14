"""Custodian idempotency contract — the receiving side of the exactly-once guarantee."""

from __future__ import annotations

OP = "OP-SI-2041-3fa9c1d2"
BODY = {"expectedRevision": 1, "newAccount": "SAFE-401", "operationId": OP}


def patch(client, body=BODY, key=OP):
    headers = {"Idempotency-Key": key} if key else {}
    return client.patch("/instructions/SI-2041", json=body, headers=headers)


def proof(client):
    return client.get("/admin/proof", params={"instructionId": "SI-2041"}).json()


def test_seeded_instruction_is_rejected_on_retired_account(custodian):
    r = custodian.get("/instructions/SI-2041").json()
    assert (r["revision"], r["status"], r["safekeepingAccount"]) == (1, "REJECTED", "SAFE-100")
    assert r["tradeId"] == "TR-2041"
    p = proof(custodian)
    assert p["receiptCount"] == 0 and p["patchRequestCount"] == 0


def test_first_patch_commits_one_receipt_and_one_revision(custodian):
    r = patch(custodian)
    assert r.status_code == 200, r.text
    receipt = r.json()
    assert receipt["replayed"] is False
    assert (receipt["previousRevision"], receipt["resultRevision"]) == (1, 2)

    instr = custodian.get("/instructions/SI-2041").json()
    assert (instr["revision"], instr["status"], instr["safekeepingAccount"]) == (2, "ACCEPTED", "SAFE-401")
    assert instr["latestOperationId"] == OP

    op = custodian.get(f"/operations/{OP}").json()
    assert op["receiptId"] == receipt["receiptId"]
    assert proof(custodian)["receiptCount"] == 1


def test_same_key_same_payload_returns_original_receipt(custodian):
    first = patch(custodian).json()
    second = patch(custodian)
    assert second.status_code == 200
    assert second.json()["receiptId"] == first["receiptId"]
    assert second.json()["replayed"] is True

    p = proof(custodian)
    assert p["receiptCount"] == 1
    assert p["currentRevision"] == 2
    assert [r["revision"] for r in p["revisions"]] == [1, 2]
    assert p["patchRequestCount"] == 2  # both requests arrived; only one changed anything


def test_known_key_is_checked_before_stale_revision(custodian):
    """After commit the instruction is at rev 2, so expectedRevision=1 is stale —
    but a replay of the known key must still return the original receipt, not 409."""
    first = patch(custodian).json()
    replay = patch(custodian)
    assert replay.status_code == 200
    assert replay.json()["receiptId"] == first["receiptId"]


def test_same_key_different_payload_is_rejected(custodian):
    patch(custodian)
    r = patch(custodian, body={**BODY, "newAccount": "SAFE-999"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    p = proof(custodian)
    assert p["receiptCount"] == 1 and p["currentAccount"] == "SAFE-401"


def test_new_key_against_amended_instruction_is_stale(custodian):
    patch(custodian)
    other = "OP-SI-2041-deadbeef"
    r = patch(custodian, body={**BODY, "operationId": other}, key=other)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "STALE_REVISION"
    assert proof(custodian)["receiptCount"] == 1


def test_missing_or_mismatched_key_is_rejected_without_writes(custodian):
    assert patch(custodian, key=None).json()["error"]["code"] == "MISSING_IDEMPOTENCY_KEY"
    assert patch(custodian, key="OP-SI-2041-other").json()["error"]["code"] == "KEY_OPERATION_MISMATCH"
    p = proof(custodian)
    assert p["receiptCount"] == 0 and p["currentRevision"] == 1


def test_invalid_account_rejected(custodian):
    r = patch(custodian, body={**BODY, "newAccount": "DROP TABLE"})
    assert r.json()["error"]["code"] == "INVALID_ACCOUNT"
    assert proof(custodian)["receiptCount"] == 0


def test_lost_response_fault_still_commits_and_is_one_shot(custodian, admin_headers):
    armed = custodian.post("/admin/faults", json={"lostResponse": True}, headers=admin_headers)
    assert armed.json()["lostResponse"] is True

    patch(custodian)  # reply is held (delay=0 in tests), but the commit happened first
    p = proof(custodian)
    assert p["receiptCount"] == 1 and p["currentRevision"] == 2
    assert p["patchRequests"][0]["outcome"] == "COMMITTED_RESPONSE_DROPPED"
    assert custodian.get("/admin/faults").json()["lostResponse"] is False  # consumed

    # Recovery path: the operation record proves the outcome without a second PATCH.
    assert custodian.get(f"/operations/{OP}").status_code == 200
    assert proof(custodian)["patchRequestCount"] == 1


def test_operation_lookup_distinguishes_absent_from_unavailable(custodian, admin_headers):
    absent = custodian.get(f"/operations/{OP}")
    assert absent.status_code == 404
    assert absent.json()["error"]["details"]["confirmedAbsent"] is True

    custodian.post("/admin/faults", json={"operationsUnavailable": True}, headers=admin_headers)
    unavailable = custodian.get(f"/operations/{OP}")
    assert unavailable.status_code == 503
    assert "confirmedAbsent" not in unavailable.json()["error"]["details"]


def test_admin_routes_require_token(custodian):
    assert custodian.post("/admin/faults", json={"lostResponse": True}).status_code == 401
    assert custodian.post("/admin/reset", headers={"X-Sim-Admin": "wrong"}).status_code == 401


def test_reset_restores_rejected_baseline(custodian, admin_headers):
    patch(custodian)
    assert custodian.post("/admin/reset", headers=admin_headers).status_code == 200
    p = proof(custodian)
    assert (p["currentRevision"], p["status"], p["receiptCount"], p["patchRequestCount"]) == (1, "REJECTED", 0, 0)


def test_already_accepted_instruction_cannot_be_amended_with_new_key(custodian):
    patch(custodian)
    other = "OP-SI-2041-cafef00d"
    r = patch(custodian, body={"expectedRevision": 2, "newAccount": "SAFE-401", "operationId": other}, key=other)
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_AMENDABLE"
    assert proof(custodian)["receiptCount"] == 1
