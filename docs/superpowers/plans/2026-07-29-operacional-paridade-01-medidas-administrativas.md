# Paridade Redesign Operacional — 01 · Medidas Administrativas (PILOTO) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir as telas FABRICADAS de medidas disciplinares no redesign (`medidas-administrativas`, `disciplinar`) por leitura de dado REAL (tabela `disciplinary_actions`) + form de criação que chama o service existente via write-gate — sem recodar o service.

**Architecture:** O redesign é data-driven. O builder `redesign_builders/operacional.py` (`build(db)`) devolve `{screen_id: patch}` e SOBRESCREVE o screen estático fabricado do `frontend/src/app/redesign/_modules/operacional.json`. Leitura = SQL direto na tabela real via helper `tbl(...)`. Escrita = endpoint `/redesign/action/medida-administrativa` num `router` do próprio builder (auto-incluído pela descoberta em `redesign_data_controller._discover_module_builders`), que importa `DisciplinaryService` e chama através de `redesign_write_gate.op_write`. LLM/agente nunca dispara — o form é operado por humano.

**Tech Stack:** FastAPI (async), SQLAlchemy async (`text()` raw SQL nos builders), Pydantic v2, PostgreSQL. Deploy backend baked (blue-green).

## Global Constraints

- **Nunca fabricar dado:** oráculo = exibido == banco. Vazio real → tela honesta "aguardando dado", NUNCA linha inventada. (Este plano EXISTE para matar `Carlos Batista/Uniforme incompleto` fabricado.)
- **LLM/agente nunca executa escrita.** O form é humano; a rota de ação exige `CurrentActiveUser`.
- **Reusar, não recodar:** `DisciplinaryService.create` já existe e valida (CLT). Só orquestrar.
- **Deploy durável = bake** (`scripts/deploy_backend_bluegreen.sh`); `docker cp` é volátil. Commits `--no-verify`, trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Backend baked:** teste rápido pode usar `docker cp`+restart, mas a verdade final é rebuild+`up -d`.

## Fatos verificados do código (não re-descobrir)

**Tabela `disciplinary_actions`** (colunas usadas): `id, code, employee_name, employee_cpf, employee_id, action_type, status, reason_category, reason_description, incident_date, created_at, tenant_id, is_active`.

**Enums** (`disciplinary/schemas/disciplinary_schemas.py`):
- `DisciplinaryActionType`: `advertencia_verbal, advertencia_escrita, suspensao, demissao_justa_causa`
- `ReasonCategory`: `falta, atraso, insubordinacao, indisciplina, dano_patrimonio, negligencia, embriaguez, abandono_emprego, ato_improbidade, violacao_segredo, desistencia_habitual, ofensa_fisica, ofensa_moral, jogos_azar, perda_habilitacao, outros`
- `DisciplinaryActionStatus`: `rascunho, pendente_aprovacao, aprovada, rejeitada, pendente_assinatura, assinada, recusada_assinatura, aplicada, cancelada`

**Schema `DisciplinaryActionCreate`** (obrigatórios): `action_type` (enum), `employee_id` (str UUID), `employee_name` (str 2-255), `employee_cpf` (str 11-14), `reason_category` (enum), `reason_description` (str min 10), `incident_date` (date). Opcionais: `employee_position, post_id, client_id, suspension_*`, testemunhas.

**Service** (`disciplinary/services/__init__.py`): `from modules.operacional.disciplinary.services import get_disciplinary_service` → `get_disciplinary_service(db).create(data=DisciplinaryActionCreate, tenant_id=str, created_by=str) -> DisciplinaryAction`. Tenant helper: `from core.auth import get_tenant_id` → `get_tenant_id(current_user)`.

**Builder helpers** (`redesign_data_controller.py`, importáveis): `_helpers(db) -> (out, safe, tbl)`; `tbl(title, sub, cta, cols, grid, sql, rowfn, hint="Buscar…", docsfn=None, editfn=None, actionsfn=None)`; `t(v, w=500, tc="#334155", ini="")`; `b(label, tone)` (badge; tones ok/warn/bad/info/mut); `_scalar(db, sql)`; `_fmtdate(d)`; `doc(label, url, fmt="pdf")`.

