# Decisões técnicas

Registro curto das decisões tomadas ao longo das etapas. Cada entrada diz o que foi decidido, por quê e o que ficou sem verificar.

## Etapa 05 — Seleção de frames: biblioteca própria, projetos externos só como referência

**Decisão.** A seleção de frames é implementada em `scrapagentes/frames.py`, sem adotar `claude-real-video` nem `claude-video` como dependência. Os dois serviram de referência de abordagem.

**O que cada um faz** (segundo a documentação pública dos repositórios; o código-fonte não foi lido linha a linha):

| Projeto | Candidatos | Dedup | Limite |
|---|---|---|---|
| claude-real-video | detecção de cena do ffmpeg em uma passada (limiar padrão 0,30) com piso de densidade | diferença de pixels em RGB reduzido (8%), janela deslizante de 4 | teto rígido de 150 frames |
| claude-video | frames de mudança de cena, com amostragem uniforme conforme a duração como reserva | miniaturas 16x16 em cinza, diferença média absoluta | teto aplicado depois do dedup |

**Critério da etapa:** o projeto permite impor a cobertura mínima por terço do vídeo (SPEC, seção 6, regra 6)? Nenhum dos dois tem essa regra, e ambos trabalham com tetos de dezenas ou centenas de frames, contra os 16 do SPEC. Adotar qualquer um exigiria de qualquer forma uma camada própria por cima, mais uma dependência (e, no caso do claude-real-video, a licença MIT que consta nas etiquetas do repositório não foi conferida no arquivo de licença).

**Como ficou.** Mesma ideia dos dois (cena do ffmpeg + hash de miniatura em cinza), com a cobertura por terço, o preenchimento uniforme e o teto de 16 implementados aqui, tudo configurável com os valores iniciais do SPEC. Só numpy e ffmpeg; Pillow é opcional e só gera a folha de contato.

**Determinismo.** A decisão é tomada sobre miniaturas extraídas em grade regular de tempo (4 por segundo), só com médias e comparações; desempates sempre pelo menor índice. As imagens finais são extraídas só dos segundos escolhidos.

**Parâmetros** (`ParametrosFrames`, sobrescrevíveis por `SCRAPAGENTES_FRAMES_<NOME>`): `limiar_cena` 0,20; `minimo_candidatos` 8; `teto` 16; `minimo_por_terco` 2; `dedup_diferenca` 2,0 (diferença média 0-255 entre miniaturas 16x16); `luma_minima` 16 (quase preto); `nitidez_minima` 8 (variância do laplaciano, só para quadros com textura); `amostras_por_s` 4; `diferenca_estavel` 6. Os quatro últimos são valores nossos, sem número no SPEC; ajustar com os vídeos reais.
