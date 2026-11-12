# AI Handover Intelligence

An API that reads a customer-service conversation between a bot and a customer and returns a structured **handover package**: whether the conversation needs a human agent, why, how urgent it is, which team should take it, and what the bot already tried.

> All data in this repository is synthetic. No real customer data or operational data from any company is used.

## The problem

When a support bot cannot resolve a request, it transfers the conversation to a human agent. That handover often fails in predictable ways:

- The agent receives the conversation without knowing what the bot already tried.
- The conversation lands in a generic queue instead of the right team.
- Sensitive cases arrive with the same priority as trivial ones.
- The customer has to explain everything again.

The root cause addressed here is that the handover decision is implicit: the bot transfers the conversation, but the reasoning behind that decision is not delivered to the agent. This project turns that decision into an explicit, structured, validated artefact.

The full analysis is in [`docs/`](docs/): problem statement, discovery notes, root cause analysis and the architecture decision record.

## How it works

```
transcript ──► POST /handover ──► LLM (structured output) ──► schema validation ──► HandoverPackage
```

The transcript is sent to Google Gemini with a response schema, so the model returns structured data instead of free text. The result is validated against a Pydantic model before it is returned.

Example response:

```json
{
  "handoff_needed": true,
  "reason": "billing_dispute",
  "summary": "Customer disputes a duplicate charge; the bot could not resolve it after two attempts.",
  "urgency": "high",
  "suggested_team": "billing",
  "confidence": 0.87,
  "flags": ["repeat_contact"]
}
```

`urgency` is advice for the human agent, not a routing decision of its own. **When `handoff_needed` is `false`, consumers must ignore `urgency`**: nothing is queued and no one is paged, so a priority on a conversation that stays with the bot has no consumer.

Why an LLM with structured output, and not keyword rules or a trained classifier, is explained in [`docs/04_adr_001_arquitetura.md`](docs/04_adr_001_arquitetura.md).

## Requirements

- Python 3.14 (tested on 3.14.7)
- A Gemini API key

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

On macOS or Linux, create the environment with `python -m venv .venv`, activate it with `source .venv/bin/activate`, and install the same file.

`requirements.txt` holds the runtime dependencies only. `requirements-dev.txt` adds Black, Ruff and pytest and includes the runtime file with `-r requirements.txt`, so one install is enough for development. The runtime set is installed from scratch the same way, using `-r requirements.txt`.

## Configuration

```powershell
Copy-Item .env.example .env
```

On macOS or Linux the equivalent is `cp .env.example .env`. Then fill in the values:

| Variable | Required | Description |
| --- | --- | --- |
| `GEMINI_API_KEY` | one of the two | Gemini API key. Preferred. |
| `GOOGLE_API_KEY` | one of the two | Used only when `GEMINI_API_KEY` is blank or unset. |
| `GEMINI_MODEL` | no | Model name. Defaults to `gemini-3.1-flash-lite`, verified working on 6 November 2026. |

Two rules apply to both the key and the model:

- **Key precedence.** When both keys hold a value, `GEMINI_API_KEY` wins. That is the opposite of the SDK's own default, and it is deliberate: the variable named after the provider the code uses is the one that decides.
- **Blank counts as unset.** An empty or whitespace-only value falls back — to the other key, or to the default model — instead of being sent to the provider as an empty string. This is why a blank variable does not produce a configuration error.

`.env` is git-ignored. `.env.example` is versioned and carries placeholders only.

### A PowerShell trap worth knowing

In PowerShell, `$env:GEMINI_API_KEY = ""` does not create an empty variable: it **deletes** it, and `.env` then puts the real key back on the next import. To simulate a missing key from the shell, set a single space, which the client strips and treats as absent:

```powershell
$env:GEMINI_API_KEY = " "
$env:GOOGLE_API_KEY = " "
```

## Running the API

```powershell
uvicorn app.main:app --reload
```

The interactive documentation is at `http://127.0.0.1:8000/docs`. If the `uvicorn` script is not on `PATH`, `python -m uvicorn app.main:app --reload` is the equivalent.

Example request:

```bash
curl -X POST http://127.0.0.1:8000/handover \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "bot", "content": "Hello! How can I help you today?"},
      {"role": "customer", "content": "I was charged twice for my last order."}
    ]
  }'
```

## Tests

```powershell
pytest
```

That is the default suite: deterministic, offline, and it never calls the provider. `pyproject.toml` restricts collection to `tests/` and deselects the `live` marker by default, so the six live cases and the live endpoint test do not run.

```powershell
pytest -m live -v
```

That runs only the tests that call the real provider. They need a key, they cost API calls, and they take seconds to minutes depending on the provider. A case that fails because the provider was unavailable is inconclusive, not a classification error: repeat the run.

