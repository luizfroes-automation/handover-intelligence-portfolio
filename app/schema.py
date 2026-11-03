"""
Output schema for the AI Handover Intelligence system.

Every field here exists because it was traced back to a specific Discovery
or Root Cause Analysis finding — none of these are "fields that sound
useful". See docs/02_discovery_notes.md and docs/03_root_cause_analysis.md.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Role(str, Enum):
    """Speaker role in a transcript message."""

    BOT = "bot"
    CUSTOMER = "customer"


class Message(BaseModel):
    """A single turn in a bot/customer conversation."""

    role: Role
    content: str


class TranscriptRequest(BaseModel):
    """Request body for the handover endpoint."""

    messages: list[Message] = Field(min_length=1)


class Urgency(str, Enum):
    """Priority level of the handoff.

    Source: Discovery, Section 4 (success criteria) — sensitive cases need
    differentiated priority signaling.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Team(str, Enum):

    BILLING = "billing"
    TECHNICAL = "technical"
    ESCALATIONS = "escalations"


class HandoverPackage(BaseModel):
    """Structured handoff package generated from a bot+customer transcript."""

    model_config = ConfigDict(hide_input_in_errors=True)

    handoff_needed: bool = Field(
        description=(
            "Whether the conversation actually needs to be transferred to " "a human."
        )
    )

    reason: str = Field(
        min_length=1,
        description=(
            "Specific reason for the transfer (e.g. 'billing_dispute', "
            "'account_status_issue'). Source: Root Cause Finding 2 — the "
            "reason must be explicit, not implicit. "
            "This field must not be empty."
        ),
    )

    summary: str = Field(
        description=(
            "Summary of what the bot already attempted before the handoff. "
            "Source: Discovery Requirement R2."
        )
    )

    urgency: Urgency = Field(
        description="Priority of the case. Source: Discovery Requirement R3."
    )

    suggested_team: Team = Field(
        description=(
            "Team/queue suggested to receive the case. Source: Discovery "
            "Requirement R4. Note: the current process allows manual "
            "correction by the receiving agent — this field is a "
            "suggestion, not an irreversible final decision."
        )
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Model's confidence in the classification above (0 to 1). "
            "Exists because, by turning the decision into an explicit "
            "artifact (Root Cause), it also needs to carry how reliable it "
            "is — this avoids treating an uncertain decision as if it were "
            "certain."
        ),
    )

    flags: list[str] = Field(
        default_factory=list,
        description=(
            "Additional flags (e.g. 'repeat_contact', 'sensitive_case'). "
            "Source: Discovery Requirement R3."
        ),
    )
