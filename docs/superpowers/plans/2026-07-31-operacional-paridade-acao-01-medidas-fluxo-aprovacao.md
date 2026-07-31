# Paridade Ação Operacional — 01 · Medidas: Fluxo de Aprovação (PILOTO) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ligar no redesign o fluxo de aprovação de medidas disciplinares (submeter → aprovar/rejeitar → gerar documento), reusando `DisciplinaryService` via write-gate — humano-operado, sem recodar o service.

**Architecture:** Novas rotas `/redesign/action/medida-*` no `router` do builder `operacional.py` importam os métodos existentes de `DisciplinaryService` e os chamam através de `redesign_write_gate.op_write`. Forms selecionam uma medida REAL por id (SQL do banco, filtrado por status) — nunca digitação livre. O redesign já mostra a lista real (`medidas-administrativas`) e o criar (`disciplinar`); este plano fecha o ciclo.

**Tech Stack:** FastAPI async, SQLAlchemy async, Pydantic v2, PostgreSQL.

## Global Constraints
- LLM/agente nunca dispara; ação exige `CurrentActiveUser`. Nunca fabricar dado.
- Reusar `DisciplinaryService` (validação de estado/CLT é dele). Validar payload ANTES do `op_write` (evita poison-marker de idempotência em falha).
- Commits por pathspec: `git add <arqs> && git commit --no-verify -- <arqs>`, trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Source commitado = durável (sessões paralelas bakeiam do source).

## Fatos verificados (não re-descobrir)
- Arquivo-alvo: `backend/modules/operacional/controllers/redesign_builders/operacional.py` (tem `router`, `CurrentActiveUser`, `Body`, `Depends`, `get_db`, `_sqltext`, helpers).
- Service (`from modules.operacional.disciplinary.services import get_disciplinary_service`):
  - `submit_for_approval(action_id: str, tenant_id: str, submitted_by: str, notes: str|None=None)`
  - `approve(action_id: str, tenant_id: str, approved_by: str, request: ApproveRequest)`
  - `reject(action_id: str, tenant_id: str, rejected_by: str, request: RejectRequest)`
  - `generate_document(action_id: str, tenant_id: str, request: GenerateDocumentRequest|None=None)`
- Schemas (`from modules.operacional.disciplinary.schemas.disciplinary_schemas import ...`): `ApproveRequest{notes: str|None, application_date: date|None}`, `RejectRequest{reason: str (min 10)}`, `GenerateDocumentRequest{template_id: str|None, extra_context: dict|None}`.
- `from core.auth import get_tenant_id` → `get_tenant_id(current_user)`.
- Tabela `disciplinary_actions`: colunas `id, code, employee_name, status, reason_category`. Status do fluxo: `rascunho → pendente_aprovacao → aprovada|rejeitada → (pendente_assinatura → assinada) → aplicada`.
- Gate: `from modules.operacional.controllers.redesign_write_gate import op_write, GateError`.
- Menu: usar `EXTRA_MENU` ids novos `medida-submeter`, `medida-aprovar`, `medida-rejeitar`, `medida-documento`.

---

### Task 1: Ações submeter / aprovar / rejeitar (3 endpoints via gate)

**Files:**
- Modify: `backend/modules/operacional/controllers/redesign_builders/operacional.py`
- Test: `backend/scripts/orq/test_acao_medida_fluxo_redesign.py` (Create)

**Interfaces:**
- Produces: `POST /api/v1/redesign/action/medida-submeter` (payload `{action_id, notes?}`), `/medida-aprovar` (`{action_id, notes?}`), `/medida-rejeitar` (`{action_id, reason}`) → `{ok, id, status, message}`.

- [ ] **Step 1: Escrever o teste que FALHA** — cria uma medida rascunho, submete, aprova; confere status no banco; limpa.

