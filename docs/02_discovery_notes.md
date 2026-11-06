# Discovery Notes — AI Handover Intelligence (P1)

**Phase:** 2 — Discovery
**Author (role):** Business Analyst / Consultant
**Method:** Structured interview ("Mom Test" technique — questions about observed
behaviour, not about the desired solution)
**Status:** Draft for validation

> Confidentiality note: the findings below were generalised from the author's real
> experience in support operations with conversational AI. No system, product,
> business vertical or specific data from any employer is cited. The patterns
> described are recognisable across the conversational CX industry as a whole, not
> exclusive to one case.

---

## 1. As-Is process (summary)

1. The customer interacts with the conversational bot.
2. The bot identifies that it cannot resolve the request and triggers the handover.
3. Automatic routing sends the conversation to a queue or team.
4. Cases flagged as sensitive (e.g. risk, safety, compliance) receive queue
   priority.
5. The human agent receives the conversation and takes over.
6. **Existing correction mechanism:** the agent has the autonomy to reallocate the
   conversation to another queue if they notice a routing error.

**[FACT — confirmed by SME]** Incorrect routing, when it happens, is not
irreversible — a manual correction exists in the current process.

## 2. Central finding (root cause candidate)

**[FACT — confirmed by SME]** The human agent receives the transferred
conversation with no visibility of **the reasoning behind the handover decision**
— that is, it is not clear to the agent:

- Which specific signal (e.g. a customer comment, an account status, a content gap
  in the knowledge base) motivated the transfer.
- What exactly the bot had already tried before giving up.

This reframes the problem: **it is not just "lost context" in generic terms — it
is specifically an explainability gap in the AI decision at the moment of
transfer.**

**[INTERPRETATION]** The distinction matters because it changes the technical
requirement: the system does not only need to "summarise the conversation" — it
needs to **expose the reasoning of the decision** in a structured and auditable
way.

## 3. Mitigations that exist today

**[FACT — confirmed by SME]** The process is already mostly automated (automatic
routing, automatic prioritisation of sensitive cases). There is no prior manual
triage — human intervention happens **after** the handover, as a one-off
correction (queue change), not as prevention.

## 4. Success criterion (defined by the SME)

If the problem were considered solved, the handover package delivered to the agent
should contain, at the same time:

1. A summary of what the bot had already tried.
2. Routing to the correct queue or team.
3. Priority signalling for sensitive cases.
4. **A suggested response draft**, to speed up the agent's first action.

**[NEW REQUIREMENT IDENTIFIED IN DISCOVERY]** Item 4 (response draft) was not in
the original scope of the brief (Section 3 of P1) — it is a Discovery finding that
increases the value scope of the solution. The decision on including it in CORE or
ENHANCEMENT is taken in the Solution Design phase (time versus value trade-off).

## 5. Derived requirements (still with no defined solution)

| # | Requirement | Origin |
|---|---|---|
| R1 | The system must capture and expose the specific reason for the handover, not only the category | Finding 2 |
| R2 | The system must indicate what had already been tried before the transfer | Finding 2 |
| R3 | The system must signal priority for sensitive cases | Success criterion |
| R4 | The system must indicate the suggested team or queue | Success criterion |
| R5 (ENHANCEMENT candidate) | The system may suggest a response draft | Success criterion |
| R6 | The system's decision must be auditable — traceable, not a black box | Finding 2 (explainability) |

## 6. Out of scope (restated)

- Improving the bot's ability to resolve the original request.
- Any change to the manual post-handover correction process (it works).
- Real data from any specific operation.

---

**Next phase:** Root Cause Analysis (03_root_cause_analysis.md) — structuring why
the explainability gap (Finding 2) exists, before moving to Options/Solution
Design.
