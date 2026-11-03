# Etapa 02 — Base e contrato do adaptador

Antes de começar: leia CLAUDE.md, docs/SPEC.md e este arquivo. Não leia outras etapas. Consulte `docs/VPS.md` para versões, caminhos e decisões de deploy.

## Objetivo
Ter o repositório, o banco, a API e o contrato do adaptador funcionando apenas com dados fictícios e o adaptador `manual`.

## Contrato
- Entra: SPEC (seções 3, 4 e 7) e `docs/VPS.md`.
- Sai: API que cria, lê e busca itens; banco com as tabelas do SPEC; registro de adaptadores; suite de contrato; fixtures geradas.

## Fora de escopo
Instagram, transcrição real, extração real de frames, fila com worker (o `POST /itens` pode criar o item de forma síncrona nesta etapa para os testes), publicação no domínio.

## Construir
1. Use o repositório já clonado na etapa 01. Antes de criar qualquer coisa, veja o que já existe nele e não sobrescreva nada existente sem avisar o Mateus. Estrutura: pacote da aplicação, pasta de testes, pasta de fixtures, migrações em arquivos SQL versionados, configuração por variáveis de ambiente, `.gitignore` que exclui segredos, dados e mídia.
2. Banco SQLite em modo WAL com `item`, `imagem`, `metrica`, `subnicho` e `job` conforme o SPEC, com restrições (chaves estrangeiras ligadas, `rede`+`url` único) e busca de texto sobre legenda e texto falado.
3. Normalizador de tags (SPEC, seção 3).
4. Registro de adaptadores e a interface do contrato (SPEC, seção 4), com erros tipados.
5. Adaptador `manual`.
6. **Suite de contrato** reutilizável: dado um adaptador e seus exemplos, verifica campos obrigatórios, vocabulário de formato, nomes e valores numéricos das métricas e erros tipados.
7. API com as rotas do SPEC (seção 7), com autenticação por chave de API em cabeçalho (rota `/saude` livre). Documentação interativa ligável só por configuração de desenvolvimento.
8. **Fixtures determinísticas geradas com ffmpeg** (sem depender de arquivos externos): um vídeo curto sintético com cenas de cores diferentes e um tom de áudio, uma imagem e uma sequência de imagens para carrossel.

## Rodar
Registrar em CLAUDE.md, seção "Comandos": como subir a API em modo de desenvolvimento e como rodar os testes.

## Testar
Testes automatizados cobrindo, no mínimo:
- Criar item fictício; duas coletas de métrica geram dois conjuntos de linhas (nada sobrescrito).
- Reingestão da mesma `rede`+`url` não duplica o item e acrescenta uma coleta.
- `Emagrecimento ` e `emagrecimento` resultam na mesma tag e na mesma busca.
- Rota sem chave devolve 401; `/saude` responde sem chave.
- Busca combinando `nicho`, `subnicho`, `formato` e período; busca por métrica sobre a coleta mais recente.
- Pacote devolve a estrutura do SPEC (com dados fictícios).
- Adaptador `manual` passa na suite de contrato.

## Validar
Subir a API localmente e exercitar as rotas com requisições reais usando as fixtures; mostrar as respostas.

## Pronto quando
- Todos os testes passam com um único comando.
- A API sobe e responde às rotas do SPEC com o adaptador `manual`.
- Os comandos de rodar e testar estão em CLAUDE.md.
- Nenhum segredo no repositório.

## Preciso do Mateus
Nada. A chave de API de produção só é definida na etapa 09.

## Entrega
Atualizar `docs/progresso.md` com evidências. Revisão por subagente.
