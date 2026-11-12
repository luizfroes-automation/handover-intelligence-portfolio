"""The key fallback is announced once, at import, without the key itself.

Each scenario reloads the module with the local `.env` disabled and only the
synthetic variables it sets, so the outcome depends on nothing else. The
warning is a startup message: `_resolve_api_key` never logs.
"""

import importlib
import logging

import dotenv
import pytest

from app import llm_client

SYNTHETIC_KEY = "synthetic-google-key-enh09"
WARNING = "GEMINI_API_KEY is not set; using GOOGLE_API_KEY"


@pytest.fixture
def isolated_import(monkeypatch):
    """Keep the local .env and the previous environment out of the scenario."""
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    yield

    # Leave the module holding the same state the isolated environment implies.
    importlib.reload(llm_client)
    monkeypatch.setattr(llm_client, "_client", None)


def _own_records(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == "app.llm_client"
    ]


def test_a_google_only_key_warns_at_import(monkeypatch, caplog, isolated_import):
    monkeypatch.setenv("GOOGLE_API_KEY", SYNTHETIC_KEY)

    with caplog.at_level(logging.WARNING, logger="app.llm_client"):
        importlib.reload(llm_client)

    assert llm_client._API_KEY == SYNTHETIC_KEY
    assert _own_records(caplog) == [WARNING]
    # The warning names the variables and carries nothing of the key.
    assert SYNTHETIC_KEY not in caplog.text


def test_a_gemini_key_does_not_warn(monkeypatch, caplog, isolated_import):
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-gemini-key-enh09")
    monkeypatch.setenv("GOOGLE_API_KEY", SYNTHETIC_KEY)

    with caplog.at_level(logging.WARNING, logger="app.llm_client"):
        importlib.reload(llm_client)

    assert llm_client._API_KEY == "synthetic-gemini-key-enh09"
    assert _own_records(caplog) == []


def test_no_key_does_not_warn(monkeypatch, caplog, isolated_import):
    with caplog.at_level(logging.WARNING, logger="app.llm_client"):
        importlib.reload(llm_client)

    assert llm_client._API_KEY is None
    assert _own_records(caplog) == []


def test_the_warning_does_not_repeat_per_resolution(
    monkeypatch, caplog, isolated_import
):
    monkeypatch.setenv("GOOGLE_API_KEY", SYNTHETIC_KEY)

    with caplog.at_level(logging.WARNING, logger="app.llm_client"):
        importlib.reload(llm_client)
        caplog.clear()

        llm_client._resolve_api_key()
        llm_client._resolve_api_key({"GOOGLE_API_KEY": SYNTHETIC_KEY})

    assert _own_records(caplog) == []
