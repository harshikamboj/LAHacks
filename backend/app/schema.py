"""Repeatable, non-destructive Atlas collections, validation, and indexes."""

from pymongo import ASCENDING
from pymongo.database import Database
from pymongo.operations import SearchIndexModel

from app.models import Stage

DIMENSIONS = 1024
VECTOR_DEFINITION = {
    "fields": [
        {
            "type": "vector",
            "path": "embedding",
            "numDimensions": DIMENSIONS,
            "similarity": "cosine",
        },
        *[
            {"type": "filter", "path": field}
            for field in ("source", "disposition", "embeddingModel", "synthetic")
        ],
    ]
}

CASE_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "caseId",
            "runId",
            "synthetic",
            "tradeId",
            "portfolioId",
            "stage",
            "version",
            "createdAt",
            "updatedAt",
            "events",
        ],
        "properties": {
            "caseId": {"bsonType": "string", "pattern": "^SI-[0-9]+$"},
            "runId": {"bsonType": "string", "minLength": 1},
            "synthetic": {"enum": [True]},
            "tradeId": {"bsonType": "string", "pattern": "^TR-[0-9]+$"},
            "portfolioId": {"bsonType": "string", "pattern": "^P-[0-9]+$"},
            "stage": {"enum": [stage.value for stage in Stage]},
            "version": {"bsonType": ["int", "long"], "minimum": 1},
            "createdAt": {"bsonType": "date"},
            "updatedAt": {"bsonType": "date"},
            "proposalHash": {"bsonType": "string", "pattern": "^sha256:[a-f0-9]{64}$"},
            "events": {
                "bsonType": "array",
                "maxItems": 100,
                "items": {
                    "bsonType": "object",
                    "required": ["at", "type", "stage", "actor", "detail"],
                    "properties": {
                        "at": {"bsonType": "date"},
                        "type": {"bsonType": "string"},
                        "stage": {"enum": [stage.value for stage in Stage]},
                        "actor": {"bsonType": "string"},
                        "detail": {"bsonType": "string"},
                    },
                },
            },
            "operation": {
                "bsonType": "object",
                "required": [
                    "operationId",
                    "idempotencyKey",
                    "payload",
                    "attemptCount",
                    "maxAttempts",
                ],
                "properties": {
                    "operationId": {"bsonType": "string", "pattern": "^OP-"},
                    "idempotencyKey": {"bsonType": "string", "pattern": "^OP-"},
                    "attemptCount": {"bsonType": ["int", "long"], "minimum": 1},
                    "maxAttempts": {"bsonType": ["int", "long"], "minimum": 1},
                    "payload": {
                        "bsonType": "object",
                        "required": ["operationId", "expectedRevision", "newAccount"],
                        "properties": {
                            "operationId": {"bsonType": "string", "pattern": "^OP-"},
                            "expectedRevision": {"bsonType": ["int", "long"], "minimum": 1},
                            "newAccount": {"bsonType": "string", "pattern": "^SAFE-[0-9]+$"},
                        },
                    },
                },
            },
        },
    }
}


def ensure_collections(db: Database) -> None:
    existing = set(db.list_collection_names())
    for name in ("cases", "incidents", "policies", "workers"):
        if name not in existing:
            options = (
                {
                    "validator": CASE_VALIDATOR,
                    "validationLevel": "strict",
                    "validationAction": "error",
                }
                if name == "cases"
                else {}
            )
            db.create_collection(name, **options)
    # collMod needs the setup user's dbAdmin role; never grant this to runtime.
    db.command(
        {
            "collMod": "cases",
            "validator": CASE_VALIDATOR,
            "validationLevel": "strict",
            "validationAction": "error",
        }
    )
    ensure_indexes(db)


def ensure_indexes(db: Database) -> None:
    db.cases.create_index([("caseId", ASCENDING)], unique=True, name="case_id_unique")
    db.cases.create_index(
        [("operation.operationId", ASCENDING)],
        unique=True,
        name="operation_id_unique",
        partialFilterExpression={"operation.operationId": {"$exists": True}},
    )
    db.cases.create_index([("stage", ASCENDING)], name="case_stage")
    db.incidents.create_index([("incidentId", ASCENDING)], unique=True, name="incident_id_unique")
    db.policies.create_index([("policyId", ASCENDING)], unique=True, name="policy_id_unique")
    db.case_runs.create_index([("caseId", 1), ("runId", 1)], unique=True, name="case_run_unique")


def ensure_vector_index(db: Database, name: str) -> dict:
    indexes = list(db.incidents.list_search_indexes(name=name))
    if not indexes:
        db.incidents.create_search_index(
            SearchIndexModel(name=name, definition=VECTOR_DEFINITION, type="vectorSearch")
        )
        return {"status": "BUILDING", "queryable": False, "created": True}
    index = indexes[0]
    if index.get("latestDefinition") != VECTOR_DEFINITION:
        raise ValueError(
            "Vector index definition differs; review before changing an existing index"
        )
    return {
        "status": index.get("status", "UNKNOWN"),
        "queryable": index.get("queryable", False),
        "created": False,
    }
