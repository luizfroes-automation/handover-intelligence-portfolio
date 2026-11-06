"""Checks that every synthetic transcript is a valid request."""

import pytest

from app.schema import Message, TranscriptRequest
from tests.fixtures.transcripts import CASES


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_case_builds_a_valid_transcript_request(case):
    request = TranscriptRequest(
        messages=[Message(**message) for message in case.messages]
    )

    assert request.messages
