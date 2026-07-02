# T1 — Financeiro & Fiscal: reconstrução por rastreabilidade & ponto de retomada

**Data:** 2026-06-28 (UTC do servidor) · **Investigação:** READ-ONLY (zero escrita/commit/rebuild além deste relatório)
**Token:** STEP-0-T1-FINFISCAL · **Raia:** `backend/modules/financial`, `backend/modules/fiscal`, `government_integrations`
**Fuso:** servidor em **UTC**; Manaus = **UTC-4**. Tudo abaixo cita UTC e (Manaus).

---

## TL;DR — onde a t1 parou em Fin/Fiscal

- A t1 trabalhou Fin/Fiscal **hoje** (27/jun Manaus = 27/jun tarde → 28/jun madrugada UTC), **última ação `accounting_controller.py` às 01:29 UTC = 21:29 Manaus**.
- **NADA foi commitado.** HEAD do git é `19c0ad16` de **2026-06-24 19:48** — não há commit em 26/27/28.
- **MAS o trabalho está BAKEADO na imagem `conecta-pro-backend:latest` rodando** (verifiquei: os marcadores das edições de 01:18 e 01:29 estão DENTRO do container) e existe a âncora de rollback **`pre-finfiscal-20260628`**.
- **Working tree compila 100%** (`py_compile` OK em todos os 16 arquivos) — nenhum arquivo cortado/quebrado. A t1 **não** morreu no meio de um arquivo; morreu **depois** de uma leva coerente, sem commitar.
- **Risco real = durabilidade (§13.7/B.7):** o código vive só no working tree do host + na layer `:latest`. **Um rebuild a partir de um checkout limpo do git PERDE tudo isto.** É o único buraco.

**Nota de completude: 8.5/10** — funcionalmente concluído, bakeado e no ar; perde 1.5 por **não estar no git** (não-durável) + 1 migration órfã na zona proibida.

---

## STEP 1 — O que a t1 COMMITOU em Fin/Fiscal
**Nada nesta janela.** Último commit do repo: `19c0ad16` (2026-06-24). Os commits de Fin/Fiscal mais recentes são todos **anteriores** a esta sessão:

| Commit | Assunto |
|---|---|
| `820df653` | fix(government_integrations): engine async no run_async — estanca leak celery-batch |
| `f7a5dfcc` | fix(financial): supplier stats total=0 (condominio_id None) |
| `06f1f036` | fix(t13-final): Fase 3 10/10 — Cobranças + Contabilidade |
| `3aa074ea` | fix(financial): T11 — fornecedores 422, orçamentos 422, estoque |
| `df016101` | fix(financial): saldo R$88.684,29 + 20/20 endpoints |

→ **Veredito:** o trabalho FECHADO (commitado) de Fin/Fiscal é antigo (≤24/jun). Tudo de 26-28/jun está aberto.

---

## STEP 2 — Trabalho ABERTO (não-commitado) em Fin/Fiscal
`git diff --shortstat` da raia: **16 arquivos, +193 / −161.** Todos sob `backend/modules/financial` (o módulo `fiscal` real não foi tocado; o "fiscal" mora em `financial/controllers/fiscal_controller.py`).

Tema **único e coerente** — blindar contra drift schema↔model e corrigir shape de resposta:

| Arquivo | Mudança |
|---|---|
| `controllers/accounting_controller.py` (ÚLTIMO, 01:29) | filtra payload às colunas REAIS do `CostCenter` (anti-drift); `journal-entries` passa a devolver o wrapper paginado `{items,total}` em vez de `list[...]` |
| `controllers/fiscal_controller.py` (01:18, +123/−129) | `current_user['email']`→`getattr(...,'email','')` (dict→obj); refactor dos GET de NF-e lendo tabela real |
| `repositories/fiscal_repository.py` | mapeia `competencia_mes/ano`→`mes/ano`, dropa `valor_devido` (coluna inexistente), default `frequencia` |
| `repositories/cashflow_repository.py` | `create()` aceita dict OU model (defensivo) em 4 repos |
| `repositories/purchase_repository.py`, `schemas/purchase_requisition.py` | ajustes de compra |
| `models/receivable_category.py` | `try/except` no property `has_children` |
| `models/{product,billing_rule,supplier,customer,warehouse,payable_account,accounting_period,receivable_category}.py` | enum `values_callable` + drift de tipo de coluna |
| `schemas/{supplier,receivable}.py` | alinhamento de schema |

→ **Veredito:** trabalho aberto é **coerente e completo** — cada edição é auto-contida, parte do sweep "telas cobertas que estavam quebradas em uso real". Nenhuma função pela metade.

---

