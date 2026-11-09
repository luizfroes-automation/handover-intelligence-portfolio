"""Internal TLS diagnostic: a fixed identifier in the log, never in the body."""

import logging
import ssl
from unittest import mock

import httpcore
import httpx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

TLS_IDENTIFIER = "tls_certificate_verification_failed"

TRANSCRIPT_MARKER = "synthetic-transcript-marker-enh14"
CREDENTIAL_MARKER = "synthetic-credential-marker-enh14"
CERTIFICATE_MARKER = "synthetic-certificate-marker-enh14"
URL_MARKER = "synthetic-authenticated-url-marker-enh14"


def _client_raising(monkeypatch, error: Exception) -> None:
    """Replace only the client acquisition; the real translation still runs."""
    fake_client = mock.MagicMock(spec=["models"])
    fake_client.models.generate_content.side_effect = error
    monkeypatch.setattr("app.llm_client._get_client", lambda: fake_client)


def _tls_verification_error() -> ssl.SSLCertVerificationError:
    return ssl.SSLCertVerificationError(
        1,
        f"certificate verify failed: {CERTIFICATE_MARKER} "
        f"url=https://user:{CREDENTIAL_MARKER}@{URL_MARKER} "
        f"transcript={TRANSCRIPT_MARKER}",
    )


def _transport_chain(tail: BaseException) -> httpx.ConnectError:
    """Reproduce the run3 shape: ConnectError <- httpcore <- tail via __context__."""
    inner = httpcore.ConnectError("synthetic transport failure")
    inner.__context__ = tail
    outer = httpx.ConnectError("synthetic transport failure")
    outer.__cause__ = inner
    return outer


def _post(messages=None):
    return client.post(
        "/handover",
        json={"messages": messages or [{"role": "bot", "content": TRANSCRIPT_MARKER}]},
    )


def test_certificate_verification_failure_is_logged_and_keeps_the_503_contract(
    monkeypatch, caplog
):
    _client_raising(monkeypatch, _transport_chain(_tls_verification_error()))

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = _post()

    assert response.status_code == 503
    assert response.json() == {
        "error": "provider_unavailable",
        "detail": "The LLM provider is temporarily unavailable. Please retry later.",
    }
    assert TLS_IDENTIFIER in caplog.text
    assert TLS_IDENTIFIER not in response.text
    for marker in (
        CERTIFICATE_MARKER,
        URL_MARKER,
        CREDENTIAL_MARKER,
        TRANSCRIPT_MARKER,
    ):
        assert marker not in caplog.text
        assert marker not in response.text


def test_generic_connection_refusal_has_no_tls_identifier(monkeypatch, caplog):
    refusal = ConnectionRefusedError(111, "synthetic refusal")
    _client_raising(monkeypatch, _transport_chain(refusal))

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = _post()

    assert response.status_code == 503
    assert "ConnectionRefusedError" in caplog.text
    assert TLS_IDENTIFIER not in caplog.text


def test_tls_error_without_verification_evidence_has_no_identifier(monkeypatch, caplog):
    """A handshake failure that is not a certificate verification failure."""
    handshake_error = ssl.SSLError(
        1, f"synthetic handshake failure {CERTIFICATE_MARKER}"
    )
    _client_raising(monkeypatch, _transport_chain(handshake_error))

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = _post()

    assert response.status_code == 503
    assert "SSLError" in caplog.text
    assert TLS_IDENTIFIER not in caplog.text
    assert CERTIFICATE_MARKER not in caplog.text


def test_proxy_error_keeps_the_configuration_contract_without_tls_identifier(
    monkeypatch, caplog
):
    _client_raising(
        monkeypatch,
        httpx.ProxyError(f"tunnel refused url=https://user:{CREDENTIAL_MARKER}@proxy"),
    )

    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = _post()

    assert response.status_code == 500
    assert response.json()["error"] == "llm_configuration_error"
    assert TLS_IDENTIFIER not in caplog.text
    assert CREDENTIAL_MARKER not in caplog.text
