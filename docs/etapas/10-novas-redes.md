# Etapa 10 — Molde para novas redes

Antes de começar: leia CLAUDE.md, docs/SPEC.md (seções 3 e 4) e este arquivo. Não leia outras etapas.

Esta etapa é um **molde que se repete** a cada rede nova (Twitter/X, por exemplo). Não é executada uma vez só. Para cada rede, copie este arquivo para `docs/etapas/10-<rede>.md` e preencha.

## Objetivo
Adicionar uma rede nova escrevendo apenas um adaptador e registrando-o. **Nada no núcleo muda.**

## Contrato
O mesmo contrato da seção 4 do SPEC: `resolver(url)` e `coletar_metricas(item)`, com erros tipados.

## Fora de escopo
Alterar banco, API, fila, transcrição ou frames. Se for preciso alterar qualquer um deles, **pare e relate**: é sinal de que o núcleo vazou detalhe de rede e a mudança é uma decisão do Mateus.

## Antes de construir: ficha da rede
Preencha e mostre ao Mateus:
- Nome da rede e como reconhecer uma URL dela.
- Formatos válidos (vocabulário do campo `formato`). Exemplo para texto: `post`, `thread`, `post_com_midia`.
- Métricas que a rede oferece e seus nomes (reutilize os padronizados quando fizer sentido; novos nomes só se necessário).
- Como o corpo do texto entra no campo `legenda`.
- O que fica fora (mídia, respostas, perfis).

## Fase 1 — Viabilidade
Teste de viabilidade como na etapa 03: as ferramentas candidatas atuais, a partir da VPS, com 3 URLs reais de formatos diferentes. Relate o que funciona, o que bloqueia, se exige login ou proxy, e registre em `docs/viabilidade-<rede>.md`. Pesquise o estado atual das ferramentas antes de testar, porque redes mudam com frequência. **Se nada funcionar, pare e relate.** A decisão é do Mateus.

## Fase 2 — Implementação
1. Adaptador da rede com o contrato.
2. Registro no registro de adaptadores.
3. Credenciais e proxy por configuração e variável de ambiente.

## Testar
- A **suite de contrato** da etapa 02 passa para o novo adaptador com fixtures de respostas gravadas.
- Testes de parsing sem rede.
- Testes reais marcados à parte, sob demanda.
- Teste de integração: ingestão completa pela API de um post real da rede, até o pacote.
- Os testes dos outros adaptadores continuam passando sem alteração.

## Validar
Relatório curto para 3 URLs reais (campos preenchidos, mídia, métricas) para o Mateus conferir.

## Pronto quando
- Suite de contrato passa.
- Nenhum arquivo do núcleo foi alterado (verificar no diff).
- Testes dos adaptadores anteriores seguem verdes.
- O Mateus confirmou o relatório de 3 posts reais.

## Preciso do Mateus
3 URLs reais da rede, decisão sobre login ou proxy e a aprovação da ficha da rede.

## Entrega
Atualizar `docs/progresso.md` com evidências. Revisão por subagente.
