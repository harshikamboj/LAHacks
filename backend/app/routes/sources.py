"""GET /api/cases/{caseId}/sources — live reads of the three systems for the evidence cards.

Each card is fetched independently, so one system being down only breaks its own card.
These are read-only calls; nothing here can change any system.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.services import simulator_clients as sims

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _card(request: str, fn) -> dict:
    fetched_at = _now()
    try:
        return {"ok": True, "request": request, "fetchedAt": fetched_at, "data": fn()}
    except sims.SimulatorError as exc:
        return {"ok": False, "request": request, "fetchedAt": fetched_at, "error": exc.message}


@router.get("/cases/{case_id}/sources")
def case_sources(case_id: str):
    custodian = _card(
        f"GET /instructions/{case_id}", lambda: sims.custodian().get_instruction(case_id)
    )

    # The custodian instruction names the trade and portfolio; without it we don't guess.
    instr = custodian.get("data") or {}
    trade_id, portfolio_id = instr.get("tradeId"), instr.get("portfolioId")

    if trade_id:
        broker = _card(f"GET /trades/{trade_id}", lambda: sims.broker().get_trade(trade_id))
    else:
        broker = {
            "ok": False,
            "request": None,
            "fetchedAt": _now(),
            "error": "Trade ID unknown until the custodian instruction can be read",
        }

    if portfolio_id:
        directory = _card(
            f"GET /accounts/{portfolio_id}", lambda: sims.directory().get_accounts_raw(portfolio_id)
        )
        contract = _card("GET /contract", lambda: sims.directory().get_contract())
        directory["contract"] = contract.get("data")
        if directory["ok"]:
            baseline = instr.get("safekeepingAccount")
            if baseline:
                status = _card(
                    f"GET /account-status/{baseline}",
                    lambda: sims.directory().get_account_status(baseline),
                )
                directory["baselineAccountStatus"] = status.get("data")
    else:
        directory = {
            "ok": False,
            "request": None,
            "fetchedAt": _now(),
            "error": "Portfolio unknown until the custodian instruction can be read",
        }

    return {"caseId": case_id, "broker": broker, "directory": directory, "custodian": custodian}
