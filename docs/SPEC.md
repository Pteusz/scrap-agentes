# SPEC — scrapagentes

Versão 1. Este documento é o contrato do projeto. Mudanças nele exigem confirmação do Mateus.

## 1. Objetivo

Guardar posts de redes sociais (Instagram primeiro; outras redes depois) com o contexto que o operador informa e as métricas coletadas ao longo do tempo, e entregar, por item, um **pacote** pronto para uma IA externa: texto, sequência de imagens e contexto. A IA não participa do pipeline.

## 2. Princípios

1. **Núcleo agnóstico de rede.** Banco, fila, transcrição, extração de frames e API só enxergam campos e arquivos padrão. O que é específico de uma rede vive no adaptador dela.
2. **Determinístico.** Sem IA no pipeline. A transcrição usa um modelo fixo de reconhecimento de fala, sem raciocínio, e é aceita como exceção.
3. **O sistema não classifica.** Nicho e subnichos vêm da request; o critério é do operador e fica fora do sistema.
4. **Métrica nunca sobrescreve.** Cada coleta cria linhas novas.
5. **Sem recoleta automática.** Métricas só são coletadas por chamada própria (rota de coleta).
6. **Leve.** Roda em VPS simples; um job pesado por vez.
7. **Identidade.** A mesma `rede` + `url` é o mesmo item.

## 3. Modelo de dados

Nomes em português sem acento. Banco: SQLite (modo WAL). Arquivos de mídia ficam em disco; o banco guarda só caminhos relativos.

### item
| campo | regra |
|---|---|
| id | identificador interno |
| rede | `instagram`, `manual`, e outras no futuro |
| url | link do conteúdo, canônico. Único junto com `rede` |
| conta | nome da conta (vem do adaptador; no `manual` vem da request) |
| nicho | um valor, informado na request |
| formato | vocabulário definido pelo adaptador. Instagram: `video`, `foto`, `carrossel` |
| data_publicacao | data de publicação do post |
| legenda | texto do post. Em redes de texto, é o corpo do post |
| duracao_s | só em vídeo |
| texto | só em vídeo: lista de trechos `{inicio_s, fim_s, texto}`, guardada como JSON |
| criado_em, atualizado_em | controle |

### imagem
| campo | regra |
|---|---|
| id, item_id | |
| ordem | posição na sequência (frames em ordem de tempo; slides em ordem do carrossel) |
| arquivo | caminho relativo |
| segundo | só em vídeo |
| marcador | só em vídeo: `comeco`, `meio` ou `fim` |

### metrica
Uma linha por número, por coleta.
| campo | regra |
|---|---|
| id, item_id | |
| coletado_em | data e hora da coleta. Linhas da mesma coleta compartilham este valor |
| nome | nome padronizado: `curtidas`, `comentarios`, `visualizacoes`, `compartilhamentos`, `seguidores_conta`. O adaptador pode declarar outros (ex.: `retweets`) |
| valor | número |

Métricas opcionais (`visualizacoes`, `seguidores_conta`) só existem quando o adaptador consegue obter.

### subnicho
`item_id`, `tag`. Tags livres. O sistema normaliza a escrita antes de gravar e de buscar: minúsculas, sem acento, espaços aparados e espaços internos colapsados. `Emagrecimento ` e `emagrecimento` são a mesma tag.

### job
Tabela auxiliar da fila: `id`, `item_id` (pode ser nulo antes da criação), `tipo` (`ingestao` ou `coleta`), `estado` (`pendente`, `executando`, `concluido`, `erro`), `tentativas`, `erro`, `parametros` (JSON), `criado_em`, `atualizado_em`.

### Marcador (regra)
Com duração `d` e segundo `t` do frame: `t < d/3` é `comeco`; `d/3 <= t < 2d/3` é `meio`; `t >= 2d/3` é `fim`.

## 4. Contrato do adaptador de rede

Cada rede é um módulo que declara:
- o nome da rede;
- os formatos válidos;
- as métricas que consegue coletar;
- como reconhece uma URL como sua.

Operações:
- **resolver(url)** devolve: conta, formato, data de publicação, legenda, duração (se vídeo), lista de arquivos de mídia já baixados (caminhos locais, em ordem) e métricas iniciais.
- **coletar_metricas(item)** devolve um mapa nome → valor.

Erros tipados: `nao_encontrado`, `bloqueado`, `exige_login`, `indisponivel`, `formato_nao_suportado`.

Regras:
- O adaptador **não** escreve no banco, **não** transcreve e **não** extrai frames.
- Limite de requisições configurável. Proxy e segredos por configuração e variáveis de ambiente.
- **Suite de contrato:** conjunto de testes reutilizável que todo adaptador precisa passar (campos obrigatórios presentes, formato dentro do vocabulário declarado, métricas com nomes e valores numéricos, erros tipados). É criada na etapa 02.

### Adaptador `manual`
Aceita um arquivo enviado na request (vídeo, foto ou carrossel). Conta, formato e data de publicação são informados na request. Métricas podem ser informadas ou ficar ausentes. Serve para testes e conteúdo avulso, e permite testar transcrição e frames sem depender de nenhuma rede.

