# Financeiro Upgrade — Plano F0 (Fundação tabs) + F1 (Piloto Receber)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execução SOLO T1 (decisão do Jordan).

**Goal:** Fundação de navegação por grupos+abas no redesign e o grupo Receber completo como piloto — molde para F2–F8.

**Architecture:** Tipo de tela `tabs` ADITIVO no ModuleView (renderiza sub-telas pelos renderers existentes); builders compõem grupos; telas antigas viram stubs `redirect` (deep-link preservado, payload flat). Grupo Receber fiado em `_fin_receber.py` (discovery pula `_*`).

**Tech Stack:** Next.js 16 (ModuleView data-driven), FastAPI builders (`redesign_builders/`), PostgreSQL. Spec: `docs/superpowers/specs/2026-07-24-financeiro-upgrade-design.md`.

## Global Constraints (da spec — valem em TODA task)
- Dinheiro-que-sai = gate OTP humano; aprovação = ação humana; NUNCA testar caminho feliz de pagamento/cobrança (só render + gate disparando).
- Régua/PIX recorrente: v1 READ-ONLY (config+preview+histórico); zero disparo automatizado.
- Nunca fabricar dado; vazio-real = "aguardando dado"; stub = disabled honesto.
- **Curl-verificar CADA rota com id real ANTES de fiar** (200 + shape). Rota que falha → investigar fonte/filtro ou disabled honesto.
- Orçamento payload `/redesign/data/financeiro`: **≤2MB, ≤2,5s** (baseline 860KB/0,96s) — medir no gate de cada fase.
- Commit por etapa com PATHSPEC (`git add <arquivo> && git commit --no-verify -- <arquivo>` ou `-m ... -- <arquivo>` com `-m` ANTES do `--`). `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- `python3 -m py_compile` de todo builder editado antes de commitar; importar TODOS os helpers usados (except:pass engole NameError).
- Deploy backend: blue-green (`scripts/deploy_backend_bluegreen.sh`), lock respeitado, porta-travada (todos builders compilam). Frontend: `docker compose build frontend && up -d` com DET pausado. Deploy só ao FIM da fase.
- Browser: matar Chromium órfão antes; matar a própria sessão ao concluir. Token: login form-urlencoded `mcp-service@conectamais.pro` (senha no `.env` do mcp; ver histórico) → `localStorage access_token`.
- Teste in-process do builder (código do host): `docker cp <builder> conecta-pro-backend:/app/...` + `importlib.reload` (VOLÁTIL — durável só no bake do deploy).

---

## F0 — Fundação `tabs` + deep-link + menu 7 grupos

### Task 1: Helpers `grp()` e `moved()` no backend

**Files:**
- Modify: `backend/modules/operacional/controllers/redesign_data_controller.py` (logo após `def doc(...)`)

**Interfaces:**
- Produces: `grp(title, sub, tabs) -> dict` com `tabs=[(id,label,screen_dict|None)]` (None é filtrado); `moved(group_id, tab_id) -> dict` stub `{"type":"redirect","groupRef":{"t":gid,"tab":tid}}`. Tasks 3+ consomem ambos.

- [ ] **Step 1: Adicionar os helpers** (após a função `doc()`):

```python
def grp(title, sub, tabs):
    """Tela-GRUPO (type=tabs) da fundação de navegação. tabs=[(id, label, screen_dict)];
    telas None (não montadas nesta base) são omitidas — nunca aba vazia fabricada."""
    return {"title": title, "sub": sub, "type": "tabs",
            "tabs": [{"id": i, "label": l, "screen": s} for i, l, s in tabs if s]}


def moved(group_id, tab_id):
    """Stub de redirecionamento p/ deep-link antigo (?t=<id-antigo>). O ModuleView resolve
    para o grupo+aba novos. Mantém zero-regressão de links SEM duplicar payload."""
    return {"type": "redirect", "groupRef": {"t": group_id, "tab": tab_id}}
