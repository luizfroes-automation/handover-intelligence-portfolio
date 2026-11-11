"""A provider refusal for capacity must not be reported as our misconfiguration.

The behaviour tests drive the real `_get_client()` path: the production code
translates the error, the real SDK builds the request and HTTPX sends it. Only
the base URL is redirected to a loopback origin, and the origin answers with the
status under test, so the number of requests it receives is the evidence that no
retry was attempted.
"""

import json
import logging
import os
import socketserver
import threading

import pytest
from fastapi.testclient import TestClient
from google import genai

from app.main import app

client = TestClient(app)

TRANSCRIPT_MARKER = "synthetic-transcript-marker-enh02"
CREDENTIAL_MARKER = "synthetic-credential-marker-enh02"
PROVIDER_BODY_MARKER = "synthetic-provider-body-marker-enh02"

RATE_LIMITED_BODY = {
    "error": "provider_rate_limited",
    "detail": (
        "The LLM provider is rate-limiting this service or its quota is exhausted."
    ),
}

CONFIGURATION_BODY = {
    "error": "llm_configuration_error",
    "detail": "The service is misconfigured. Please contact support.",
}


def _provider_error_body(status: int, message: str, code: int | None = None) -> dict:
    """The shape the Gemini API documents for an error response."""
    reason = {
        401: "UNAUTHENTICATED",
        403: "PERMISSION_DENIED",
        429: "RESOURCE_EXHAUSTED",
    }[status]
    return {
        "error": {
            "code": status if code is None else code,
            "message": message,
            "status": reason,
        }
    }


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class Origin(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(10)
        try:
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = self.request.recv(4096)
                if not chunk:
                    break
                data += chunk
            head, _, rest = data.partition(b"\r\n\r\n")
            length = 0
            api_key = None
            for line in head.decode("latin-1").split("\r\n"):
                name, _, value = line.partition(":")
                if name.lower() == "content-length":
                    length = int(value.strip())
                if name.lower() == "x-goog-api-key":
                    api_key = value.strip()
            body = rest
            while len(body) < length:
                chunk = self.request.recv(4096)
                if not chunk:
                    break
                body += chunk

            self.server.events.append("request_received")
            self.server.events.append(
                "api_key_matches_synthetic="
                + ("true" if api_key == self.server.expected_key else "false")
            )
            payload = json.dumps(self.server.payload).encode()
            headers = [
                b"HTTP/1.1 " + str(self.server.status).encode() + b" Error\r\n",
                b"Content-Type: application/json\r\n",
                b"Connection: close\r\n",
                b"Retry-After: 27\r\n",
                b"Content-Length: " + str(len(payload)).encode() + b"\r\n",
            ]
            self.request.sendall(b"".join(headers) + b"\r\n" + payload)
        except OSError:
            self.server.events.append("handler_closed")


@pytest.fixture(autouse=True)
def loopback_only(monkeypatch):
    """Keep the SDK's HTTPX client from routing through an environment proxy."""
    for name in list(os.environ):
        if "proxy" in name.lower():
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("httpx._utils.getproxies", dict)
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)


@pytest.fixture
def origin():
    servers = []

    def start(*, status: int, payload: dict):
        server = Server(("127.0.0.1", 0), Origin)
        server.events = []
        server.status = status
        server.payload = payload
        server.expected_key = CREDENTIAL_MARKER
        servers.append(server)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server

    yield start

    for server in servers:
        server.shutdown()
        server.server_close()


def _use_origin(monkeypatch, server) -> None:
    """Keep the production client path, redirecting only the base URL."""
    real_client = genai.Client

    def build(*args, **kwargs):
        options = dict(kwargs.get("http_options") or {})
        options["base_url"] = f"http://127.0.0.1:{server.server_address[1]}"
        kwargs["http_options"] = options
        return real_client(*args, **kwargs)

    monkeypatch.setattr("app.llm_client.genai.Client", build)
    monkeypatch.setattr("app.llm_client._client", None)
    monkeypatch.setattr("app.llm_client._API_KEY", CREDENTIAL_MARKER)


def _post():
    return client.post(
        "/handover",
        json={"messages": [{"role": "bot", "content": TRANSCRIPT_MARKER}]},
    )


def test_a_rate_limited_origin_reaches_the_503_contract(monkeypatch, caplog, origin):
    server = origin(
        status=429,
        payload=_provider_error_body(
            429, f"quota exhausted for {PROVIDER_BODY_MARKER}"
        ),
    )
    _use_origin(monkeypatch, server)

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = _post()

    assert response.status_code == 503
    assert response.json() == RATE_LIMITED_BODY
    # The origin received exactly one request: the P1 did not retry.
    assert server.events.count("request_received") == 1
    assert "api_key_matches_synthetic=true" in server.events
    # The provider's timing hint is not forwarded, because the service does not
    # promise that a later attempt would succeed.
    assert "retry-after" not in response.headers
    assert "provider_throttled_or_quota_exhausted" in caplog.text
    for marker in (TRANSCRIPT_MARKER, CREDENTIAL_MARKER, PROVIDER_BODY_MARKER):
        assert marker not in caplog.text
        assert marker not in response.text


def test_a_body_code_that_disagrees_does_not_change_the_classification(
    monkeypatch, caplog, origin
):
    """The SDK carries the HTTP status; the body is provider text, not contract."""
    server = origin(
        status=429,
        payload=_provider_error_body(429, "solve this", code=400),
    )
    _use_origin(monkeypatch, server)

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = _post()

    assert response.status_code == 503
    assert response.json()["error"] == "provider_rate_limited"
    assert server.events.count("request_received") == 1


def test_an_authentication_rejection_keeps_the_configuration_contract(
    monkeypatch, caplog, origin
):
    server = origin(
        status=401,
        payload=_provider_error_body(401, f"invalid key {PROVIDER_BODY_MARKER}"),
    )
    _use_origin(monkeypatch, server)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = _post()

    assert response.status_code == 500
    assert response.json() == CONFIGURATION_BODY
    # The origin received exactly one request, with the synthetic key.
    assert server.events.count("request_received") == 1
    assert "api_key_matches_synthetic=true" in server.events
    # The rejection category is named; the cause is not claimed.
    assert "LLM provider rejected authentication or permission" in caplog.text
    assert "misconfigured" not in caplog.text
    assert "provider_auth_rejected" in caplog.text
    assert "provider_permission_denied" not in caplog.text
    for marker in (TRANSCRIPT_MARKER, CREDENTIAL_MARKER, PROVIDER_BODY_MARKER):
        assert marker not in caplog.text
        assert marker not in response.text


def test_a_permission_rejection_keeps_the_configuration_contract(
    monkeypatch, caplog, origin
):
    server = origin(
        status=403,
        payload=_provider_error_body(403, f"permission denied {PROVIDER_BODY_MARKER}"),
    )
    _use_origin(monkeypatch, server)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = _post()

    assert response.status_code == 500
    assert response.json() == CONFIGURATION_BODY
    assert server.events.count("request_received") == 1
    assert "api_key_matches_synthetic=true" in server.events
    assert "LLM provider rejected authentication or permission" in caplog.text
    assert "misconfigured" not in caplog.text
    assert "provider_permission_denied" in caplog.text
    assert "provider_auth_rejected" not in caplog.text
    for marker in (TRANSCRIPT_MARKER, CREDENTIAL_MARKER, PROVIDER_BODY_MARKER):
        assert marker not in caplog.text
        assert marker not in response.text
