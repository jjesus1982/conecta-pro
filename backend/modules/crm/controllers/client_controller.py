"""
CRM Clients Controller — Clientes ativos da base Conecta PRO.

A tabela `clients` é a fonte oficial. Este controller expõe os clientes
convertidos com dados financeiros (MRR, contratos) para o módulo CRM.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
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
    busca: str = Query(None, description="Trecho do nome ou do CNPJ/CPF (parcial, sem acento de caixa)"),
    db: AsyncSession = Depends(get_async_session),
):
    """Lista todos os clientes ativos com dados financeiros.

    `busca` ENTROU em 30/09/2026 porque antes ela era aceita e IGNORADA: as tools passam
    filtros por `**_`, então `listar_clientes(busca="Toscana")` devolvia a base inteira e
    parecia ter funcionado. Filtro que não filtra é pior que filtro que recusa — quem lê o
    resultado conclui que o cliente não existe ou que existem 31 «Toscana».
    """
    where = "WHERE c.ativo = true"
    params: dict = {}
    if busca:
        # ⚠️ O ramo do documento só entra quando há DÍGITO. Sem esta guarda, uma busca por
        # texto puro («Toscana») virava `document LIKE '%%'`, que casa com TODAS as linhas —
        # o OR anulava o filtro do nome e a listagem voltava inteira, parecendo que o filtro
        # não existia. Medido em 30/09/2026: 26 de 26 clientes para uma busca com 1 resultado.
        digitos = "".join(ch for ch in busca if ch.isdigit())
        cond = ["unaccent(lower(c.name)) LIKE unaccent(lower(:busca))"]
        params["busca"] = f"%{busca.strip()}%"
        if digitos:
            cond.append("regexp_replace(coalesce(c.document_number,''),'[^0-9]','','g') LIKE :busca_doc")
            params["busca_doc"] = f"%{digitos}%"
        where += " AND (" + " OR ".join(cond) + ")"
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
                (SELECT SUM(cc.monthly_value) FROM contracts cc
                 WHERE cc.client_id = c.id AND cc.status = 'active'), 0
            ) as mrr,
            (SELECT COUNT(*) FROM contracts cc
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
