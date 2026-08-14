# Raio-X — Financeiro · 14/08/2026

**Método:** skill `raio-x-modulo` (5 passos) · `backend_recon financial` · 8 travas ·
4 oráculos · veracity sweep nas telas · graphify (6.819 nós, 15.513 arestas, 188 comunidades).
**READ-ONLY.**

> Feito depois de o T1 declarar "financeiro fechado". O código está limpo; o que este raio-x
> mostra é o que **"fechado" ainda não cobre**.

---

## Veredito por lente

| Lente | Status | Evidência |
|---|---|---|
| **DADO** | ⚠️ | 4 oráculos verdes · mas KPI "A pagar" **esconde R$140.799,11** |
| **TELA** | ⚠️ | 138 telas · dashboard 3 de 4 KPIs batem |
| **CÓDIGO** | ✅ | 0 chamada a método inexistente · 0 vocabulário CRÍTICO · 1 rota 404 |
| **PRAZO** | ⚠️ | transitória crescendo em agosto sem alarme |

**Paridade:** 596 rotas · **576 expostas** · 20 órfãs (16 falso-órfão) · **0 gerador órfão**.

---

## A · Achado estrutural: DOIS sistemas contábeis paralelos

```
accounting_entries        5.904 lançamentos   ← o razão VIVO
                          12 arquivos escrevem, vários com psycopg2 CRU
                          sem aprovação · corte de período por TRIGGER no banco

fin_journal_entries          11 lançamentos   ← o diário ORM
fin_journal_entry_lines      23 linhas
                          16 arquivos referenciam · fluxo de aprovação completo
                          8 rotas montadas e respondendo 200
                          pending-approval · approve · post
```

Os dois usam o mesmo plano (`fin_accounting_accounts`, 88 contas).

**O que funciona não tem aprovação; o que tem aprovação quase não é usado.** E o
`period_closing_service` fecha o período do **diário de 11 lançamentos**, não do razão de
5.904 — o corte real de período é o **trigger `trg_bloqueia_periodo_fechado`**.

⚠️ **Correção minha:** cheguei a concluir que `journal_entries` não existia e quase reportei
"8 rotas quebradas". O modelo mapeia para **`fin_journal_entries`**; as rotas devolvem **200**,
provado por HTTP. *Prove o arreio antes de acusar o código.*

## B · 21 arquivos com conexão crua (`psycopg2`)

Maior concentração do sistema — 21 contra 6 em `government_integrations` e 3 em
`people_management`. Inclui os três que escrevem no razão:

```
services/extrato_para_razao.py      ← escritura o extrato
services/apuracao_resultado.py      ← criou os 154 lançamentos do PL
controllers/accounting_controller.py
```

Conexão fora da sessão do ORM = transação própria, nenhuma trava de aplicação. **O que segura
o corte de período é o trigger do banco** — e isso é acerto, porque remendo por serviço não
cobriria estes 21.

## C · O KPI que esconde R$140 mil

```
TELA   "A pagar (aberto)"  R$ 11.373,61
BANCO  pago       219 títulos · R$ 855.927,84
       cancelada   64 títulos · R$  90.708,12
       pendente    10 títulos · R$  11.373,61   ← o que a tela mostra
       suspensa     8 títulos · R$ 140.799,11   ← INVISÍVEL
```

`redesign_data_controller.py:453` usa `status IN ('pendente','parcial')` — lista **positiva**.
`suspensa` não está nela nem entre os liquidados: **sumiu do painel**.

A decisão de origem está **certa** (commit de hoje: *"dívida SUSPENSA não é cobrança — tira de
vencido"*). O efeito colateral é que ela não aparece **em lugar nenhum**. Dívida suspensa
continua sendo dívida; precisa de linha própria, não de soma ao vencido.

## D · Contábil — um avanço grande e três pendências

| | antes (manhã) | agora |
|---|---|---|
| PL — lançamentos em 3.x | 0 | **154** ✅ |
| Resultado | −R$242.664,67 | **−R$205.541,46** |
| Transitória | R$320.013,72 | **R$665.744,14** ❌ |
| Contas 3.x corrompidas | 4 | **4** ❌ |

**O PL é entrega real do T1** — não é lançamento de fachada:

```
3.3.1.01 / 5.1.1.01    7 lanç · R$ 719.031,91   encerra despesa contra resultado
3.3.1.01 / 5.2.1.04   42 lanç · R$ 576.114,09
3.2.1.01 / 3.3.1.01   40 lanç · R$ 348.823,12   resultado → lucros acumulados
```

**A transitória, porém, dobrou — e o crescimento é de AGOSTO:**

```
2026-08 ·  51 lanç · R$ 354.887,85   ← 55% do total, num mês só
2026-07 ·  97 lanç · R$  57.835,00
2026-06 · 124 lanç · R$  56.321,24
```

Seis vezes mais valor que julho, com metade dos lançamentos. **Não é acúmulo histórico: é
dinheiro entrando agora sem classificação** — e agosto é justamente o que passa a valer.

**E as 4 contas 3.x seguem corrompidas** (Portaria, Vigilância, Limpeza e ISS dentro do grupo
de patrimônio) — agora com 154 lançamentos por cima, o que torna o conserto mais delicado.

## E · Duas conciliações automáticas sem botão

```
POST /financial/conciliar/auto              → Inter × Notas, lote até 649 transações
POST /financial/bank-reconciliations/auto   → 4 estratégias em cascata, recebíveis
```

**Não são duplicatas** (direções opostas: saídas × entradas), mas **nenhuma tem superfície no
front**. As outras 2 órfãs são MCP (`/mcp/financial/*`) — server-to-server, legítimas.

## F · Lead de fabricação (da trava, publicado no sino hoje)

```
financial/services/ordem_pagamento_service.py:232
  return {'ok': True, 'aviso': f'OTP gravado, e-mail falhou: {str(exc)[:120]}', ...}
```

Devolve `ok: True` quando o e-mail do OTP falhou. O OTP **foi** gravado — não é mentira
completa — mas num fluxo de pagamento, "ok" com o humano sem o código é sucesso que engana.
**Pista da trava, não veredito.**

---

## O que "fechado" cobre e o que não cobre

**Cobre:** código (0 repositório, 0 vocabulário), 4 oráculos verdes, paridade 97%, e o PL que
saiu do zero.

**Não cobre:** a transitória de agosto, as contas 3.x, o KPI que esconde suspensas, as duas
conciliações sem botão — e, principalmente, **não existe `fechado_financeiro.py`**. O T4
fechou o operacional com gate executável que eu reproduzi; aqui "fechado" é declaração.

---

## NÃO COBERTO por este raio-x

- **Navegador**: nenhuma tela aberta; tudo por builder, rota e banco.
- **Passo 4 parcial**: li os controllers das 4 órfãs reais e o do `JournalEntry`; **não li os
  16 falso-órfãos**.
- **Grafo**: reconstruído e consultado 2×. Ele **não** responde bem "código que ninguém chama"
  (BFS semântica); serviu para achar a duplicação contábil, que era o objetivo.
- **Período anterior a 01/08**: fora de escopo por decisão do Jordan (14/08) — o histórico
  serviu à homologação e não se refaz.
