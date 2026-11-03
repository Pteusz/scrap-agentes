# Etapa 05 — Frames e marcadores

Antes de começar: leia CLAUDE.md, docs/SPEC.md (seções 3 e 6) e este arquivo. Não leia outras etapas.

## Objetivo
Selecionar, de forma determinística, uma sequência de frames de um vídeo que cubra começo, meio e fim, e marcar cada frame.

## Contrato
- Entra: caminho de um vídeo e a duração.
- Sai: lista de `{ordem, arquivo, segundo, marcador}` com as imagens salvas em disco.

## Fora de escopo
Qualquer IA, leitura de texto na tela (OCR), integração com a fila (etapa 07).

## Construir
1. Antes de escrever código, avalie rapidamente o projeto **claude-real-video** (MIT; detecção de cena e dedup) e a abordagem do **claude-video** (filtro de cena do ffmpeg, dedup perceptual, fallback uniforme) como dependência ou referência. Registre a decisão em `docs/decisoes.md`: usar a biblioteca, usar partes ou implementar por conta própria. O critério é se ela permite impor a **regra de cobertura por terço** do SPEC; se não permitir, implemente a camada de cobertura por cima.
2. Implementar as regras da seção 6 do SPEC: candidatos por mudança de cena (primeiro frame útil incluído), descarte de quase pretos e muito borrados, dedup por hash perceptual, fallback uniforme com menos de 8 candidatos, teto, cobertura mínima por terço, inclusão do primeiro e do último.
3. Marcador conforme a regra do SPEC (seção 3).
4. Todos os parâmetros em configuração, com os valores iniciais do SPEC.
5. Mesma entrada produz exatamente os mesmos segundos.

## Rodar
Comando que recebe um vídeo e imprime os frames escolhidos (segundo e marcador) e salva as imagens.

## Testar
Com vídeos sintéticos gerados com ffmpeg:
- 30 s com 6 cenas de cores bem distintas: pelo menos um frame por cena, sem duplicatas.
- 30 s totalmente estático: cai no fallback uniforme e ainda cobre os três terços.
- Começo preto de alguns segundos: o primeiro frame escolhido não é preto.
- Teto: nunca passa de 16 por padrão; mínimo de 2 em cada terço.
- Marcadores corretos nas bordas (t exatamente em d/3 e 2d/3).
- Determinismo: duas execuções, mesma lista de segundos.
- Vídeo curtíssimo (poucos segundos): não falha e devolve pelo menos um frame.

## Validar
Gere uma folha de contato (as imagens escolhidas em grade, com segundo e marcador) para 2 vídeos reais que o Mateus fornecer e mostre a ele. Ele julga se a sequência permite entender começo, meio e fim.

## Pronto quando
- Testes passam.
- Decisão sobre a biblioteca registrada em `docs/decisoes.md`.
- O Mateus aprovou a folha de contato de ao menos 2 vídeos reais.
- Tempo de processamento por vídeo relatado na VPS.

## Preciso do Mateus
2 vídeos reais de tipos diferentes (por exemplo, uma pessoa falando para a câmera e um com cortes rápidos) e a aprovação da folha de contato.

## Entrega
Atualizar `docs/progresso.md` com evidências. Revisão por subagente.
