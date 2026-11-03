# Modelo de etapa

Toda etapa segue esta estrutura. Cada etapa tem um objetivo, termina em comandos que você mesmo roda e só é concluída com evidência.

```
# Etapa NN — nome

Antes de começar: leia CLAUDE.md, docs/SPEC.md e este arquivo. Não leia outras etapas.

## Objetivo
Uma frase.

## Contrato
O que entra e o que sai.

## Fora de escopo
O que não fazer nesta etapa.

## Construir
O que criar, nomeando arquivos e interfaces.

## Rodar
O comando para executar o que foi construído.

## Testar
Comandos de teste e dados de teste (fixtures).

## Validar
Critério observável. Quando só o Mateus consegue julgar, produzir um resumo curto para ele conferir.

## Pronto quando
Lista objetiva. Cada item é verificável por comando ou por conferência do Mateus.

## Preciso do Mateus
Insumos que dependem dele.

## Entrega
Atualizar docs/progresso.md com a saída dos comandos como evidência.
Pedir a um subagente para comparar o diff com esta etapa e apontar apenas lacunas que afetem correção ou requisito.
```

## Regras gerais
- Planejar antes de implementar quando a etapa tiver incerteza (modo de planejamento). Pular o plano só para mudanças que se descrevem em uma frase.
- Escrever o teste antes ou junto com a funcionalidade.
- Se falhar 3 vezes pelo mesmo motivo, parar e relatar.
- Sessão nova a cada etapa, com este conjunto de documentos como base.
