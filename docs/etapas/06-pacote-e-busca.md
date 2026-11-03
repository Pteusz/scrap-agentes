# Etapa 06 — Pacote e busca

Antes de começar: leia CLAUDE.md, docs/SPEC.md (seções 3 e 7) e este arquivo. Não leia outras etapas.

## Objetivo
Montar o pacote final por item e a busca completa, integrando transcrição e frames, com o adaptador `manual`.

## Contrato
- `GET /itens/{id}/pacote` devolve contexto, métricas mais recentes, texto com minutagem (vídeo) e imagens em ordem, com `segundo`, `marcador` e `fala_proxima`.
- `GET /itens` aceita todos os filtros do SPEC.

## Fora de escopo
Fila e worker (etapa 07), Instagram real.

## Construir
1. Ingestão síncrona para testes: arquivo enviado no `manual` passa por transcrição (etapa 04) e frames (etapa 05) e é gravado.
2. Montagem do pacote conforme o SPEC. `fala_proxima` é o trecho cujo intervalo contém o segundo da imagem, ou o mais próximo.
3. Rota de imagem autenticada.
4. Busca completa: filtros combináveis, paginação, modo "todos" ou "qualquer" para subnichos, filtro de métrica sobre a coleta mais recente, texto livre.

## Rodar
Comando da API, como em CLAUDE.md.

## Testar
- Vídeo sintético com fala (ou a fixture do Mateus): pacote com texto e imagens, imagens em ordem de tempo, marcadores coerentes com o segundo.
- Foto: pacote com uma imagem e sem texto, marcador ou segundo.
- Carrossel: imagens na ordem enviada, sem marcador.
- `fala_proxima` correto em um caso construído de propósito.
- Busca: cada filtro isolado e combinados; paginação estável; subnicho com escrita diferente casa.
- Métrica: depois de duas coletas com valores diferentes, a busca e o pacote usam a mais recente.

## Validar
Mostrar ao Mateus um pacote completo de um vídeo real, impresso de forma legível (contexto, texto, imagens com legenda de segundo e marcador), e um exemplo de busca combinada.

## Pronto quando
- Testes passam.
- O pacote tem exatamente os campos do SPEC.
- O Mateus aprovou o formato do pacote de um vídeo real.

## Preciso do Mateus
Aprovação do formato do pacote.

## Entrega
Atualizar `docs/progresso.md` com evidências. Revisão por subagente.