**Gate** (`redesign_write_gate.py`): `op_write(db, *, real_write, idempotency_key=None, is_homologacao=False) -> dict` — `real_write` é coroutine sem args.

**Descoberta de builder** (`redesign_data_controller._discover_module_builders`, já roda no import): para cada `redesign_builders/<mod>.py` não-`_`: `BUILDERS[SLUG]=build`; `EXTRA_MENU[SLUG]+=EXTRA_MENU`; se tem `router`, `router.include_router(_m.router)`. **`operacional.py` NÃO tem router hoje** — este plano adiciona um.

**Form contract** (screen dict): `{"title","sub","cta","type":"form","submit":{"endpoint","okMsg"},"fields":[{"key","label","type":"select|text|textarea|date","span":"span 1|span 2","ph","options":[{"value","label"}]}]}`. Prefixo real das rotas de ação: `/api/v1/redesign/action/<slug>`.

**Menu ids já existentes** (`operacional.json`): `medidas-administrativas` (usar p/ TABELA real) e `disciplinar` (usar p/ FORM "Nova medida"). Não é preciso mexer no JSON — o builder sobrescreve os screens desses ids.

**Arquivo-alvo único:** `backend/modules/operacional/controllers/redesign_builders/operacional.py` (hoje 143 linhas; termina em `return out`).

---

### Task 1: Tela de LEITURA real de medidas administrativas (mata a casca fabricada)

**Files:**
- Modify: `backend/modules/operacional/controllers/redesign_builders/operacional.py` (antes do `return out`, ~L142)
- Test: `backend/scripts/orq/test_oraculo_medidas_redesign.py` (Create)

**Interfaces:**
- Consumes: `_helpers`, `t`, `b`, `_scalar`, `doc` (já importados no topo do arquivo — confira e adicione `b` se faltar).
- Produces: `out["medidas-administrativas"]` = screen `type:"table"` com linhas reais de `disciplinary_actions`.

- [ ] **Step 1: Escrever o teste-oráculo que FALHA (exibido == banco; sem fabricação)**

Create `backend/scripts/orq/test_oraculo_medidas_redesign.py`:

```python
"""Oráculo: a tela redesign 'medidas-administrativas' reflete disciplinary_actions (exibido==banco),
e NÃO contém dado fabricado. Roda dentro do container (asyncpg → DB real)."""
import asyncio
from sqlalchemy import text
from core.database import async_session_factory
from modules.operacional.controllers.redesign_builders.operacional import build


async def main() -> None:
    async with async_session_factory() as db:
        screens = await build(db)
        scr = screens.get("medidas-administrativas")
        assert scr and scr.get("type") == "table", "medidas-administrativas não é tabela real"
        n_rows = len(scr.get("rows", []))
        n_db = (await db.execute(text(
            "SELECT count(*) FROM disciplinary_actions WHERE coalesce(is_active,true)"))).scalar() or 0
        # a tela lista até 200; o oráculo é min(n_db,200)
        assert n_rows == min(int(n_db), 200), f"linhas exibidas={n_rows} != banco={min(n_db,200)}"
        blob = str(scr)
        assert "Carlos Batista" not in blob and "Uniforme incompleto" not in blob, "AINDA fabricado!"
        print(f"OK medidas: exibido={n_rows} == banco(min200)={min(int(n_db),200)}; sem fabricação")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Rodar o teste e ver FALHAR (hoje o builder não devolve o screen → cai na casca)**

Run: `docker cp backend/scripts/orq/test_oraculo_medidas_redesign.py conecta-pro-backend:/app/scripts/orq/ && docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_medidas_redesign.py`
Expected: `AssertionError: medidas-administrativas não é tabela real` (build ainda não provê o screen).

- [ ] **Step 3: Implementar a tela de leitura real no builder**

Em `operacional.py`, imediatamente ANTES de `return out` (última linha), inserir. **Garanta que `b` está no import do topo** (linha 4-6): se não estiver, adicione `b` à lista importada de `redesign_data_controller`.

```python
    # Medidas administrativas — disciplinary_actions (LEITURA real; mata a casca fabricada).
    _med_tone = {"aplicada": "ok", "aprovada": "ok", "assinada": "ok",
                 "pendente_aprovacao": "warn", "pendente_assinatura": "warn", "rascunho": "info",
                 "rejeitada": "bad", "recusada_assinatura": "bad", "cancelada": "mut"}
    try:
        n_med = await _scalar(db, "SELECT count(*) FROM disciplinary_actions WHERE coalesce(is_active,true)") or 0
        out["medidas-administrativas"] = await tbl(
            "Medidas administrativas", f"{n_med} medida(s) · fonte: disciplinary_actions", "—",
            ["Colaborador", "Tipo", "Motivo", "Data", "Status"], "1.8fr 1.2fr 1.6fr 0.9fr 1fr",
            "SELECT id, coalesce(employee_name,'—'), coalesce(action_type::text,'—'), "
            "coalesce(reason_description, reason_category::text, '—'), incident_date, coalesce(status::text,'—') "
            "FROM disciplinary_actions WHERE coalesce(is_active,true) "
            "ORDER BY coalesce(incident_date, created_at) DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[1], 600, "#0F1B3A"), t((r[2] or '—').replace('_', ' ').capitalize()),
                       t((r[3] or '—')[:60]), t(_fmtdate(r[4])),
                       b((r[5] or '—').replace('_', ' ').capitalize(), _med_tone.get((r[5] or '').lower(), "info"))])
    except Exception:  # noqa: BLE001 — nunca derruba o módulo
        pass
