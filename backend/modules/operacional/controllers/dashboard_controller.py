"""
Controller de Dashboard Unificado do Operacional.

Fornece endpoints para:
- Dashboard consolidado (funcionários + diaristas)
- Métricas de ocupação
- Alocação de diaristas a postos
- Sugestões de alocação
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.services.integration_service import (
    get_integration_service,
)

router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================


class AlocarDiaristaPostoRequest(BaseModel):
    """Request para alocar diarista a um condomínio.

    REWRITE (Ciclo 3, item 15): alinhado ao schema atual de diarist_assignments
    (condominio_id/unidade_id/data_inicio/data_fim). Campos antigos removidos
    sem equivalente no banco: post_id (→ condominio_id), shift_id, cliente_id,
    contrato_id.
    """

    diarista_id: UUID
    condominio_id: UUID
    data_inicio: date
    data_fim: date | None = None
    unidade_id: UUID | None = None
    valor_acordado: Decimal | None = Field(None, ge=0)
    observacoes: str | None = Field(None, max_length=500)


class DesalocarDiaristaRequest(BaseModel):
    """Request para desalocar diarista."""

    motivo: str | None = Field(None, max_length=500)


class DashboardResponse(BaseModel):
    """Response do dashboard unificado."""

    data_referencia: str
    postos: dict[str, Any]
    escalas: dict[str, Any]
    turnos: dict[str, Any]
    funcionarios: dict[str, Any]
    diaristas: dict[str, Any]
    ocupacao: dict[str, Any]
    alertas: list[dict[str, Any]]


class MetricasPeriodoResponse(BaseModel):
    """Response das métricas de período."""

    periodo: dict[str, Any]
    diaristas: dict[str, Any]
    funcionarios: dict[str, Any]
    consolidado: dict[str, Any]


class OcupacaoPostoResponse(BaseModel):
    """Response da ocupação de um posto."""

    posto_id: str
    posto_nome: str
    posto_tipo: str
    funcionarios_alocados: int
    diaristas_alocados: int
    total_alocados: int
    status: str
    detalhes: dict[str, Any]


class SugestaoDiaristaResponse(BaseModel):
    """Response de sugestão de diarista."""

    diarist_id: str
    nome: str
    score: int
    motivos: list[str]
    avaliacao: float | None = None
    total_servicos: int


# =============================================================================
# ENDPOINTS - DASHBOARD
# =============================================================================


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Dashboard unificado",
    description="Retorna métricas consolidadas de funcionários fixos e diaristas",
)
async def get_dashboard(
    current_user: CurrentActiveUser,
    data: date | None = Query(None, description="Data de referência (default: hoje)"),
    cliente_id: UUID | None = Query(None, description="Filtrar por cliente"),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """
    Retorna dashboard unificado do operacional.

    Inclui:
    - Status de postos
    - Escalas e turnos
    - Funcionários alocados
    - Diaristas em serviço
    - Taxa de ocupação
    - Alertas automáticos
    """
    service = get_integration_service(db)

    try:
        dashboard = await service.get_dashboard_unificado(
            data_referencia=data,
            cliente_id=cliente_id,
        )
        return dashboard
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao gerar dashboard: {str(e)}"
        )


@router.get(
    "/metricas",
    response_model=MetricasPeriodoResponse,
    summary="Métricas de período",
    description="Retorna métricas consolidadas para um período específico",
)
async def get_metricas_periodo(
    current_user: CurrentActiveUser,
    data_inicio: date = Query(..., description="Data inicial"),
    data_fim: date = Query(..., description="Data final"),
    cliente_id: UUID | None = Query(None, description="Filtrar por cliente"),
    db: AsyncSession = Depends(get_db),
) -> MetricasPeriodoResponse:
    """
    Retorna métricas de um período específico.

    Inclui:
    - Schedules de diaristas realizados/cancelados/faltas
    - Horas trabalhadas
    - Turnos de funcionários
    - Taxa de comparecimento
    """
    if data_fim < data_inicio:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Data fim deve ser maior ou igual a data início"
        )

    service = get_integration_service(db)

    try:
        metricas = await service.get_metricas_periodo(
            data_inicio=data_inicio,
            data_fim=data_fim,
            cliente_id=cliente_id,
        )
        return metricas
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao calcular métricas: {str(e)}"
        )


# =============================================================================
# ENDPOINTS - OCUPAÇÃO DE POSTOS
# =============================================================================


@router.get(
    "/ocupacao",
    response_model=list[OcupacaoPostoResponse],
    summary="Ocupação de postos",
    description="Retorna status de ocupação de cada posto ativo",
)
async def get_ocupacao_postos(
    current_user: CurrentActiveUser,
    data: date | None = Query(None, description="Data de referência (default: hoje)"),
    db: AsyncSession = Depends(get_db),
) -> list[OcupacaoPostoResponse]:
    """
    Retorna ocupação detalhada de cada posto.

    Mostra para cada posto:
    - Funcionários fixos alocados
    - Diaristas alocados
    - Status (coberto/descoberto)
    """
    service = get_integration_service(db)

    try:
        ocupacao = await service.get_ocupacao_postos(data_referencia=data)
        return ocupacao
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao consultar ocupação: {str(e)}"
        )


# =============================================================================
# ENDPOINTS - ALOCAÇÃO DE DIARISTAS
# =============================================================================


@router.post(
    "/alocar-diarista",
    summary="Alocar diarista a condomínio",
    description="Aloca um diarista a um condomínio (diarist_assignments)",
    status_code=201,
)
async def alocar_diarista_posto(
    request: AlocarDiaristaPostoRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Aloca um diarista a um condomínio.

    Validações:
    - Diarista deve estar ativo e disponível
    - Condomínio deve existir
    - Não pode haver conflito de datas
    """
    service = get_integration_service(db)

    try:
        assignment = await service.alocar_diarista_posto(
            diarista_id=request.diarista_id,
            condominio_id=request.condominio_id,
            data_inicio=request.data_inicio,
            data_fim=request.data_fim,
            unidade_id=request.unidade_id,
            valor_acordado=request.valor_acordado,
            observacoes=request.observacoes,
        )

        return {
            "success": True,
            "message": "Diarista alocado com sucesso",
            "assignment_id": str(assignment.id),
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao alocar diarista: {str(e)}"
        )


