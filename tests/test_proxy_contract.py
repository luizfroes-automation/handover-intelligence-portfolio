"""The real SDK reaches the proxy contract when the CONNECT is refused.

The proxy answers the tunnel request with 502 or 407 and closes; the SDK turns it
into `httpx.ProxyError`, the client into `ProxyFailureError`, and the API answers
`500 proxy_error`. Each test counts the tunnel attempts, so a retry would fail it,
and the reason phrase carries a marker that must never reach the body or the log.
"""

import logging
import os
import socketserver
import threading

import pytest
from fastapi.testclient import TestClient
from google import genai

from app.main import app

client = TestClient(app)

TRANSCRIPT_MARKER = "synthetic-transcript-marker-enh15"
CREDENTIAL_MARKER = "synthetic-credential-marker-enh15"
REASON_MARKER = "synthetic-proxy-reason-marker-enh15"

PROXY_BODY = {
    "error": "proxy_error",
    "detail": "The request could not be completed through the proxy.",
}


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class Proxy(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = self.request.recv(4096)
            if not chunk:
                break
            data += chunk
        if data.startswith(b"CONNECT "):
            self.server.attempts += 1
        self.request.sendall(
            b"HTTP/1.1 "
            + str(self.server.status).encode()
            + b" "
            + REASON_MARKER.encode()
            + b"\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        )


@pytest.fixture
def proxy_origin():
    servers = []

    def start(status: int) -> Server:
        server = Server(("127.0.0.1", 0), Proxy)
        server.status = status
        server.attempts = 0
        servers.append(server)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server

    yield start

    for server in servers:
        server.shutdown()
        server.server_close()


def _use_proxy(monkeypatch, server: Server) -> None:
    """Keep the production client path and send it through the loopback proxy."""
    real_client = genai.Client

    def build(*args, **kwargs):
        options = dict(kwargs.get("http_options") or {})
        options["base_url"] = "https://example.invalid"
        kwargs["http_options"] = options
        return real_client(*args, **kwargs)

    for name in list(os.environ):
        if "proxy" in name.lower():
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTPS_PROXY", f"http://127.0.0.1:{server.server_address[1]}")
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    monkeypatch.setattr("app.llm_client.genai.Client", build)
    monkeypatch.setattr("app.llm_client._client", None)
    monkeypatch.setattr("app.llm_client._API_KEY", CREDENTIAL_MARKER)


@pytest.mark.parametrize("status", [502, 407])
def test_a_refused_connect_reaches_the_proxy_contract(
    monkeypatch, caplog, proxy_origin, status
):
    server = proxy_origin(status)
    _use_proxy(monkeypatch, server)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = client.post(
            "/handover",
            json={"messages": [{"role": "bot", "content": TRANSCRIPT_MARKER}]},
        )

    assert response.status_code == 500
    assert response.json() == PROXY_BODY
    # Exactly one tunnel attempt: the P1 did not retry.
    assert server.attempts == 1
    assert "proxy_failure_origin_undetermined" in caplog.text
    assert "ProxyFailureError" in caplog.text
    assert "ProxyError" in caplog.text
    # The raw reason phrase and the request never reach the client or the log.
    for marker in (TRANSCRIPT_MARKER, CREDENTIAL_MARKER, REASON_MARKER):
        assert marker not in caplog.text
        assert marker not in response.text
