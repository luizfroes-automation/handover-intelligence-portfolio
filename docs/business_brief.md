# Structured handover for automated support

*6 November 2026. Synthetic data.*

## Problem

When the bot cannot resolve a case, it transfers without what it already tried, with the
priority of a trivial case and into a generic queue. That decision exists only inside the bot.

## Solution

An API receives the transcript and returns the explicit decision: whether to transfer, why,
what was tried, urgency, queue and confidence. The package is validated against a contract —
validation guarantees the form, not the correctness.

## Architecture

`transcript → endpoint → model with structured output → validation → package`. Provider
failures become three stable responses — unavailable, invalid response, configuration — so
the caller knows whether to retry, escalate or open a ticket.

## Impact — hypothesis, not measured

The agent would start with context, and sensitive cases would not compete with simple ones.
The confidence indicator will be able to separate what goes straight through from what needs
review, once calibrated. Nothing was measured: time, cost and routing would need a real pilot.

## Limitations

1. **Self-declared, uncalibrated confidence.** On an ambiguous case it declared 95% certainty.
   Until that number is trustworthy, sensitive cases need human review. Record:
   `docs/tech-05-evidence.md`.
2. **Reproducibility.** Results depend on the model version. The system now ships with the
   version used in all the live runs, and any comparison must record version and date. See
   `app/llm_client.py`.
3. **Small base.** Six synthetic cases, one model, two runs: the five declared pass, which
   does not prove production. See `tests/fixtures/transcripts.py`.

**Measured:** decision and urgency matched on the five declared cases, in both runs; the
sixth is ambiguous by construction and has no expected result. Record:
`docs/tech-05-evidence.md`.

## Next steps

- Timeout, retry and a fallback for provider outages.
- Input size limits and handling of safety-filter blocks.