When no key is configured, live tests are **skipped with the reason visible** instead of failing, so the default suite stays green on a machine without credentials. That also means a green run (exit code 0) does not prove the integration was exercised. Three things are easy to conflate: a **skipped** result means the test never ran; a `FAILED` or `XFAIL` result means the test executed, but the failure may have happened before the HTTP call — a missing key, a malformed request — so neither proves the provider was reached; and a `PASSED` live case is the one outcome that shows the call reached the provider and that its response validated against the schema. What a pass proves beyond that depends on the test: the end-to-end case checks that `POST /handover` answers 200 with a valid package, while each of the six classification cases also asserts `handoff_needed` and, where the case declares it, the urgency band. A pass covers the declared outcome of those cases — it does not show that every classification is right, and it does not calibrate the model. Only the `live` marker exercises the real API.

A single test:

```powershell
pytest tests/test_api.py::test_name -v
```

Lint and formatting:

```powershell
ruff check .
black --check .
```

## Continuous integration

Every pull request targeting `main` and every push to `main` runs `.github/workflows/ci.yml` on a GitHub-hosted runner with Python 3.14. It installs `requirements-dev.txt` and runs three independent jobs:

| Job | Command | What it proves |
| --- | --- | --- |
| `pytest` | `python -m pytest` | The deterministic suite passes |
| `ruff` | `python -m ruff check .` | The lint rules pass |
| `black` | `python -m black --check .` | The code is already formatted |

The local equivalents are the same three commands: `pytest`, `ruff check .` and `black --check .`.

Three different facts are easy to merge into one overstated guarantee, so the workflow is explicit about each:

- **No credentials are supplied.** The workflow has no `env:` block and references no secret; a clean checkout has no `.env`. `app/llm_client.py` calls `load_dotenv()` at import, which finds no file and therefore resolves no key.
- **The `live` marker is deselected** by `pyproject.toml`, exactly as in the local default suite, so the eight provider tests do not run.
- **Network access is not blocked.** `contents: read` limits the GitHub token, not the runner's egress. A test or import that attempted an external call would still attempt it. The protection is selection plus the absence of a key, not a sandbox — an audit run that fails on outbound connections was used to check this ticket, but it is not part of the workflow.

## Error handling

Provider failures never reach the client as raw SDK exceptions. The LLM client translates them into domain exceptions, and the API maps each one to a stable response:

| Condition | HTTP | `error` |
| --- | --- | --- |
| Provider unreachable, timed out or returned 5xx | 503 | `provider_unavailable` |
| Provider refused the request for capacity or an exhausted quota (HTTP 429) | 503 | `provider_rate_limited` |
| Provider returned no structured output, or output that fails validation | 502 | `invalid_llm_response` |
| Provider reported a content block on the prompt or the candidate | 502 | `content_blocked` |
| Provider rejected the request (4xx other than 429, e.g. unknown model or invalid key), or the HTTP client raised a proxy error (e.g. a refused CONNECT tunnel) | 500 | `llm_configuration_error` |
| Any other unexpected error | 500 | `internal_error` |
| Empty transcript | 422 | `detail[]` with `type`, `loc`, `msg` |

Error responses have the form `{"error": "...", "detail": "..."}`. Messages are fixed, but can vary with the condition that produced the response even when the error code is the same. A 422 is the exception: it returns `{"detail": [...]}`, one entry per rejected rule with its `type`, `loc` and `msg` and nothing else. The rejected value is not echoed, so a client that sends a 2,001-character message learns the limit it broke, not a copy of its own text. The provider's original error is kept in the server log as the exception cause and is never included in the response body.

The 503 answer is not one condition. `provider_unavailable` covers a transport failure or a provider 5xx; `provider_rate_limited` covers the provider refusing the request for capacity or an exhausted quota, which arrives as an HTTP 429 from the provider. The status is 503 rather than 429 because the limit belongs to the dependency that serves this service: a public 429 would tell the caller of `/handover` that it sent too many requests, and the evidence does not attribute the consumption to the caller. The response separates the two 503 conditions without claiming that repeating the call would succeed: no retry is configured and the provider's `Retry-After` is not forwarded. The provider's own body is not forwarded either. The log records `provider_throttled_or_quota_exhausted` for this branch, and `provider_auth_rejected` (401) or `provider_permission_denied` (403) for the configuration branch. Whether a rejection came from an expired key, a disabled API or a project restriction is a hypothesis for the investigation, not part of the identifier.

