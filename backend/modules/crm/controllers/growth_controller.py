"""
Controller das 9 features de crescimento do CRM (HubSpot-like).
Um único router montado sob /crm. Endpoints públicos: /public/forms/* e /public/booking/*.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db
from modules.crm.models.lead import Lead
from modules.crm.services import growth_services as G

router = APIRouter(tags=["CRM - Growth"])


def _rows(result) -> list[dict]:
    return [dict(r) for r in result.mappings().all()]


async def _one(db, sql, params) -> dict | None:
    r = (await db.execute(text(sql), params)).mappings().first()
    return dict(r) if r else None


_PUBLIC_ERP = os.getenv("PUBLIC_ERP_URL", "https://erp.conectamais.pro").rstrip("/")
_DOCS_DIR = "/app/uploads/docs"


async def _salvar_pdf(db, tipo: str, titulo: str, pdf_bytes: bytes, *, ref_tipo=None, ref_id=None, teste=False) -> dict:
    """Persiste + registra + link público (delega ao serviço compartilhado docs_registry)."""
    from modules.crm.services.docs_registry import salvar_pdf

    return await salvar_pdf(db, tipo, titulo, pdf_bytes, ref_tipo=ref_tipo, ref_id=ref_id, teste=teste)


@router.get("/docs/download/{doc_id}")
async def baixar_documento(doc_id: str, t: str = "", db: AsyncSession = Depends(get_db)):
    """Download PÚBLICO (tokenizado) de um documento registrado — clicável no navegador/Cowork."""
    from fastapi import Response

    row = await _one(
        db, "SELECT tipo, titulo, arquivo, token FROM crm_documents WHERE id=:id AND arquivado=false", {"id": doc_id}
    )
    if not row or not t or row["token"] != t:
        raise HTTPException(404, "Documento não encontrado")
    import os as _os

    if not _os.path.exists(row["arquivo"]):
        raise HTTPException(404, "Arquivo não disponível")
    with open(row["arquivo"], "rb") as fh:
        data = fh.read()
    fn = f"{row['tipo']}_{doc_id[:8]}.pdf"
    return Response(
        content=data, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{fn}"'}
    )


@router.get("/docs")
async def listar_documentos(db: AsyncSession = Depends(get_db), tipo: str | None = None, limite: int = 50):
    """Lista os documentos gerados/registrados (registro no Conecta PRO). Ignora arquivados."""
    where = "WHERE arquivado=false" + (" AND tipo=:tipo" if tipo else "")
    rows = _rows(
        await db.execute(
            text(f"""
        SELECT id, tipo, titulo, token, tamanho_kb, teste, to_char(created_at,'DD/MM/YYYY HH24:MI') criado
        FROM crm_documents {where} ORDER BY created_at DESC LIMIT :lim
    """),
            {"tipo": tipo, "lim": limite} if tipo else {"lim": limite},
        )
    )
    for r in rows:
        r["download_url"] = f"{_PUBLIC_ERP}/api/v1/crm/docs/download/{r['id']}?t={r.pop('token')}"
    return {"total": len(rows), "documentos": rows}


@router.get("/audit")
async def consultar_auditoria(
    db: AsyncSession = Depends(get_db), limite: int = 50, metodo: str | None = None, busca: str | None = None
):
    """Log de auditoria das escritas (quem/quando/o quê/resultado). Filtra por método (POST/PUT/DELETE)
    ou trecho do caminho (busca)."""
    where, p = ["1=1"], {"lim": limite}
    if metodo:
        where.append("a.method = :m")
        p["m"] = metodo.upper()
    if busca:
        where.append("a.path ILIKE :b")
        p["b"] = f"%{busca}%"
    rows = _rows(
        await db.execute(
            text(f"""
        SELECT to_char(a.ts,'DD/MM/YYYY HH24:MI:SS') quando, COALESCE(u.name, u.email, '—') quem,
               a.method metodo, a.path caminho, a.status, a.ip
        FROM crm_audit_log a LEFT JOIN users u ON u.id = a.user_id
        WHERE {" AND ".join(where)} ORDER BY a.ts DESC LIMIT :lim
    """),
            p,
        )
    )
    return {"total": len(rows), "eventos": rows}


# ===================================================================== PRECIFICAÇÃO (CCT 2026)
@router.get("/pricing/parametros")
async def pricing_parametros(db: AsyncSession = Depends(get_db)):
    """Parâmetros editáveis de precificação (Lucro Real, CCT 2026) — encargos, tributos, margem, benefícios."""
    rows = _rows(
        await db.execute(text("SELECT chave, valor, label, grupo FROM crm_pricing_params ORDER BY grupo, chave"))
    )
    for r in rows:
        r["valor"] = float(r["valor"])
    return {"regime": "Lucro Real · CCT 2026 SINDECOMPRESTS", "parametros": rows}


class ParamsIn(BaseModel):
    valores: dict


@router.put("/pricing/parametros")
async def pricing_atualizar_parametros(
    data: ParamsIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    """Atualiza parâmetros (sincronizar a planilha). valores = {chave: valor}."""
    n = 0
    for k, v in (data.valores or {}).items():
        res = await db.execute(
            text("UPDATE crm_pricing_params SET valor=:v, updated_at=now() WHERE chave=:k"), {"v": float(v), "k": k}
        )
        n += res.rowcount or 0
    await db.commit()
    return {"atualizados": n}


@router.get("/pricing/funcoes")
async def pricing_funcoes(db: AsyncSession = Depends(get_db)):
    """Tabela de preços por função (custo, preço, markup, adicionais) — alinhada à planilha."""
    from modules.crm.services.pricing_cct import calcular_funcao

    rows = _rows(await db.execute(text("SELECT * FROM crm_pricing_funcoes WHERE ativo ORDER BY ordem")))
    out = []
    for r in rows:
        c = await calcular_funcao(db, r)
        out.append(
            {
                "funcao": c["funcao"],
                "adicionais": c["adicionais"],
                "salario_base": c["salario_base"],
                "custo_total": c["custo_total"],
                "preco": c["preco"],
                "markup_pct": c["markup_pct"],
                "lucro_liquido": c["lucro_liquido"],
            }
        )
    return {"regime": "Lucro Real · Margem 15% · CCT 2026", "funcoes": out}


class SimularIn(BaseModel):
    funcao: str | None = None
    salario_base: float | None = None
    jornada_dias: int = 15
    postos: int = 1
    noturno: bool = False
    hora_reduzida: bool = False
    ronda: bool = False
    periculosidade: bool = False
    insalubridade: bool = False
    margem: float | None = None


@router.post("/pricing/simular")
async def pricing_simular(data: SimularIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Simula o preço de uma função (replica o simulador da planilha). Aceita função existente OU salário base."""
    from modules.crm.services.pricing_cct import calcular, carregar_params

    base, jornada = data.salario_base, data.jornada_dias
    flags = {
        "noturno": data.noturno,
        "hora_reduzida": data.hora_reduzida,
        "ronda": data.ronda,
        "periculosidade": data.periculosidade,
        "insalubridade": data.insalubridade,
        "margem": data.margem,
    }
    if data.funcao and base is None:
        row = await _one(
            db,
            """SELECT salario_base, jornada_dias, noturno, hora_reduzida, ronda,
                                periculosidade, insalubridade FROM crm_pricing_funcoes WHERE nome ILIKE :n""",
            {"n": data.funcao},
        )
        if row:
            base = float(row["salario_base"])
            jornada = int(row["jornada_dias"])
            # a função carrega seus adicionais; o payload pode ATIVAR mais (OR)
            for k in ("noturno", "hora_reduzida", "ronda", "periculosidade", "insalubridade"):
                flags[k] = bool(flags.get(k)) or bool(row[k])
    if base is None:
        base = 1670
    r = calcular(base, jornada, flags, await carregar_params(db))
    r["postos"] = data.postos
    r["preco_total_postos"] = round(r["preco"] * data.postos, 2)
    return r


