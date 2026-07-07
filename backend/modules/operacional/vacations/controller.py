"""
Controller de Férias e Afastamentos.

LEITURA: a fonte canônica é a tabela `hr_vacation_requests` (módulo DP /
People Management). A tabela local `vacation_requests` é um espelho
DEPRECATED e desatualizado — ler dela produzia solicitações fantasma
(faltavam FER-2026-001..005 SUBMITTED).

ESCRITA: desabilitada (HTTP 501). Escrever no espelho deprecated criaria
estado fantasma que o DP nunca vê.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser, get_current_active_user
from core.database import get_db

from .schemas import (
    VacationRequestCreate,
    VacationRequestListResponse,
    VacationRequestResponse,
    VacationRequestUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/vacations",
    tags=["Operacional - Férias e Afastamentos"],
    dependencies=[Depends(get_current_active_user)],
)

_READ_ONLY_DETAIL = (
    "Solicitações de férias são geridas pelo módulo DP (People Management) — "
    "este endpoint é somente leitura."
)

# Mapeamento status hr_vacation_requests (uppercase) → status PT usado no response
_STATUS_PT = {
    "SUBMITTED": "pendente",
    "PENDING": "pendente",
    "APPROVED": "aprovado",
    "REJECTED": "rejeitado",
    "DRAFT": "rascunho",
    "CANCELLED": "cancelado",
    "SCHEDULED": "programado",
    "IN_PROGRESS": "em_andamento",
    "COMPLETED": "concluido",
    "INTERRUPTED": "interrompido",
    "PAID": "pago",
}

_BASE_SELECT = """
    SELECT
        CAST(h.id AS TEXT) AS id,
        CAST(h.employee_id AS TEXT) AS employee_id,
        e.nome AS employee_name,
        h.status AS raw_status,
        h.request_code,
        h.start_date,
        h.end_date,
        h.days_requested,
        h.employee_notes,
        h.hr_notes,
        h.rejection_reason,
        CAST(h.hr_approved_by AS TEXT) AS approved_by,
        h.hr_approved_at AS approved_at,
        h.created_at,
        COALESCE(h.updated_at, h.created_at) AS updated_at
    FROM hr_vacation_requests h
    LEFT JOIN employees e ON e.id = h.employee_id
"""


def _map_status(raw: str | None) -> str:
    """Mapeia status da tabela canônica para o vocabulário PT do response."""
    if not raw:
        return "desconhecido"
    return _STATUS_PT.get(raw.upper(), raw.lower())


def _row_to_response(row) -> VacationRequestResponse:
    """Converte uma linha de hr_vacation_requests no shape do response atual."""
    days_str = None
    if row.days_requested is not None:
        days_str = f"{row.days_requested} dia{'s' if row.days_requested != 1 else ''}"
    return VacationRequestResponse(
        id=row.id,
        employee_id=row.employee_id,
        employee_name=row.employee_name,
        type="ferias",
        status=_map_status(row.raw_status),
        start_date=row.start_date,
        end_date=row.end_date,
        days=days_str,
        reason=row.employee_notes,
        notes=row.hr_notes,
        approved_by=row.approved_by,
        approved_at=row.approved_at,
        rejected_reason=row.rejection_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=VacationRequestListResponse)
async def list_vacation_requests(
    current_user: CurrentActiveUser,
    status: str | None = Query(None),
    type_filter: str | None = Query(None, alias="type"),
    employee_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> VacationRequestListResponse:
    """Lista solicitações de férias (fonte canônica: hr_vacation_requests, módulo DP)."""
    try:
        result = await db.execute(text(_BASE_SELECT + " ORDER BY h.created_at DESC"))
        rows = result.fetchall()

        items = [_row_to_response(r) for r in rows]

        if status:
            items = [i for i in items if i.status == status]
        if type_filter:
            # A fonte canônica contém apenas férias
            items = [i for i in items if i.type == type_filter]
        if employee_id:
            items = [i for i in items if i.employee_id == employee_id]

        total = len(items)
        pendente = sum(1 for i in items if i.status == "pendente")
        aprovado = sum(1 for i in items if i.status == "aprovado")
        rejeitado = sum(1 for i in items if i.status == "rejeitado")

        return VacationRequestListResponse(
            items=items,
            total=total,
            pendente=pendente,
            aprovado=aprovado,
            rejeitado=rejeitado,
        )
    except (RuntimeError, ValueError, OSError) as e:
        logger.error("Erro ao listar férias: %s", e)
        return VacationRequestListResponse(items=[], total=0, pendente=0, aprovado=0, rejeitado=0)


@router.post("", status_code=501)
async def create_vacation_request(
    data: VacationRequestCreate,
    current_user: CurrentActiveUser,
) -> None:
    """DESABILITADO: escrita é responsabilidade do módulo DP."""
    raise HTTPException(status_code=501, detail=_READ_ONLY_DETAIL)


@router.get("/{request_id}", response_model=VacationRequestResponse)
async def get_vacation_request(
    request_id: str, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)
) -> VacationRequestResponse:
    """Busca uma solicitação pelo ID (fonte canônica: hr_vacation_requests)."""
    result = await db.execute(
        text(_BASE_SELECT + " WHERE CAST(h.id AS TEXT) = :rid"),
        {"rid": request_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    return _row_to_response(row)


@router.patch("/{request_id}", status_code=501)
async def update_vacation_request(
    request_id: str,
    data: VacationRequestUpdate,
    current_user: CurrentActiveUser,
) -> None:
    """DESABILITADO: escrita é responsabilidade do módulo DP."""
    raise HTTPException(status_code=501, detail=_READ_ONLY_DETAIL)


@router.post("/{request_id}/approve", status_code=501)
async def approve_vacation_request(
    request_id: str,
    current_user: CurrentActiveUser,
) -> None:
    """DESABILITADO: aprovação é responsabilidade do módulo DP."""
    raise HTTPException(status_code=501, detail=_READ_ONLY_DETAIL)


@router.post("/{request_id}/reject", status_code=501)
async def reject_vacation_request(
    request_id: str,
    current_user: CurrentActiveUser,
    reason: str | None = None,
) -> None:
    """DESABILITADO: rejeição é responsabilidade do módulo DP."""
    raise HTTPException(status_code=501, detail=_READ_ONLY_DETAIL)


@router.delete("/{request_id}", status_code=501)
async def delete_vacation_request(
    request_id: str,
    current_user: CurrentActiveUser,
) -> None:
    """DESABILITADO: cancelamento é responsabilidade do módulo DP."""
    raise HTTPException(status_code=501, detail=_READ_ONLY_DETAIL)
