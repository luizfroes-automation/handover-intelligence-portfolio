"""Deterministic end-to-end check of the handover endpoint.

The LLM is replaced at the client boundary, following the error-handling convention:
the fixture substitutes ``_get_client``, not ``_client``. The test proves the
wiring — what the endpoint sent to the provider and what it returned — and says
nothing about classification quality.
"""

from unittest import mock

from fastapi.testclient import TestClient

from app import llm_client
from app.main import app
from app.schema import HandoverPackage, Team, Urgency

client = TestClient(app)

TRANSCRIPT = [
    {"role": "bot", "content": "Hello! How can I help you today?"},
    {"role": "customer", "content": "I was charged twice for my last order."},
]

EXPECTED_CONTENTS = (
    "bot: Hello! How can I help you today?\n"
    "customer: I was charged twice for my last order."
)


def _package() -> HandoverPackage:
    return HandoverPackage(
        handoff_needed=True,
        reason="billing_dispute",
        summary="Duplicate charge requires human review.",
        urgency=Urgency.HIGH,
        suggested_team=Team.BILLING,
        confidence=0.92,
        flags=["repeat_contact"],
    )


def _fake_client(monkeypatch, parsed):
    response = mock.Mock(spec=["parsed"])
    response.parsed = parsed
    fake = mock.MagicMock(spec=["models"])
    fake.models.generate_content.return_value = response
    monkeypatch.setattr(llm_client, "_get_client", lambda: fake)
    return fake


def test_post_handover_returns_the_generated_package(monkeypatch):
    package = _package()
    fake = _fake_client(monkeypatch, package)

    response = client.post("/handover", json={"messages": TRANSCRIPT})

    assert response.status_code == 200
    assert HandoverPackage.model_validate(response.json()) == package
    assert (
        fake.models.generate_content.call_args.kwargs["contents"] == EXPECTED_CONTENTS
    )
