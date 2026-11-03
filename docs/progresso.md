# Progresso

Atualize ao fim de cada etapa, colando a saída dos comandos como evidência.

| etapa | nome | estado | evidência |
|---|---|---|---|
| 01 | Reconhecimento da VPS e esqueleto de deploy | concluída (2026-11-03) | ver "Evidências da etapa 01" |
| 02 | Base e contrato do adaptador | concluída (2026-11-03) | ver "Evidências da etapa 02" |
| 03 | Adaptador Instagram | concluída (2026-11-03) | ver "Evidências da etapa 03" |
| 04 | Transcrição | concluída (2026-11-03) | ver "Evidências da etapa 04" |
| 05 | Frames e marcadores | concluída | folhas de contato aprovadas pelo Mateus |
| 06 | Pacote e busca | concluída | formato do pacote aprovado pelo Mateus |
| 07 | Fila e worker | concluída (2026-11-03) | ver "Evidências da etapa 07" |
| 08 | Métrica sob demanda | concluída (2026-11-03) | ver "Evidências da etapa 08" |
| 09 | Publicação e endurecimento | concluída, aguardando validação do Mateus (2026-11-03) | ver "Evidências da etapa 09" |
| 10 | Molde para novas redes | pendente | |

## Evidências da etapa 01
Detalhes e inventário completo em `docs/VPS.md`.

HTTPS de fora da VPS (PowerShell, com validação de certificado):
```
> Invoke-WebRequest -UseBasicParsing https://scrapagentes.khoral.com.br/saude
200 {"status":"ok"}
```
Certificado: `issuer=Let's Encrypt CN=YE1`, válido de 03/11/2026 a 01/02/2027.

Porta interna não responde pela internet:
```
$ curl http://194.163.134.245:8100/saude
HTTP 000  (sem resposta)
```

Reinício só do serviço mínimo:
```
$ systemctl --user restart scrapagentes-api; systemctl --user is-active scrapagentes-api
active
$ curl http://172.18.0.1:8100/saude
{"status":"ok"}
```

Portas depois (as mesmas de antes, mais `172.18.0.1:8100`): 22, 80, 81, 443, 5432, 631, 53, 4100, 51775. `agentes-trabalhador`, `docker`, `postgresql@16-main` e `fail2ban`: `active`.

GitHub: leitura (`git ls-remote`) ok com repositório vazio; escrita ok (push de branch temporária aceito). A `main` foi publicada com um commit vazio (`a434556`); o Mateus trocou a branch padrão para `main` e a temporária foi apagada:
```
$ curl https://api.github.com/repos/Pteusz/scrap-agentes | grep default_branch
"default_branch": "main",
$ git ls-remote --heads origin
a4345560fcfb7c244675a38eefc92ce5237e4c5a	refs/heads/main
```

Pendências herdadas para etapas futuras: `ffmpeg` não instalado (etapa 04, exige `sudo`); firewall local e do provedor não verificados (`sudo` exige senha); backup externo a definir (etapa 09); `.gitignore` com `.venv/` antes do primeiro commit real; `CLAUDE.md` e `docs/` estão no clone da VPS sem commit, aguardando confirmação do Mateus para o primeiro push.

## Evidências da etapa 02

Testes (VPS, `~/scrapagentes`, Python 3.12.3, um comando só):
```
$ .venv/bin/python -m pytest
................................                                         [100%]
36 passed, 1 warning in 4.95s
```
O aviso é de depreciação do `httpx` dentro do `starlette.testclient`; não afeta o resultado.

O que os testes cobrem: item criado e duas coletas de métrica sem sobrescrita (4 linhas, 2 `coletado_em`); reingestão da mesma rede+url sem duplicar item e com nova coleta; tags `Emagrecimento ` e `emagrecimento` viram a mesma tag no banco e na busca; 401 sem chave e `/saude` aberto; busca combinada nicho+subnicho+formato+período; busca por métrica usa a coleta mais recente; estrutura do pacote (foto, carrossel, vídeo); `manual` passa na suite de contrato (`scrapagentes/contrato.py`) e a suite reprova adaptadores que violam o contrato; erros tipados viram job com `erro`.

