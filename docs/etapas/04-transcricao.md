# Etapa 04 — Transcrição

Antes de começar: leia CLAUDE.md, docs/SPEC.md e este arquivo. Não leia outras etapas. Consulte `docs/VPS.md` (capacidade e decisão de tamanho de modelo).

## Objetivo
Transformar um arquivo de vídeo em uma lista de trechos com minutagem, de forma independente de qualquer rede.

## Contrato
- Entra: caminho de um arquivo de vídeo (ou áudio).
- Sai: lista ordenada de `{inicio_s, fim_s, texto}`; lista vazia se não houver fala.

## Fora de escopo
Separar falantes (diarização), tradução, legendas queimadas, integração com a fila (etapa 07).

## Construir
1. Extração de áudio com ffmpeg (16 kHz, mono).
2. Transcrição com **faster-whisper**, em CPU com quantização int8, com **VAD ligado** para reduzir alucinação em silêncio e música. Idioma configurável, com `pt` como padrão (não depender de autodetecção).
3. Tamanho do modelo configurável. Valor inicial vem de `docs/VPS.md`; confirme com o teste desta etapa.
4. Um trabalho de transcrição por vez (trava simples), para não disputar CPU e RAM.
5. Saída normalizada: trechos em ordem, sem sobreposição, com `fim_s` não maior que a duração.

## Rodar
Comando que recebe um arquivo e imprime os trechos.

## Testar
- Fixture do Mateus: `tests/fixtures/fala_pt.mp4` e `tests/fixtures/fala_pt.txt` (transcrição correta feita à mão).
- Vídeo sem fala (fixture sintética da etapa 02): devolve lista vazia, sem erro.
- Trechos ordenados, sem sobreposição, dentro da duração.
- Determinismo: duas execuções do mesmo arquivo dão o mesmo texto.

## Validar
- Calcule e relate o **WER** (taxa de erro de palavras) contra a transcrição feita à mão, para o tamanho de modelo escolhido. Teste ao menos dois tamanhos e mostre a comparação de erro e de tempo.
- Relate o tempo de processamento dividido pela duração do áudio, na VPS.
- Recomende o tamanho de modelo final com base nesses números.
- O Mateus decide o limite aceito de erro.

## Pronto quando
- Testes automáticos passam.
- WER e tempo medidos na VPS para pelo menos dois tamanhos de modelo, com recomendação.
- O Mateus aprovou o limite de erro e o modelo escolhido.
- A trava de um trabalho por vez foi testada.

## Preciso do Mateus
- Trecho de vídeo em português de 30 a 60 s e a transcrição correta feita à mão.
- Limite aceito de erro de transcrição.

## Entrega
Atualizar `docs/progresso.md` com evidências. Revisão por subagente.
