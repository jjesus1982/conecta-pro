"""
Repository para operacoes de banco de dados do modulo de Turnover.

Implementa o padrao Repository para abstrair operacoes de
persistencia das predicoes de turnover, fatores de risco e alertas.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, and_, delete, func, literal_column, or_, select, update
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from modules.retention.turnover.models.turnover_models import (
    AuditLogTurnover,
    CategoriaFator,
    NivelRisco,
    RiskAlert,
    RiskFactor,
    TurnoverPrediction,
)
from modules.retention.turnover.schemas.turnover_schemas import (
    AlertCreate,
    AlertFilter,
    PredictionCreate,
    PredictionFilter,
    RiskFactorCreate,
)

logger = logging.getLogger(__name__)


class TurnoverRepository:
    """Repository para operacoes de predicao de turnover."""

    def __init__(self, session: AsyncSession) -> None:
        """Inicializa o repository com a sessao do banco."""
        self.session = session

    # =========================================================================
    # Prediction Operations
    # =========================================================================

    async def create_prediction(
        self,
        data: PredictionCreate,
    ) -> TurnoverPrediction:
        """
        Cria uma nova predicao de turnover.

        Args:
            data: Dados da predicao

        Returns:
            TurnoverPrediction criada
        """
        prediction = TurnoverPrediction(
            funcionario_id=data.funcionario_id,
            condominium_id=data.condominium_id,
            score_risco=data.score_risco,
            nivel=data.nivel,
            modelo_versao=data.modelo_versao,
            features_usadas=data.features_usadas,
            metricas_modelo=data.metricas_modelo,
            valido_ate=data.valido_ate,
            calculado_por=data.calculado_por,
        )
        self.session.add(prediction)
        await self.session.flush()
        await self.session.refresh(prediction)
        logger.info(f"Predicao criada: funcionario={data.funcionario_id}, score={data.score_risco}")
        return prediction

    async def get_prediction_by_id(
        self,
        prediction_id: UUID,
    ) -> TurnoverPrediction | None:
        """Busca predicao por ID."""
        result = await self.session.execute(
            select(TurnoverPrediction)
            .options(selectinload(TurnoverPrediction.fatores))
            .where(
                and_(
                    TurnoverPrediction.id == prediction_id,
                    TurnoverPrediction.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_prediction(
        self,
        funcionario_id: UUID,
    ) -> TurnoverPrediction | None:
        """Busca a predicao mais recente de um funcionario."""
        result = await self.session.execute(
            select(TurnoverPrediction)
            .options(selectinload(TurnoverPrediction.fatores))
            .where(
                and_(
                    TurnoverPrediction.funcionario_id == funcionario_id,
                    TurnoverPrediction.recalculado.is_(False),
                    TurnoverPrediction.deleted_at.is_(None),
                )
            )
            .order_by(TurnoverPrediction.data_calculo.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_predictions_by_funcionario(
        self,
        funcionario_id: UUID,
        limit: int = 30,
    ) -> list[TurnoverPrediction]:
        """Busca historico de predicoes de um funcionario."""
        result = await self.session.execute(
            select(TurnoverPrediction)
            .options(selectinload(TurnoverPrediction.fatores))
            .where(
                and_(
                    TurnoverPrediction.funcionario_id == funcionario_id,
                    TurnoverPrediction.deleted_at.is_(None),
                )
            )
            .order_by(TurnoverPrediction.data_calculo.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_predictions(
        self,
        filters: PredictionFilter,
        skip: int = 0,
        limit: int = 50,
        order_by: str = "score_risco",
        order_desc: bool = True,
    ) -> tuple[list[TurnoverPrediction], int]:
        """
        Lista predicoes com filtros e paginacao.

        Args:
            filters: Filtros de busca
            skip: Offset para paginacao
            limit: Limite de resultados
            order_by: Campo para ordenacao
            order_desc: Ordenar decrescente

        Returns:
            Tupla (lista de predicoes, total)
        """
        # Query base - apenas predicoes ativas (nao recalculadas)
        query = select(TurnoverPrediction).where(
            and_(
                TurnoverPrediction.condominium_id == filters.condominium_id,
                TurnoverPrediction.recalculado.is_(False),
                TurnoverPrediction.deleted_at.is_(None),
            )
        )

        # Aplicar filtros
        if filters.nivel:
            query = query.where(TurnoverPrediction.nivel == filters.nivel)

        if filters.score_minimo is not None:
            query = query.where(TurnoverPrediction.score_risco >= filters.score_minimo)

        if filters.score_maximo is not None:
            query = query.where(TurnoverPrediction.score_risco <= filters.score_maximo)

        if filters.apenas_alerta:
            query = query.where(TurnoverPrediction.score_risco >= 70)

        if filters.data_inicio:
            query = query.where(TurnoverPrediction.data_calculo >= filters.data_inicio)

        if filters.data_fim:
            query = query.where(TurnoverPrediction.data_calculo <= filters.data_fim)

        # Contagem total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Ordenacao
        _valid_order_column_cols = {c.key for c in sa_inspect(TurnoverPrediction).mapper.column_attrs}
        order_column = getattr(TurnoverPrediction, order_by if order_by in _valid_order_column_cols else "score_risco")
        if order_desc:
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())

        # Paginacao
        query = query.offset(skip).limit(limit)
        query = query.options(selectinload(TurnoverPrediction.fatores))

        result = await self.session.execute(query)
        predictions = list(result.scalars().all())

        return predictions, total

    async def mark_prediction_recalculado(
        self,
        funcionario_id: UUID,
    ) -> int:
        """Marca predicoes anteriores como recalculadas."""
        result = await self.session.execute(
            update(TurnoverPrediction)
            .where(
                and_(
                    TurnoverPrediction.funcionario_id == funcionario_id,
                    TurnoverPrediction.recalculado.is_(False),
                )
            )
            .values(recalculado=True)
        )
        return result.rowcount

    async def get_predictions_by_nivel(
        self,
        condominium_id: UUID,
        nivel: NivelRisco,
        limit: int = 100,
    ) -> list[TurnoverPrediction]:
        """Busca predicoes por nivel de risco."""
        result = await self.session.execute(
            select(TurnoverPrediction)
            .options(selectinload(TurnoverPrediction.fatores))
            .where(
                and_(
                    TurnoverPrediction.condominium_id == condominium_id,
                    TurnoverPrediction.nivel == nivel,
                    TurnoverPrediction.recalculado.is_(False),
                    TurnoverPrediction.deleted_at.is_(None),
                )
            )
            .order_by(TurnoverPrediction.score_risco.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_funcionarios_sem_predicao(
        self,
        condominium_id: UUID,
        funcionario_ids: list[UUID],
    ) -> list[UUID]:
        """Retorna funcionarios que nao tem predicao ativa."""
        result = await self.session.execute(
            select(TurnoverPrediction.funcionario_id).where(
                and_(
                    TurnoverPrediction.condominium_id == condominium_id,
                    TurnoverPrediction.funcionario_id.in_(funcionario_ids),
                    TurnoverPrediction.recalculado.is_(False),
                    TurnoverPrediction.deleted_at.is_(None),
                )
            )
        )
        com_predicao = {row[0] for row in result.all()}
        return [fid for fid in funcionario_ids if fid not in com_predicao]

    # =========================================================================
    # Risk Factor Operations
    # =========================================================================

    async def create_risk_factors(
        self,
        fatores: list[RiskFactorCreate],
    ) -> list[RiskFactor]:
        """Cria multiplos fatores de risco."""
        risk_factors = [
            RiskFactor(
                prediction_id=f.prediction_id,
                nome=f.nome,
                categoria=f.categoria,
                peso=f.peso,
                valor_atual=f.valor_atual,
                valor_normalizado=f.valor_normalizado,
                contribuicao_score=f.contribuicao_score,
                threshold_violado=f.threshold_violado,
                descricao=f.descricao,
                recomendacao_acao=f.recomendacao_acao,
                dados_brutos=f.dados_brutos,
            )
            for f in fatores
        ]
        self.session.add_all(risk_factors)
        await self.session.flush()
        return risk_factors

    async def get_factors_by_prediction(
        self,
        prediction_id: UUID,
    ) -> list[RiskFactor]:
        """Busca fatores de uma predicao."""
        result = await self.session.execute(
            select(RiskFactor)
            .where(RiskFactor.prediction_id == prediction_id)
            .order_by(RiskFactor.contribuicao_score.desc())
        )
        return list(result.scalars().all())

    async def get_aggregated_factors(
        self,
        condominium_id: UUID,
        categoria: CategoriaFator | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retorna estatisticas agregadas dos fatores de risco.

        Args:
            condominium_id: ID do condominio
            categoria: Filtrar por categoria

        Returns:
            Lista com estatisticas por fator
        """
        # Subquery para predicoes ativas do condominio
        pred_subquery = (
            select(TurnoverPrediction.id)
            .where(
                and_(
                    TurnoverPrediction.condominium_id == condominium_id,
                    TurnoverPrediction.recalculado.is_(False),
                    TurnoverPrediction.deleted_at.is_(None),
                )
            )
            .scalar_subquery()
        )

        # Query de agregacao
        query = (
            select(
                RiskFactor.nome,
                RiskFactor.categoria,
                func.count(RiskFactor.id).label("total_ocorrencias"),
                func.avg(RiskFactor.contribuicao_score).label("contribuicao_media"),
                func.max(RiskFactor.contribuicao_score).label("contribuicao_maxima"),
                func.avg(func.cast(RiskFactor.threshold_violado, Integer)).label("percentual_threshold"),
                # [Turnover rewrite] JOIN + count(distinct funcionario_id) — antes usava um
                # scalar_subquery correlacionado dentro de count(distinct), invalido em GROUP BY.
                func.count(func.distinct(TurnoverPrediction.funcionario_id)).label("funcionarios_afetados"),
            )
            .join(TurnoverPrediction, TurnoverPrediction.id == RiskFactor.prediction_id)
            .where(RiskFactor.prediction_id.in_(pred_subquery))
            .group_by(
                RiskFactor.nome,
                RiskFactor.categoria,
            )
            .order_by(func.avg(RiskFactor.contribuicao_score).desc())
        )

        if categoria:
            query = query.where(RiskFactor.categoria == categoria)

        result = await self.session.execute(query)
        return [
            {
                "nome": row.nome,
                "categoria": row.categoria,
                "total_ocorrencias": row.total_ocorrencias,
                "contribuicao_media": round(row.contribuicao_media or 0, 2),
                "contribuicao_maxima": round(row.contribuicao_maxima or 0, 2),
                "percentual_threshold_violado": round((row.percentual_threshold or 0) * 100, 2),
                "funcionarios_afetados": row.funcionarios_afetados or 0,
            }
            for row in result.all()
        ]

    # =========================================================================
    # Alert Operations
    # =========================================================================

    async def create_alert(
        self,
        data: AlertCreate,
    ) -> RiskAlert:
        """Cria um novo alerta de risco."""
        alert = RiskAlert(
            funcionario_id=data.funcionario_id,
            prediction_id=data.prediction_id,
            condominium_id=data.condominium_id,
            tipo=data.tipo,
            score_atual=data.score_atual,
            score_anterior=data.score_anterior,
            variacao_score=data.variacao_score,
            nivel_atual=data.nivel_atual,
            nivel_anterior=data.nivel_anterior,
            titulo=data.titulo,
            mensagem=data.mensagem,
            enviado_para=data.enviado_para,
            prioridade=data.prioridade,
            expira_em=data.expira_em,
            dados_extras=data.dados_extras,
        )
        self.session.add(alert)
        await self.session.flush()
        await self.session.refresh(alert)
        logger.info(f"Alerta criado: tipo={data.tipo.value}, funcionario={data.funcionario_id}")
        return alert

    async def get_alert_by_id(
        self,
        alert_id: UUID,
    ) -> RiskAlert | None:
        """Busca alerta por ID."""
        result = await self.session.execute(select(RiskAlert).where(RiskAlert.id == alert_id))
        return result.scalar_one_or_none()

    async def list_alerts(
        self,
        filters: AlertFilter,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[RiskAlert], int]:
        """Lista alertas com filtros e paginacao."""
        query = select(RiskAlert).where(RiskAlert.condominium_id == filters.condominium_id)

        if filters.tipo:
            query = query.where(RiskAlert.tipo == filters.tipo)

        if filters.visualizado is not None:
            query = query.where(RiskAlert.visualizado == filters.visualizado)

        if filters.prioridade_maxima:
            query = query.where(RiskAlert.prioridade <= filters.prioridade_maxima)

        if filters.data_inicio:
            query = query.where(RiskAlert.created_at >= filters.data_inicio)

        if filters.data_fim:
            query = query.where(RiskAlert.created_at <= filters.data_fim)

        # Contagem
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Ordenacao e paginacao
        query = query.order_by(RiskAlert.prioridade.asc(), RiskAlert.created_at.desc()).offset(skip).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def get_pending_alerts(
        self,
        condominium_id: UUID,
        limit: int = 50,
    ) -> list[RiskAlert]:
        """Busca alertas pendentes (nao visualizados)."""
        result = await self.session.execute(
            select(RiskAlert)
            .where(
                and_(
                    RiskAlert.condominium_id == condominium_id,
                    RiskAlert.visualizado.is_(False),
                    or_(
                        RiskAlert.expira_em.is_(None),
                        RiskAlert.expira_em > datetime.utcnow(),
                    ),
                )
            )
            .order_by(RiskAlert.prioridade.asc(), RiskAlert.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_alert_visualizado(
        self,
        alert_id: UUID,
        usuario_id: UUID,
    ) -> RiskAlert | None:
        """Marca alerta como visualizado."""
        alert = await self.get_alert_by_id(alert_id)
        if alert:
            alert.marcar_visualizado(usuario_id)
            await self.session.flush()
            await self.session.refresh(alert)
        return alert

    async def register_alert_action(
        self,
        alert_id: UUID,
        acao: str,
        usuario_id: UUID,
    ) -> RiskAlert | None:
        """Registra acao tomada em um alerta."""
        alert = await self.get_alert_by_id(alert_id)
        if alert:
            alert.registrar_acao(acao, usuario_id)
            await self.session.flush()
            await self.session.refresh(alert)
        return alert

    async def count_alerts_by_period(
        self,
        condominium_id: UUID,
        data_inicio: datetime,
        data_fim: datetime | None = None,
    ) -> int:
        """Conta alertas em um periodo."""
        query = select(func.count(RiskAlert.id)).where(
            and_(
                RiskAlert.condominium_id == condominium_id,
                RiskAlert.created_at >= data_inicio,
            )
        )
        if data_fim:
            query = query.where(RiskAlert.created_at <= data_fim)

        result = await self.session.execute(query)
        return result.scalar() or 0

    # =========================================================================
    # Dashboard/Statistics Operations
    # =========================================================================

    async def get_distribution_by_nivel(
        self,
        condominium_id: UUID,
    ) -> list[dict[str, Any]]:
        """Retorna distribuicao de predicoes por nivel."""
        result = await self.session.execute(
            select(
                TurnoverPrediction.nivel,
                func.count(TurnoverPrediction.id).label("quantidade"),
            )
            .where(
                and_(
                    TurnoverPrediction.condominium_id == condominium_id,
                    TurnoverPrediction.recalculado.is_(False),
                    TurnoverPrediction.deleted_at.is_(None),
                )
            )
            .group_by(TurnoverPrediction.nivel)
        )
        return [{"nivel": row.nivel, "quantidade": row.quantidade} for row in result.all()]

    async def get_average_score(
        self,
        condominium_id: UUID,
    ) -> Decimal:
        """Retorna score medio do condominio."""
        result = await self.session.execute(
            select(func.avg(TurnoverPrediction.score_risco)).where(
                and_(
                    TurnoverPrediction.condominium_id == condominium_id,
                    TurnoverPrediction.recalculado.is_(False),
                    TurnoverPrediction.deleted_at.is_(None),
                )
            )
        )
        return Decimal(str(round(result.scalar() or 0, 2)))

    async def get_trend_data(
        self,
        condominium_id: UUID,
        dias: int = 30,
    ) -> list[dict[str, Any]]:
        """Retorna dados de tendencia dos ultimos N dias."""
        data_inicio = datetime.utcnow() - timedelta(days=dias)

        # [Turnover rewrite] date_trunc com unidade LITERAL (nao bound param), senao SELECT e
        # GROUP BY viram $1/$4 distintos e o Postgres exige data_calculo no GROUP BY.
        _dia = func.date_trunc(literal_column("'day'"), TurnoverPrediction.data_calculo)
        result = await self.session.execute(
            select(
                _dia.label("data"),
                func.avg(TurnoverPrediction.score_risco).label("score_medio"),
                func.sum(
                    func.cast(
                        TurnoverPrediction.nivel == NivelRisco.CRITICO,
                        Integer,
                    )
                ).label("total_criticos"),
                func.sum(
                    func.cast(
                        TurnoverPrediction.nivel == NivelRisco.ALTO,
                        Integer,
                    )
                ).label("total_altos"),
            )
            .where(
                and_(
                    TurnoverPrediction.condominium_id == condominium_id,
                    TurnoverPrediction.data_calculo >= data_inicio,
                    TurnoverPrediction.deleted_at.is_(None),
                )
            )
            .group_by(_dia)
            .order_by(_dia)
        )

        return [
            {
                "data": row.data,
                "score_medio": round(row.score_medio or 0, 2),
                "total_criticos": int(row.total_criticos or 0),
                "total_altos": int(row.total_altos or 0),
            }
            for row in result.all()
        ]

    async def count_active_predictions(
        self,
        condominium_id: UUID,
    ) -> int:
        """Conta predicoes ativas."""
        result = await self.session.execute(
            select(func.count(TurnoverPrediction.id)).where(
                and_(
                    TurnoverPrediction.condominium_id == condominium_id,
                    TurnoverPrediction.recalculado.is_(False),
                    TurnoverPrediction.deleted_at.is_(None),
                )
            )
        )
        return result.scalar() or 0

    async def get_score_variation(
        self,
        condominium_id: UUID,
        dias: int = 30,
    ) -> tuple[int, int]:
        """
        Retorna contagem de funcionarios com risco crescente/decrescente.

        Returns:
            Tupla (risco_crescente, risco_decrescente)
        """
        data_limite = datetime.utcnow() - timedelta(days=dias)

        # Subquery para predicoes recentes
        subq = (
            select(
                TurnoverPrediction.funcionario_id,
                TurnoverPrediction.score_risco,
                TurnoverPrediction.data_calculo,
                func.row_number()
                .over(
                    partition_by=TurnoverPrediction.funcionario_id,
                    order_by=TurnoverPrediction.data_calculo.desc(),
                )
                .label("rn"),
            )
            .where(
                and_(
                    TurnoverPrediction.condominium_id == condominium_id,
                    TurnoverPrediction.data_calculo >= data_limite,
                    TurnoverPrediction.deleted_at.is_(None),
                )
            )
            .subquery()
        )

        # Pegar 2 ultimas predicoes de cada funcionario
        current = (
            select(
                subq.c.funcionario_id,
                subq.c.score_risco.label("score_atual"),
            )
            .where(subq.c.rn == 1)
            .subquery()
        )

        previous = (
            select(
                subq.c.funcionario_id,
                subq.c.score_risco.label("score_anterior"),
            )
            .where(subq.c.rn == 2)
            .subquery()
        )

        # Join e calcular variacao
        comparison = select(
            current.c.funcionario_id,
            current.c.score_atual,
            previous.c.score_anterior,
        ).join(
            previous,
            current.c.funcionario_id == previous.c.funcionario_id,
        )

        result = await self.session.execute(comparison)
        rows = result.all()

        crescente = sum(1 for r in rows if r.score_atual > r.score_anterior)
        decrescente = sum(1 for r in rows if r.score_atual < r.score_anterior)

        return crescente, decrescente

    # =========================================================================
    # Audit Log Operations
    # =========================================================================

    async def create_audit_log(
        self,
        usuario_id: UUID,
        condominium_id: UUID,
        acao: str,
        recurso: str,
        recurso_id: UUID | None = None,
        funcionario_id: UUID | None = None,
        detalhes: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLogTurnover:
        """Registra log de auditoria."""
        log = AuditLogTurnover(
            usuario_id=usuario_id,
            condominium_id=condominium_id,
            acao=acao,
            recurso=recurso,
            recurso_id=recurso_id,
            funcionario_id=funcionario_id,
            detalhes=detalhes,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def get_audit_logs(
        self,
        condominium_id: UUID,
        usuario_id: UUID | None = None,
        funcionario_id: UUID | None = None,
        acao: str | None = None,
        data_inicio: datetime | None = None,
        data_fim: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditLogTurnover]:
        """Busca logs de auditoria."""
        query = select(AuditLogTurnover).where(AuditLogTurnover.condominium_id == condominium_id)

        if usuario_id:
            query = query.where(AuditLogTurnover.usuario_id == usuario_id)
        if funcionario_id:
            query = query.where(AuditLogTurnover.funcionario_id == funcionario_id)
        if acao:
            query = query.where(AuditLogTurnover.acao == acao)
        if data_inicio:
            query = query.where(AuditLogTurnover.created_at >= data_inicio)
        if data_fim:
            query = query.where(AuditLogTurnover.created_at <= data_fim)

        query = query.order_by(AuditLogTurnover.created_at.desc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    # =========================================================================
    # Cleanup Operations
    # =========================================================================

    async def cleanup_old_predictions(
        self,
        condominium_id: UUID,
        dias_retencao: int = 365,
    ) -> int:
        """Remove predicoes antigas recalculadas."""
        data_limite = datetime.utcnow() - timedelta(days=dias_retencao)

        result = await self.session.execute(
            delete(TurnoverPrediction).where(
                and_(
                    TurnoverPrediction.condominium_id == condominium_id,
                    TurnoverPrediction.recalculado.is_(True),
                    TurnoverPrediction.data_calculo < data_limite,
                )
            )
        )
        logger.info(f"Cleanup: {result.rowcount} predicoes antigas removidas do condominio {condominium_id}")
        return result.rowcount

    async def cleanup_expired_alerts(
        self,
        condominium_id: UUID,
    ) -> int:
        """Remove alertas expirados e visualizados."""
        data_limite = datetime.utcnow() - timedelta(days=90)

        result = await self.session.execute(
            delete(RiskAlert).where(
                and_(
                    RiskAlert.condominium_id == condominium_id,
                    RiskAlert.visualizado.is_(True),
                    RiskAlert.created_at < data_limite,
                )
            )
        )
        return result.rowcount
