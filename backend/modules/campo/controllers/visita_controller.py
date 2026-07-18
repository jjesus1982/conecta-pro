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
    VisitaDashboardStats,
    VisitaFiltro,
    VisitaFollowupRequest,
    VisitaFotoRequest,
    VisitaInteresseRequest,
    VisitaLevantamentoRequest,
    VisitaListItem,
    VisitaNecessidadeRequest,
    VisitaPaginatedResponse,
    VisitaPropostaRequest,
    VisitaRead,
    VisitaReagendarRequest,
    VisitaResultadoRequest,
    VisitaUpdate,
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


@router.get("/pendentes-confirmacao", response_model=list[VisitaListItem])
async def listar_pendentes_confirmacao(
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Lista visitas que precisam confirmacao."""
    visitas = await service.listar_pendentes_confirmacao()
    return [VisitaListItem.model_validate(v) for v in visitas]


@router.get("/responsavel/{responsavel_id}", response_model=list[VisitaListItem])
async def listar_visitas_responsavel(
    responsavel_id: UUID,
    current_user: CurrentActiveUser,
    data: date | None = None,
    apenas_agendadas: bool = False,
    service: VisitaService = Depends(get_service),
):
    """Lista visitas de um responsavel."""
    visitas = await service.listar_visitas_responsavel(responsavel_id, data, apenas_agendadas)
    return [VisitaListItem.model_validate(v) for v in visitas]


@router.get("/cliente/{cliente_id}", response_model=list[VisitaListItem])
async def listar_visitas_cliente(
    cliente_id: UUID,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Lista visitas de um cliente."""
    visitas = await service.listar_visitas_cliente(cliente_id)
    return [VisitaListItem.model_validate(v) for v in visitas]


@router.get("/lead/{lead_id}", response_model=list[VisitaListItem])
async def listar_visitas_lead(
    lead_id: UUID,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Lista visitas de um lead."""
    visitas = await service.listar_visitas_lead(lead_id)
    return [VisitaListItem.model_validate(v) for v in visitas]


@router.get("/dashboard", response_model=VisitaDashboardStats)
async def obter_dashboard(
    current_user: CurrentActiveUser,
    responsavel_id: UUID | None = None,
    periodo_dias: int = Query(30, ge=1, le=365),
    service: VisitaService = Depends(get_service),
):
    """Obtem estatisticas para dashboard."""
    return await service.obter_estatisticas(responsavel_id, periodo_dias)


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


@router.get("/numero/{numero}", response_model=VisitaRead)
async def obter_visita_por_numero(
    numero: str,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Obtem Visita por numero."""
    visita = await service.obter_visita_por_numero(numero)
    if not visita:
        raise HTTPException(status_code=404, detail="Visita nao encontrada")
    return VisitaRead.model_validate(visita)


@router.patch("/{visita_id}", response_model=VisitaRead)
async def atualizar_visita(
    visita_id: UUID,
    data: VisitaUpdate,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Atualiza uma Visita."""
    visita = await service.atualizar_visita(visita_id, data)
    if not visita:
        raise HTTPException(status_code=404, detail="Visita nao encontrada")
    return VisitaRead.model_validate(visita)


@router.delete("/{visita_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_visita(
    visita_id: UUID,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Exclui uma Visita."""
    success = await service.excluir_visita(visita_id)
    if not success:
        raise HTTPException(status_code=404, detail="Visita nao encontrada")


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


@router.post("/{visita_id}/iniciar-deslocamento", response_model=VisitaRead)
async def iniciar_deslocamento(
    visita_id: UUID,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Marca inicio do deslocamento."""
    try:
        visita = await service.iniciar_deslocamento(visita_id)
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


@router.post("/{visita_id}/interesse", response_model=VisitaRead)
async def registrar_interesse(
    visita_id: UUID,
    data: VisitaInteresseRequest,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Registra nivel de interesse."""
    try:
        servicos = [s.model_dump() for s in data.servicos] if data.servicos else None
        visita = await service.registrar_interesse(visita_id, data.nivel, servicos)
        if not visita:
            raise HTTPException(status_code=404, detail="Visita nao encontrada")
        return VisitaRead.model_validate(visita)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{visita_id}/proposta", response_model=VisitaRead)
async def vincular_proposta(
    visita_id: UUID,
    data: VisitaPropostaRequest,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Vincula proposta gerada a visita."""
    visita = await service.vincular_proposta(visita_id, data.proposta_id, data.valor)
    if not visita:
        raise HTTPException(status_code=404, detail="Visita nao encontrada")
    return VisitaRead.model_validate(visita)


# =============================================================================
# LEVANTAMENTO TECNICO
# =============================================================================


@router.post("/{visita_id}/levantamento", response_model=VisitaRead, status_code=201)
async def adicionar_levantamento(
    visita_id: UUID,
    data: VisitaLevantamentoRequest,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Adiciona dados de levantamento tecnico."""
    visita = await service.adicionar_levantamento(visita_id, data.dados.model_dump())
    if not visita:
        raise HTTPException(status_code=404, detail="Visita nao encontrada")
    return VisitaRead.model_validate(visita)


@router.post("/{visita_id}/necessidade", response_model=VisitaRead, status_code=201)
async def adicionar_necessidade(
    visita_id: UUID,
    data: VisitaNecessidadeRequest,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Adiciona necessidade identificada."""
    visita = await service.adicionar_necessidade(
        visita_id,
        data.categoria,
        data.descricao,
        data.prioridade,
        data.estimativa_valor,
    )
    if not visita:
        raise HTTPException(status_code=404, detail="Visita nao encontrada")
    return VisitaRead.model_validate(visita)


# =============================================================================
# FOLLOW-UP E FOTOS
# =============================================================================


@router.post("/{visita_id}/followup", response_model=VisitaRead)
async def agendar_followup(
    visita_id: UUID,
    data: VisitaFollowupRequest,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Agenda follow-up."""
    visita = await service.agendar_followup(visita_id, data.data, data.tipo, data.observacoes)
    if not visita:
        raise HTTPException(status_code=404, detail="Visita nao encontrada")
    return VisitaRead.model_validate(visita)


@router.post("/{visita_id}/foto", response_model=VisitaRead, status_code=201)
async def adicionar_foto(
    visita_id: UUID,
    data: VisitaFotoRequest,
    current_user: CurrentActiveUser,
    service: VisitaService = Depends(get_service),
):
    """Adiciona foto a visita."""
    visita = await service.adicionar_foto(visita_id, data.url, data.descricao, data.tipo)
    if not visita:
        raise HTTPException(status_code=404, detail="Visita nao encontrada")
    return VisitaRead.model_validate(visita)


@router.get("/{visita_id}/pdf", summary="Relatório da visita em PDF (marca Conecta)")
async def visita_relatorio_pdf(
    visita_id: UUID,
    download: bool = Query(False),
    service: VisitaService = Depends(get_service),
):
    """Gera o relatório da visita técnica/comercial em PDF (gerador build_visit_report_pdf)."""
    from fastapi.responses import Response as _R

    from modules.crm.services.doc_pdf import build_visit_report_pdf

    v = await service.obter_visita(visita_id)
    if not v:
        raise HTTPException(status_code=404, detail="visita não encontrada")

    def g(k, d=""):
        val = getattr(v, k, None)
        if isinstance(val, list):
            val = ", ".join(str(x) for x in val)
        elif isinstance(val, dict):
            val = "; ".join(f"{kk}: {vv}" for kk, vv in val.items())
        return val if val not in (None, "") else d

    dv = getattr(v, "data_visita", None)
    d = {
        "numero": g("numero"),
        "tipo": g("tipo"),
        "cliente_nome": g("prospect_empresa") or g("prospect_nome") or g("responsavel_nome") or "—",
        "data_visita": dv.strftime("%d/%m/%Y") if hasattr(dv, "strftime") else str(dv or ""),
        "responsavel": g("responsavel_nome"),
        "descricao": g("descricao_atendimento"),
        "situacao_atual": g("objetivo"),
        "diagnostico_tecnico": g("levantamento"),
        "achados": g("necessidades_identificadas"),
        "oportunidade_comercial": g("interesse_nivel"),
        "proximos_passos": g("proximos_passos"),
        "panorama": g("resultado"),
        "corpo": g("descricao_atendimento"),
    }
    pdf = build_visit_report_pdf(d)
    disp = "attachment" if download else "inline"
    return _R(content=pdf, media_type="application/pdf",
              headers={"Content-Disposition": f'{disp}; filename="visita_{g("numero") or visita_id}.pdf"'})