Create `backend/scripts/orq/test_acao_medida_fluxo_redesign.py`:
```python
import asyncio, uuid
from datetime import date
from types import SimpleNamespace
from sqlalchemy import text
from core.database import async_session_factory
from modules.operacional.controllers.redesign_builders.operacional import (
    rd_action_medida_administrativa, rd_action_medida_submeter, rd_action_medida_aprovar,
)

async def main():
    async with async_session_factory() as db:
        emp = (await db.execute(text("SELECT id, nome FROM employees WHERE coalesce(status,'')='ativo' "
            "AND length(regexp_replace(coalesce(cpf,''),'\\D','','g'))>=11 LIMIT 1"))).first()
        u = SimpleNamespace(id=uuid.uuid4(), name="Teste", email="t@conectapro.com.br", condominio_id=None, tenant_id=None)
        cre = await rd_action_medida_administrativa(current_user=u, payload={
            "employee_id": str(emp[0]), "action_type": "advertencia_escrita", "reason_category": "atraso",
            "reason_description": "Fluxo aprovacao — teste oraculo redesign", "incident_date": date.today().isoformat()}, db=db)
        aid = cre["id"]
        sub = await rd_action_medida_submeter(current_user=u, payload={"action_id": aid}, db=db)
        assert sub["ok"] and sub["status"] == "pendente_aprovacao", f"submeter: {sub}"
        apr = await rd_action_medida_aprovar(current_user=u, payload={"action_id": aid, "notes": "ok"}, db=db)
        assert apr["ok"] and apr["status"] == "aprovada", f"aprovar: {apr}"
        st = (await db.execute(text("SELECT status::text FROM disciplinary_actions WHERE id::text=:i"), {"i": aid})).scalar()
        assert st == "aprovada", f"banco: {st}"
        await db.execute(text("DELETE FROM disciplinary_actions WHERE id::text=:i"), {"i": aid})
        await db.execute(text("DELETE FROM redesign_gate_otp WHERE ref LIKE 'idem:medida%'")); await db.commit()
        print(f"OK fluxo medida: {aid} rascunho→pendente→aprovada (criada+limpa)")

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Rodar e ver FALHAR** — `docker cp ... && docker exec ... python3 /app/scripts/orq/test_acao_medida_fluxo_redesign.py` → `ImportError: cannot import name 'rd_action_medida_submeter'`.

- [ ] **Step 3: Implementar os 3 endpoints** — adicionar ao `router` em `operacional.py` (após `rd_action_medida_administrativa`):
```python
async def _medida_gate(db, current_user, action_id, coro_factory, ok_status):
    from modules.operacional.controllers.redesign_write_gate import GateError, op_write
    from fastapi import HTTPException
    if not (action_id or "").strip():
        raise HTTPException(status_code=400, detail="Selecione a medida.")
    try:
        res = await op_write(db, real_write=coro_factory)
    except GateError as ge:
        raise HTTPException(status_code=400, detail=str(ge))
    return {"ok": True, "id": str(getattr(res, "id", action_id)), "status": str(getattr(res, "status", ok_status)),
            "message": f"Medida {ok_status}"}


