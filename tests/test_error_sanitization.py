"""Negative tests: a rejected request never reproduces its own content.

Every payload here is synthetic. The marker stands in for transcript text that
must not appear in an HTTP body or in a log record, on any of the paths that can
report a failure: validation (422), total size (413) and the three failures
raised downstream of the endpoint (502, 500, 503).
"""

import logging
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError, field_validator

from app.errors import (
    InvalidLLMResponseError,
    LLMConfigurationError,
    ProviderUnavailableError,
)
from app.llm_client import generate_handover_package
from app.main import app
from app.sanitization import sanitize_validation_errors
from app.schema import (
    MAX_MESSAGE_CHARS,
    HandoverPackage,
    Message,
    Team,
    TranscriptRequest,
    Urgency,
)

MARKER = "synthetic-transcript-marker-enh08"

client = TestClient(app, raise_server_exceptions=False)


class _EchoingModel(BaseModel):
    """A validator that writes the rejected value into its own message."""

    value: str

    @field_validator("value")
    @classmethod
    def echo(cls, value: str) -> str:
        raise ValueError(f"rejected value: {value}")


def _post(messages):
    return client.post("/handover", json={"messages": messages})


def _content_at_the_limit() -> str:
    padding = MAX_MESSAGE_CHARS - len(MARKER)
    return MARKER + "x" * padding


def _over_the_message_limit():
    return [{"role": "bot", "content": _content_at_the_limit() + "x"}]


def _over_the_total_limit():
    return [{"role": "bot", "content": _content_at_the_limit()}] * 11


def _package() -> HandoverPackage:
    return HandoverPackage(
        handoff_needed=False,
        reason="bounded_input",
        summary="probe",
        urgency=Urgency.LOW,
        suggested_team=Team.ESCALATIONS,
        confidence=0.5,
    )


def _raise_invalid_from_provider_output(payload: dict):
    def raise_it(transcript):
        try:
            HandoverPackage.model_validate(payload)
        except ValidationError as exc:
            raise InvalidLLMResponseError(
                "LLM provider output does not match the handover package schema"
            ) from exc

    return raise_it


def _raise_behind_a_cause(error: Exception):
    def raise_it(transcript):
        try:
            raise RuntimeError(f"upstream failure while encoding {MARKER}")
        except RuntimeError as cause:
            raise error from cause

    return raise_it


def test_validation_response_keeps_only_safe_fields():
    response = _post(_over_the_message_limit())

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert set(error) == {"type", "loc", "msg"}
    assert error["type"] == "string_too_long"
    assert error["loc"] == ["body", "messages", 0, "content"]
    assert "at most 2000 characters" in error["msg"]
    assert MARKER not in response.text


def test_validation_response_drops_the_context_and_the_input():
    response = _post([{"role": "bot", "content": "  \n\t  "}])

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert set(error) == {"type", "loc", "msg"}
    assert error["type"] == "value_error"
    assert error["msg"] == "Value rejected by a field rule"


def test_custom_validator_messages_are_not_forwarded():
    with pytest.raises(ValidationError) as caught:
        _EchoingModel(value=MARKER)

    [error] = sanitize_validation_errors(caught.value.errors())

    assert error["type"] == "value_error"
    assert error["loc"] == ["value"]
    assert error["msg"] == "Value rejected by a field rule"


