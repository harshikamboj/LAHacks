"""Broker simulator — read-only authority for the executed trade.

Run: uv run uvicorn simulators.broker:create_app --factory --port 8101
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI

from simulators.common import Store, data_dir, error, load_fixture, require_admin

SOURCE = "SIMULATED_BROKER"

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id     TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    side         TEXT NOT NULL,
    security     TEXT NOT NULL,
    quantity     INTEGER NOT NULL,
    price        TEXT NOT NULL,
    currency     TEXT NOT NULL,
    status       TEXT NOT NULL,
    executed_at  TEXT NOT NULL
);
"""


def seed(store: Store) -> None:
    """Drop and reload synthetic trades from fixtures/trades.json."""
    with store.lock:
        store.conn.execute("BEGIN IMMEDIATE")
        store.conn.execute("DELETE FROM trades")
        for t in load_fixture("trades.json"):
            store.conn.execute(
                "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    t["tradeId"],
                    t["portfolioId"],
                    t["side"],
                    t["security"],
                    t["quantity"],
                    t["price"],
                    t["currency"],
                    t["status"],
                    t["executedAt"],
                ),
            )
        store.conn.execute("COMMIT")


def create_app(db_path: Path | None = None) -> FastAPI:
    store = Store(db_path or data_dir() / "broker.db")
    store.script(SCHEMA)
    if store.query_one("SELECT COUNT(*) AS n FROM trades")["n"] == 0:
        seed(store)

    app = FastAPI(title="Broker simulator (synthetic)", version="1")
    app.state.store = store

    @app.get("/health")
    def health():
        return {"ok": True, "source": SOURCE}

    @app.get("/trades/{trade_id}")
    def get_trade(trade_id: str):
        row = store.query_one("SELECT * FROM trades WHERE trade_id = ?", (trade_id,))
        if row is None:
            return error(404, "TRADE_NOT_FOUND", f"No trade {trade_id}")
        return {
            "tradeId": row["trade_id"],
            "portfolioId": row["portfolio_id"],
            "side": row["side"],
            "security": row["security"],
            "quantity": row["quantity"],
            "price": row["price"],
            "currency": row["currency"],
            "status": row["status"],
            "executedAt": row["executed_at"],
            "source": SOURCE,
        }

    @app.post("/admin/reset", dependencies=[Depends(require_admin)])
    def reset():
        seed(store)
        return {"reset": True}

    return app
