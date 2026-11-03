# Túnel do celular como proxy residencial

Objetivo: a VPS sair para a internet pelo IP do celular do Mateus (operadora ou Wi-Fi de casa), só quando o adaptador de uma rede pedir. O núcleo continua agnóstico de rede; só o adaptador lê a variável de proxy.

## Como funciona

O celular abre uma conexão SSH **para** a VPS (saída, funciona atrás de CGNAT) e pede um encaminhamento reverso sem destino:

```
celular (Termux)  --ssh -R 127.0.0.1:1080-->  VPS (porta 1080 só no loopback)
```

Com `-R <porta>` sem destino, o `ssh` do celular vira um servidor SOCKS: quem conecta em `127.0.0.1:1080` na VPS sai pela rede do celular. A porta 1080 nunca fica exposta à internet.

Na VPS: `SCRAPAGENTES_PROXY=socks5h://127.0.0.1:1080` (o `h` faz a resolução de DNS também pelo celular).

Regras do projeto que continuam valendo:
- Proxy fora do ar => erro tipado `indisponivel`. **Nunca** cair em silêncio para o IP da VPS.
- Nada de segredos no repositório. A chave privada fica só no celular.

## Dados da VPS (conferidos em modo leitura)

- Host: `194.163.134.245`, porta SSH `22`, usuário `pteuz`
- OpenSSH 9.6 (suporta `restrict` e `permitlisten`), `PasswordAuthentication no`
- Porta `1080` livre
- Impressão digital da chave de host (ED25519), para você conferir na primeira conexão do celular:
  `SHA256:84UfBER4TQgYwJn0FNjExdaG47Rq7jn41Nwj8a4aPOA`

## Passos no celular (Termux)

Atualize pacotes e instale o necessário:

```sh
pkg update
pkg install openssh autossh
```

Se o `pkg update` perguntar sobre arquivos de configuração, aceite o padrão (Enter).

Gere uma chave **só para este túnel**, sem senha (o celular não tem teclado prático e o acesso será restrito de qualquer jeito):

```sh
ssh-keygen -t ed25519 -f ~/.ssh/id_tunel -N "" -C "celular-tunel"
cat ~/.ssh/id_tunel.pub
```

Envie ao Claude **só o conteúdo de `id_tunel.pub`** (uma linha começando com `ssh-ed25519`). É a chave pública, pode ser colada no chat. **Nunca envie `id_tunel`** (sem `.pub`).

## Passo na VPS (só após confirmação do Mateus)

Será acrescentada **uma linha** ao final de `~pteuz/.ssh/authorized_keys`, sem alterar as duas que já existem:

```
restrict,port-forwarding,permitlisten="127.0.0.1:1080" ssh-ed25519 AAAA...(chave do celular) celular-tunel
```

Efeito: essa chave não abre shell nem executa comando; só pode pedir o encaminhamento reverso em `127.0.0.1:1080`. Para revogar, apague essa linha.

## Subir o túnel (no celular)

Primeira conexão, para aceitar e conferir a chave de host (compare com a impressão digital acima):

```sh
ssh -i ~/.ssh/id_tunel -N -R 127.0.0.1:1080 pteuz@194.163.134.245
```

Se aparecer o aviso de autenticidade, confira o `SHA256:84Ufb...` acima e digite `yes`. Interrompa com Ctrl+C depois de ver que conectou sem erro.

Uso normal, com reconexão automática:

```sh
termux-wake-lock
autossh -M 0 -N -R 127.0.0.1:1080 \
  -i ~/.ssh/id_tunel \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  pteuz@194.163.134.245
```

No Android:
- Configurações > Apps > Termux > Bateria: **sem restrições** (ou "não otimizar"). Sem isso o Android derruba o túnel com a tela apagada.
- Deixe a notificação do Termux (com o wake lock) ativa.
- Parar o túnel: Ctrl+C, ou `pkill autossh`, ou fechar o Termux.
- O tráfego do túnel consome o plano de dados quando o celular está no 4G/5G.

## Teste de aceitação (na VPS)

```sh
curl --socks5-hostname 127.0.0.1:1080 https://ifconfig.me
```

Deve mostrar o IP do celular (operadora ou Wi-Fi), **não** o IP da VPS (`2a02:c207:2297:8338::1` / `194.163.134.245`). Sem o túnel, o `curl` deve falhar com "connection refused" (prova de que a porta só existe com o celular conectado).

## Depois do túnel

1. Repetir os testes do Instagram com e sem `socks5h://127.0.0.1:1080` e registrar em `docs/viabilidade-instagram.md`.
2. Fase 2 da etapa 03: o adaptador lê `SCRAPAGENTES_PROXY`; proxy configurado e fora do ar => `indisponivel`.
3. O túnel ajuda contra bloqueio por IP (429). **Não** resolve sozinho o bloqueio anônimo dos reels, que não depende de IP (ver `docs/viabilidade-instagram.md`).

## Riscos assumidos

- O IP exposto ao Instagram é o do celular pessoal do Mateus. Volume baixo e sob demanda.
- Enquanto for o celular de uso diário, o túnel cai quando o aparelho estiver sem rede ou o Android matar o processo. Um aparelho dedicado depois repete os mesmos passos.
