# scrapagentes

Acervo de posts de redes sociais (começando pelo Instagram) que guarda conteúdo, contexto informado pelo operador e métricas ao longo do tempo, e entrega um **pacote final** para uma IA externa. O sistema em si é determinístico: a IA só consome o pacote.

Domínio: `scrapagentes.khoral.com.br`
Repositório: `https://github.com/Pteusz/scrap-agentes.git`. O acesso ao GitHub já está configurado na VPS; a etapa 01 estuda como.

## Antes de qualquer trabalho
1. Leia este arquivo, `docs/SPEC.md` e **apenas** o arquivo da etapa em curso em `docs/etapas/`.
2. Consulte `docs/progresso.md` para saber qual é a etapa atual e quais insumos dependem do Mateus.
3. Trabalhe em **uma etapa por vez**. Não antecipe etapas futuras nem amplie o escopo.

## Regras fixas
- Núcleo agnóstico de rede. Tudo específico de uma rede mora no adaptador dessa rede (ver SPEC, seção 4).
- Nenhuma classificação por IA. Nicho e subnichos vêm da request. A IA só recebe o pacote.
- Métrica nunca sobrescreve: cada coleta cria linhas novas. Não existe recoleta automática; só por chamada própria.
- Nomes de tabelas, campos e rotas em português sem acento, exatamente como no SPEC. Documentação e mensagens em português.
- Segredos (chave de API, credenciais de proxy) só em variáveis de ambiente. Nunca no repositório, nem em logs.
- Git: um commit (ou poucos) por etapa, com mensagem em português. Nunca `push --force`. Não reescreva histórico. O primeiro push exige confirmação do Mateus. Nunca imprima chaves SSH nem tokens.
- A VPS pode hospedar outros serviços. **Não altere nem pare nada que já exista.** Qualquer mudança na VPS (instalar pacote, abrir porta, mexer em proxy, firewall ou DNS) exige confirmação explícita do Mateus antes.
- Nunca desative verificação TLS nem contorne bloqueios de rede; se algo for bloqueado, relate.
- Um job pesado por vez (transcrição e extração de frames). A VPS é simples.

## Como uma etapa termina
Cada etapa tem uma seção "Pronto quando" com checagens que você mesmo roda. Só marque a etapa como concluída quando os comandos de teste e validação passarem e você tiver colado a saída como evidência em `docs/progresso.md`. "Parece pronto" não conta.

Se uma tentativa falhar 3 vezes pelo mesmo motivo, pare e relate o que tentou e o que viu. Não continue em ciclo.

## Comandos
Serão registrados aqui ao fim da etapa 02 (rodar API, rodar worker, rodar testes, rodar testes reais).

## Mapa
- `docs/SPEC.md` — modelo de dados, contrato do adaptador, API, regras. É o contrato do projeto.
- `docs/etapas/` — uma etapa por arquivo. O molde está em `00-modelo-de-etapa.md`.
- `docs/progresso.md` — estado das etapas, evidências e insumos pendentes do Mateus.
- `docs/VPS.md` — criado na etapa 01: inventário e decisões de deploy da VPS.
- `docs/decisoes.md` — decisões técnicas tomadas ao longo das etapas (criado na etapa 05, usado depois).
- `docs/viabilidade-<rede>.md` — testes de viabilidade de cada rede (etapas 03 e 10).
