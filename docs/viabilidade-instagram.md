# Viabilidade — Instagram (etapa 03, fase 1)

Data: 2026-11-03. Origem: VPS `vps2` (IP de datacenter, sem login) e, para comparar, o IP do celular do Mateus pelo túnel reverso (`docs/tunel-celular.md`). Ambiente de teste isolado em `~/viab-venv` (fora do projeto). Uma requisição por post, com 4 a 30 s de pausa; tentativas repetidas pelo mesmo motivo foram interrompidas em 3.

URLs: ver `docs/progresso.md`, seção "URLs de teste do Instagram".

## Resultado por candidato (anônimo)
| candidato | foto | carrossel | vídeo (reel) |
|---|---|---|---|
| HTTP direto (`httpx`, página e `/embed/captioned/`) | 200, mas só a casca genérica (≈505 KB, sem dados do post; exige JavaScript) | idem | idem |
| **Instaloader 4.16** | **OK** | **OK** | **OK em 4 de 5 reels** |
| yt-dlp 2026.10.26 | não testado | falha | falha no reel problemático (mesma falha do servidor) |
| instadata | não instalável: exige Python 3.13+, a VPS tem 3.12.3 | — | — |

**Correção de uma conclusão anterior.** Na primeira rodada o reel falhou e concluí que o Instagram não entrega reels a clientes anônimos. Estava errado: o Instaloader 4.16 já contém a correção de junho de 2026 (PR #2706: novo `doc_id` da consulta `PolarisPostRootQuery`, normalização do retorno e consulta ao endpoint de clips para contagem de reproduções). Com ela, 4 de 5 reels funcionam. O reel `DfSLSZpjl_4` falha sempre com `field_exception` devolvido pelo próprio servidor, também no yt-dlp: é um caso de borda daquele post, não bloqueio.

## Campos obtidos
- **Foto** (GraphImage): conta, data (UTC), legenda, curtidas, comentários, URL da imagem.
- **Carrossel** (GraphSidecar): conta, data, legenda, curtidas, comentários, URLs dos slides em ordem.
- **Reel** (GraphVideo): conta, data, legenda, curtidas, comentários, URL do vídeo. `video_view_count` e `video_duration` costumam vir **vazios** no modo anônimo: `visualizacoes` normalmente fica ausente e a duração é lida com o `ffmpeg` no arquivo baixado.
- Download da mídia na CDN pela VPS responde 200 (imagem e vídeo). Tempo por post: 0,6 a 3,1 s.

## Proxy
Foto, carrossel e reels funcionam **direto da VPS, sem proxy**, e pelo túnel do celular com o mesmo resultado. Nenhum 429 nas requisições feitas. Decisão: o adaptador roda sem proxy por padrão; `SCRAPAGENTES_PROXY=socks5h://127.0.0.1:1080` liga o túnel quando houver bloqueio por IP. Proxy configurado e fora do ar vira erro `indisponivel`, sem cair em silêncio para o IP da VPS.

## O que continua sem se saber
- Comportamento com volume maior ou ao longo dos dias (amostra pequena). O adaptador impõe intervalo mínimo de 5 s entre consultas (`SCRAPAGENTES_IG_INTERVALO_S`).
- Se a correção do `doc_id` continua válida: o Instagram troca esses identificadores de tempos em tempos. Quando quebrar, o sintoma é `indisponivel` em todos os posts; a saída é atualizar o Instaloader.
- Posts de carrossel com vídeo em algum slide não são suportados nesta etapa (erro `formato_nao_suportado`).
