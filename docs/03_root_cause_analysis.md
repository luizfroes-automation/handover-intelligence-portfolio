# Root Cause Analysis — AI Handover Intelligence (P1)

**Phase:** 3 — Root Cause Analysis
**Author (role):** Business Analyst / Consultant
**Method:** Issue Tree (MECE) — ref. Conn & McLean, *Bulletproof Problem Solving*
**Status:** Draft for validation

> Limitation note: this project has no real production data for statistical
> validation of the hypotheses below. The assessment is based on domain expert
> (SME) accounts and logical reasoning. Each hypothesis is marked as **Assessed
> hypothesis**, not as **Measured**. In a real consultancy with access to
> production data, this phase would include quantitative validation (e.g. log
> analysis, correlation rate).

---

## 1. Central question of the issue tree

> Why does the human agent not receive visibility of the specific reason for the
> handover decision? (Discovery Finding 2)

## 2. Hypotheses (MECE)

| # | Hypothesis | Category (Fishbone) |
|---|---|---|
| A | The technology never captures the reason for the decision — it is lost at the source, because the bot decides but does not record why | Technology |
| B | The technology captures the reason, but does not pass that data on to the agent at the moment of the handover | Process / Technology |
| C | The organisational process does not require the reason to be communicated to the agent as a handover quality criterion | Process |
| D | The reason is passed on, but in a format the agent cannot read quickly under time pressure | People / UX |

## 3. Assessment of each hypothesis

### Hypothesis A — the reason is never captured
**[ASSESSED HYPOTHESIS — probably false, or partly false]**
According to the SME account, the system already uses clear signals to decide the
handover (e.g. a specific customer comment, an account status, a content gap).
That indicates the decision signal **exists inside the system** — it is not
random. It is therefore unlikely that the reason simply does not exist.

### Hypothesis B — the reason exists, but is not passed on
**[ASSESSED HYPOTHESIS — most likely, main root cause candidate]**
The SME account confirms that the agent "never knew what the AI looked at" — that
is, the signal exists in the system's decision but is lost between the decision
and the delivery to the agent. This is consistent with a common pattern in
classification and routing architectures: the model produces a binary decision or
a category (e.g. "transfer: yes/no", "queue: X") and discards the intermediate
reasoning, because **the handover payload was never designed to carry it.**

### Hypothesis C — the process does not require the reason to be communicated
**[ASSESSED HYPOTHESIS — true, but a consequence of B, not an independent cause]**
It is reasonable that, if the technology was never designed to carry the reason
(Hypothesis B), the organisational process also never formalised that requirement
— there was no way to require something the system does not produce. I treat this
as a **symptom arising from B**, not as a separate root cause.

### Hypothesis D — the reason is passed on but ignored because of its format
**[ASSESSED HYPOTHESIS — not supported by the available account]**
There is no evidence, in the SME account, that the reason reaches the agent in any
format, even a bad one. The account indicates absence of the information, not a
badly formatted presence. The hypothesis is discarded for lack of evidence — not
because it is logically impossible.

## 4. Identified root cause

**[ASSESSED HYPOTHESIS — most likely root cause, subject to validation with real data in a production reproduction]**

> The root cause is structural and architectural: **the bot's decision moment —
> why transfer, to where, with what priority — does not produce a structured
> output artefact that carries the reasoning**; it produces only an action
> (transfer) and, at most, a simple category. The reasoning is lost because it was
> never designed to be an explicit product of the decision.

This reframes the problem in an actionable way: the solution does not need to "add
AI" in the generic sense — it needs to **turn the handover decision, which is
implicit today, into a structured and explicit artefact.**

## 5. Why this is not (only) a people or process problem

**[INTERPRETATION]** One could argue that "the agent should ask more" or that
"there should be a handover checklist". That would treat the symptom (Hypothesis
C), not the cause (Hypothesis B). As long as the system does not produce the
reason in a structured way, no process or people training solves it — there is no
data to communicate.

This is an important distinction for the Business Case: **it rules out process and
training solutions as the main answer**, without yet committing to a specific
technical solution, which comes in the next phase, Options.

---

**Next phase:** Solution architecture (04_adr_001_arquitetura.md) — compare more than
one solution alternative, not all of them with AI, and record the choice and the
trade-offs it assumes.
