"""The generated schema must describe the bodies the handlers actually return.

Every example asserted here is compared against a response produced through
`TestClient`, so the document cannot drift from the API: changing a handler body
without the schema fails this module. The exact-body tests in `test_api.py`,
`test_rate_limit.py` and `test_error_sanitization.py` remain the independent
reference for the contract itself.
"""

from unittest import mock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.errors import (
    InvalidLLMResponseError,
    LLMConfigurationError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)
from app.main import app

client = TestClient(app)
failing_client = TestClient(app, raise_server_exceptions=False)

MESSAGES = [{"role": "bot", "content": "Hello"}]

DOCUMENTED_STATUSES = {"200", "413", "422", "500", "502", "503"}


def _client_raising(monkeypatch, error: Exception) -> None:
    """Replace only the client acquisition; the real handlers keep running."""
    fake_client = mock.MagicMock(spec=["models"])
    fake_client.models.generate_content.side_effect = error
    monkeypatch.setattr("app.llm_client._get_client", lambda: fake_client)


def _post(body: dict | None = None):
    return client.post("/handover", json=body or {"messages": MESSAGES})


@pytest.fixture(scope="module")
def schema() -> dict:
    return client.get("/openapi.json").json()


def _operation(schema: dict) -> dict:
    return schema["paths"]["/handover"]["post"]


def _media(schema: dict, status: str) -> dict:
    return _operation(schema)["responses"][status]["content"]["application/json"]


def _examples(schema: dict, status: str) -> dict:
    return {
        name: example["value"]
        for name, example in _media(schema, status).get("examples", {}).items()
    }


def _component_name(schema: dict, status: str) -> str:
    ref = _media(schema, status)["schema"]["$ref"]
    return ref.rsplit("/", 1)[-1]


def _component(schema: dict, name: str) -> dict:
    return schema["components"]["schemas"][name]


def _item_component(schema: dict) -> dict:
    """The model of one entry in the 422 `detail` array."""
    detail = _component(schema, _component_name(schema, "422"))["properties"]["detail"]
    return _component(schema, detail["items"]["$ref"].rsplit("/", 1)[-1])


# --- what the document declares ------------------------------------------- #


def test_the_endpoint_documents_every_error_it_returns(schema):
    assert DOCUMENTED_STATUSES <= set(_operation(schema)["responses"])


def test_the_validation_schema_carries_only_the_sanitized_fields(schema):
    """The response omits `input` and `ctx`; the document must not advertise them."""
    assert _component_name(schema, "422") != "HTTPValidationError"

    item = _item_component(schema)

    assert set(item["properties"]) == {"type", "loc", "msg"}
    assert set(item["required"]) == {"type", "loc", "msg"}
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    assert "ValidationError" not in schema["components"]["schemas"]


def test_the_500_declares_both_shapes_and_never_a_null_detail(schema):
    union = _component(schema, _component_name(schema, "500"))
    members = [
        _component(schema, member["$ref"].rsplit("/", 1)[-1])
        for member in union["anyOf"]
    ]

    required = {frozenset(member.get("required", ())) for member in members}
    assert frozenset({"error", "detail"}) in required
    assert frozenset({"error"}) in required

    for member in members:
        properties = member["properties"]
        assert set(properties) <= {"error", "detail"}
        if "detail" in properties:
            # A plain string: never `null`, never an optional variant.
            assert "anyOf" not in properties["detail"]
            assert properties["detail"].get("type") == "string"


def test_the_503_documents_three_distinct_bodies(schema):
    examples = _examples(schema, "503")

    assert set(examples) == {
        "provider_unavailable",
        "provider_unavailable_connection_failure",
        "provider_rate_limited",
    }
    codes = [value["error"] for value in examples.values()]
    assert codes.count("provider_unavailable") == 2
    assert codes.count("provider_rate_limited") == 1


# --- the document against the responses ----------------------------------- #


def test_a_validation_rejection_matches_the_documented_shape(schema):
    response = _post({"messages": [{"role": "bot", "content": ""}]})

    assert response.status_code == 422
    entry = response.json()["detail"][0]
    assert set(entry) == set(_item_component(schema)["properties"])


def test_a_configuration_error_matches_its_example(schema, monkeypatch):
    _client_raising(monkeypatch, LLMConfigurationError("synthetic"))

    response = _post()

    assert response.status_code == 500
    assert response.json() == _examples(schema, "500")["configuration_error"]


def test_an_internal_error_matches_its_example_without_a_detail(schema, monkeypatch):
    _client_raising(monkeypatch, RuntimeError("synthetic"))

    response = failing_client.post("/handover", json={"messages": MESSAGES})

    assert response.status_code == 500
    assert "detail" not in response.json()
    assert response.json() == _examples(schema, "500")["internal_error"]


def test_an_invalid_response_matches_its_example(schema, monkeypatch):
    _client_raising(monkeypatch, InvalidLLMResponseError("synthetic"))

    response = _post()

    assert response.status_code == 502
    assert response.json() == _examples(schema, "502")["invalid_llm_response"]


def test_a_transcript_too_large_matches_its_example(schema):
    messages = [{"role": "bot", "content": "a" * 2000} for _ in range(11)]

    response = _post({"messages": messages})

    assert response.status_code == 413
    assert response.json() == _examples(schema, "413")["transcript_too_large"]


def test_a_provider_failure_matches_its_example(schema, monkeypatch):
    _client_raising(monkeypatch, ProviderUnavailableError("synthetic"))

    response = _post()

    assert response.status_code == 503
    assert response.json() == _examples(schema, "503")["provider_unavailable"]


def test_an_undetermined_connection_failure_matches_its_example(schema, monkeypatch):
    error = ProviderUnavailableError("synthetic")
    error.__cause__ = httpx.ConnectError("connection refused")
    _client_raising(monkeypatch, error)

    response = _post()

    assert response.status_code == 503
    assert (
        response.json()
        == _examples(schema, "503")["provider_unavailable_connection_failure"]
    )


def test_rate_limiting_matches_its_example(schema, monkeypatch):
    _client_raising(monkeypatch, ProviderRateLimitedError("synthetic"))

    response = _post()

    assert response.status_code == 503
    assert response.json() == _examples(schema, "503")["provider_rate_limited"]


def test_the_served_document_is_the_generated_one(schema):
    assert schema == app.openapi()
