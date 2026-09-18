# Problem Statement — AI Handover Intelligence (P1)

**Fase:** 1 — Discovery / Problem Framing
**Autor (papel):** Business Analyst / Consultant
**Status:** Rascunho para validação
**Data:** 12 September 2026

> Nota de integridade: este documento descreve um cenário **genérico e sintético**,
> construído a partir de padrões conhecidos do setor de atendimento ao cliente com
> IA conversacional. Nenhum dado, métrica ou detalhe operacional real de qualquer
> empregador é utilizado aqui.

---

## 1. Contexto

Operações de atendimento ao cliente que utilizam IA conversacional (bots) para
resolução de primeiro nível frequentemente precisam transferir ("handover") a
conversa para um agente humano quando o bot não consegue resolver a solicitação
sozinho.

Esse padrão é comum em setores regulados ou de alto volume: telecom, serviços
financeiros, seguros, apostas/gaming, e-commerce.

## 2. Problema observado

Quando o handover bot → humano acontece, observam-se falhas recorrentes no
processo de transferência em si (não na capacidade do bot de resolver o problema
original):

- O agente humano recebe a conversa sem visibilidade clara do que já foi
  tentado pelo bot.
- A conversa é roteada para uma fila genérica em vez do time/especialidade
  correta.
- Casos sensíveis (ex: risco, segurança, disputas financeiras) não chegam
  sinalizados com prioridade diferenciada de uma dúvida trivial.
- O cliente precisa reexplicar o contexto do zero ao agente humano.

## 3. Quem é afetado

| Ator | Impacto observado |
|---|---|
| Cliente | Retrabalho (reexplicar o problema), possível frustração |
| Agente humano | Tempo gasto reconstruindo contexto antes de agir |
| Operação/negócio | Potencial aumento de tempo médio de resolução e de re-contatos |

## 4. Por que importa agora

**[HIPÓTESE]** Falhas de handover são um ponto de fricção conhecido em operações
de atendimento com IA conversacional em escala — a literatura de mercado e
benchmarks de CX apontam handover mal executado como uma das principais fontes
de insatisfação em jornadas híbridas bot+humano.

**[NÃO MEDIDO NESTE PROJETO]** Este documento não apresenta números de impacto
financeiro ou operacional medidos. Qualquer estimativa de impacto será
apresentada separadamente no Business Brief (Fase 6), com classificação
explícita de Medido / Hipótese / Estimativa.

## 5. Fora de escopo (explicitamente)

Este Problem Statement **não cobre**:

- Por que o bot não conseguiu resolver a solicitação original (isso é um
  problema de capability do bot, não de handover)
- Qualidade do agente humano após o handover
- Qualquer solução técnica ou tecnológica (deliberadamente omitida nesta fase)
- Dados, métricas ou processos reais de qualquer empregador específico

## 6. Perguntas em aberto para a fase de Discovery

1. O problema está na **transferência de informação** (contexto perdido) ou no
   **roteamento** (fila errada) — ou ambos, com pesos diferentes?
2. Existe hoje algum processo manual/humano tentando mitigar isso, ou é
   inexistente?
3. Qual seria o critério de sucesso se o problema fosse resolvido? (Isso vira
   a base dos requisitos na próxima fase.)

---

**Próxima fase:** Discovery Notes (02_discovery_notes.md) — resposta às
perguntas da seção 6 e definição de requisitos e constraints.
