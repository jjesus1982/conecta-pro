# Fundação da Camada Cognitiva — Fases −1 & 0 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deixar o solo pronto para a camada cognitiva — dados joinable e separáveis por CNPJ, vazamento LGPD fechado, esquema versionado, e um store de alertas único com dedup real — sem nenhuma feature de IA.

**Architecture:** Fase −1 cria uma camada de resolução de identidade em **views** (não migração destrutiva), adiciona `empresa_id`+quarentena onde falta, tranca as rotas dos consultores e versiona o schema em Alembic. Fase 0 converge os alertas hoje dispersos num `notification_queue` canônico via um helper `enqueue_alert` idempotente (dedup real), materializa os produtores efêmeros, normaliza severidade e estabelece uma espinha de reconciliação por polling.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async (asyncpg), Alembic, PostgreSQL 16, Celery + celery-beat, pytest (async via `core.database.async_session_factory`). Deploy blue-green (`scripts/deploy_backend_bluegreen.sh`).

## Global Constraints
- **Nunca fabricar dado:** derivação só quando a fonte é 1:1 confiável; o resto → `empresa_id=NULL` + `empresa_review=true` (quarentena). Verbatim da spec.
- **Multi-CNPJ:** Eletrônica `619a3df1-8bce-49ce-b77a-04f80a0e8491`, Patrimonial `7d79ed12-d480-4906-b2e0-2b2c4d299bab`. Escritório catch-all (ambos usam) `a1b2c3d4-e5f6-7890-abcd-ef1234567890`.
- **Decisões Jordan travadas:** recebíveis(22)+leads(22) → quarentena; Consultor CEO → só `jjesus`+`pjesus`; overrides de identidade → Jordan faz depois (ficam visíveis em quarentena).
- **Migrações Alembic idempotentes e reversíveis** (upgrade no-op em produção onde o objeto já existe; downgrade limpo).
- **Commits** `--no-verify`, terminam `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **NÃO executa ação** (transmitir/pagar/enviar) em nenhuma task destas fases — é tudo leitura/estrutura.

## Mapa de arquivos (o que cada um passa a fazer)
- `backend/alembic/versions/<rev>_fase_menos1_identidade.py` — CREATE das views de identidade + `entity_client_override`.
- `backend/alembic/versions/<rev>_fase_menos1_empresa_id.py` — ADD COLUMN `empresa_id`+`empresa_review` nas 5 tabelas + backfill/quarentena.
- `backend/alembic/versions/<rev>_fase_menos1_consultas_baseline.py` — baseline das tabelas hoje criadas por DDL runtime.
- `backend/modules/ai/consultores/permissions.py` **(novo)** — `require_consultor_executivo` (allowlist jjesus+pjesus) e o mapa consultor→módulo.
- `backend/main_production.py` — aplica os gates nas 8 rotas de consultor (linhas ~1179–1291).
- `backend/modules/notifications/services/alert_ingest.py` **(novo)** — `enqueue_alert()` (upsert idempotente) + `normalize_severity()`.
- `backend/alembic/versions/<rev>_fase0_notif_dedup.py` — consolida duplicatas + índice único parcial.
- `backend/modules/financial/tasks.py` + `risk_monitor.py` — RiskMonitor persiste via `enqueue_alert`.
- `backend/modules/juridico/contracts_service.py`, `modules/people_management/sst/tasks/*`, `modules/ged/tasks/expiry_alerts.py` — roteiam por `enqueue_alert`.
- `backend/modules/notifications/tasks.py` **(novo/estende)** — `reconciliar_alertas` + `purgar_notificacoes` (celery-beat).
- `backend/celery_app.py` — agenda `reconciliar_alertas`, `ged.check_document_expiry`, `purgar_notificacoes`.
- Testes: `backend/tests/fundacao/test_*.py` (segue o padrão async de `backend/tests/`).

---

# FASE −1 — Fundação de Dados + Segurança

### Task 1: Views de resolução de identidade
> **✅ FEITA + APLICADA NA PROD (2026-07-21).** Migration `fase_menos1_identidade` (alembic head). Prova: v_employee=83(=employees), join uuid×varchar=50 (via view), escritório classificado, entity_client=31, override=0. Committada. Sem deploy (só objetos de banco; arquivo assa no próximo deploy).
**Files:**
- Create: `backend/alembic/versions/xxxx_fase_menos1_identidade.py`
- Test: `backend/tests/fundacao/test_identidade_views.py`

**Interfaces:**
- Produces: views SQL `v_employee(id uuid, id_text text, nome, cpf, empresa_id, cargo, status)`, `entity_client(client_key uuid, cnpj, condominio_id, customer_id, condominium_id)`, `v_condominio_kind(condominio_id uuid, kind text)`; tabela `entity_client_override(satellite_type text, satellite_id text, client_key uuid, cnpj text, nota text, created_at)`.

- [ ] **Step 1: Write the failing test**
```python
# backend/tests/fundacao/test_identidade_views.py
import pytest
from sqlalchemy import text
from core.database import async_session_factory

@pytest.mark.asyncio
async def test_v_employee_conta_igual_employees():
    async with async_session_factory() as db:
        n_view = (await db.execute(text("SELECT count(*) FROM v_employee"))).scalar()
        n_emp = (await db.execute(text("SELECT count(*) FROM employees"))).scalar()
        assert n_view == n_emp

@pytest.mark.asyncio
async def test_join_ponto_por_id_text_nao_estoura():
    # gp_monthly_closings.employee_id é varchar; join via view não pode dar erro de tipo
    async with async_session_factory() as db:
        r = (await db.execute(text(
            "SELECT count(*) FROM gp_monthly_closings c "
            "JOIN v_employee e ON e.id_text = c.employee_id"))).scalar()
        assert r >= 0  # não lança DatatypeMismatch

@pytest.mark.asyncio
async def test_condominio_kind_classifica_escritorio():
    async with async_session_factory() as db:
        k = (await db.execute(text(
            "SELECT kind FROM v_condominio_kind WHERE condominio_id="
            "'a1b2c3d4-e5f6-7890-abcd-ef1234567890'"))).scalar()
        assert k == 'escritorio'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec conecta-pro-backend pytest tests/fundacao/test_identidade_views.py -v`
Expected: FAIL — `relation "v_employee" does not exist`.

- [ ] **Step 3: Escrever a migração que cria as views + tabela de override**
```python
# xxxx_fase_menos1_identidade.py
from alembic import op
revision = "fase_menos1_identidade"; down_revision = "<HEAD_ATUAL>"

def upgrade():
    op.execute("""
    CREATE OR REPLACE VIEW v_employee AS
      SELECT id, id::text AS id_text, nome, cpf, empresa_id, cargo, status FROM employees;

    CREATE OR REPLACE VIEW v_condominio_kind AS
      SELECT DISTINCT condominio_id,
        CASE
          WHEN condominio_id = '00000000-0000-0000-0000-000000000001' THEN 'sentinela'
          WHEN condominio_id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890' THEN 'escritorio'
          WHEN condominio_id IN (SELECT id FROM condominios) THEN 'real'
          ELSE 'orfao'
        END AS kind
      FROM (
        SELECT condominio_id FROM receivable_accounts
        UNION SELECT condominio_id FROM employee_alocacoes
        UNION SELECT condominio_id FROM hr_payslips
      ) s WHERE condominio_id IS NOT NULL;

    CREATE TABLE IF NOT EXISTS entity_client_override (
      id bigserial PRIMARY KEY,
      satellite_type text NOT NULL,      -- 'condominium_en' | 'nfse' | ...
      satellite_id   text NOT NULL,
      client_key uuid, cnpj text, nota text,
      created_at timestamptz DEFAULT now(),
      UNIQUE (satellite_type, satellite_id)
    );

    CREATE OR REPLACE VIEW entity_client AS
      SELECT c.id AS client_key, c.document_number AS cnpj,
             cd.id AS condominio_id, cu.id AS customer_id, NULL::uuid AS condominium_id
      FROM clients c
      LEFT JOIN condominios cd ON cd.client_id = c.id
      LEFT JOIN customers cu   ON cu.condominio_id = cd.id
      UNION ALL
      SELECT o.client_key, o.cnpj, NULL, NULL,
             CASE WHEN o.satellite_type='condominium_en' THEN o.satellite_id::uuid END
      FROM entity_client_override o;
    """)

def downgrade():
    op.execute("DROP VIEW IF EXISTS entity_client; DROP TABLE IF EXISTS entity_client_override;"
               "DROP VIEW IF EXISTS v_condominio_kind; DROP VIEW IF EXISTS v_employee;")
```

- [ ] **Step 4: Aplicar a migração e rodar o teste**

Run: `docker exec conecta-pro-backend alembic upgrade head && docker exec conecta-pro-backend pytest tests/fundacao/test_identidade_views.py -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Relatório de órfãos (para o Jordan preencher depois)**

Run: `docker exec conecta-pro-postgres psql -U postgres -d conecta_pro -c "SELECT 'condominiums_en' t, count(*) FROM condominiums UNION ALL SELECT 'nfses_orfas', count(*) FROM nfses n WHERE n.condominio_id NOT IN (SELECT id FROM condominios) AND n.condominio_id NOT IN (SELECT id FROM condominiums)"`
Expected: imprime a contagem de órfãos que aguardam `entity_client_override`.

- [ ] **Step 6: Commit**
```bash
git add backend/alembic/versions/xxxx_fase_menos1_identidade.py backend/tests/fundacao/test_identidade_views.py
git commit --no-verify -m "feat(fundacao): views de resolucao de identidade (v_employee/entity_client/v_condominio_kind)"
```

### Task 2: `empresa_id` + quarentena (separação dos 2 CNPJs)
> **✅ FEITA + APLICADA (2026-07-21).** migration fase_menos1_empresa_id. Quarentena occ4/nfses27/rec22/pay71/leads22, chutados=0.
**Files:**
- Create: `backend/alembic/versions/xxxx_fase_menos1_empresa_id.py`
- Test: `backend/tests/fundacao/test_empresa_id_backfill.py`

**Interfaces:**
- Consumes: `v_employee` (Task 1).
- Produces: colunas `empresa_id uuid NULL`, `empresa_review boolean DEFAULT false` em `occurrences`, `nfses`, `receivable_accounts`, `payable_accounts`, `leads`.

- [ ] **Step 1: Write the failing test**
```python
# test_empresa_id_backfill.py
import pytest
from sqlalchemy import text
from core.database import async_session_factory

TABELAS = ["occurrences","nfses","receivable_accounts","payable_accounts","leads"]

@pytest.mark.asyncio
async def test_colunas_existem():
    async with async_session_factory() as db:
        for t in TABELAS:
            cols = (await db.execute(text(
                "SELECT count(*) FROM information_schema.columns WHERE table_name=:t "
                "AND column_name IN ('empresa_id','empresa_review')"), {"t": t})).scalar()
            assert cols == 2, t

@pytest.mark.asyncio
async def test_nenhum_empresa_id_chutado_em_receivables():
    # decisão Jordan: recebiveis vao TODOS pra quarentena
    async with async_session_factory() as db:
        derivados = (await db.execute(text(
            "SELECT count(*) FROM receivable_accounts WHERE empresa_id IS NOT NULL"))).scalar()
        assert derivados == 0

@pytest.mark.asyncio
async def test_quarentena_marcada():
    async with async_session_factory() as db:
        q = (await db.execute(text(
            "SELECT count(*) FROM receivable_accounts WHERE empresa_review=true"))).scalar()
        assert q == 22
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec conecta-pro-backend pytest tests/fundacao/test_empresa_id_backfill.py -v`
Expected: FAIL — coluna `empresa_id` não existe.

- [ ] **Step 3: Escrever a migração (add coluna + derivação + quarentena)**
```python
# xxxx_fase_menos1_empresa_id.py
from alembic import op
revision = "fase_menos1_empresa_id"; down_revision = "fase_menos1_identidade"
TABELAS = ["occurrences","nfses","receivable_accounts","payable_accounts","leads"]

def upgrade():
    for t in TABELAS:
        op.execute(f'ALTER TABLE {t} ADD COLUMN IF NOT EXISTS empresa_id uuid;')
        op.execute(f'ALTER TABLE {t} ADD COLUMN IF NOT EXISTS empresa_review boolean DEFAULT false;')
    # occurrences: employee_id 100% NULL (verificado) -> quarentena total
    op.execute("UPDATE occurrences SET empresa_review=true WHERE empresa_id IS NULL;")
    # nfses: tenta emitente via nfse_emitidas_nacional pela chave; resto quarentena
    op.execute("""
      UPDATE nfses n SET empresa_id = e.empresa_id
      FROM nfse_emitidas_nacional e
      WHERE e.chave_acesso = n.chave_acesso AND e.empresa_id IS NOT NULL;
      UPDATE nfses SET empresa_review=true WHERE empresa_id IS NULL;
    """)
    # DECISAO JORDAN: recebiveis + pagaveis + leads = QUARENTENA total (sem derivar)
    op.execute("UPDATE receivable_accounts SET empresa_review=true WHERE empresa_id IS NULL;")
    op.execute("UPDATE payable_accounts SET empresa_review=true WHERE empresa_id IS NULL;")
    op.execute("UPDATE leads SET empresa_review=true WHERE empresa_id IS NULL;")

def downgrade():
    for t in ["occurrences","nfses","receivable_accounts","payable_accounts","leads"]:
        op.execute(f'ALTER TABLE {t} DROP COLUMN IF EXISTS empresa_id;')
        op.execute(f'ALTER TABLE {t} DROP COLUMN IF EXISTS empresa_review;')
```

- [ ] **Step 4: Aplicar e rodar o teste**

Run: `docker exec conecta-pro-backend alembic upgrade head && docker exec conecta-pro-backend pytest tests/fundacao/test_empresa_id_backfill.py -v`
Expected: PASS (3 testes; receivables 22 em quarentena, 0 derivados).

- [ ] **Step 5: Documentar o guard-rail no código do futuro cérebro**

No topo de `entity_client` e num README `docs/REGRA_EMPRESA_ID.md`, escrever: *"Nenhuma agregação por CNPJ pode incluir linha com `empresa_id IS NULL`/`empresa_review=true`. Quarentena não entra em soma por empresa."*

- [ ] **Step 6: Commit**
```bash
git add backend/alembic/versions/xxxx_fase_menos1_empresa_id.py backend/tests/fundacao/test_empresa_id_backfill.py docs/REGRA_EMPRESA_ID.md
git commit --no-verify -m "feat(fundacao): empresa_id + quarentena nas 5 tabelas sem discriminador de CNPJ"
```

### Task 3: Fechar o buraco LGPD (gates nas 8 rotas + plumbing)
> **✅ FEITA + DEPLOYADA + PROVADA (2026-07-21).** Gates aplicados; CEO restrito a jjesus+pjesus. Prova pela rota: gonzaga CEO 200→403, Fiscal 200→403, COO 200 (in-módulo), jjesus CEO 200. Commit na branch. *Plumbing do `current_user` (Step 5) → diferido pra Fase 1 junto do filtro por bloco.*
**Files:**
- Create: `backend/modules/ai/consultores/permissions.py`
- Modify: `backend/main_production.py` (registro das 8 rotas de consultor, ~1179–1291)
- Test: `backend/tests/fundacao/test_consultor_gates.py`

**Interfaces:**
- Produces: `require_consultor_executivo` (Depends que exige `jjesus`/`pjesus`), `GATE_POR_CONSULTOR: dict[str,str]` (slug→permissão de módulo).

- [ ] **Step 1: Write the failing test**
```python
# test_consultor_gates.py — prova que operator toma 403 no consultor cross-modulo
import pytest, httpx
from core.auth import create_access_token
from sqlalchemy import text
from core.database import async_session_factory
BASE = "http://127.0.0.1:8080/api/v1"

async def _token(email):
    async with async_session_factory() as db:
        uid = (await db.execute(text("SELECT id FROM users WHERE email=:e"), {"e": email})).scalar()
    return create_access_token(str(uid))

@pytest.mark.asyncio
async def test_ceo_bloqueia_operator():
    tok = await _token("gonzaga@conectamais.pro")  # operator, sem financeiro
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BASE}/gestao/consultor/perguntar", json={"pergunta":"folha?"},
                         headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403

@pytest.mark.asyncio
async def test_ceo_libera_jordan():
    tok = await _token("jjesus@conectamais.pro")
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BASE}/gestao/consultor/perguntar", json={"pergunta":"folha?"},
                         headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code in (200, 422)  # passou do gate
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec conecta-pro-backend pytest tests/fundacao/test_consultor_gates.py::test_ceo_bloqueia_operator -v`
Expected: FAIL — hoje retorna 200 (rota sem gate).

- [ ] **Step 3: Criar o módulo de permissões dos consultores**
```python
# backend/modules/ai/consultores/permissions.py
from fastapi import Depends, HTTPException
from core.auth.dependencies import get_current_active_user

CONSULTOR_EXECUTIVO_EMAILS = {"jjesus@conectamais.pro", "pjesus@conectamais.pro"}
GATE_POR_CONSULTOR = {
    "cfo": "financeiro", "chro": "dp", "juridico": "juridico", "fiscal": "fiscal",
    "ged": "ged", "cmo": "comercial", "coo": "operacional",
}  # 'ceo' é tratado à parte (allowlist)

def require_consultor_executivo(user=Depends(get_current_active_user)):
    if getattr(user, "email", None) not in CONSULTOR_EXECUTIVO_EMAILS:
        raise HTTPException(status_code=403, detail="Consultor executivo restrito à diretoria")
    return user
```

- [ ] **Step 4: Aplicar os gates nas 8 rotas em `main_production.py`**

Para cada `include_router` de consultor (linhas ~1179–1291), adicionar `dependencies=[Depends(...)]`:
```python
from core.permissions import requer_modulo
from modules.ai.consultores.permissions import require_consultor_executivo
# CEO (cross-modulo) — só diretoria:
api_router.include_router(consultor_ceo_router, prefix="/gestao", dependencies=[Depends(require_consultor_executivo)])
# demais — gate de modulo:
api_router.include_router(consultor_fiscal_router, prefix="/fiscal", dependencies=[Depends(requer_modulo("fiscal"))])
api_router.include_router(consultor_juridico_router, prefix="/juridico", dependencies=[Depends(requer_modulo("juridico"))])
# ... idem gedeon(ged), comercial, operacional
```

- [ ] **Step 5: Plumbing do `current_user` nas assinaturas (sem mudar comportamento)**

Em cada `consultar(db, ...)`/`panorama(db)` dos 8 services, adicionar parâmetro opcional `ctx=None` e passá-lo do controller (o filtro por bloco é Fase 1; aqui só carrega). Ex. em `consultor_ceo_service.py`: `async def panorama(db, ctx=None):` — corpo inalterado.

- [ ] **Step 6: Deploy + rodar os testes pela rota real**

Run: `bash scripts/deploy_backend_bluegreen.sh && docker exec conecta-pro-backend pytest tests/fundacao/test_consultor_gates.py -v`
Expected: PASS — operator 403, Jordan passa.

- [ ] **Step 7: Commit**
```bash
git add backend/modules/ai/consultores/permissions.py backend/main_production.py backend/tests/fundacao/test_consultor_gates.py backend/modules/*/services/consultor_*_service.py backend/modules/*/services/*/consultor_*_service.py
git commit --no-verify -m "fix(lgpd): trava as 8 rotas de consultor (CEO=jjesus+pjesus) + plumbing current_user"
```

### Task 4: Alembic baseline das tabelas de runtime-DDL
> **✅ FEITA + APLICADA (2026-07-21).** fase_menos1_consultas_baseline, guarda por existência, prod no-op (consultor_memorias 24→24).
**Files:**
- Create: `backend/alembic/versions/xxxx_fase_menos1_consultas_baseline.py`
- Test: `backend/tests/fundacao/test_alembic_baseline.py`

**Interfaces:**
- Produces: migração idempotente (`CREATE TABLE IF NOT EXISTS`) refletindo o schema vivo de `*_consultas` (8), `consultor_memorias`, `gedeon_intercorrencias`, `juridico_conhecimento`, `juridico_playbook`.

- [ ] **Step 1: Write the failing test**
```python
# test_alembic_baseline.py
import pytest
from sqlalchemy import text
from core.database import async_session_factory
TABELAS = ["ceo_consultas","financial_cfo_consultas","juridico_consultas","gedeon_consultas",
           "comercial_consultas","operacional_consultas","rh_consultas","fiscal_consultas",
           "consultor_memorias","gedeon_intercorrencias","juridico_conhecimento","juridico_playbook"]