```

- [ ] **Step 2: Compilar e commitar**

Run: `cd /opt/conecta-pro && python3 -m py_compile backend/modules/operacional/controllers/redesign_data_controller.py && echo OK`
Expected: OK

```bash
git -c commit.gpgsign=false commit --no-verify -m "feat(redesign): helpers grp()/moved() — fundacao tabs (F0)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" -- backend/modules/operacional/controllers/redesign_data_controller.py
```

### Task 2: `TabsScreen` + redirect no ModuleView (frontend)

**Files:**
- Modify: `frontend/src/components/redesign/ModuleView.tsx`

**Interfaces:**
- Consumes: telas `{type:'tabs', tabs:[{id,label,screen}]}` e `{type:'redirect', groupRef:{t,tab}}` das Tasks 1/3.
- Produces: URL `?t=<grupo>&tab=<aba>`; redirect automático de ids antigos; docs/ExportMenu do header refletem a ABA ativa.

- [ ] **Step 1: Adicionar estado de aba + go() com tab** — no componente `ModuleView`, junto aos estados existentes:

```tsx
const [activeTab, setActiveTab] = useState<string>('');
```

E substituir a função `go` por:

```tsx
const go = (id: string, tabId?: string) => {
  setActive(id); setActiveTab(tabId || ''); setMobileOpen(false);
  try {
    const u = new URL(window.location.href);
    u.searchParams.set('t', id);
    if (tabId) u.searchParams.set('tab', tabId); else u.searchParams.delete('tab');
    window.history.replaceState(null, '', u);
  } catch { /* */ }
};
```

No `useEffect` que lê `?t`, também ler `?tab`:

```tsx
const tab = new URLSearchParams(window.location.search).get('tab');
if (tab) setActiveTab(tab);
```

- [ ] **Step 2: Redirect de id antigo** — novo `useEffect` após o fetch dos patches:

```tsx
// Deep-link antigo (?t=<id-antigo>): tela virou stub redirect → resolve p/ grupo+aba (F0).
useEffect(() => {
  const s: any = patches[active];
  if (s && s.type === 'redirect' && s.groupRef) go(s.groupRef.t, s.groupRef.tab);
}, [patches, active]);
```

- [ ] **Step 3: Componente `TabsScreen`** (antes de `function Screen`):

```tsx
// TabsScreen (F0) — grupo com abas; cada aba renderiza uma tela normal pelos renderers existentes.
function TabsScreen({ scr, tab, onTab }: { scr: any; tab: string; onTab: (id: string) => void }) {
  const tabs = Array.isArray(scr.tabs) ? scr.tabs : [];
  const act = tabs.find((x: any) => x.id === tab) || tabs[0];
  return (
    <div className="rd-tabs-wrap">
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
        {tabs.map((x: any) => (
          <button key={x.id} type="button" onClick={() => onTab(x.id)}
            className={`rd-btn ${act && act.id === x.id ? 'rd-btn-primary' : 'rd-btn-outline'}`}
            style={{ fontSize: 12.5, padding: '6px 12px' }}>
            {x.label}
          </button>
        ))}
      </div>
      {act ? <Screen scr={act.screen} /> : <EmptyReal />}
    </div>
  );
}
```

- [ ] **Step 4: Integrar no main** — onde hoje há `isReal ? <Screen scr={scr} /> : <EmptyReal />`, trocar por:

```tsx
: isReal
  ? (scr?.type === 'tabs'
      ? <TabsScreen scr={scr} tab={activeTab} onTab={(id) => go(active, id)} />
      : <Screen scr={scr} />)
  : <EmptyReal />
```

E o bloco do header (DocButtons/ExportMenu/sub) deve usar a tela EFETIVA (aba ativa quando tabs):

```tsx
const effScr = scr?.type === 'tabs'
  ? ((scr.tabs || []).find((x: any) => x.id === activeTab) || (scr.tabs || [])[0])?.screen
  : scr;