Validação ao vivo (API de desenvolvimento em `127.0.0.1:8200`, banco em `/tmp`, removido depois; fixtures geradas com ffmpeg):
```
GET  /saude                          -> {"status":"ok"}
GET  /itens  (sem chave)             -> 401
POST /itens  (multipart, vídeo)      -> {"job_id":1,"item_id":1}
GET  /jobs/1                         -> estado "concluido", nicho "saude" (normalizado), subnichos ["treino","dieta"]
POST /itens/1/coletas {curtidas:250} -> {"job_id":2,"item_id":1}
GET  /itens?nicho=saude&subnicho=TREINO&metrica=curtidas&min=200 -> total 1, curtidas 250.0 (última coleta)
GET  /itens/1/pacote                 -> contexto{rede,link,conta,nicho,subnichos,formato,data_publicacao,legenda,duracao_s:6.0}, metricas, texto [], imagens []
PATCH /itens/1/subnichos {adicionar:["Novo"]} -> ["dieta","novo","treino"]
GET  /docs                           -> 404 (docs só com SCRAPAGENTES_DOCS=1)
```
Serviço mínimo da etapa 01 intacto: `curl http://172.18.0.1:8100/saude` -> `{"status":"ok"}`; porta 8200 encerrada ao fim.

Revisão por subagente independente (veredito: cumprida no essencial). Corrigido após a revisão, com teste para cada item:
- chave de API não-ASCII dava 500; agora compara bytes e responde 401;
- tipos errados no JSON (`url`, `nicho`, `subnichos`) davam 500; agora 422;
- `coletado_em` podia coincidir entre conexões concorrentes; agora `BEGIN IMMEDIATE` antes de ler o último instante;
- mídia no disco não era atômica com o banco; agora grava em `midia/<id>.novo` e só renomeia após o commit, limpando em caso de falha;
- reingestão sem legenda apagava a legenda; agora preserva.
Registrado para depois: upload sem limite de tamanho e lido em memória (etapa 09); migração sem trava entre processos (importa com o worker, etapa 07); a rota usa `arquivos` (plural, para carrossel) onde o SPEC diz `arquivo`.

Decisões e observações:
- O `nicho` também é normalizado (minúsculas, sem acento), igual aos subnichos; a busca por nicho é por igualdade normalizada.
- Ingestão síncrona nesta etapa: a API cria o job, executa na hora e devolve 202 com `job_id` e `item_id`; falhas viram job `erro`. A fila e o worker chegam na etapa 07.
- `ffmpeg` vem do pacote `imageio-ffmpeg` no venv (sem `sudo`); `SCRAPAGENTES_FFMPEG` permite apontar outro binário.
- Dependências instaladas no venv da VPS (`~/scrapagentes/.venv`): `requirements-dev.txt`. Nenhuma alteração fora do home de `pteuz`.
- Sem segredos no repositório: a chave de API só vem de `SCRAPAGENTES_CHAVE_API`; os testes usam um valor fictício.
- Não feito (fora do escopo): Instagram, transcrição e frames reais, worker, publicação.

## Evidências da etapa 03
Viabilidade e decisões em `docs/viabilidade-instagram.md`; túnel do celular em `docs/tunel-celular.md`.

Testes offline (VPS, fonte gravada, sem rede):
```
$ .venv/bin/python -m pytest
64 passed, 1 warning
```
(36 da etapa 02 + 28 novos: reconhecimento e canonização de URL, classificação foto/vídeo/carrossel, métricas ausentes omitidas, suíte de contrato com 3 formatos e 5 erros tipados, limpeza da pasta temporária em sucesso e falha, limitador de intervalo, proxy inválido sem vazar credencial, proxy fora do ar -> `indisponivel` sem vazar credencial, ingestão pela API.)