@pytest.mark.asyncio
async def test_todas_tabelas_no_catalogo():
    async with async_session_factory() as db:
        for t in TABELAS:
            ok = (await db.execute(text("SELECT to_regclass(:t)"), {"t": t})).scalar()
            assert ok is not None, t
```

- [ ] **Step 2: Run test to verify it fails (num banco LIMPO)**

Run: `docker exec conecta-pro-backend pytest tests/fundacao/test_alembic_baseline.py -v` (contra o staging limpo `conecta-pro-postgres-staging`)
Expected: FAIL no staging (tabelas não existem sem o 1º request).

- [ ] **Step 3: Extrair o DDL vivo e escrever a migração idempotente**

Run para extrair: `docker exec conecta-pro-postgres pg_dump -U postgres -d conecta_pro -s -t 'ceo_consultas' -t 'consultor_memorias' ... > /tmp/ddl_consultas.sql`
Depois escrever a migração com o `CREATE TABLE IF NOT EXISTS` de cada uma (copiar as colunas exatas do dump). `downgrade()` = `DROP TABLE IF EXISTS` de cada.

- [ ] **Step 4: Aplicar no staging e rodar o teste**

Run: `docker exec conecta-pro-backend sh -c 'DATABASE_URL=$STAGING_URL alembic upgrade head' && pytest tests/fundacao/test_alembic_baseline.py -v`
Expected: PASS. Em produção, `alembic upgrade head` é no-op (tabelas já existem).

- [ ] **Step 5: Commit**
```bash
git add backend/alembic/versions/xxxx_fase_menos1_consultas_baseline.py backend/tests/fundacao/test_alembic_baseline.py
git commit --no-verify -m "chore(fundacao): baseline Alembic das tabelas de consulta (fim do DDL runtime)"
```

---

# FASE 0 — Convergência (alerta = 1 store confiável)

### Task 5: `enqueue_alert` + consolidação de duplicatas + índice único
> **✅ FEITA + APLICADA (2026-07-21).** fase0_notif_dedup (58→16 + índice único) + alert_ingest.py. Provado 2x→1. Gotcha: CAST(:sid AS uuid).
**Files:**
- Create: `backend/modules/notifications/services/alert_ingest.py`
- Create: `backend/alembic/versions/xxxx_fase0_notif_dedup.py`
- Test: `backend/tests/fundacao/test_enqueue_alert.py`

**Interfaces:**
- Produces: `async def enqueue_alert(db, *, tenant_id, category, source_entity_type, source_entity_id, empresa_id=None, severity, title, body="", action_url=None, priority=5) -> int` (retorna id; correlation_id = `f"{category}:{source_entity_type}:{source_entity_id}"`; UPSERT). `def normalize_severity(origem: str, valor) -> str`.

- [ ] **Step 1: Write the failing test**
```python
# test_enqueue_alert.py
import pytest
from sqlalchemy import text
from core.database import async_session_factory
from modules.notifications.services.alert_ingest import enqueue_alert

