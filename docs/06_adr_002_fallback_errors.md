# ADR-002 — Fallback to human review when the provider does not assess the conversation

**Status:** Accepted
**Date:** 12 November 2026
**Relates to:** ADR-001 (structured output), ADR-003 (provider).

## Context

Every request that reaches the provider can end without an assessment. The client translates the provider failure into a domain error, the API answers with a status that describes it, and the conversation is left with no decision at all.

`HandoverPackage` cannot express that state honestly. All seven fields are products of the assessment: `handoff_needed` is the model's decision, `reason` must not be empty, `summary` describes what the bot attempted, `urgency` and `suggested_team` presume a classification, and `confidence` would be a number with no assessment behind it. Reusing the package with `handoff_needed: true` would turn an availability policy into a model decision and attach a fabricated confidence to it.

The API also does not hold the conversation: it never stores the transcript and never echoes it in an error body. The caller still has what it sent.

## Decision

The API keeps the current status and error code and adds one key to the body when the failure is a capacity or quota refusal.

### The trigger is the classification of the failure

The verifiable condition is that the request ended **without a usable assessment**. That condition alone does not say which failures should produce a reviewable case, because the API knows different amounts about each of them. In this delivery the trigger is deliberately narrow: a reviewable case is offered only when the API has identified a **capacity or quota refusal** — the provider's HTTP 429, which the client classifies and the API answers as `503` with `error: provider_rate_limited`.

The other provider failures keep their current response:

- **`provider_unavailable`** — timeout, transport failure, provider 5xx, and the neutral branch whose origin is undetermined. It may be transient, and the standard message is the one that tells the caller to retry. The neutral branch no longer promises a retry, but it also does not establish that the provider failed to process the call: a timeout can happen after the call was received. *Unknown* is not the same as *refused*, and only the second one is a classification this delivery can act on.
- **`invalid_llm_response`** — the call ran and produced something unusable. Retry is the documented remedy, and a refusal by the provider's safety filter is a different condition that needs a contract of its own.

A configuration failure (`500 llm_configuration_error`) and a rejected input (`413`, `422`) never produce a reviewable case: one is ours to fix, the other belongs to the caller.

### The answer

The status stays `503` and the code stays `provider_rate_limited`. The body gains one key:

```json
{
  "error": "provider_rate_limited",
  "detail": "The LLM provider is rate-limiting this service or its quota is exhausted.",
  "fallback": {
    "assessment": "unavailable",
    "error": "provider_rate_limited",
    "urgency": "high"
  }
}
```

- `assessment: "unavailable"` states what the service observed: this request received no usable assessment.
- `error` makes the object self-contained, so it survives being stored on its own.
- `urgency: "high"` is a **triage rule, not a measurement**: an unassessed case must not queue behind assessed ones until a person decides. Every value in the object is a single literal and the model is closed to extra fields, so neither this service nor a future change can put a different value there by accident.

`handoff_needed`, `confidence`, `summary` and `suggested_team` do not exist in this type. A consumer that validates the body against `HandoverPackage` fails loudly, and that is the point: the difference is carried by the type, not by a flag that can be mistaken for a model decision.

The API returns the case; it does not queue it. The caller chooses the review queue, keeps the conversation, and deduplicates with its own identifier. No idempotency key is issued, because a digest of the transcript would be a digest of user content, and a short conversation can be guessed.

## Compatibility

The published `503` was `ErrorResponse` — `error` and `detail`, both required, extra properties allowed. Adding `fallback` keeps both keys, so a consumer that reads them and ignores unknown keys is unaffected; a consumer that compares the exact body has to be updated.

The generated document changes more than the body. The `503` stops being one model and becomes a closed `anyOf`:

- the `provider_rate_limited` branch **requires** `fallback`;
- the `provider_unavailable` branch **rejects** it, in both documented bodies, because the branch refuses unknown properties.

A client generated from the new document therefore validates both directions: a rate-limit body without `fallback` is invalid, and a `provider_unavailable` body carrying `fallback` is invalid. Both statements are constraints of the **document**, not of the handler: they hold for a client that validates the response against the schema — which is what a generated client usually does, and what the contract tests do — and they do not apply to a client that only reads keys without validating. For that client the change is limited to the added key. The schema is stricter, not looser; the body is additive.