Testes reais (`SCRAPAGENTES_TESTES_REAIS=1 .venv/bin/python -m pytest tests_reais -m real`):
```
8 passed, 6 warnings in 38.30s
```
foto, carrossel, 4 reels, reel com falha do servidor (erro tipado) e post inexistente (erro tipado).

Relatório do adaptador (`python -m scrapagentes.adaptadores.instagram <url>`), para o Mateus conferir:
| URL | formato | conta | data (UTC) | curtidas | comentários | duração | mídia |
|---|---|---|---|---|---|---|---|
| /p/DfSJbEzDXf5/ | foto | rockstargames | 2026-11-03 14:56 | 1.026.938 | 9.341 | — | 1 jpg |
| /reel/DczJptKyQtf/ | video | nelson.miranda.prof | 2026-09-02 21:06 | 17.099 | 130 | 77,11 s | 1 mp4 (16 MB) |
| /p/Cyn3G8FLV1v/ | carrossel | mateus.maverick | 2023-10-20 13:47 | 4 | 0 | — | 4 jpg |

Erros e proxy:
```
reel DfSLSZpjl_4 (falha do servidor) -> ERRO indisponivel: o Instagram não devolveu os dados do post (...)
SCRAPAGENTES_PROXY=socks5h://127.0.0.1:1080 (túnel) + carrossel -> formato carrossel, 4 arquivos
SCRAPAGENTES_PROXY=socks5h://127.0.0.1:9 (fora do ar) -> ERRO indisponivel: falha de conexão com o Instagram (via proxy configurado)
```

Decisões e observações:
- Fonte: Instaloader 4.16 anônimo (`instaloader>=4.16` e `pysocks` em `requirements.txt`). Sem login, sem cookies, sem proxy por padrão.
- `Resolvido` ganhou `pasta_temporaria` (interno, não muda o SPEC): o adaptador baixa para uma pasta temporária e o núcleo a apaga depois de copiar, também em caso de erro.
- `visualizacoes` normalmente não vem em reels anônimos e fica ausente; a duração vem do `ffmpeg`.
- Carrossel com vídeo em algum slide -> `formato_nao_suportado` (fora do escopo desta etapa).
- Reingestão de um item existente baixa a mídia de novo (otimização para etapa futura).
- Intervalo mínimo de 5 s entre consultas (`SCRAPAGENTES_IG_INTERVALO_S`).
- Risco: o `doc_id` do Instagram muda de tempos em tempos; sintoma é `indisponivel` em tudo; saída é atualizar o Instaloader.
- Conferência dos números pelo Mateus: tudo bate. Túnel `autossh` validado. Sem revisão por subagente nesta etapa (não solicitada). Push aguarda confirmação do Mateus.

## Evidências da etapa 04
Módulo `scrapagentes/transcricao.py`: ffmpeg -> WAV 16 kHz mono; faster-whisper 1.2.1 em CPU, int8, VAD ligado, idioma `pt` fixo, temperatura 0; trechos normalizados (ordem, sem sobreposição, sem passar da duração); trava de um trabalho por vez (thread + `flock` entre processos). Comando: `python -m scrapagentes.transcricao <arquivo> [--modelo small] [--referencia texto.txt]`.

Testes (VPS):
```
$ .venv/bin/python -m pytest
71 passed
$ SCRAPAGENTES_TESTES_REAIS=1 .venv/bin/python -m pytest tests_reais/test_transcricao_real.py -m real
fala em português (WER < 30%, trechos ordenados), determinismo (duas execuções idênticas): passed
vídeo sem fala -> lista vazia, sem erro: passed
```
A trava foi testada com 4 threads (no máximo 1 ativa) e entre dois processos (o segundo esperou o primeiro soltar).

