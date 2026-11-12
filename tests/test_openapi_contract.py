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
from pydantic import ValidationError

from app.error_contract import ErrorResponses, ProviderFailureResponses
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


def _union_members(schema: dict, status: str = "500") -> list[dict]:
    union = _component(schema, _component_name(schema, status))
    return [
        _component(schema, member["$ref"].rsplit("/", 1)[-1])
        for member in union["anyOf"]
    ]


def _pinned_code(member: dict) -> str:
    error = member["properties"]["error"]
    return error["const"] if "const" in error else error["enum"][0]


def test_the_500_binds_each_branch_to_its_status_code(schema):
    members = _union_members(schema)

    assert {_pinned_code(member) for member in members} == {
        "llm_configuration_error",
        "internal_error",
    }

    by_code = {_pinned_code(member): member for member in members}
    assert set(by_code["llm_configuration_error"]["required"]) == {"error", "detail"}
    assert set(by_code["internal_error"]["required"]) == {"error"}

    for member in members:
        # Every declared property is required and nothing else is accepted.
        assert set(member["properties"]) == set(member["required"])
        assert member["additionalProperties"] is False


def test_the_500_schema_excludes_the_two_counterexamples(schema):
    """The union must reject a body that a client could misread."""
    by_code = {_pinned_code(member): member for member in _union_members(schema)}

    # `{"error": "llm_configuration_error"}` misses a required property.
    assert "detail" in by_code["llm_configuration_error"]["required"]

    # `{"error": "internal_error", "detail": null}` carries a forbidden property.
    internal = by_code["internal_error"]
    assert internal["additionalProperties"] is False
    assert set(internal["properties"]) == {"error"}


def test_the_500_schema_references_the_models_that_are_exercised(schema):
    """The acceptance tests below must test the models the document points at."""
    refs = [
        member["$ref"].rsplit("/", 1)[-1]
        for member in _component(schema, _component_name(schema, "500"))["anyOf"]
    ]
    assert refs == ["ConfigurationErrorResponse", "InternalErrorResponse"]
    assert _component_name(schema, "500") == "ErrorResponses"


def test_the_500_model_accepts_every_documented_body(schema):
    for value in _examples(schema, "500").values():
        validated = ErrorResponses.model_validate(value)
        assert validated.root.error == value["error"]


def test_the_500_model_rejects_the_counterexamples():
    with pytest.raises(ValidationError):
        ErrorResponses.model_validate({"error": "llm_configuration_error"})

    with pytest.raises(ValidationError):
        ErrorResponses.model_validate({"error": "internal_error", "detail": None})

    with pytest.raises(ValidationError):
        ErrorResponses.model_validate(
            {"error": "internal_error", "detail": "not allowed"}
        )


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


def test_the_503_binds_each_branch_to_its_code(schema):
    members = _union_members(schema, "503")
    by_code = {_pinned_code(member): member for member in members}

    assert set(by_code) == {"provider_unavailable", "provider_rate_limited"}

    unavailable = by_code["provider_unavailable"]
    assert "fallback" not in unavailable["properties"]
    assert unavailable["additionalProperties"] is False

    limited = by_code["provider_rate_limited"]
    assert "fallback" in limited["required"]
    assert set(limited["properties"]) == {"error", "detail", "fallback"}
    assert limited["additionalProperties"] is False


def test_the_503_examples_follow_their_branch(schema):
    examples = _examples(schema, "503")

    for name in ("provider_unavailable", "provider_unavailable_connection_failure"):
        assert "fallback" not in examples[name]

    assert examples["provider_rate_limited"]["fallback"] == {
        "assessment": "unavailable",
        "error": "provider_rate_limited",
        "urgency": "high",
    }


def test_the_503_schema_references_the_models_that_are_exercised(schema):
    refs = [
        member["$ref"].rsplit("/", 1)[-1]
        for member in _component(schema, _component_name(schema, "503"))["anyOf"]
    ]
    assert refs == ["ProviderUnavailableResponse", "ProviderRateLimitedResponse"]
    assert _component_name(schema, "503") == "ProviderFailureResponses"


def test_the_503_model_accepts_every_documented_body(schema):
    for value in _examples(schema, "503").values():
        validated = ProviderFailureResponses.model_validate(value)
        assert validated.root.error == value["error"]


def test_the_503_model_rejects_a_fallback_on_the_wrong_branch():
    with pytest.raises(ValidationError):
        ProviderFailureResponses.model_validate(
            {
                "error": "provider_unavailable",
                "detail": "The LLM provider is temporarily unavailable.",
                "fallback": {
                    "assessment": "unavailable",
                    "error": "provider_rate_limited",
                    "urgency": "high",
                },
            }
        )


def test_the_503_model_rejects_a_missing_or_wrong_fallback():
    with pytest.raises(ValidationError):
        ProviderFailureResponses.model_validate(
            {"error": "provider_rate_limited", "detail": "The LLM provider..."}
        )

    with pytest.raises(ValidationError):
        ProviderFailureResponses.model_validate(
            {
                "error": "provider_rate_limited",
                "detail": "The LLM provider...",
                "fallback": {
                    "assessment": "unavailable",
                    "error": "provider_rate_limited",
                    "urgency": "low",
                },
            }
        )

    with pytest.raises(ValidationError):
        ProviderFailureResponses.model_validate(
            {
                "error": "provider_rate_limited",
                "detail": "The LLM provider...",
                "fallback": {
                    "assessment": "unavailable",
                    "error": "provider_rate_limited",
                    "urgency": "high",
                    "confidence": 0.9,
                },
            }
        )


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
