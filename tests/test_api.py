from fastapi.testclient import TestClient

from app.main import app
from app.schema import HandoverPackage

client = TestClient(app)


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
    from unittest import mock

    package = HandoverPackage(
        handoff_needed=True,
        reason="billing_dispute",
        summary="Duplicate charge requires human review.",
        urgency="high",
        suggested_team="billing",
        confidence=0.9,
    )
    fake_generate = mock.MagicMock(return_value=package)
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    response = client.post("/handover", json={"messages": []})

    assert response.status_code == 422
    fake_generate.assert_not_called()


def test_provider_unavailable_returns_503(monkeypatch):
    from unittest import mock

    from app.errors import ProviderUnavailableError

    fake_generate = mock.MagicMock(
        side_effect=ProviderUnavailableError("provider is down")
    )
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)

    response = client.post(
        "/handover", json={"messages": [{"role": "bot", "content": "Hello"}]}
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": "provider_unavailable",
        "detail": ("The LLM provider is temporarily unavailable. Please retry later."),
    }


def test_invalid_llm_response_returns_502(monkeypatch):
    from unittest import mock

    from app.errors import InvalidLLMResponseError

    fake_generate = mock.MagicMock(
        side_effect=InvalidLLMResponseError("output does not match the contract")
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
    from unittest import mock

    from app.errors import LLMConfigurationError

    fake_generate = mock.MagicMock(
        side_effect=LLMConfigurationError("client rejected by the provider")
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
    from unittest import mock

    fake_generate = mock.MagicMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr("app.main.generate_handover_package", fake_generate)
    failing_client = TestClient(app, raise_server_exceptions=False)

    response = failing_client.post(
        "/handover", json={"messages": [{"role": "bot", "content": "Hello"}]}
    )

    assert response.status_code == 500
    assert response.json() == {"error": "internal_error"}
    assert "detail" not in response.json()
    assert "boom" not in response.text
