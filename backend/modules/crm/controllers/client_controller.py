"""
CRM Clients Controller — Clientes ativos da base Conecta PRO.

A tabela `clients` é a fonte oficial. Este controller expõe os clientes
convertidos com dados financeiros (MRR, contratos) para o módulo CRM.
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clients", tags=["CRM - Clientes"])


@router.get("")
@router.get("/")
async def listar_clientes(
    current_user: CurrentActiveUser,
    status: str = Query(None, description="Filtrar por status (active, inactive)"),
    segment: str = Query(None, description="Filtrar por segmento"),
    db: AsyncSession = Depends(get_async_session),
):
    """Lista todos os clientes ativos com dados financeiros."""
    where = "WHERE c.ativo = true"
    params: dict = {}
    if status:
        where += " AND c.status = :status"
        params["status"] = status
    if segment:
        where += " AND c.segment = :segment"
        params["segment"] = segment

    result = await db.execute(
        text(f"""
        SELECT
            c.id, c.code, c.name, c.trading_name,
            c.document_number, c.email, c.phone, c.mobile,
            c.address_street, c.address_number, c.address_neighborhood,
            c.address_city, c.address_state, c.address_zipcode,
            c.status, c.segment, c.contract_start_date,
            c.health_score, c.satisfaction_score,
            c.total_revenue, c.total_debt,
            c.is_defaulter, c.is_vip,
            c.crm_origin, c.lead_id,
            c.created_at,
            COALESCE(
                (SELECT SUM(cc.monthly_value) FROM client_contracts cc
                 WHERE cc.client_id = c.id AND cc.status = 'active'), 0
            ) as mrr,
            (SELECT COUNT(*) FROM client_contracts cc
             WHERE cc.client_id = c.id AND cc.status = 'active') as contratos_ativos,
            l.name as lead_name, l.source as lead_source
        FROM clients c
        LEFT JOIN leads l ON c.lead_id = l.id
        {where}
        ORDER BY c.name
    """),
        params,
    )
    rows = result.fetchall()

    return {
        "items": [
            {
                "id": str(r[0]),
                "code": r[1],
                "name": r[2],
                "trading_name": r[3],
                "cnpj": r[4],
                "email": r[5],
                "phone": r[6],
                "mobile": r[7],
                "endereco": {
                    "rua": r[8],
                    "numero": r[9],
                    "bairro": r[10],
                    "cidade": r[11],
                    "estado": r[12],
                    "cep": r[13],
                },
                "endereco_texto": ", ".join(p for p in [r[8], r[9], r[10], r[11], r[12]] if p) or None,
                "status": r[14],
                "segment": r[15],
                "contract_start_date": str(r[16]) if r[16] else None,
                "health_score": r[17],
                "satisfaction_score": r[18],
                "total_revenue": float(r[19]) if r[19] else 0,
                "total_debt": float(r[20]) if r[20] else 0,
                "is_defaulter": r[21],
                "is_vip": r[22],
                "crm_origin": r[23],
                "lead_id": str(r[24]) if r[24] else None,
                "created_at": r[25].isoformat() if r[25] else None,
                "mrr": float(r[26]),
                "contratos_ativos": r[27],
                "lead_name": r[28],
                "lead_source": r[29],
            }
            for r in rows
        ],
        "total": len(rows),
        "gerado_em": datetime.now().isoformat(),
    }


@router.get("/resumo")
async def resumo_clientes(current_user: CurrentActiveUser, db: AsyncSession = Depends(get_async_session)):
    """Resumo da base de clientes."""
    result = await db.execute(
        text("""
        SELECT
            COUNT(*) FILTER (WHERE c.ativo) as ativos,
            COUNT(*) FILTER (WHERE NOT c.ativo) as inativos,
            COUNT(*) FILTER (WHERE c.is_defaulter) as inadimplentes,
            COUNT(*) FILTER (WHERE c.is_vip) as vip,
            COUNT(c.lead_id) as originados_crm,
            COALESCE(SUM(
                (SELECT SUM(cc.monthly_value) FROM client_contracts cc
                 WHERE cc.client_id = c.id AND cc.status = 'active')
            ), 0) as mrr_total,
            COUNT(DISTINCT c.segment) as segmentos
        FROM clients c
    """)
    )
    row = result.fetchone()

    return {
        "clientes_ativos": row[0],
        "clientes_inativos": row[1],
        "inadimplentes": row[2],
        "vip": row[3],
        "originados_crm": row[4],
        "mrr_total": float(row[5]),
        "segmentos": row[6],
        "gerado_em": datetime.now().isoformat(),
    }


@router.get("/{client_id}")
async def detalhe_cliente(
    client_id: UUID,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_async_session),
):
    """Detalhe completo de um cliente com contratos e lead origem."""
    result = await db.execute(
        text("""
        SELECT
            c.*, l.name as lead_name, l.source as lead_source, l.score as lead_score
        FROM clients c
        LEFT JOIN leads l ON c.lead_id = l.id
        WHERE c.id = :cid
    """),
        {"cid": str(client_id)},
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Buscar contratos
    contratos = await db.execute(
        text("""
        SELECT id, service_type, monthly_value, start_date, end_date, status
        FROM client_contracts WHERE client_id = :cid ORDER BY start_date DESC
    """),
        {"cid": str(client_id)},
    )

    return {
        "id": str(row.id),
        "name": row.name,
        "cnpj": row.document_number,
        "email": row.email,
        "phone": row.phone,
        "status": row.status,
        "segment": row.segment,
        "health_score": row.health_score,
        "crm_origin": row.crm_origin,
        "lead_name": row.lead_name if hasattr(row, "lead_name") else None,
        "contratos": [
            {
                "id": str(ct.id),
                "service_type": ct.service_type,
                "monthly_value": float(ct.monthly_value) if ct.monthly_value else 0,
                "start_date": str(ct.start_date) if ct.start_date else None,
                "status": ct.status,
            }
            for ct in contratos.fetchall()
        ],
    }
