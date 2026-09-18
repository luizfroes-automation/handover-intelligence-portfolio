# ADR-001 — Arquitetura da solução (AI Handover Intelligence)

**Status:** Decidido
**Contexto:** Root Cause Analysis (03) identificou que a decisão de handoff
precisa virar um **artefato estruturado e explícito**, não uma ação implícita.

## Opções consideradas (rápido, não elicitação completa)

| Opção | Descrição | Por que não |
|---|---|---|
| A. Regras fixas (if/else) | Classificar handoff por palavras-chave/regras | Não generaliza para linguagem natural variada; não escala pra novos motivos sem reescrever regras |
| B. Classificador ML tradicional (ex: scikit-learn) | Treinar um modelo supervisionado pequeno | Exigiria dataset rotulado que não existe (sintético não é suficiente pra treinar bem); fora do escopo de tempo do projeto |
| **C. LLM com structured output** | Usar um LLM para ler a transcrição e gerar JSON validado contra schema | **Escolhida** — generaliza bem para linguagem natural, não exige dataset de treino, e o "raciocínio" (reason/summary) é subproduto natural de um LLM, resolvendo diretamente o gap de explicabilidade do Root Cause |

## Decisão

Usar LLM com **structured output / function calling** (não parsing de texto livre),
validado contra schema Pydantic antes de qualquer resposta ser considerada válida.

## Trade-off assumido (declarar em entrevista)

- Custo por chamada de API (vs. regra fixa, que é gratuita)
- Dependência de um provedor externo (Anthropic/OpenAI)
- Latência maior que uma regra local

Esses trade-offs são aceitáveis para portfólio e são o padrão de mercado atual
para este tipo de tarefa (classificação semântica sobre linguagem natural).