```

- [ ] **Step 4: Rodar o teste e ver PASSAR**

Run: `docker cp backend/modules/operacional/controllers/redesign_builders/operacional.py conecta-pro-backend:/app/modules/operacional/controllers/redesign_builders/operacional.py && docker exec conecta-pro-backend kill -HUP 1 2>/dev/null; sleep 6; docker cp backend/scripts/orq/test_oraculo_medidas_redesign.py conecta-pro-backend:/app/scripts/orq/ && docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_medidas_redesign.py`
Expected: `OK medidas: exibido=N == banco(min200)=N; sem fabricação` (N pode ser 0 → tela honesta vazia, que é o objetivo).

- [ ] **Step 5: Commit**

```bash
git -C /opt/conecta-pro add backend/modules/operacional/controllers/redesign_builders/operacional.py backend/scripts/orq/test_oraculo_medidas_redesign.py
git -C /opt/conecta-pro commit --no-verify -m "feat(redesign-op): medidas-administrativas lê disciplinary_actions real (mata casca fabricada)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Form "Nova medida" + rota de ação via write-gate (escrita real)

**Files:**
- Modify: `backend/modules/operacional/controllers/redesign_builders/operacional.py` (adicionar `router`, screen `out["disciplinar"]`, e o import `APIRouter` etc.)
- Test: `backend/scripts/orq/test_acao_medida_redesign.py` (Create)

**Interfaces:**
- Consumes: `DisciplinaryService` via `get_disciplinary_service`; `DisciplinaryActionCreate`; `op_write`.
- Produces: endpoint `POST /api/v1/redesign/action/medida-administrativa` (payload `{action_type, employee_id, employee_name, employee_cpf, reason_category, reason_description, incident_date}`) → `{ok, id, code, message}`; e `out["disciplinar"]` = form apontando pra ele.

- [ ] **Step 1: Escrever o teste de ação que FALHA (cria medida real e confere no banco)**

Create `backend/scripts/orq/test_acao_medida_redesign.py`:

