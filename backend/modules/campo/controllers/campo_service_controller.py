"""
Controller CAMPO Service - Conecta PRO v3.0.0
===============================================

Gerencia suporte técnico em campo, tickets de atendimento,
e coordenação de técnicos para instalações e suporte.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.campo.models.campo_tecnico import CampoTecnico

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


@router.post("/tickets", response_model=TicketResponse, status_code=201)
async def create_ticket(current_user: CurrentActiveUser, request: TicketRequest):
    """
    Cria novo ticket de atendimento.

    Persistencia de tickets de campo ainda nao implementada (sem tabela no banco).
    Retorna 501 em vez de devolver um ticket que nao seria salvo.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Persistencia de tickets de campo nao implementada.",
    )


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket(current_user: CurrentActiveUser, ticket_id: str):
    """
    Consulta ticket específico.

    Nao ha tabela de tickets de campo; nenhum ticket pode ser recuperado.
    Retorna 404 em vez de fabricar um "Cliente Exemplo".
    """
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Ticket nao encontrado: {ticket_id} (persistencia de tickets de campo nao implementada).",
    )


@router.put("/tickets/{ticket_id}")
async def update_ticket(
    ticket_id: str,
    update: TicketUpdate,  # pylint: disable=unused-argument
    current_user: CurrentActiveUser,
):
    """
    Atualiza ticket.

    Persistencia de tickets de campo ainda nao implementada (sem tabela no banco).
    Retorna 501 em vez de simular uma atualizacao que nao ocorre.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Persistencia de tickets de campo nao implementada.",
    )


@router.post("/technicians", response_model=TechnicianInfo, status_code=201)
async def create_technician(
    technician: TechnicianInfo, current_user: CurrentActiveUser, session: AsyncSession = Depends(get_db)
):
    """
    Cadastra novo técnico.

    Args:
        technician: Dados do técnico
        session: Sessão do banco de dados

    Returns:
        Dados do técnico cadastrado
    """
    try:
        logger.info(f"Cadastrando técnico {technician.name}")

        # Criar novo técnico no banco
        new_tecnico = CampoTecnico(
            nome=technician.name,
            documento=technician.document,
            telefone=technician.phone,
            email=technician.email,
            especialidade=technician.specialty,
            status=technician.status,
            localizacao_atual=technician.current_location,
        )

        session.add(new_tecnico)
        await session.commit()
        await session.refresh(new_tecnico)

        logger.info(f"Técnico {technician.name} cadastrado com ID {new_tecnico.id}")

        return TechnicianInfo(
            id=new_tecnico.id,
            name=new_tecnico.nome,
            document=new_tecnico.documento,
            phone=new_tecnico.telefone or "",
            email=new_tecnico.email or "",
            specialty=new_tecnico.especialidade or "",
            status=new_tecnico.status,
            current_location=new_tecnico.localizacao_atual,
        )

    except IntegrityError as e:
        await session.rollback()
        logger.error(f"Erro de integridade ao cadastrar técnico: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Técnico já existe com este documento: {technician.document}",
        )
    except Exception as e:
        await session.rollback()
        logger.error(f"Erro ao cadastrar técnico: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao cadastrar técnico: {str(e)}"
        )


@router.get("/technicians")
async def list_technicians(
    current_user: CurrentActiveUser,
    tech_status: str | None = None,
    specialty: str | None = None,
    session: AsyncSession = Depends(get_db),
):
    """
    Lista técnicos cadastrados.

    Args:
        tech_status: Filtro por status
        specialty: Filtro por especialidade
        session: Sessão do banco de dados

    Returns:
        Lista de técnicos
    """
    from sqlalchemy import text

    # A tabela campo_tecnicos não existe; os "técnicos/agentes de campo" são os funcionários ativos.
    try:
        where = "status='ativo'"
        params: dict = {}
        if specialty:
            where += " AND cargo ILIKE :sp"
            params["sp"] = f"%{specialty}%"
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT id::text AS id, nome, cpf, telefone, celular, email, cargo, status "
                        f"FROM employees WHERE {where} ORDER BY nome LIMIT 300"
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )
        technicians_list = [
            {
                "id": r["id"],
                "name": r["nome"],
                "document": r["cpf"],
                "phone": r["celular"] or r["telefone"],
                "email": r["email"],
                "specialty": r["cargo"],
                "status": r["status"],
                "current_location": None,
                "created_at": None,
            }
            for r in rows
        ]
        return {
            "technicians": technicians_list,
            "total": len(technicians_list),
            "filters": {"status": tech_status, "specialty": specialty},
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"Erro ao listar técnicos: {e}")
        return {"technicians": [], "total": 0, "filters": {"status": tech_status, "specialty": specialty}}


@router.post("/tickets/{ticket_id}/assign/{technician_id}")
async def assign_technician(ticket_id: str, current_user: CurrentActiveUser, technician_id: str):
    """
    Atribui técnico ao ticket.

    Persistencia de tickets de campo ainda nao implementada (sem tabela no banco).
    Retorna 501 em vez de simular uma atribuicao que nao e salva.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Persistencia de tickets de campo nao implementada.",
    )


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
    vazio = {
        "agentes": 0,
        "agentes_em_campo": 0,
        "checkins": 0,
        "checkins_hoje": 0,
        "checkins_list": [],
        "ocorrencias": 0,
        "alertas": [],
        "registros": 0,
    }
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
        logger.error(f"Erro ao gerar dashboard CAMPO: {e}")
        return vazio
