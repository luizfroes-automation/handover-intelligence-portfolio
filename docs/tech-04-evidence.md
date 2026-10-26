# Evidência — tratamento de erro do endpoint /handover

Execução local com `python -m uvicorn app.main:app` e chamadas pelo Swagger UI
(`http://127.0.0.1:8000/docs`), em 26 de outubro de 2026.

## Cenário 1 — modelo inexistente (erro de configuração do provider)

**Como foi provocado:** `$env:GEMINI_MODEL = "modelo-inexistente"` antes de subir o servidor.

**Requisição:**

```json
{
  "messages": [
    {"role": "bot", "content": "Hello! How can I help you today?"},
    {"role": "customer", "content": "I was charged twice for my last order."}
  ]
}
```

**Resposta (status 500):**

```json
{
  "error": "llm_configuration_error",
  "detail": "The service is misconfigured. Please contact support."
}
```

**Log do servidor (trecho):**

```
LLM client is misconfigured
Traceback (most recent call last):
  File "...\app\llm_client.py", line 56, in generate_handover_package
    response = client.models.generate_content(
[... frames do SDK omitidos ...]
google.genai.errors.ClientError: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/modelo-inexistente is not found for API version v1beta, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}

The above exception was the direct cause of the following exception:

[... frames do FastAPI omitidos ...]
  File "...\app\llm_client.py", line 74, in generate_handover_package
    raise LLMConfigurationError(
        "LLM provider rejected the client configuration"
    ) from exc
app.errors.LLMConfigurationError: LLM provider rejected the client configuration
INFO:     127.0.0.1:62802 - "POST /handover HTTP/1.1" 500 Internal Server Error
```

**O que demonstra:** o erro do provider chega ao cliente como um erro de domínio
com corpo estável, sem stack trace nem mensagem do provider. A mensagem original
do provider fica preservada no log, encadeada como causa.

## Cenário 2 — transcript vazio (validação de entrada)

**Como foi provocado:** requisição com lista de mensagens vazia, mantendo o modelo
inexistente configurado.

**Requisição:**

```json
{"messages": []}
```

**Resposta (status 422):**

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

**Log do servidor:**

```
INFO:     127.0.0.1:58336 - "POST /handover HTTP/1.1" 422 Unprocessable Content
```

**O que demonstra:** a requisição é rejeitada antes de chegar ao provider. Com o
modelo inexistente ainda configurado, qualquer chamada ao provider resultaria em
500; a resposta 422 sem nenhum erro no log confirma que o provider não foi chamado.

## Observação — indisponibilidade real do provider

Durante a execução da suíte de testes, o provider respondeu 503 ("high demand")
a uma chamada real. O log registrou `LLM provider unavailable` com a
`ProviderUnavailableError` encadeada ao `ServerError` original, e o endpoint
respondeu 503.