Only the capacity refusal carries a reviewable case in the 503 answer. Its body adds `fallback`: `{"assessment": "unavailable", "error": "provider_rate_limited", "urgency": "high"}`. The object states that the request received no usable assessment, why, and the triage rule; it has no `handoff_needed`, `confidence`, `summary` or `suggested_team`, so a body that validated against `HandoverPackage` fails loudly instead of being mistaken for a model decision. The API returns the case and does not queue it: the caller chooses the review queue, keeps the conversation and deduplicates with its own identifier. The two `provider_unavailable` bodies keep exactly `error` and `detail`, and the generated `503` describes a closed union of the two branches: a client that validates the response treats a `fallback` on a `provider_unavailable` body as invalid. The decision and its compatibility impact are in [`docs/06_adr_002_fallback_errors.md`](docs/06_adr_002_fallback_errors.md).

A content block is the other refusal. The provider answers `200` and reports it in the body, either on the prompt (`prompt_feedback.block_reason`) or on the first candidate (`finish_reason`), so the client reads both **before** it trusts the parsed package — the SDK parses the candidate's text even when the candidate was blocked. The response is `502 content_blocked` with a reviewable case whose `error` is `content_blocked`, and no retry instruction: the service neither advises nor performs a retry on this branch. `MAX_TOKENS` is not a block and keeps `invalid_llm_response`. The log distinguishes `prompt_content_blocked` from `candidate_content_blocked` and records the recognized reason; the provider's text and safety categories are not forwarded, and only the first candidate is read, because it is the one the SDK uses. The classified values are listed in the ADR amendment.

Conversation content never reaches a log record either. The server logs the exception type, the raising frame and — for a validation failure — the failed rule; it does not log exception messages or exception chains with `exc_info`, because a message raised while serving a request can quote that request. A validation line reports at most five rules, followed by how many were omitted. That limit is a number of entries, not a character budget: the next rule is dropped, not shortened, and each forwarded text is either fixed in code or composed by Pydantic from the schema.

The guarantee has two documented boundaries. `loc` names schema fields and list indices, which holds because no model forbids extra fields: an unknown key sent by the client is ignored, not reported. A model switched to `extra="forbid"` would put that key into `loc`, so `tests/test_error_sanitization.py` fails if it happens. `msg` is forwarded only for messages Pydantic composes from the schema; a message raised by a field validator is replaced by a fixed text, and a custom Pydantic error type would bypass that rule unless it is deliberately allowlisted in `app/sanitization.py`. No validator in the project raises a custom type today — the only one raises `ValueError`.

The API currently maps `httpx.ProxyError` to `500 llm_configuration_error`. A proxy can refuse a `CONNECT` tunnel because it cannot reach the destination. The exception alone does not establish the underlying cause or whether a later attempt would succeed.

The provider call uses a transport timeout of 20,000 ms (`DEFAULT_TIMEOUT_MS` in `app/llm_client.py`). The SDK receives it in milliseconds, converts it to seconds and hands it to HTTPX, where a single value covers four phases: connecting, reading, writing and waiting for a pool connection. The test demonstrates the read phase: it bounds how long the service waits for the next block of data, so a response that keeps sending data can take longer than 20 s in total. It bounds how long the service waits for progress, not how long the provider works — a call may still complete remotely after the client gives up — and it does not cancel anything on the provider side. The value is a provisional operational hypothesis, not a measured p99. Retry is not configured: a failed call is not repeated, including a rate-limit refusal from the provider. Check it with `python -m pytest tests/test_timeout.py`.

## Limitations

1. **Self-declared, uncalibrated confidence.** On a case designed to be ambiguous, the system declared 95% certainty. The number is the model's own claim, and it has not been calibrated against outcomes. Until it is, sensitive cases need human review. Record: [`docs/tech-05-evidence.md`](docs/tech-05-evidence.md).
2. **Reproducibility.** Results depend on the model version. The code ships with `gemini-3.1-flash-lite`, verified on 6 November 2026 and used in all the live runs, and any comparison must record version and date. See [`app/llm_client.py`](app/llm_client.py).
3. **Small base.** Six synthetic cases, one model, two runs: the five declared ones pass, which does not prove production. See [`tests/fixtures/transcripts.py`](tests/fixtures/transcripts.py).

## Project structure

```
app/
  main.py         FastAPI app, endpoint and error handlers
  llm_client.py   Gemini integration, model and key resolution, error translation
  errors.py       Domain exceptions
  schema.py       Request and response models
  diagnostics.py  Internal identifiers derived from an exception chain
  sanitization.py Diagnostics for rejected requests, without their content
tests/            Unit tests and fixtures
docs/             Problem analysis, architecture decisions and verification evidence
```

## Notes on the Windows console

Some PowerShell setups print UTF-8 output in the console's legacy code page (CP437). Accented characters and the em dash can look garbled in command output even though the files are valid UTF-8 — the defect is in the terminal, not in the file. Reading the file with an editor that detects UTF-8 shows the correct text.

The empty-variable behaviour described under Configuration is the other console trap: `$env:NAME = ""` deletes the variable, so a probe that intends to test "variable set but empty" has to set a space instead.
