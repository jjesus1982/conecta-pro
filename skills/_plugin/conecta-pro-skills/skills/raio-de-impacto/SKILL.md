---
name: raio-de-impacto
description: Descobre QUEM MAIS depende do que você vai editar, antes de editar. Adapta graphify ao Conecta PRO — aqui o grafo não serve para achar defeito (os defeitos são semânticos e de dado), serve para responder "se eu mudar isto, o que quebra e quem mais está errado pelo mesmo motivo". Use antes de mexer em serviço/cliente/helper compartilhado, e sempre que corrigir um defeito que pode ter irmãos.
---

# Raio de impacto — Conecta PRO

O `graphify` genérico promete navegar arquitetura. Rodei no fiscal: 123 nós, e **nenhum
defeito daquele dia era estrutural** — eram filtro SQL errado, conta classificada por
convenção errada, portal devolvendo página genérica. Grafo de chamadas não enxerga nada
disso.

O que ele (ou um grep bem feito) resolve de verdade aqui é outra pergunta, e ela custou caro
duas vezes: **"quem mais?"**

## As duas perguntas que valem

### 1. Antes de editar — quem consome isto?

```bash
cd /opt/conecta-pro
grep -rn "nome_da_funcao\|NomeDaClasse" backend/ --include=*.py | grep -v "def \|class "
git log --since="1 day ago" --oneline -- <arquivo>     # outra sessão está aqui?
git status --short -- <arquivo>                        # WIP alheio?
```

Caso real: mudei a assinatura de `contrapartida_entrada` (parâmetro novo). Havia **um**
chamador em produção e uma suíte de testes que o T1 tinha deixado. Rodei a suíte: 18 passed.
Se eu não tivesse procurado, teria descoberto pelo alarme das 05:00 — ou pior, não teria
descoberto.

### 2. Depois de achar um defeito — ele tem irmãos?

Esta é a que dói. Corrigir o caso que apareceu e deixar a família viva é o padrão desta casa:

| Achei e corrigi | Quantos eram de verdade |
|---|---|
| faturamento ancorado no `max()` do arquivo, em `fiscal.py` | **5** (financeiro.py ×2, redesign_data_controller ×2) |
| `NOT IN ('pago','paga',…)` numa tabela que diz `cumprida` | **5** (mais 3 em redesign_data_controller) |
| `utcnow()+timedelta` virando validade, em `cnd_sync_task` | **3** (mais 2 em crf_client) |

Nos três casos eu declarei "corrigido" com um terço da família viva. **Depois de todo
conserto, procure a assinatura no repositório inteiro** — e prefira os caçadores mecânicos:

```bash
docker exec conecta-pro-backend python3 /app/scripts/qa/cacar_fabricacao.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/checar_vocabulario.py
```

## Quando graphify ganha do grep

| Situação | Ferramenta |
|---|---|
| "quem chama esta função?" | **grep** — mais rápido, sem cerimônia |
| "que assinatura é essa e onde mais aparece?" | **caçadores** em `scripts/qa/` |
| "rota codada sem superfície no front?" | **conecta-backend-recon** |
| "não conheço este subsistema, qual a forma dele?" | **graphify** (nós-deus, comunidades) |
| "o que é código morto aqui?" | **graphify** dentro do `raio-x-modulo` |

**Regra:** só invoque `graphify` quando a pergunta for sobre FORMA de um subsistema que você
não conhece. Rodar para gerar nós e não consultar é cerimônia — foi o que fiz no fiscal.

## Se for usar graphify

```bash
cd /opt/conecta-pro   # graphify-out/ do repo é o grafo grande; não deixe encolher
graphify query "quem consome <coisa>"
graphify path "<A>" "<B>"
graphify explain "<nó>"
```

⚠️ A proteção de encolhimento recusa gravar um grafo menor que o existente. Se você rodar
num subdiretório, o `graph.json` do repositório **não** é sobrescrito — e a saída do seu
build fica só em memória. Trabalhe com `query` sobre o grafo grande.

## Saída

Uma frase por consumidor, e a decisão: **edito, aviso, ou espero.** Se houver WIP de outra
sessão no mesmo arquivo, a resposta padrão é **espero** — ver [[plano-conecta]].