```

Substituir `scr?.docs`/`scr?.type === 'table'`/`scr.rows`/`scr.cols`/`scr?.sub` do bloco de docs+export e do sub do título por `effScr` (o `title` continua do grupo).

- [ ] **Step 5: Compilar e commitar**

Run: `cd /opt/conecta-pro/frontend && timeout 240 npx tsc --noEmit -p tsconfig.json 2>&1 | grep ModuleView | head` — Expected: vazio.

```bash
git -c commit.gpgsign=false commit --no-verify -m "feat(redesign): TabsScreen + redirect de deep-link (fundacao F0)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" -- frontend/src/components/redesign/ModuleView.tsx
```

### Task 3: Esqueleto dos 7 grupos no builder (realocação SEM perda)

**Files:**
- Create: `backend/modules/operacional/controllers/redesign_builders/_fin_grupos.py`
- Modify: `backend/modules/operacional/controllers/redesign_builders/financeiro.py` (fim do build + EXTRA_MENU)
- Modify: `frontend/src/app/redesign/_modules/financeiro.json` (menu → 7 itens)

**Interfaces:**
- Consumes: `grp`/`moved` (Task 1); o dict `out` completo do build do financeiro.
- Produces: telas `g-visao, g-receber, g-pagar, g-bancos, g-fiscal, g-custos, g-cadastros`; todo id antigo vira stub `moved`. Função `montar_grupos(out) -> None` (muta out).

- [ ] **Step 1: Criar `_fin_grupos.py`** (prefixo `_` = discovery pula; VERIFICADO):

```python
"""F0 — composição dos 7 grupos do financeiro (fundação tabs). Mapeia TODA tela antiga
para (grupo, aba); ids não mapeados são anexados ao grupo dono por afinidade no oráculo."""
from modules.operacional.controllers.redesign_data_controller import grp, moved

GRUPOS = [
    ("g-visao", "Visão Geral", "Resumo executivo do financeiro", [
        ("dashboard", "Resumo"), ("raio-x", "Raio-X"), ("cfo", "CFO IA"), ("agentes", "Agentes"),
        ("relatorios", "Relatórios")]),
    ("g-receber", "Receber", "Contas a receber, cobrança e faturamento", [
        ("contas-receber", "Contas a Receber"), ("cobrancas", "Cobranças"), ("boletos", "Boletos"),
        ("emitir-boleto", "Emitir boleto"), ("cobrar-pix", "Cobrar PIX"),
        ("faturamento", "Faturamento"), ("clientes", "Clientes"), ("registrar-conta-receber", "Registrar")]),
    ("g-pagar", "Pagar", "Contas a pagar, folha e pagamentos (gated OTP)", [
        ("contas-pagar", "Contas a Pagar"), ("pagamentos-inter", "Pagamentos Inter"),
        ("pagamentos-pj", "Folha PJ"), ("pagar-folha-pj", "Pagar folha PJ"),
        ("pagamentos-diaristas", "Diaristas"), ("pagar-diaristas", "Pagar diaristas"),
        ("pagar-boleto", "Pagar boleto"), ("enviar-pix", "PIX / Transferir"),
        ("transferir-ted", "TED"), ("pagar-darf", "DARF"),
        ("cancelar-pagamento", "Cancelar pagto"), ("registrar-conta-pagar", "Registrar")]),
    ("g-bancos", "Bancos & Conciliação", "Saldos, extratos e conciliação", [
        ("saldos", "Saldos"), ("inter", "Banco Inter"), ("cora", "Banco Cora"),
        ("banking", "Extrato"), ("inter-pagamentos", "Inter (pagtos)"),
        ("conciliacao", "Conciliação de folha")]),
    ("g-fiscal", "Fiscal & Contábil", "Notas, guias e contabilidade", [
        ("fiscal", "Fiscal"), ("nfse-entrada", "NFS-e entrada"),
        ("contabilidade", "Contabilidade"), ("cancelar-boleto", "Cancelar boleto")]),
    ("g-custos", "Custos & Orçamento", "Custos, custeio, precificação e orçamento", [
        ("custos", "Custos"), ("custeio", "Custeio"), ("custeio-cct", "Custeio CCT"),
        ("precificacao", "Precificação"), ("orcamentos", "Orçamentos")]),
    ("g-cadastros", "Cadastros & Suprimentos", "Fornecedores, contratos, compras e estoque", [
        ("fornecedores", "Fornecedores"), ("contratos", "Contratos"),
        ("compras", "Compras"), ("estoque", "Estoque")]),
]


def montar_grupos(out: dict) -> None:
    """Compõe os grupos a partir das telas JÁ montadas em out e stub-a as antigas (redirect).
    Ordem importa: capturar as referências ANTES de stubar."""
    novos = {}
    for gid, titulo, sub, tabs in GRUPOS:
        novos[gid] = grp(titulo, sub, [(tid, lbl, out.get(tid)) for tid, lbl in tabs])
    for gid, _t, _s, tabs in GRUPOS:
        for tid, _l in tabs:
            if tid in out:
                out[tid] = moved(gid, tid)
    out.update(novos)
