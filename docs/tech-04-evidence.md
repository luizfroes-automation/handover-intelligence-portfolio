# Evidence — error handling of the /handover endpoint

Local run with `python -m uvicorn app.main:app` and calls through Swagger UI
(`http://127.0.0.1:8000/docs`), on 26 October 2026.

## Scenario 1 — non-existent model (provider configuration error)

**How it was provoked:** `$env:GEMINI_MODEL = "modelo-inexistente"` before starting the
server. The model name is Portuguese for "non-existent model". The command and the log
lines below are unaltered from the run on 26 October 2026, except for the marked omissions.

**Request:**

```json
{
  "messages": [
    {"role": "bot", "content": "Hello! How can I help you today?"},
    {"role": "customer", "content": "I was charged twice for my last order."}
  ]
}
```

**Response (status 500):**

```json
{
  "error": "llm_configuration_error",
  "detail": "The service is misconfigured. Please contact support."
}
```

**Server log (excerpt):**

```
LLM client is misconfigured
Traceback (most recent call last):
  File "...\app\llm_client.py", line 56, in generate_handover_package
    response = client.models.generate_content(
[... SDK frames omitted ...]
google.genai.errors.ClientError: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/modelo-inexistente is not found for API version v1beta, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}

The above exception was the direct cause of the following exception:

[... FastAPI frames omitted ...]
  File "...\app\llm_client.py", line 74, in generate_handover_package
    raise LLMConfigurationError(
        "LLM provider rejected the client configuration"
    ) from exc
app.errors.LLMConfigurationError: LLM provider rejected the client configuration
INFO:     127.0.0.1:62802 - "POST /handover HTTP/1.1" 500 Internal Server Error
```

**What it demonstrates:** the provider error reaches the client as a domain error with a
stable body, with no stack trace and no provider message. The original provider message is
preserved in the log, chained as the cause.

## Scenario 2 — empty transcript (input validation)

**How it was provoked:** a request with an empty list of messages, keeping the non-existent
model configured.

**Request:**

```json
{"messages": []}
```

**Response (status 422):**

```json
{
  "detail": [
    {
      "type": "too_short",
      "loc": ["body", "messages"],
      "msg": "List should have at least 1 item after validation, not 0",
      "input": [],
      "ctx": {"field_type": "List", "min_length": 1, "actual_length": 0}
    }
  ]
}
```

**Server log:**

```
INFO:     127.0.0.1:58336 - "POST /handover HTTP/1.1" 422 Unprocessable Content
```

**What it demonstrates:** the request is rejected before it reaches the provider. With the
non-existent model still configured, any call to the provider would result in 500; the 422
response with no error in the log confirms the provider was not called.

## Observation — real provider unavailability

While the test suite was running, the provider answered 503 ("high demand") to a real call.
The log recorded `LLM provider unavailable` with `ProviderUnavailableError` chained to the
original `ServerError`, and the endpoint answered 503.

## Observation — suite timing variance

The same suite took about 170 s in one run and 6.23 s in another. The difference is entirely
in the test that calls the real provider: 5.52 s in the second run, ending in 503, against
milliseconds for everything else. With no timeout configured, the time depends on how the
provider answers. See the planned timeout and retry and the live-split work.

## Suite command without the test that calls the provider

```powershell
python -m pytest --ignore=tests/llm_manual_test.py --deselect tests/test_api.py::test_post_handover_returns_valid_handover_package -v
```

Result: 26 collected, 1 deselected, 25 passed. The deselected one is the integration test
`tests/test_api.py::test_post_handover_returns_valid_handover_package`; splitting by marker
is the live-split work.
