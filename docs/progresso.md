# Progresso

Atualize ao fim de cada etapa, colando a saída dos comandos como evidência.

| etapa | nome | estado | evidência |
|---|---|---|---|
| 01 | Reconhecimento da VPS e esqueleto de deploy | concluída (2026-11-03) | ver "Evidências da etapa 01" |
| 02 | Base e contrato do adaptador | concluída (2026-11-03) | ver "Evidências da etapa 02" |
| 03 | Adaptador Instagram | pendente | |
| 04 | Transcrição | pendente | |
| 05 | Frames e marcadores | pendente | |
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

## Insumos que dependem do Mateus
| insumo | etapa | estado |
|---|---|---|
| Confirmação para alterar a VPS (instalar, abrir porta, mexer em proxy ou firewall) | 01 | feito (alterações no home de `pteuz`; proxy cadastrado pelo Mateus) |
| Registro DNS de `scrapagentes.khoral.com.br` apontando para a VPS | 01 | feito |
| Confirmar que `https://github.com/Pteusz/scrap-agentes.git` é o destino do projeto, qual é a branch padrão e se o repositório já tem conteúdo | 01 | feito (destino confirmado, padrão `main`, estava vazio) |
| Confirmação antes do primeiro push ao GitHub | 01 | teste de escrita feito; **push do conteúdo real ainda pendente** |
| 3 URLs públicas do Instagram: um vídeo, uma foto, um carrossel | 03 | pendente |
| Decisão sobre proxy residencial (provedor e credenciais por variável de ambiente) | 03 | pendente |
| Trecho de vídeo em português de 30 a 60 s e a transcrição correta feita à mão | 04 | pendente |
| Limite aceito de erro de transcrição | 04 | pendente |
| Chave de API de produção definida por ele | 09 | pendente |
