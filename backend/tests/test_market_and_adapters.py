import json

import pytest
from bson import Decimal128

from app.market import parse_observation
from app.services.workflow import UnsafeEvidence, parse_directory


def observation():
    return {
        "_id": "F92124100:2026-09-15",
        "cusip": "F92124100",
        "symbol": "TTE",
        "description": "TOTALENERGIES SE ORDINARY SHAR",
        "settlement_date": {"$date": "2026-09-15T00:00:00Z"},
        "outstanding_fail_quantity": 1277,
        "prior_close_price": {"$numberDecimal": "91.14"},
        "source_archive": "cnsfails202609b.zip",
    }


def test_observation_preserves_date_decimal_and_identity():
    doc = parse_observation(json.dumps(observation()))
    assert str(doc["prior_close_price"]) == "91.14"
    assert isinstance(doc["prior_close_price"], Decimal128)
    assert doc["settlement_date"].utcoffset().total_seconds() == 0


def test_missing_price_and_empty_symbol_are_valid_not_zero():
    doc = parse_observation(json.dumps({**observation(), "symbol": "", "prior_close_price": None}))
    assert doc["prior_close_price"] is None and doc["symbol"] == ""


@pytest.mark.parametrize(
    "changes",
    [
        {"cusip": "BAD"},
        {"_id": "F92124100:2026-09-16"},
        {"settlement_date": {"$date": "2026-09-15T13:00:00Z"}},
        {"outstanding_fail_quantity": 0},
        {"outstanding_fail_quantity": True},
        {"prior_close_price": {"$numberDecimal": "-1"}},
        {"prior_close_price": "91.14"},
    ],
)
def test_invalid_observations_rejected(changes):
    with pytest.raises(ValueError):
        parse_observation(json.dumps({**observation(), **changes}))


@pytest.mark.parametrize(
    "version,raw",
    [
        (
            1,
            {
                "portfolioId": "P-17",
                "settlementAccount": "SAFE-401",
                "accountStatus": "ACTIVE",
                "mappingRevision": 7,
            },
        ),
        (
            2,
            {
                "schemaVersion": 2,
                "portfolio": {"id": "P-17"},
                "delivery": {"safekeepingAccount": "SAFE-401", "status": "ACTIVE"},
                "mappingRevision": 7,
            },
        ),
    ],
)
def test_known_directory_adapters(version, raw):
    result = parse_directory(raw, version, "P-17")
    assert result["activeAccount"] == "SAFE-401" and result["mappingRevision"] == 7


@pytest.mark.parametrize(
    "changes",
    [
        {"portfolioId": "P-22"},
        {"mappingRevision": True},
        {"accountStatus": "RETIRED"},
        {"delivery": {"safekeepingAccount": "SAFE-999"}},
    ],
)
def test_directory_conflicts_fail_closed(changes):
    raw = {
        "portfolioId": "P-17",
        "settlementAccount": "SAFE-401",
        "accountStatus": "ACTIVE",
        "mappingRevision": 7,
    }
    with pytest.raises(UnsafeEvidence):
        parse_directory({**raw, **changes}, 1, "P-17")


def test_unknown_directory_version_is_not_guessed():
    with pytest.raises(UnsafeEvidence):
        parse_directory({"routing": {"custodyLeg": {"acct": "SAFE-401"}}}, 3, "P-17")
