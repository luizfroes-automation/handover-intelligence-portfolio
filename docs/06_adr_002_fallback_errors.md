# ADR-002 — Fallback to human review when the provider does not assess the conversation

**Status:** Accepted
**Date:** 12 November 2026
**Relates to:** ADR-001 (structured output), ADR-003 (provider).

## Context

Every request that reaches the provider can end without an assessment. The client translates the provider failure into a domain error, the API answers with a status that describes it, and the conversation is left with no decision at all.

`HandoverPackage` cannot express that state honestly. All seven fields are products of the assessment: `handoff_needed` is the model's decision, `reason` must not be empty, `summary` describes what the bot attempted, `urgency` and `suggested_team` presume a classification, and `confidence` would be a number written by code that never ran. Reusing the package with `handoff_needed: true` would turn an availability policy into a model decision and attach a fabricated confidence to it.

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

- `assessment: "unavailable"` states what is missing: no AI judgement exists for this conversation.
- `error` makes the object self-contained, so it survives being stored on its own.
- `urgency: "high"` is a **triage rule, not a measurement**: an unassessed case must not queue behind assessed ones until a person decides. Every value in the object is a single literal and the model is closed to extra fields, so neither this service nor a future change can put a different value there by accident.

`handoff_needed`, `confidence`, `summary` and `suggested_team` do not exist in this type. A consumer that validates the body against `HandoverPackage` fails loudly, and that is the point: the difference is carried by the type, not by a flag that can be mistaken for a model decision.

The API returns the case; it does not queue it. The caller chooses the review queue, keeps the conversation, and deduplicates with its own identifier. No idempotency key is issued, because a digest of the transcript would be a digest of user content, and a short conversation can be guessed.

## Compatibility

The published `503` was `ErrorResponse` — `error` and `detail`, both required, extra properties allowed. Adding `fallback` keeps both keys, so a consumer that reads them and ignores unknown keys is unaffected; a consumer that compares the exact body has to be updated.

The generated document changes more than the body. The `503` stops being one model and becomes a closed `anyOf`:

- the `provider_rate_limited` branch **requires** `fallback`;
- the `provider_unavailable` branch **rejects** it, in both documented bodies, because the branch refuses unknown properties.

A client generated from the new document therefore validates both directions: a rate-limit body without `fallback` is invalid, and a `provider_unavailable` body carrying `fallback` is invalid. The schema is stricter, not looser; the body is additive.

**Consumers checked:** there is no first-party client in either repository. The readers of the contract are the test suite, which pins the exact bodies, and the OpenAPI document itself. No integration outside these repositories is known, so the compatibility claim is limited to what was checked: additive in the JSON body, stricter in the schema, and no known consumer that requires the previous exact shape.

## Options rejected

| Option | Why not |
|---|---|
| Reuse `HandoverPackage` with `handoff_needed: true` and a fixed summary | It fabricates a decision and a confidence, and it hides where the package came from — the failure the type exists to prevent |
| Answer `200` or `202` with the fallback package | It hides the provider failure from monitoring, rewrites a contract that was just documented, and `202` would claim the case was accepted and queued — it was not |
| A separate endpoint or a request flag | It moves the decision to every caller and multiplies the API surface for a payload the caller can already store; the failure itself is not optional, so the answer should not be either |
| Offer the fallback for every provider failure | It would create human work for transient failures and duplicate a case that a retry later resolves; the classification that says "the provider refused to evaluate" exists only for the capacity refusal today |

## Trade-offs

- **Queue noise.** Every capacity refusal becomes a case a person may have to close. That is the declared cost of not losing the conversation; a rate limit can last for a quota window or for a day, and the API cannot tell which.
- **Duplicate work.** A caller that both retries and queues will duplicate the case. Deduplication belongs to the caller, which knows its retry policy and its conversation identifier.
- **A stricter document.** A generated client must implement the `anyOf`. The alternative — one permissive model — would accept a `fallback` on a `provider_unavailable` body, which is the contradiction this design removes.

## What this does not claim

- It does not claim the provider's quota is exhausted rather than a short window. The status does not distinguish them, the body would, and the body is not read.
- It does not claim that a retry would fail or succeed. No retry is configured, and nothing here authorises one.
- It does not cover the safety filter. A refusal is a condition of its own and needs its own decision.
- It does not make the case assessed. The payload contains no AI judgement, and the high urgency is policy, not a prediction.
