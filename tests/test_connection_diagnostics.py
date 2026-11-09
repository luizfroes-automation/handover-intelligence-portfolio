"""Internal diagnostic for a connection failure with an undetermined origin.

The chain below is the one the Linux refusal evidence produced, and it is the
same whether the refused TCP connection was to the destination or to the proxy:
the exception carries no information about which peer was attempted. The test
therefore demonstrates the handling of a chain that cannot identify the peer,
not a decision to treat two distinguishable cases alike.
"""

import logging
import ssl
from unittest import mock

import httpcore
import httpx
from fastapi.testclient import TestClient

from app.diagnostics import (
    CONNECTION_FAILURE_ORIGIN_UNDETERMINED,
    connection_failure_identifier,
)
from app.errors import ProviderUnavailableError
from app.main import app

client = TestClient(app)

TLS_IDENTIFIER = "tls_certificate_verification_failed"
NEUTRAL_IDENTIFIER = "connection_failure_origin_undetermined"

TRANSCRIPT_MARKER = "synthetic-transcript-marker-enh12"
CREDENTIAL_MARKER = "synthetic-credential-marker-enh12"
CERTIFICATE_MARKER = "synthetic-certificate-marker-enh12"
URL_MARKER = "synthetic-authenticated-url-marker-enh12"

PROVIDER_UNAVAILABLE_BODY = {
    "error": "provider_unavailable",
    "detail": "The LLM provider is temporarily unavailable. Please retry later.",
}

CONNECTION_FAILURE_BODY = {
    "error": "provider_unavailable",
    "detail": "A connection failure prevented the request from completing.",
}


def _client_raising(monkeypatch, error: Exception) -> None:
    fake_client = mock.MagicMock(spec=["models"])
    fake_client.models.generate_content.side_effect = error
    monkeypatch.setattr("app.llm_client._get_client", lambda: fake_client)


def _refusal_chain() -> httpx.ConnectError:
    """ConnectError <- httpcore.ConnectError <- ConnectionRefusedError."""
    refusal = ConnectionRefusedError(111, f"connection refused {TRANSCRIPT_MARKER}")
    inner = httpcore.ConnectError(f"transport failed url={URL_MARKER}")
    inner.__context__ = refusal
    outer = httpx.ConnectError(f"transport failed key={CREDENTIAL_MARKER}")
    outer.__cause__ = inner
    return outer


def _tls_chain() -> httpx.ConnectError:
    """ConnectError <- httpcore.ConnectError <- SSLCertVerificationError."""
    tls_error = ssl.SSLCertVerificationError(
        1, f"certificate verify failed {CERTIFICATE_MARKER}"
    )
    inner = httpcore.ConnectError("transport failed")
    inner.__context__ = tls_error
    outer = httpx.ConnectError("transport failed")
    outer.__cause__ = inner
    return outer


def _post():
    return client.post(
        "/handover",
        json={"messages": [{"role": "bot", "content": TRANSCRIPT_MARKER}]},
    )


def _records_with(caplog, token: str) -> list[logging.LogRecord]:
    return [record for record in caplog.records if token in record.getMessage()]


def test_refusal_chain_logs_the_neutral_identifier_and_keeps_the_503(
    monkeypatch, caplog
):
    _client_raising(monkeypatch, _refusal_chain())

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = _post()

    assert response.status_code == 503
    assert response.json() == CONNECTION_FAILURE_BODY
    assert NEUTRAL_IDENTIFIER in caplog.text
    assert TLS_IDENTIFIER not in caplog.text

    neutral_records = _records_with(caplog, NEUTRAL_IDENTIFIER)
    assert len(neutral_records) == 1
    assert "provider unavailable" not in neutral_records[0].getMessage().lower()
    assert NEUTRAL_IDENTIFIER not in response.text


def test_the_neutral_identifier_does_not_leak_the_request(monkeypatch, caplog):
    _client_raising(monkeypatch, _refusal_chain())

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = _post()

    for marker in (
        TRANSCRIPT_MARKER,
        CREDENTIAL_MARKER,
        URL_MARKER,
        CERTIFICATE_MARKER,
    ):
        assert marker not in caplog.text
        assert marker not in response.text


def test_certificate_verification_keeps_its_own_identifier(monkeypatch, caplog):
    _client_raising(monkeypatch, _tls_chain())

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = _post()

    assert response.status_code == 503
    assert response.json() == PROVIDER_UNAVAILABLE_BODY
    assert TLS_IDENTIFIER in caplog.text
    assert NEUTRAL_IDENTIFIER not in caplog.text


def test_a_timeout_branch_carries_neither_identifier(monkeypatch, caplog):
    timeout = httpx.ConnectTimeout("synthetic timeout")
    timeout.__context__ = ConnectionRefusedError(111, "refused")
    _client_raising(monkeypatch, timeout)

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = _post()

    assert response.status_code == 503
    assert response.json() == PROVIDER_UNAVAILABLE_BODY
    assert NEUTRAL_IDENTIFIER not in caplog.text
    assert TLS_IDENTIFIER not in caplog.text
    assert "provider unavailable" in caplog.text.lower()


def test_proxy_error_keeps_the_configuration_contract(monkeypatch, caplog):
    _client_raising(monkeypatch, httpx.ProxyError(f"tunnel refused {URL_MARKER}"))

    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = _post()

    assert response.status_code == 500
    assert response.json()["error"] == "llm_configuration_error"
    assert NEUTRAL_IDENTIFIER not in caplog.text
    assert TLS_IDENTIFIER not in caplog.text


# --- the identifier selector on its own ------------------------------------ #


def _translated(cause: BaseException) -> ProviderUnavailableError:
    error = ProviderUnavailableError("synthetic")
    error.__cause__ = cause
    return error


def test_the_constant_is_the_logged_token():
    assert CONNECTION_FAILURE_ORIGIN_UNDETERMINED == NEUTRAL_IDENTIFIER


def test_the_selector_returns_the_neutral_token_for_a_refusal_chain():
    translated = _translated(_refusal_chain())
    assert connection_failure_identifier(translated) == NEUTRAL_IDENTIFIER


def test_the_selector_prefers_the_tls_token():
    translated = _translated(_tls_chain())
    assert connection_failure_identifier(translated) == TLS_IDENTIFIER


def test_the_selector_returns_none_for_other_branches():
    for cause in (
        httpx.ConnectTimeout("synthetic timeout"),
        httpx.ReadError("synthetic read failure"),
        httpx.ProxyError("synthetic proxy failure"),
        RuntimeError("synthetic unexpected error"),
    ):
        assert connection_failure_identifier(_translated(cause)) is None


def test_the_selector_returns_none_without_a_cause():
    assert connection_failure_identifier(ProviderUnavailableError("synthetic")) is None


def test_the_selector_terminates_on_a_cycle():
    first = httpx.ConnectError("first")
    second = httpcore.ConnectError("second")
    first.__cause__ = second
    second.__cause__ = first
    assert connection_failure_identifier(_translated(first)) == NEUTRAL_IDENTIFIER
