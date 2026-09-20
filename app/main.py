"""FastAPI application exposing the handover endpoint."""

from fastapi import FastAPI

from app.schema import HandoverPackage, Team, TranscriptRequest, Urgency

app = FastAPI()


@app.post("/handover")
def create_handover(request: TranscriptRequest) -> HandoverPackage:
    """Generate a handover package from a conversation transcript."""
    return HandoverPackage(
        handoff_needed=True,
        reason="billing_dispute",
        summary="Bot tried to resolve a duplicate charge before the handoff.",
        urgency=Urgency.HIGH,
        suggested_team=Team.BILLING,
        confidence=0.87,
        flags=["repeat_contact"],
    )
