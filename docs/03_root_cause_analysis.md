# Root Cause Analysis — AI Handover Intelligence (P1)

**Fase:** 3 — Root Cause Analysis
**Autor (papel):** Business Analyst / Consultant
**Método:** Issue Tree (MECE) — ref. Conn & McLean, *Bulletproof Problem Solving*
**Status:** Rascunho para validação

> Nota de limitação: este projeto não possui dados de produção reais para
> validação estatística das hipóteses abaixo. A avaliação é baseada em
> relato de especialista de domínio (SME) e raciocínio lógico. Cada hipótese
> é marcada como **Hipótese avaliada**, não como **Medido**. Numa consultoria
> real com acesso a dados de produção, esta fase incluiria validação
> quantitativa (ex: análise de logs, taxa de correlação).

---

## 1. Pergunta central do issue tree

> Por que o agente humano não recebe visibilidade sobre o motivo específico
> da decisão de handoff? (Achado 2 do Discovery)

## 2. Hipóteses (MECE)

| # | Hipótese | Categoria (Fishbone) |
|---|---|---|
| A | A tecnologia nunca captura o motivo da decisão — ele é perdido na origem (o bot decide, mas não registra "por quê") | Tecnologia |
| B | A tecnologia captura o motivo, mas não repassa esse dado ao agente no momento do handoff | Processo / Tecnologia |
| C | O processo organizacional não exige que o motivo seja comunicado ao agente como critério de qualidade do handoff | Processo |
| D | O motivo é repassado, mas em formato que o agente não consegue ler rapidamente sob pressão de tempo | Pessoas / UX |

## 3. Avaliação de cada hipótese

### Hipótese A — Motivo nunca é capturado
**[HIPÓTESE AVALIADA — provavelmente falsa, ou parcialmente falsa]**
Segundo o relato do SME, o sistema já usa sinais claros para decidir o handoff
(ex: um comentário específico do cliente, um status de conta, uma lacuna de
conteúdo). Isso indica que o sinal de decisão **existe internamente** no
sistema — ele não é aleatório. Portanto, é pouco provável que o motivo
simplesmente "não exista".

### Hipótese B — Motivo existe, mas não é repassado
**[HIPÓTESE AVALIADA — mais provável, principal candidata a causa raiz]**
O relato do SME confirma que o agente "nunca sabia o que a IA olhou" — ou
seja, o sinal existe na decisão do sistema, mas se perde entre a decisão e a
entrega ao agente. Isso é consistente com um padrão comum em arquiteturas de
classificação/roteamento: o modelo produz uma decisão binária ou uma
categoria (ex: "transferir: sim/não", "fila: X"), mas descarta o raciocínio
intermediário porque **o payload de handoff nunca foi desenhado para carregá-lo.**

### Hipótese C — Processo não exige comunicação do motivo
**[HIPÓTESE AVALIADA — verdadeira, mas consequência da B, não causa independente]**
É razoável que, se a tecnologia nunca foi desenhada para carregar o motivo
(Hipótese B), o processo organizacional também nunca tenha formalizado essa
exigência — não havia como exigir algo que o sistema não produz. Trato isso
como **sintoma decorrente de B**, não como causa raiz separada.

### Hipótese D — Motivo é repassado mas ignorado por formato
**[HIPÓTESE AVALIADA — não suportada pelo relato disponível]**
Não há evidência, no relato do SME, de que o motivo chegue ao agente em
qualquer formato (mesmo ruim). O relato indica ausência da informação, não
presença mal formatada. Esta hipótese fica descartada por falta de evidência
— não por ser logicamente impossível.

## 4. Causa raiz identificada

**[HIPÓTESE AVALIADA — causa raiz mais provável, sujeita a validação com dado real numa reprodução em produção]**

> A causa raiz é estrutural/arquitetural: **o momento de decisão do bot (por
> que transferir, para onde, com que prioridade) não produz um artefato de
> saída estruturado que carregue o raciocínio** — apenas uma ação (transferir)
> e, no máximo, uma categoria simples. O raciocínio se perde porque nunca foi
> desenhado para ser um "produto" explícito da decisão.

Isso reformula o problema de forma acionável: a solução não precisa "adicionar
IA" no sentido genérico — precisa **transformar a decisão de handoff, que hoje
é implícita, em um artefato estruturado e explícito.**

## 5. Por que isso não é (só) um problema de pessoas ou de processo

**[INTERPRETAÇÃO]** Poderia-se argumentar que "o agente deveria perguntar mais"
ou "deveria haver um checklist de handoff". Isso trataria o sintoma (Hipótese C),
não a causa (Hipótese B). Enquanto o sistema não produzir o motivo de forma
estruturada, nenhum processo ou treinamento de pessoas resolve — não há dado
pra comunicar.

Esta é uma distinção importante para o Business Case: **descarta soluções de
processo/treinamento como resposta principal**, sem ainda comprometer com
uma solução técnica específica (isso vem na próxima fase, Options).

---

**Próxima fase:** Solution Options (04_solution_options.md) — gerar mais de
uma alternativa de solução (nem todas com IA) para resolver a causa raiz
identificada, comparar trade-offs, e só então recomendar.
