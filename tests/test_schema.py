import pytest
from pydantic import ValidationError

from app.schema import HandoverPackage, Urgency


def test_handover_package_created_with_valid_fields():
    package = HandoverPackage(
        handoff_needed=True,
        reason="billing_dispute",
        summary="Bot tried to refund a duplicate charge, customer asked for a human.",
        urgency=Urgency.HIGH,
        suggested_team="billing",
        confidence=0.87,
        flags=["repeat_contact"],
    )

    assert isinstance(package, HandoverPackage)


def test_creation_fails_with_urgency_value_outside_enum():
    with pytest.raises(ValidationError):
        HandoverPackage(
            handoff_needed=True,
            reason="billing_dispute",
            summary="Bot tried to refund a duplicate charge, customer asked for a human.",
            urgency="banana",
            suggested_team="billing",
            confidence=0.87,
            flags=["repeat_contact"],
        )


def test_creation_fails_when_confidence_exceeds_maximum():
    with pytest.raises(ValidationError):
        HandoverPackage(
            handoff_needed=True,
            reason="billing_dispute",
            summary="Bot tried to refund a duplicate charge, customer asked for a human.",
            urgency=Urgency.HIGH,
            suggested_team="billing",
            confidence=1.5,
            flags=["repeat_contact"],
        )


def test_creation_fails_when_required_field_is_missing():
    with pytest.raises(ValidationError):
        HandoverPackage(
            reason="billing_dispute",
            summary="Bot tried to refund a duplicate charge, customer asked for a human.",
            urgency=Urgency.HIGH,
            suggested_team="billing",
            confidence=0.87,
            flags=["repeat_contact"],
        )

def test_creation_fails_when_reason_field_is_empty_string():
    with pytest.raises(ValidationError):
        HandoverPackage(
            handoff_needed=True,
            reason="",
            summary="Bot tried to refund a duplicate charge, customer asked for a human.",
            urgency=Urgency.HIGH,
            suggested_team="billing",
            confidence=0.87,
            flags=["repeat_contact"],
        )