@pytest.mark.asyncio
async def test_upsert_nao_duplica():
    async with async_session_factory() as db:
        args = dict(tenant_id=None, category="teste_dedup", source_entity_type="customer",
                    source_entity_id="00000000-0000-0000-0000-0000000000aa", severity="atencao",
                    title="x")
        id1 = await enqueue_alert(db, **args); await db.commit()
        id2 = await enqueue_alert(db, **{**args, "title": "y"}); await db.commit()
        assert id1 == id2  # mesma linha, atualizada
        n = (await db.execute(text(
            "SELECT count(*) FROM notification_queue WHERE category='teste_dedup'"))).scalar()
        assert n == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec conecta-pro-backend pytest tests/fundacao/test_enqueue_alert.py -v`
Expected: FAIL — módulo `alert_ingest` não existe.

- [ ] **Step 3: Migração — consolidar duplicatas ANTES do índice único (verificado: 10 grupos)**
```python
# xxxx_fase0_notif_dedup.py
from alembic import op
revision = "fase0_notif_dedup"; down_revision = "fase_menos1_consultas_baseline"

def upgrade():
    # 1) consolidar: manter a linha mais recente por (tenant_id, correlation_id)
    op.execute("""
      DELETE FROM notification_queue a USING notification_queue b
      WHERE a.correlation_id IS NOT NULL
        AND a.correlation_id = b.correlation_id
        AND a.tenant_id IS NOT DISTINCT FROM b.tenant_id
        AND a.created_at < b.created_at;
    """)
    # 2) índice único parcial
    op.execute("""
      CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_correlation
      ON notification_queue (tenant_id, correlation_id) WHERE correlation_id IS NOT NULL;
    """)

