# BI-dashboard: deletar subsistema dormente + KPIs financeiros reais

> **For agentic workers:** execução inline nesta sessão (contexto completo já carregado). Steps com checkbox.

**Goal:** Remover o subsistema `financial/bi_dashboard/` (71 rotas, 70 sem consumidor) e trocar o único consumidor real — o hook `useFinancialOverview`, que alimentava 4 KPIs do financeiro com meta-stats de dashboards (campos `undefined`) — por dados reais do endpoint `/api/v1/financial/dashboard`.

**Architecture:** O hook `useFinancialOverview` mantém nome+shape (`IFinancialOverview` flat), mas passa a bater no endpoint real (aninhado) e mapear. Isso conserta as 3 páginas sem editá-las e remove o último import do bi_dashboard → subsistema deletável.

**Tech Stack:** FastAPI (backend baked, deploy blue-green), Next.js 16 + @tanstack/react-query v5 + axios `@/lib/api` (frontend).

## Global Constraints
- Backend durável = rebuild blue-green (`scripts/deploy_backend_bluegreen.sh`); docker cp = volátil.
- Frontend build: `NODE_OPTIONS=--max-old-space-size=8192`, pausar det-robot (OOM). Subir com `docker-compose.yml` (serviço `frontend`, :3001), NUNCA prod.yml.
- Nunca fabricar dado: KPI exibido == fato no banco. Endpoint `/financial/dashboard` já é 100% real (bank_transactions/accounts/receivables).
- Commits `--no-verify`, `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Branch atual `fase5-hermes-camada-cognitiva` (não default, ok commitar).

---

### Task 1: Hook `useFinancialOverview` real (conserta os 4 KPIs)

**Files:**
- Create: `frontend/src/hooks/financial/useFinancialOverview.ts`
- Modify: `frontend/src/hooks/financial/useFinancial.ts` (remover bloco bi_dashboard 144-150; re-exportar o novo hook)
- Modify: `frontend/src/hooks/financial/index.ts:104-107` (dropar useBIDashboards/useBIDashboard/biDashboardKeys; manter useFinancialOverview)

**Interfaces:**
- Produces: `useFinancialOverview(params?: { condominio_id?: string })` → react-query result com `data: IFinancialOverview` (`{receita_total, despesa_total, saldo, inadimplencia}`) e `isLoading`.
- Consumes: `api` de `@/lib/api`; `IFinancialOverview` de `@/types/financial`; endpoint `GET /api/v1/financial/dashboard` (retorna `{saldo:{atual}, mes_atual:{entradas,saidas}, contas_receber:{vencido}}`).

- [ ] **Step 1: criar o hook real**

```ts
// frontend/src/hooks/financial/useFinancialOverview.ts
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { IFinancialOverview } from '@/types/financial';

/** KPIs do financeiro a partir do endpoint REAL /financial/dashboard (aninhado → flat). */
export function useFinancialOverview(params?: { condominio_id?: string }) {
  return useQuery({
    queryKey: ['financial-overview', params?.condominio_id ?? null],
    queryFn: async (): Promise<IFinancialOverview> => {
      const { data } = await api.get('/api/v1/financial/dashboard', { params });
      return {
        receita_total: Number(data?.mes_atual?.entradas ?? 0),
        despesa_total: Number(data?.mes_atual?.saidas ?? 0),
        saldo: Number(data?.saldo?.atual ?? 0),
        inadimplencia: Number(data?.contas_receber?.vencido ?? 0),
      };
    },
    staleTime: 60_000,
  });
}
```

- [ ] **Step 2:** em `useFinancial.ts`, remover o bloco BI (linhas ~144-150: `export * from '.../financial-bi-dashboard...'` e o `export { ...as useBIDashboards/useBIDashboard/useFinancialOverview/biDashboardKeys }`). No lugar: `export { useFinancialOverview } from './useFinancialOverview';`

- [ ] **Step 3:** em `hooks/financial/index.ts`, remover `useBIDashboards`, `useBIDashboard`, `biDashboardKeys` (linhas 104,105,107); manter `useFinancialOverview` (106) apontando pro novo.

- [ ] **Step 4 (verify):** `cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep -iE "useFinancialOverview|financial-bi-dashboard|IFinancialOverview" || echo "sem erros ligados ao hook"`. Esperado: sem erros nessas refs.

---

### Task 2: Remover types gerados + placeholder do bi_dashboard (frontend)

**Files:**
- Delete: `frontend/src/types/generated/financial/financial-bi-dashboard/` (dir)
- Modify: `frontend/src/types/temp-placeholders.d.ts:26` (remover o re-export do bi-dashboard)

- [ ] **Step 1:** apagar o dir gerado `financial-bi-dashboard/`.
- [ ] **Step 2:** remover a linha 26 de `temp-placeholders.d.ts`.
- [ ] **Step 3 (verify):** `grep -rn "financial-bi-dashboard" frontend/src` → só pode sobrar ZERO (ou nada). Esperado: vazio.

---

### Task 3: Deletar o subsistema backend + mount + testes

**Files:**
- Delete: `backend/modules/financial/bi_dashboard/` (24 arquivos)
- Modify: `backend/main_production.py` (remover import linha ~753 `bi_dashboard_router,` e o `include_router(bi_dashboard_router...)` ~792)
- Delete: `backend/tests/test_bi_dashboard_api.py`, `backend/tests/test_bi_dashboard_models.py`, `backend/tests/modules/analytics/test_bi_dashboard_models.py`
- Modify: `backend/tests/test_critical_modules.py` (remover `test_import_bi_dashboard`), `backend/tests/test_aggregator_imports.py:203` (remover `"bi_dashboard_router"`), `backend/extract_financial_openapi.py` (remover import+include bi_dashboard)

- [ ] **Step 1:** remover import e include_router em `main_production.py`.
- [ ] **Step 2:** apagar o dir `bi_dashboard/` e os 3 arquivos de teste.
- [ ] **Step 3:** limpar refs em test_critical_modules, test_aggregator_imports, extract_financial_openapi.
- [ ] **Step 4 (verify import):** `docker cp` dos arquivos editados + `docker exec ... python -c "import main_production"` deve importar sem erro (app boota sem o router). Ou verify pós-deploy.
- [ ] **Step 5 (verify grep):** `grep -rn "bi_dashboard" backend/modules backend/main_production.py` → ZERO fora de eventuais comentários.

---

### Task 4: Deploy + verificação end-to-end

- [ ] **Step 1:** commit backend+frontend (source) numa leva.
- [ ] **Step 2:** deploy backend blue-green (`scripts/deploy_backend_bluegreen.sh`), aguardar green healthy.
- [ ] **Step 3 (verify backend):** `curl -s -o /dev/null -w '%{http_code}' localhost:8080/api/v1/financial/bi-dashboard/bi/dashboards/stats` → **404** (rota morta). Controle: `/api/v1/financial/dashboard` → 401 (viva+auth).
- [ ] **Step 4:** rebuild+deploy frontend (pausar det-robot, NODE_OPTIONS=8192, docker-compose.yml serviço frontend, purgar `.next/static`).
- [ ] **Step 5 (verify KPI real):** provar in-process/via query que `/financial/dashboard` retorna saldo/entradas/saidas/vencido reais; na tela `modulos/financeiro`, os 4 KPIs deixam de ser `undefined`/`R$ 0,00`. Oráculo: valor == banco.

**Rollback:** tudo num commit; `git revert` + redeploy. Nada de migration/DB (as tabelas `financial_dashboards`/`financial_kpis` ficam órfãs, inertes — não deletar dado; só código).
