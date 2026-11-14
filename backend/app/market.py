"""SEC observations are historical context, never an authority for account amendments."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from bson import Decimal128, json_util
from bson.json_util import JSONOptions
from pymongo import ReplaceOne

ANCHOR_ID = "F92124100:2026-09-15"


def parse_observation(line: str) -> dict:
    doc = json_util.loads(line, json_options=JSONOptions(tz_aware=True))
    if not isinstance(doc, dict) or not re.fullmatch(r"[A-Z0-9]{9}", doc.get("cusip", "")):
        raise ValueError("Invalid CUSIP")
    date = doc.get("settlement_date")
    if not isinstance(date, datetime) or date.utcoffset().total_seconds() != 0:
        raise ValueError("UTC BSON date required")
    if any((date.hour, date.minute, date.second, date.microsecond)):
        raise ValueError("Settlement date must be UTC midnight")
    if doc.get("_id") != f"{doc['cusip']}:{date.date().isoformat()}":
        raise ValueError("Observation ID does not match CUSIP/date")
    quantity = doc.get("outstanding_fail_quantity")
    if type(quantity) is not int or quantity <= 0:
        raise ValueError("Positive integer quantity required")
    price = doc.get("prior_close_price")
    if price is not None and (
        not isinstance(price, Decimal128)
        or not price.to_decimal().is_finite()
        or price.to_decimal() < 0
    ):
        raise ValueError("Invalid prior-close decimal")
    if not all(isinstance(doc.get(k), str) for k in ("symbol", "description", "source_archive")):
        raise ValueError("Display labels and archive are required")
    return doc


def import_market(db, path: Path, batch_size: int = 1000) -> dict:
    parsed = rejected = null_prices = blank_symbols = duplicates = 0
    seen = set()
    batch = []
    errors = []
    for number, line in enumerate(path.open(encoding="utf-8"), 1):
        if not line.strip():
            continue
        try:
            doc = parse_observation(line)
            if doc["_id"] in seen:
                duplicates += 1
                raise ValueError("Duplicate observation ID in input")
            seen.add(doc["_id"])
            parsed += 1
            null_prices += doc["prior_close_price"] is None
            blank_symbols += doc["symbol"] == ""
            batch.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
            if len(batch) >= batch_size:
                db.market_fail_observations.bulk_write(batch, ordered=False)
                batch = []
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            rejected += 1
            if len(errors) < 5:
                errors.append({"line": number, "reason": str(exc)})
    if batch:
        db.market_fail_observations.bulk_write(batch, ordered=False)
    db.market_fail_observations.create_index([("cusip", 1), ("settlement_date", 1)])
    anchor = db.market_fail_observations.find_one({"_id": ANCHOR_ID})
    anchor_ok = bool(
        anchor
        and anchor["symbol"] == "TTE"
        and anchor["outstanding_fail_quantity"] == 1277
        and str(anchor["prior_close_price"]) == "91.14"
    )
    return {
        "parsed": parsed,
        "rejected": rejected,
        "duplicateIds": duplicates,
        "nullPrices": null_prices,
        "blankSymbols": blank_symbols,
        "stored": db.market_fail_observations.count_documents({}),
        "anchorVerified": anchor_ok,
        "errors": errors,
    }


def market_context(db, cusip: str, settlement_date: str) -> dict:
    date = datetime.fromisoformat(settlement_date).replace(tzinfo=timezone.utc)
    doc = db.market_fail_observations.find_one(
        {"_id": f"{cusip}:{settlement_date}", "cusip": cusip, "settlement_date": date}
    )
    return {
        "status": "FOUND" if doc else "NONE",
        "observationId": doc["_id"] if doc else None,
        "observation": doc,
        "source": "SEC NSCC CNS aggregate market data",
        "scope": "Historical market-wide outstanding shares; not this fictional trade",
        "lookup": {"cusip": cusip, "settlementDate": settlement_date},
    }
