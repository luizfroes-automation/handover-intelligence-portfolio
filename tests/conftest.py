"""Test-session configuration for the suite.

The live tests talk to the real provider. Without a key they are skipped, with
the reason visible in the output, instead of failing: the default suite must
stay green on a machine that has no credentials. The key is read from the
client's module snapshot, so it matches whatever the client itself resolved.
"""

import pytest

from app import llm_client

LIVE_SKIP_REASON = "live test needs GEMINI_API_KEY or GOOGLE_API_KEY"


def pytest_collection_modifyitems(config, items):
    if llm_client._API_KEY is not None:
        return
    skip_live = pytest.mark.skip(reason=LIVE_SKIP_REASON)
    for item in items:
        if item.get_closest_marker("live") is not None:
            item.add_marker(skip_live)
