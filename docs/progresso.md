# Progresso

Atualize ao fim de cada etapa, colando a saída dos comandos como evidência.

| etapa | nome | estado | evidência |
|---|---|---|---|
| 01 | Reconhecimento da VPS e esqueleto de deploy | concluída (2026-11-03) | ver "Evidências da etapa 01" |
| 02 | Base e contrato do adaptador | pendente | |
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
