"""Tests for the handover endpoint error contract."""

import logging
from unittest import mock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.errors import (
    InvalidLLMResponseError,
    LLMConfigurationError,
    ProviderUnavailableError,
)
from app.llm_client import generate_handover_package
from app.main import app
from app.schema import HandoverPackage, Team, Urgency
from tests.fixtures.transcripts import CASES

client = TestClient(app)


@pytest.mark.live
def test_post_handover_returns_valid_handover_package():
    transcript = {
        "messages": [
            {"role": "bot", "content": "Hello! How can I help you today?"},
            {
                "role": "customer",
                "content": "I was charged twice for my last order.",
            },
            {
                "role": "bot",
                "content": "I'm sorry about that. Let me check your billing history.",
            },
            {
                "role": "customer",
                "content": "This is the second time this happens, I want to talk to a person.",
            },
        ]
    }

    response = client.post("/handover", json=transcript)

    assert response.status_code == 200

    package = HandoverPackage.model_validate(response.json())
    assert isinstance(package, HandoverPackage)


def test_empty_messages_is_rejected_before_the_llm(monkeypatch):
    package = HandoverPackage(
        handoff_needed=True,
        reason="billing_dispute",
        summary="Duplicate charge requires human review.",
        urgency=Urgency.HIGH,
        suggested_team=Team.BILLING,
        confidence=0.9,
    )
    fake_generate = mock.create_autospec(
        generate_handover_package, return_value=package
    )
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    response = client.post("/handover", json={"messages": []})

    assert response.status_code == 422
    fake_generate.assert_not_called()


def test_provider_unavailable_returns_503(monkeypatch):
    fake_generate = mock.create_autospec(
        generate_handover_package,
        side_effect=ProviderUnavailableError("provider is down"),
    )
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    response = client.post(
        "/handover", json={"messages": [{"role": "bot", "content": "Hello"}]}
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": "provider_unavailable",
        "detail": "The LLM provider is temporarily unavailable. Please retry later.",
    }


TRANSCRIPT_MARKER = "synthetic-transcript-marker-enh07"
CREDENTIAL_MARKER = "synthetic-credential-marker-enh07"


def _client_raising(monkeypatch, error: Exception) -> None:
    """Replace only the client acquisition; the real function keeps running."""
    fake_client = mock.MagicMock(spec=["models"])
    fake_client.models.generate_content.side_effect = error
    monkeypatch.setattr("app.llm_client._get_client", lambda: fake_client)


def test_transport_error_reaches_the_503_contract_without_leaking(monkeypatch, caplog):
    error = httpx.RemoteProtocolError(
        f"peer closed the stream: {TRANSCRIPT_MARKER} key={CREDENTIAL_MARKER}"
    )
    _client_raising(monkeypatch, error)

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = client.post(
            "/handover",
            json={"messages": [{"role": "bot", "content": TRANSCRIPT_MARKER}]},
        )

    assert response.status_code == 503
    assert response.json() == {
        "error": "provider_unavailable",
        "detail": "The LLM provider is temporarily unavailable. Please retry later.",
    }
    assert TRANSCRIPT_MARKER not in response.text
    assert CREDENTIAL_MARKER not in response.text
    assert TRANSCRIPT_MARKER not in caplog.text
    assert CREDENTIAL_MARKER not in caplog.text
    assert "ProviderUnavailableError" in caplog.text
    assert "RemoteProtocolError" in caplog.text


def test_unexpected_client_error_keeps_the_generic_500(monkeypatch, caplog):
    _client_raising(monkeypatch, RuntimeError(f"boom {TRANSCRIPT_MARKER}"))
    failing_client = TestClient(app, raise_server_exceptions=False)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = failing_client.post(
            "/handover",
            json={"messages": [{"role": "bot", "content": TRANSCRIPT_MARKER}]},
        )

    assert response.status_code == 500
    assert response.json() == {"error": "internal_error"}
    assert TRANSCRIPT_MARKER not in response.text
    assert TRANSCRIPT_MARKER not in caplog.text
    assert "RuntimeError" in caplog.text


def test_client_side_transport_error_keeps_the_generic_500(monkeypatch, caplog):
    """A malformed request is our failure; it must not answer 503 for the provider."""
    _client_raising(
        monkeypatch, httpx.LocalProtocolError(f"malformed request {TRANSCRIPT_MARKER}")
    )
    failing_client = TestClient(app, raise_server_exceptions=False)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = failing_client.post(
            "/handover",
            json={"messages": [{"role": "bot", "content": TRANSCRIPT_MARKER}]},
        )

    assert response.status_code == 500
    assert response.json() == {"error": "internal_error"}
    assert TRANSCRIPT_MARKER not in response.text
    assert TRANSCRIPT_MARKER not in caplog.text
    assert "LocalProtocolError" in caplog.text


def test_invalid_llm_response_returns_502(monkeypatch):
    fake_generate = mock.create_autospec(
        generate_handover_package,
        side_effect=InvalidLLMResponseError("output does not match the contract"),
    )
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    response = client.post(
        "/handover", json={"messages": [{"role": "bot", "content": "Hello"}]}
    )

    assert response.status_code == 502
    assert response.json() == {
        "error": "invalid_llm_response",
        "detail": (
            "The LLM provider returned an invalid response. "
            "Please retry; if it persists, contact support."
        ),
    }