## STEP 3 — ONDE parou (mtime + integridade)
- **Último arquivo tocado:** `accounting_controller.py` — **2026-06-28 01:29 UTC (21:29 Manaus)**.
- Sequência da leva final (28/jun UTC): `fiscal_controller`+`product`+`billing_rule`+`purchase_*` (01:18) → `fiscal_repository`+`cashflow_repository`+`receivable_category` (01:21) → `accounting_controller` (01:29).
- **`py_compile`: 16/16 OK.** Zero arquivo cortado. O diff do último arquivo é uma edição **completa** (cost-center filter + wrapper de journal-entries fechados).
- **Container rodando == working tree** para Fin/Fiscal: marcadores de 01:18 e 01:29 presentes DENTRO de `conecta-pro-backend`. Âncora `pre-finfiscal-20260628` existe.
- `/health` = healthy · 21/28 containers healthy.

→ **Veredito:** a t1 parou **após** concluir e bakear a leva, no `accounting_controller.py` 21:29 Manaus. **Working tree de Fin/Fiscal é seguro pra retomar** (compila, está no ar). Provável fim de sessão (OOM/morte) ocorreu **antes do commit**, não no meio de uma edição.

---

## STEP 4 — O que a própria t1 declarou (relatórios)
Fonte: `AUDITORIA_TELAS_FRONTEND_2026-06-26.md` + `RESPOSTA_T1_AO_T2_cobertura_2026-06-28.md`.

**Declarado FEITO em Fin/Fiscal:**
- **WAVE 2 Financeiro (26/jun):** fix em ponto único `frontend/src/lib/api-client.ts` (customInstance) — colapsa prefixo dobrado do orval em `/financial/*`. Destravou: clientes 11, conciliação **2.876 transações**, contabilidade 62 contas, orçamentos 12, fornecedores, estoque, compras. Bakeado (`pre-financeiro-20260626`).
- **Residual fiscal (27/jun):** 3 GET de `fiscal_controller.py` (nfse/nfe/dashboard) reescritos lendo tabela real `nfses` → **27 NFS-e, R$ 542.673,92, 7 obrigações**. `journal-entries` → wrapper `{items}` (11 lançamentos). Bakeado (`pre-fiscal-20260627`).
- **Bug sistêmico:** **176 colunas `Enum()` sem `values_callable`** corrigidas em massa (int-enums revertidos).
- Declarado: **">>> FINANCEIRO 100% CONCLUÍDO <<<"**.

**PRÓXIMO alvo declarado (RESPOSTA_T1_AO_T2 §5):** os próximos alvos são de **outras raias** (P1 Serviços, P3 Instalações, P2 profundidade DP/Folha, convergência clima/retention). **Em Fin/Fiscal a t1 não listou pendência funcional** — considerou fechado.

→ **Veredito:** segundo a própria t1, Fin/Fiscal estava **feito e bakeado**; o próximo trabalho dela era fora de Fin/Fiscal.

---

## STEP 5 — Estado & retomada

| Pergunta | Resposta |
|---|---|
| Commitado em Fin/Fiscal? | **Não** — nada desde 24/jun. |
| Aberto/não-commitado? | 16 arquivos `financial/*` (+193/−161), coerentes. |
| Onde parou? | `accounting_controller.py` 01:29 UTC / 21:29 Manaus — **completo, compila**. |
| Bakeado/no ar? | **Sim** — container roda o código; âncora `pre-finfiscal-20260628`. |
| Próximo alvo (t1)? | Fora de Fin/Fiscal (Serviços/Instalações/DP). Fin/Fiscal = fechado. |
| **Working tree seguro pra retomar?** | **SIM.** Compila, no ar, nenhum arquivo quebrado. |
| **Único risco** | **Não está no git.** Rebuild de checkout limpo regride tudo (§13.7/B.7 durabilidade). |

### Ação recomendada pra "continuar a partir daí" (FORA do escopo read-only — requer sua autorização)
1. **Persistir no git** os 16 arquivos de `financial/*` num commit cirúrgico (§13.3) — separado do refactor de outros módulos e do ruído `agents/cto/*`. Sufixo `[session: t1] [module: financial]` (B.8). **Isso fecha o buraco de durabilidade.**
2. **Migration órfã na zona proibida:** `backend/alembic/versions/camada3_financial_kpis.py` (untracked, 30/mai) — decidir versionar ou quarentenar (B.6 zona proibida; não tocar sem decisão sua).
3. **Não rebuildar** sem antes commitar — senão a layer `:latest` é a única cópia.

> Observação de raia: a sessão de hoje tocou **muito além de Fin/Fiscal** (CRM, recruitment, SST, people_management, services, notifications, scheduler, audit, ai-models — leva `values_callable` em massa às 20:12 UTC). Ao commitar Fin/Fiscal, **isolar** só `backend/modules/financial` pra não arrastar trabalho de outros módulos não-verificados.
