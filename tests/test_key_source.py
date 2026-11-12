"""The key fallback is announced once per execution of the module.

Each scenario loads a fresh copy of the module instead of reloading the one the
suite already imported: the probe has its own state, so `_API_KEY`, `_client`
and the logger of `app.llm_client` are never touched. The local `.env` is
disabled and both variables are cleared, so only the synthetic environment of
the test decides the outcome.
"""

import importlib.util
import itertools
import logging

import dotenv
import pytest

from app import llm_client as suite_client

SYNTHETIC_KEY = "synthetic-google-key-enh09"
WARNING = "GEMINI_API_KEY is not set; using GOOGLE_API_KEY"

_sequence = itertools.count()


@pytest.fixture
def isolated_module(monkeypatch):
    """Load a fresh copy of the client module, leaving the suite's import alone."""
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    def load():
        name = f"enh09_probe_{next(_sequence)}"
        spec = importlib.util.spec_from_file_location(name, suite_client.__file__)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return load


def _warnings(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.getMessage() == WARNING
    ]


def test_a_google_only_key_warns_at_import(monkeypatch, caplog, isolated_module):
    monkeypatch.setenv("GOOGLE_API_KEY", SYNTHETIC_KEY)

    with caplog.at_level(logging.WARNING):
        module = isolated_module()

    assert module._API_KEY == SYNTHETIC_KEY
    assert _warnings(caplog) == [WARNING]
    # The warning names the variables and carries nothing of the key.
    assert SYNTHETIC_KEY not in caplog.text


def test_a_gemini_key_does_not_warn(monkeypatch, caplog, isolated_module):
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-gemini-key-enh09")
    monkeypatch.setenv("GOOGLE_API_KEY", SYNTHETIC_KEY)

    with caplog.at_level(logging.WARNING):
        module = isolated_module()

    assert module._API_KEY == "synthetic-gemini-key-enh09"
    assert _warnings(caplog) == []


def test_no_key_does_not_warn(monkeypatch, caplog, isolated_module):
    with caplog.at_level(logging.WARNING):
        module = isolated_module()

    assert module._API_KEY is None
    assert _warnings(caplog) == []


def test_each_execution_of_the_module_emits_its_own_warning(
    monkeypatch, caplog, isolated_module
):
    """One per module execution: a reload or a new process can repeat it."""
    monkeypatch.setenv("GOOGLE_API_KEY", SYNTHETIC_KEY)

    with caplog.at_level(logging.WARNING):
        isolated_module()
        isolated_module()

    assert _warnings(caplog) == [WARNING, WARNING]


def test_the_warning_does_not_repeat_per_resolution(
    monkeypatch, caplog, isolated_module
):
    monkeypatch.setenv("GOOGLE_API_KEY", SYNTHETIC_KEY)

    with caplog.at_level(logging.WARNING):
        module = isolated_module()
        caplog.clear()

        module._resolve_api_key()
        module._resolve_api_key({"GOOGLE_API_KEY": SYNTHETIC_KEY})

    assert _warnings(caplog) == []


def test_the_probe_leaves_the_suite_module_untouched(monkeypatch, isolated_module):
    before_key = suite_client._API_KEY
    before_client = suite_client._client

    monkeypatch.setenv("GOOGLE_API_KEY", SYNTHETIC_KEY)
    isolated_module()

    assert suite_client._API_KEY == before_key
    assert suite_client._client is before_client