Medição na VPS (4 vCPUs, `fala_pt.mp4`, 67,9 s, referência feita à mão; cache de modelo quente):
| modelo | WER | tempo | tempo / duração | pico de RAM |
|---|---|---|---|---|
| `base` | 11,8% | 39,6 s | 0,58x | 397 MB |
| `small` | **6,4%** | 122,5 s | 1,80x | 732 MB |

O tempo do `small` variou entre execuções (88,6 s e 122,5 s) porque a VPS é compartilhada. O WER ignora maiúsculas e pontuação; acentos e algarismos contam como erro (por exemplo "20" contra "vinte").
Erros típicos: `base` troca "planeja" por "planejo", "a ponta só para" por "aponta só pro", "atacar a sistema"; `small` escreve "corrigido" por "corrigir" e "a cada sistema" por "atacar sistema".

**Recomendação: `small`** (metade do erro do `base`, 1,8x o tempo real, 732 MB de RAM, cabe no limite de um job por vez). `base` é a saída se o tempo pesar mais que a precisão.

Decisões e observações:
- O `faster-whisper` 1.2.1 não funciona com o PyAV 19 (erro `metadata_errors`). Contorno: o áudio já extraído com o ffmpeg é lido do WAV e passado como array ao modelo, sem usar o decodificador do `faster-whisper`.
- `tests/fixtures/` está no `.gitignore`: `fala_pt.mp4` e `fala_pt.txt` não são versionados; os testes reais os pulam se não existirem. Se quiser versioná-los, é só mudar o `.gitignore`.
- Modelos baixados ficam no cache do usuário `pteuz` (`~/.cache/huggingface`), fora do repositório.
- Aprovado pelo Mateus: modelo `small`, limite de WER de 10% (medido 6,4% na fixture). Sem revisão por subagente nesta etapa (não solicitada).

## Evidências da etapa 05
Módulo `scrapagentes/frames.py` (decisão sobre bibliotecas em `docs/decisoes.md`). Comando: `python -m scrapagentes.frames <video> [--saida pasta] [--folha folha.jpg]`. Pillow só é usado na folha de contato.

Testes (VPS):
```
$ .venv/bin/python -m pytest
82 passed   (11 novos em tests/test_frames.py)
```
Cobertos com vídeos sintéticos do ffmpeg: 30 s com 6 cenas de cor (todas as cenas têm frame, segundos sem repetição); 30 s estático (amostragem uniforme, 2+ por terço); começo preto (nenhum frame preto escolhido); 60 cenas curtas (teto 16, 2+ por terço); marcadores nas bordas (d/3 e 2d/3); determinismo; vídeo de 1,5 s; erros claros.

Primeira medição com um vídeo real (`fala_pt.mp4`, 67,9 s, pessoa falando com cortes para telas de slides e de repositório):
```
16 frames, tempo=11.1s, duracao=67.9s, tempo/duracao=0.16x
 1 0.00s comeco | 2 9.50s comeco | 3 12.75s comeco | 4 16.75s comeco | 5 23.00s meio | ... | 11 45.25s meio
12 52.00s fim | 13 56.75s fim | 14 60.25s fim | 15 63.75s fim | 16 67.50s fim
```
Reels do Mateus (`Dd4DyYzgCvf`, 125,6 s: 16 frames, 16,7 s, 0,13x; `DcrYj5FDSUC`, 8,6 s: 10 frames, 4,5 s, 0,52x). Ajuste aprovado por ele após a primeira folha: o preenchimento uniforme e a cobertura por terço preferem frames diferentes dos já escolhidos (repetidos só se não houver outro). No vídeo curto o final parado caiu de 4 para 2 frames; sobraram 2 por exigência do mínimo por terço, e a fusão entre cenas aparece em 4 frames. Suíte: 82 passed.