def test_malformed_json_reports_the_position_but_not_the_body():
    body = '{"messages": [{"role": "bot", "content": "' + MARKER + '"'

    response = client.post(
        "/handover",
        content=body.encode(),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert set(error) == {"type", "loc", "msg"}
    assert error["type"] == "json_invalid"
    assert MARKER not in response.text


def test_unknown_fields_are_ignored_and_never_become_a_location(monkeypatch, caplog):
    fake_generate = mock.create_autospec(
        generate_handover_package, return_value=_package()
    )
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = client.post(
            "/handover",
            json={
                "messages": [{"role": "bot", "content": "Hello", MARKER: MARKER}],
                MARKER: MARKER,
            },
        )

    assert response.status_code == 200
    assert MARKER not in response.text
    assert MARKER not in caplog.text
    fake_generate.assert_called_once()


def test_no_model_forbids_extra_fields():
    """Only ``extra="forbid"`` puts the key sent by the client into ``loc``."""
    for model in (Message, TranscriptRequest, HandoverPackage):
        assert model.model_config.get("extra") != "forbid"


def test_validation_log_limits_the_number_of_rules_reported(caplog):
    messages = [{"role": "bot", "content": _content_at_the_limit() + "x"}] * 100

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = _post(messages)

    assert response.status_code == 422
    assert len(response.json()["detail"]) == 100
    assert caplog.text.count("[string_too_long]") == 5
    assert "+95 more" in caplog.text
    assert MARKER not in caplog.text


def test_validation_is_logged_with_diagnostics_but_without_the_content(caplog):
    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = _post(_over_the_message_limit())

    assert response.status_code == 422
    assert MARKER not in caplog.text
    assert "string_too_long" in caplog.text
    assert "messages/0/content" in caplog.text


def test_rejected_structural_input_never_reaches_the_llm(monkeypatch):
    fake_generate = mock.create_autospec(
        generate_handover_package, return_value=_package()
    )
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    assert _post(_over_the_message_limit()).status_code == 422
    fake_generate.assert_not_called()


def test_total_limit_response_and_log_carry_no_content(monkeypatch, caplog):
    fake_generate = mock.create_autospec(
        generate_handover_package, return_value=_package()
    )
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = _post(_over_the_total_limit())

    assert response.status_code == 413
    assert response.json()["error"] == "transcript_too_large"
    assert MARKER not in response.text
    assert MARKER not in caplog.text
    fake_generate.assert_not_called()


def test_invalid_provider_output_logs_the_rule_but_not_the_content(monkeypatch, caplog):
    payload = {
        "handoff_needed": True,
        "reason": "billing_dispute",
        "summary": "Duplicate charge requires human review.",
        "urgency": "high",
        "suggested_team": "billing",
        "confidence": 0.9,
        "flags": MARKER,
    }
    fake_generate = mock.create_autospec(generate_handover_package)
    fake_generate.side_effect = _raise_invalid_from_provider_output(payload)
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = _post([{"role": "bot", "content": "Hello"}])

    assert response.status_code == 502
    assert MARKER not in response.text
    assert MARKER not in caplog.text
    assert "ValidationError" in caplog.text
    assert "flags" in caplog.text
    assert "list_type" in caplog.text


def test_configuration_failure_logs_the_chain_but_not_the_content(monkeypatch, caplog):
    fake_generate = mock.create_autospec(generate_handover_package)
    fake_generate.side_effect = _raise_behind_a_cause(
        LLMConfigurationError("LLM provider rejected the client configuration")
    )
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = _post([{"role": "bot", "content": "Hello"}])

    assert response.status_code == 500
    assert response.json() == {
        "error": "llm_configuration_error",
        "detail": "The service is misconfigured. Please contact support.",
    }
    assert MARKER not in caplog.text
    assert "LLMConfigurationError" in caplog.text
    assert "RuntimeError" in caplog.text


def test_unexpected_failure_logs_the_type_and_location_but_not_the_content(
    monkeypatch, caplog
):
    fake_generate = mock.create_autospec(generate_handover_package)
    fake_generate.side_effect = RuntimeError(f"failed to encode transcript: {MARKER}")
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = _post([{"role": "bot", "content": "Hello"}])

    assert response.status_code == 500
    assert response.json() == {"error": "internal_error"}
    assert MARKER not in caplog.text
    assert "failed to encode transcript" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_provider_unavailable_logs_the_cause_type_but_not_its_message(
    monkeypatch, caplog
):
    fake_generate = mock.create_autospec(generate_handover_package)
    fake_generate.side_effect = _raise_behind_a_cause(
        ProviderUnavailableError("LLM provider failed to serve the request")
    )
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = _post([{"role": "bot", "content": "Hello"}])

    assert response.status_code == 503
    assert MARKER not in caplog.text
    assert "ProviderUnavailableError" in caplog.text


def test_pydantic_errors_still_carry_the_rejected_input():
    """Characterises the leak the sanitizer removes: errors() keeps the value."""
    with pytest.raises(ValidationError) as caught:
        HandoverPackage.model_validate(
            {
                "handoff_needed": True,
                "reason": "billing_dispute",
                "summary": "Duplicate charge requires human review.",
                "urgency": "high",
                "suggested_team": "billing",
                "confidence": 0.9,
                "flags": MARKER,
            }
        )

    assert MARKER in repr(caught.value.errors())
