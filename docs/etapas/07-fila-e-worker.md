# Etapa 07 — Fila e worker

Antes de começar: leia CLAUDE.md, docs/SPEC.md (seções 3, 5 e 7) e este arquivo. Não leia outras etapas. Consulte `docs/VPS.md` (como rodar processos).

## Objetivo
Tornar a ingestão assíncrona: a API só cria o job, e um processo worker executa o pipeline completo.

## Contrato
- `POST /itens` devolve `202` com `job_id` e `item_id` imediatamente.
- `GET /jobs/{id}` mostra o estado.
- O worker consome a tabela `job` e executa o pipeline do SPEC (seção 5).

## Fora de escopo
Redis ou outra infraestrutura de fila, agendamento automático de qualquer coisa, coleta de métricas sob demanda (etapa 08).

## Construir
1. Processo worker separado da API, que busca jobs pendentes na tabela `job`.
2. Execução do pipeline: adaptador, transcrição e frames (vídeo) ou imagens em ordem (foto e carrossel), gravação e primeira coleta.
3. **Um job pesado por vez**.
4. Retentativa limitada (no máximo 2 retentativas) com o erro registrado em cada tentativa; estado final `erro` com mensagem legível.
5. Recuperação: se o worker cair no meio de um job, o job volta a `pendente` ao reiniciar (sem duplicar item, imagens ou métricas).
6. Idempotência: reingestão de `rede`+`url` existente atualiza e acrescenta coleta, sem duplicar; `reprocessar=true` refaz a mídia.
7. Registro em CLAUDE.md dos comandos para rodar API e worker.

## Rodar
Comandos de API e worker, conforme CLAUDE.md.

## Testar
- Ciclo completo com o adaptador `manual`: criar job, worker executa, item e pacote disponíveis.
- Falha forçada no adaptador: job termina em `erro` com a mensagem; outros jobs seguem.
- Queda do worker no meio: reinício retoma sem duplicar.
- Dois jobs pesados enfileirados: executam em sequência.
- Reingestão: sem duplicar; `reprocessar=true` refaz as imagens.

## Validar
- Teste de ponta a ponta com **um post real de cada formato** (vídeo, foto, carrossel), usando as URLs do Mateus. Mostrar o estado do job, o tempo total e o pacote de cada um.
- Medir uso de CPU e RAM durante um job de vídeo na VPS e relatar.

## Pronto quando
- Testes passam.
- Os 3 posts reais viraram pacotes completos.
- Nenhum item ou imagem duplicado após queda e reinício.
- Uso de recursos na VPS relatado.

## Preciso do Mateus
As 3 URLs reais (as mesmas da etapa 03 servem) e conferência dos pacotes.

## Entrega
Atualizar `docs/progresso.md` com evidências. Revisão por subagente.
