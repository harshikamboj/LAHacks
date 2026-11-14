import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.services.memory import EmbeddingUnavailable, IncidentMemory, VoyageEmbeddings


def settings(**kwargs):
    return Settings(_env_file=None, **kwargs)


def test_no_key_returns_pending_without_database_or_provider_calls():
    result = IncidentMemory(None, settings()).retrieve("account field moved")
    assert result == {
        "query": "account field moved",
        "status": "PENDING",
        "reason": "VOYAGE_API_KEY_MISSING",
        "matches": [],
    }


def test_disabled_memory_does_not_query_database():
    result = IncidentMemory(None, settings(memory_enabled=False)).retrieve("account field moved")
    assert result["status"] == "DISABLED"
    assert result["matches"] == []


def test_document_and_query_use_same_model_and_correct_input_type():
    requests = []

    def respond(request):
        import json

        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.25] * 1024}]})

    client = VoyageEmbeddings(
        settings(voyage_api_key="test-key"), transport=httpx.MockTransport(respond)
    )
    assert len(client.embed(["historical incident"], input_type="document")[0]) == 1024
    client.embed(["live rejection"], input_type="query")
    assert [r["input_type"] for r in requests] == ["document", "query"]
    assert {r["model"] for r in requests} == {"voyage-3.5-lite"}


@pytest.mark.parametrize("vector", [[0.25] * 16, [0] * 1024, [True] * 1024])
def test_bad_embeddings_fail_closed(vector):
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"data": [{"index": 0, "embedding": vector}]})
    )
    client = VoyageEmbeddings(settings(voyage_api_key="test-key"), transport=transport)
    with pytest.raises(EmbeddingUnavailable, match="VOYAGE_INVALID_EMBEDDING_RESPONSE"):
        client.embed(["incident"], input_type="document")


def test_provider_error_does_not_expose_body_or_credentials():
    transport = httpx.MockTransport(lambda _: httpx.Response(401, text="private provider body"))
    client = VoyageEmbeddings(settings(voyage_api_key="private-key"), transport=transport)
    with pytest.raises(EmbeddingUnavailable, match="^VOYAGE_HTTP_401$"):
        client.embed(["incident"], input_type="query")
    assert "private-key" not in repr(SecretStr("private-key"))


def test_vector_query_uses_local_read_concern_and_verified_model_filter():
    from types import SimpleNamespace
    from unittest.mock import Mock

    collection = Mock()
    collection.list_search_indexes.return_value = [{"queryable": True}]
    collection.count_documents.return_value = 9
    collection.with_options.return_value = collection
    collection.aggregate.return_value = [
        {
            "incidentId": "INC-004",
            "score": 0.9,
            "suggestedNextCheck": "GET_DIRECTORY_CONTRACT",
        }
    ]
    embeddings = Mock()
    embeddings.embed.return_value = [[0.25] * 1024]
    memory = IncidentMemory(
        SimpleNamespace(incidents=collection),
        settings(voyage_api_key="test-key"),
        embeddings=embeddings,
    )
    result = memory.retrieve("account field moved", source="directory")
    assert result["status"] == "FOUND"
    concern = collection.with_options.call_args.kwargs["read_concern"]
    assert concern.document == {"level": "local"}
    search = collection.aggregate.call_args.args[0][0]["$vectorSearch"]
    assert search["filter"] == {
        "disposition": {"$eq": "VERIFIED"},
        "synthetic": {"$eq": True},
        "embeddingModel": {"$eq": "voyage-3.5-lite"},
        "source": {"$eq": "directory"},
    }
    embeddings.embed.assert_called_once_with(["account field moved"], input_type="query")