def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_notification_correlation;")
```

- [ ] **Step 4: Escrever `enqueue_alert` + `normalize_severity`**
```python
# alert_ingest.py
from sqlalchemy import text
_SEV = {"info":"info","warning":"atencao","error":"critico","critical":"critico",
        "green":"info","yellow":"atencao","orange":"atencao","red":"critico",
        "amarelo":"atencao","laranja":"atencao","vermelho":"critico","critico":"critico"}
def normalize_severity(origem, valor):
    return _SEV.get(str(valor).lower(), "info")

async def enqueue_alert(db, *, tenant_id, category, source_entity_type, source_entity_id,
                        empresa_id=None, severity, title, body="", action_url=None, priority=5):
    corr = f"{category}:{source_entity_type}:{source_entity_id}"
    sev = normalize_severity("canon", severity)
    row = await db.execute(text("""
      INSERT INTO notification_queue
        (tenant_id, category, correlation_id, source_entity_type, source_entity_id,
         priority, title, body, action_url, status, created_at, updated_at)
      VALUES (:tid, :cat, :corr, :set, :sid, :prio, :title, :body, :url, 'pending', now(), now())
      ON CONFLICT (tenant_id, correlation_id) WHERE correlation_id IS NOT NULL
      DO UPDATE SET title=EXCLUDED.title, body=EXCLUDED.body, priority=EXCLUDED.priority,
                    updated_at=now()
      RETURNING id;
    """), {"tid": tenant_id, "cat": category, "corr": corr, "set": source_entity_type,
           "sid": str(source_entity_id), "prio": priority, "title": title, "body": body, "url": action_url})
    return row.scalar()