Aprovado pelo Mateus: folhas de contato dos 2 reels (a do `fala_pt.mp4` também foi mostrada). Sem revisão por subagente (não solicitada).

## Evidências da etapa 06
Já existiam da etapa 02: montagem do pacote, rota de imagem autenticada e busca com todos os filtros (testes em `tests/test_api.py`). Nesta etapa entrou a parte que faltava: a ingestão de vídeo passa por transcrição (etapa 04) e frames (etapa 05) antes de gravar (`servico._processar_video`). Trabalho pesado roda antes da transação de escrita; a pasta de processamento é apagada sempre. Vídeo sem faixa de áudio fica com `texto = []`; falha nos frames vira job com `erro`, sem item nem pasta órfã. Reprocessar refaz texto e imagens. A ingestão continua síncrona (worker na etapa 07): um vídeo de 68 s leva cerca de 100 s na VPS com o modelo `small`.

Testes (VPS):
```
$ .venv/bin/python -m pytest
89 passed   (7 novos em tests/test_pacote_video.py; o conftest troca a transcrição por um stub nos testes offline)
```
Cobertos em `test_pacote_video.py`: vídeo com fala simulada e frames reais (campos exatos do SPEC, imagens em ordem de tempo, marcador coerente com o segundo, JPEG servido pela rota); `fala_proxima` em caso construído (entre trechos, dentro de um trecho, depois do fim, sem fala); busca por texto falado; vídeo sem áudio; reprocessar; falha nos frames; métrica mais recente no pacote e na busca. Foto, carrossel, filtros combinados, paginação e subnicho com grafia diferente já eram cobertos em `test_api.py`.

Pacote real impresso com `python -m scrapagentes.mostrar_pacote tests/fixtures/fala_pt.mp4` (transcrição de verdade, 22 trechos, 16 imagens de 0,00 s a 67,50 s; marcadores comeco/meio/fim coerentes; busca combinada `nicho + subnichos + formato + curtidas>=100 + q=hackers` devolveu o item). A saída completa foi mostrada ao Mateus no chat.

Aprovado pelo Mateus: formato do pacote do vídeo real. Revisão por subagente (prevista na entrega) não feita, como nas etapas 03 a 05; fica para quando ele pedir.

## Evidências da etapa 07
Implementado: `POST /itens` e `POST /itens/{id}/coletas` só validam e enfileiram (202); o worker `python -m scrapagentes.trabalhador` consome a tabela `job` (ver `docs/decisoes.md`, etapa 07). Observação: para item novo a resposta traz `item_id: null` até o worker criá-lo.

Testes (VPS):
```
$ .venv/bin/python -m pytest
102 passed   (13 novos em tests/test_fila.py; os demais testes passaram a drenar a fila)
```
`test_fila.py` cobre: ciclo API -> worker; falha forçada com 3 tentativas registradas enquanto os outros jobs seguem; retentativa que funciona; erro definitivo sem retentativa; queda antes do commit e depois do commit (antes da troca da mídia) sem duplicar; job que derruba o worker esgota as tentativas; limpeza de `processamento-*`; dois jobs de vídeo em sequência (trava); reingestão enfileirada duas vezes; reprocessar; item sem pasta de mídia; coleta pela fila.

