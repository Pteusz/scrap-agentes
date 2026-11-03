# VPS — inventário e decisões de deploy

Etapa 01, Fase A (somente leitura). Coletado em 2026-11-03 na `vps2` (194.163.134.245), via `ssh vps2`. Nada foi alterado.

## 1. Inventário

| # | item | comando | resultado |
|---|---|---|---|
| 1 | Sistema | `cat /etc/os-release; uname -r` | Ubuntu 24.04.3 LTS, kernel 6.8.0-147-generic |
| 1 | Usuário e sudo | `id; sudo -n true` | `pteuz` (uid 1000, grupos `sudo`, `users`). `sudo` **exige senha**, então não rodo comandos privilegiados sozinho. Não está no grupo `docker` |
| 1 | Hora | `timedatectl` | Europe/Berlin (CET), relógio sincronizado, NTP ativo |
| 1 | Locale | `locale` | `C.UTF-8` (UTF-8 ok) |
| 2 | CPU | `nproc; lscpu` | 4 vCPUs, AMD EPYC |
| 2 | RAM / swap | `free -h` | 7,8 GiB total, ~6,4 GiB disponíveis; swap 4 GiB sem uso |
| 2 | Disco | `df -h` | `/` 145 GB, 91 GB livres (38% usado) |
| 2 | GPU | `lspci` | nenhuma (apenas VGA virtual) |
| 2 | Limites | `ulimit -n -u` | arquivos abertos 1024; processos 31611 |
| 3 | Python | `python3 --version` | 3.12.3; `venv` ok; pip 24.0 |
| 3 | ffmpeg / ffprobe | `ffmpeg -version` | **não instalado** |
| 3 | sqlite3 (CLI) | `sqlite3 --version` | não instalado (não é necessário) |
| 3 | FTS5 no Python | `sqlite3` do Python, `create virtual table ... using fts5` | **ok**, SQLite 3.45.1 |
| 3 | Docker / Compose | `docker --version` | Docker 29.2.0, Compose v5.0.2. `pteuz` **sem permissão** no socket |
| 3 | git / curl | `git --version` | git 2.43.0, curl 8.5.0 |
| 4 | Serviços ativos | `systemctl list-units --type=service --state=running` | ssh, docker, postgresql@16, fail2ban, cron, `agentes-trabalhador`, lightdm, x2goserver, cups, snapd, entre outros do sistema |
| 4 | Contêineres | `docker ps` | sem permissão. Pelo `ps`, há `nginx-proxy-manager` (ver item 5) |
| 4 | Portas em escuta | `ss -tlnp` | 22 (ssh); **80, 81, 443** em 0.0.0.0/:: (docker-proxy → Nginx Proxy Manager); 5432 (PostgreSQL, só 127.0.0.1); 631 (cups, local); 53 (resolved, local); 172.18.0.1:4100 e 127.0.0.1:51775 (processo `beam.smp`, de outro serviço) |
| 4 | Cron | `crontab -l; ls /etc/cron.d` | 06:00 diário: `/opt/streamscrap` (`main.py top`); `@reboot`: `/opt/modular-agentes/scripts/painel.sh`; `e2scrub_all`, `staticroute`, `sysstat` |
| 4 | Timers | `systemctl list-timers` | rotina padrão do Ubuntu (apt, logrotate, sysstat, fwupd etc.) |
| 4 | Pastas em `/opt` | `ls /opt` | agentes, modular-agentes (+data, +cliente-exemplo), nginx-proxy-manager, scraper, streaming, streamscrap, containerd |
| 5 | Proxy reverso | `ps`; `/opt/nginx-proxy-manager/docker-compose.yml` | **Nginx Proxy Manager** (`jc21/nginx-proxy-manager`), contêiner `nginx-proxy-manager`, portas 80/81/443, rede Docker externa `web` (gateway 172.18.0.1). Dados em `/opt/nginx-proxy-manager/data`, certificados em `/opt/nginx-proxy-manager/letsencrypt` (Let's Encrypt pelo próprio NPM). Painel na porta 81 (responde 200 local, servidor openresty) |
| 6 | Firewall local | `sudo -n ufw status` | **desconhecido**: exige senha de sudo. Há `fail2ban` ativo e config de logrotate do `ufw`, indício de ufw. Falta: Mateus rodar `sudo ufw status verbose` |
| 6 | Firewall do provedor | — | desconhecido (só pelo painel do provedor) |
| 7 | IP público | `curl https://ifconfig.me` | 194.163.134.245 |
| 7 | DNS do domínio | `getent hosts scrapagentes.khoral.com.br` | **194.163.134.245** (aponta para esta VPS) |
| 8 | Saída HTTPS | `curl -w %{http_code}` | example.com 200; www.instagram.com 200. Sem variável de proxy no ambiente |
| 9 | Subida após reinício | `systemctl` / `crontab` | serviços em systemd; NPM com `restart: unless-stopped` |
| 9 | Logs | `ls /etc/logrotate.d` | journald + rsyslog; logrotate presente (para serviços próprios é preciso criar regra) |
| 9 | Backup | `ls /etc/cron.daily`, crontab | **não há rotina de backup** visível |
| 11 | git | `git --version; git config --global` | 2.43.0; `user.name=Pteusz`, `user.email=mateusmaverick20@gmail.com` |
| 11 | Autenticação GitHub | `ssh -T git@github.com`; `~/.ssh/config` | chave SSH dedicada `~/.ssh/id_ed25519_github` (`IdentitiesOnly yes`). GitHub responde "Hi Pteusz!" |
| 11 | Leitura do repositório | `git ls-remote git@github.com:Pteusz/scrap-agentes.git` | acesso ok, **sem referências**: o repositório está **vazio** (sem branch nem commits) |
| 11 | Escrita | `git push` de branch temporária (Fase B) | **ok**: push aceito. A branch temporária foi apagada do remoto depois que o Mateus trocou a branch padrão para `main` (o GitHub não apaga a padrão) |

### Estimativa de capacidade para transcrição (item 10, **estimativa**, não medida)
4 vCPUs e ~6 GiB livres, compartilhados com PostgreSQL, Docker e o `agentes-trabalhador`. Em CPU com int8, o modelo `small` do faster-whisper é realista (~2 GB de RAM, de 1x a 2x o tempo real em 4 vCPUs). O `medium` é possível (~5 GB), mas disputa memória com o restante. **Um** job pesado por vez. Teste real na etapa 04 para fixar o modelo.

## 2. Decisões de deploy

| decisão | escolha | justificativa |
|---|---|---|
| Proxy reverso | **Reaproveitar o Nginx Proxy Manager** | Já ocupa 80/443 e emite os certificados. Subir outro proxy colidiria nas portas. Basta cadastrar um Proxy Host |
| Porta interna da API | **8100**, ligada ao gateway da rede Docker `web`, `172.18.0.1:8100` | O NPM é um contêiner e não alcança `127.0.0.1` do host. O gateway `172.18.0.1` já é usado por outro serviço (porta 4100). Ligar só nele mantém a porta fora da internet. 8100 está livre |
| Upstream no NPM | `http://172.18.0.1:8100` | idem |
| Processos | **systemd --user** (`scrapagentes-api` já existe como serviço mínimo; `scrapagentes-worker` será criado na etapa 07) | A VPS já roda o `agentes-trabalhador` em systemd. `pteuz` não está no grupo `docker`, e Compose não traz ganho para dois processos Python |
| Usuário dos serviços | `pteuz`, ou usuário dedicado se o Mateus preferir | Evita root. Dedicado é mais limpo, mas exige `sudo useradd` |
| Código | **Decidido: `/home/pteuz/scrapagentes`** (sem sudo; `/opt` é de root) | Evita depender de `sudo`. Serviços rodam como `pteuz` em `systemd --user` |
| Dados | **Decidido: `/home/pteuz/scrapagentes-data/`** (banco e frames) | Fora do repositório; pasta de mídia não pública |
| Logs | journald (`journalctl -u scrapagentes-*`) | Já tem rotação própria |
| Backup | cópia diária do banco SQLite (`.backup`) para a pasta de dados, mantendo 7 dias; cópia externa fica para decidir na etapa 09 | Não existe rotina hoje |
| Fluxo de código | clone em `git@github.com:Pteusz/scrap-agentes.git`; atualização por `git pull` manual e `systemctl restart` | Simples e auditável |
| Transcrição | `small`, int8, 1 job pesado por vez | ver estimativa acima |
| Porta 81 do NPM | painel público em `http://194.163.134.245:81` (se o firewall permitir) | só para o cadastro do domínio |

## 3. Riscos e bloqueios

| risco | o que o Mateus precisa fazer |
|---|---|
| `sudo` pede senha; nada que exija root roda sem ele | Rodar os comandos privilegiados que eu listar, ou criar `/opt/scrapagentes` com `chown pteuz` |
| `ffmpeg` não está instalado | Autorizar `sudo apt install ffmpeg` (também feito por ele, por causa do sudo). Necessário só a partir da etapa 04 |
| Firewall local e do provedor desconhecidos | Rodar `sudo ufw status verbose` e colar a saída. Não é preciso abrir porta nova: o tráfego entra por 443 |
| Cadastro do domínio no NPM ainda não feito | Criar o Proxy Host `scrapagentes.khoral.com.br` → `http://172.18.0.1:8100`, com SSL Let's Encrypt (link do painel acima). Passo a passo no momento certo |
| Recursos compartilhados com outros serviços (PostgreSQL, agentes) | Nenhuma ação; manter um job pesado por vez |
| Sem backup na VPS | Definir destino do backup externo até a etapa 09 |
| Repositório vazio | Nenhuma ação; a primeira publicação será o conteúdo de `CLAUDE.md` e `docs/` |

## 4. Fase B — o que foi feito (2026-11-03)

### Estado do repositório
- Remoto: `git@github.com:Pteusz/scrap-agentes.git`. Branch padrão: `main` (trocada pelo Mateus).
- Estava vazio. Último commit: `a434556 teste de escrita (temporario)` (commit vazio, criado no teste de escrita e hoje na `main`).
- Clone na VPS: `/home/pteuz/scrapagentes`. Existe regra de proteção para `main` no GitHub; o push da `main` vazia passou, e pode bloquear pushes diretos depois.
- `CLAUDE.md` e `docs/` foram copiados para o clone **sem commit nem push**. O primeiro push do conteúdo real exige confirmação do Mateus.

### Alterações na VPS (todas no home de `pteuz`, sem `sudo`)
| alteração | caminho |
|---|---|
| Clone do repositório | `/home/pteuz/scrapagentes` |
| Pasta de dados (vazia) | `/home/pteuz/scrapagentes-data` |
| venv com `fastapi` e `uvicorn` | `/home/pteuz/scrapagentes/.venv` |
| Serviço mínimo (só `/saude`) | `/home/pteuz/scrapagentes/servico_minimo/app.py` |
| Unidade `systemd --user` | `/home/pteuz/.config/systemd/user/scrapagentes-api.service` (`172.18.0.1:8100`, `Restart=on-failure`) |
| Proxy Host no NPM (feito pelo Mateus) | `scrapagentes.khoral.com.br` → `http://172.18.0.1:8100`, SSL Let's Encrypt |

### Comandos
```bash
ssh vps2 "systemctl --user start scrapagentes-api"      # subir
ssh vps2 "systemctl --user stop scrapagentes-api"       # parar
ssh vps2 "systemctl --user restart scrapagentes-api"    # reiniciar
ssh vps2 "systemctl --user status scrapagentes-api"     # estado
ssh vps2 "journalctl --user -u scrapagentes-api -n 50 --no-pager"   # logs
ssh vps2 "cd ~/scrapagentes && git pull"                # atualizar código
```
O serviço sobe sozinho após reinício da VPS porque o usuário tem `linger=yes`.

### Reversão (desfaz só o que foi criado aqui)
```bash
ssh vps2 "systemctl --user disable --now scrapagentes-api && rm ~/.config/systemd/user/scrapagentes-api.service && systemctl --user daemon-reload"
ssh vps2 "rm -rf ~/scrapagentes ~/scrapagentes-data"
```
No painel do NPM (`http://194.163.134.245:81`): apagar o Proxy Host `scrapagentes.khoral.com.br` e, se quiser, o certificado. No GitHub: a `main` com o commit vazio pode ser mantida.

### Comparação antes e depois
Portas em escuta antes: 22, 53, 80, 81, 443, 631, 5432, 4100 (172.18.0.1), 51775 (127.0.0.1). Depois: as mesmas **mais** `172.18.0.1:8100`. `agentes-trabalhador`, `docker`, `postgresql@16-main` e `fail2ban` continuam `active`.