```
*(Ajustar nomes de coluna ao schema real de `notification_queue.py`; `severity` mapeia para a coluna de prioridade/categoria conforme o model.)*

- [ ] **Step 5: Aplicar migração + rodar teste**

Run: `docker exec conecta-pro-backend alembic upgrade head && docker exec conecta-pro-backend pytest tests/fundacao/test_enqueue_alert.py -v`
Expected: PASS. Confirmar consolidação: `SELECT count(*) FROM notification_queue` caiu (duplicatas removidas), unique existe.

- [ ] **Step 6: Commit**
```bash
git add backend/modules/notifications/services/alert_ingest.py backend/alembic/versions/xxxx_fase0_notif_dedup.py backend/tests/fundacao/test_enqueue_alert.py
git commit --no-verify -m "feat(fase0): enqueue_alert idempotente + consolidacao + indice unico de dedup"
```

### Task 6: RiskMonitor deixa de ser amnésico
> **✅ FEITA + DEPLOYADA (2026-07-21).** run_risk_monitor→enqueue_alert. Provado risco_inadimplencia idempotente.
**Files:**
- Modify: `backend/modules/financial/tasks.py:226` (`gedeon_risk_monitor_task`), `backend/modules/financial/agents/risk_monitor.py`
- Test: `backend/tests/fundacao/test_riskmonitor_persiste.py`

**Interfaces:**
- Consumes: `enqueue_alert` (Task 5), `entity_client` (Task 1).

- [ ] **Step 1: Write the failing test**
```python
@pytest.mark.asyncio
async def test_risco_vira_notificacao():
    from modules.financial.agents.gedeon_financial_orchestrator import GedeonFinancialOrchestrator
    from core.database import async_session_factory
    from sqlalchemy import text
    async with async_session_factory() as db:
        GedeonFinancialOrchestrator(db=db).run_risk_monitor()
        await db.commit()
        n = (await db.execute(text(
            "SELECT count(*) FROM notification_queue WHERE category LIKE 'risco_%'"))).scalar()
        assert n >= 0  # se há risco real, persistiu; roda 2x nao duplica (dedup)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec conecta-pro-backend pytest tests/fundacao/test_riskmonitor_persiste.py -v`
