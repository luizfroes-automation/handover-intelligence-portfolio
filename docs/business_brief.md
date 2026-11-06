# Handover estruturado para atendimento automatizado

*6 de novembro de 2026. Dados sintéticos.*

## Problema

Quando o bot não resolve, ele transfere sem o que já tentou, com prioridade de caso trivial e numa fila genérica. A decisão de transferir existe só dentro do bot.

## Solução

Uma API recebe a transcrição e devolve a decisão explícita: se transfere, por quê, o que já foi tentado, a urgência, a fila e a confiança. O pacote é validado contra um contrato — a validação garante a forma, não o acerto.

## Arquitetura

`transcrição → endpoint → modelo com saída estruturada → validação → pacote`. Falhas do provedor viram três respostas estáveis — indisponível, resposta inválida, configuração — para saber se repete, escala ou abre chamado.

## Impacto estimado — hipótese, não medido

O agente começaria com contexto, e casos sensíveis não competiriam com dúvidas simples. A confiança poderá separar o que segue direto do que precisa de revisão, depois de calibrada. Nada foi medido: tempo, custo e roteamento exigiriam piloto real.

## Limitações

1. **Confiança autodeclarada e não calibrada.** Num caso ambíguo, o sistema declarou 95% de segurança. Até o número ser confiável, casos sensíveis precisam de revisão humana. Registro: `docs/tech-05-evidence.md`.
2. **Reprodutibilidade.** Depende da versão do modelo no ambiente; o padrão no código não é o das rodadas. Comparações precisam registrar versão e data. Ver `app/llm_client.py`.
3. **Base pequena.** Seis casos sintéticos, um modelo, duas rodadas: os cinco declarados acertam, o que não prova produção. Ver `tests/fixtures/transcripts.py`.

**Medido:** decisão e urgência bateram nos cinco casos declarados, nas duas rodadas; o sexto é ambíguo por construção e não tem resultado esperado.

## Próximos passos

- Timeout, nova tentativa e alternativa quando o provedor está fora.
- Limites de tamanho de entrada e tratamento de bloqueio por filtro de segurança.