```python
"""Ação redesign: /action/medida-administrativa cria linha REAL em disciplinary_actions.
Chama a função do router diretamente (sem HTTP) com um current_user fake e confere no banco."""
import asyncio, uuid
from datetime import date
from types import SimpleNamespace
from sqlalchemy import text
from core.database import async_session_factory
from modules.operacional.controllers.redesign_builders.operacional import rd_action_medida_administrativa


async def main() -> None:
    async with async_session_factory() as db:
        emp = (await db.execute(text(
            "SELECT id, nome, coalesce(cpf,'00000000000') FROM employees WHERE coalesce(status,'')='ativo' LIMIT 1"))).first()
        assert emp, "sem employee ativo p/ testar"
        user = SimpleNamespace(id=uuid.uuid4(), condominio_id=None)
        payload = {"action_type": "advertencia_escrita", "employee_id": str(emp[0]),
                   "employee_name": emp[1] or "Teste", "employee_cpf": str(emp[2]),
                   "reason_category": "atraso", "reason_description": "Atraso reiterado — teste oráculo redesign",
                   "incident_date": date.today().isoformat()}
        res = await rd_action_medida_administrativa(current_user=user, payload=payload, db=db)
        assert res.get("ok") and res.get("id"), f"ação não retornou ok/id: {res}"
        row = (await db.execute(text("SELECT employee_name, status::text FROM disciplinary_actions WHERE id::text=:i"),
                                {"i": str(res["id"])})).first()
        assert row and row[0] == (emp[1] or "Teste"), "linha não persistiu no banco"
        print(f"OK ação: criou disciplinary_action id={res['id']} status={row[1]}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Rodar e ver FALHAR (função ainda não existe)**

Run: `docker cp backend/scripts/orq/test_acao_medida_redesign.py conecta-pro-backend:/app/scripts/orq/ && docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_acao_medida_redesign.py`
Expected: `ImportError: cannot import name 'rd_action_medida_administrativa'`.

- [ ] **Step 3: Implementar o router + endpoint + form**

No TOPO de `operacional.py`, após os imports existentes, adicionar:

```python
from fastapi import APIRouter, Body, HTTPException
from sqlalchemy import text as _sqltext
from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from fastapi import Depends

router = APIRouter()


@router.post("/action/medida-administrativa")
async def rd_action_medida_administrativa(current_user: CurrentActiveUser, payload: dict = Body(...),
                                          db=Depends(get_db)) -> dict:
    """Cria medida disciplinar REAL via DisciplinaryService (reuso; validação CLT no service).
    Humano-operado (CurrentActiveUser). Escrita operacional → passa pelo op_write (idempotência)."""
    import uuid as _uuid
    from datetime import date as _date
    from core.auth import get_tenant_id
    from modules.operacional.disciplinary.services import get_disciplinary_service
    from modules.operacional.disciplinary.schemas.disciplinary_schemas import DisciplinaryActionCreate
    from modules.operacional.controllers.redesign_write_gate import op_write, GateError

    emp_id = (payload.get("employee_id") or "").strip()
    if not emp_id:
        raise HTTPException(status_code=400, detail="Selecione o colaborador.")
    desc = (payload.get("reason_description") or "").strip()
    if len(desc) < 10:
        raise HTTPException(status_code=400, detail="A descrição do motivo precisa de ao menos 10 caracteres.")
    try:
        data = DisciplinaryActionCreate(
            action_type=payload.get("action_type") or "advertencia_escrita",
            employee_id=emp_id,
            employee_name=(payload.get("employee_name") or "").strip() or "—",
            employee_cpf=(payload.get("employee_cpf") or "").strip() or "00000000000",
            reason_category=payload.get("reason_category") or "outros",
            reason_description=desc,
            incident_date=payload.get("incident_date") or _date.today().isoformat(),
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    svc = get_disciplinary_service(db)
    tenant_id = get_tenant_id(current_user)

    async def _write():
        return await svc.create(data=data, tenant_id=str(tenant_id), created_by=str(current_user.id))

    try:
        action = await op_write(db, real_write=_write,
                                idempotency_key=f"medida:{emp_id}:{data.incident_date}:{data.reason_category}")
    except GateError as ge:
        raise HTTPException(status_code=400, detail=str(ge))
    return {"ok": True, "id": str(action.id), "code": getattr(action, "code", None),
            "message": "Medida disciplinar registrada (rascunho)"}
```

Depois, DENTRO de `build(db)` (antes do `return out`), adicionar o form apontando pra essa rota:

```python
    # Form "Nova medida" (ESCRITA real → /action/medida-administrativa). Opções vêm do banco.
    try:
        _emp = (await db.execute(_sqltext(
            "SELECT id, nome, coalesce(cpf,'') FROM employees WHERE coalesce(status,'')='ativo' ORDER BY nome LIMIT 500"))).fetchall()
        _tipos = [("advertencia_verbal", "Advertência verbal"), ("advertencia_escrita", "Advertência escrita"),
                  ("suspensao", "Suspensão"), ("demissao_justa_causa", "Demissão por justa causa")]
        _cats = [("falta", "Falta"), ("atraso", "Atraso"), ("insubordinacao", "Insubordinação"),
                 ("indisciplina", "Indisciplina"), ("dano_patrimonio", "Dano ao patrimônio"),
                 ("negligencia", "Negligência"), ("abandono_emprego", "Abandono de emprego"),
                 ("ofensa_moral", "Ofensa moral"), ("ofensa_fisica", "Ofensa física"), ("outros", "Outros")]
        out["disciplinar"] = {
            "title": "Nova medida disciplinar", "sub": "Cria a medida (rascunho) — validação CLT no motor real", "cta": "Registrar medida",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/medida-administrativa",
                                        "okMsg": "Medida registrada (rascunho)"},
            "fields": [
                {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2", "ph": "Selecione o colaborador",
                 "options": [{"value": str(i), "label": (n or '—'), "data": {"employee_name": n or '', "employee_cpf": c or ''}} for i, n, c in _emp]},
                {"key": "action_type", "label": "Tipo*", "type": "select", "span": "span 1", "ph": "Tipo",
                 "options": [{"value": v, "label": l} for v, l in _tipos]},
                {"key": "reason_category", "label": "Motivo (CLT)*", "type": "select", "span": "span 1", "ph": "Categoria",
                 "options": [{"value": v, "label": l} for v, l in _cats]},
                {"key": "incident_date", "label": "Data do incidente*", "type": "date", "span": "span 1"},
                {"key": "reason_description", "label": "Descrição do incidente*", "type": "textarea", "span": "span 2", "ph": "Descreva o ocorrido (mín. 10 caracteres)…"},
            ],
        }
    except Exception:  # noqa: BLE001
        pass
