"""A content block is a refusal, not an invalid response to be retried.

The provider reports the block on a `200`, so the transport-level classification
cannot see it: the client reads the prompt feedback and the first candidate's
finish reason before it trusts `parsed`. These tests drive the real `_get_client`
path against a loopback origin that answers `200` with a synthetic body.
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
from app.schema import HandoverPackage

client = TestClient(app)

TRANSCRIPT_MARKER = "synthetic-transcript-marker-enh05"
CREDENTIAL_MARKER = "synthetic-credential-marker-enh05"
PROVIDER_BODY_MARKER = "synthetic-provider-body-marker-enh05"
PROMPT_BLOCK_MARKER = "synthetic-prompt-block-marker-enh05"
SAFETY_CATEGORY = "HARM_CATEGORY_HARASSMENT"

CONTENT_BLOCKED_BODY = {
    "error": "content_blocked",
    "detail": (
        "The LLM provider reported a content block. "
        "No usable assessment is available for this request."
    ),
    "fallback": {
        "assessment": "unavailable",
        "error": "content_blocked",
        "urgency": "high",
    },
}

INVALID_RESPONSE_BODY = {
    "error": "invalid_llm_response",
    "detail": (
        "The LLM provider returned an invalid response. "
        "Please retry; if it persists, contact support."
    ),
}

PACKAGE = {
    "handoff_needed": True,
    "reason": "billing_dispute",
    "summary": f"duplicate charge {PROVIDER_BODY_MARKER}",
    "urgency": "high",
    "suggested_team": "billing",
    "confidence": 0.8,
}

PACKAGE_JSON = json.dumps(PACKAGE)


def _candidate(*, finish_reason: str, text: str | None = None) -> dict:
    candidate = {
        "finishReason": finish_reason,
        "index": 0,
        "safetyRatings": [
            {
                "category": SAFETY_CATEGORY,
                "probability": "HIGH",
                "blocked": True,
            }
        ],
    }
    if text is not None:
        candidate["content"] = {"role": "model", "parts": [{"text": text}]}
    return candidate


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class Origin(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(10)
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
        self.request.sendall(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            b"Connection: close\r\nContent-Length: "
            + str(len(payload)).encode()
            + b"\r\n\r\n"
            + payload
        )


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

    def start(payload: dict):
        server = Server(("127.0.0.1", 0), Origin)
        server.events = []
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


# --- the primary regression ------------------------------------------------ #


def test_a_safety_block_with_valid_json_is_not_accepted(monkeypatch, caplog, origin):
    """The SDK parses the text even when the candidate was blocked."""
    server = origin(
        {"candidates": [_candidate(finish_reason="SAFETY", text=PACKAGE_JSON)]}
    )
    _use_origin(monkeypatch, server)

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = _post()

    assert response.status_code == 502
    assert response.json() == CONTENT_BLOCKED_BODY
    assert server.events.count("request_received") == 1
    assert "api_key_matches_synthetic=true" in server.events
    assert "candidate_content_blocked" in caplog.text
    assert "SAFETY" in caplog.text
    for marker in (
        TRANSCRIPT_MARKER,
        CREDENTIAL_MARKER,
        PROVIDER_BODY_MARKER,
        SAFETY_CATEGORY,
    ):
        assert marker not in caplog.text
        assert marker not in response.text


# --- the two stages -------------------------------------------------------- #


def test_a_prompt_block_without_candidates_is_content_blocked(
    monkeypatch, caplog, origin
):
    server = origin(
        {
            "promptFeedback": {
                "blockReason": "SAFETY",
                "blockReasonMessage": f"blocked {PROMPT_BLOCK_MARKER}",
                "safetyRatings": [
                    {
                        "category": SAFETY_CATEGORY,
                        "probability": "HIGH",
                        "blocked": True,
                    }
                ],
            }
        }
    )
    _use_origin(monkeypatch, server)

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = _post()

    assert response.status_code == 502
    assert response.json() == CONTENT_BLOCKED_BODY
    assert server.events.count("request_received") == 1
    assert "api_key_matches_synthetic=true" in server.events
    assert "prompt_content_blocked" in caplog.text
    assert "candidate_content_blocked" not in caplog.text
    assert "SAFETY" in caplog.text
    for marker in (
        TRANSCRIPT_MARKER,
        CREDENTIAL_MARKER,
        PROMPT_BLOCK_MARKER,
        SAFETY_CATEGORY,
    ):
        assert marker not in caplog.text
        assert marker not in response.text


def test_a_blocked_alternative_does_not_veto_the_first_candidate(monkeypatch, origin):
    """Only the candidate the SDK reads decides; the second one is unused."""
    server = origin(
        {
            "candidates": [
                _candidate(finish_reason="STOP", text=PACKAGE_JSON),
                _candidate(finish_reason="SAFETY"),
            ]
        }
    )
    _use_origin(monkeypatch, server)

    response = _post()

    assert response.status_code == 200
    assert server.events.count("request_received") == 1
    assert "api_key_matches_synthetic=true" in server.events
    assert HandoverPackage.model_validate(response.json())


# --- what is not a block --------------------------------------------------- #


def test_a_stopped_candidate_keeps_the_normal_flow(monkeypatch, origin):
    server = origin(
        {"candidates": [_candidate(finish_reason="STOP", text=PACKAGE_JSON)]}
    )
    _use_origin(monkeypatch, server)

    response = _post()

    assert response.status_code == 200
    assert server.events.count("request_received") == 1
    assert "api_key_matches_synthetic=true" in server.events
    assert response.json()["handoff_needed"] is True


def test_a_truncated_candidate_stays_an_invalid_response(monkeypatch, origin):
    server = origin(
        {"candidates": [_candidate(finish_reason="MAX_TOKENS", text=PACKAGE_JSON[:40])]}
    )
    _use_origin(monkeypatch, server)

    response = _post()

    assert response.status_code == 502
    assert response.json() == INVALID_RESPONSE_BODY
    assert "fallback" not in response.json()
    assert server.events.count("request_received") == 1
    assert "api_key_matches_synthetic=true" in server.events


def test_an_unclassified_finish_reason_is_not_a_block(monkeypatch, origin):
    server = origin({"candidates": [_candidate(finish_reason="OTHER")]})
    _use_origin(monkeypatch, server)

    response = _post()

    assert response.status_code == 502
    assert response.json() == INVALID_RESPONSE_BODY
    assert server.events.count("request_received") == 1
    assert "api_key_matches_synthetic=true" in server.events
