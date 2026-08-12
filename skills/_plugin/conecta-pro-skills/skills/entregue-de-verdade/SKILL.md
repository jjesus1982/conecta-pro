---
name: entregue-de-verdade
description: Checagem antes de dizer "pronto/funcionando/entregue" no Conecta PRO. Substitui superpowers:verification-before-completion aqui — a diferença é que neste sistema "feito" e "entregue" são estados distintos, e três coisas específicas separam um do outro. Use antes de QUALQUER frase de conclusão, e sempre que for reportar resultado ao Jordan.
---

# Entregue de verdade — Conecta PRO

`verification-before-completion` genérico diz: não afirme o que não verificou. Correto, e
insuficiente aqui. Neste sistema existe um estado intermediário que engana:

> **FEITO** = o código está certo e o teste passa.
> **ENTREGUE** = a pessoa que abre o sistema vê o resultado.

Em 12/08/2026 eu disse "pronto" três vezes estando apenas em FEITO.

## Os três portões

Faltando **um**, não é entregue:

### 1. Servido pela ROTA REAL, depois do bake

`docker cp` **não recarrega módulo já importado** pelo servidor. O oráculo roda `python3`
novo e enxerga a mudança; a API continua com o código velho em memória.

```bash
# depois do bake, com token real
curl -s "http://localhost:8080/api/v1/redesign/data/<slug>" -H "Authorization: Bearer $TK"
```

Caso real: as telas multi-CNPJ tinham 3 oráculos verdes e a rota devolvia `AUSENTE` para as
três. Só o bake entregou.

### 2. Oráculo verde — e que PEGA o defeito

Oráculo que passa antes e depois do conserto não prova nada. Rode-o contra o código anterior
e veja falhar:

```bash
git show HEAD:backend/<arquivo> > /tmp/ANTES.py
docker cp /tmp/ANTES.py conecta-pro-backend:/app/<arquivo>
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/<oraculo>.py  # tem que FALHAR
```

### 3. Nenhuma superfície nova sem vigia

Tela, KPI ou número novo sem oráculo é dívida no dia em que nasce. O Balanço Patrimonial
ficou meses exibindo PL de +R$ 2,02 milhões onde havia prejuízo de R$ 97 mil — não havia
oráculo contábil, e nada apontava a ausência.

## O que NÃO conta como verificação

| Isso | Por que não basta |
|---|---|
| "o endpoint respondeu 201" | `type:"form"` descarta o corpo; calculadora pode devolver o número e a tela jogar fora |
| "o status voltou `criada`" | o sync de CND devolveu `criada` com o portal FORA DO AR. A prova é o número do documento, não o status da operação |
| "o teste passa" | ver portão 2 |
| "está no commit" | ver portão 1 |
| ausência de erro | silêncio não é aprovação — "NÃO VERIFICADO" é resultado válido |

## Ao reportar ao Jordan

Diga nesta ordem: **o número medido**, depois a conclusão. Nunca o contrário.

- ✅ "obrigações em aberto: 54 → 28; valor R$ 214.226,97 → R$ 92.965,65"
- ❌ "corrigi o filtro de obrigações"

E diga o que **não** foi coberto. Toda vez. Em 11/08 a lente TELA ficou sem navegador
(Playwright indisponível) e isso foi dito no relatório — silêncio ali teria virado
"verificado" na cabeça de quem lê.

## Autocorreção

Se você já afirmou algo e depois mediu diferente, **corrija na hora, com o número**, e siga.
Sem preâmbulo, sem autoflagelo. Exemplo real: "o erro do faturamento é de 4%, não de 2,6× —
comparei com uma tabela só."
