# Etapa 01 — Reconhecimento da VPS e esqueleto de deploy

Antes de começar: leia CLAUDE.md, docs/SPEC.md e este arquivo. Não leia outras etapas.

## Objetivo
Entender como a VPS funciona (deploy, portas, proxy, firewall, recursos, rede) e provar o caminho domínio → HTTPS → aplicação com um serviço mínimo, para não descobrir gargalos de infraestrutura no fim do projeto.

## Contrato
- Entra: acesso à VPS e o domínio `scrapagentes.khoral.com.br`.
- Sai: `docs/VPS.md` com inventário e decisões de deploy, e um serviço mínimo respondendo em HTTPS no domínio.

## Fora de escopo
Qualquer código do produto. Alterar, parar ou reconfigurar serviços que já existem na VPS.

## Fase A — Estudo (somente leitura)
Nada é alterado nesta fase. Registre em `docs/VPS.md`, em tabela, cada item abaixo com o comando usado e o resultado. Onde não for possível descobrir, escreva "desconhecido" e diga o que falta.

1. **Sistema:** distribuição e versão, kernel, usuário atual, se há `sudo`, fuso horário e sincronização de hora, locale UTF-8.
2. **Recursos:** vCPUs, RAM, swap, espaço em disco livre por partição, GPU (esperado: nenhuma), limites do usuário.
3. **Ferramentas:** versões de Python disponíveis, `pip`/`venv`, `ffmpeg`/`ffprobe` (e se há suporte aos filtros que o SPEC usa), `sqlite3` (e se o SQLite embutido no Python tem FTS5), Docker e Compose, `git`, `curl`.
4. **O que já roda (inventário para não colidir):** serviços do sistema ativos, contêineres, processos de longa duração, e **todas as portas em escuta com o processo dono**. Registrar também tarefas agendadas (cron/timers).
5. **Proxy reverso:** existe nginx, Caddy, Traefik ou outro? Onde ficam as configurações? Quem ocupa as portas 80 e 443? Como são emitidos os certificados hoje?
6. **Firewall:** regras locais (ufw/nftables/iptables) e se o provedor tem firewall externo; quais portas estão abertas para fora.
7. **DNS:** para onde `scrapagentes.khoral.com.br` resolve hoje, qual é o IP público da VPS, e se o registro já aponta para ela.
8. **Rede de saída:** a VPS alcança a internet por HTTPS? Teste só de conectividade (sem coletar dados) até um site público qualquer e até `instagram.com`. Registrar o código de resposta ou o erro. Há proxy de saída configurado no ambiente?
9. **Operação:** como serviços sobem após reinício (systemd ou outro), onde ficam os logs e se há rotação, e se existe rotina de backup.
10. **Capacidade para transcrição:** com base em CPU e RAM, indique qual tamanho de modelo do faster-whisper é realista em CPU (com quantização int8) e quantos jobs pesados simultâneos a VPS suporta. Este item é uma estimativa; marque-a como tal e proponha o teste real na etapa 04.
11. **Git e GitHub:** versão do `git`; identidade configurada (`user.name` e `user.email`); **como** a VPS se autentica no GitHub (chave SSH, token, `gh`, credential helper, deploy key), descobrindo o método **sem exibir** chaves nem tokens; qual conta ou usuário o GitHub reconhece; e se o acesso de leitura ao repositório `https://github.com/Pteusz/scrap-agentes.git` funciona (por exemplo, listando as referências remotas, sem clonar). Registrar também se a chave tem permissão de escrita, **sem fazer push** nesta fase.

### Saída da Fase A: seção "Decisões de deploy" em `docs/VPS.md`
Responder, com justificativa curta:
- Reaproveitar o proxy reverso existente ou usar o Caddy (ou outro) para este projeto? Sem colidir com as portas 80/443 já usadas.
- Em que porta interna a API vai escutar?
- API e worker rodam em systemd ou Docker Compose? Por quê, dado o que a VPS já usa.
- Onde ficam banco, frames e logs (caminhos) e como será o backup.
- Fluxo de código na VPS: onde o repositório fica clonado, como as atualizações chegam (pull manual, por exemplo) e como o serviço é reiniciado depois.
- Tamanho de modelo de transcrição e concorrência recomendados.
- **Riscos e bloqueios** (por exemplo: DNS fora do lugar, 80/443 ocupadas por outro serviço, pouca RAM, sem saída para a internet). Para cada risco: o que o Mateus precisa fazer.

**Pare ao fim da Fase A e mostre o resumo ao Mateus. Só siga para a Fase B com a confirmação dele.**

## Fase B — Esqueleto de deploy (com confirmação)
Peça confirmação antes de cada alteração na VPS (instalar pacote, criar serviço, mexer em proxy, abrir porta). Se o DNS ainda não aponta para a VPS, pare e diga qual registro o Mateus precisa criar.

1. Subir um serviço mínimo (uma rota `/saude` que devolve ok), na porta interna decidida, atrás do proxy, no domínio, com HTTPS válido.
2. Configurá-lo para subir sozinho conforme a decisão (systemd ou Compose) e para reiniciar em caso de falha. Não reinicie a VPS inteira.
3. Documentar em `docs/VPS.md` os comandos exatos de subir, parar, ver logs e reverter tudo o que foi feito.
4. **Repositório:** clonar `https://github.com/Pteusz/scrap-agentes.git` no caminho decidido (se ainda não estiver clonado) e registrar em `docs/VPS.md` o estado dele: branch padrão, se está vazio ou tem conteúdo (README, licença, arquivos), e último commit. Com a confirmação do Mateus, testar a escrita: criar um commit trivial em uma branch temporária, fazer push dela e apagá-la em seguida. Copiar `CLAUDE.md` e `docs/` do pacote para o repositório só se ainda não estiverem lá.

## Rodar
Os comandos de subir/parar do serviço mínimo, tal como documentados.

## Testar
- De fora da VPS (ou de uma máquina diferente): `https://scrapagentes.khoral.com.br/saude` responde 200.
- O certificado é válido (sem desativar verificação).
- A porta interna da aplicação **não** responde pela internet pública, só pelo proxy.

## Validar
- Compare o inventário de portas e serviços da Fase A com o estado depois da Fase B: tudo que existia antes continua rodando nas mesmas portas.
- Reinicie só o serviço mínimo e confirme que ele volta.
- Mostre ao Mateus a lista do que foi alterado e como reverter.

## Pronto quando
- `docs/VPS.md` completo, sem "desconhecido" nas perguntas que bloqueiam o deploy.
- Seção "Decisões de deploy" respondida.
- Serviço mínimo responde 200 em HTTPS no domínio, de fora.
- Nenhum serviço pré-existente foi afetado (comparação das portas e serviços).
- Reversão documentada.
- Acesso ao GitHub pela VPS confirmado (leitura e, com confirmação, escrita), método de autenticação documentado sem expor segredos, e repositório clonado com seu estado registrado.

## Preciso do Mateus
- Confirmação para alterar a VPS (por item).
- Registro DNS do domínio apontando para a VPS, se ainda não existir.
- Acesso à VPS para os comandos.
- Confirmação de que o repositório é o destino do projeto, qual é a branch padrão e se pode haver conteúdo prévio nele.
- Confirmação para o teste de escrita no GitHub.

## Entrega
Atualizar `docs/progresso.md` com evidências. Revisão por subagente comparando as alterações com esta etapa.