**Consumers checked:** there is no first-party client in either repository. The readers of the contract are the test suite, which pins the exact bodies, and the OpenAPI document itself. No integration outside these repositories is known, so the compatibility claim is limited to what was checked: additive in the JSON body, stricter in the schema, and no known consumer that requires the previous exact shape.

## Options rejected

| Option | Why not |
|---|---|
| Reuse `HandoverPackage` with `handoff_needed: true` and a fixed summary | It fabricates a decision and a confidence, and it hides where the package came from — the failure the type exists to prevent |
| Answer `200` or `202` with the fallback package | It hides the provider failure from monitoring, rewrites a contract that was just documented, and `202` would claim the case was accepted and queued — it was not |
| A separate endpoint or a request flag | It moves the decision to every caller and multiplies the API surface for a payload the caller can already store; the failure itself is not optional, so the answer should not be either |
| Offer the fallback for every provider failure | It would create human work for transient failures and duplicate a case that a retry later resolves; the classification that establishes a refusal exists only for the capacity refusal today |

## Trade-offs

- **Queue noise.** Every capacity refusal becomes a case a person may have to close. That is the declared cost of not losing the conversation; a rate limit can last for a quota window or for a day, and the API cannot tell which.
- **Duplicate work.** A caller that both retries and queues will duplicate the case. Deduplication belongs to the caller, which knows its retry policy and its conversation identifier.
- **A stricter document.** A generated client must implement the `anyOf`. The alternative — one permissive model — would accept a `fallback` on a `provider_unavailable` body, which is the contradiction this design removes.

## What this does not claim

- It does not claim the provider's quota is exhausted rather than a short window. The status does not distinguish them, the body would, and the body is not read.
- It does not claim that a retry would fail or succeed. No retry is configured, and nothing here authorises one.
- It does not cover the safety filter. A refusal is a condition of its own and needs its own decision.
- It does not make the case assessed. The payload contains no assessment, and the high urgency is policy, not a prediction.

## Amendment — content blocks (12 November 2026)

The provider can refuse to process a conversation, or to finish a response, because of its content. This is **not an HTTP failure**: the API answers `200` and the refusal lives in the body, in two independent fields. The decision above covered a capacity refusal; this amendment extends the same reasoning to a content refusal.

### Signals

| Step | Field | Values classified |
|---|---|---|
| Input block | `prompt_feedback.block_reason` | `SAFETY`, `BLOCKLIST`, `PROHIBITED_CONTENT` |
| Output block | first candidate's `finish_reason` | `SAFETY`, `BLOCKLIST`, `PROHIBITED_CONTENT`, `SPII`, `RECITATION` |

`OTHER`, the image reasons and unknown values stay outside the initial classification. `MODEL_ARMOR` and `JAILBREAK` are marked unavailable in the Gemini API by the pinned SDK. `RECITATION` is included as a content restriction the provider reported, not as a safety category: the effect on the service is the same — no usable assessment is available — and this branch neither advises nor performs a retry.

### Order of checks

Prompt block, then the first candidate's finish reason, then `parsed`. The SDK builds `parsed` from the first candidate's text and never consults the finish reason, so a block reported on that candidate must be read **before** the parsed package is trusted. Only the first candidate is inspected, because it is the one the SDK uses: a block on an alternative the service would never read must not veto a usable output.

`MAX_TOKENS` is not a block. A truncated response stays `502 invalid_llm_response`, because a larger budget is a different remedy and a different decision.

### Contract

`502` with `error: content_blocked`, no retry instruction, and a reviewable case:

```json
{
  "error": "content_blocked",
  "detail": "The LLM provider reported a content block. No usable assessment is available for this request.",
  "fallback": {
    "assessment": "unavailable",
    "error": "content_blocked",
    "urgency": "high"
  }
}
```

The `502` becomes a closed union: `invalid_llm_response` keeps its body and rejects `fallback`, and `content_blocked` requires the package, whose `error` literal is its own — a package pinning the capacity refusal is not valid here. The log distinguishes the step, `prompt_content_blocked` or `candidate_content_blocked`, together with the recognized reason; the provider's text and safety categories are never forwarded.

### Why it triggers human review

The same criterion as the capacity refusal: no usable assessment is available, and this branch neither advises nor performs a retry. A blocked conversation is sensitive by definition, and the caller decides whether to queue it.

### What this amendment does not claim

- It does not claim the conversation is unsafe. The provider reported a block; its categories are not forwarded and not interpreted.
- It does not classify unrecognized values or image reasons.
- It does not change how a truncated or malformed response is handled.
