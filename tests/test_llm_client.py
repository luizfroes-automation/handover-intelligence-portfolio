"""Tests for the LLM client error handling and success path."""

from types import SimpleNamespace
from unittest import mock

import httpx
import pytest
from google.genai import errors
from pydantic import ValidationError

from app import llm_client
from app.errors import (
    InvalidLLMResponseError,
    LLMConfigurationError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
    ProxyFailureError,
)
from app.proxy_observer import observe_proxy_connect
from app.schema import HandoverPackage, Team, Urgency

TRANSCRIPT = [
    {"role": "bot", "content": "Hello! How can I help you today?"},
    {"role": "customer", "content": "I was charged twice for my last order."},
]


@pytest.fixture
def fake_client(monkeypatch):
    # Replaces the function that hands out the client, not the module variable.
    client = mock.MagicMock(spec=["models"])
    monkeypatch.setattr(llm_client, "_get_client", lambda: client)
    return client


def _valid_package() -> HandoverPackage:
    return HandoverPackage(
        handoff_needed=True,
        reason="billing_dispute",
        summary="Bot tried to resolve a duplicate charge before the handoff.",
        urgency=Urgency.HIGH,
        suggested_team=Team.BILLING,
        confidence=0.87,
        flags=["repeat_contact"],
    )


def test_connect_error_raises_provider_unavailable_error(fake_client):
    fake_client.models.generate_content.side_effect = httpx.ConnectError(
        "connection refused"
    )

    with pytest.raises(ProviderUnavailableError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert isinstance(exc_info.value.__cause__, httpx.ConnectError)
    assert str(exc_info.value) == "LLM provider is unreachable"


def test_server_error_raises_provider_unavailable_error(fake_client):
    fake_client.models.generate_content.side_effect = errors.ServerError(
        503, {"error": {"message": "service unavailable"}}
    )

    with pytest.raises(ProviderUnavailableError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert isinstance(exc_info.value.__cause__, errors.ServerError)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409])
