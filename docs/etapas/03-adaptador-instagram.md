# Etapa 03 — Adaptador Instagram

Antes de começar: leia CLAUDE.md, docs/SPEC.md e este arquivo. Não leia outras etapas. Consulte `docs/VPS.md` (saída de rede).

## Objetivo
Coletar posts públicos do Instagram (legenda, data, curtidas, comentários, formato, mídia) por trás do contrato do adaptador. A viabilidade vem primeiro: coletar de uma VPS pode ser bloqueado.

## Contrato
- Entra: URL pública de post do Instagram.
- Sai: o que o contrato `resolver` e `coletar_metricas` do SPEC definem, com mídia baixada em disco.

## Fora de escopo
Coleta em massa de perfis, hashtags, stories, qualquer login de conta pessoal, contorno de bloqueios por meios não previstos pelo Mateus.

## Fase 1 — Teste de viabilidade (antes de qualquer código definitivo)
Candidatos a avaliar, na ordem: **Instaloader** (sem login para perfis públicos), **instadata** (camadas: HTTP anônimo, TLS imitando Chrome, cookies, navegador). A biblioteca **instagrapi** só entra se o Mateus aceitar usar uma conta; não use contas sem autorização dele.

Para cada candidato, a partir da VPS, nas 3 URLs fornecidas (vídeo, foto, carrossel), com e sem proxy residencial quando o Mateus liberar:
- funcionou? quais campos vieram (legenda, data, curtidas, comentários, visualizações, mídia)?
- erros e bloqueios observados (mensagens, códigos);
- tempo por post e intervalo mínimo entre requisições que se mostrou seguro;
- se exige proxy residencial para funcionar da VPS.

Registre em `docs/viabilidade-instagram.md`. **Se nenhum candidato funcionar, pare e relate.** A decisão sobre proxy, conta ou outra abordagem é do Mateus.

## Fase 2 — Implementação
Com a opção escolhida:
1. Adaptador `instagram` conforme o contrato: `resolver` reconhece URL, determina o formato (`video`, `foto`, `carrossel`), baixa a mídia em ordem e devolve conta, data, legenda, duração e métricas iniciais. `coletar_metricas` devolve `curtidas`, `comentarios` e `visualizacoes` quando houver.
2. Erros tipados do SPEC (bloqueado, não encontrado, indisponível, exige login).
3. Limite de requisições e proxy por configuração; credenciais só por variável de ambiente.
4. Sem login por padrão.

## Rodar
Comando para resolver uma URL e imprimir o resultado (modo de inspeção), e comando para rodar os testes reais.

## Testar
- **Testes de parsing** com respostas gravadas (fixtures), sem rede.
- **Suite de contrato** passando para o adaptador `instagram` usando essas fixtures.
- **Testes reais**, marcados à parte e rodados só sob demanda, nas 3 URLs do Mateus.

## Validar
O Claude Code produz um relatório curto para cada uma das 3 URLs: formato detectado, campos preenchidos e vazios, quantidade e tipo de mídia baixada, métricas. O **Mateus confere** os números com o que vê no Instagram.

## Pronto quando
- `docs/viabilidade-instagram.md` existe e justifica a escolha.
- Suite de contrato passa com fixtures.
- Os 3 testes reais passam e o Mateus confirmou o relatório.
- Nenhum segredo no repositório nem nos logs.

## Preciso do Mateus
- 3 URLs públicas: um vídeo, uma foto, um carrossel.
- Decisão sobre proxy residencial e as credenciais (por variável de ambiente).
- Autorização explícita se algum candidato exigir conta.

## Entrega
Atualizar `docs/progresso.md` com evidências. Revisão por subagente.
