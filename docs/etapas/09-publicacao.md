# Etapa 09 — Publicação e endurecimento

Antes de começar: leia CLAUDE.md, docs/SPEC.md (seções 7 e 10) e este arquivo. Não leia outras etapas. Releia `docs/VPS.md` e as decisões de deploy da etapa 01. O caminho domínio → HTTPS → aplicação já foi provado na etapa 01; aqui a aplicação real substitui o serviço mínimo e fica pronta para uso.

## Objetivo
Colocar a API e o worker reais no ar em `scrapagentes.khoral.com.br`, com autenticação, limites, reinício automático e backup, sem afetar nada que já existia na VPS.

## Contrato
- Entra: aplicação das etapas 02 a 08, decisões de `docs/VPS.md`.
- Sai: serviço em produção no domínio, procedimento de operação e backup documentados.

## Fora de escopo
Novas funcionalidades, novas redes, alterar serviços alheios.

## Construir
Peça confirmação do Mateus antes de alterar a VPS.
1. Substituir o serviço mínimo pela API real e subir o worker, conforme a decisão de deploy (systemd ou Compose), com reinício automático em falha e subida após reinício do servidor.
2. Chave de API de produção lida de variável de ambiente (definida pelo Mateus), nunca no repositório nem em logs.
3. Documentação interativa da API desligada em produção.
4. Apenas a API fica acessível de fora, via proxy; worker, banco e pasta de mídia não.
5. Limites: tamanho máximo de upload, limite simples de requisições por chave, timeouts.
6. Logs com rotação, sem segredos.
7. Backup: cópia consistente do banco (usando o mecanismo próprio do SQLite) e da pasta de frames, com rotina documentada e teste de restauração.
8. Procedimento de operação em `docs/VPS.md`: subir, parar, atualizar, ver logs, reverter.

## Rodar
Comandos de operação documentados.

## Testar
De fora da VPS:
- Rota sem chave devolve 401; com chave correta funciona; `/saude` livre.
- A documentação interativa responde 404.
- A porta interna da aplicação não responde pela internet pública.
- Certificado válido, sem desativar verificação.
- Reiniciar o serviço da API e o worker: voltam sozinhos.
- Restaurar o backup em pasta temporária e abrir o banco: dados presentes.

## Validar
- Comparar o inventário de portas e serviços da etapa 01 com o estado atual: nada pré-existente foi afetado.
- Teste de ponta a ponta no domínio com 3 posts reais (vídeo, foto, carrossel): adicionar, acompanhar o job, buscar, pegar o pacote.

## Pronto quando
- Todos os testes de fora passam.
- Backup restaurado com sucesso.
- Procedimento de operação e reversão documentado.
- Nenhum serviço pré-existente afetado.
- O Mateus validou o ponta a ponta.

## Preciso do Mateus
- Chave de API de produção.
- Confirmação para as alterações na VPS.
- Validação do ponta a ponta.

## Entrega
Atualizar `docs/progresso.md` com evidências. Revisão por subagente.
