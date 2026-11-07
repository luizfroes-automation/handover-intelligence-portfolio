# Default model evidence

**Date:** 6 November 2026.
**Environment:** Windows, PowerShell 5.1, Python 3.14.7, `.venv` at the project root.
**Keys:** the real key from the local `.env`. No key appears in this document.

## The condition of the proof

`load_dotenv()` does not overwrite a variable that already exists, and the local `.env`
defined `GEMINI_MODEL`. To exercise the code default, both had to go: the variable was
removed from the session (`Remove-Item Env:GEMINI_MODEL`) and the line was commented out in
a copy of `.env`. The file was restored byte for byte afterwards â€” `SHA256` before and after:
`AC8FE96Câ€¦B42493DB`.

```
$ .\.venv\Scripts\python.exe -c "import os; print('GEMINI_MODEL present:', 'GEMINI_MODEL' in os.environ)"
GEMINI_MODEL present: False

$ .\.venv\Scripts\python.exe -c "from app import llm_client as m; print(m._MODEL)"
gemini-3.8-flash
```

## RED â€” the old default does not serve

The first attempt was the live test. It came back **inconclusive**, not red:

```
$ pytest -m live -k simple_unresolved_request -q
1 skipped, 38 deselected, 3 warnings in 133.96s (0:02:13)
```

Skipped because the case raised `ProviderUnavailableError`, and the suite's own policy is
that a provider failure makes the round inconclusive and it is repeated. Calling the client
directly showed what the provider actually answered:

```
model: gemini-3.8-flash
RAISED ProviderUnavailableError -> LLM provider failed to serve the request
cause: ServerError 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is
currently experiencing high demand. Spikes in demand are usually temporary. Please try again
later.', 'status': 'UNAVAILABLE'}}
elapsed 43.3s
```

**The finding matters more than the failure:** `503 UNAVAILABLE` is not `404 NOT_FOUND`. The
model exists and is overloaded, which is a different fault from the one the ticket assumed
("model was discontinued"). The error-handling work recorded a real `404 NOT_FOUND` for a model that does not
exist, so the two are distinguishable in this system. Twice, 43 s and 134 s, with no
timeout configured (the planned timeout and retry): the old default is not serviceable, but it is not missing.

## The candidate

```
$ GEMINI_MODEL=gemini-3.1-flash-lite python -c "... generate_handover_package(CASES[0]) ..."
model: gemini-3.1-flash-lite
OK handoff_needed=True urgency=medium confidence=1.0
elapsed 1.0s
```

## GREEN â€” the new default, with nothing else set

Same condition as the RED: no `GEMINI_MODEL` in the session, none in `.env`.

```
$ .\.venv\Scripts\python.exe -c "from app import llm_client as m; print('model used:', m._MODEL)"
model used: gemini-3.1-flash-lite

$ pytest -m live -k simple_unresolved_request -q
1 passed, 41 deselected, 3 warnings in 1.34s
```

**Recorded on 6 November 2026.** A default model is perishable: this date is the only thing
that says how old the choice is when a future call starts failing.

## The design question, answered

`_resolve_api_key` treats a blank value as absent. The model now follows the same rule:

```python
def _resolve_model(environ: Mapping[str, str] | None = None) -> str:
    source = os.environ if environ is None else environ
    return (source.get("GEMINI_MODEL") or "").strip() or DEFAULT_MODEL
```

Why: with `os.getenv("GEMINI_MODEL", default)`, an empty variable returns `""` â€” the default
only applies when the variable does not exist. That sends an empty model name to the
provider, and the provider answers 4xx, which this system correctly classifies as *our*
configuration error (`LLMConfigurationError â†’ 500`). So a blank variable produces a 500 that
blames configuration for something a default would have fixed, and it breaks the rule the key
already follows. One rule, both variables.

Consequence, and it is the point: `$env:GEMINI_MODEL=""` now exercises the default. That was
a trap for the proof, and it is a defect for the operator.

### Measured, because PowerShell hides the case

`$env:GEMINI_MODEL = ""` in PowerShell **deletes** the variable, so the child process sees it
absent â€” the two cases collapse and the operator cannot reproduce the defect from the shell.
The empty value has to be handed over through the environment mapping:

```
--- empty string ---
GEMINI_MODEL value: ''
resolved model: gemini-3.1-flash-lite

--- unset ---
GEMINI_MODEL value: 'model-from-dotenv'
resolved model: model-from-dotenv
```

For this experiment the `.env` in use declared `GEMINI_MODEL=model-from-dotenv`, so the two
outputs cannot be explained by the file: an empty variable resolves to the **code default**,
and only its absence lets `.env` decide.

**Corner case this exposes, recorded rather than hidden:** `load_dotenv()` does not overwrite a
variable that exists, so an empty `GEMINI_MODEL` in the process environment also blocks the
value in `.env` â€” the result is the code default, not the `.env` value. That is the price of
"blank is absent" meeting "dotenv never overrides", and it is the least surprising of the
options: the alternative is an empty model name and a 500 blaming configuration.

## Unit tests

```
$ pytest tests/test_llm_client.py -q -k resolve_model
3 failed          (before: no _resolve_model, no DEFAULT_MODEL)
4 passed          (after)

$ pytest -q
36 passed, 7 deselected, 3 warnings         (32 before, +4)
```

The four cover: absent variable â†’ default, empty string â†’ default, whitespace only â†’ default,
declared value â†’ itself.

## What this ticket does not prove

- **Nothing about the other models.** `gemini-3.1-flash-lite` answered on this date; it can be
  retired next month.
- **Nothing about calibration or accuracy.** The single call proves the default is serviceable,
  not that the classification is right.
- **Nothing about the README.** It still documents `python -m` as the way to run things: the README update.
