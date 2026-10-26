# AI Handover Intelligence

An API that reads a customer-service conversation between a bot and a customer and returns a structured **handover package**: whether the conversation needs a human agent, why, how urgent it is, which team should take it, and what the bot already tried.

> All data in this repository is synthetic. No real customer data or operational data from any company is used.

## The problem

When a support bot cannot resolve a request, it transfers the conversation to a human agent. That handover often fails in predictable ways:

- The agent receives the conversation without knowing what the bot already tried.
- The conversation lands in a generic queue instead of the right team.
- Sensitive cases arrive with the same priority as trivial ones.
- The customer has to explain everything again.

The root cause addressed here is that the handover decision is implicit: the bot transfers the conversation, but the reasoning behind that decision is not delivered to the agent. This project turns that decision into an explicit, structured, validated artifact.

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

Why an LLM with structured output, and not keyword rules or a trained classifier, is explained in [`docs/04_adr_001_arquitetura.md`](docs/04_adr_001_arquitetura.md).

## Error handling

Provider failures never reach the client as raw SDK exceptions. The LLM client translates them into domain exceptions, and the API maps each one to a stable response:

| Condition | HTTP | `error` |
| --- | --- | --- |
| Provider unreachable, timed out or returned 5xx | 503 | `provider_unavailable` |
| Provider returned no structured output, or output that fails validation | 502 | `invalid_llm_response` |
| Provider rejected the request (4xx, e.g. unknown model or invalid key) | 500 | `llm_configuration_error` |
| Any other unexpected error | 500 | `internal_error` |
| Empty transcript | 422 | FastAPI validation error |

Error responses have the form `{"error": "...", "detail": "..."}` with a fixed message per error type. The provider's original error is kept in the server log as the exception cause and is never included in the response body. Conversation content is never logged.

## Tech stack

Python, FastAPI, Pydantic, Google Gemini (`google-genai` SDK), pytest, Black, Ruff.

## Getting started

Requirements: Python 3.14 and a Gemini API key.

```bash
python -m venv venv
```

Activate it:

```bash
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# macOS / Linux
source venv/bin/activate
```

Install the dependencies:

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
```

Create a `.env` file from the example and fill in your values:

```bash
cp .env.example .env
```

| Variable | Description |
| --- | --- |
| `GEMINI_API_KEY` | Your Gemini API key |
| `GEMINI_MODEL` | Gemini model to use. Set it to a model currently available for your key |

## Running the API

```bash
python -m uvicorn app.main:app --reload
```

The interactive documentation is available at `http://127.0.0.1:8000/docs`.

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

## Running the tests

```bash
python -m pytest tests/ --ignore=tests/llm_manual_test.py
```

Most tests mock the LLM client and run offline. One test in `tests/test_api.py` calls the real Gemini API, so it needs a valid key and network access, and it may fail if the provider is temporarily unavailable.

Lint and formatting:

```bash
python -m ruff check .
python -m black --check .
```

## Project structure

```
app/
  main.py         FastAPI app, endpoint and error handlers
  llm_client.py   Gemini integration and error translation
  errors.py       Domain exceptions
  schema.py       Request and response models
tests/            Unit tests and fixtures
docs/             Problem analysis, architecture decisions and verification evidence
```

## Limitations

- The dataset is synthetic; the system has not been tested at production volume.
- The suggested team and urgency are recommendations for a human agent, not final decisions.
- No timeout or retry is configured for the provider client yet.
- Some tests call the real provider and are not yet separated from the offline unit tests.
