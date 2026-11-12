"""`GET /health` is a liveness check, not a provider check.

The route answers while the provider is unreachable, without credentials, and
without touching the client: a monitor must be able to tell "the process is
serving" from "the provider is down".
"""

from fastapi.testclient import TestClient

from app import llm_client
from app.main import app

client = TestClient(app)


def test_health_returns_the_liveness_body():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_answers_without_provider_credentials(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(llm_client, "_API_KEY", None)
    monkeypatch.setattr(llm_client, "_client", None)

    response = client.get("/health")

    assert response.status_code == 200
    # The route neither created nor kept a client.
    assert llm_client._client is None


def test_health_does_not_touch_the_provider_client(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("the health route touched the provider client")

    monkeypatch.setattr(llm_client, "_get_client", forbidden)
    monkeypatch.setattr(llm_client.genai, "Client", forbidden)
    monkeypatch.setattr(llm_client, "_client", None)

    response = client.get("/health")

    assert response.status_code == 200
    assert llm_client._client is None


def test_the_health_route_is_documented_in_the_schema():
    schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/health"]["get"]
    assert "200" in operation["responses"]

    media = operation["responses"]["200"]["content"]["application/json"]
    assert media["example"] == {"status": "ok"}

    name = media["schema"]["$ref"].rsplit("/", 1)[-1]
    component = schema["components"]["schemas"][name]
    assert component["required"] == ["status"]
    assert component["properties"]["status"]["const"] == "ok"


def test_the_health_route_documents_only_the_successful_response():
    """No 502 or 503 is advertised: the route does not depend on the provider."""
    schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/health"]["get"]
    assert set(operation["responses"]) == {"200"}