## 5. Pipeline

1. A request vira um job e devolve `job_id`.
2. O worker chama o adaptador (`resolver`).
3. Se o formato é vídeo: extrai áudio e transcreve; seleciona frames (seção 6) e calcula marcadores. Se é foto ou carrossel: guarda as imagens em ordem.
4. Grava item, imagens, subnichos e a primeira coleta de métricas.
5. Job concluído (ou `erro`, com mensagem).

Reingestão da mesma `rede` + `url`: atualiza campos textuais (legenda, nicho, subnichos quando informados) e acrescenta uma coleta de métricas. Não reprocessa a mídia, salvo `reprocessar=true`.

## 6. Seleção de frames (vídeo)

Regras determinísticas. Valores iniciais configuráveis:
1. Candidatos: primeiro frame útil e todo frame em que a pontuação de mudança de cena do ffmpeg passa de `0,20`.
2. Descartar frames quase pretos e muito borrados por medida simples.
3. Deduplicar por hash perceptual (miniatura em tons de cinza pequena) com limiar de diferença configurável.
4. Se restarem menos de 8 candidatos, completar com amostragem uniforme no tempo.
5. Teto padrão: 16 frames. Se passar, reduzir por amostragem uniforme entre os candidatos.
6. **Cobertura:** pelo menos 2 frames em cada terço do vídeo (começo, meio, fim), incluindo o primeiro frame útil e o último antes dos créditos. Se um terço ficar abaixo do mínimo, completar com o frame estável mais próximo dos maiores vazios de tempo.
7. Mesma entrada produz os mesmos segundos (determinismo).

## 7. API

Autenticação por chave de API em cabeçalho, exigida em todas as rotas exceto `/saude`. A documentação interativa fica desligada em produção.

| rota | função |
|---|---|
| `POST /itens` | adicionar. Corpo: `url` (ou arquivo, no `manual`), `nicho`, `subnichos[]`, e para `manual`: `conta`, `formato`, `data_publicacao`. Opcional: `reprocessar`. Devolve `202` com `job_id` e `item_id` |
| `GET /jobs/{id}` | estado do job |
| `GET /itens/{id}/pacote` | pacote final (abaixo) |
| `GET /itens/{id}/imagens/{ordem}` | arquivo da imagem, autenticado |
| `GET /itens` | busca paginada. Filtros combináveis: `rede`, `conta`, `nicho`, `subnicho` (um ou vários, com modo "todos" ou "qualquer"), `formato`, `publicado_de`, `publicado_ate`, métrica (`nome`, `min`, `max`, sobre a coleta mais recente), `q` (texto livre sobre legenda e texto falado) |
| `PATCH /itens/{id}/subnichos` | adicionar, remover ou substituir tags, sem reprocessar |
| `POST /itens/{id}/coletas` | coleta de métricas sob demanda. Devolve `202` com `job_id` |
| `GET /saude` | sem autenticação; devolve apenas que o serviço está no ar |

### Pacote
- **contexto:** rede, link, conta, nicho, subnichos, formato, data de publicação, legenda, duração.
- **metricas:** coleta mais recente (`coletado_em` e valores por nome).
- **texto:** só em vídeo, lista de trechos com `inicio_s`, `fim_s`, `texto`.
- **imagens:** em ordem; cada uma com `ordem`, rota do arquivo e, em vídeo, `segundo`, `marcador` e `fala_proxima` (o trecho de fala que contém aquele segundo, ou o mais próximo).

## 8. Instagram (adaptador inicial)

Formatos `video`, `foto`, `carrossel`. Métricas: `curtidas`, `comentarios`, e `visualizacoes` quando disponível. A biblioteca de coleta é escolhida na etapa 03 após teste de viabilidade a partir da VPS.

## 9. Stack

Python, FastAPI, SQLite em modo WAL (com busca de texto FTS5), ffmpeg, faster-whisper, pytest. Dois processos: API e worker (a fila é a tabela `job`; sem Redis). Proxy reverso e forma de rodar os processos (systemd ou Docker Compose) são decididos na etapa 01 conforme o que a VPS já tem.

## 10. Deploy e domínio

Código-fonte: `https://github.com/Pteusz/scrap-agentes.git`. Endereço: `scrapagentes.khoral.com.br`, com HTTPS válido. Só a API fica exposta; worker e banco não são acessíveis de fora. A pasta de mídia não é pública. Chave de API vem de variável de ambiente.

## 11. Fora de escopo

Classificação por IA, taxonomia, recoleta automática ou agendada, interface gráfica, vários usuários, scraping em massa de perfis ou hashtags, stories, qualquer login de conta pessoal (salvo decisão futura do Mateus).

## 12. Decisões deixadas para as etapas

| decisão | etapa |
|---|---|
| Proxy reverso, forma de rodar processos, caminhos de dados | 01 |
| Tamanho do modelo de transcrição e jobs paralelos | 01 e 04 |
| Biblioteca de coleta do Instagram e necessidade de proxy residencial | 03 |
| Limite aceito de erro de transcrição | 04 |
| Biblioteca pronta de frames ou implementação própria | 05 |