@router.post(
    "/desalocar-diarista/{assignment_id}",
    summary="Desalocar diarista",
    description="Remove alocação de diarista de um posto",
    status_code=201,
)
async def desalocar_diarista(
    assignment_id: UUID,
    request: DesalocarDiaristaRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Encerra a alocação de um diarista (status ENCERRADO + data_fim=hoje).
    """
    service = get_integration_service(db)

    try:
        assignment = await service.desalocar_diarista_posto(
            assignment_id=assignment_id,
            motivo=request.motivo,
        )

        return {
            "success": True,
            "message": "Diarista desalocado com sucesso",
            "assignment_id": str(assignment.id),
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao desalocar diarista: {str(e)}"
        )


# =============================================================================
# ENDPOINTS - SUGESTÕES
# =============================================================================


@router.get(
    "/sugerir-diarista/{post_id}",
    response_model=list[SugestaoDiaristaResponse],
    summary="Sugerir diarista para posto",
    description="Retorna diaristas sugeridos para cobrir um posto",
)
async def sugerir_diarista_posto(
    post_id: UUID,
    current_user: CurrentActiveUser,
    data: date = Query(..., description="Data desejada para cobertura"),
    habilidades: str | None = Query(None, description="Habilidades requeridas (separadas por vírgula)"),
    db: AsyncSession = Depends(get_db),
) -> list[SugestaoDiaristaResponse]:
    """
    Sugere diaristas disponíveis para um posto.

    Ordena por:
    - Score de adequação
    - Habilidades compatíveis
    - Avaliação média
    """
    service = get_integration_service(db)

    habilidades_lista: list[str] | None = None
    if habilidades:
        habilidades_lista = [h.strip() for h in habilidades.split(",")]

    try:
        sugestoes = await service.sugerir_diarista_posto(
            post_id=post_id,
            data=data,
            habilidades_requeridas=habilidades_lista,
        )
        return sugestoes
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao sugerir diaristas: {str(e)}"
        )


# =============================================================================
# ENDPOINTS - RELATÓRIOS RÁPIDOS
# =============================================================================


@router.get("/resumo-dia", summary="Resumo do dia", description="Retorna resumo executivo do dia atual")
async def get_resumo_dia(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Retorna resumo executivo do dia atual.

    Inclui principais métricas e alertas.
    """
    service = get_integration_service(db)

    try:
        dashboard = await service.get_dashboard_unificado()

        return {
            "data": dashboard["data_referencia"],
            "resumo": {
                "postos_ativos": dashboard["postos"]["ativos"],
                "turnos_hoje": dashboard["turnos"]["hoje"],
                "turnos_em_andamento": dashboard["turnos"]["em_andamento"],
                "diaristas_em_servico": dashboard["diaristas"]["em_servico"],
                "taxa_ocupacao": dashboard["ocupacao"]["taxa_ocupacao_percentual"],
            },
            "alertas_criticos": [a for a in dashboard["alertas"] if a["tipo"] == "error"],
            "total_alertas": len(dashboard["alertas"]),
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao gerar resumo: {str(e)}")


@router.get("/kpis", summary="KPIs operacionais", description="Retorna KPIs principais do operacional")
async def get_kpis(
    current_user: CurrentActiveUser,
    periodo_dias: int = Query(30, ge=7, le=365, description="Período em dias"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Retorna KPIs operacionais.

    Métricas calculadas para o período especificado.
    """
    service = get_integration_service(db)

    data_fim = date.today()
    data_inicio = data_fim - timedelta(days=periodo_dias)

    try:
        metricas = await service.get_metricas_periodo(data_inicio, data_fim)
        dashboard = await service.get_dashboard_unificado()

        # Tendência REAL: mesmo cálculo sobre o período imediatamente anterior
        # (shifts/diarist_schedules reais) — deltas em pontos percentuais/valores.
        anterior_fim = data_inicio - timedelta(days=1)
        anterior_inicio = anterior_fim - timedelta(days=periodo_dias - 1)
        metricas_anteriores = await service.get_metricas_periodo(anterior_inicio, anterior_fim)

        comparacao = {
            "periodo_anterior": metricas_anteriores["periodo"],
            "delta_taxa_comparecimento_diaristas": round(
                metricas["diaristas"]["taxa_comparecimento"]
                - metricas_anteriores["diaristas"]["taxa_comparecimento"],
                2,
            ),
            "delta_taxa_conclusao_turnos": round(
                metricas["funcionarios"]["taxa_conclusao"] - metricas_anteriores["funcionarios"]["taxa_conclusao"],
                2,
            ),
            "delta_horas_diaristas": round(
                metricas["diaristas"]["horas_trabalhadas"] - metricas_anteriores["diaristas"]["horas_trabalhadas"],
                2,
            ),
            "delta_servicos_realizados": (
                metricas["consolidado"]["servicos_concluidos"]
                - metricas_anteriores["consolidado"]["servicos_concluidos"]
            ),
        }

        return {
            "periodo": metricas["periodo"],
            "kpis": {
                "taxa_ocupacao_atual": dashboard["ocupacao"]["taxa_ocupacao_percentual"],
                "taxa_comparecimento_diaristas": metricas["diaristas"]["taxa_comparecimento"],
                "taxa_conclusao_turnos": metricas["funcionarios"]["taxa_conclusao"],
                "total_horas_diaristas": metricas["diaristas"]["horas_trabalhadas"],
                "total_servicos_realizados": metricas["consolidado"]["servicos_concluidos"],
            },
            "tendencia": {
                "comparado_periodo_anterior": comparacao,
            },
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao calcular KPIs: {str(e)}"
        )


@router.get("/kpi-trends", summary="Tendências de KPIs", description="Retorna dados históricos para sparklines de KPIs")
async def get_kpi_trends(
    current_user: CurrentActiveUser,
    period: str = Query("7d", description="Período de análise (7d, 30d, 90d)"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Retorna dados históricos de KPIs para sparklines.

    Períodos suportados:
    - 7d: últimos 7 dias
    - 30d: últimos 30 dias
    - 90d: últimos 90 dias

    Retorna arrays de valores para:
    - Postos ativos
    - Colaboradores ativos
    - Escalas em andamento
    - Ocorrências do mês
    - Taxa de cobertura (%)
    """
    from modules.operacional.repositories import PostRepository

    # Definir período
    periods: dict[str, int] = {
        "7d": 7,
        "30d": 30,
        "90d": 90,
    }

    if period not in periods:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Período inválido. Use: {', '.join(periods.keys())}"
        )

    days = periods[period]
    hoje = date.today()

    try:
        post_repo = PostRepository(db)

        # Stats de postos: FOTO ATUAL (não existe histórico diário de postos/
        # alocações no banco). get_stats é ASYNC e retorna PostStats (Pydantic)
        # — await + acesso por atributo (o bug antigo era coroutine sem await
        # sendo lida com .get()).
        stats = await post_repo.get_stats()
        total_postos = stats.by_status.get("active", 0)
        colaboradores_result = await db.execute(
            text("SELECT count(*) FROM employees WHERE status = 'ativo'")
        )
        total_colaboradores = int(colaboradores_result.scalar() or 0)
        cobertura_atual = round((stats.filled / stats.total * 100) if stats.total > 0 else 0)

        # Escalas em andamento: FOTO ATUAL (scales.is_active — NÃO existe
        # coluna "ativo"; status varchar 'in_progress').
        escalas_atual = (
            await db.execute(
                text("SELECT count(*) FROM scales WHERE status = 'in_progress' AND is_active = true")
            )
        ).scalar_one()

        # Calcular dados diários
        postos_ativos: list[int] = []
        colaboradores_ativos: list[int] = []
        escalas_em_andamento: list[int] = []
        ocorrencias_mes: list[int] = []
        cobertura_percentual: list[int] = []

        # Gerar dados para cada dia do período.
        # HONESTIDADE: só ocorrências têm carimbo temporal (occurred_at) —
        # as demais séries repetem a foto atual porque não há histórico.
        for i in range(days):
            data_ref = hoje - timedelta(days=days - i - 1)

            postos_ativos.append(total_postos)
            colaboradores_ativos.append(total_colaboradores)
            escalas_em_andamento.append(escalas_atual)
            cobertura_percentual.append(cobertura_atual)

            # Ocorrências do mês acumuladas até data_ref (occurred_at é a
            # coluna real — "data_ocorrencia" não existe)
            primeiro_dia_mes = data_ref.replace(day=1)
            ocorrencias = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM occurrences "
                        "WHERE occurred_at >= :ini AND occurred_at < :fim"
                    ),
                    {"ini": primeiro_dia_mes, "fim": data_ref + timedelta(days=1)},
                )
            ).scalar_one()
            ocorrencias_mes.append(ocorrencias)

        return {
            "period": period,
            "days": days,
            "data": {
                "postos_ativos": postos_ativos,
                "colaboradores_ativos": colaboradores_ativos,
                "escalas_em_andamento": escalas_em_andamento,
                "ocorrencias_mes": ocorrencias_mes,
                "cobertura_percentual": cobertura_percentual,
            },
            "nota": (
                "Séries de postos/colaboradores/escalas/cobertura refletem a foto atual "
                "(não há histórico diário no banco); apenas ocorrencias_mes é histórica (occurred_at)."
            ),
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao calcular tendências: {str(e)}"
        )
