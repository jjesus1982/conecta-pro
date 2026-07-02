"""
Controller para API de Predicao de Turnover.

Implementa todos os endpoints REST para o modulo de predicao
de turnover com IA, incluindo calculo de risco, alertas,
dashboard e historico.

Seguranca:
- Score NUNCA visivel para o funcionario
- Todos os acessos sao registrados para auditoria
- Requer autenticacao e permissoes adequadas
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import (
    CurrentActiveUser,
    require_roles,
)
from core.database import get_db
from modules.retention.turnover.models.turnover_models import (
    CategoriaFator,
    NivelRisco,
    TipoAlerta,
)
from modules.retention.turnover.repositories.turnover_repository import (
    TurnoverRepository,
)
from modules.retention.turnover.schemas.turnover_schemas import (
    AlertAcaoRequest,
    AlertFilter,
    AlertListResponse,
    AlertResponse,
    AlertSummary,
    AlertVisualizarRequest,
    DashboardResponse,
    FatoresListResponse,
    FeatureConfig,
    FeaturesConfigResponse,
    HistoricoResponse,
    PredictionFilter,
    PredictionListResponse,
    PredictionResponse,
    PredictionSummary,
    RecalcularBatchRequest,
    RecalcularBatchResponse,
    RecalcularRequest,
    RecalcularResponse,
    RiskFactorResponse,
    RiskFactorSummary,
)
from modules.retention.turnover.services.risk_analyzer import RiskAnalyzer
from modules.retention.turnover.services.turnover_predictor import (
    FEATURES_CONFIG,
    TurnoverPredictor,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/retention/turnover",
    tags=["Retention - Turnover Prediction"],
)


# =============================================================================
# Helper Functions
# =============================================================================


def get_client_info(request: Request) -> tuple[str | None, str | None]:
    """Extrai IP e User-Agent do request."""
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    return ip, user_agent


async def verificar_permissao_visualizacao(
    user: CurrentActiveUser,
    condominium_id: UUID,
) -> None:
    """Verifica se usuario pode visualizar dados de turnover."""
    # Admin pode ver tudo
    if user.role == "admin":
        return

    # Verificar se pertence ao condominio
    user_condominium = getattr(user, "condominium_id", None)
    if user_condominium and str(user_condominium) != str(condominium_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem permissao para acessar dados deste condominio",
        )


# =============================================================================
# Prediction Endpoints
# =============================================================================


@router.get(
    "/predictions",
    response_model=PredictionListResponse,
    summary="Listar predicoes de turnover",
    description="Lista todas as predicoes de risco de turnover com filtros",
)
async def listar_predictions(
    request: Request,
    current_user: CurrentActiveUser,
    condominium_id: UUID = Query(..., description="ID do condominio"),
    nivel: NivelRisco | None = Query(None, description="Filtrar por nivel"),
    score_minimo: float | None = Query(None, ge=0, le=100),
    score_maximo: float | None = Query(None, ge=0, le=100),
    apenas_alerta: bool = Query(False, description="Apenas scores >= 70"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    order_by: str = Query("score_risco", description="Campo para ordenacao"),
    order_desc: bool = Query(True, description="Ordem decrescente"),
    db: AsyncSession = Depends(get_db),
) -> PredictionListResponse:
    """Lista predicoes de turnover com filtros e paginacao."""
    await verificar_permissao_visualizacao(current_user, condominium_id)

    repository = TurnoverRepository(db)
    analyzer = RiskAnalyzer(db)

    filters = PredictionFilter(
        condominium_id=condominium_id,
        nivel=nivel,
        score_minimo=score_minimo,
        score_maximo=score_maximo,
        apenas_alerta=apenas_alerta,
    )

    predictions, total = await repository.list_predictions(
        filters=filters,
        skip=skip,
        limit=limit,
        order_by=order_by,
        order_desc=order_desc,
    )

    # Registrar auditoria
    ip, ua = get_client_info(request)
    await analyzer.registrar_acesso_auditoria(
        usuario_id=current_user.id,
        condominium_id=condominium_id,
        acao="consulta_lista",
        recurso="predictions",
        ip_address=ip,
        user_agent=ua,
    )

    items = [
        PredictionSummary(
            id=p.id,
            funcionario_id=p.funcionario_id,
            data_calculo=p.data_calculo,
            score_risco=p.score_risco,
            nivel=p.nivel,
            is_alerta_necessario=p.is_alerta_necessario,
            principais_fatores=[
                RiskFactorSummary(
                    nome=f.nome,
                    categoria=f.categoria,
                    contribuicao_score=f.contribuicao_score,
                    threshold_violado=f.threshold_violado,
                    descricao=f.descricao,
                )
                for f in p.principais_fatores
            ],
        )
        for p in predictions
    ]

    return PredictionListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        nivel_filtro=nivel,
    )


@router.get(
    "/funcionario/{funcionario_id}/risk",
    response_model=PredictionResponse,
    summary="Obter risco atual do funcionario",
    description="Retorna a predicao de risco mais recente do funcionario",
)
async def get_risk_funcionario(
    request: Request,
    funcionario_id: UUID,
    current_user: CurrentActiveUser,
    condominium_id: UUID = Query(..., description="ID do condominio"),
    db: AsyncSession = Depends(get_db),
) -> PredictionResponse:
    """Retorna predicao de risco atual do funcionario."""
    await verificar_permissao_visualizacao(current_user, condominium_id)

    repository = TurnoverRepository(db)
    analyzer = RiskAnalyzer(db)

    prediction = await repository.get_latest_prediction(funcionario_id)

    if not prediction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Predicao nao encontrada para este funcionario",
        )

    # Registrar auditoria
    ip, ua = get_client_info(request)
    await analyzer.registrar_acesso_auditoria(
        usuario_id=current_user.id,
        condominium_id=condominium_id,
        acao="consulta_score",
        recurso="prediction",
        recurso_id=prediction.id,
        funcionario_id=funcionario_id,
        ip_address=ip,
        user_agent=ua,
    )

    fatores_response = [
        RiskFactorResponse(
            id=f.id,
            nome=f.nome,
            categoria=f.categoria,
            peso=f.peso,
            valor_atual=f.valor_atual,
            valor_normalizado=f.valor_normalizado,
            contribuicao_score=f.contribuicao_score,
            threshold_violado=f.threshold_violado,
            recomendacao_acao=f.recomendacao_acao,
            descricao=f.descricao,
            is_critico=f.is_critico,
            is_significativo=f.is_significativo,
            created_at=f.created_at,
        )
        for f in prediction.fatores
    ]

    return PredictionResponse(
        id=prediction.id,
        funcionario_id=prediction.funcionario_id,
        condominium_id=prediction.condominium_id,
        data_calculo=prediction.data_calculo,
        score_risco=prediction.score_risco,
        nivel=prediction.nivel,
        modelo_versao=prediction.modelo_versao,
        features_usadas=prediction.features_usadas,
        metricas_modelo=prediction.metricas_modelo,
        valido_ate=prediction.valido_ate,
        recalculado=prediction.recalculado,
        is_alerta_necessario=prediction.is_alerta_necessario,
        is_critico=prediction.is_critico,
        fatores=fatores_response,
        created_at=prediction.created_at,
        updated_at=prediction.updated_at,
    )


@router.post(
    "/funcionario/{funcionario_id}/recalcular",
    response_model=RecalcularResponse,
    summary="Recalcular risco do funcionario",
    description="Forca recalculo do risco de turnover",
)
async def recalcular_funcionario(
    request: Request,
    funcionario_id: UUID,
    current_user: CurrentActiveUser,
    condominium_id: UUID = Query(..., description="ID do condominio"),
    dados: RecalcularRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> RecalcularResponse:
    """Recalcula risco de turnover para funcionario especifico."""
    await verificar_permissao_visualizacao(current_user, condominium_id)

    predictor = TurnoverPredictor(db)
    analyzer = RiskAnalyzer(db)

    # [Veracidade] Features REAIS do funcionário (sem demonstração fabricada): tempo de
    # empresa via employees.data_admissao; o que o sistema ainda não rastreia (faltas mensais,
    # clima individual, distância, extras) fica 0/neutro — honesto, aguardando dado.
    from datetime import date as _date

    from sqlalchemy import text as _text

    _adm = (
        await db.execute(
            _text("SELECT data_admissao FROM employees WHERE CAST(id AS TEXT) = :e"),
            {"e": str(funcionario_id)},
        )
    ).scalar()
    dados_funcionario = {
        "funcionario_id": str(funcionario_id),
        "faltas_ultimo_mes": 0,
        "atrasos_ultimo_mes": 0,
        "ocorrencias_trimestre": 0,
        "advertencias_total": 0,
        "score_clima_atual": 3.0,
        "tendencia_clima": 0.0,
        "distancia_casa_posto_km": 0,
        "horas_extras_media": 0,
        "tempo_empresa_meses": int((_date.today() - _adm).days // 30) if _adm else 0,
        "dias_sem_aumento": 0,
    }

    try:
        result = await predictor.recalcular_funcionario(
            funcionario_id=funcionario_id,
            condominium_id=condominium_id,
            dados_funcionario=dados_funcionario,
            calculado_por=current_user.id,
        )

        # Registrar auditoria
        ip, ua = get_client_info(request)
        await analyzer.registrar_acesso_auditoria(
            usuario_id=current_user.id,
            condominium_id=condominium_id,
            acao="recalcular",
            recurso="prediction",
            recurso_id=result.predicao_id,
            funcionario_id=funcionario_id,
            detalhes={"motivo": dados.motivo if dados else None},
            ip_address=ip,
            user_agent=ua,
        )

        return result

    except Exception as e:
        logger.error(f"Erro ao recalcular risco: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao recalcular risco",
        )


@router.post(
    "/recalcular-todos",
    response_model=RecalcularBatchResponse,
    summary="Recalcular risco de todos os funcionarios",
    description="Recalcula risco em lote (apenas admin)",
    dependencies=[Depends(require_roles("admin"))],
)
async def recalcular_todos(
    request: Request,
    current_user: CurrentActiveUser,
    condominium_id: UUID = Query(..., description="ID do condominio"),
    dados: RecalcularBatchRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> RecalcularBatchResponse:
    """Recalcula risco de turnover para todos os funcionarios."""
    predictor = TurnoverPredictor(db)
    analyzer = RiskAnalyzer(db)

    # [Veracidade] Recalcula sobre funcionários REAIS (ids informados ou todos os ativos),
    # com tempo de empresa real; features ainda não rastreadas ficam 0/neutro (sem fabricar).
    from datetime import date as _date

    from sqlalchemy import text as _text

    _ids = (
        list(dados.funcionario_ids)
        if dados and dados.funcionario_ids
        else [str(r[0]) for r in (await db.execute(_text("SELECT id FROM employees WHERE status='ativo'"))).fetchall()]
    )
    funcionarios_dados = []
    for _fid in _ids:
        _adm = (
            await db.execute(_text("SELECT data_admissao FROM employees WHERE CAST(id AS TEXT) = :e"), {"e": str(_fid)})
        ).scalar()
        funcionarios_dados.append(
            {
                "funcionario_id": str(_fid),
                "faltas_ultimo_mes": 0,
                "atrasos_ultimo_mes": 0,
                "ocorrencias_trimestre": 0,
                "advertencias_total": 0,
                "score_clima_atual": 3.0,
                "tendencia_clima": 0.0,
                "distancia_casa_posto_km": 0,
                "horas_extras_media": 0,
                "tempo_empresa_meses": int((_date.today() - _adm).days // 30) if _adm else 0,
                "dias_sem_aumento": 0,
            }
        )

    try:
        result = await predictor.calcular_risco_batch(
            funcionarios_dados=funcionarios_dados,
            condominium_id=condominium_id,
            calculado_por=current_user.id,
        )

        # Registrar auditoria
        ip, ua = get_client_info(request)
        await analyzer.registrar_acesso_auditoria(
            usuario_id=current_user.id,
            condominium_id=condominium_id,
            acao="recalcular_batch",
            recurso="predictions",
            detalhes={
                "total_processados": result.total_processados,
                "sucesso": result.total_sucesso,
                "erros": result.total_erros,
            },
            ip_address=ip,
            user_agent=ua,
        )

        return result

    except Exception as e:
        logger.error(f"Erro ao recalcular batch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao recalcular riscos em lote",
        )


# =============================================================================
# Alert Endpoints
# =============================================================================


@router.get(
    "/alerts",
    response_model=AlertListResponse,
    summary="Listar alertas de risco",
    description="Lista todos os alertas de risco de turnover",
)
async def listar_alerts(
    request: Request,
    current_user: CurrentActiveUser,
    condominium_id: UUID = Query(..., description="ID do condominio"),
    tipo: TipoAlerta | None = Query(None, description="Filtrar por tipo"),
    visualizado: bool | None = Query(None, description="Filtrar por status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> AlertListResponse:
    """Lista alertas de risco de turnover."""
    await verificar_permissao_visualizacao(current_user, condominium_id)

    repository = TurnoverRepository(db)
    analyzer = RiskAnalyzer(db)

    filters = AlertFilter(
        condominium_id=condominium_id,
        tipo=tipo,
        visualizado=visualizado,
    )

    alerts, total = await repository.list_alerts(
        filters=filters,
        skip=skip,
        limit=limit,
    )

    # Registrar auditoria
    ip, ua = get_client_info(request)
    await analyzer.registrar_acesso_auditoria(
        usuario_id=current_user.id,
        condominium_id=condominium_id,
        acao="consulta_alertas",
        recurso="alerts",
        ip_address=ip,
        user_agent=ua,
    )

    items = [
        AlertSummary(
            id=a.id,
            funcionario_id=a.funcionario_id,
            tipo=a.tipo,
            titulo=a.titulo,
            score_atual=a.score_atual,
            nivel_atual=a.nivel_atual,
            visualizado=a.visualizado,
            prioridade=a.prioridade,
            created_at=a.created_at,
        )
        for a in alerts
    ]

    return AlertListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        apenas_pendentes=visualizado is False,
    )


@router.get(
    "/alerts/pendentes",
    response_model=AlertListResponse,
    summary="Listar alertas pendentes",
    description="Lista alertas que ainda nao foram visualizados",
)
async def listar_alerts_pendentes(
    request: Request,
    current_user: CurrentActiveUser,
    condominium_id: UUID = Query(..., description="ID do condominio"),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> AlertListResponse:
    """Lista alertas pendentes de visualizacao."""
    await verificar_permissao_visualizacao(current_user, condominium_id)

    analyzer = RiskAnalyzer(db)

    alerts = await analyzer.get_alertas_pendentes(condominium_id, limit)

    # Registrar auditoria
    ip, ua = get_client_info(request)
    await analyzer.registrar_acesso_auditoria(
        usuario_id=current_user.id,
        condominium_id=condominium_id,
        acao="consulta_alertas_pendentes",
        recurso="alerts",
        ip_address=ip,
        user_agent=ua,
    )

    items = [
        AlertSummary(
            id=a.id,
            funcionario_id=a.funcionario_id,
            tipo=a.tipo,
            titulo=a.titulo,
            score_atual=a.score_atual,
            nivel_atual=a.nivel_atual,
            visualizado=a.visualizado,
            prioridade=a.prioridade,
            created_at=a.created_at,
        )
        for a in alerts
    ]

    return AlertListResponse(
        items=items,
        total=len(alerts),
        skip=0,
        limit=limit,
        apenas_pendentes=True,
    )


@router.post(
    "/alerts/{alert_id}/visualizar",
    response_model=AlertResponse,
    summary="Marcar alerta como visualizado",
)
async def visualizar_alert(
    request: Request,
    alert_id: UUID,
    dados: AlertVisualizarRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """Marca um alerta como visualizado."""
    analyzer = RiskAnalyzer(db)

    alert = await analyzer.marcar_alerta_visualizado(
        alert_id=alert_id,
        usuario_id=dados.usuario_id,
    )

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alerta nao encontrado",
        )

    # Registrar auditoria
    ip, ua = get_client_info(request)
    await analyzer.registrar_acesso_auditoria(
        usuario_id=current_user.id,
        condominium_id=alert.condominium_id,
        acao="visualizar_alerta",
        recurso="alert",
        recurso_id=alert_id,
        funcionario_id=alert.funcionario_id,
        ip_address=ip,
        user_agent=ua,
    )

    return AlertResponse(
        id=alert.id,
        funcionario_id=alert.funcionario_id,
        prediction_id=alert.prediction_id,
        condominium_id=alert.condominium_id,
        tipo=alert.tipo,
        titulo=alert.titulo,
        mensagem=alert.mensagem,
        score_atual=alert.score_atual,
        score_anterior=alert.score_anterior,
        variacao_score=alert.variacao_score,
        nivel_atual=alert.nivel_atual,
        nivel_anterior=alert.nivel_anterior,
        enviado_para=alert.enviado_para,
        visualizado=alert.visualizado,
        data_visualizacao=alert.data_visualizacao,
        visualizado_por=alert.visualizado_por,
        acao_tomada=alert.acao_tomada,
        acao_por=alert.acao_por,
        data_acao=alert.data_acao,
        prioridade=alert.prioridade,
        expira_em=alert.expira_em,
        is_pendente=alert.is_pendente,
        is_expirado=alert.is_expirado,
        is_acao_pendente=alert.is_acao_pendente,
        created_at=alert.created_at,
    )


@router.post(
    "/alerts/{alert_id}/acao",
    response_model=AlertResponse,
    summary="Registrar acao em alerta",
)
async def registrar_acao_alert(
    request: Request,
    alert_id: UUID,
    dados: AlertAcaoRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """Registra uma acao tomada sobre um alerta."""
    analyzer = RiskAnalyzer(db)

    alert = await analyzer.registrar_acao_alerta(
        alert_id=alert_id,
        acao=dados.acao,
        usuario_id=dados.usuario_id,
    )

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alerta nao encontrado",
        )

    # Registrar auditoria
    ip, ua = get_client_info(request)
    await analyzer.registrar_acesso_auditoria(
        usuario_id=current_user.id,
        condominium_id=alert.condominium_id,
        acao="registrar_acao_alerta",
        recurso="alert",
        recurso_id=alert_id,
        funcionario_id=alert.funcionario_id,
        detalhes={"acao": dados.acao},
        ip_address=ip,
        user_agent=ua,
    )

    return AlertResponse(
        id=alert.id,
        funcionario_id=alert.funcionario_id,
        prediction_id=alert.prediction_id,
        condominium_id=alert.condominium_id,
        tipo=alert.tipo,
        titulo=alert.titulo,
        mensagem=alert.mensagem,
        score_atual=alert.score_atual,
        score_anterior=alert.score_anterior,
        variacao_score=alert.variacao_score,
        nivel_atual=alert.nivel_atual,
        nivel_anterior=alert.nivel_anterior,
        enviado_para=alert.enviado_para,
        visualizado=alert.visualizado,
        data_visualizacao=alert.data_visualizacao,
        visualizado_por=alert.visualizado_por,
        acao_tomada=alert.acao_tomada,
        acao_por=alert.acao_por,
        data_acao=alert.data_acao,
        prioridade=alert.prioridade,
        expira_em=alert.expira_em,
        is_pendente=alert.is_pendente,
        is_expirado=alert.is_expirado,
        is_acao_pendente=alert.is_acao_pendente,
        created_at=alert.created_at,
    )


# =============================================================================
# Dashboard Endpoints
# =============================================================================


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Obter dados do dashboard",
    description="Retorna dados consolidados para o dashboard de turnover",
)
async def get_dashboard(
    request: Request,
    current_user: CurrentActiveUser,
    condominium_id: UUID = Query(..., description="ID do condominio"),
    setor_id: UUID | None = Query(None, description="Filtrar por setor"),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """Retorna dados do dashboard de turnover."""
    await verificar_permissao_visualizacao(current_user, condominium_id)

    analyzer = RiskAnalyzer(db)

    try:
        dashboard = await analyzer.get_dashboard_data(
            condominium_id=condominium_id,
            setor_id=setor_id,
        )

        # Registrar auditoria
        ip, ua = get_client_info(request)
        await analyzer.registrar_acesso_auditoria(
            usuario_id=current_user.id,
            condominium_id=condominium_id,
            acao="consulta_dashboard",
            recurso="dashboard",
            ip_address=ip,
            user_agent=ua,
        )

        return dashboard

    except Exception as e:
        logger.error(f"Erro ao obter dashboard: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao obter dados do dashboard",
        )


# =============================================================================
# Factors Endpoints
# =============================================================================


@router.get(
    "/factors",
    response_model=FatoresListResponse,
    summary="Listar fatores de risco agregados",
    description="Retorna estatisticas agregadas dos fatores de risco",
)
async def listar_fatores(
    request: Request,
    current_user: CurrentActiveUser,
    condominium_id: UUID = Query(..., description="ID do condominio"),
    categoria: CategoriaFator | None = Query(None, description="Filtrar categoria"),
    db: AsyncSession = Depends(get_db),
) -> FatoresListResponse:
    """Lista fatores de risco com estatisticas agregadas."""
    await verificar_permissao_visualizacao(current_user, condominium_id)

    analyzer = RiskAnalyzer(db)

    fatores = await analyzer.get_fatores_agregados(
        condominium_id=condominium_id,
        categoria=categoria,
    )

    # Registrar auditoria
    ip, ua = get_client_info(request)
    await analyzer.registrar_acesso_auditoria(
        usuario_id=current_user.id,
        condominium_id=condominium_id,
        acao="consulta_fatores",
        recurso="factors",
        ip_address=ip,
        user_agent=ua,
    )

    return FatoresListResponse(
        items=fatores,
        total_fatores=len(fatores),
        categoria_filtro=categoria,
    )


# =============================================================================
# History Endpoints
# =============================================================================


@router.get(
    "/historico/{funcionario_id}",
    response_model=HistoricoResponse,
    summary="Historico de predicoes do funcionario",
    description="Retorna historico completo de predicoes de turnover",
)
async def get_historico(
    request: Request,
    funcionario_id: UUID,
    current_user: CurrentActiveUser,
    condominium_id: UUID = Query(..., description="ID do condominio"),
    limite: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> HistoricoResponse:
    """Retorna historico de predicoes do funcionario."""
    await verificar_permissao_visualizacao(current_user, condominium_id)

    analyzer = RiskAnalyzer(db)

    try:
        historico = await analyzer.get_historico_funcionario(
            funcionario_id=funcionario_id,
            limite=limite,
        )

        # Registrar auditoria
        ip, ua = get_client_info(request)
        await analyzer.registrar_acesso_auditoria(
            usuario_id=current_user.id,
            condominium_id=condominium_id,
            acao="consulta_historico",
            recurso="historico",
            funcionario_id=funcionario_id,
            ip_address=ip,
            user_agent=ua,
        )

        return historico

    except Exception as e:
        logger.error(f"Erro ao obter historico: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao obter historico",
        )


# =============================================================================
# Configuration Endpoints
# =============================================================================


@router.get(
    "/config/features",
    response_model=FeaturesConfigResponse,
    summary="Configuracao das features",
    description="Retorna configuracao das features usadas no modelo",
)
async def get_features_config(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> FeaturesConfigResponse:
    """Retorna configuracao das features do modelo."""
    predictor = TurnoverPredictor(db)

    features = [
        FeatureConfig(
            nome=config.nome,
            categoria=config.categoria,
            peso=config.peso,
            descricao=config.descricao,
            threshold_alto=config.threshold_alto,
            threshold_baixo=config.threshold_baixo,
            threshold_negativo=config.threshold_negativo,
            threshold_critico=config.threshold_critico,
            ativo=True,
        )
        for config in FEATURES_CONFIG.values()
    ]

    return FeaturesConfigResponse(
        features=features,
        total_peso=predictor.get_total_peso(),
        modelo_versao=predictor.MODELO_VERSAO,
    )