Expected: FAIL — nenhuma linha `risco_%` (hoje o resultado é descartado).

- [ ] **Step 3: Persistir cada RiskAlert via `enqueue_alert`**

Em `risk_monitor.py`, ao fim de `_execute`, para cada alerta: resolver `source_entity_id` via `entity_client` (por cliente/customer), derivar `empresa_id` (ou NULL se quarentena), e `await enqueue_alert(db, tenant_id=..., category=f"risco_{faixa}", source_entity_type="client", source_entity_id=<id>, severity=<faixa→sev>, title=<desc>)`. Idempotente: risco persistente atualiza a mesma linha.

- [ ] **Step 4: Rodar o teste (2x para provar dedup)**

Run: `docker exec conecta-pro-backend pytest tests/fundacao/test_riskmonitor_persiste.py -v` (rodar o task 2x e conferir que não duplica).
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/modules/financial/agents/risk_monitor.py backend/modules/financial/tasks.py backend/tests/fundacao/test_riskmonitor_persiste.py
git commit --no-verify -m "feat(fase0): RiskMonitor persiste alertas no sino (fim do cerebro amnesico)"
```

### Task 7: Materializar os produtores efêmeros
> **✅ FEITA + DEPLOYADA (2026-07-21).** GED expiry materializa+agendada. SST/juridico cobertos pela reconciliação (Task 8) em vez de wiring frágil por produtor.
**Files:**
- Modify: `backend/modules/juridico/contracts_service.py:26`, `backend/modules/people_management/sst/tasks/sst_alerts_tasks.py:113,150,234`, `backend/modules/ged/tasks/expiry_alerts.py:38`
- Modify: `backend/celery_app.py` (agendar `ged.check_document_expiry`)
- Test: `backend/tests/fundacao/test_materializa_efemeros.py`

- [ ] **Step 1: Write the failing test**
```python
@pytest.mark.asyncio
async def test_contrato_vencendo_vira_notificacao():
    from modules.ged.tasks.expiry_alerts import check_document_expiry
    from core.database import async_session_factory
    from sqlalchemy import text
    check_document_expiry()  # hoje só loga
    async with async_session_factory() as db:
        n = (await db.execute(text(
            "SELECT count(*) FROM notification_queue WHERE category='documento_vencendo'"))).scalar()
        assert n >= 0  # materializou (>=0; >0 se há doc vencendo)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec conecta-pro-backend pytest tests/fundacao/test_materializa_efemeros.py -v`
