# Problem Statement — AI Handover Intelligence (P1)

**Phase:** 1 — Discovery / Problem Framing
**Author (role):** Business Analyst / Consultant
**Status:** Draft for validation
**Date:** 12 September 2026

> Integrity note: this document describes a **generic, synthetic** scenario, built
> from patterns known in the customer-support industry with conversational AI.
> No real data, metric or operational detail from any employer is used here.

---

## 1. Context

Customer-support operations that use conversational AI (bots) for first-level
resolution often need to transfer ("hand over") the conversation to a human agent
when the bot cannot resolve the request on its own.

The pattern is common in regulated or high-volume sectors: telecom, financial
services, insurance, betting/gaming, e-commerce.

## 2. Observed problem

When the bot → human handover happens, recurring failures are observed in the
transfer process itself (not in the bot's ability to resolve the original problem):

- The human agent receives the conversation with no clear visibility of what the
  bot has already tried.
- The conversation is routed to a generic queue instead of the correct
  team/speciality.
- Sensitive cases (e.g. risk, safety, financial disputes) do not arrive flagged
  with a priority different from a trivial question.
- The customer has to re-explain the context from scratch to the human agent.

## 3. Who is affected

| Actor | Observed impact |
|---|---|
| Customer | Rework (re-explaining the problem), possible frustration |
| Human agent | Time spent rebuilding context before acting |
| Operation/business | Potential increase in average resolution time and repeat contacts |

## 4. Why it matters now

**[HYPOTHESIS]** Handover failures are a known friction point in support
operations with conversational AI at scale — market literature and CX benchmarks
point to badly executed handover as one of the main sources of dissatisfaction in
hybrid bot+human journeys.

**[NOT MEASURED IN THIS PROJECT]** This document presents no measured financial
or operational impact figures. Any impact estimate is presented separately in the
Business Brief (Phase 6), with an explicit Measured / Hypothesis / Estimate
classification.

## 5. Out of scope (explicitly)

This Problem Statement **does not cover**:

- Why the bot could not resolve the original request (that is a bot capability
  problem, not a handover problem)
- The quality of the human agent after the handover
- Any technical or technological solution (deliberately omitted at this phase)
- Data, metrics or real processes from any specific employer

## 6. Open questions for the Discovery phase

1. Is the problem in the **transfer of information** (lost context) or in
   **routing** (wrong queue) — or both, with different weights?
2. Is there any manual or human process today trying to mitigate this, or does it
   not exist?
3. What would the success criterion be if the problem were solved? That becomes
   the basis of the requirements in the next phase.

---

**Next phase:** Discovery Notes (02_discovery_notes.md) — answers to the
questions in section 6, and definition of requirements and constraints.
