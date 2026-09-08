"""
Controller CAMPO Service - Conecta PRO v3.0.0
===============================================

Gerencia suporte técnico em campo, tickets de atendimento,
e coordenação de técnicos para instalações e suporte.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

# Configurar logging
logger = logging.getLogger(__name__)

# Router para CAMPO Service
router = APIRouter(prefix="/campo", tags=["Campo Service"])


class TechnicianInfo(BaseModel):
    """Informações do técnico."""

    id: str | None = None
    name: str
    document: str
    phone: str
    email: str
    specialty: str
    status: str = "active"
    current_location: dict | None = None


class TicketRequest(BaseModel):
    """Request para criar ticket."""

    client_name: str
    client_address: str
    client_phone: str
    service_type: str
    priority: str = "normal"
    description: str
    scheduled_time: datetime | None = None


class TicketResponse(BaseModel):
    """Response de ticket."""

    ticket_id: str
    client_name: str
    service_type: str
    priority: str
    status: str
    created_at: datetime
    technician_assigned: str | None = None


class TicketUpdate(BaseModel):
    """Atualização de ticket."""

    status: str | None = None
    technician_id: str | None = None
    resolution: str | None = None
    observations: str | None = None


# NOTA DE VERACIDADE: nao existe tabela de tickets de campo no banco (apenas
# client_portal_tickets/client_tickets, que sao do Portal do Cliente, dominio distinto).
# Enquanto a persistencia de tickets de campo nao for implementada, estes endpoints
# NAO devem fabricar dados de exemplo. get_ticket -> 404; create/update/assign -> 501.


@router.get("/dashboard")
async def campo_dashboard(current_user: CurrentActiveUser, session: AsyncSession = Depends(get_db)):
    """
    Dashboard do CAMPO com estatísticas.

    Args:
        session: Sessão do banco de dados

    Returns:
        Estatísticas do CAMPO
    """
    from zoneinfo import ZoneInfo

    from sqlalchemy import text

    # "Hoje" em Manaus (UTC-4); as batidas (check-ins de agentes em campo) ficam em gp_clock_punches
    # (objeto date, não string: asyncpg exige date no comparativo ::date = :hoje)
    hoje = datetime.now(ZoneInfo("America/Manaus")).date()
    try:
        agentes = (await session.execute(text("SELECT count(*) FROM employees WHERE status='ativo'"))).scalar() or 0
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT max(p.employee_id::text) AS eid, e.nome AS colaborador, p.posto_nome, "
                        "min(p.punch_timestamp) FILTER (WHERE p.punch_type='entrada') AS checkin_at, "
                        "max(p.punch_timestamp) FILTER (WHERE p.punch_type='saida') AS checkout_at "
                        "FROM gp_clock_punches p JOIN employees e ON p.employee_id = e.id "
                        "WHERE p.punch_timestamp::date = :hoje "
                        "GROUP BY e.nome, p.posto_nome ORDER BY 4 DESC NULLS LAST"
                    ),
                    {"hoje": hoje},
                )
            )
            .mappings()
            .all()
        )
        checkins_list = [
            {
                "id": r["eid"],
                "colaborador": r["colaborador"],
                "nome": r["colaborador"],
                "posto": r["posto_nome"],
                "local": r["posto_nome"],
                "status": "em_campo" if (r["checkin_at"] and not r["checkout_at"]) else "finalizado",
                "checkin_at": r["checkin_at"].strftime("%H:%M") if r["checkin_at"] else None,
                "checkout_at": r["checkout_at"].strftime("%H:%M") if r["checkout_at"] else None,
                "data_checkin": r["checkin_at"].isoformat() if r["checkin_at"] else None,
                "data_checkout": r["checkout_at"].isoformat() if r["checkout_at"] else None,
            }
            for r in rows
        ]
        em_campo = sum(1 for c in checkins_list if c["status"] == "em_campo")
        try:
            ocorr = (
                await session.execute(
                    text("SELECT count(*) FROM occurrences WHERE created_at::date = :hoje"), {"hoje": hoje}
                )
            ).scalar() or 0
        except Exception:  # noqa: BLE001
            ocorr = 0
        return {
            "agentes": int(agentes),
            "agentes_em_campo": int(em_campo),
            "checkins": len(checkins_list),
            "checkins_hoje": len(checkins_list),
            "checkins_list": checkins_list,
            "ocorrencias": int(ocorr),
            "alertas": [],
            "registros": len(checkins_list),
            "technicians": {"total": int(agentes), "active": int(em_campo)},  # compat
        }
    except Exception as e:  # noqa: BLE001
        # Zeros devolvidos por falha se leem como "noite tranquila" — pior que erro,
        # porque o gerente confia. Falhou, diz que falhou.
        logger.error(f"Erro ao gerar dashboard CAMPO: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Não foi possível montar o painel de campo.") from e