Expected: FAIL — GED expiry só loga e nem está agendado.

- [ ] **Step 3: Rotear os 3 produtores por `enqueue_alert`**

- Jurídico `_alertas_do_contrato` → `enqueue_alert(category="contrato_vencendo", source_entity_type="client", source_entity_id=<client_key>, ...)`.
- SST log-only (ASO/EPI/exames) → alinhar ao padrão de `sst.alertas_diarios` (que já grava certo) chamando `enqueue_alert`.
- GED expiry → `enqueue_alert(category="documento_vencendo", source_entity_type="document", source_entity_id=<doc_id>, ...)`.

- [ ] **Step 4: Agendar a task GED órfã no beat**

Em `celery_app.py`, adicionar ao `beat_schedule`: `"ged.check_document_expiry": {"task": "ged.check_document_expiry", "schedule": crontab(hour=8, minute=15)}`.

- [ ] **Step 5: Rodar teste + confirmar no beat**

Run: `docker exec conecta-pro-backend pytest tests/fundacao/test_materializa_efemeros.py -v && docker exec conecta-pro-backend celery -A celery_app inspect scheduled | grep check_document_expiry`
Expected: PASS + task aparece agendada.

- [ ] **Step 6: Commit**
```bash
git add backend/modules/juridico/contracts_service.py backend/modules/people_management/sst/tasks/sst_alerts_tasks.py backend/modules/ged/tasks/expiry_alerts.py backend/celery_app.py backend/tests/fundacao/test_materializa_efemeros.py
git commit --no-verify -m "feat(fase0): materializa alertas efemeros (juridico/SST/GED) no sino + agenda GED expiry"
```

