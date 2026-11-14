"""Custodian simulator — authority for the instruction, the amendment outcome and the receipt.

The exactly-once guarantee lives here, on the receiving side:
  * every PATCH carries an Idempotency-Key (= the worker's stable operationId);
  * a known key is checked BEFORE the revision check, so a replay returns the original receipt;
  * a known key with a different payload is rejected;
  * the instruction change, its revision row and its receipt commit in ONE SQLite transaction;
  * the `lost_response` fault drops the reply only AFTER that commit, so the change is durable
    even though the caller never hears back.

Run: uv run uvicorn simulators.custodian:create_app --factory --port 8103
"""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header
from pydantic import BaseModel

from simulators.common import (
    Store,
    canonical_hash,
    data_dir,
    ensure_columns,
    error,
    load_fixture,
    require_admin,
    utc_now,
)

SOURCE = "SIMULATED_CUSTODIAN"
ACCOUNT_RE = re.compile(r"^SAFE-[0-9]+$")
FAULT_NAMES = ("lost_response", "operations_unavailable")

SCHEMA = """
CREATE TABLE IF NOT EXISTS instructions (
    instruction_id      TEXT PRIMARY KEY,
    trade_id            TEXT NOT NULL,
    portfolio_id        TEXT NOT NULL,
    side                TEXT NOT NULL,
    security            TEXT NOT NULL,
    quantity            INTEGER NOT NULL,
    revision            INTEGER NOT NULL,
    safekeeping_account TEXT NOT NULL,
    status              TEXT NOT NULL,
    rejection_reason    TEXT,
    rejection_note      TEXT,
    latest_operation_id TEXT,
    updated_at          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS instruction_revisions (
    instruction_id      TEXT NOT NULL,
    revision            INTEGER NOT NULL,
    safekeeping_account TEXT NOT NULL,
    status              TEXT NOT NULL,
    operation_id        TEXT,
    created_at          TEXT NOT NULL,
    PRIMARY KEY (instruction_id, revision)
);
CREATE TABLE IF NOT EXISTS operations (
    idempotency_key   TEXT PRIMARY KEY,
    operation_id      TEXT NOT NULL UNIQUE,
    receipt_id        TEXT NOT NULL UNIQUE,
    instruction_id    TEXT NOT NULL,
    payload_hash      TEXT NOT NULL,
    payload_json      TEXT NOT NULL,
    previous_revision INTEGER NOT NULL,
    result_revision   INTEGER NOT NULL,
    account           TEXT NOT NULL,
    status            TEXT NOT NULL,
    created_at        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS patch_requests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    instruction_id  TEXT NOT NULL,
    idempotency_key TEXT,
    outcome         TEXT NOT NULL,
    received_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS faults (
    name  TEXT PRIMARY KEY,
    armed INTEGER NOT NULL DEFAULT 0
);
"""


class AmendBody(BaseModel):
    expectedRevision: int
    newAccount: str | None = None
    operationId: str | None = None
    accountId: str | None = None


class FaultsBody(BaseModel):
    lostResponse: bool | None = None
    operationsUnavailable: bool | None = None


def seed(store: Store) -> None:
    """Reset to the canonical rejected instruction; clear receipts, PATCH log and faults."""
    now = utc_now()
    with store.lock:
        c = store.conn
        c.execute("BEGIN IMMEDIATE")
        for table in (
            "instructions",
            "instruction_revisions",
            "operations",
            "patch_requests",
            "faults",
        ):
            c.execute(f"DELETE FROM {table}")
        for i in load_fixture("instructions.json"):
            c.execute(
                "INSERT INTO instructions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    i["instructionId"],
                    i["tradeId"],
                    i["portfolioId"],
                    i["side"],
                    i["security"],
                    i["quantity"],
                    i["revision"],
                    i["safekeepingAccount"],
                    i["status"],
                    i["rejectionReason"],
                    i["rejectionNote"],
                    None,
                    now,
                    i["cusip"],
                    i["settlementDate"],
                ),
            )
            c.execute(
                "INSERT INTO instruction_revisions VALUES (?,?,?,?,?,?)",
                (
                    i["instructionId"],
                    i["revision"],
                    i["safekeepingAccount"],
                    i["status"],
                    None,
                    now,
                ),
            )
        for name in FAULT_NAMES:
            c.execute("INSERT INTO faults(name, armed) VALUES (?, 0)", (name,))
        c.execute("COMMIT")


