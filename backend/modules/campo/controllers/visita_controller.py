"""
Controller para Visita.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.campo.models.visita import ResultadoVisita, StatusVisita, TipoResponsavel, TipoVisita
from modules.campo.schemas.visita import (
    VisitaCancelarRequest,
    VisitaCheckinRequest,
    VisitaCheckoutRequest,
    VisitaConfirmarRequest,
    VisitaCreate,
    VisitaFiltro,
    VisitaListItem,
    VisitaPaginatedResponse,
    VisitaRead,
    VisitaReagendarRequest,
    VisitaResultadoRequest,
)
from modules.campo.services.visita_service import VisitaService

router = APIRouter()


def get_service(db: AsyncSession = Depends(get_db)) -> VisitaService:
    """Dependency para obter service."""
    return VisitaService(db)


# =============================================================================
# CRUD
# =============================================================================


@router.post("/", response_model=VisitaRead, status_code=status.HTTP_201_CREATED)
async def criar_visita(
    data: VisitaCreate,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Cria uma nova Visita."""
    visita = await service.criar_visita(data)
    return VisitaRead.model_validate(visita)


@router.get("/", response_model=VisitaPaginatedResponse)
async def listar_visitas(
    current_user: CurrentActiveUser,
    tipo: TipoVisita | None = None,
    status_visita: StatusVisita | None = Query(None, alias="status"),
    resultado: ResultadoVisita | None = None,
    responsavel_id: UUID | None = None,
    responsavel_tipo: TipoResponsavel | None = None,
    cliente_id: UUID | None = None,
    lead_id: UUID | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cidade: str | None = None,
    estado: str | None = None,
    confirmada: bool | None = None,
    proposta_gerada: bool | None = None,
    busca: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    service: VisitaService = Depends(get_service),
):
    """Lista Visitas com filtros e paginacao."""
    filtro = VisitaFiltro(
        tipo=tipo,
        status=status_visita,
        resultado=resultado,
        responsavel_id=responsavel_id,
        responsavel_tipo=responsavel_tipo,
        cliente_id=cliente_id,
        lead_id=lead_id,
        data_inicio=data_inicio,
        data_fim=data_fim,
        cidade=cidade,
        estado=estado,
        confirmada=confirmada,
        proposta_gerada=proposta_gerada,
        busca=busca,
    )
    return await service.listar_visitas(filtro, page, page_size)


@router.get("/{visita_id}", response_model=VisitaRead)
async def obter_visita(
    visita_id: UUID,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Obtem detalhes de uma Visita."""
    visita = await service.obter_visita(visita_id)
    if not visita:
        raise HTTPException(status_code=404, detail="Visita nao encontrada")
    return VisitaRead.model_validate(visita)


# =============================================================================
# ACOES DO FLUXO
# =============================================================================


@router.post("/{visita_id}/confirmar", response_model=VisitaRead)
async def confirmar_visita(
    visita_id: UUID,
    data: VisitaConfirmarRequest,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Confirma uma visita."""
    try:
        visita = await service.confirmar_visita(visita_id, data.confirmado_por)
        if not visita:
            raise HTTPException(status_code=404, detail="Visita nao encontrada")
        return VisitaRead.model_validate(visita)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{visita_id}/checkin", response_model=VisitaRead)
async def fazer_checkin(
    visita_id: UUID,
    data: VisitaCheckinRequest,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Registra check-in no local."""
    try:
        visita = await service.fazer_checkin(visita_id, data.latitude, data.longitude)
        if not visita:
            raise HTTPException(status_code=404, detail="Visita nao encontrada")
        return VisitaRead.model_validate(visita)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{visita_id}/checkout", response_model=VisitaRead)
async def fazer_checkout(
    visita_id: UUID,
    data: VisitaCheckoutRequest,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Registra check-out do local."""
    visita = await service.fazer_checkout(visita_id, data.latitude, data.longitude)
    if not visita:
        raise HTTPException(status_code=404, detail="Visita nao encontrada")
    return VisitaRead.model_validate(visita)


@router.post("/{visita_id}/resultado", response_model=VisitaRead)
async def registrar_resultado(
    visita_id: UUID,
    data: VisitaResultadoRequest,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Registra resultado da visita."""
    visita = await service.registrar_resultado(
        visita_id,
        data.resultado,
        data.descricao_atendimento,
        data.proximos_passos,
    )
    if not visita:
        raise HTTPException(status_code=404, detail="Visita nao encontrada")
    return VisitaRead.model_validate(visita)


@router.post("/{visita_id}/cancelar", response_model=VisitaRead)
async def cancelar_visita(
    visita_id: UUID,
    data: VisitaCancelarRequest,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Cancela uma visita."""
    try:
        cancelado_por = None
        visita = await service.cancelar_visita(visita_id, data.motivo, cancelado_por)
        if not visita:
            raise HTTPException(status_code=404, detail="Visita nao encontrada")
        return VisitaRead.model_validate(visita)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{visita_id}/reagendar", response_model=VisitaRead)
async def reagendar_visita(
    visita_id: UUID,
    data: VisitaReagendarRequest,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Reagenda uma visita."""
    try:
        visita = await service.reagendar_visita(
            visita_id,
            data.nova_data,
            data.novo_horario,
            data.motivo,
        )
        if not visita:
            raise HTTPException(status_code=404, detail="Visita nao encontrada")
        return VisitaRead.model_validate(visita)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# CONVERSAO COMERCIAL
# =============================================================================


# =============================================================================
# LEVANTAMENTO TECNICO
# =============================================================================


# =============================================================================
# FOLLOW-UP E FOTOS
# =============================================================================


@router.get("/{visita_id}/pdf", summary="Relatório da visita em PDF (marca Conecta)")
async def visita_relatorio_pdf(
    visita_id: UUID,
    current_user: CurrentActiveUser,
    download: bool = Query(False),
    service: VisitaService = Depends(get_service),
):
    """Gera o relatório da visita técnica/comercial em PDF (gerador build_visit_report_pdf)."""
    from fastapi.responses import Response as _R

    from modules.campo.services.visita_service import visita_to_pdf_dict
    from modules.crm.services.doc_pdf import build_visit_report_pdf

    v = await service.obter_visita(visita_id)
    if not v:
        raise HTTPException(status_code=404, detail="visita não encontrada")

    d = visita_to_pdf_dict(v)
    pdf = build_visit_report_pdf(d)
    disp = "attachment" if download else "inline"
    return _R(content=pdf, media_type="application/pdf",
              headers={"Content-Disposition": f'{disp}; filename="visita_{d.get("numero") or visita_id}.pdf"'})