Ponta a ponta real na VPS (API na porta 8200 e worker em processos separados, dados em `/tmp/sa-e2e`, tudo removido depois). Três URLs enfileiradas com o worker parado (`pendente`, tentativas 0), depois worker ligado:
```
job 1 reel  /p/Dd4DyYzgCvf/ (canonizada)  concluido, tentativas 1, erro null  125,6 s de vídeo, 31 trechos, 16 frames (0,0..125,25 s; comeco 5 / meio 5 / fim 6)  curtidas 7809, comentarios 8556  ~189 s
job 2 foto  /p/DfSJbEzDXf5/               concluido, tentativas 1  1 imagem  curtidas 1.151.678  0,8 s
job 3 carrossel /p/Cyn3G8FLV1v/           concluido, tentativas 1  4 imagens  curtidas 4  5,1 s
total 3 jobs: ~190 s (20:49:35 -> 20:52:51 UTC)
itens 3 | imagens por item [(1,16),(2,1),(3,4)] | coletas por item [(1,1),(2,1),(3,1)]
```
Queda real (`kill -9` no worker, 45 s dentro do job de vídeo; o mesmo reel reenviado com `reprocessar=true`):
```
depois do kill -9:  job 4 estado=executando tentativas=1; sobra dados/processamento-*; banco igual ao de antes
worker reiniciado:  "recuperação: 1 job(s) voltaram à fila, 0 esgotaram as tentativas"
                    job 4 (ingestao) tentativa 2 -> concluido em 185,3 s
job 4: concluido, tentativas 2, erro "tentativa 1/3: processo interrompido"
depois:  itens 3 | imagens por item [(1,16),(2,1),(3,4)] | coletas por item [(1,2),(2,1),(3,1)] | subnichos 3
         sem processamento-* e sem midia/*.novo
```
Nenhum item, imagem ou subnicho duplicado; a única linha nova é a coleta (métrica) da segunda ingestão, que é o comportamento previsto (métrica nunca sobrescreve).

Recursos na VPS (`vmstat -n 2` da máquina inteira, que também roda outros serviços), durante o job de vídeo com `small`: CPU ocupada no pico 76% (usuário ~56-66%, cerca de 2,5 dos 4 vCPU), contra ~32% de base; memória livre entre 3,5 e 4,4 GB (base ~3,75 GB; queda de 0,25 a 0,5 GB), sem uso de swap; load average 2,93 no fim. Foto e carrossel são desprezíveis (menos de 6 s). Pico de RSS por processo não foi capturado.

Pendente do Mateus: conferir os três pacotes (vídeo, foto, carrossel) e decidir sobre `item_id: null`. A unidade systemd `scrapagentes-worker` (--user) não foi criada: mexer na VPS exige a confirmação dele. Revisão por subagente não feita (não solicitada).

## Evidências da etapa 08
A rota `POST /itens/{id}/coletas`, o tipo de job `coleta` e a gravação de um `coletado_em` por coleta já existiam desde as etapas 02 e 07. Nesta etapa entraram os testes que faltavam (`tests/test_coleta.py`, 7 novos) e a validação real. Nenhum código de produção mudou.

Testes (VPS):
```
$ .venv/bin/python -m pytest
109 passed   (7 novos em tests/test_coleta.py)
```
Cobertos: rodar o worker sem job pendente não coleta nada; todas as linhas de uma coleta compartilham o mesmo `coletado_em` (3 coletas = 3 datas, 2 linhas cada); falha do adaptador (`bloqueado` e `nao_encontrado`) deixa o job em `erro` com código e mensagem e as coletas anteriores e o pacote intactos; item de rede sem adaptador devolve 422 com mensagem clara e não cria job; adaptador removido depois de enfileirar vira job `erro`; varredura do código de produção sem agendador, cron, `Timer`, `asyncio.sleep`, `add_job` e afins, e `enfileirar_coleta` só referenciada em `api.py` e `servico.py`. As duas coletas seguidas, a métrica mais recente no pacote e na busca e a coleta sem métrica já eram cobertas em `test_api.py`, `test_pacote_video.py` e `test_fila.py`.

Validação real (foto `DfSJbEzDXf5`, API na porta 8201 e worker `--uma-vez`, dados em `/tmp/sa-c8`, removidos depois). Ingestão e duas chamadas de `POST /itens/1/coletas`, todos os jobs `concluido`, tentativas 1:
```
coletado_em                         comentarios   curtidas
2026-11-03T21:05:29.146738+00:00    9910          1166725     (ingestão)
2026-11-03T21:05:36.622944+00:00    9910          1166862     (coleta 1)
2026-11-03T21:05:48.099835+00:00    9911          1167102     (coleta 2)
pacote: coletado_em 2026-11-03T21:05:48.099835+00:00, curtidas 1167102, comentarios 9911
```
Três conjuntos preservados, com datas distintas e valores que de fato mudaram; o pacote usa o mais recente.