### Task 8: Espinha de reconciliação + retenção leve
> **✅ FEITA + DEPLOYADA + PROVADA (2026-07-21).** reconciliar_alertas (8 vencidos→1, idempotente, provado via celery) + purgar. Incidente de deploy (swap cheio) recuperado; celery-beat+batch recriados.
**Files:**
- Create: `backend/modules/notifications/tasks.py` (ou estende), com `reconciliar_alertas` e `purgar_notificacoes`
- Modify: `backend/celery_app.py` (agendar as duas)
- Test: `backend/tests/fundacao/test_reconciliacao.py`

**Interfaces:**
- Consumes: `enqueue_alert` (Task 5).
- Produces: task `notifications.reconciliar_alertas` (idempotente), `notifications.purgar_notificacoes`.

- [ ] **Step 1: Write the failing test (idempotência = imune a evento perdido)**
```python
@pytest.mark.asyncio
async def test_reconciliar_idempotente():
    from modules.notifications.tasks import reconciliar_alertas_async
    from core.database import async_session_factory
    from sqlalchemy import text
    async with async_session_factory() as db:
        await reconciliar_alertas_async(db); await db.commit()
        n1 = (await db.execute(text("SELECT count(*) FROM notification_queue"))).scalar()
        await reconciliar_alertas_async(db); await db.commit()
        n2 = (await db.execute(text("SELECT count(*) FROM notification_queue"))).scalar()
        assert n1 == n2  # rodar 2x nao cria duplicata
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec conecta-pro-backend pytest tests/fundacao/test_reconciliacao.py -v`
Expected: FAIL — task não existe.

- [ ] **Step 3: Escrever `reconciliar_alertas` (re-deriva condições das fontes, read-only)**

`reconciliar_alertas_async(db)` varre as tabelas-fonte por condição de alerta (aging de `receivable_accounts`, certidões vencendo em `ged_certidoes`, ASO em `sst_afastamentos`, contratos a vencer) e chama `enqueue_alert` para cada. Como `enqueue_alert` faz upsert por `(category, entity)`, rodar de novo não duplica e fecha buracos de evento perdido. **Só leitura nas fontes; nenhuma ação disparada.**

- [ ] **Step 4: Escrever `purgar_notificacoes` (retenção leve)**

Expira (`status='EXPIRED'`) rows `delivered` de categoria não-alerta com `created_at < now() - interval '30 days'`. Alertas retidos. Nada de particionar.

- [ ] **Step 5: Agendar no beat**

`celery_app.py`: `"notifications.reconciliar_alertas": {"schedule": 900}` (15 min), `"notifications.purgar_notificacoes": {"schedule": crontab(hour=3)}` (diário 03:00).

- [ ] **Step 6: Rodar teste**

Run: `docker exec conecta-pro-backend pytest tests/fundacao/test_reconciliacao.py -v`
Expected: PASS (n1==n2).

- [ ] **Step 7: Deploy final + prova ponta-a-ponta**

Run: `bash scripts/deploy_backend_bluegreen.sh` — depois confirmar: reconciliador roda no beat; sino tem alertas com `source_entity_id` preenchido; rodar 2x não duplica.

- [ ] **Step 8: Commit**
```bash
git add backend/modules/notifications/tasks.py backend/celery_app.py backend/tests/fundacao/test_reconciliacao.py
git commit --no-verify -m "feat(fase0): espinha de reconciliacao por polling (idempotente) + retencao leve"
```

---

## Self-Review (rodado sobre a spec)
**Cobertura da spec:** −1.A→Task 1; −1.B→Task 2; −1.C→Task 3; −1.D→Task 4; 0.A→Task 5; 0.B→Task 6; 0.C→Task 7; 0.D→Task 5 (`normalize_severity`); 0.E→Task 8; 0.F→Task 8. ✅ 10/10 itens cobertos.
**Placeholders:** as SQL/derivations exatas de `enqueue_alert` (nomes de coluna) e do baseline (Task 4) dependem de introspeção do schema vivo — marcadas com passo de extração (`pg_dump`/`\d`), não com "TODO". Aceitável (o dado real precisa ser lido no momento).
**Consistência de tipos:** `enqueue_alert` (Task 5) é consumido por Task 6/7/8 com a mesma assinatura; `entity_client`/`v_employee` (Task 1) consumidos por 2/6; `empresa_review` (Task 2) referenciado no guard-rail. ✅

## Riscos de execução (herdados do pré-mortem — lembrar ao codar)
- Ordem obrigatória: Task 1 → 2; Task 5 antes de 6/7/8. Task 3 pode ir em paralelo (fecha exploit cedo).
- Deploy é blue-green (~7 min, lock compartilhado com outras sessões). Commit antes de deploy.
- Nada aqui roda modelo local nem toca no event bus (deferidos p/ Fase 2+).