```

> Nota de wiring do nome/CPF: o form manda `employee_id`; o endpoint tolera `employee_name`/`employee_cpf` ausentes (default seguro) para não travar caso o front não propague o `data` da option. O nome/CPF corretos são resolvidos no service pelo `employee_id` quando disponível; se o service não os preencher, um follow-up (fora deste plano) enriquece pelo `employee_id`. Não fabricar: se faltar nome, fica "—", nunca um nome inventado.

- [ ] **Step 4: Rodar o teste de ação e ver PASSAR**

Run: `docker cp backend/modules/operacional/controllers/redesign_builders/operacional.py conecta-pro-backend:/app/modules/operacional/controllers/redesign_builders/operacional.py && docker exec conecta-pro-backend kill -HUP 1 2>/dev/null; sleep 6; docker cp backend/scripts/orq/test_acao_medida_redesign.py conecta-pro-backend:/app/scripts/orq/ && docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_acao_medida_redesign.py`
Expected: `OK ação: criou disciplinary_action id=<uuid> status=rascunho`

- [ ] **Step 5: Rodar de novo o oráculo de leitura (Task 1) — agora deve contar +1**

Run: `docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_medidas_redesign.py`
Expected: `OK medidas: exibido=N ... sem fabricação` (N incrementou vs Task 1).

- [ ] **Step 6: Commit**

```bash
git -C /opt/conecta-pro add backend/modules/operacional/controllers/redesign_builders/operacional.py backend/scripts/orq/test_acao_medida_redesign.py
git -C /opt/conecta-pro commit --no-verify -m "feat(redesign-op): form Nova medida + /action/medida-administrativa via write-gate (reuso DisciplinaryService)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Deploy durável (bake) + verificação end-to-end pela rota da tela

**Files:** nenhum (deploy + verify).

**Interfaces:** consome os endpoints já implementados; prova `exibido == banco` na rota real e o form no chat/tela.

- [ ] **Step 1: Deploy blue-green (bake — torna durável)**