Recoleta automática: não existe. O teste de varredura acima passa e o worker só consome jobs criados pela rota ou pela ingestão. Revisão por subagente não feita (não solicitada), como nas etapas anteriores.

## Evidências da etapa 09
Produção em `https://scrapagentes.khoral.com.br` (Nginx Proxy Manager -> `172.18.0.1:8100`). API e worker são unidades `systemd --user` (Linger ligado) com `Restart=always`; backup diário por timer (03:30). Operação em `docs/VPS.md`, seção 5.

Testes de fora da VPS (máquina do Mateus, `curl.exe` do Windows, verificação TLS ligada):
```
/saude                       -> {"status":"ok"} [200]
/itens sem chave             -> 401
/itens chave errada          -> 401
/itens chave certa           -> {"total":0,...} [200]
/docs, /openapi.json, /redoc -> 404, 404, 404
POST /itens com 3 MiB pelo proxy -> 422 (a app respondeu; o NPM não barrou)
porta 8100 no IP público     -> inacessível
certificado                  -> Let's Encrypt, CN scrapagentes.khoral.com.br, 2026-11-03 a 2027-02-01
http://.../saude (porta 80)  -> 200 (sem redirecionamento para https)
```
Reinício: `kill -9` nos dois processos -> ambos `active` em até 15 s com PIDs novos (1268039/1268047 -> 1268737/1268748); `/saude` 200; `systemctl --user restart` também volta; as 3 unidades `enabled`; `Linger=yes`.

Ponta a ponta no domínio (nicho `teste-producao`, subnicho `e2e`): `POST /itens` x3 -> jobs 1, 2, 3 (202) -> `GET /jobs/N` até `concluido` (vídeo transcrito levou cerca de 3 min; os outros esperaram na fila, um job pesado por vez) -> `GET /itens?nicho=teste-producao&subnicho=e2e` devolveu `total 3` (vídeo @odanilogato, foto @rockstargames, carrossel @mateus.maverick) -> `GET /itens/N/pacote`: vídeo 16 imagens (frames), foto 1, carrossel 4, 2 métricas cada, texto presente; `GET /itens/1/imagens/1` -> 200, 105313 B. Os 3 itens ficaram no banco de produção.

Backup e restauração (na VPS, banco com os 3 itens):
```
backup criado: /home/pteuz/scrapagentes-backups/backup-20261103-222034
{'itens': 3, 'imagens': 21, 'metricas': 6, 'com_legenda': 3, 'arquivos_de_midia': 22}
```
A verificação copia o backup para pasta temporária, abre o banco (`integrity_check` ok) e conta as linhas. O serviço do timer também rodou (status=0/SUCCESS); próximo disparo em 2026-11-04 03:30.

Comparação com o inventário da etapa 01: portas antes 22, 53, 80, 81, 443, 631, 5432, 172.18.0.1:4100, 127.0.0.1:51775; agora as mesmas mais `172.18.0.1:8100` e `127.0.0.1:1080` (esta é a ponta do túnel do celular da etapa 03, não é desta etapa). `docker` e `fail2ban` `active`, processo `agentes-trabalhador` presente, os dois crons (`/opt/streamscrap` 06:00 e o `@reboot` do painel) intactos, NPM e PostgreSQL não tocados.

Limites (`scrapagentes/limites.py`, testes em `tests/test_producao.py`): corpo máximo 200 MiB (413), prazo de 300 s para receber o corpo (408), 120 requisições/min por chave (429 com `Retry-After`; chaves erradas dividem um balde, o que freia adivinhação; `/saude` livre), keep-alive de 10 s no uvicorn. A chave nunca é guardada nem registrada.

