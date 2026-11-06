# Evidence of the `live` runs

**Date:** 6 November 2026.
**Command:** `python -m pytest -m live -v`, plus a per-case breakdown to record the observed
value and the `confidence` (pytest says pass/fail, not what the model answered).

**Effective model:** `gemini-3.1-flash-lite`, read from `GEMINI_MODEL` in the local `.env`.
The client default in `app/llm_client.py` is `gemini-3.8-flash`: anyone reproducing without a
`.env` runs a different model. That is the environment work, item 6.

**Keys:** the real ones from the local `.env`. No key appears in this document.

## The input changed after the observation — declared, with a reason

The order in the history is this, and it stays visible on purpose:

| Commit | What changes |
|---|---|
| `78b9b0c` | fixtures with the expected value declared **before** any `live` run |
| `7ca8967` | first `live` test; runs 1 and 2 with transcript A |
| `b35b76a` | the transcript of the ambiguous case **replaced** (reason below) |
| `6859cd6` | `xfail` removed (not because the expected value changed) |
| `2d14c6f` | the corrected case became `needs_history_lookup` and `ambiguous_mixed_signal` came in |

**Transcript A, the original** (`78b9b0c`):

```
customer: It still does not work.
bot:      Could you tell me what is not working?
customer: The thing I told you about before.
bot:      I do not have that context in this chat.
customer: Forget it.
```

It was not testing insufficient context: the customer **gives up**. There is no customer
question the bot cannot interpret — there is a customer ending the conversation, which is the
no-reply case scenario ("the customer went quiet"), outside the scope of this ticket. The
model's `handoff_needed=false` was a defensible reading, and the "finding" belonged to the
fixture. Replacing the input is the decision recorded here; the expected value (`true`,
low–medium) never changed.

## Final runs (7 and 8, with the set of 6 cases)

| Case | Expected | Observed (breakdown) | `confidence` | Run 7 (`pytest`) | Run 8 (`pytest`) |
|---|---|---|---|---|---|
| `simple_unresolved_request` | true / low–medium | true / medium | 0.95 | PASSED | PASSED |
| `urgent_sensitive_case` | true / high | true / high | 0.98 | PASSED | PASSED |
| `needs_history_lookup` | true / low–medium | true / medium | 0.95 | PASSED | PASSED |
| `ambiguous_mixed_signal` | **not asserted** | false / low | **0.95** | PASSED | PASSED |
| `resolved_no_handoff` | false / — | false / low | 1.00 | PASSED | PASSED |
| `repeated_contact` | true / medium–high | true / high | 0.98 | PASSED | PASSED |

`pytest -m live`: `7 passed, 32 deselected` in both runs (six cases plus the end-to-end
`live` test). Default suite: `32 passed, 7 deselected`.

**Calibration finding, not fixed here:** on the case designed to be ambiguous, the model
answered `handoff_needed=false` **with `confidence` 0.95** — it does not signal uncertainty
on a case where two readings are defensible. The finding is that `confidence` is
self-declared and not calibrated, and it goes to the business brief limitations
(**the business brief**). The idea of a threshold (for example, `confidence` below 0.8 on an
ambiguous case) is a **hypothesis tested on one case**, not an established contract: one case
and one model do not fix a calibration rule.

## History of the earlier runs

| Run | Set | Result |
|---|---|---|
| 1 and 2 | transcript A, 5 cases | `1 failed, 5 passed` — the ambiguous case returned `false` (reasons `customer_disengagement`, `customer_declined_assistance`, `customer_abandonment`) |
| 3 and 4 | corrected transcript, still 5 cases | every asserted field matched |
| 5 and 6 | `pytest`, 5 cases + endpoint | `6 passed` |

## Xfail: the path was exercised

With `KNOWN_MISSES` empty the path would have had no proof. Two mutations in production code
(fixed return with `handoff_needed=False`, no network call) and a temporary entry in
`KNOWN_MISSES`:

```
A) case fails + xfail(strict, raises=AssertionError) -> XFAIL,  exit 0
B) case passes + xfail(strict)                       -> [XPASS(strict)] -> FAILED, exit 1
```

Proof A shows the mechanism working; B shows why it is strict: if the model starts getting it
right, the run fails and the marking has to be removed. Both were reverted with the files
restored byte for byte.

## Divergences between runs

- **Asserted fields** (`handoff_needed`, `urgency` range): stable in every run.
- **Free fields** (`reason`, `flags`, `summary`): they vary and are not asserted. Examples:
  `order_modification_request` × `order_modification_inquiry`; `customer_resolved` ×
  `customer_issue_resolved`; `billing_dispute` × `unauthorized_transaction_fraud`.
- **Provider failures:** none. No skip for a missing key in the runs with a real key.

## How to reproduce

```powershell
python -m pytest -m live -v
```

The per-case breakdown was generated with a loop over `tests.fixtures.transcripts.CASES`
calling `generate_handover_package` and printing `handoff_needed`, `urgency.value`,
`confidence` and `reason`. Nothing beyond the model and the answers is recorded.
