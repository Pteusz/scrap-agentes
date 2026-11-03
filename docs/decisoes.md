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

## Etapa 07 — Fila na tabela `job`, worker separado

**Fila.** A tabela `job` é a fila (sem Redis nem broker). A API só valida e insere o job `pendente`; o worker (`python -m scrapagentes.trabalhador`) reivindica o mais antigo com um `UPDATE ... RETURNING` atômico (`tentativas + 1`) e roda um job por vez. Dois workers não executam o mesmo job; a trava de trabalho pesado (transcrição e frames) continua valendo entre processos.

**Retentativas.** No máximo 3 execuções (1 + 2 retentativas). Falha transitória volta o job para `pendente` e ele vai para o fim da fila (`atualizado_em` muda), então um job ruim não trava os outros. O campo `erro` acumula uma linha por tentativa (`tentativa N/3: codigo: mensagem`). Erros definitivos não são repetidos: `nao_encontrado`, `formato_nao_suportado`, `exige_login`, `entrada_invalida` (erro fica como `codigo: mensagem`).

**Queda do processo.** O job fecha (`concluido` + `item_id`) na mesma transação que grava item, imagens, métricas, subnichos e índice de busca: ou tudo ou nada. A mídia é gravada em `midia/<id>.novo` antes do commit e trocada depois dele. Ao subir, o worker (`recuperar`): põe jobs `executando` de volta em `pendente` (anotando "processo interrompido"; se já usou as 3 tentativas, vira `erro`), apaga `processamento-*` e resolve cada `midia/<id>.novo`: se o job de ingestão desse item fechou depois da criação da pasta, conclui a troca; senão apaga. Item cuja pasta de mídia sumiu é refeito na próxima ingestão.

**`item_id` na resposta do `POST /itens`.** O SPEC diz 202 com `job_id` e `item_id`. Com a fila, um item novo só passa a existir quando o worker roda, então a resposta traz `item_id: null` nesse caso (o id real aparece em `GET /jobs/{id}`). Para URL já ingerida a resposta traz o id existente. **Confirmar com o Mateus** se isso serve ou se prefere criar o item vazio na hora.

**Uploads do adaptador manual** ficam em `dados/entrada/<job_id>/` até o job terminar (sucesso ou erro final).
