"""Account Directory simulator — authority for the current receiving (safekeeping) account.

The response shape of GET /accounts/{portfolioId} depends on the active contract version,
so the agent has to adapt when the directory changes:
  v1 -> settlementAccount
  v2 -> delivery.safekeepingAccount
  v3 -> routing.custodyLeg.acct
        (no validated adapter: the agent must send the case to manual review)

Run: uv run uvicorn simulators.directory:create_app --factory --port 8102
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from simulators.common import Store, data_dir, error, load_fixture, require_admin, utc_now

SOURCE = "SIMULATED_DIRECTORY"

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id   TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('ACTIVE','RETIRED')),
    authorized   INTEGER NOT NULL,
    retired_on   TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

CONTRACTS = {
    1: {
        "accountPath": "settlementAccount",
        "statusPath": "accountStatus",
        "portfolioPath": "portfolioId",
    },
    2: {
        "accountPath": "delivery.safekeepingAccount",
        "statusPath": "delivery.status",
        "portfolioPath": "portfolio.id",
    },
    3: {
        "accountPath": "routing.custodyLeg.acct",
        "statusPath": None,
        "portfolioPath": "portfolioRef",
    },
}


class ContractBody(BaseModel):
    version: int = Field(ge=1, le=3)


def seed(store: Store) -> None:
    fixture = load_fixture("accounts.json")
    with store.lock:
        store.conn.execute("BEGIN IMMEDIATE")
        store.conn.execute("DELETE FROM accounts")
        for a in fixture["accounts"]:
            store.conn.execute(
                "INSERT INTO accounts VALUES (?,?,?,?,?)",
                (
                    a["accountId"],
                    a["portfolioId"],
                    a["status"],
                    int(a["authorized"]),
                    a["retiredOn"],
                ),
            )
        _set_contract(store, fixture["defaultContractVersion"])
        store.conn.execute(
            "INSERT OR REPLACE INTO settings VALUES ('mapping_revision', ?)",
            (str(fixture.get("mappingRevision", 7)),),
        )
        store.conn.execute("COMMIT")


def _set_contract(store: Store, version: int) -> None:
    with store.lock:
        store.conn.execute(
            "INSERT INTO settings(key, value) VALUES ('contract_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(version),),
        )
        store.conn.execute(
            "INSERT INTO settings(key, value) VALUES ('contract_changed_at', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (utc_now(),),
        )


def _contract(store: Store) -> tuple[int, str]:
    version = store.query_one("SELECT value FROM settings WHERE key = 'contract_version'")
    changed = store.query_one("SELECT value FROM settings WHERE key = 'contract_changed_at'")
    return int(version["value"]), changed["value"]


def create_app(db_path: Path | None = None) -> FastAPI:
    store = Store(db_path or data_dir() / "directory.db")
    store.script(SCHEMA)
    if store.query_one("SELECT COUNT(*) AS n FROM accounts")["n"] == 0:
        seed(store)

    app = FastAPI(title="Account directory simulator (synthetic)", version="1")
    app.state.store = store

    @app.get("/health")
    def health():
        return {"ok": True, "source": SOURCE}

    @app.get("/contract")
    def contract():
        version, changed_at = _contract(store)
        return {
            "version": version,
            "contractVersion": version,
            **CONTRACTS[version],
            "changedAt": changed_at,
            "source": SOURCE,
        }

    @app.get("/accounts/{portfolio_id}")
    def get_accounts(portfolio_id: str):
        rows = store.query_all("SELECT * FROM accounts WHERE portfolio_id = ?", (portfolio_id,))
        if not rows:
            return error(404, "PORTFOLIO_NOT_FOUND", f"No accounts for portfolio {portfolio_id}")
        active = [r for r in rows if r["status"] == "ACTIVE" and r["authorized"]]
        retired = [r for r in rows if r["status"] == "RETIRED"]
        if len(active) != 1:
            # The directory refuses to pick one for you; callers must treat this as a conflict.
            return error(
                409,
                "AMBIGUOUS_ACTIVE_ACCOUNT",
                f"Portfolio {portfolio_id} has {len(active)} active authorized accounts",
                {"activeAccounts": [r["account_id"] for r in active]},
            )
        acct = active[0]["account_id"]
        version, _ = _contract(store)
        as_of = utc_now()
        revision_row = store.query_one("SELECT value FROM settings WHERE key = 'mapping_revision'")
        mapping_revision = int(revision_row["value"]) if revision_row else 7
        if version == 1:
            return {
                "portfolioId": portfolio_id,
                "settlementAccount": acct,
                "accountStatus": "ACTIVE",
                "retiredAccounts": [r["account_id"] for r in retired],
                "asOf": as_of,
                "source": SOURCE,
                "mappingRevision": mapping_revision,
            }
        if version == 2:
            return {
                "schemaVersion": 2,
                "portfolio": {"id": portfolio_id},
                "delivery": {"safekeepingAccount": acct, "status": "ACTIVE"},
                "history": [
                    {"account": r["account_id"], "status": "RETIRED", "retiredOn": r["retired_on"]}
                    for r in retired
                ],
                "asOf": as_of,
                "source": SOURCE,
                "mappingRevision": mapping_revision,
            }
        return {
            "schemaVersion": 3,
            "portfolioRef": portfolio_id,
            "routing": {"custodyLeg": {"acct": acct}},
            "asOf": as_of,
            "source": SOURCE,
            "mappingRevision": mapping_revision,
        }

    @app.get("/account-status/{account_id}")
    def account_status(account_id: str):
        row = store.query_one("SELECT * FROM accounts WHERE account_id = ?", (account_id,))
        if row is None:
            return error(404, "ACCOUNT_NOT_FOUND", f"No account {account_id}")
        return {
            "accountId": row["account_id"],
            "portfolioId": row["portfolio_id"],
            "status": row["status"],
            "authorized": bool(row["authorized"]),
            "retiredOn": row["retired_on"],
            "source": SOURCE,
        }

    @app.post("/admin/contract", dependencies=[Depends(require_admin)])
    def set_contract(body: ContractBody):
        _set_contract(store, body.version)
        return {"version": body.version}

    @app.post("/admin/reset", dependencies=[Depends(require_admin)])
    def reset():
        seed(store)
        return {"reset": True, "contractVersion": _contract(store)[0]}

    app.add_api_route("/directory/contract", contract, methods=["GET"])
    app.add_api_route("/directory/portfolios/{portfolio_id}", get_accounts, methods=["GET"])
    return app