def test_llm_configuration_error_returns_500(monkeypatch):
    fake_generate = mock.create_autospec(
        generate_handover_package,
        side_effect=LLMConfigurationError("client rejected by the provider"),
    )
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    response = client.post(
        "/handover", json={"messages": [{"role": "bot", "content": "Hello"}]}
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": "llm_configuration_error",
        "detail": "The service is misconfigured. Please contact support.",
    }


def test_unexpected_error_returns_generic_500(monkeypatch):
    fake_generate = mock.create_autospec(
        generate_handover_package, side_effect=RuntimeError("boom")
    )
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)
    failing_client = TestClient(app, raise_server_exceptions=False)

    response = failing_client.post(
        "/handover", json={"messages": [{"role": "bot", "content": "Hello"}]}
    )

    assert response.status_code == 500
    assert response.json() == {"error": "internal_error"}
    assert "detail" not in response.json()
    assert "boom" not in response.text


def test_transcript_without_a_customer_message_reaches_the_llm(monkeypatch):
    case = next(case for case in CASES if case.id == "customer_never_replied")
    package = HandoverPackage(
        handoff_needed=False,
        reason="no_customer_request",
        summary="The bot opened the conversation and the customer never replied.",
        urgency=Urgency.LOW,
        suggested_team=Team.ESCALATIONS,
        confidence=0.6,
    )
    fake_generate = mock.create_autospec(
        generate_handover_package, return_value=package
    )
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    response = client.post("/handover", json={"messages": case.messages})

    assert response.status_code == 200
    fake_generate.assert_called_once()
    assert fake_generate.call_args.args[0] == case.messages
    assert response.json()["handoff_needed"] is False
    assert response.json()["urgency"] == "low"


MAX_MESSAGE_CHARS = 2000
MAX_MESSAGES = 100
MAX_TRANSCRIPT_CHARS = 20000


def _package() -> HandoverPackage:
    return HandoverPackage(
        handoff_needed=False,
        reason="bounded_input",
        summary="probe",
        urgency=Urgency.LOW,
        suggested_team=Team.ESCALATIONS,
        confidence=0.5,
    )


def _messages(count: int, chars_each: int) -> list[dict]:
    return [{"role": "bot", "content": "a" * chars_each} for _ in range(count)]


REJECTED_STRUCTURAL = [
    ("empty content", [{"role": "bot", "content": ""}]),
    ("whitespace only", [{"role": "bot", "content": "  \n\t  "}]),
    ("one character over the message limit", _messages(1, MAX_MESSAGE_CHARS + 1)),
    ("one message over the count limit", _messages(MAX_MESSAGES + 1, 10)),
]


@pytest.mark.parametrize(
    "label, messages",
    REJECTED_STRUCTURAL,
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_rejects_structural_violations_without_calling_the_llm(
    monkeypatch, label, messages
):
    fake_generate = mock.create_autospec(
        generate_handover_package, return_value=_package()
    )
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    response = client.post("/handover", json={"messages": messages})

    assert response.status_code == 422
    fake_generate.assert_not_called()


def test_rejects_a_transcript_over_the_total_without_calling_the_llm(monkeypatch):
    messages = _messages(10, MAX_MESSAGE_CHARS) + [{"role": "bot", "content": "a"}]
    assert (
        sum(len(message["content"]) for message in messages) == MAX_TRANSCRIPT_CHARS + 1
    )

    fake_generate = mock.create_autospec(
        generate_handover_package, return_value=_package()
    )
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    response = client.post("/handover", json={"messages": messages})

    assert response.status_code == 413
    assert response.json()["error"] == "transcript_too_large"
    assert "aaaa" not in response.text
    fake_generate.assert_not_called()


ACCEPTED_AT_THE_BOUNDARY = [
    ("message exactly at the limit", _messages(1, MAX_MESSAGE_CHARS)),
    ("count exactly at the limit", _messages(MAX_MESSAGES, 100)),
    ("total exactly at the limit", _messages(10, MAX_MESSAGE_CHARS)),
]


@pytest.mark.parametrize(
    "label, messages",
    ACCEPTED_AT_THE_BOUNDARY,
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_accepts_inputs_at_the_boundary(monkeypatch, label, messages):
    fake_generate = mock.create_autospec(
        generate_handover_package, return_value=_package()
    )
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    response = client.post("/handover", json={"messages": messages})

    assert response.status_code == 200
    fake_generate.assert_called_once()


def test_preserves_the_content_exactly_as_sent(monkeypatch):
    sent = "  the customer wrote this\n\twith a line break and a tab\tinside  "
    messages = [{"role": "bot", "content": sent}]
    fake_generate = mock.create_autospec(
        generate_handover_package, return_value=_package()
    )
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    response = client.post("/handover", json={"messages": messages})

    assert response.status_code == 200
    delivered = fake_generate.call_args.args[0]
    assert delivered[0]["content"] == sent
    assert delivered[0]["content"].startswith("  ")
    assert delivered[0]["content"].endswith("  ")


def test_structural_error_wins_over_the_total_limit(monkeypatch):
    messages = _messages(MAX_MESSAGES + 1, MAX_MESSAGE_CHARS)
    assert sum(len(message["content"]) for message in messages) > MAX_TRANSCRIPT_CHARS

    fake_generate = mock.create_autospec(
        generate_handover_package, return_value=_package()
    )
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    response = client.post("/handover", json={"messages": messages})

    assert response.status_code == 422
    fake_generate.assert_not_called()
