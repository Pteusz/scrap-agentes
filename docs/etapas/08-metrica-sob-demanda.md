# Etapa 08 — Métrica sob demanda

Antes de começar: leia CLAUDE.md, docs/SPEC.md (seções 2, 3 e 7) e este arquivo. Não leia outras etapas.

## Objetivo
Permitir uma nova coleta de métricas de um item existente apenas por chamada própria, acrescentando linhas novas sem tocar nas anteriores.

## Contrato
- `POST /itens/{id}/coletas` cria um job de coleta e devolve `202` com `job_id`.
- O worker chama `coletar_metricas` do adaptador da rede do item e grava um conjunto novo de linhas em `metrica` com a data e hora da coleta.

## Fora de escopo
Qualquer agendamento ou recoleta automática, painel de evolução.

## Construir
1. Rota e tipo de job `coleta`.
2. Gravação de um novo `coletado_em` por coleta; todas as linhas da coleta compartilham o mesmo valor.
3. Falha do adaptador (bloqueio, post removido) registra o erro no job e **não altera nem apaga** coletas anteriores.
4. Garantir por teste e por busca no código que **não existe** nenhum agendador, cron interno ou laço de recoleta.

## Rodar
Comandos de API e worker, conforme CLAUDE.md.

## Testar
- Duas chamadas seguidas geram dois conjuntos distintos de linhas, ambos preservados.
- Pacote e busca por métrica passam a usar o conjunto mais recente.
- Falha forçada: coletas antigas intactas, job em `erro`.
- Item de rede sem adaptador registrado: erro claro.
- Busca no código por agendadores devolve nada.

## Validar
Com um post real do Instagram, executar duas coletas e mostrar a diferença entre elas (mesmo que os valores não mudem, mostrar as duas datas).

## Pronto quando
- Testes passam.
- Duas coletas reais preservadas com datas distintas.
- Confirmado que não há recoleta automática.

## Preciso do Mateus
Um post real para o teste (pode ser um dos 3 anteriores).

## Entrega
Atualizar `docs/progresso.md` com evidências. Revisão por subagente.
