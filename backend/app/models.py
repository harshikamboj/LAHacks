"""Shared durable data models; API/worker services can build on these types."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from bson import Decimal128
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Stage(StrEnum):
    NEW = "NEW"
    INVESTIGATING = "INVESTIGATING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    AWAITING_VERIFICATION = "AWAITING_VERIFICATION"
    VERIFIED = "VERIFIED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    DENIED = "DENIED"
    NO_ACTION = "NO_ACTION"


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    caseId: str = Field(pattern=r"^SI-[0-9]+$")
    runId: str = Field(min_length=1)
    instructionId: str = Field(pattern=r"^SI-[0-9]+$")
    tradeId: str = Field(pattern=r"^TR-[0-9]+$")
    portfolioId: str = Field(pattern=r"^P-[0-9]+$")
    expectedRevision: int = Field(ge=1)
    oldAccount: str = Field(pattern=r"^SAFE-[0-9]+$")
    newAccount: str = Field(pattern=r"^SAFE-[0-9]+$")
    mutation: Literal["AMEND_SAFEKEEPING_ACCOUNT"] = "AMEND_SAFEKEEPING_ACCOUNT"
    policyVersion: str = Field(min_length=1)
    mappingRevision: int = Field(default=7, ge=1)

    @model_validator(mode="after")
    def validate_scope(self):
        if self.instructionId != self.caseId or self.oldAccount == self.newAccount:
            raise ValueError("Proposal must amend this instruction to a different account")
        return self


class CaseDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    caseId: str = Field(pattern=r"^SI-[0-9]+$")
    runId: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    synthetic: Literal[True] = True
    tradeId: str = Field(pattern=r"^TR-[0-9]+$")
    portfolioId: str = Field(pattern=r"^P-[0-9]+$")
    stage: Stage = Stage.NEW
    version: int = Field(default=1, ge=1)
    evidence: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    createdAt: AwareDatetime
    updatedAt: AwareDatetime

    def to_bson(self) -> dict:
        doc = self.model_dump(mode="python")
        doc["stage"] = self.stage.value
        return doc


def bson_public(value: Any) -> Any:
    """JSON-safe API view; keep BSON datetimes in the stored documents."""
    if isinstance(value, dict):
        return {k: bson_public(v) for k, v in value.items() if k != "_id"}
    if isinstance(value, list):
        return [bson_public(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal128):
        return str(value.to_decimal())
    return value
