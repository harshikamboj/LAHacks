"""Real Voyage embeddings + Atlas Vector Search, with explicit pending states."""

import hashlib
import math
import time

import httpx
from pymongo.errors import PyMongoError
from pymongo.read_concern import ReadConcern

from app.config import Settings
from app.db import utcnow
from app.schema import DIMENSIONS

NEXT_CHECKS = {
    "GET_ACCOUNT_STATUS",
    "GET_BROKER_TRADE",
    "GET_CUSTODIAN_INSTRUCTION",
    "GET_DIRECTORY_CONTRACT",
    "GET_CUSTODIAN_OPERATION",
}


class EmbeddingUnavailable(RuntimeError):
    pass


def incident_text(incident: dict) -> str:
    return incident["symptom"] + " " + incident["verifiedResolution"]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class VoyageEmbeddings:
    def __init__(self, settings: Settings, *, transport=None):
        self.settings = settings
        self.transport = transport

    def embed(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        if input_type not in {"document", "query"}:
            raise ValueError("Use document or query embedding input_type")
        if not self.settings.voyage_api_key.get_secret_value():
            raise EmbeddingUnavailable("VOYAGE_API_KEY_MISSING")
        try:
            with httpx.Client(timeout=30, transport=self.transport) as client:
                response = client.post(
                    "https://api.voyageai.com/v1/embeddings",
                    headers={
                        "Authorization": "Bearer " + self.settings.voyage_api_key.get_secret_value()
                    },
                    json={
                        "input": texts,
                        "model": self.settings.voyage_model,
                        "input_type": input_type,
                        "output_dimension": DIMENSIONS,
                        "truncation": False,
                    },
                )
                response.raise_for_status()
                data = sorted(response.json()["data"], key=lambda item: item["index"])
            if [row["index"] for row in data] != list(range(len(texts))):
                raise ValueError("Embedding result count/index mismatch")
            vectors = [row["embedding"] for row in data]
            for vector in vectors:
                if (
                    len(vector) != DIMENSIONS
                    or any(
                        isinstance(n, bool)
                        or not isinstance(n, (int, float))
                        or not math.isfinite(n)
                        for n in vector
                    )
                    or not any(vector)
                ):
                    raise ValueError("Invalid embedding vector")
            return vectors
        except httpx.HTTPStatusError as exc:
            raise EmbeddingUnavailable(f"VOYAGE_HTTP_{exc.response.status_code}") from None
        except httpx.RequestError:
            raise EmbeddingUnavailable("VOYAGE_UNREACHABLE") from None
        except (KeyError, TypeError, ValueError):
            raise EmbeddingUnavailable("VOYAGE_INVALID_EMBEDDING_RESPONSE") from None


class IncidentMemory:
    def __init__(self, db, settings: Settings, *, embeddings=None):
        self.db, self.settings = db, settings
        self.embeddings = embeddings or VoyageEmbeddings(settings)
        self.query_vectors = {}
        self.query_retry_at = 0.0

    def status(self) -> dict:
        if not self.settings.memory_enabled:
            return {"vectorSearch": "DISABLED", "reason": "MEMORY_ENABLED_FALSE"}
        if not self.settings.voyage_api_key.get_secret_value():
            return {"vectorSearch": "PENDING", "reason": "VOYAGE_API_KEY_MISSING"}
        try:
            indexes = list(
                self.db.incidents.list_search_indexes(name=self.settings.mongodb_vector_index)
            )
            if not indexes or not indexes[0].get("queryable"):
                return {"vectorSearch": "PENDING", "reason": "VECTOR_INDEX_NOT_QUERYABLE"}
            count = self.db.incidents.count_documents(
                {
                    "synthetic": True,
                    "disposition": "VERIFIED",
                    "embeddingModel": self.settings.voyage_model,
                    "embeddingDimensions": DIMENSIONS,
                    "embedding": {"$exists": True},
                }
            )
            if not count:
                return {"vectorSearch": "PENDING", "reason": "INCIDENT_EMBEDDINGS_MISSING"}
            return {"vectorSearch": "READY", "reason": None, "embeddedIncidents": count}
        except PyMongoError:
            return {"vectorSearch": "PENDING", "reason": "ATLAS_MEMORY_UNAVAILABLE"}

    def retrieve(self, query: str, *, source: str | None = None, limit: int = 3) -> dict:
        if not query.strip() or not 1 <= limit <= 10:
            raise ValueError("Non-empty query and limit between 1 and 10 are required")
        status = self.status()
        result = {"query": query, "status": "PENDING", "reason": status["reason"], "matches": []}
        if status["vectorSearch"] != "READY":
            if status["vectorSearch"] == "DISABLED":
                result["status"] = "DISABLED"
            return result
        try:
            cached = self.query_vectors.get(query)
            if cached and time.monotonic() - cached[0] < 600:
                vector = cached[1]
            else:
                if time.monotonic() < self.query_retry_at:
                    raise EmbeddingUnavailable("VOYAGE_RATE_LIMIT_RETRY_PENDING")
                vector = self.embeddings.embed([query], input_type="query")[0]
                if len(self.query_vectors) >= 32:
                    self.query_vectors.clear()
                self.query_vectors[query] = (time.monotonic(), vector)
            filters = {
                "disposition": {"$eq": "VERIFIED"},
                "synthetic": {"$eq": True},
                "embeddingModel": {"$eq": self.settings.voyage_model},
            }
            if source:
                filters["source"] = {"$eq": source}
            matches = list(
                # Atlas $vectorSearch requires local read concern. Case/checkpoint reads
                # retain the database's majority concern; this override is query-specific.
                self.db.incidents.with_options(read_concern=ReadConcern("local")).aggregate(
                    [
                        {
                            "$vectorSearch": {
                                "index": self.settings.mongodb_vector_index,
                                "path": "embedding",
                                "queryVector": vector,
                                "numCandidates": max(50, limit * 20),
                                "limit": limit,
                                "filter": filters,
                            }
                        },
                        {
                            "$project": {
                                "_id": 0,
                                "incidentId": 1,
                                "title": 1,
                                "symptom": 1,
                                "verifiedResolution": 1,
                                "suggestedNextCheck": 1,
                                "source": 1,
                                "disposition": 1,
                                "learnedFromCaseId": 1,
                                "createdAt": 1,
                                "learnedFromRunId": 1,
                                "learningScope": 1,
                                "portfolioId": 1,
                                "verifiedReceiptId": 1,
                                "score": {"$meta": "vectorSearchScore"},
                            }
                        },
                    ],
                    maxTimeMS=self.settings.mongodb_timeout_ms,
                )
            )
            # Memory can only name a known READ tool. Live data and approval remain authoritative.
            for match in matches:
                if match.get("suggestedNextCheck") not in NEXT_CHECKS:
                    match["suggestedNextCheck"] = None
            return {
                "query": query,
                "status": "FOUND" if matches else "NONE",
                "reason": None,
                "matches": matches,
            }
        except EmbeddingUnavailable as exc:
            if str(exc) == "VOYAGE_HTTP_429":
                self.query_retry_at = time.monotonic() + 60
            result["reason"] = str(exc)
        except PyMongoError:
            result["reason"] = "ATLAS_VECTOR_QUERY_UNAVAILABLE"
        return result

    def learn_verified(self, case: dict) -> dict:
        """Publish only independently verified effects. Stable ID makes restart/retry idempotent."""
        verification = case.get("verification", {})
        receipt = verification.get("receipt", {})
        instruction = verification.get("instruction", {})
        operation = case.get("operation", {})
        if (
            case.get("stage") != "VERIFIED"
            or not receipt.get("receiptId")
            or receipt.get("operationId") != operation.get("operationId")
            or receipt.get("payloadHash") != operation.get("payloadHash")
            or instruction.get("latestOperationId") != operation.get("operationId")
            or instruction.get("status") != "ACCEPTED"
            or instruction.get("safekeepingAccount") != case["proposal"]["newAccount"]
        ):
            raise ValueError("Only matching independent verification can become experience")
        incident_id = "INC-LEARN-" + case["caseId"] + "-" + case["runId"]
        previous = self.db.incidents.find_one({"incidentId": incident_id})
        if (
            previous
            and previous.get("embeddingModel") == self.settings.voyage_model
            and previous.get("embedding")
        ):
            return {"incidentId": incident_id, "status": "STORED"}
        if not self.settings.memory_enabled:
            raise EmbeddingUnavailable("MEMORY_ENABLED_FALSE")
        incident = {
            "incidentId": incident_id,
            "synthetic": True,
            "disposition": "VERIFIED",
            "source": "directory:" + self.settings.demo_case_id,
            "title": "Verified receiving-account reconciliation",
            "symptom": "Retired receiving account; invalid safekeeping account; "
            "current receiving account mapping requires validation.",
            "verifiedResolution": (
                "Inspect the live directory contract before reading the receiving account. "
                "Validate the supported format, current account ownership and authorization. "
                "Get fresh exact approval, persist intent, and independently verify "
                "the custodian receipt and instruction."
            ),
            "suggestedNextCheck": "GET_DIRECTORY_CONTRACT",
            "learnedFromCaseId": case["caseId"],
            "learnedFromRunId": case["runId"],
            "learningScope": case.get("demoOwner", self.settings.demo_case_id),
            "portfolioId": case["portfolioId"],
            "verifiedReceiptId": receipt["receiptId"],
            "verifiedOperationId": operation["operationId"],
            "verifiedPayloadHash": operation["payloadHash"],
            "verifiedAccount": instruction["safekeepingAccount"],
            "createdAt": utcnow(),
        }
        vector = self.embeddings.embed([incident_text(incident)], input_type="document")[0]
        incident.update(
            embedding=vector,
            embeddingModel=self.settings.voyage_model,
            embeddingDimensions=DIMENSIONS,
            embeddingTextHash=text_hash(incident_text(incident)),
            embeddedAt=utcnow(),
        )
        self.db.incidents.update_one(
            {"incidentId": incident_id, "synthetic": True}, {"$setOnInsert": incident}, upsert=True
        )
        return {"incidentId": incident_id, "status": "STORED"}