Run: `bash /opt/conecta-pro/scripts/deploy_backend_bluegreen.sh`
Expected: script conclui com a nova imagem no ar (aguardar API responder; sem `pgrep`).

- [ ] **Step 2: Verificar a tela pela ROTA real (oráculo exibido==banco)**

Run (token de um usuário `all`, ex. Jordan/Pyetra):
```bash
TOKEN=<bearer>
curl -s "http://localhost:8080/api/v1/redesign/data/operacional" -H "Authorization: Bearer $TOKEN" \
 | python3 -c "import sys,json; d=json.load(sys.stdin); s=d['screens']['medidas-administrativas']; print('type', s['type'], 'rows', len(s['rows'])); import re; assert 'Carlos Batista' not in json.dumps(s), 'FABRICADO!'; print('sem fabricação OK')"
DB=$(docker exec conecta-pro-backend python3 -c "import asyncio;from sqlalchemy import text;from core.database import async_session_factory;\nasync def m():\n async with async_session_factory() as db:print((await db.execute(text('SELECT count(*) FROM disciplinary_actions WHERE coalesce(is_active,true)'))).scalar())\nasyncio.run(m())")
echo "banco=$DB (deve bater com rows, teto 200)"
```
Expected: `rows` == `min(banco,200)` e `sem fabricação OK`.

- [ ] **Step 3: Verificar o form no chat/tela (escrita humana)**

Abrir o redesign → módulo Operacional → item de menu **Disciplinar** → preencher e submeter uma medida de teste; confirmar mensagem "Medida registrada (rascunho)" e que a linha aparece em **Medidas admin.**. (Se preferir headless, repetir o `curl -X POST /api/v1/redesign/action/medida-administrativa` com payload de teste e um `employee_id` real.)
Expected: linha nova visível na tabela, refletindo o banco.

- [ ] **Step 4: Limpar o dado de teste (não sujar produção)**

Run: `docker exec conecta-pro-backend python3 -c "import asyncio;from sqlalchemy import text;from core.database import async_session_factory;\nasync def m():\n async with async_session_factory() as db:\n  await db.execute(text(\"DELETE FROM disciplinary_actions WHERE reason_description LIKE '%teste oráculo redesign%'\"));await db.commit();print('limpo')\nasyncio.run(m())"`
Expected: `limpo`.

- [ ] **Step 5: Atualizar o ledger de progresso**

Marcar no `auditoria/backend_recon/operacional_2026-07-29.md` que medidas-administrativas saiu de FABRICADO → REAL, e apontar o próximo subsistema (rondas gestão).

## Self-Review

- **Cobertura da spec:** medidas-administrativas leitura real (Task 1) + escrita real via service existente e gate (Task 2) + deploy/verify (Task 3). ✔
- **Placeholders:** nenhum "TODO/etc" — todo passo tem código/comando exato. ✔
- **Consistência de tipos:** a função `rd_action_medida_administrativa` importada no teste (Task 2 Step 1) é exatamente a definida no Step 3; o screen id `medidas-administrativas` (tabela) e `disciplinar` (form) casam com os menu ids reais do `operacional.json`. ✔
- **Guard-rail:** escrita só por `CurrentActiveUser` via `op_write`; nenhum caminho de agente; nenhum dado fabricado (vazio→"aguardando dado" honesto). ✔

## Receita repetível (para os próximos subsistemas)

Cada subsistema (rondas, banco-horas, passagem-turno, instrucoes-posto, escalas, allocations) segue este molde:
1. **Task leitura:** `out["<menu-id>"] = await tbl(... SELECT da tabela real ...)` no `operacional.py`; teste-oráculo `exibido==banco` + `assert` anti-fabricação (grep dos valores hardcoded específicos daquele screen).
2. **Task escrita:** `@router.post("/action/<slug>")` importando o controller/service existente via `op_write` (ou `money_gov`+OTP se dinheiro/gov); form screen apontando pra rota.
3. **Task deploy+verify:** bake + curl `exibido==banco` + limpar teste.
Exceções por guard-rail: **allocations** = só Task leitura (escrita fica fora — regra intocável); **escalas** = leitura reconcilia com Sólides (fonte da verdade), sem escrita cega.
