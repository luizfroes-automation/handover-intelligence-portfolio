"""Tests for the LLM client error handling and success path."""

from unittest import mock

import httpx
import pytest
from google.genai import errors
from pydantic import ValidationError

from app import llm_client
from app.errors import (
    InvalidLLMResponseError,
    LLMConfigurationError,
    ProviderUnavailableError,
)
from app.schema import HandoverPackage, Team, Urgency

TRANSCRIPT = [
    {"role": "bot", "content": "Hello! How can I help you today?"},
    {"role": "customer", "content": "I was charged twice for my last order."},
]


@pytest.fixture
def fake_client(monkeypatch):
    # Substitui a função que entrega o cliente, não a variável de módulo.
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


def test_server_error_raises_provider_unavailable_error(fake_client):
    fake_client.models.generate_content.side_effect = errors.ServerError(
        503, {"error": {"message": "service unavailable"}}
    )

    with pytest.raises(ProviderUnavailableError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert isinstance(exc_info.value.__cause__, errors.ServerError)


def test_client_error_raises_llm_configuration_error(fake_client):
    fake_client.models.generate_content.side_effect = errors.ClientError(
        404, {"error": {"message": "model not found"}}
    )

    with pytest.raises(LLMConfigurationError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert isinstance(exc_info.value.__cause__, errors.ClientError)


def test_timeout_raises_provider_unavailable_error(fake_client):
    fake_client.models.generate_content.side_effect = httpx.TimeoutException(
        "request timed out"
    )

    with pytest.raises(ProviderUnavailableError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert isinstance(exc_info.value.__cause__, httpx.TimeoutException)


def test_parsed_none_raises_invalid_llm_response_error(fake_client):
    response = mock.Mock(spec=["parsed"])
    response.parsed = None
    fake_client.models.generate_content.return_value = response

    with pytest.raises(InvalidLLMResponseError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    # Uma resposta sem saída estruturada não tem exceção do provider para encadear.
    assert exc_info.value.__cause__ is None


def test_schema_violation_raises_invalid_llm_response_error(fake_client):
    payload = _valid_package().model_dump()
    payload["confidence"] = 1.5
    response = mock.Mock(spec=["parsed"])
    response.parsed = payload
    fake_client.models.generate_content.return_value = response

    with pytest.raises(InvalidLLMResponseError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert isinstance(exc_info.value.__cause__, ValidationError)


def test_valid_response_returns_handover_package(fake_client):
    package = _valid_package()
    response = mock.Mock(spec=["parsed"])
    response.parsed = package
    fake_client.models.generate_content.return_value = response

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

    assert resolved == "gemini-key"


def test_resolve_api_key_falls_back_to_google():
    resolved = llm_client._resolve_api_key({"GOOGLE_API_KEY": "google-key"})

    assert resolved == "google-key"


def test_resolve_api_key_treats_empty_gemini_as_absent():
    resolved = llm_client._resolve_api_key(
        {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": "google-key"}
    )

    assert resolved == "google-key"


def test_resolve_api_key_treats_blank_gemini_as_absent():
    resolved = llm_client._resolve_api_key(
        {"GEMINI_API_KEY": "   ", "GOOGLE_API_KEY": "google-key"}
    )

    assert resolved == "google-key"


def test_resolve_api_key_returns_none_when_no_key_is_set():
    assert llm_client._resolve_api_key({}) is None
    assert (
        llm_client._resolve_api_key({"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""})
        is None
    )


def test_resolve_api_key_strips_surrounding_whitespace():
    resolved = llm_client._resolve_api_key({"GEMINI_API_KEY": "  abc  "})

    assert resolved == "abc"


def test_schema_violation_hides_transcript_content(fake_client):
    payload = {"summary": "CUSTOMER-DATA-MARKER"}
    response = mock.Mock(spec=["parsed"])
    response.parsed = payload
    fake_client.models.generate_content.return_value = response

    with pytest.raises(InvalidLLMResponseError) as exc_info:
        llm_client.generate_handover_package(TRANSCRIPT)

    assert isinstance(exc_info.value.__cause__, ValidationError)
    message = str(exc_info.value.__cause__)
    assert "CUSTOMER-DATA-MARKER" not in message
    assert "reason" in message
