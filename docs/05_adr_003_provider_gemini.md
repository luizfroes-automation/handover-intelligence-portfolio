# ADR-003 — Provider: Google Gemini

**Status:** Accepted
**Date:** 7 November 2026
**Supersedes:** the "Dependency on an external provider (Anthropic/OpenAI)" item of the
"Trade-off assumed (to declare in an interview)" section in ADR-001, and nothing else.

> **On the number.** ADR-002 is reserved for the fallback design, which is not yet written.
> This decision was implemented before that one was designed, but it takes the next free
> number, so the sequence reflects the reservation rather than the chronology.

## Context

ADR-001 (12 September 2026) decided on an LLM with structured output and accepted a
dependency on an external provider, listing Anthropic and OpenAI among the candidates. The
architecture decision held: structured output, a response schema, and validation against the
Pydantic model before a response counts as valid.

The provider itself was not part of that decision. The implementation chose Google Gemini in
the client work, and the choice was never recorded, so the document set implied something the
code did not implement. This ADR records what was adopted.

## Decision

Use Google Gemini through the official `google-genai` SDK.

- **Model:** `gemini-3.1-flash-lite`, the default in `app/llm_client.py`, verified working on
  6 November 2026. The name is configuration, not architecture: `GEMINI_MODEL` overrides it and
  a blank value counts as unset.
- **Credentials:** `GEMINI_API_KEY`, with `GOOGLE_API_KEY` as a fallback. When both hold a
  value, `GEMINI_API_KEY` wins, which is the opposite of the SDK's own default and is the
  behaviour the code documents.
- **Structured output:** a response schema on the request and Pydantic validation on the way
  back. The provider does not change that part of ADR-001.

## What this supersedes

It supersedes **one item of the "Trade-off assumed (to declare in an interview)" section in
ADR-001**:

> Dependency on an external provider (Anthropic/OpenAI)

That item named two candidates, but ADR-001 never chose between providers: it assumed an
external one and recorded the cost of that assumption. This ADR records which provider was
actually adopted, and replaces that item.

Everything else in ADR-001 stands: structured output over fixed rules and over a trained
classifier, validation before a response is accepted, and the trade-offs assumed.

ADR-001 is **not** rewritten. An ADR records the decision as it was taken, and editing it would
erase the fact that Gemini was not among the candidates named in September.

## What this does not claim

There was **no documented comparative evaluation** between Anthropic, OpenAI and Google. The
provider was chosen during implementation, and the reasons that are on record are practical:
a free tier that allowed the work without a budget, a direct API without an intermediary, and
native structured output, which is what ADR-001 requires.

This ADR records an **adoption**, not a selection study. Writing a retrospective comparison
now would invent evidence that never existed, and a claim like that does not survive one
question about how the comparison was made. The honest statement is the one above: the choice
was made while building, and the comparison was never written down.

## Consequences

- **One vendor.** A single provider, a single SDK, a single set of failure modes. A second
  provider would be a new ADR, not an edit to this one.
- **The model is perishable.** The name is configuration with a date, not a constant of the
  architecture. `gemini-3.8-flash` answered `503 UNAVAILABLE` when it was tried again, and the
  default moved to a model that answered on the day it was measured.
- **Error translation is coarse.** Every provider 4xx becomes a configuration error, so a rate
  limit arrives as broken configuration. The distinction belongs to the client, and it is not
  made yet.
- **No timeout or retry** is configured on the client. A provider that accepts the connection
  and then stalls holds the request open.
- **Reproducibility is name-deep.** Recording the model version and the date is part of
  reproducing a result; the same name does not guarantee the same behaviour over time.

## A note on terminology

This document says *handover*. The API mixes both words on purpose and that mix is contract:
the returned object is `HandoverPackage` and the boolean inside it is `handoff_needed`.
Renaming either is a breaking change and is not proposed here — prose says handover, identifiers
stay exactly as they are.

ADR-001 predates this note and still says *handoff* in places. It is left as written, for the
same reason it is not rewritten.