## Insumos que dependem do Mateus
| insumo | etapa | estado |
|---|---|---|
| Confirmação para alterar a VPS (instalar, abrir porta, mexer em proxy ou firewall) | 01 | feito (alterações no home de `pteuz`; proxy cadastrado pelo Mateus) |
| Registro DNS de `scrapagentes.khoral.com.br` apontando para a VPS | 01 | feito |
| Confirmar que `https://github.com/Pteusz/scrap-agentes.git` é o destino do projeto, qual é a branch padrão e se o repositório já tem conteúdo | 01 | feito (destino confirmado, padrão `main`, estava vazio) |
| Confirmação antes do primeiro push ao GitHub | 01 | teste de escrita feito; **push do conteúdo real ainda pendente** |
| 3 URLs públicas do Instagram: um vídeo, uma foto, um carrossel | 03 | recebidas em 2026-11-03 (abaixo, sem parâmetros de rastreio) |
| Decisão sobre proxy residencial | 03 | resolvido: não é necessário agora; túnel do celular pronto como reserva (`docs/tunel-celular.md`) |
| Trocar o túnel manual do Termux por `autossh` e desligar a otimização de bateria do Termux | 03 | feito (`~/bin/tunel.sh`; teste pelo túnel devolveu o IP do celular e o adaptador resolveu o carrossel) |
| Conferir os números do relatório do adaptador contra o Instagram | 03 | feito (Mateus confirmou que batem) |
| Trecho de vídeo em português de 30 a 60 s e a transcrição correta feita à mão | 04 | recebido (reel `DfQdA_OS8m2`, 67,9 s; ligeiramente acima de 60 s) |
| Limite aceito de erro de transcrição (WER) e aprovação do modelo | 04 | feito: modelo `small`, WER até 10% (medido: 6,4%) |
| 2 vídeos reais de tipos diferentes (ex.: pessoa falando para a câmera e cortes rápidos) e aprovação da folha de contato | 05 | feito: reels `Dd4DyYzgCvf` e `DcrYj5FDSUC`; folhas aprovadas |
| Aprovação do formato do pacote de um vídeo real | 06 | feito (pacote do `fala_pt.mp4`) |
| Conferir os 3 pacotes reais (vídeo, foto, carrossel) da etapa 07 | 07 | a conferir |
| Aprovar a criação da unidade systemd `scrapagentes-worker` (--user) na VPS | 07/09 | feito (aprovado; instalada na etapa 09) |
| Chave de API de produção | 09 | feito: arquivo `~/.config/scrapagentes/ambiente` (600) criado na VPS a pedido dele; ler com `ssh vps2 'grep CHAVE ~/.config/scrapagentes/ambiente'` |
| Validar o ponta a ponta no domínio (3 posts reais) | 09 | a validar |
| Decidir se `POST /itens` deve devolver `item_id` para itens novos (hoje `null`) | 07 | em aberto |
| Destino da cópia externa do backup (hoje só na própria VPS) | 09 | em aberto |

## URLs de teste do Instagram (etapa 03)
Recebidas do Mateus em 2026-11-03; guardadas sem `utm_source`, `rpxt` e `srtk` (parâmetros de rastreio de compartilhamento, que não identificam o post).
| formato | URL |
|---|---|
| foto (feed) | https://www.instagram.com/p/DfSJbEzDXf5/ |
| vídeo (reel; falha no servidor do Instagram, serve de caso de erro) | https://www.instagram.com/reel/DfSLSZpjl_4/ |
| reels extras que funcionam | `DczJptKyQtf`, `De2QnoYB5Xe`, `Db8eACCzSvD`, `De0R33YN7r2` |
| carrossel | https://www.instagram.com/p/Cyn3G8FLV1v/ |