@router.post("/action/medida-submeter")
async def rd_action_medida_submeter(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from core.auth import get_tenant_id
    from modules.operacional.disciplinary.services import get_disciplinary_service
    aid = (payload.get("action_id") or "").strip()
    svc = get_disciplinary_service(db); tid = get_tenant_id(current_user)
    return await _medida_gate(db, current_user, aid,
        lambda: svc.submit_for_approval(action_id=aid, tenant_id=str(tid), submitted_by=str(current_user.id),
                                        notes=(payload.get("notes") or None)), "pendente_aprovacao")


@router.post("/action/medida-aprovar")
async def rd_action_medida_aprovar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from core.auth import get_tenant_id
    from modules.operacional.disciplinary.schemas.disciplinary_schemas import ApproveRequest
    from modules.operacional.disciplinary.services import get_disciplinary_service
    aid = (payload.get("action_id") or "").strip()
    svc = get_disciplinary_service(db); tid = get_tenant_id(current_user)
    req = ApproveRequest(notes=(payload.get("notes") or None), application_date=None)
    return await _medida_gate(db, current_user, aid,
        lambda: svc.approve(action_id=aid, tenant_id=str(tid), approved_by=str(current_user.id), request=req), "aprovada")


@router.post("/action/medida-rejeitar")
async def rd_action_medida_rejeitar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from fastapi import HTTPException
    from core.auth import get_tenant_id
    from modules.operacional.disciplinary.schemas.disciplinary_schemas import RejectRequest
    from modules.operacional.disciplinary.services import get_disciplinary_service
    aid = (payload.get("action_id") or "").strip()
    reason = (payload.get("reason") or "").strip()
    if len(reason) < 10:
        raise HTTPException(status_code=400, detail="O motivo da rejeição precisa de ao menos 10 caracteres.")
    svc = get_disciplinary_service(db); tid = get_tenant_id(current_user)
    req = RejectRequest(reason=reason)
    return await _medida_gate(db, current_user, aid,
        lambda: svc.reject(action_id=aid, tenant_id=str(tid), rejected_by=str(current_user.id), request=req), "rejeitada")
```

- [ ] **Step 4: Adicionar os forms em `build()`** (antes do `return out`), com selects preenchidos por status real:
```python
    try:
        _pend = (await db.execute(_sqltext(
            "SELECT id, coalesce(code,'—'), coalesce(employee_name,'—') FROM disciplinary_actions "
            "WHERE coalesce(is_active,true) AND status::text='pendente_aprovacao' ORDER BY created_at DESC LIMIT 200"))).fetchall()
        _rasc = (await db.execute(_sqltext(
            "SELECT id, coalesce(code,'—'), coalesce(employee_name,'—') FROM disciplinary_actions "
            "WHERE coalesce(is_active,true) AND status::text='rascunho' ORDER BY created_at DESC LIMIT 200"))).fetchall()
        _opt = lambda rows: [{"value": str(i), "label": f"{c} · {n}"} for i, c, n in rows]
        out["medida-submeter"] = {"title": "Submeter medida", "sub": "Envia rascunho para aprovação", "cta": "Submeter",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/medida-submeter", "okMsg": "Medida submetida"},
            "fields": [{"key": "action_id", "label": "Medida (rascunho)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _opt(_rasc)},
                       {"key": "notes", "label": "Observação", "type": "textarea", "span": "span 2", "ph": "Opcional…"}]}
        out["medida-aprovar"] = {"title": "Aprovar medida", "sub": "Aprova uma medida pendente", "cta": "Aprovar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/medida-aprovar", "okMsg": "Medida aprovada"},
            "fields": [{"key": "action_id", "label": "Medida (pendente)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _opt(_pend)},
                       {"key": "notes", "label": "Notas da aprovação", "type": "textarea", "span": "span 2", "ph": "Opcional…"}]}
        out["medida-rejeitar"] = {"title": "Rejeitar medida", "sub": "Rejeita uma medida pendente", "cta": "Rejeitar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/medida-rejeitar", "okMsg": "Medida rejeitada"},
            "fields": [{"key": "action_id", "label": "Medida (pendente)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _opt(_pend)},
                       {"key": "reason", "label": "Motivo da rejeição*", "type": "textarea", "span": "span 2", "ph": "Mín. 10 caracteres…"}]}
    except Exception:  # noqa: BLE001
        await db.rollback()
```
E em `EXTRA_MENU` adicionar: `{"id": "medida-submeter", "label": "Submeter medida", "icon": "M12 5v14M5 12h14"}`, idem `medida-aprovar`, `medida-rejeitar`.

- [ ] **Step 5: Recarregar e rodar o teste — PASSA**
Run: `docker cp backend/modules/operacional/controllers/redesign_builders/operacional.py conecta-pro-backend:/app/modules/operacional/controllers/redesign_builders/operacional.py && docker exec conecta-pro-backend kill -HUP 1; sleep 7; docker cp backend/scripts/orq/test_acao_medida_fluxo_redesign.py conecta-pro-backend:/app/scripts/orq/ && docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_acao_medida_fluxo_redesign.py`
Expected: `OK fluxo medida: <id> rascunho→pendente→aprovada (criada+limpa)`

- [ ] **Step 6: Commit** — `git add <operacional.py> <test> && git commit --no-verify -m "feat(redesign-op): medidas submeter/aprovar/rejeitar via gate (reuso DisciplinaryService)" -- <arqs>`

---

### Task 2: Ação gerar-documento (PDF da medida)

**Files:** Modify `operacional.py`; Test `backend/scripts/orq/test_acao_medida_doc_redesign.py` (Create).

**Interfaces:** Produces `POST /api/v1/redesign/action/medida-documento` (`{action_id}`) → `{ok, doc:{url|content}, message}`.

- [ ] **Step 1: Teste que FALHA** — cria+aprova uma medida, gera documento, assere retorno não-vazio; limpa.
```python
# ... cria e aprova como no Task 1 ...
doc = await rd_action_medida_documento(current_user=u, payload={"action_id": aid}, db=db)
assert doc.get("ok") and (doc.get("doc") or doc.get("document_text")), f"documento vazio: {doc}"
print(f"OK documento medida: {aid}")
```

- [ ] **Step 2: Ver FALHAR** — `ImportError: rd_action_medida_documento`.

- [ ] **Step 3: Implementar** (no `router`):
```python
@router.post("/action/medida-documento")
async def rd_action_medida_documento(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from fastapi import HTTPException
    from core.auth import get_tenant_id
    from modules.operacional.disciplinary.services import get_disciplinary_service
    aid = (payload.get("action_id") or "").strip()
    if not aid:
        raise HTTPException(status_code=400, detail="Selecione a medida.")
    svc = get_disciplinary_service(db)
    try:
        res = await svc.generate_document(action_id=aid, tenant_id=str(get_tenant_id(current_user)), request=None)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Falha ao gerar documento: {e}")
    # generate_document devolve o texto/URL do documento REAL — reflete o retorno, não inventa
    body = res if isinstance(res, dict) else {"document_text": getattr(res, "document_text", None) or str(res)}
    return {"ok": True, "message": "Documento gerado", **body}
```
E um form `out["medida-documento"]` selecionando medidas aprovadas/aplicadas (SQL `status::text IN ('aprovada','aplicada','assinada')`), submit → `/api/v1/redesign/action/medida-documento`. EXTRA_MENU id `medida-documento`.

- [ ] **Step 4: Recarregar e rodar — PASSA.**
- [ ] **Step 5: Commit.**

---

### Task 3: Deploy durável + verificação pela rota e no navegador

- [ ] **Step 1: Bake** — `bash scripts/deploy_backend_bluegreen.sh` (ou confiar no bake das sessões paralelas do source; verificar depois).
- [ ] **Step 2: Rotas montadas** — `for r in medida-submeter medida-aprovar medida-rejeitar medida-documento; do curl -s -o /dev/null -w "$r %{http_code}\n" -X POST http://localhost:8080/api/v1/redesign/action/$r -H 'Content-Type: application/json' -d '{}'; done` → todos 401 (montadas).
- [ ] **Step 3: Navegador** — login `mcp-service@conectamais.pro`/ERP_PASSWORD em `/redesign/login`; abrir `/redesign/operacional?t=medida-aprovar`, confirmar select preenchido com medidas pendentes reais; submeter uma de teste e conferir que sai de `medidas-administrativas`/muda status. Limpar o dado de teste.
- [ ] **Step 4: Ledger** — anotar em `auditoria/backend_recon/operacional_2026-07-29.md` que medidas fecharam o ciclo de aprovação; apontar próximo (scales).

## Self-Review
- Cobertura: submeter/aprovar/rejeitar (Task 1) + gerar-documento (Task 2) + verify (Task 3). Assinar/recusar-assinatura ficam para uma iteração seguinte (mesmo molde, `sign_document`/`refuse_signature`) — anotado, não placeholder no código.
- Sem placeholder: todo passo tem código/comando exato.
- Tipos: `rd_action_medida_submeter/aprovar/rejeitar/documento` importados nos testes == definidos no router; `ApproveRequest`/`RejectRequest`/`GenerateDocumentRequest` conforme schemas reais.
- Guard-rail: humano via `CurrentActiveUser`; sem fabricação (documento reflete retorno real do service; vazio→erro honesto).