@router.delete("/docs/{doc_id}", status_code=204)
async def excluir_documento(doc_id: str, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Exclui (soft-delete) um documento registrado."""
    await db.execute(text("UPDATE crm_documents SET arquivado=true WHERE id=:id"), {"id": doc_id})
    await db.commit()


@router.post("/docs/expurgar-teste")
async def expurgar_documentos_teste(
    _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db), confirmar: bool = False
):
    """Arquiva (soft-delete) TODOS os documentos de teste (teste=true). confirmar=false só mostra a contagem."""
    n = (await _one(db, "SELECT count(*) v FROM crm_documents WHERE teste=true AND arquivado=false", {})) or {}
    qtd = int(n.get("v", 0))
    if not confirmar:
        return {
            "preview": True,
            "documentos_teste": qtd,
            "aviso": f"{qtd} documento(s) de teste serão arquivados. Reenvie com confirmar=true.",
        }
    await db.execute(text("UPDATE crm_documents SET arquivado=true WHERE teste=true AND arquivado=false"))
    await db.commit()
    return {"expurgados": qtd}


# ===================================================================== ASSETS (upload sem SSH)
_ASSETS_DIR = "/app/uploads/assets"
_ASSET_NAMES = {  # tipo -> nome canônico do arquivo lido pelo gerador de PDF
    "logo": "logo-conecta-mais.png",
    "logo_transparente": "logo-transparente.png",
    "logo_branco": "logo-branco.png",
    "selo": "selo.png",
}


class AssetUploadIn(BaseModel):
    tipo: str = "logo"
    conteudo_base64: str
    nome: str | None = None


@router.post("/assets/upload", status_code=201)
async def upload_asset(data: AssetUploadIn, _=Depends(get_current_active_user)):
    """Recebe um asset (logo/selo) em base64 e grava no volume PERSISTENTE /app/uploads/assets.
    O gerador de PDF passa a usar o logo comercial automaticamente (sem rebuild)."""
    import base64
    import os

    raw = data.conteudo_base64
    if "," in raw and raw.strip().startswith("data:"):  # tira prefixo data URI se vier
        raw = raw.split(",", 1)[1]
    try:
        blob = base64.b64decode(raw, validate=False)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"base64 inválido: {exc}")
    if not blob:
        raise HTTPException(400, "conteúdo vazio")
    nome = data.nome or _ASSET_NAMES.get(data.tipo, f"{data.tipo}.png")
    nome = os.path.basename(nome)  # evita path traversal
    os.makedirs(_ASSETS_DIR, exist_ok=True)
    dest = os.path.join(_ASSETS_DIR, nome)
    with open(dest, "wb") as fh:
        fh.write(blob)
    return {"ok": True, "arquivo": nome, "tamanho_kb": round(len(blob) / 1024, 1), "destino": dest}


@router.get("/assets")
async def listar_assets(_=Depends(get_current_active_user)):
    """Lista os assets enviados (persistentes)."""
    import os

    if not os.path.isdir(_ASSETS_DIR):
        return {"assets": []}
    out = []
    for n in sorted(os.listdir(_ASSETS_DIR)):
        fp = os.path.join(_ASSETS_DIR, n)
        if os.path.isfile(fp):
            out.append({"nome": n, "tamanho_kb": round(os.path.getsize(fp) / 1024, 1)})
    return {"assets": out}


# =====================================================================================
# 4) CATÁLOGO DE PRODUTOS/SERVIÇOS (SKU)
# =====================================================================================
class ProductIn(BaseModel):
    name: str
    sku: str | None = None
    description: str | None = None
    category: str | None = None
    unit: str = "un"
    unit_price: float = 0
    is_recurring: bool = False
    service_type: str | None = None
    is_active: bool = True


@router.get("/products")
async def list_products(
    db: AsyncSession = Depends(get_db), search: str | None = None, category: str | None = None, only_active: bool = True
):
    where = ["1=1"]
    p: dict[str, Any] = {}
    if only_active:
        where.append("is_active = true")
    if search:
        where.append("(name ILIKE :s OR sku ILIKE :s)")
        p["s"] = f"%{search}%"
    if category:
        where.append("category = :c")
        p["c"] = category
    return _rows(await db.execute(text(f"SELECT * FROM crm_products WHERE {' AND '.join(where)} ORDER BY name"), p))


@router.post("/products", status_code=201)
async def create_product(data: ProductIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    return (
        await _one(
            db,
            """
        INSERT INTO crm_products (id, sku, name, description, category, unit, unit_price, is_recurring,
                                  service_type, is_active, created_at, updated_at)
        VALUES (gen_random_uuid(), :sku, :name, :description, :category, :unit, :unit_price, :is_recurring,
                :service_type, :is_active, now(), now()) RETURNING *
    """,
            data.model_dump(),
        )
        or {}
    )


@router.put("/products/{pid}")
async def update_product(
    pid: str, data: ProductIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    row = await _one(
        db,
        """
        UPDATE crm_products SET sku=:sku, name=:name, description=:description, category=:category,
            unit=:unit, unit_price=:unit_price, is_recurring=:is_recurring, service_type=:service_type,
            is_active=:is_active, updated_at=now() WHERE id=:id RETURNING *
    """,
        {**data.model_dump(), "id": pid},
    )
    if not row:
        raise HTTPException(404, "Produto não encontrado")
    return row


@router.delete("/products/{pid}", status_code=204)
async def delete_product(pid: str, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await db.execute(text("UPDATE crm_products SET is_active=false, updated_at=now() WHERE id=:id"), {"id": pid})
    await db.commit()


# =====================================================================================
# 1) SEQUÊNCIAS / CADÊNCIAS
# =====================================================================================
class SequenceIn(BaseModel):
    name: str
    description: str | None = None
    channel: str = "email"
    steps: list[dict] = []
    is_active: bool = True


@router.get("/sequences")
async def list_sequences(db: AsyncSession = Depends(get_db)):
    return _rows(await db.execute(text("SELECT * FROM crm_sequences ORDER BY created_at DESC")))


@router.post("/sequences", status_code=201)
async def create_sequence(data: SequenceIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    import json

    return (
        await _one(
            db,
            """
        INSERT INTO crm_sequences (id, name, description, channel, steps, is_active, created_at, updated_at)
        VALUES (gen_random_uuid(), :name, :description, :channel, CAST(:steps AS jsonb), :is_active, now(), now())
        RETURNING *
    """,
            {**data.model_dump(exclude={"steps"}), "steps": json.dumps(data.steps)},
        )
        or {}
    )


@router.put("/sequences/{sid}")
async def update_sequence(
    sid: str, data: SequenceIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    import json

    row = await _one(
        db,
        """
        UPDATE crm_sequences SET name=:name, description=:description, channel=:channel,
            steps=CAST(:steps AS jsonb), is_active=:is_active, updated_at=now() WHERE id=:id RETURNING *
    """,
        {**data.model_dump(exclude={"steps"}), "steps": json.dumps(data.steps), "id": sid},
    )
    if not row:
        raise HTTPException(404, "Sequência não encontrada")
    return row


@router.delete("/sequences/{sid}", status_code=204)
async def delete_sequence(sid: str, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await db.execute(text("DELETE FROM crm_sequences WHERE id=:id"), {"id": sid})
    await db.commit()


class EnrollIn(BaseModel):
    lead_id: str


@router.post("/sequences/{sid}/enroll", status_code=201)
async def enroll_in_sequence(
    sid: str, data: EnrollIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    seq = await _one(db, "SELECT id, steps FROM crm_sequences WHERE id=:id AND is_active=true", {"id": sid})
    if not seq:
        raise HTTPException(404, "Sequência não encontrada ou inativa")
    eid = await G.enroll_lead(db, seq, data.lead_id)
    return {"enrollment_id": eid, "enrolled": bool(eid)}


@router.get("/sequences/{sid}/enrollments")
async def list_enrollments(sid: str, db: AsyncSession = Depends(get_db)):
    return _rows(
        await db.execute(
            text("""
        SELECT e.*, l.name lead_name, l.email lead_email FROM crm_sequence_enrollments e
        LEFT JOIN leads l ON l.id = e.lead_id WHERE e.sequence_id=:s ORDER BY e.enrolled_at DESC
    """),
            {"s": sid},
        )
    )


@router.post("/sequences/process-due")
async def process_due(_=Depends(get_current_active_user), db: AsyncSession = Depends(get_db), limit: int = 100):
    """Processa manualmente os passos vencidos (o Celery beat chama isso de hora em hora)."""
    return await G.process_due_enrollments(db, limit)


# =====================================================================================
# 2) WORKFLOWS / AUTOMAÇÃO
# =====================================================================================
class WorkflowIn(BaseModel):
    name: str
    description: str | None = None
    trigger_event: str
    conditions: list[dict] = []
    actions: list[dict] = []
    is_active: bool = True


@router.get("/workflows")
async def list_workflows(db: AsyncSession = Depends(get_db)):
    return _rows(await db.execute(text("SELECT * FROM crm_workflows ORDER BY created_at DESC")))


@router.post("/workflows", status_code=201)
async def create_workflow(data: WorkflowIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    import json

    return (
        await _one(
            db,
            """
        INSERT INTO crm_workflows (id, name, description, trigger_event, conditions, actions, is_active,
                                   run_count, created_at, updated_at)
        VALUES (gen_random_uuid(), :name, :description, :trigger_event, CAST(:conditions AS jsonb),
                CAST(:actions AS jsonb), :is_active, 0, now(), now()) RETURNING *
    """,
            {
                **data.model_dump(exclude={"conditions", "actions"}),
                "conditions": json.dumps(data.conditions),
                "actions": json.dumps(data.actions),
            },
        )
        or {}
    )


@router.put("/workflows/{wid}")
async def update_workflow(
    wid: str, data: WorkflowIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    import json

    row = await _one(
        db,
        """
        UPDATE crm_workflows SET name=:name, description=:description, trigger_event=:trigger_event,
            conditions=CAST(:conditions AS jsonb), actions=CAST(:actions AS jsonb), is_active=:is_active,
            updated_at=now() WHERE id=:id RETURNING *
    """,
        {
            **data.model_dump(exclude={"conditions", "actions"}),
            "conditions": json.dumps(data.conditions),
            "actions": json.dumps(data.actions),
            "id": wid,
        },
    )
    if not row:
        raise HTTPException(404, "Workflow não encontrado")
    return row


@router.delete("/workflows/{wid}", status_code=204)
async def delete_workflow(wid: str, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await db.execute(text("DELETE FROM crm_workflows WHERE id=:id"), {"id": wid})
    await db.commit()


class WorkflowTestIn(BaseModel):
    lead_id: str


@router.post("/workflows/{wid}/test")
async def test_workflow(
    wid: str, data: WorkflowTestIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    wf = await _one(db, "SELECT trigger_event FROM crm_workflows WHERE id=:id", {"id": wid})
    if not wf:
        raise HTTPException(404, "Workflow não encontrado")
    lead = await _one(db, "SELECT * FROM leads WHERE id=:id", {"id": data.lead_id})
    if not lead:
        raise HTTPException(404, "Lead não encontrado")
    fired = await G.run_workflows_for_event(db, wf["trigger_event"], lead, "lead")
    return {"fired": fired}


@router.get("/workflows/{wid}/runs")
async def workflow_runs(wid: str, db: AsyncSession = Depends(get_db)):
    return _rows(
        await db.execute(
            text("SELECT * FROM crm_workflow_runs WHERE workflow_id=:w ORDER BY created_at DESC LIMIT 100"), {"w": wid}
        )
    )


# =====================================================================================
# 3) FORMULÁRIOS DE CAPTURA
# =====================================================================================
class FormIn(BaseModel):
    name: str
    slug: str
    fields: list[dict] = []
    redirect_url: str | None = None
    source: str = "website"
    is_active: bool = True


@router.get("/forms")
async def list_forms(db: AsyncSession = Depends(get_db)):
    return _rows(await db.execute(text("SELECT * FROM crm_forms ORDER BY created_at DESC")))


@router.post("/forms", status_code=201)
async def create_form(data: FormIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    import json

    exists = await _one(db, "SELECT id FROM crm_forms WHERE slug=:s", {"s": data.slug})
    if exists:
        raise HTTPException(409, "Já existe um formulário com esse slug")
    return (
        await _one(
            db,
            """
        INSERT INTO crm_forms (id, name, slug, fields, redirect_url, source, submit_count, is_active,
                               created_at, updated_at)
        VALUES (gen_random_uuid(), :name, :slug, CAST(:fields AS jsonb), :redirect_url, :source, 0,
                :is_active, now(), now()) RETURNING *
    """,
            {**data.model_dump(exclude={"fields"}), "fields": json.dumps(data.fields)},
        )
        or {}
    )


@router.put("/forms/{fid}")
async def update_form(fid: str, data: FormIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    import json

    row = await _one(
        db,
        """
        UPDATE crm_forms SET name=:name, slug=:slug, fields=CAST(:fields AS jsonb), redirect_url=:redirect_url,
            source=:source, is_active=:is_active, updated_at=now() WHERE id=:id RETURNING *
    """,
        {**data.model_dump(exclude={"fields"}), "fields": json.dumps(data.fields), "id": fid},
    )
    if not row:
        raise HTTPException(404, "Formulário não encontrado")
    return row


@router.delete("/forms/{fid}", status_code=204)
async def delete_form(fid: str, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await db.execute(text("DELETE FROM crm_forms WHERE id=:id"), {"id": fid})
    await db.commit()


@router.get("/forms/{fid}/submissions")
async def form_submissions(fid: str, db: AsyncSession = Depends(get_db)):
    return _rows(
        await db.execute(
            text("SELECT * FROM crm_form_submissions WHERE form_id=:f ORDER BY created_at DESC LIMIT 200"), {"f": fid}
        )
    )


# ---- PÚBLICO (sem auth) ----
@router.get("/public/forms/{slug}")
async def public_form(slug: str, db: AsyncSession = Depends(get_db)):
    form = await _one(
        db, "SELECT id, name, slug, fields, redirect_url FROM crm_forms WHERE slug=:s AND is_active=true", {"s": slug}
    )
    if not form:
        raise HTTPException(404, "Formulário não encontrado")
    return form


@router.post("/public/forms/{slug}/submit", status_code=201)
async def public_form_submit(slug: str, payload: dict, request: Request, db: AsyncSession = Depends(get_db)):
    form = await _one(db, "SELECT id, source FROM crm_forms WHERE slug=:s AND is_active=true", {"s": slug})
    if not form:
        raise HTTPException(404, "Formulário não encontrado")
    import json

    name = (payload.get("name") or payload.get("nome") or "Lead do site")[:255]
    email = payload.get("email")
    phone = payload.get("phone") or payload.get("telefone")
    company = payload.get("company") or payload.get("empresa")
    # cria o lead via ORM (aplica defaults score/probability/expected_value)
    lead = Lead(name=name, email=email, phone=phone, company=company, source=form["source"] or "website", status="new")
    db.add(lead)
    await db.flush()
    lead_id = str(lead.id)
    xff = request.headers.get("x-forwarded-for")
    ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else None)
    await db.execute(
        text("""
        INSERT INTO crm_form_submissions (id, form_id, data, lead_id, ip_address, created_at)
        VALUES (gen_random_uuid(), :f, CAST(:data AS jsonb), :lead, :ip, now())
    """),
        {"f": form["id"], "data": json.dumps(payload), "lead": lead_id, "ip": ip},
    )
    await db.execute(text("UPDATE crm_forms SET submit_count = submit_count + 1 WHERE id=:f"), {"f": form["id"]})
    await db.commit()
    # dispara workflows do evento form_submitted + scoring
    leaddict = await _one(db, "SELECT * FROM leads WHERE id=:id", {"id": lead_id})
    await G.run_workflows_for_event(db, "form_submitted", leaddict or {"id": lead_id}, "lead")
    await G.run_workflows_for_event(db, "lead_created", leaddict or {"id": lead_id}, "lead")
    await G.recompute_lead_score(db, lead_id)
    return {"ok": True, "lead_id": lead_id}


# =====================================================================================
# 5) AGENDAMENTO DE REUNIÃO/VISTORIA
# =====================================================================================
class BookingLinkIn(BaseModel):
    name: str
    slug: str
    duration_min: int = 60
    weekly_availability: dict = {}
    is_active: bool = True


@router.get("/booking-links")
async def list_booking_links(db: AsyncSession = Depends(get_db)):
    return _rows(await db.execute(text("SELECT * FROM crm_booking_links ORDER BY created_at DESC")))


@router.post("/booking-links", status_code=201)
async def create_booking_link(
    data: BookingLinkIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    import json

    if await _one(db, "SELECT id FROM crm_booking_links WHERE slug=:s", {"s": data.slug}):
        raise HTTPException(409, "Slug já existe")
    return (
        await _one(
            db,
            """
        INSERT INTO crm_booking_links (id, name, slug, duration_min, weekly_availability, is_active,
                                       created_at, updated_at)
        VALUES (gen_random_uuid(), :name, :slug, :duration_min, CAST(:wa AS jsonb), :is_active, now(), now())
        RETURNING *
    """,
            {**data.model_dump(exclude={"weekly_availability"}), "wa": json.dumps(data.weekly_availability)},
        )
        or {}
    )


@router.put("/booking-links/{bid}")
async def update_booking_link(
    bid: str, data: BookingLinkIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    import json

    row = await _one(
        db,
        """
        UPDATE crm_booking_links SET name=:name, slug=:slug, duration_min=:duration_min,
            weekly_availability=CAST(:wa AS jsonb), is_active=:is_active, updated_at=now() WHERE id=:id RETURNING *
    """,
        {**data.model_dump(exclude={"weekly_availability"}), "wa": json.dumps(data.weekly_availability), "id": bid},
    )
    if not row:
        raise HTTPException(404, "Link não encontrado")
    return row


@router.delete("/booking-links/{bid}", status_code=204)
async def delete_booking_link(bid: str, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await db.execute(text("DELETE FROM crm_booking_links WHERE id=:id"), {"id": bid})
    await db.commit()


@router.get("/bookings")
async def list_bookings(db: AsyncSession = Depends(get_db)):
    return _rows(
        await db.execute(
            text("""
        SELECT b.*, bl.name link_name FROM crm_bookings b
        LEFT JOIN crm_booking_links bl ON bl.id=b.booking_link_id ORDER BY b.scheduled_at DESC LIMIT 200""")
        )
    )


# ---- PÚBLICO ----
@router.get("/public/booking/{slug}")
async def public_booking_link(slug: str, db: AsyncSession = Depends(get_db)):
    link = await _one(
        db,
        """SELECT id, name, slug, duration_min, weekly_availability
                             FROM crm_booking_links WHERE slug=:s AND is_active=true""",
        {"s": slug},
    )
    if not link:
        raise HTTPException(404, "Link de agendamento não encontrado")
    return link


class BookingIn(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    scheduled_at: datetime
    notes: str | None = None


@router.post("/public/booking/{slug}", status_code=201)
async def public_booking_create(slug: str, data: BookingIn, db: AsyncSession = Depends(get_db)):
    link = await _one(db, "SELECT id FROM crm_booking_links WHERE slug=:s AND is_active=true", {"s": slug})
    if not link:
        raise HTTPException(404, "Link de agendamento não encontrado")
    # cria lead do agendamento
    lead = Lead(name=data.name[:255], email=data.email, phone=data.phone, source="website", status="new")
    db.add(lead)
    await db.flush()
    lead_id = str(lead.id)
    booking = await _one(
        db,
        """
        INSERT INTO crm_bookings (id, booking_link_id, name, email, phone, scheduled_at, status, notes,
                                  lead_id, created_at, updated_at)
        VALUES (gen_random_uuid(), :bl, :name, :email, :phone, :sched, 'scheduled', :notes, :lead, now(), now())
        RETURNING *
    """,
        {
            "bl": link["id"],
            "name": data.name[:255],
            "email": data.email,
            "phone": data.phone,
            "sched": data.scheduled_at,
            "notes": data.notes,
            "lead": lead_id,
        },
    )
    await db.commit()
    leaddict = await _one(db, "SELECT * FROM leads WHERE id=:id", {"id": lead_id})
    await G.run_workflows_for_event(db, "meeting_booked", leaddict or {"id": lead_id}, "lead")
    return {"ok": True, "booking_id": booking["id"] if booking else None, "lead_id": lead_id}


# =====================================================================================
# 6) SEGMENTOS / LISTAS DINÂMICAS
# =====================================================================================
class SegmentIn(BaseModel):
    name: str
    entity: str = "lead"
    filters: list[dict] = []
    is_active: bool = True


@router.get("/segments")
async def list_segments(db: AsyncSession = Depends(get_db)):
    return _rows(await db.execute(text("SELECT * FROM crm_segments ORDER BY created_at DESC")))


@router.post("/segments", status_code=201)
async def create_segment(data: SegmentIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    import json

    return (
        await _one(
            db,
            """
        INSERT INTO crm_segments (id, name, entity, filters, is_active, created_at, updated_at)
        VALUES (gen_random_uuid(), :name, :entity, CAST(:filters AS jsonb), :is_active, now(), now()) RETURNING *
    """,
            {**data.model_dump(exclude={"filters"}), "filters": json.dumps(data.filters)},
        )
        or {}
    )


@router.put("/segments/{sid}")
async def update_segment(
    sid: str, data: SegmentIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    import json

    row = await _one(
        db,
        """
        UPDATE crm_segments SET name=:name, entity=:entity, filters=CAST(:filters AS jsonb),
            is_active=:is_active, updated_at=now() WHERE id=:id RETURNING *
    """,
        {**data.model_dump(exclude={"filters"}), "filters": json.dumps(data.filters), "id": sid},
    )
    if not row:
        raise HTTPException(404, "Segmento não encontrado")
    return row


@router.delete("/segments/{sid}", status_code=204)
async def delete_segment(sid: str, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await db.execute(text("DELETE FROM crm_segments WHERE id=:id"), {"id": sid})
    await db.commit()


@router.get("/segments/{sid}/results")
async def segment_results(sid: str, db: AsyncSession = Depends(get_db)):
    seg = await _one(db, "SELECT entity, filters FROM crm_segments WHERE id=:id", {"id": sid})
    if not seg:
        raise HTTPException(404, "Segmento não encontrado")
    built = G.build_segment_sql(seg["entity"], list(seg["filters"] or []))
    if not built:
        raise HTTPException(400, "Entidade de segmento inválida")
    sql, params = built
    rows = _rows(await db.execute(text(sql), params))
    return {"count": len(rows), "results": rows}


class SegmentPreviewIn(BaseModel):
    entity: str = "lead"
    filters: list[dict] = []


@router.post("/segments/preview")
async def segment_preview(
    data: SegmentPreviewIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    built = G.build_segment_sql(data.entity, data.filters)
    if not built:
        raise HTTPException(400, "Entidade inválida")
    sql, params = built
    rows = _rows(await db.execute(text(sql), params))
    return {"count": len(rows), "results": rows[:100]}


# =====================================================================================
# 7) PROPRIEDADES CUSTOMIZADAS
# =====================================================================================
class CustomPropIn(BaseModel):
    entity: str
    key: str
    label: str
    field_type: str = "text"
    options: list | None = None
    is_active: bool = True


@router.get("/properties")
async def list_properties(db: AsyncSession = Depends(get_db), entity: str | None = None):
    if entity:
        return _rows(
            await db.execute(
                text("SELECT * FROM crm_custom_properties WHERE entity=:e AND is_active=true ORDER BY label"),
                {"e": entity},
            )
        )
    return _rows(
        await db.execute(text("SELECT * FROM crm_custom_properties WHERE is_active=true ORDER BY entity, label"))
    )


@router.post("/properties", status_code=201)
async def create_property(data: CustomPropIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    import json

    if data.entity not in ("lead", "opportunity"):
        raise HTTPException(400, "entity deve ser 'lead' ou 'opportunity'")
    if await _one(
        db, "SELECT id FROM crm_custom_properties WHERE entity=:e AND key=:k", {"e": data.entity, "k": data.key}
    ):
        raise HTTPException(409, "Já existe propriedade com essa chave nessa entidade")
    return (
        await _one(
            db,
            """
        INSERT INTO crm_custom_properties (id, entity, key, label, field_type, options, is_active, created_at, updated_at)
        VALUES (gen_random_uuid(), :entity, :key, :label, :field_type, CAST(:options AS jsonb), :is_active, now(), now())
        RETURNING *
    """,
            {
                **data.model_dump(exclude={"options"}),
                "options": json.dumps(data.options) if data.options is not None else None,
            },
        )
        or {}
    )


@router.delete("/properties/{pid}", status_code=204)
async def delete_property(pid: str, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await db.execute(text("UPDATE crm_custom_properties SET is_active=false WHERE id=:id"), {"id": pid})
    await db.commit()


class CustomValuesIn(BaseModel):
    values: dict


@router.put("/entities/{entity}/{entity_id}/custom")
async def set_custom_values(
    entity: str,
    entity_id: str,
    data: CustomValuesIn,
    _=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    table = {"lead": "leads", "opportunity": "opportunities"}.get(entity)
    if not table:
        raise HTTPException(400, "entity inválida")
    import json

    row = await _one(
        db,
        f"""
        UPDATE {table} SET custom_fields = COALESCE(custom_fields,'{{}}'::jsonb) || CAST(:v AS jsonb)
        WHERE id=:id RETURNING id, custom_fields
    """,
        {"v": json.dumps(data.values), "id": entity_id},
    )
    if not row:
        raise HTTPException(404, "Registro não encontrado")
    return row


# =====================================================================================
# 8) LEAD SCORING CONFIGURÁVEL
# =====================================================================================
class ScoringRuleIn(BaseModel):
    name: str
    field: str
    operator: str = "eq"
    value: str | None = None
    points: int = 0
    is_active: bool = True


@router.get("/scoring/rules")
async def list_scoring_rules(db: AsyncSession = Depends(get_db)):
    return _rows(await db.execute(text("SELECT * FROM crm_scoring_rules ORDER BY created_at DESC")))


@router.post("/scoring/rules", status_code=201)
async def create_scoring_rule(
    data: ScoringRuleIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    return (
        await _one(
            db,
            """
        INSERT INTO crm_scoring_rules (id, name, field, operator, value, points, is_active, created_at, updated_at)
        VALUES (gen_random_uuid(), :name, :field, :operator, :value, :points, :is_active, now(), now()) RETURNING *
    """,
            data.model_dump(),
        )
        or {}
    )


@router.put("/scoring/rules/{rid}")
async def update_scoring_rule(
    rid: str, data: ScoringRuleIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    row = await _one(
        db,
        """
        UPDATE crm_scoring_rules SET name=:name, field=:field, operator=:operator, value=:value,
            points=:points, is_active=:is_active, updated_at=now() WHERE id=:id RETURNING *
    """,
        {**data.model_dump(), "id": rid},
    )
    if not row:
        raise HTTPException(404, "Regra não encontrada")
    return row


@router.delete("/scoring/rules/{rid}", status_code=204)
async def delete_scoring_rule(rid: str, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await db.execute(text("DELETE FROM crm_scoring_rules WHERE id=:id"), {"id": rid})
    await db.commit()


@router.post("/scoring/recompute")
async def scoring_recompute_all(_=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    n = await G.recompute_all_lead_scores(db)
    return {"updated": n}


@router.post("/scoring/recompute/{lead_id}")
async def scoring_recompute_one(lead_id: str, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    score = await G.recompute_lead_score(db, lead_id)
    if score is None:
        raise HTTPException(404, "Lead não encontrado")
    return {"lead_id": lead_id, "score": score}


# =====================================================================================
# 9) FORECAST / METAS
# =====================================================================================
STAGE_PROB = {
    "qualification": 0.1,
    "needs_analysis": 0.25,
    "proposal": 0.5,
    "negotiation": 0.75,
    "closed_won": 1.0,
    "closed_lost": 0.0,
}


class QuotaIn(BaseModel):
    seller_id: str | None = None
    seller_name: str | None = None
    period_year: int
    period_month: int
    target_value: float | None = None  # None = não mexe no valor (ex.: setar só a meta por contagem)
    target_count: int | None = None  # meta por QUANTIDADE de contratos/mês


@router.get("/quotas")
async def list_quotas(db: AsyncSession = Depends(get_db)):
    return _rows(await db.execute(text("SELECT * FROM crm_quotas ORDER BY period_year DESC, period_month DESC")))


@router.post("/quotas", status_code=201)
async def upsert_quota(data: QuotaIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    # UPSERT de verdade por (seller_id, ano, mês). A UNIQUE é NULLS NOT DISTINCT (migration
    # crm_followups_20260626), então metas da empresa (seller_id NULL) também conflitam — não
    # duplicam mais. target_value=None NÃO zera o valor; target_count=None NÃO zera a contagem,
    # permitindo setar valor e contagem independentemente sem um clobrar o outro.
    return (
        await _one(
            db,
            """
        INSERT INTO crm_quotas (id, seller_id, seller_name, period_year, period_month, target_value, target_count, created_at, updated_at)
        VALUES (gen_random_uuid(), :seller_id, :seller_name, :period_year, :period_month, COALESCE(:target_value, 0), :target_count, now(), now())
        ON CONFLICT (seller_id, period_year, period_month)
        DO UPDATE SET
            target_value = CASE WHEN :target_value IS NULL THEN crm_quotas.target_value ELSE :target_value END,
            target_count = COALESCE(:target_count, crm_quotas.target_count),
            seller_name  = COALESCE(:seller_name, crm_quotas.seller_name),
            updated_at = now()
        RETURNING *
    """,
            data.model_dump(),
        )
        or {}
    )


@router.delete("/quotas/{qid}", status_code=204)
async def delete_quota(qid: str, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await db.execute(text("DELETE FROM crm_quotas WHERE id=:id"), {"id": qid})
    await db.commit()


@router.get("/forecast")
async def forecast(db: AsyncSession = Depends(get_db)):
    """Previsão ponderada do pipeline aberto por estágio + total ponderado, e metas do mês."""
    by_stage = _rows(
        await db.execute(
            text("""
        SELECT stage, count(*) deals, COALESCE(SUM(value),0) total_value
        FROM opportunities WHERE stage NOT IN ('closed_won','closed_lost') GROUP BY stage
    """)
        )
    )
    weighted_total = 0.0
    open_total = 0.0
    for s in by_stage:
        prob = STAGE_PROB.get(s["stage"], 0.2)
        s["probability"] = prob
        s["weighted"] = round(float(s["total_value"]) * prob, 2)
        weighted_total += s["weighted"]
        open_total += float(s["total_value"])
    won = await _one(
        db,
        """
        SELECT COALESCE(SUM(value),0) v, count(*) c FROM opportunities
        WHERE stage='closed_won' AND EXTRACT(MONTH FROM updated_at)=EXTRACT(MONTH FROM now())
          AND EXTRACT(YEAR FROM updated_at)=EXTRACT(YEAR FROM now())
    """,
        {},
    )
    quotas = await _one(
        db,
        """
        SELECT COALESCE(SUM(target_value),0) t, COALESCE(MAX(target_count),0) c FROM crm_quotas
        WHERE period_year=EXTRACT(YEAR FROM now()) AND period_month=EXTRACT(MONTH FROM now())
    """,
        {},
    )
    target = float(quotas["t"]) if quotas else 0.0
    meta_contratos = int(quotas["c"]) if quotas else 0
    won_val = float(won["v"]) if won else 0.0
    contratos_fechados = won["c"] if won else 0
    return {
        "open_total": round(open_total, 2),
        "weighted_forecast": round(weighted_total, 2),
        "won_this_month": won_val,
        "won_deals": contratos_fechados,
        "month_target": target,
        "attainment_pct": round((won_val / target * 100), 1) if target else None,
        "projected_vs_target": round(won_val + weighted_total - target, 2) if target else None,
        # meta por QUANTIDADE de contratos (KPI "≥1 contrato novo/mês")
        "contratos_fechados_mes": contratos_fechados,
        "meta_contratos_mes": meta_contratos,
        "atingimento_contratos_pct": round((contratos_fechados / meta_contratos * 100), 1) if meta_contratos else None,
        "by_stage": by_stage,
    }


@router.get("/forecast/by-seller")
async def forecast_by_seller(db: AsyncSession = Depends(get_db)):
    rows = _rows(
        await db.execute(
            text("""
        SELECT owner_id seller_id, count(*) open_deals, COALESCE(SUM(value),0) open_value
        FROM opportunities WHERE stage NOT IN ('closed_won','closed_lost')
        GROUP BY owner_id
    """)
        )
    )
    return {"sellers": rows}


@router.get("/reports/comercial/pdf")
async def relatorio_comercial_pdf(
    _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db), salvar: bool = False, teste: bool = False
):
    """Gera o Relatório Comercial em PDF (MRR, clientes, pipeline, top deals). salvar=true: registra + link."""
    from fastapi import Response

    mrr = (
        await _one(db, "SELECT COALESCE(SUM(monthly_value),0) v FROM client_contracts WHERE status='active'", {})
    ) or {}
    clientes = (await _one(db, "SELECT count(*) v FROM clients WHERE ativo", {})) or {}
    won = (
        await _one(
            db,
            """SELECT COALESCE(SUM(value),0) v FROM opportunities WHERE stage='closed_won'
                             AND EXTRACT(MONTH FROM updated_at)=EXTRACT(MONTH FROM now())
                             AND EXTRACT(YEAR FROM updated_at)=EXTRACT(YEAR FROM now())""",
            {},
        )
    ) or {}
    estagios = _rows(
        await db.execute(
            text("""
        SELECT stage, count(*) deals, COALESCE(SUM(value),0) valor FROM opportunities
        WHERE stage NOT IN ('closed_won','closed_lost') GROUP BY stage ORDER BY 3 DESC""")
        )
    )
    por_estagio, aberto = [], 0.0
    for s in estagios:
        prob = STAGE_PROB.get(s["stage"], 0.2)
        por_estagio.append(
            {
                "estagio": STAGE_LABEL_PT.get(s["stage"], s["stage"]),
                "deals": s["deals"],
                "valor": float(s["valor"]),
                "ponderado": round(float(s["valor"]) * prob, 2),
            }
        )
        aberto += float(s["valor"])
    top = _rows(
        await db.execute(
            text("""
        SELECT COALESCE(company_name, title) cliente, stage, value FROM opportunities
        WHERE stage NOT IN ('closed_won','closed_lost') ORDER BY value DESC LIMIT 8""")
        )
    )
    top_deals = [
        {
            "cliente": t["cliente"],
            "estagio": STAGE_LABEL_PT.get(t["stage"], t["stage"]),
            "valor": float(t["value"] or 0),
        }
        for t in top
    ]
    ctx = {
        "mrr": float(mrr.get("v", 0)),
        "clientes": clientes.get("v", 0),
        "pipeline_aberto": aberto,
        "ganho_mes": float(won.get("v", 0)),
        "por_estagio": por_estagio,
        "top_deals": top_deals,
    }
    from modules.crm.services.report_pdf import build_commercial_report_pdf

    pdf = build_commercial_report_pdf(ctx)
    if salvar:
        return await _salvar_pdf(db, "relatorio", "Relatório Comercial", pdf, teste=teste)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="relatorio_comercial.pdf"'},
    )


STAGE_LABEL_PT = {
    "qualification": "Qualificação",
    "needs_analysis": "Análise",
    "proposal": "Proposta",
    "negotiation": "Negociação",
    "closed_won": "Ganho",
    "closed_lost": "Perdido",
}


# ===================================================================== DOCS (recibo / OS)
class ReciboIn(BaseModel):
    pagador: str
    valor: float
    referente: str
    documento: str | None = None
    forma_pagamento: str | None = None
    numero: str | None = None


class OrdemServicoIn(BaseModel):
    cliente: str
    servico: str
    descricao: str | None = None
    documento: str | None = None
    endereco: str | None = None
    responsavel: str | None = None
    valor: float | None = None
    prazo: str | None = None
    observacoes: str | None = None
    numero: str | None = None


@router.post("/docs/recibo/pdf")
async def gerar_recibo_pdf(
    data: ReciboIn,
    _=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    salvar: bool = False,
    teste: bool = False,
):
    """Gera um RECIBO de pagamento em PDF no padrão Conecta Mais (com selo).
    salvar=true: registra no Conecta PRO e devolve link público de download."""
    from fastapi import Response

    from modules.crm.services.doc_pdf import build_recibo_pdf

    pdf = build_recibo_pdf(data.model_dump())
    if salvar:
        return await _salvar_pdf(db, "recibo", f"Recibo {data.numero or ''} - {data.pagador}", pdf, teste=teste)
    return Response(
        content=pdf, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="recibo.pdf"'}
    )


@router.post("/docs/ordem-servico/pdf")
async def gerar_os_pdf(
    data: OrdemServicoIn,
    _=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    salvar: bool = False,
    teste: bool = False,
):
    """Gera uma ORDEM DE SERVIÇO em PDF (com selo). salvar=true: registra + link de download."""
    from fastapi import Response

    from modules.crm.services.doc_pdf import build_ordem_servico_pdf

    pdf = build_ordem_servico_pdf(data.model_dump())
    if salvar:
        return await _salvar_pdf(db, "ordem_servico", f"OS {data.numero or ''} - {data.cliente}", pdf, teste=teste)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="ordem_servico.pdf"'},
    )


class AditivoIn(BaseModel):
    contrato_numero: str
    cliente: str | None = None
    documento: str | None = None
    tipo: str = "outro"
    objeto: str | None = None
    novo_valor: float | None = None
    nova_vigencia_fim: str | None = None
    justificativa: str | None = None
    numero: str | None = None


class AtestadoIn(BaseModel):
    emitente: str
    emitente_documento: str | None = None
    emitente_responsavel: str | None = None
    emitente_cargo: str | None = None
    servico: str
    periodo: str | None = None
    valor: float | None = None
    cidade: str | None = None
    observacoes: str | None = None
    numero: str | None = None


@router.post("/docs/aditivo/pdf")
async def gerar_aditivo_pdf(
    data: AditivoIn,
    _=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    salvar: bool = False,
    teste: bool = False,
):
    """Gera um TERMO ADITIVO de contrato em PDF (com selo). Enriquece pelo contrato. salvar=true: registra + link."""
    from fastapi import Response

    payload = data.model_dump()
    if not payload.get("cliente") and payload.get("contrato_numero"):
        row = await _one(
            db,
            """SELECT cl.name client_name, cl.document_number doc FROM contracts c
                                LEFT JOIN clients cl ON cl.id=c.client_id WHERE c.contract_number=:k""",
            {"k": payload["contrato_numero"]},
        )
        if row:
            payload["cliente"] = row.get("client_name")
            payload["documento"] = payload.get("documento") or row.get("doc")
    from modules.crm.services.doc_pdf import build_aditivo_pdf

    pdf = build_aditivo_pdf(payload)
    if salvar:
        return await _salvar_pdf(
            db,
            "aditivo",
            f"Aditivo {data.numero or ''} - {data.contrato_numero}",
            pdf,
            ref_tipo="contract",
            ref_id=data.contrato_numero,
            teste=teste,
        )
    return Response(
        content=pdf, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="aditivo.pdf"'}
    )


@router.post("/docs/atestado/pdf")
async def gerar_atestado_pdf(
    data: AtestadoIn,
    _=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    salvar: bool = False,
    teste: bool = False,
):
    """Gera um ATESTADO DE CAPACIDADE TÉCNICA em PDF (com selo). salvar=true: registra + link."""
    from fastapi import Response

    from modules.crm.services.doc_pdf import build_atestado_pdf

    pdf = build_atestado_pdf(data.model_dump())
    if salvar:
        return await _salvar_pdf(db, "atestado", f"Atestado {data.numero or ''} - {data.emitente}", pdf, teste=teste)
    return Response(
        content=pdf, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="atestado.pdf"'}
    )


# =====================================================================================
# 10) FOLLOW-UP / WHATSAPP (José Luís) — PROMPT 7
# =====================================================================================
from modules.crm.services import followups as F  # noqa: E402
from modules.crm.services.phone import canonical_br, to_e164_br  # noqa: E402


class WhatsAppCadastroIn(BaseModel):
    cnpj_ou_id: str
    numero: str


@router.post("/whatsapp/cadastrar", status_code=201)
async def cadastrar_whatsapp(
    data: WhatsAppCadastroIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    """Grava/normaliza (E.164) o WhatsApp de um cliente (por CNPJ ou id) ou lead (id)."""
    e164 = to_e164_br(data.numero)
    if not e164:
        raise HTTPException(422, f"Número inválido: '{data.numero}'. Use DDD+número (ex.: 92 99123-4567).")
    alvo = data.cnpj_ou_id.strip()
    is_uuid = "-" in alvo and len(alvo) >= 32
    # tenta cliente
    if is_uuid:
        row = await _one(db, "SELECT id, name FROM clients WHERE id=:id", {"id": alvo})
    else:
        doc = "".join(c for c in alvo if c.isdigit())
        row = await _one(
            db,
            "SELECT id, name FROM clients WHERE regexp_replace(coalesce(document_number,''),'\\D','','g')=:d LIMIT 1",
            {"d": doc},
        )
    if row:
        await db.execute(
            text("UPDATE clients SET whatsapp=:w, updated_at=now() WHERE id=:id"), {"w": e164, "id": row["id"]}
        )
        await db.commit()
        return {"ok": True, "tipo": "cliente", "id": str(row["id"]), "nome": row["name"], "whatsapp": e164}
    # senão, tenta lead por id
    if is_uuid:
        lead = await _one(db, "SELECT id, name FROM leads WHERE id=:id", {"id": alvo})
        if lead:
            await db.execute(
                text("UPDATE leads SET phone=:w, updated_at=now() WHERE id=:id"),
                {"w": canonical_br(e164), "id": lead["id"]},
            )
            await db.commit()
            return {"ok": True, "tipo": "lead", "id": str(lead["id"]), "nome": lead["name"], "whatsapp": e164}
    raise HTTPException(404, f"Cliente/lead não encontrado: '{alvo}'")


class FollowupIn(BaseModel):
    deal_id: str | None = None
    cliente: str | None = None  # id ou CNPJ
    lead_id: str | None = None
    proposal_id: str | None = None
    mensagem: str
    canal: str = "whatsapp"
    template: str | None = None
    confirmar: bool = False


@router.post("/followups", status_code=201)
async def criar_followup(data: FollowupIn, user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Toque manual do José Luís. confirmar=false: preview (resolve número, sem enviar).
    confirmar=true: envia de verdade e registra em crm_followups (respeita opt-out/horário/anti-spam)."""
    target = await F.resolve_target(
        db, deal_id=data.deal_id, cliente=data.cliente, lead_id=data.lead_id, proposal_id=data.proposal_id
    )
    if not data.confirmar:
        return {
            "preview": True,
            "alvo": {"nome": target.get("nome"), "telefone": target.get("phone_e164"), "fonte": target.get("fonte")},
            "mensagem": data.mensagem,
            "canal": data.canal,
            "aviso": "Reenvie com confirmar=true para o José Luís disparar.",
            "sem_telefone": not target.get("phone_e164"),
        }
    return await F.send_followup(
        db,
        target=target,
        mensagem=data.mensagem,
        canal=data.canal,
        template=data.template,
        deal_id=data.deal_id,
        proposal_id=data.proposal_id,
        criado_por=getattr(user, "email", None),
    )


@router.get("/followups/pendentes")
async def followups_pendentes(db: AsyncSession = Depends(get_db)):
    """Toques agendados/a fazer (deal, cliente, canal, data)."""
    return {"pendentes": await F.list_pending(db)}


@router.get("/followups/historico")
async def followups_historico(deal_id: str, db: AsyncSession = Depends(get_db)):
    """Histórico de toques + respostas de um deal."""
    return {"deal_id": deal_id, "historico": await F.history(db, deal_id)}


class RespostaIn(BaseModel):
    deal_id: str | None = None
    followup_id: str | None = None
    status: str = "respondido"
    classificacao: str | None = None  # interessado | duvida | recusou
    nota: str | None = None


@router.post("/followups/resposta", status_code=201)
async def followup_resposta(data: RespostaIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Registra manualmente o retorno do cliente (quando não veio pelo inbound automático)."""
    r = await F.register_response(
        db,
        deal_id=data.deal_id,
        followup_id=data.followup_id,
        status=data.status,
        classificacao=data.classificacao,
        nota=data.nota,
    )
    if not r:
        raise HTTPException(404, "Nenhum follow-up enviado encontrado para esse deal.")
    return r


class OptoutIn(BaseModel):
    numero: str
    motivo: str | None = None


@router.post("/followups/optout", status_code=201)
async def followup_optout(data: OptoutIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Marca um número como opt-out (não receber follow-ups)."""
    c = canonical_br(data.numero)
    if not c:
        raise HTTPException(422, "Número inválido.")
    await F.add_optout(db, c, data.motivo)
    return {"ok": True, "phone": c, "opt_out": True}


# =====================================================================================
# 11) ORQUESTRAÇÃO José Luís ↔ Jordan (painel de negociações)
# =====================================================================================
from modules.crm.services import orchestration as O  # noqa: E402


@router.get("/negociacoes")
async def listar_negociacoes(db: AsyncSession = Depends(get_db)):
    """Painel das negociações em aberto: cliente, proposta, quem conduz, última resposta."""
    return {"negociacoes": await O.painel_negociacoes(db)}


@router.get("/negociacoes/pendentes")
async def negociacoes_pendentes(db: AsyncSession = Depends(get_db)):
    """Propostas enviadas SEM resposta do cliente (com dias parados)."""
    return {"pendentes": await O.pendentes_sem_resposta(db)}


@router.get("/negociacoes/status")
async def negociacao_status(cliente: str, db: AsyncSession = Depends(get_db)):
    """Status de uma negociação por cliente/CNPJ/nº de proposta."""
    return await O.status_cliente(db, cliente)


class ResponsavelIn(BaseModel):
    cliente: str
    responsavel: str  # 'jordan' (assumir/pausa) | 'jose_luis' (devolver/reativa)


@router.post("/negociacoes/responsavel", status_code=201)
async def definir_responsavel(
    data: ResponsavelIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    """Define quem conduz a negociação. 'jordan' pausa o acompanhamento do José Luís; 'jose_luis' reativa."""
    if data.responsavel not in ("jordan", "jose_luis", "fechado"):
        raise HTTPException(422, "responsavel deve ser 'jordan', 'jose_luis' ou 'fechado'")
    r = await O.set_responsavel(db, data.cliente, data.responsavel)
    if not r.get("ok"):
        raise HTTPException(404, r.get("motivo", "negociação não encontrada"))
    return r


@router.get("/resumo-executivo")
async def resumo_executivo_endpoint(db: AsyncSession = Depends(get_db)):
    """Retrato da casa: pipeline + propostas + leads + contratos/MRR + pendências, num lugar só."""
    return await O.resumo_executivo(db)


@router.get("/pipeline-resumo")
async def pipeline_resumo_endpoint(db: AsyncSession = Depends(get_db)):
    """Funil: deals por estágio, valor aberto, previsão ponderada, ganho do mês e meta."""
    return await O.resumo_pipeline(db)


# =====================================================================================
# 12) FASE 1 — Analytics comercial / Financeiro / What-if / Lote
# =====================================================================================
@router.get("/relatorio-comercial")
async def relatorio_comercial_endpoint(db: AsyncSession = Depends(get_db)):
    """Raio-x de vendas: win/loss, conversão do funil, motivos de perda, ROI por canal, ranking MRR, ciclo médio."""
    return await O.relatorio_comercial(db)


@router.get("/financeiro")
async def financeiro_endpoint(db: AsyncSession = Depends(get_db)):
    """Retrato financeiro: MRR, recebíveis, inadimplência, caixa do mês, faturamento NFS-e."""
    return await O.resumo_financeiro(db)


class SimularIn2(BaseModel):
    deals: list[str] | None = None
    estagio: str | None = "negotiation"


@router.post("/simular-fechamento")
async def simular_fechamento_endpoint(
    data: SimularIn2, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    """What-if: se fechar estes deals (ou todos de um estágio), como fica ganho/meta."""
    return await O.simular_fechamento(db, deals=data.deals, estagio=data.estagio)


class LoteIn(BaseModel):
    mensagem: str | None = None
    confirmar: bool = False


@router.post("/followups/lote", status_code=201)
async def followup_lote_endpoint(data: LoteIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Toque em lote em todos os clientes com proposta pendente. confirmar=false = preview."""
    return await O.followup_em_lote(db, mensagem=data.mensagem, confirmar=data.confirmar)


# =====================================================================================
# 13) FASE 2 — Assistente de Visita Técnica & Comercial + Reuniões
# =====================================================================================
from modules.crm.services import visit_reports as V  # noqa: E402


class VisitaIn(BaseModel):
    cliente_nome: str
    panorama: str | None = None
    data_visita: str | None = None


@router.post("/visitas", status_code=201)
async def criar_visita(data: VisitaIn, user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Inicia um relatório de visita técnica/comercial (rascunho)."""
    return await V.criar_relatorio(
        db,
        cliente_nome=data.cliente_nome,
        panorama=data.panorama,
        data_visita=data.data_visita,
        criado_por=getattr(user, "email", None),
    )


class AchadosIn(BaseModel):
    ref: str
    achados: list  # [{tipo, descricao}] ou ["nota livre"]


@router.post("/visitas/achados", status_code=201)
async def visita_achados(data: AchadosIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Anexa achados (análises de foto/áudio/vídeo ou notas) ao relatório."""
    return await V.adicionar_achados(db, data.ref, data.achados)


class MontarIn(BaseModel):
    ref: str
    situacao_atual: str | None = None
    diagnostico_tecnico: str | None = None
    oportunidade_comercial: str | None = None
    proximos_passos: str | None = None
    conteudo_md: str | None = None


@router.post("/visitas/montar", status_code=201)
async def visita_montar(data: MontarIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Grava o relatório sintetizado (o LLM redige; aqui persiste)."""
    return await V.montar_relatorio(
        db,
        data.ref,
        situacao_atual=data.situacao_atual,
        diagnostico_tecnico=data.diagnostico_tecnico,
        oportunidade_comercial=data.oportunidade_comercial,
        proximos_passos=data.proximos_passos,
        conteudo_md=data.conteudo_md,
    )


@router.get("/visitas")
async def listar_visitas(db: AsyncSession = Depends(get_db)):
    """Lista os relatórios de visita."""
    return {"visitas": await V.listar_relatorios(db)}


@router.get("/visitas/detalhe")
async def visita_detalhe(ref: str, db: AsyncSession = Depends(get_db)):
    """Detalhe de um relatório de visita (por id ou nome do cliente)."""
    r = await V.get_relatorio(db, ref)
    if not r:
        raise HTTPException(404, "relatório não encontrado")
    return r


class VisitaPdfIn(BaseModel):
    ref: str
    salvar: bool = True
    teste: bool = False


@router.post("/visitas/pdf", status_code=201)
async def visita_pdf(data: VisitaPdfIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Gera o PDF do relatório de visita (com selo) e registra (download_url)."""
    from fastapi import Response

    from modules.crm.services.doc_pdf import build_visit_report_pdf

    pd = await V.pdf_data(db, data.ref)
    if not pd:
        raise HTTPException(404, "relatório não encontrado")
    pdf = build_visit_report_pdf(pd)
    if data.salvar:
        await V.finalizar(db, data.ref)
        return await _salvar_pdf(
            db, "relatorio_visita", f"Relatório de Visita - {pd.get('cliente_nome')}", pdf, teste=data.teste
        )
    return Response(
        content=pdf, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="visita.pdf"'}
    )


class RegLeadVisitaIn(BaseModel):
    ref: str
    telefone: str | None = None
    cnpj: str | None = None
    valor_estimado: float | None = None


@router.post("/visitas/registrar-lead", status_code=201)
async def visita_registrar_lead(
    data: RegLeadVisitaIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    """Cria/atualiza lead + oportunidade a partir da visita."""
    return await V.registrar_lead_da_visita(
        db, data.ref, telefone=data.telefone, cnpj=data.cnpj, valor_estimado=data.valor_estimado
    )


# ── Reuniões ──
class ReuniaoIn(BaseModel):
    titulo: str
    quando_iso: str
    cliente_nome: str | None = None
    local: str | None = None
    tipo: str = "reuniao"
    lead_id: str | None = None
    deal_id: str | None = None
    visit_report_id: str | None = None
    notes: str | None = None


@router.post("/reunioes", status_code=201)
async def criar_reuniao(data: ReuniaoIn, user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Sugere uma reunião (status 'sugerido' — Jordan confirma)."""
    from datetime import datetime, timedelta, timezone

    try:
        quando = datetime.fromisoformat(data.quando_iso.replace("Z", ""))
        if quando.tzinfo is None:
            quando = quando.replace(tzinfo=timezone(timedelta(hours=-4)))
    except Exception:
        raise HTTPException(422, "quando_iso inválido (use YYYY-MM-DDTHH:MM)")
    return await V.sugerir_reuniao(
        db,
        titulo=data.titulo,
        quando=quando,
        cliente_nome=data.cliente_nome,
        local=data.local,
        tipo=data.tipo,
        lead_id=data.lead_id,
        deal_id=data.deal_id,
        visit_report_id=data.visit_report_id,
        criado_por=getattr(user, "email", None),
        notes=data.notes,
    )


class MeetingActionIn(BaseModel):
    meeting_id: str


@router.post("/reunioes/confirmar", status_code=201)
async def confirmar_reuniao_ep(
    data: MeetingActionIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    return await V.confirmar_reuniao(db, data.meeting_id)


@router.post("/reunioes/cancelar", status_code=201)
async def cancelar_reuniao_ep(
    data: MeetingActionIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    return await V.cancelar_reuniao(db, data.meeting_id)


@router.get("/reunioes")
async def listar_reunioes_ep(db: AsyncSession = Depends(get_db), futuras: bool = True):
    """Lista as reuniões (futuras por padrão)."""
    return {"reunioes": await V.listar_reunioes(db, futuras=futuras)}


# =====================================================================================
# 14) FASE 3 — Cross-sell / Radar de frios / Reativação
# =====================================================================================
@router.get("/cross-sell")
async def cross_sell_endpoint(cliente: str, db: AsyncSession = Depends(get_db)):
    """Sugere serviço complementar que falta a um cliente (a partir dos contratos reais)."""
    return await O.sugerir_cross_sell(db, cliente)


@router.get("/leads-frios")
async def leads_frios_endpoint(db: AsyncSession = Depends(get_db), dias: int = 14):
    """Leads que esfriaram (sem interação há >= N dias, ainda abertos)."""
    return {"frios": await O.leads_frios(db, dias=dias)}


class ReativarIn(BaseModel):
    ref: str
    mensagem: str | None = None
    confirmar: bool = True


@router.post("/reativar-lead", status_code=201)
async def reativar_lead_endpoint(
    data: ReativarIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    """Reengaja um lead frio por WhatsApp (envio real). confirmar=false = preview."""
    return await O.reativar_lead(db, data.ref, mensagem=data.mensagem, confirmar=data.confirmar)


# =====================================================================================
# 15) FASE 4 — NPS pós-venda
# =====================================================================================
class NpsIn(BaseModel):
    ref: str
    confirmar: bool = False


@router.post("/nps/enviar", status_code=201)
async def nps_enviar(data: NpsIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Envia pesquisa NPS (0-10) a um cliente por WhatsApp. confirmar=false = preview."""
    return await O.enviar_nps(db, data.ref, confirmar=data.confirmar)


@router.get("/nps")
async def nps_resumo(db: AsyncSession = Depends(get_db)):
    """Resumo do NPS: respostas, média, promotores/neutros/detratores e o NPS."""
    return await O.resumo_nps(db)


# =====================================================================================
# 16) FECHAMENTO DO CICLO — heartbeat / métricas / ficha viva
# =====================================================================================
@router.get("/ciclo/diagnostico")
async def ciclo_diagnostico(db: AsyncSession = Depends(get_db)):
    """Saúde do ciclo Cowork↔Conecta PRO↔WhatsApp (WhatsApp online, agente, webhook, cadência)."""
    return await O.diagnostico_ciclo(db)


@router.get("/ciclo/metricas")
async def ciclo_metricas(db: AsyncSession = Depends(get_db)):
    """Funil/desempenho do José Luís: leads captados, follow-ups, taxa de resposta, visitas, NPS."""
    return await O.metricas_jose_luis(db)


@router.get("/funil")
async def funil(db: AsyncSession = Depends(get_db)):
    """Funil UNIFICADO (primeiro contato → fechamento): leads de conversa + deals, por etapa,
    com o gargalo e quem está parado há mais tempo (calculado dos dados existentes, sem migration)."""
    return await O.funil_comercial(db)


class NotaIn(BaseModel):
    ref: str
    nota: str


@router.post("/clientes/anotar", status_code=201)
async def anotar_cliente_ep(data: NotaIn, user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Adiciona uma anotação à ficha viva do cliente (compartilhada com o José Luís)."""
    return await O.anotar_cliente(db, data.ref, data.nota, autor=getattr(user, "email", None))


@router.get("/clientes/ficha")
async def ficha_cliente_ep(ref: str, db: AsyncSession = Depends(get_db)):
    """Ficha viva do cliente: dados + anotações + último status de negociação."""
    return await O.ficha_cliente(db, ref)
