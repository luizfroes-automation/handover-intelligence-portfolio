# Discovery Notes — AI Handover Intelligence (P1)

**Fase:** 2 — Discovery
**Autor (papel):** Business Analyst / Consultant
**Método:** Entrevista estruturada (técnica "Mom Test" — perguntas sobre
comportamento observado, não sobre solução desejada)
**Status:** Rascunho para validação

> Nota de confidencialidade: os achados abaixo foram generalizados a partir de
> experiência real do autor em operações de atendimento com IA conversacional.
> Nenhum sistema, produto, vertical de negócio ou dado específico de qualquer
> empregador é citado. Os padrões descritos são reconhecíveis no setor de CX
> conversacional como um todo, não exclusivos de um caso.

---

## 1. Processo As-Is (resumido)

1. Cliente interage com bot conversacional.
2. Bot identifica que não pode resolver a solicitação e aciona handoff.
3. Roteamento automático direciona a conversa para uma fila/time.
4. Casos sinalizados como sensíveis (ex: risco, segurança, compliance)
   recebem prioridade de fila.
5. Agente humano recebe a conversa e assume o atendimento.
6. **Mecanismo de correção existente:** o agente tem autonomia para
   realocar a conversa para outra fila, caso perceba erro de roteamento.

**[FATO — confirmado por SME]** O roteamento incorreto, quando ocorre, não é
irreversível — existe correção manual disponível no processo atual.

## 2. Achado central (root cause candidate)

**[FATO — confirmado por SME]** O agente humano recebe a conversa transferida
sem visibilidade sobre **a justificativa da decisão de handoff** — ou seja,
não fica claro para o agente:

- Qual sinal específico (ex: um comentário do cliente, um status de conta,
  uma lacuna de conteúdo na base de conhecimento) motivou a transferência.
- O que exatamente o bot já tentou antes de desistir.

Isso reposiciona o problema: **não é apenas "perda de contexto" em termos
genéricos — é especificamente uma lacuna de explicabilidade da decisão de
IA no momento da transferência.**

**[INTERPRETAÇÃO]** Essa distinção importa porque muda o requisito técnico:
o sistema não precisa apenas "resumir a conversa" — precisa **expor o
raciocínio da decisão** de forma estruturada e auditável.

## 3. Mitigações existentes hoje

**[FATO — confirmado por SME]** O processo já é majoritariamente automatizado
(roteamento automático, priorização automática de casos sensíveis). Não existe
triagem manual prévia — a intervenção humana acontece **depois** do handoff,
como correção pontual (mudança de fila), não como prevenção.

## 4. Critério de sucesso (definido pelo SME)

Se o problema fosse considerado resolvido, o pacote de handoff entregue ao
agente deveria conter, simultaneamente:

1. Resumo do que já foi tentado pelo bot.
2. Roteamento para a fila/time correto.
3. Sinalização de prioridade para casos sensíveis.
4. **Rascunho de resposta sugerido**, para acelerar a primeira ação do agente.

**[NOVO REQUISITO IDENTIFICADO NO DISCOVERY]** O item 4 (rascunho de resposta)
não estava no escopo original do brief (Seção 3 do P1) — é um achado de
Discovery que aumenta o escopo de valor da solução. Decisão sobre incluí-lo
no CORE ou no ENHANCEMENT será tomada na fase de Solution Design (trade-off
de tempo vs. valor).

## 5. Requisitos derivados (ainda sem solução definida)

| # | Requisito | Origem |
|---|---|---|
| R1 | O sistema deve capturar e expor o motivo específico do handoff (não só a categoria) | Achado 2 |
| R2 | O sistema deve indicar o que já foi tentado antes da transferência | Achado 2 |
| R3 | O sistema deve sinalizar prioridade para casos sensíveis | Critério de sucesso |
| R4 | O sistema deve indicar o time/fila sugerido | Critério de sucesso |
| R5 (candidato a ENHANCEMENT) | O sistema pode sugerir um rascunho de resposta | Critério de sucesso |
| R6 | A decisão do sistema deve ser auditável (rastreável, não uma caixa-preta) | Achado 2 (explicabilidade) |

## 6. Fora de escopo (reafirmado)

- Melhorar a capacidade do bot de resolver a solicitação original.
- Qualquer alteração no processo de correção manual pós-handoff (já funciona).
- Dado real de qualquer operação específica.

---

**Próxima fase:** Root Cause Analysis (03_root_cause_analysis.md) — estruturar
por que a lacuna de explicabilidade (Achado 2) existe, antes de ir para
Options/Solution Design.
