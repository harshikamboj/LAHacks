"""Seed only team-authored synthetic fixtures; preserve in-progress cases and policies."""

import json
from pathlib import Path

from app.db import CaseStore, utcnow
from app.schema import DIMENSIONS
from app.services.memory import EmbeddingUnavailable, VoyageEmbeddings, incident_text, text_hash

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name: str) -> list[dict]:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def seed_database(db, settings) -> dict:
    now = utcnow()
    for policy in load_fixture("policies"):
        if policy.get("synthetic") is not True:
            raise ValueError("Only synthetic fixtures can be seeded")
        db.policies.update_one(
            {"policyId": policy["policyId"], "synthetic": True},
            {"$setOnInsert": {**policy, "createdAt": now}},
            upsert=True,
        )
    pending = []
    for incident in load_fixture("incidents"):
        if incident.get("synthetic") is not True:
            raise ValueError("Only synthetic fixtures can be seeded")
        query = {"incidentId": incident["incidentId"], "synthetic": True}
        previous = db.incidents.find_one(query) or {}
        digest = text_hash(incident_text(incident))
        valid = (
            incident["disposition"] == "VERIFIED"
            and previous.get("embeddingModel") == settings.voyage_model
            and previous.get("embeddingDimensions") == DIMENSIONS
            and previous.get("embeddingTextHash") == digest
            and len(previous.get("embedding", [])) == DIMENSIONS
        )
        update = {"$set": {**incident, "updatedAt": now}, "$setOnInsert": {"createdAt": now}}
        if not valid:
            update["$unset"] = dict.fromkeys(
                (
                    "embedding",
                    "embeddingModel",
                    "embeddingDimensions",
                    "embeddingTextHash",
                    "embeddedAt",
                ),
                "",
            )
            if incident["disposition"] == "VERIFIED":
                pending.append((query, incident, digest))
        db.incidents.update_one(query, update, upsert=True)
    reason = None
    if pending:
        try:
            vectors = VoyageEmbeddings(settings).embed(
                [incident_text(item[1]) for item in pending], input_type="document"
            )
            for (query, incident, digest), vector in zip(pending, vectors, strict=True):
                # Do not attach an embedding if fixture text changed during the API request.
                db.incidents.update_one(
                    {
                        **query,
                        "symptom": incident["symptom"],
                        "verifiedResolution": incident["verifiedResolution"],
                        "disposition": "VERIFIED",
                    },
                    {
                        "$set": {
                            "embedding": vector,
                            "embeddingModel": settings.voyage_model,
                            "embeddingDimensions": DIMENSIONS,
                            "embeddingTextHash": digest,
                            "embeddedAt": utcnow(),
                        }
                    },
                )
        except EmbeddingUnavailable as exc:
            reason = str(exc)
    case = CaseStore(db).create_case()
    return {
        "case": {"caseId": case["caseId"], "stage": case["stage"], "version": case["version"]},
        "incidents": db.incidents.count_documents({"synthetic": True}),
        "embeddedIncidents": db.incidents.count_documents(
            {
                "synthetic": True,
                "disposition": "VERIFIED",
                "embeddingModel": settings.voyage_model,
                "embedding": {"$exists": True},
            }
        ),
        "embeddingPendingReason": reason,
    }
