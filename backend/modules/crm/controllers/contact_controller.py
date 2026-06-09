"""
CRM Contacts + Activities + 360° Controller
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["CRM - Contatos & Atividades"])


# === SCHEMAS ===


class ContactCreate(BaseModel):
    client_id: str
    name: str
    role: str | None = None
    email: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    is_primary: bool = False
    notes: str | None = None


class ActivityCreate(BaseModel):
    client_id: str
    type: str = Field(default="note", description="call|email|whatsapp|visit|meeting|note")
    subject: str
    description: str | None = None
    outcome: str | None = None
    scheduled_at: str | None = None


# === CONTACTS ===


@router.get("/contacts/")
async def listar_contatos(
    current_user: CurrentActiveUser,
    client_id: str | None = Query(None),
    db: AsyncSession = Depends(get_async_session),
):
    """Lista contatos CRM, opcionalmente filtrados por cliente."""
    where = ""
    params: dict = {}
    if client_id:
        where = "WHERE cc.client_id = :client_id"
        params = {"client_id": client_id}

    result = await db.execute(
        text(f"""
        SELECT cc.id, cc.client_id, cc.name, cc.role, cc.email, cc.phone,
               cc.whatsapp, cc.is_primary, cc.notes, cc.created_at,
               c.name as client_name
        FROM crm_contacts cc
        JOIN clients c ON cc.client_id = c.id
        {where}
        ORDER BY cc.is_primary DESC, cc.name
    """),
        params,
    )
    rows = result.fetchall()

    return {
        "items": [
            {
                "id": str(r[0]),
                "client_id": str(r[1]),
                "name": r[2],
                "role": r[3],
                "email": r[4],
                "phone": r[5],
                "whatsapp": r[6],
                "is_primary": r[7],
                "notes": r[8],
                "created_at": r[9].isoformat() if r[9] else None,
                "client_name": r[10],
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.post("/contacts/", status_code=201)
async def criar_contato(
    data: ContactCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_async_session),
):
    """Cria novo contato vinculado a um cliente."""
    result = await db.execute(
        text("""
        INSERT INTO crm_contacts (client_id, name, role, email, phone, whatsapp, is_primary, notes)
        VALUES (:client_id, :name, :role, :email, :phone, :whatsapp, :is_primary, :notes)
        RETURNING id
    """),
        {
            "client_id": data.client_id,
            "name": data.name,
            "role": data.role,
            "email": data.email,
            "phone": data.phone,
            "whatsapp": data.whatsapp,
            "is_primary": data.is_primary,
            "notes": data.notes,
        },
    )
    await db.commit()
    row = result.fetchone()
    return {"id": str(row[0]), "message": "Contato criado"}


@router.delete("/contacts/{contact_id}")
async def deletar_contato(
    contact_id: UUID,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_async_session),
):
    """Remove contato."""
    await db.execute(text("DELETE FROM crm_contacts WHERE id = :id"), {"id": str(contact_id)})
    await db.commit()
    return {"message": "Contato removido"}


# === ACTIVITIES ===


@router.get("/activities/recent")
async def atividades_recentes(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_async_session),
):
    """Ultimas 20 atividades de todos os clientes."""
    result = await db.execute(
        text("""
        SELECT a.id, a.client_id, a.type, a.subject, a.description,
               a.outcome, a.created_at, c.name as client_name
        FROM crm_activities a
        JOIN clients c ON a.client_id = c.id
        ORDER BY a.created_at DESC
        LIMIT 20
    """)
    )
    rows = result.fetchall()

    return {
        "items": [
            {
                "id": str(r[0]),
                "client_id": str(r[1]),
                "type": r[2],
                "subject": r[3],
                "description": r[4],
                "outcome": r[5],
                "created_at": r[6].isoformat() if r[6] else None,
                "client_name": r[7],
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.get("/activities/")
async def listar_atividades(
    current_user: CurrentActiveUser,
    client_id: str | None = Query(None),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_async_session),
):
    """Lista atividades CRM."""
    where = ""
    params: dict = {"lim": limit}
    if client_id:
        where = "WHERE a.client_id = :client_id"
        params["client_id"] = client_id

    result = await db.execute(
        text(f"""
        SELECT a.id, a.client_id, a.type, a.subject, a.description,
               a.outcome, a.scheduled_at, a.completed_at, a.created_at,
               c.name as client_name
        FROM crm_activities a
        JOIN clients c ON a.client_id = c.id
        {where}
        ORDER BY a.created_at DESC
        LIMIT :lim
    """),
        params,
    )
    rows = result.fetchall()

    return {
        "items": [
            {
                "id": str(r[0]),
                "client_id": str(r[1]),
                "type": r[2],
                "subject": r[3],
                "description": r[4],
                "outcome": r[5],
                "scheduled_at": r[6].isoformat() if r[6] else None,
                "completed_at": r[7].isoformat() if r[7] else None,
                "created_at": r[8].isoformat() if r[8] else None,
                "client_name": r[9],
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.post("/activities/", status_code=201)
async def criar_atividade(
    data: ActivityCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_async_session),
):
    """Registra atividade (chamada, email, visita, nota)."""
    result = await db.execute(
        text("""
        INSERT INTO crm_activities (client_id, type, subject, description, outcome, scheduled_at)
        VALUES (:client_id, :type, :subject, :description, :outcome, :scheduled_at)
        RETURNING id
    """),
        {
            "client_id": data.client_id,
            "type": data.type,
            "subject": data.subject,
            "description": data.description,
            "outcome": data.outcome,
            "scheduled_at": data.scheduled_at,
        },
    )
    await db.commit()
    row = result.fetchone()
    return {"id": str(row[0]), "message": "Atividade registrada"}


# === 360° CLIENT VIEW ===


@router.get("/clients/{client_id}/360")
async def visao_360_cliente(
    client_id: UUID,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_async_session),
):
    """Visao 360 do cliente — contratos, NFS-e, oportunidades, atividades, contatos."""
    cid = str(client_id)

    # Cliente
    client = await db.execute(
        text("""
        SELECT c.id, c.name, c.document_number, c.email, c.phone, c.status,
               c.segment, c.health_score, c.is_defaulter, c.is_vip, c.crm_origin,
               l.name as lead_name, l.source as lead_source
        FROM clients c LEFT JOIN leads l ON c.lead_id = l.id
        WHERE c.id = :cid
    """),
        {"cid": cid},
    )
    cl = client.fetchone()
    if not cl:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")

    # Contratos
    contratos = await db.execute(
        text("""
        SELECT id, service_type, monthly_value, start_date, end_date, status
        FROM client_contracts WHERE client_id = :cid AND status = 'active'
        ORDER BY start_date DESC
    """),
        {"cid": cid},
    )

    # MRR
    mrr_result = await db.execute(
        text("""
        SELECT COALESCE(SUM(monthly_value), 0) FROM client_contracts
        WHERE client_id = :cid AND status = 'active'
    """),
        {"cid": cid},
    )
    mrr = float(mrr_result.scalar() or 0)

    # Oportunidades
    opps = await db.execute(
        text("""
        SELECT o.id, o.title, o.stage, o.value, o.probability
        FROM opportunities o JOIN leads l ON o.lead_id = l.id
        WHERE l.client_id = :cid AND o.is_active = true
        ORDER BY o.value DESC
    """),
        {"cid": cid},
    )

    # Contatos
    contacts = await db.execute(
        text("""
        SELECT id, name, role, email, phone, whatsapp, is_primary
        FROM crm_contacts WHERE client_id = :cid
        ORDER BY is_primary DESC, name
    """),
        {"cid": cid},
    )

    # Atividades recentes
    activities = await db.execute(
        text("""
        SELECT id, type, subject, description, outcome, created_at
        FROM crm_activities WHERE client_id = :cid
        ORDER BY created_at DESC LIMIT 10
    """),
        {"cid": cid},
    )

    # NFS-e
    nfse = await db.execute(
        text("""
        SELECT numero_nfse, data_competencia, valor_servicos, status
        FROM nfses WHERE tomador_cpf_cnpj = :cnpj
        ORDER BY data_competencia DESC LIMIT 10
    """),
        {"cnpj": cl[2]},
    )

    # Funcionarios alocados (via allocations -> posts -> client)
    funcionarios = await db.execute(
        text("""
        SELECT DISTINCT e.id, e.nome, e.cargo, e.matricula
        FROM employees e
        JOIN allocations a ON a.employee_id = e.id
        JOIN posts p ON a.post_id = p.id
        WHERE p.client_id = :cid
          AND a.status = 'active'
          AND e.is_active = true
        ORDER BY e.nome
    """),
        {"cid": cid},
    )

    # MRR historico (NFS-e agrupado por mes)
    mrr_hist = await db.execute(
        text("""
        SELECT DATE_TRUNC('month', data_competencia) as mes,
               SUM(valor_servicos) as total
        FROM nfses
        WHERE tomador_cpf_cnpj = :cnpj
        GROUP BY mes
        ORDER BY mes DESC
        LIMIT 12
    """),
        {"cnpj": cl[2]},
    )

    return {
        "cliente": {
            "id": str(cl[0]),
            "name": cl[1],
            "cnpj": cl[2],
            "email": cl[3],
            "phone": cl[4],
            "status": cl[5],
            "segment": cl[6],
            "health_score": cl[7],
            "is_defaulter": cl[8],
            "is_vip": cl[9],
            "crm_origin": cl[10],
            "lead_name": cl[11],
            "lead_source": cl[12],
            "mrr": mrr,
        },
        "contratos": [
            {
                "id": str(r[0]),
                "service_type": r[1],
                "monthly_value": float(r[2]) if r[2] else 0,
                "start_date": str(r[3]) if r[3] else None,
                "status": r[5],
            }
            for r in contratos.fetchall()
        ],
        "oportunidades": [
            {"id": str(r[0]), "title": r[1], "stage": r[2], "value": r[3], "probability": r[4]} for r in opps.fetchall()
        ],
        "contatos": [
            {
                "id": str(r[0]),
                "name": r[1],
                "role": r[2],
                "email": r[3],
                "phone": r[4],
                "whatsapp": r[5],
                "is_primary": r[6],
            }
            for r in contacts.fetchall()
        ],
        "atividades": [
            {
                "id": str(r[0]),
                "type": r[1],
                "subject": r[2],
                "description": r[3],
                "outcome": r[4],
                "created_at": r[5].isoformat() if r[5] else None,
            }
            for r in activities.fetchall()
        ],
        "nfse": [
            {
                "numero": r[0],
                "competencia": str(r[1]) if r[1] else None,
                "valor": float(r[2]) if r[2] else 0,
                "status": r[3],
            }
            for r in nfse.fetchall()
        ],
        "funcionarios_alocados": [
            {
                "id": str(r[0]),
                "nome": r[1],
                "cargo": r[2],
                "matricula": r[3],
            }
            for r in funcionarios.fetchall()
        ],
        "mrr_historico": [
            {
                "mes": r[0].strftime("%Y-%m") if r[0] else None,
                "total": float(r[1]) if r[1] else 0,
            }
            for r in mrr_hist.fetchall()
        ],
        "gerado_em": datetime.now().isoformat(),
    }