def test_client_error_raises_llm_configuration_error(fake_client, status):
    fake_client.models.generate_content.side_effect = errors.ClientError(
        status, {"error": {"message": "rejected"}}
    )

    with pytest.raises(LLMConfigurationError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert isinstance(exc_info.value.__cause__, errors.ClientError)
    assert exc_info.value.__cause__.code == status


def test_rate_limited_client_error_raises_provider_rate_limited_error(fake_client):
    fake_client.models.generate_content.side_effect = errors.ClientError(
        429,
        {
            "error": {
                "code": 429,
                "message": "quota exceeded for CUSTOMER-DATA-MARKER",
                "status": "RESOURCE_EXHAUSTED",
            }
        },
    )

    with pytest.raises(ProviderRateLimitedError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert isinstance(exc_info.value.__cause__, errors.ClientError)
    assert exc_info.value.__cause__.code == 429
    # The provider message is not forwarded into our own message.
    assert "CUSTOMER-DATA-MARKER" not in str(exc_info.value)


def test_timeout_raises_provider_unavailable_error(fake_client):
    fake_client.models.generate_content.side_effect = httpx.TimeoutException(
        "request timed out"
    )

    with pytest.raises(ProviderUnavailableError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert isinstance(exc_info.value.__cause__, httpx.TimeoutException)
    assert str(exc_info.value) == "LLM provider request timed out"


def test_remote_protocol_error_raises_provider_unavailable_error(fake_client):
    original = httpx.RemoteProtocolError("peer closed the connection")
    fake_client.models.generate_content.side_effect = original

    with pytest.raises(ProviderUnavailableError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert exc_info.value.__cause__ is original
    assert str(exc_info.value) == "LLM provider connection failed"


TRANSPORT_ERRORS = [
    ("read error", httpx.ReadError),
    ("write error", httpx.WriteError),
    ("close error", httpx.CloseError),
]


@pytest.mark.parametrize(
    "label, error_class",
    TRANSPORT_ERRORS,
    ids=[label for label, _ in TRANSPORT_ERRORS],
)
def test_transport_errors_raise_provider_unavailable_error(
    fake_client, label, error_class
):
    fake_client.models.generate_content.side_effect = error_class("stream interrupted")

    with pytest.raises(ProviderUnavailableError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert isinstance(exc_info.value.__cause__, error_class)
    assert str(exc_info.value) == "LLM provider connection failed"


def test_local_protocol_error_is_not_blamed_on_the_provider(fake_client):
    """A malformed request is our bug, not an unavailable provider."""
    original = httpx.LocalProtocolError("malformed request")
    fake_client.models.generate_content.side_effect = original

    with pytest.raises(httpx.LocalProtocolError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert exc_info.value is original


CLIENT_SIDE_TRANSPORT_ERRORS = [
    ("unsupported protocol", httpx.UnsupportedProtocol),
]


@pytest.mark.parametrize(
    "label, error_class",
    CLIENT_SIDE_TRANSPORT_ERRORS,
    ids=[label for label, _ in CLIENT_SIDE_TRANSPORT_ERRORS],
)
def test_client_side_transport_errors_are_not_blamed_on_the_provider(
    fake_client, label, error_class
):
    original = error_class("client-side transport failure")
    fake_client.models.generate_content.side_effect = original

    with pytest.raises(error_class) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert exc_info.value is original


def test_proxy_error_raises_proxy_failure_error(fake_client):
    original = httpx.ProxyError("tunnel refused with status 407")
    fake_client.models.generate_content.side_effect = original

    with pytest.raises(ProxyFailureError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert exc_info.value.__cause__ is original
    assert str(exc_info.value) == "Proxy request failed"
    # No trace observation was attached: the field stays absent instead of
    # being parsed from the exception message.
    assert exc_info.value.proxy_connect_status is None


def test_a_malformed_observation_keeps_the_original_proxy_failure(fake_client):
    request = httpx.Request("POST", "https://example.invalid")
    observe_proxy_connect(request)
    trace = request.extensions["trace"]
    trace(
        "http11.receive_response_headers.started",
        {"request": SimpleNamespace(method=b"CONNECT")},
    )
    trace(
        "http11.receive_response_headers.complete",
        {"return_value": (b"HTTP/1.1", 407, b"reason", "not-a-list")},
    )
    original = httpx.ProxyError("tunnel refused with status 407")
    original.request = request
    fake_client.models.generate_content.side_effect = original

    with pytest.raises(ProxyFailureError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert exc_info.value.__cause__ is original
    assert str(exc_info.value) == "Proxy request failed"
    assert exc_info.value.proxy_connect_status is None


def _response(parsed):
    """A response stub carrying only what the client reads."""
    response = mock.Mock(spec=["parsed", "prompt_feedback", "candidates"])
    response.parsed = parsed
    response.prompt_feedback = None
    response.candidates = None
    return response


def test_parsed_none_raises_invalid_llm_response_error(fake_client):
    fake_client.models.generate_content.return_value = _response(None)

    with pytest.raises(InvalidLLMResponseError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    # A response without structured output has no provider exception to chain.
    assert exc_info.value.__cause__ is None


def test_schema_violation_raises_invalid_llm_response_error(fake_client):
    payload = _valid_package().model_dump()
    payload["confidence"] = 1.5
    fake_client.models.generate_content.return_value = _response(payload)

    with pytest.raises(InvalidLLMResponseError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert isinstance(exc_info.value.__cause__, ValidationError)


def test_valid_response_returns_handover_package(fake_client):
    package = _valid_package()
    fake_client.models.generate_content.return_value = _response(package)

    result = llm_client.generate_handover_package(TRANSCRIPT)

    assert isinstance(result, HandoverPackage)
    assert result == package


def test_missing_api_key_raises_llm_configuration_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(llm_client, "_API_KEY", None)
    monkeypatch.setattr(llm_client, "_client", None)

    with pytest.raises(
        LLMConfigurationError, match="GEMINI_API_KEY or GOOGLE_API_KEY"
    ) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert exc_info.value.__cause__ is None


def test_resolve_api_key_prefers_gemini_when_both_are_set():
    resolved = llm_client._resolve_api_key(
        {"GEMINI_API_KEY": "gemini-key", "GOOGLE_API_KEY": "google-key"}
    )

    assert resolved.value == "gemini-key"
    assert resolved.source == "GEMINI_API_KEY"


def test_resolve_api_key_falls_back_to_google():
    resolved = llm_client._resolve_api_key({"GOOGLE_API_KEY": "google-key"})

    assert resolved.value == "google-key"
    assert resolved.source == "GOOGLE_API_KEY"


def test_resolve_api_key_treats_empty_gemini_as_absent():
    resolved = llm_client._resolve_api_key(
        {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": "google-key"}
    )

    assert resolved.value == "google-key"
    assert resolved.source == "GOOGLE_API_KEY"


def test_resolve_api_key_treats_blank_gemini_as_absent():
    resolved = llm_client._resolve_api_key(
        {"GEMINI_API_KEY": "   ", "GOOGLE_API_KEY": "google-key"}
    )

    assert resolved.value == "google-key"
    assert resolved.source == "GOOGLE_API_KEY"


def test_resolve_api_key_returns_none_when_no_key_is_set():
    for environ in ({}, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}):
        resolved = llm_client._resolve_api_key(environ)
        assert resolved.value is None
        assert resolved.source is None


def test_resolve_api_key_strips_surrounding_whitespace():
    resolved = llm_client._resolve_api_key({"GEMINI_API_KEY": "  abc  "})

    assert resolved.value == "abc"
    assert resolved.source == "GEMINI_API_KEY"


def test_schema_violation_hides_transcript_content(fake_client):
    payload = {"summary": "CUSTOMER-DATA-MARKER"}
    fake_client.models.generate_content.return_value = _response(payload)

    with pytest.raises(InvalidLLMResponseError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert isinstance(exc_info.value.__cause__, ValidationError)
    message = str(exc_info.value.__cause__)
    assert "CUSTOMER-DATA-MARKER" not in message
    assert "reason" in message


def test_resolve_model_returns_the_default_when_the_variable_is_absent():
    assert llm_client._resolve_model({}) == llm_client.DEFAULT_MODEL


def test_resolve_model_treats_blank_as_absent():
    assert (
        llm_client._resolve_model({"GEMINI_MODEL": "   "}) == llm_client.DEFAULT_MODEL
    )


def test_resolve_model_treats_an_empty_string_as_absent():
    assert llm_client._resolve_model({"GEMINI_MODEL": ""}) == llm_client.DEFAULT_MODEL


def test_resolve_model_returns_the_declared_value():
    assert llm_client._resolve_model({"GEMINI_MODEL": "gemini-x"}) == "gemini-x"
