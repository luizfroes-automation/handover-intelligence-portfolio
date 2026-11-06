# the transcript suite — evidência das rodadas `live`

**Data:** 6 November 2026.
**Comando:** `python -m pytest -m live -v`, mais um detalhamento por caso para registrar valor observado e `confidence` (o pytest diz passa/falha, não o que o modelo respondeu).

**Modelo efetivo:** `gemini-3.1-flash-lite`, lido de `GEMINI_MODEL` no `.env` local. O default do cliente em `app/llm_client.py` é `gemini-3.8-flash`: quem reproduzir sem `.env` roda outro modelo. Isso é o the environment work, item 6.

**Chaves:** as reais do `.env` local. Nenhuma chave aparece neste documento.

## O input mudou depois do observado — declarado, com motivo

A ordem no histórico é esta, e ela fica visível de propósito:

| Commit | O que muda |
|---|---|
| `78b9b0c` | fixtures com o esperado declarado, **antes** de qualquer rodada `live` |
| `7ca8967` | primeiro teste `live`; rodadas 1 e 2 com a transcrição A |
| `b35b76a` | transcrição do caso ambíguo **trocada** (motivo abaixo) |
| `6859cd6` | `xfail` removido (não porque o esperado mudou) |
| `2d14c6f` | o caso corrigido virou `needs_history_lookup` e entrou `ambiguous_mixed_signal` |

**Transcrição A, a original** (`78b9b0c`):

```
customer: It still does not work.
bot:      Could you tell me what is not working?
customer: The thing I told you about before.
bot:      I do not have that context in this chat.
customer: Forget it.
```

Ela não testava contexto insuficiente: o cliente **desiste**. Não há pergunta do cliente que o bot não consiga interpretar — há um cliente encerrando a conversa, que é o cenário do the no-reply case ("cliente calou"), fora do escopo deste ticket. O `handoff_needed=false` do modelo era leitura defensável, e o "achado" era da fixture. A troca do input é a decisão registrada aqui; o esperado (`true`, low–medium) nunca mudou.

## Rodadas finais (7 e 8, com o conjunto de 6 casos)

| Caso | Esperado | Observado (detalhamento) | `confidence` | Rodada 7 (`pytest`) | Rodada 8 (`pytest`) |
|---|---|---|---|---|---|
| `simple_unresolved_request` | true / low–medium | true / medium | 0.95 | PASSED | PASSED |
| `urgent_sensitive_case` | true / high | true / high | 0.98 | PASSED | PASSED |
| `needs_history_lookup` | true / low–medium | true / medium | 0.95 | PASSED | PASSED |
| `ambiguous_mixed_signal` | **não assertado** | false / low | **0.95** | PASSED | PASSED |
| `resolved_no_handoff` | false / — | false / low | 1.00 | PASSED | PASSED |
| `repeated_contact` | true / medium–high | true / high | 0.98 | PASSED | PASSED |

`pytest -m live`: `7 passed, 32 deselected` nas duas rodadas (seis casos mais o teste `live` de ponta a ponta). Suíte padrão: `32 passed, 7 deselected`.

**Achado de calibração, não corrigido aqui:** no caso desenhado para ser ambíguo, o modelo respondeu `handoff_needed=false` **com `confidence` 0.95** — ele não sinaliza incerteza num caso em que duas leituras são defensáveis. O achado é sobre o `confidence` ser autodeclarado e não calibrado, e vai para as limitações do business brief (**the business brief**). A ideia de um limiar (por exemplo, `confidence` abaixo de 0.8 em caso ambíguo) é **hipótese testada em um caso**, não contrato estabelecido: um caso e um modelo não fixam regra de calibração.

## Histórico das rodadas anteriores

| Rodada | Conjunto | Resultado |
|---|---|---|
| 1 e 2 | transcrição A, 5 casos | `1 failed, 5 passed` — o caso ambíguo devolvia `false` (motivos `customer_disengagement`, `customer_declined_assistance`, `customer_abandonment`) |
| 3 e 4 | transcrição corrigida, ainda com 5 casos | todos os campos assertados bateram |
| 5 e 6 | `pytest`, 5 casos + endpoint | `6 passed` |

## Xfail: o caminho foi exercitado

Com `KNOWN_MISSES` vazio, o caminho ficaria sem prova. Duas mutações em produção (retorno fixo com `handoff_needed=False`, sem chamada de rede) e uma entrada temporária em `KNOWN_MISSES`:

```
A) caso falha + xfail(strict, raises=AssertionError) -> XFAIL,  exit 0
B) caso passa + xfail(strict)                       -> [XPASS(strict)] -> FAILED, exit 1
```

A prova A mostra o mecanismo funcionando; a B mostra por que ele é estrito: se o modelo começar a acertar, a rodada falha e a marcação tem de ser removida. Ambas foram revertidas com os arquivos restaurados byte a byte.

## Divergências entre rodadas

- **Campos assertados** (`handoff_needed`, faixa de `urgency`): estáveis em todas as rodadas.
- **Campos livres** (`reason`, `flags`, `summary`): variam e não são assertados. Exemplos: `order_modification_request` × `order_modification_inquiry`; `customer_resolved` × `customer_issue_resolved`; `billing_dispute` × `unauthorized_transaction_fraud`.
- **Falhas de provider:** nenhuma. Nenhum skip por falta de chave nas rodadas com chave real.

## Como reproduzir

```powershell
python -m pytest -m live -v
```

O detalhamento caso a caso foi gerado com um laço sobre `tests.fixtures.transcripts.CASES` chamando `generate_handover_package` e imprimindo `handoff_needed`, `urgency.value`, `confidence` e `reason`. Nada além do modelo e das respostas é registrado.
