import pytest
from pydantic import ValidationError

from app.config import Settings
from app.hashing import proposal_hash
from app.models import Proposal


def proposal():
    return {
        "caseId": "SI-2041",
        "runId": "run-one",
        "instructionId": "SI-2041",
        "tradeId": "TR-2041",
        "portfolioId": "P-17",
        "expectedRevision": 1,
        "oldAccount": "SAFE-100",
        "newAccount": "SAFE-401",
        "mutation": "AMEND_SAFEKEEPING_ACCOUNT",
        "policyVersion": "v1",
    }


def test_hash_is_canonical_and_bound_to_run_account_revision_and_policy():
    original = proposal()
    digest = proposal_hash(original)
    assert proposal_hash(dict(reversed(list(original.items())))) == digest
    for field, value in (
        ("runId", "run-two"),
        ("newAccount", "SAFE-402"),
        ("expectedRevision", 2),
        ("policyVersion", "v2"),
    ):
        assert proposal_hash({**original, field: value}) != digest


@pytest.mark.parametrize(
    "changes",
    [
        {"instructionId": "SI-9999"},
        {"newAccount": "SAFE-100"},
        {"expectedRevision": "1"},
        {"expectedRevision": 0},
        {"unexpected": True},
    ],
)
def test_proposal_rejects_wrong_scope_or_malformed_payload(changes):
    with pytest.raises(ValidationError):
        Proposal.model_validate({**proposal(), **changes})


def test_settings_hide_secrets_and_reject_unrelated_database():
    config = Settings(_env_file=None, mongodb_uri="mongodb://secret-user:secret-password@example")
    assert "secret-password" not in repr(config)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mongodb_db="production")
