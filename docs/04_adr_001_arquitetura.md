# ADR-001 — Solution architecture (AI Handover Intelligence)

**Status:** Decided
**Context:** Root Cause Analysis (03) identified that the handoff decision has to
become a **structured and explicit artefact**, not an implicit action.

## Options considered (brief, not a full elicitation)

| Option | Description | Why not |
|---|---|---|
| A. Fixed rules (if/else) | Classify the handoff by keywords or rules | Does not generalise to varied natural language; does not scale to new reasons without rewriting rules |
| B. Traditional ML classifier (e.g. scikit-learn) | Train a small supervised model | Would need a labelled dataset that does not exist — synthetic data is not enough to train well — and it is outside the project's time scope |
| **C. LLM with structured output** | Use an LLM to read the transcript and generate JSON validated against a schema | **Chosen** — generalises well to natural language, needs no training dataset, and the reasoning (reason/summary) is a natural by-product of an LLM, which resolves the explainability gap from the Root Cause directly |

## Decision

Use an LLM with **structured output / function calling**, not free-text parsing,
validated against a Pydantic schema before any response is considered valid.

## Trade-off assumed (to declare in an interview)

- Cost per API call, against a fixed rule, which is free
- Dependency on an external provider (Anthropic/OpenAI)
- Higher latency than a local rule

These trade-offs are acceptable for a portfolio and are the current market standard
for this kind of task: semantic classification over natural language.
