# Progresso

Atualize ao fim de cada etapa, colando a saída dos comandos como evidência.

| etapa | nome | estado | evidência |
|---|---|---|---|
| 01 | Reconhecimento da VPS e esqueleto de deploy | concluída (2026-11-03) | ver "Evidências da etapa 01" |
| 02 | Base e contrato do adaptador | concluída (2026-11-03) | ver "Evidências da etapa 02" |
| 03 | Adaptador Instagram | concluída (2026-11-03) | ver "Evidências da etapa 03" |
| 04 | Transcrição | concluída (2026-11-03) | ver "Evidências da etapa 04" |
| 05 | Frames e marcadores | concluída | folhas de contato aprovadas pelo Mateus |
| 06 | Pacote e busca | pendente | |
| 07 | Fila e worker | pendente | |
| 08 | Métrica sob demanda | pendente | |
| 09 | Publicação e endurecimento | pendente | |
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
| Chave de API de produção definida por ele | 09 | pendente |

## URLs de teste do Instagram (etapa 03)
Recebidas do Mateus em 2026-11-03; guardadas sem `utm_source`, `rpxt` e `srtk` (parâmetros de rastreio de compartilhamento, que não identificam o post).
| formato | URL |
|---|---|
| foto (feed) | https://www.instagram.com/p/DfSJbEzDXf5/ |
| vídeo (reel; falha no servidor do Instagram, serve de caso de erro) | https://www.instagram.com/reel/DfSLSZpjl_4/ |
| reels extras que funcionam | `DczJptKyQtf`, `De2QnoYB5Xe`, `Db8eACCzSvD`, `De0R33YN7r2` |
| carrossel | https://www.instagram.com/p/Cyn3G8FLV1v/ |
