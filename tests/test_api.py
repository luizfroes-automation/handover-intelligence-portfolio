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
