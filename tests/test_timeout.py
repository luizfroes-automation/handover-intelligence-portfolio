"""The provider call must stop waiting when the response stops progressing.

The behaviour test drives the real `_get_client()` path: the production code
chooses the timeout, the real SDK builds the request and the real HTTPX applies
it. Only the base URL is redirected to a loopback origin, and the timeout is
lowered to a laboratory value through the same constant production reads.
"""

import json
import logging
import socketserver
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from google import genai

from app import llm_client
from app.errors import ProviderUnavailableError
from app.main import app

client = TestClient(app)

LAB_TIMEOUT_MS = 300
PRODUCTION_TIMEOUT_MS = 20_000
HOLD_SECONDS = 2.0

TRANSCRIPT_MARKER = "synthetic-transcript-marker-enh03"
CREDENTIAL_MARKER = "synthetic-credential-marker-enh03"

PROVIDER_UNAVAILABLE_BODY = {
    "error": "provider_unavailable",
    "detail": "The LLM provider is temporarily unavailable. Please retry later.",
}

PACKAGE_BODY = {
    "handoff_needed": False,
    "reason": "resolved_no_handoff",
    "summary": "synthetic package from the loopback origin",
    "urgency": "low",
    "suggested_team": "escalations",
    "confidence": 0.5,
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
            for line in head.decode("latin-1").split("\r\n"):
                name, _, value = line.partition(":")
                if name.lower() == "content-length":
                    length = int(value.strip())
            body = rest
            while len(body) < length:
                chunk = self.request.recv(4096)
                if not chunk:
                    break
                body += chunk

            self.server.events.append("request_received")
            self.server.release.wait(self.server.hold)
            payload = json.dumps(self.server.payload).encode()
            self.request.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                b"Connection: close\r\nContent-Length: "
                + str(len(payload)).encode()
                + b"\r\n\r\n"
                + payload
            )
            self.server.events.append("response_sent")
        except OSError:
            self.server.events.append("handler_closed")


@pytest.fixture
def origin():
    servers = []

    def start(*, hold: float, payload: dict) -> Server:
        server = Server(("127.0.0.1", 0), Origin)
        server.events = []
        server.hold = hold
        server.payload = payload
        server.release = threading.Event()
        servers.append(server)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server

    yield start

    for server in servers:
        server.release.set()
        server.shutdown()
        server.server_close()


def _use_origin(monkeypatch, server: Server, timeout_ms: int) -> None:
    """Keep the production client path, redirecting only the base URL."""
    real_client = genai.Client

    def build(*args, **kwargs):
        options = dict(kwargs.get("http_options") or {})
        options["base_url"] = f"http://127.0.0.1:{server.server_address[1]}"
        kwargs["http_options"] = options
        return real_client(*args, **kwargs)

    monkeypatch.setattr("app.llm_client.genai.Client", build)
    monkeypatch.setattr("app.llm_client._client", None)
    monkeypatch.setattr("app.llm_client._API_KEY", "synthetic-loopback-only")
    monkeypatch.setattr("app.llm_client.DEFAULT_TIMEOUT_MS", timeout_ms, raising=False)


def _post():
    return client.post(
        "/handover",
        json={"messages": [{"role": "bot", "content": TRANSCRIPT_MARKER}]},
    )


def test_the_production_client_configures_the_provisional_timeout(monkeypatch):
    captured = {}

    def spy(*args, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("app.llm_client.genai.Client", spy)
    monkeypatch.setattr("app.llm_client._client", None)
    monkeypatch.setattr("app.llm_client._API_KEY", "synthetic-loopback-only")

    llm_client._get_client()

    options = captured.get("http_options") or {}
    assert options.get("timeout") == PRODUCTION_TIMEOUT_MS


def test_a_stalled_read_reaches_the_503_contract(monkeypatch, caplog, origin):
    server = origin(hold=HOLD_SECONDS, payload={"candidates": []})
    _use_origin(monkeypatch, server, LAB_TIMEOUT_MS)

    started = time.monotonic()
    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = _post()
    elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert response.json() == PROVIDER_UNAVAILABLE_BODY
    assert "request_received" in server.events
    assert TRANSCRIPT_MARKER not in caplog.text
    assert TRANSCRIPT_MARKER not in response.text
    assert CREDENTIAL_MARKER not in caplog.text
    assert CREDENTIAL_MARKER not in response.text
    assert elapsed < HOLD_SECONDS / 2


def test_the_translated_cause_is_a_read_timeout(monkeypatch, origin):
    server = origin(hold=HOLD_SECONDS, payload={"candidates": []})
    _use_origin(monkeypatch, server, LAB_TIMEOUT_MS)

    with pytest.raises(ProviderUnavailableError) as exc_info:
        llm_client.generate_handover_package(
            [{"role": "bot", "content": TRANSCRIPT_MARKER}]
        )

    assert "request_received" in server.events
    assert isinstance(exc_info.value.__cause__, httpx.ReadTimeout)


def test_a_fast_response_keeps_the_normal_flow(monkeypatch, origin):
    server = origin(
        hold=0.0,
        payload={
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [{"text": json.dumps(PACKAGE_BODY)}],
                    }
                }
            ]
        },
    )
    _use_origin(monkeypatch, server, LAB_TIMEOUT_MS)

    response = _post()

    assert server.events[:2] == ["request_received", "response_sent"]
    assert response.status_code == 200
    assert response.json()["handoff_needed"] is False