def _instruction_json(row) -> dict:
    return {
        "instructionId": row["instruction_id"],
        "tradeId": row["trade_id"],
        "portfolioId": row["portfolio_id"],
        "side": row["side"],
        "security": row["security"],
        "quantity": row["quantity"],
        "revision": row["revision"],
        "safekeepingAccount": row["safekeeping_account"],
        "status": row["status"],
        "rejectionReason": row["rejection_reason"],
        "rejectionNote": row["rejection_note"],
        "latestOperationId": row["latest_operation_id"],
        "updatedAt": row["updated_at"],
        "source": SOURCE,
        "cusip": row["cusip"],
        "symbol": row["security"],
        "settlementDate": row["settlement_date"],
    }


def _receipt_json(row) -> dict:
    return {
        "receiptId": row["receipt_id"],
        "operationId": row["operation_id"],
        "instructionId": row["instruction_id"],
        "previousRevision": row["previous_revision"],
        "resultRevision": row["result_revision"],
        "account": row["account"],
        "status": row["status"],
        "committedAt": row["created_at"],
        "payloadHash": row["payload_hash"],
        "accountId": row["account"],
        "revision": row["result_revision"],
        "appliedAt": row["created_at"],
        "source": SOURCE,
    }


def create_app(db_path: Path | None = None) -> FastAPI:
    store = Store(db_path or data_dir() / "custodian.db")
    store.script(SCHEMA)
    ensure_columns(store, "instructions", ("cusip", "settlement_date"))
    if store.query_one("SELECT COUNT(*) AS n FROM instructions")["n"] == 0:
        seed(store)

    app = FastAPI(title="Custodian simulator (synthetic)", version="1")
    app.state.store = store

    def fault_armed(name: str) -> bool:
        row = store.query_one("SELECT armed FROM faults WHERE name = ?", (name,))
        return bool(row and row["armed"])

    def log_request(instruction_id: str, key: str | None, outcome: str) -> None:
        with store.lock:
            store.conn.execute(
                "INSERT INTO patch_requests(instruction_id, idempotency_key, outcome, received_at) "
                "VALUES (?,?,?,?)",
                (instruction_id, key, outcome, utc_now()),
            )

    @app.get("/health")
    def health():
        return {"ok": True, "source": SOURCE}

    @app.get("/instructions/{instruction_id}")
    def get_instruction(instruction_id: str):
        row = store.query_one(
            "SELECT * FROM instructions WHERE instruction_id = ?", (instruction_id,)
        )
        if row is None:
            return error(404, "INSTRUCTION_NOT_FOUND", f"No instruction {instruction_id}")
        return _instruction_json(row)

    # Plain `def` (not async) so FastAPI runs it in a worker thread and time.sleep is safe.
    @app.patch("/instructions/{instruction_id}")
    def amend_instruction(
        instruction_id: str,
        body: AmendBody,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        if not idempotency_key:
            log_request(instruction_id, None, "REJECTED_MISSING_KEY")
            return error(400, "MISSING_IDEMPOTENCY_KEY", "Idempotency-Key header is required")
        if body.operationId and idempotency_key != body.operationId:
            log_request(instruction_id, idempotency_key, "REJECTED_KEY_MISMATCH")
            return error(
                400, "KEY_OPERATION_MISMATCH", "Idempotency-Key must equal body.operationId"
            )
        account = body.accountId or body.newAccount
        if body.accountId and body.newAccount and body.accountId != body.newAccount:
            return error(400, "CONFLICTING_ACCOUNT_FIELDS", "Account fields disagree")
        if not account or not ACCOUNT_RE.fullmatch(account):
            log_request(instruction_id, idempotency_key, "REJECTED_INVALID_ACCOUNT")
            return error(
                400, "INVALID_ACCOUNT", f"{body.newAccount!r} is not a SAFE-<digits> account"
            )

        body.newAccount = account
        body.operationId = idempotency_key
        payload = {
            "instructionId": instruction_id,
            "expectedRevision": body.expectedRevision,
            "accountId": body.newAccount,
        }
        payload_hash = canonical_hash(payload)
        drop_response = False

        with store.lock:
            c = store.conn
            c.execute("BEGIN IMMEDIATE")
            try:
                # 1. Known key first — before any revision check.
                existing = c.execute(
                    "SELECT * FROM operations WHERE idempotency_key = ?", (idempotency_key,)
                ).fetchone()
                if existing is not None:
                    if existing["payload_hash"] == payload_hash:
                        outcome = "REPLAYED_ORIGINAL_RECEIPT"
                        response = {**_receipt_json(existing), "replayed": True}
                    else:
                        outcome = "REJECTED_KEY_REUSED"
                        response = error(
                            409,
                            "IDEMPOTENCY_KEY_REUSED",
                            "This Idempotency-Key was already used with a different payload",
                            {"operationId": existing["operation_id"]},
                        )
                else:
                    instr = c.execute(
                        "SELECT * FROM instructions WHERE instruction_id = ?", (instruction_id,)
                    ).fetchone()
                    if instr is None:
                        outcome = "REJECTED_NOT_FOUND"
                        response = error(
                            404, "INSTRUCTION_NOT_FOUND", f"No instruction {instruction_id}"
                        )
                    elif instr["revision"] != body.expectedRevision:
                        outcome = "REJECTED_STALE_REVISION"
                        response = error(
                            409,
                            "STALE_REVISION",
                            f"Expected revision {body.expectedRevision}, "
                            f"current is {instr['revision']}",
                            {"currentRevision": instr["revision"]},
                        )
                    elif instr["status"] != "REJECTED":
                        outcome = "REJECTED_NOT_AMENDABLE"
                        response = error(
                            409,
                            "NOT_AMENDABLE",
                            f"Instruction status is {instr['status']}, "
                            "only REJECTED can be amended",
                        )
                    else:
                        # 2. Apply the amendment and its receipt atomically.
                        now = utc_now()
                        new_rev = instr["revision"] + 1
                        receipt_id = "RCPT-" + secrets.token_hex(4)
                        c.execute(
                            "UPDATE instructions SET revision = ?, safekeeping_account = ?, "
                            "status = 'ACCEPTED', "
                            "latest_operation_id = ?, updated_at = ? WHERE instruction_id = ?",
                            (new_rev, body.newAccount, body.operationId, now, instruction_id),
                        )
                        c.execute(
                            "INSERT INTO instruction_revisions VALUES (?,?,?,?,?,?)",
                            (
                                instruction_id,
                                new_rev,
                                body.newAccount,
                                "ACCEPTED",
                                body.operationId,
                                now,
                            ),
                        )
                        c.execute(
                            "INSERT INTO operations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                idempotency_key,
                                body.operationId,
                                receipt_id,
                                instruction_id,
                                payload_hash,
                                json.dumps(payload, sort_keys=True),
                                instr["revision"],
                                new_rev,
                                body.newAccount,
                                "ACCEPTED",
                                now,
                            ),
                        )
                        row = c.execute(
                            "SELECT * FROM operations WHERE idempotency_key = ?", (idempotency_key,)
                        ).fetchone()
                        response = {**_receipt_json(row), "replayed": False}
                        outcome = "COMMITTED"
                        # 3. One-shot fault: consume it inside the same transaction.
                        armed = c.execute(
                            "SELECT armed FROM faults WHERE name = 'lost_response'"
                        ).fetchone()
                        if armed and armed["armed"]:
                            c.execute("UPDATE faults SET armed = 0 WHERE name = 'lost_response'")
                            drop_response = True
                            outcome = "COMMITTED_RESPONSE_DROPPED"
                c.execute(
                    "INSERT INTO patch_requests"
                    "(instruction_id, idempotency_key, outcome, received_at) "
                    "VALUES (?,?,?,?)",
                    (instruction_id, idempotency_key, outcome, utc_now()),
                )
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise

        if drop_response:
            # The amendment is already durable. Hold the reply past the caller's timeout so the
            # caller sees an ambiguous outcome (it cannot tell committed from failed).
            time.sleep(float(os.getenv("LOST_RESPONSE_DELAY_SECONDS", "10")))
        return response

    @app.get("/operations/{operation_id}")
    def get_operation(operation_id: str):
        if fault_armed("operations_unavailable"):
            return error(
                503,
                "OPERATIONS_UNAVAILABLE",
                "Operation lookup temporarily unavailable; this is NOT a confirmation of absence",
            )
        row = store.query_one("SELECT * FROM operations WHERE operation_id = ?", (operation_id,))
        if row is None:
            return error(
                404,
                "OPERATION_NOT_FOUND",
                f"No committed operation {operation_id}",
                {"operationId": operation_id, "confirmedAbsent": True},
            )
        return _receipt_json(row)

    @app.get("/admin/proof")
    def proof(instructionId: str = "SI-2041"):
        instr = store.query_one(
            "SELECT * FROM instructions WHERE instruction_id = ?", (instructionId,)
        )
        if instr is None:
            return error(404, "INSTRUCTION_NOT_FOUND", f"No instruction {instructionId}")
        receipts = store.query_all(
            "SELECT * FROM operations WHERE instruction_id = ? ORDER BY created_at",
            (instructionId,),
        )
        revisions = store.query_all(
            "SELECT * FROM instruction_revisions WHERE instruction_id = ? ORDER BY revision",
            (instructionId,),
        )
        patches = store.query_all(
            "SELECT * FROM patch_requests WHERE instruction_id = ? ORDER BY id", (instructionId,)
        )
        return {
            "instructionId": instructionId,
            "currentRevision": instr["revision"],
            "currentAccount": instr["safekeeping_account"],
            "status": instr["status"],
            "receiptCount": len(receipts),
            "patchRequestCount": len(patches),
            "receipts": [
                {
                    "receiptId": r["receipt_id"],
                    "operationId": r["operation_id"],
                    "resultRevision": r["result_revision"],
                    "committedAt": r["created_at"],
                }
                for r in receipts
            ],
            "revisions": [
                {
                    "revision": r["revision"],
                    "account": r["safekeeping_account"],
                    "status": r["status"],
                    "operationId": r["operation_id"],
                    "createdAt": r["created_at"],
                }
                for r in revisions
            ],
            "patchRequests": [
                {
                    "idempotencyKey": p["idempotency_key"],
                    "outcome": p["outcome"],
                    "receivedAt": p["received_at"],
                }
                for p in patches
            ],
            "source": SOURCE,
        }

    @app.get("/admin/faults")
    def get_faults():
        return {
            "lostResponse": fault_armed("lost_response"),
            "operationsUnavailable": fault_armed("operations_unavailable"),
        }

    @app.post("/admin/faults", dependencies=[Depends(require_admin)])
    def set_faults(body: FaultsBody):
        with store.lock:
            if body.lostResponse is not None:
                store.conn.execute(
                    "UPDATE faults SET armed = ? WHERE name = 'lost_response'",
                    (int(body.lostResponse),),
                )
            if body.operationsUnavailable is not None:
                store.conn.execute(
                    "UPDATE faults SET armed = ? WHERE name = 'operations_unavailable'",
                    (int(body.operationsUnavailable),),
                )
        return get_faults()

    @app.post("/admin/reset", dependencies=[Depends(require_admin)])
    def reset():
        seed(store)
        return {"reset": True}

    app.add_api_route("/custodian/instructions/{instruction_id}", get_instruction, methods=["GET"])
    app.add_api_route(
        "/custodian/instructions/{instruction_id}", amend_instruction, methods=["PATCH"]
    )
    app.add_api_route("/custodian/operations/{operation_id}", get_operation, methods=["GET"])
    return app
