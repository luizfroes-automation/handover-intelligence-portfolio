"""Live classification checks against the real provider.

The expected outcome of each case was committed before the first run and is not
adjusted to match what the model returned. A case the model gets consistently
wrong becomes an entry in ``KNOWN_MISSES`` and runs as ``xfail(strict=True)``:
the expectation stays the same, and the strict marker fails the run if the model
starts passing, forcing the entry to be removed instead of forgotten.

A provider failure is not a classification error: the round is inconclusive and
the test is skipped so the run can be repeated.
"""

import pytest

from app.errors import ProviderUnavailableError
from app.llm_client import generate_handover_package
from app.schema import HandoverPackage
from tests.fixtures.transcripts import CASES

pytestmark = pytest.mark.live

# Case id -> finding note. Empty until a run shows a consistent miss.
KNOWN_MISSES: dict[str, str] = {}

PARAMS = [
    (
        pytest.param(
            case,
            marks=pytest.mark.xfail(
                strict=True, raises=AssertionError, reason=KNOWN_MISSES[case.id]
            ),
        )
        if case.id in KNOWN_MISSES
        else pytest.param(case)
    )
    for case in CASES
]


@pytest.mark.parametrize("case", PARAMS, ids=[case.id for case in CASES])
def test_classifies_the_transcript(case):
    try:
        package = generate_handover_package(case.messages)
    except ProviderUnavailableError:
        pytest.skip("provider unavailable: round inconclusive, repeat the run")

    assert isinstance(package, HandoverPackage)
    if case.handoff_needed is not None:
        assert package.handoff_needed is case.handoff_needed
    if case.urgency:
        assert package.urgency.value in case.urgency
