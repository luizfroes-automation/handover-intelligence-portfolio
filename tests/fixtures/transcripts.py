"""Synthetic transcripts with the outcome each one is expected to produce.

The expected values are written before the first live run and never adjusted to
match what the model returned. A case the model gets consistently wrong becomes
``xfail(strict=True)`` in the live test, with the finding in its reason.

``handoff_needed`` may be ``None``: that marks a case where reasonable
classifications diverge. Nothing is asserted about the outcome; the observed
``confidence`` is recorded in the evidence instead, which is what the field is
for.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptCase:
    """One handover scenario, with the outcome declared up front."""

    id: str
    messages: list[dict]
    handoff_needed: bool | None
    urgency: tuple[str, ...]
    rationale: str


CASES = [
    TranscriptCase(
        id="simple_unresolved_request",
        messages=[
            {
                "role": "customer",
                "content": (
                    "Hi, I need to change the delivery address on order 73820."
                ),
            },
            {
                "role": "bot",
                "content": "I found the order, but I cannot change the address here.",
            },
            {
                "role": "customer",
                "content": "So how do I change it?",
            },
            {
                "role": "bot",
                "content": (
                    "I do not have that information. Please contact customer support."
                ),
            },
        ],
        handoff_needed=True,
        urgency=("low", "medium"),
        rationale=(
            "The bot cannot perform the request and gives no usable path forward, "
            "so a human has to finish it. Nothing here is time-critical."
        ),
    ),
    TranscriptCase(
        id="urgent_sensitive_case",
        messages=[
            {
                "role": "customer",
                "content": (
                    "There is a charge of 1,200 on my card that I never made. "
                    "I think someone has my account and I am really scared."
                ),
            },
            {
                "role": "bot",
                "content": "I can see the charge. I cannot freeze the account here.",
            },
            {
                "role": "customer",
                "content": (
                    "Please, I have children at home and I cannot lose this money."
                ),
            },
        ],
        handoff_needed=True,
        urgency=("high",),
        rationale=(
            "Suspected account takeover with an unrecognised high-value charge and "
            "visible distress: money is still exposed while the conversation runs."
        ),
    ),
    TranscriptCase(
        id="needs_history_lookup",
        messages=[
            {"role": "customer", "content": "I need the charge reversed."},
            {"role": "bot", "content": "Which charge would you like reversed?"},
            {
                "role": "customer",
                "content": (
                    "The one from the same order as last time, like we did before."
                ),
            },
            {
                "role": "bot",
                "content": (
                    "I do not have access to your previous conversations. "
                    "Could you give me the order number?"
                ),
            },
            {
                "role": "customer",
                "content": "I do not have it. Can you look it up from my account?",
            },
        ],
        handoff_needed=True,
        urgency=("low", "medium"),
        rationale=(
            "The customer is engaged and asks for a resolution the bot cannot "
            "reach: the reference is a previous order the bot has no access to. "
            "A human with account history can resolve it; guessing a category "
            "would send it nowhere."
        ),
    ),
    TranscriptCase(
        id="ambiguous_mixed_signal",
        messages=[
            {
                "role": "customer",
                "content": (
                    "I was charged twice for the same order. The app still shows "
                    "both charges."
                ),
            },
            {
                "role": "bot",
                "content": (
                    "I processed a refund for the duplicate. It can take a few "
                    "days to disappear from the app."
                ),
            },
            {
                "role": "customer",
                "content": (
                    "Okay. But if it does not disappear, will I have to call again?"
                ),
            },
        ],
        handoff_needed=None,
        urgency=(),
        rationale=(
            "Both readings are defensible: the bot acted and the remaining step is "
            "waiting, or the customer is asking for a commitment the bot cannot "
            "make. The outcome is not asserted; the confidence the model reports "
            "is recorded in the evidence."
        ),
    ),
    TranscriptCase(
        id="resolved_no_handoff",
        messages=[
            {"role": "customer", "content": "I cannot log in to my account."},
            {"role": "bot", "content": "I sent a password reset link to your email."},
            {"role": "customer", "content": "Got it, I am in. Thank you."},
            {"role": "bot", "content": "Glad it worked. Anything else?"},
            {"role": "customer", "content": "No, that is all."},
        ],
        handoff_needed=False,
        urgency=(),
        rationale=(
            "The bot solved the problem and the customer confirmed it. Handing "
            "this off would spend human time on a closed case."
        ),
    ),
    TranscriptCase(
        id="repeated_contact",
        messages=[
            {
                "role": "customer",
                "content": (
                    "This is the third time I am contacting you about the same "
                    "refund. Nobody has answered me."
                ),
            },
            {
                "role": "bot",
                "content": "I see previous contacts. I cannot process the refund.",
            },
            {
                "role": "customer",
                "content": "Then give me someone who can.",
            },
        ],
        handoff_needed=True,
        urgency=("medium", "high"),
        rationale=(
            "Repeat contact about an unresolved refund is a failure of the "
            "automated path; the case is already degraded and a human owns it now."
        ),
    ),
    TranscriptCase(
        id="customer_never_replied",
        messages=[
            {
                "role": "bot",
                "content": "Hello! How can I help you today?",
            },
            {
                "role": "bot",
                "content": "I can help with orders, payments and account access.",
            },
            {
                "role": "bot",
                "content": (
                    "If you are still there, tell me what you need and I will take "
                    "it from there."
                ),
            },
        ],
        handoff_needed=False,
        urgency=(),
        rationale=(
            "No message in the transcript comes from the customer: the bot spoke "
            "into an empty conversation. There is nothing to hand over, because no "
            "request was made and no work is waiting. This is the structural case, "
            "decided by the absence of a customer message; it is not the case where "
            "a customer disengages after being refused, which has customer messages "
            "and belongs elsewhere. No urgency band is declared: nothing is queued, "
            "so urgency has no consumer."
        ),
    ),
]