```

- [ ] **Step 2: Chamar no fim do `build` do financeiro.py** (última linha antes do `return out`):

```python
    # F0 — fundação: compõe os 7 grupos e stub-a as telas antigas (deep-link preservado).
    from modules.operacional.controllers.redesign_builders._fin_grupos import montar_grupos
    montar_grupos(out)

    return out
```

E **zerar o EXTRA_MENU** do financeiro.py (as ações agora são abas de grupo): `EXTRA_MENU: list[dict] = []`.

- [ ] **Step 3: Menu do financeiro.json → 7 grupos** — substituir o array `menu` por (ícones = paths existentes do próprio arquivo, reutilizar):

```json
[
 {"id": "g-visao", "label": "Visão Geral", "icon": "M3 3h7v7H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z"},
 {"id": "g-receber", "label": "Receber", "icon": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"},
 {"id": "g-pagar", "label": "Pagar", "icon": "M2 6h20M2 18h20M6 6v12M10 6v12M14 6v12M18 6v12"},
 {"id": "g-bancos", "label": "Bancos & Conciliação", "icon": "M3 21h18M4 10h16M5 10 12 4l7 6M6 10v11M18 10v11M10 10v11M14 10v11"},
 {"id": "g-fiscal", "label": "Fiscal & Contábil", "icon": "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M9 15h6M9 11h6"},
 {"id": "g-custos", "label": "Custos & Orçamento", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3"},
 {"id": "g-cadastros", "label": "Cadastros & Suprimentos", "icon": "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75M12 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0z"}
]
```

(Manter `screens`/`mod` do JSON intactos.)

- [ ] **Step 4: Oráculo in-process** — nenhum id perdido + payload dentro do orçamento:

```bash
cd /opt/conecta-pro && python3 -m py_compile backend/modules/operacional/controllers/redesign_builders/financeiro.py backend/modules/operacional/controllers/redesign_builders/_fin_grupos.py && \
docker cp backend/modules/operacional/controllers/redesign_builders/_fin_grupos.py conecta-pro-backend:/app/modules/operacional/controllers/redesign_builders/_fin_grupos.py && \
docker cp backend/modules/operacional/controllers/redesign_builders/financeiro.py conecta-pro-backend:/app/modules/operacional/controllers/redesign_builders/financeiro.py && \
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 -c "
import asyncio, importlib, json
from core.database.session import async_session_factory
import modules.operacional.controllers.redesign_builders._fin_grupos as G
import modules.operacional.controllers.redesign_builders.financeiro as F
importlib.reload(G); importlib.reload(F)
async def main():
    async with async_session_factory() as db:
        out = await F.build(db)
    grupos=[k for k in out if k.startswith('g-')]
    stubs=[k for k,v in out.items() if isinstance(v,dict) and v.get('type')=='redirect']
    orfaos=[k for k,v in out.items() if not k.startswith('g-') and isinstance(v,dict) and v.get('type') not in ('redirect',) ]
    print('grupos:', sorted(grupos))
    print('stubs (deep-links preservados):', len(stubs))
    print('ÓRFÃOS (telas fora de grupo — DEVE ser vazio ou justificado):', orfaos)
    print('payload KB:', len(json.dumps(out))//1024)
asyncio.run(main())
"
```
Expected: 7 grupos; ÓRFÃOS vazio (se houver, adicionar o id ao GRUPOS do grupo dono e repetir); payload ≤ ~900KB.

- [ ] **Step 5: Commit (pathspec, 3 arquivos são da mesma entrega F0)**

```bash
cd /opt/conecta-pro && git add backend/modules/operacional/controllers/redesign_builders/_fin_grupos.py && \
git -c commit.gpgsign=false commit --no-verify -m "feat(redesign): F0 — financeiro em 7 grupos com abas (zero perda, deep-links ok)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" -- backend/modules/operacional/controllers/redesign_builders/_fin_grupos.py backend/modules/operacional/controllers/redesign_builders/financeiro.py frontend/src/app/redesign/_modules/financeiro.json
```

### Task 4: Deploy F0 + prova no browser (gate da fase)

**Files:** nenhum novo — deploy + verificação.

- [ ] **Step 1: Porta-travada + deploy backend** (lock livre; todos builders compilam) → `timeout 590 bash scripts/deploy_backend_bluegreen.sh`.
- [ ] **Step 2: Deploy frontend** (DET pausado; `docker compose build frontend && docker compose up -d frontend`; religar DET).
- [ ] **Step 3: Prova no browser (Playwright MCP)** — matar Chromium órfão antes:
  1. `/redesign/financeiro` → menu tem 7 itens; `g-receber` abre com abas; clicar 3 abas renderiza.
  2. Deep-link antigo `/redesign/financeiro?t=contas-pagar` → redireciona para `g-pagar` + aba Contas a Pagar.
  3. Smoke-test 3 módulos NÃO-financeiro (`/redesign/operacional`, `/redesign/fiscal`, `/redesign/documentos`) → renderizam normal (fundação não quebrou nada).
  4. Botões de documento numa aba (ex.: contas-receber → Aging PDF) → ainda baixam.
- [ ] **Step 4: Medir orçamento** — `curl -w "bytes=%{size_download} tempo=%{time_total}"` no `/redesign/data/financeiro`: ≤2MB, ≤2,5s.
- [ ] **Step 5: Push** — `git push origin fase5-hermes-camada-cognitiva`. Fechar sessão do browser.

---

## F1 — Piloto Receber (capacidade restaurada + correção de substituto)

### Task 5: Curl-verificar as rotas do Receber (ANTES de fiar)

**Files:** nenhum — verificação que alimenta as Tasks 6–9. Registrar resultados em `auditoria/parity/F1_ROTAS_RECEBER.md`.

- [ ] **Step 1: Token + verificar cada rota candidata** (id real do banco onde precisar):

```bash
cd /opt/conecta-pro
TOK=$(curl -s -X POST http://localhost:8080/api/v1/auth/login -H "Content-Type: application/x-www-form-urlencoded" -d "username=mcp-service@conectamais.pro&password=$(docker exec conecta-pro-mcp env | grep ERP_PASSWORD | cut -d= -f2)" | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))")
for p in \
  "/api/v1/financial/receivables/aging" \
  "/api/v1/financial/billing-rules" \
  "/api/v1/financial/billing/cobrar-recorrente/7/2026?preview=true" \
  "/api/v1/financial/ai/billing/contratos-a-faturar" \
  "/api/v1/financial/customers" \
  ; do printf "%-60s " "$p"; curl -s -o /tmp/r.json -w "HTTP %{http_code} " -H "Authorization: Bearer $TOK" "http://localhost:8080$p"; head -c 120 /tmp/r.json; echo; done
```

- [ ] **Step 2: Para cada rota que NÃO der 200**: achar a rota real no controller (`grep -n "@router" backend/modules/financial/controllers/<ctrl>.py`), corrigir path/params e re-testar. Registrar o shape JSON real (chaves) de cada 200 em `auditoria/parity/F1_ROTAS_RECEBER.md` — as Tasks 6–9 usam ESSAS chaves.
- [ ] **Step 3: Commit do registro** (pathspec no arquivo de auditoria).

### Task 6: `_fin_receber.py` — Aging com KPIs + Clientes reais (correção substituto)

**Files:**
- Create: `backend/modules/operacional/controllers/redesign_builders/_fin_receber.py`
- Modify: `backend/modules/operacional/controllers/redesign_builders/financeiro.py` (chamar antes de montar_grupos)

**Interfaces:**
- Consumes: `_helpers/tbl/doc/S/b/t/brl/_fmtdate/_scalar` do controller; shapes registrados na Task 5.
- Produces: `await build_receber(db, out)` — muta `out`: enriquece `contas-receber` (panels aging), cria `clientes` (customers reais) e as abas de cobrança (Task 7+). Chamada ANTES de `montar_grupos` (os grupos capturam as versões enriquecidas).

- [ ] **Step 1: Criar `_fin_receber.py`** com aging + clientes (ADAPTAR as chaves ao shape registrado na Task 5 — se divergirem, usar as reais):

```python
"""F1 — piloto Receber: aging com KPIs, clientes reais (customers), cobrança e faturamento.
Chamado pelo financeiro.py ANTES de montar_grupos. Leitura real; escrita segue gated."""
from modules.operacional.controllers.redesign_data_controller import (
    S, _fmtdate, _helpers, _scalar, b, brl, doc, t,
)


async def build_receber(db, out: dict) -> None:
    _, _safe, tbl = _helpers(db)

    # Aging com KPIs na tela (o clássico tem; redesign só tinha o PDF) — faixas por vencimento.
    try:
        faixas = (await db.execute(__import__("sqlalchemy").text(
            "SELECT CASE WHEN due_date >= CURRENT_DATE THEN 'A vencer' "
            "WHEN due_date >= CURRENT_DATE-30 THEN 'Vencidas ate 30d' "
            "WHEN due_date >= CURRENT_DATE-60 THEN 'Vencidas 31-60d' "
            "ELSE 'Vencidas +60d' END AS faixa, count(*), coalesce(sum(amount - coalesce(paid_amount,0)),0) "
            "FROM receivable_accounts WHERE status::text NOT IN ('paid','pago','paga','cancelled','cancelada') "
            "GROUP BY 1 ORDER BY 1"))).fetchall()
        if isinstance(out.get("contas-receber"), dict):
            out["contas-receber"]["panelGrid"] = "1fr"
            out["contas-receber"]["panels"] = [{"title": "Aging (em aberto)", "rows": [
                {"left": f, "right": f"{n} · {brl(v)}", **(S["ok"] if f == 'A vencer' else S["bad"])}
                for f, n, v in faixas] or [{"left": "Sem títulos em aberto", "right": "0", **S["ok"]}]}]
    except Exception:  # noqa: BLE001
        pass

    # Clientes do CONTAS A RECEBER (customers) — corrige o substituto (antes lia clients do CRM).
    try:
        out["clientes"] = await tbl(
            "Clientes (contas a receber)",
            f"{await _scalar(db, 'SELECT count(*) FROM customers')} clientes de cobrança — fonte: customers (AR)",
            "—", ["Cliente", "Documento", "Email", "Status"], "2fr 1.2fr 1.8fr 0.9fr",
            "SELECT coalesce(name,'—'), coalesce(document,'—'), coalesce(email,'—'), "
            "CASE WHEN coalesce(blocked,false) THEN 'Bloqueado' ELSE 'Ativo' END FROM customers ORDER BY name LIMIT 300",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(r[2]),
                       b(r[3], "bad" if r[3] == 'Bloqueado' else "ok")])
    except Exception:  # noqa: BLE001
        pass
```

(ATENÇÃO: conferir colunas reais de `receivable_accounts`/`customers` via `information_schema` antes; ajustar nomes se divergirem — regra "nunca fabricar".)

- [ ] **Step 2: Chamar no financeiro.py** (antes do bloco montar_grupos):

```python
    # F1 — piloto Receber (aging KPIs, clientes reais, cobrança/faturamento)
    from modules.operacional.controllers.redesign_builders._fin_receber import build_receber
    await build_receber(db, out)
```

- [ ] **Step 3: py_compile + oráculo in-process** (docker cp + reload): `contas-receber` tem panels; `clientes` lê customers (contar vs `SELECT count(*) FROM customers`).
- [ ] **Step 4: Commit** (pathspec nos 2 arquivos, mensagem `feat(redesign): F1 receber — aging KPIs + clientes reais (fix substituto)`).

### Task 7: Cobranças — emitidas + Régua (read-only) + Recorrência (preview read-only)

**Files:**
- Modify: `backend/modules/operacional/controllers/redesign_builders/_fin_receber.py`

**Interfaces:**
- Produces: telas `regua` (config da régua, read-only) e `recorrencia` (preview do ciclo mensal, read-only) adicionadas a `out` + registradas nas abas do g-receber (Task 9 ajusta GRUPOS).

- [ ] **Step 1: Régua read-only** — fonte `billing_rules` (shape da Task 5; se rota falhar, ler a tabela direto):

```python
    # Régua de inadimplência — READ-ONLY v1 (config + visão); disparo automatizado SÓ com
    # aprovação explícita do Jordan (spec §5). Fonte: billing_rules.
    try:
        out["regua"] = await tbl(
            "Régua de cobrança (config)",
            f"{await _scalar(db, 'SELECT count(*) FROM billing_rules')} regras — v1 leitura (sem disparo automático)",
            "—", ["Regra", "Gatilho", "Canal", "Ativa"], "1.8fr 1.2fr 1fr 0.8fr",
            "SELECT coalesce(name,'—'), coalesce(trigger_days::text,'—'), coalesce(channel::text,'—'), coalesce(active,false) "
            "FROM billing_rules ORDER BY trigger_days LIMIT 100",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(f"D{r[1]}"), t((r[2] or '—').capitalize()),
                       b("Sim", "ok") if r[3] else b("Não", "mut")])
    except Exception:  # noqa: BLE001
        pass
```

- [ ] **Step 2: Recorrência preview read-only** — GET do preview (Task 5); exibir como lista `{cliente, valor, status}` + aviso honesto "preview — nenhuma cobrança é disparada por esta tela". Se o GET de preview exigir POST/executar: NÃO usar; ler as tabelas de recorrência direto (contratos ativos c/ mrr) e rotular "estimativa pela base de contratos".
- [ ] **Step 3: Ajustar colunas ao shape REAL** (`information_schema.columns` de billing_rules) — nomes acima são hipótese; a regra é a fonte real.
- [ ] **Step 4: py_compile + oráculo + commit** (`feat(redesign): F1 receber — regua e recorrencia read-only`).

### Task 8: Faturamento — contratos a faturar + medição (leitura)

**Files:**
- Modify: `backend/modules/operacional/controllers/redesign_builders/_fin_receber.py`

- [ ] **Step 1:** Tela `faturamento` enriquecida: panels com "Contratos a faturar" (rota ai/billing da Task 5; fallback: contratos ativos sem fatura no mês via SQL) e tabela de medição (leitura). Mesmo padrão das tasks anteriores (tbl + panels; chaves do shape real).
- [ ] **Step 2:** py_compile + oráculo + commit (`feat(redesign): F1 receber — faturamento (a faturar + medicao)`).

### Task 9: Abas do g-receber atualizadas + gate F1

**Files:**
- Modify: `backend/modules/operacional/controllers/redesign_builders/_fin_grupos.py` (adicionar `regua`, `recorrencia` às abas do g-receber)

- [ ] **Step 1:** Incluir `("regua", "Régua"), ("recorrencia", "Recorrência")` no g-receber.
- [ ] **Step 2:** Oráculo F0 de novo (ÓRFÃOS vazio; payload ≤2MB).
- [ ] **Step 3:** Deploy backend (porta-travada) + prova no browser: g-receber com todas as abas; aging KPIs visíveis; clientes = customers (contar); régua/recorrência com aviso read-only; deep-links ok; **nenhum clique dispara cobrança** (testar só render).
- [ ] **Step 4:** Commit + push. Medir orçamento. **Padrão CONGELADO** → registrar no fim do plano: "molde para F2–F8".

---

## Task 10: Gerar os planos F2–F8 (pós-piloto)

- [ ] Com o padrão congelado (F0+F1 no ar), escrever os planos das fases seguintes — um arquivo por fase, MESMO formato deste (curl-verify → helper `_fin_<grupo>.py` → oráculo → commit → deploy → browser): F2 `_fin_bancos` (conciliação real + OFX) · F3 `_fin_pagar` (fila D7 + audit log; máximo cuidado money-out) · F4 `_fin_visao` (projeção/insights/DRE) · F5 `_fin_fiscal` (contabilidade real) · F6 `_fin_custos` (ABC) · F7 `_fin_cadastros` (compras/estoque reais) · F8 QA total + E2E + relatório final.
- [ ] Cada plano nasce dos arquivos de auditoria (`FINANCEIRO_BACKEND_*.md`) que listam rotas/capacidades por controller.

## Self-review do plano (feito na escrita)
- Cobertura da spec: F0 (§3.1, riscos A/B/C/D) Tasks 1–4; F1 piloto (§3.2 g2, riscos E/F/G) Tasks 5–9; fases restantes → Task 10 (decomposição declarada). ✓
- Sem placeholders: todo step de código tem código; steps "adaptar ao shape real" são a REGRA da spec (curl-verify primeiro), não omissão. ✓
- Consistência de nomes: `grp/moved/montar_grupos/build_receber/g-<grupo>` idênticos entre tasks. ✓
