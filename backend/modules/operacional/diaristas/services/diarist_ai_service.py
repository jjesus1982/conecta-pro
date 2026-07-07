"""Service de IA para Diaristas.

Regras de veracidade:
- Toda métrica vem de dados reais (diarist_schedules / diarist_payments / diarists).
- Sem dado no período => listas vazias / zeros com mensagem explicativa; nunca inventar score.
"""

import logging
from datetime import date, time, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.operacional.diaristas.models.diarist import (
    Diarist,
    DiaristPayment,
    DiaristSchedule,
    DiaristStatus,
    DiaristType,
    PaymentStatus,
    ScheduleStatus,
)
from modules.operacional.diaristas.repositories.diarist_repository import DiaristRepository
from modules.operacional.diaristas.schemas.diarist_schemas import (
    DiaristAvailabilityResponse,
    DiaristPerformanceResponse,
    DiaristSuggestionResponse,
    ScheduleOptimizationResponse,
)

logger = logging.getLogger(__name__)

# Status que ocupam a diarista (não cancelados/faltas)
_ACTIVE_SCHEDULE_STATUSES = {
    ScheduleStatus.AGENDADO.value,
    ScheduleStatus.CONFIRMADO.value,
    ScheduleStatus.EM_ANDAMENTO.value,
    ScheduleStatus.CONCLUIDO.value,
}


class DiaristAIService:
    """Service de IA para recomendações e análises de diaristas."""

    def __init__(self, db: AsyncSession):
        """Inicializa o service."""
        self.db = db
        self.repository = DiaristRepository(db)

    # ==================== MÉTRICAS BASE (dados reais) ====================

    async def _get_schedule_metrics(
        self,
        diarist_id: UUID,
        data_inicio: date,
        data_fim: date,
    ) -> dict:
        """Calcula métricas reais de agendamentos da diarista no período.

        Usa somente colunas reais: data_trabalho, status (ENUM PG uppercase),
        checkin_real/checkout_real (via duracao_minutos).
        """
        result = await self.db.execute(
            select(DiaristSchedule).where(
                DiaristSchedule.diarist_id == diarist_id,
                DiaristSchedule.data_trabalho >= data_inicio,
                DiaristSchedule.data_trabalho <= data_fim,
            )
        )
        schedules = list(result.scalars().all())

        total = len(schedules)
        concluidos = sum(1 for s in schedules if s.status == ScheduleStatus.CONCLUIDO.value)
        cancelados = sum(1 for s in schedules if s.status == ScheduleStatus.CANCELADO.value)
        faltas = sum(1 for s in schedules if s.status == ScheduleStatus.NAO_COMPARECEU.value)

        # Horas reais: só entre checkin_real e checkout_real de serviços concluídos
        minutos = sum(
            (s.duracao_minutos or 0) for s in schedules if s.status == ScheduleStatus.CONCLUIDO.value
        )
        horas_trabalhadas = minutos / 60

        pontuais = sum(
            1
            for s in schedules
            if s.status == ScheduleStatus.CONCLUIDO.value and s.checkin_real is not None
        )

        comparecimentos_esperados = concluidos + faltas
        return {
            "total": total,
            "concluidos": concluidos,
            "cancelados": cancelados,
            "faltas": faltas,
            "horas_trabalhadas": round(horas_trabalhadas, 2),
            "taxa_conclusao": (concluidos / total * 100) if total > 0 else 0.0,
            "taxa_pontualidade": (pontuais / concluidos * 100) if concluidos > 0 else 0.0,
            "taxa_comparecimento": (
                (concluidos / comparecimentos_esperados * 100) if comparecimentos_esperados > 0 else 0.0
            ),
        }

    # ==================== SUGESTÃO ====================

    async def suggest_diarists(
        self,
        data: date,
        tipo: DiaristType | None = None,
        duracao_horas: int = 8,
        priorizar_conhecidas: bool = True,
        condominio_id: UUID | None = None,
    ) -> list[DiaristSuggestionResponse]:
        """
        Sugere diaristas para uma data específica.

        Critérios de pontuação (sobre dados reais dos últimos 90 dias):
        - Avaliação média (peso 30%)
        - Taxa de conclusão (peso 20%)
        - Experiência no condomínio informado (peso 25%)
        - Pontualidade (peso 15%)
        - Disponibilidade de horário (peso 10%)

        condominio_id é opcional: None = sem bônus de experiência local.
        Sem diaristas disponíveis => lista vazia (honesto).
        """
        available = await self.repository.get_available_diarists(data=data, tipo=tipo)
        if not available:
            return []

        janela_inicio = data - timedelta(days=90)
        scored: list[tuple[Diarist, float, dict]] = []

        for diarist in available:
            metrics = await self._get_schedule_metrics(diarist.id, janela_inicio, data)

            known_assignments = 0
            if condominio_id and priorizar_conhecidas:
                assignments = await self.repository.list_assignments(
                    diarist_id=diarist.id,
                    condominio_id=condominio_id,
                )
                known_assignments = len(assignments)

            score = self._calculate_suggestion_score(
                diarist=diarist,
                metrics=metrics,
                known_assignments=known_assignments,
                duracao_horas=duracao_horas,
            )
            scored.append((diarist, score, metrics))

        scored.sort(key=lambda x: x[1], reverse=True)

        suggestions = []
        for diarist, score, metrics in scored[:5]:
            tipos = diarist.tipos_servico or []
            diarist_tipo = tipos[0] if tipos else (tipo.value if tipo else "outro")
            suggestions.append(
                DiaristSuggestionResponse(
                    diarist_id=str(diarist.id),
                    diarist_nome=diarist.nome,
                    diarist_tipo=diarist_tipo,
                    score=round(score, 2),
                    motivo="; ".join(self._get_score_reasons(diarist, score)),
                    disponivel=True,
                    valor_diaria=float(diarist.valor_diaria or 0),
                    media_avaliacao=float(diarist.avaliacao_media or 0),
                    total_diarias=int(diarist.total_servicos or 0),
                )
            )
        return suggestions

    def _calculate_suggestion_score(
        self,
        diarist: Diarist,
        metrics: dict,
        known_assignments: int,
        duracao_horas: int,
    ) -> float:
        """Calcula score de sugestão a partir de métricas reais já carregadas."""
        score = 0.0

        # Avaliação média (peso 30%) - máximo 30 pontos
        if diarist.avaliacao_media:
            score += float(diarist.avaliacao_media) * 6  # 5 * 6 = 30

        # Taxa de conclusão (peso 20%) - máximo 20 pontos
        if metrics["total"] > 0:
            score += metrics["taxa_conclusao"] * 0.2

        # Experiência no condomínio (peso 25%) - máximo 25 pontos
        if known_assignments:
            score += min(known_assignments * 5, 25)

        # Pontualidade (peso 15%) - máximo 15 pontos
        score += metrics["taxa_pontualidade"] * 0.15

        # Disponibilidade de horário (peso 10%) - máximo 10 pontos
        if diarist.hora_fim_disponivel and diarist.hora_inicio_disponivel:
            horas_disponiveis = diarist.hora_fim_disponivel.hour - diarist.hora_inicio_disponivel.hour
            if horas_disponiveis >= duracao_horas:
                score += 10
            elif duracao_horas > 0:
                score += (horas_disponiveis / duracao_horas) * 10

        return score

    def _get_score_reasons(self, diarist: Diarist, score: float) -> list[str]:
        """Gera motivos para a pontuação (só afirma o que consta no cadastro)."""
        reasons = []

        if diarist.avaliacao_media and float(diarist.avaliacao_media) >= 4.5:
            reasons.append("Excelente avaliação dos clientes")
        elif diarist.avaliacao_media and float(diarist.avaliacao_media) >= 4.0:
            reasons.append("Boa avaliação dos clientes")

        if diarist.experiencia_anos and diarist.experiencia_anos >= 5:
            reasons.append(f"{diarist.experiencia_anos} anos de experiência")

        if diarist.total_servicos and diarist.total_servicos >= 50:
            reasons.append(f"{diarist.total_servicos} serviços realizados")

        if diarist.aceita_hora_extra:
            reasons.append("Aceita hora extra")

        if score >= 80:
            reasons.append("Altamente recomendada")
        elif score >= 60:
            reasons.append("Recomendada")

        return reasons if reasons else ["Disponível para a data"]

    # ==================== DISPONIBILIDADE ====================

    async def analyze_availability(
        self,
        data_inicio: date,
        data_fim: date,
        tipo: DiaristType | None = None,
        condominio_id: UUID | None = None,
    ) -> list[DiaristAvailabilityResponse]:
        """
        Analisa disponibilidade de diaristas em um período.

        Retorna uma linha por diarista/dia:
        - disponivel=True para diaristas livres no dia (horário do cadastro);
        - disponivel=False para diaristas já agendadas (horário do agendamento).

        condominio_id filtra apenas os agendamentos (None = todos).
        Período inválido ou sem dados => lista vazia (honesto).
        """
        if data_fim < data_inicio:
            return []

        rows: list[DiaristAvailabilityResponse] = []
        current = data_inicio

        while current <= data_fim:
            available = await self.repository.get_available_diarists(data=current, tipo=tipo)
            scheduled = await self.repository.get_schedules_by_date(
                data=current,
                condominio_id=condominio_id,
            )

            for diarist in available:
                rows.append(
                    DiaristAvailabilityResponse(
                        diarist_id=str(diarist.id),
                        diarist_nome=diarist.nome,
                        data=current,
                        horario_inicio=diarist.hora_inicio_disponivel or time(8, 0),
                        horario_fim=diarist.hora_fim_disponivel or time(17, 0),
                        disponivel=True,
                        motivo=None,
                    )
                )

            for schedule in scheduled:
                if str(schedule.status) not in _ACTIVE_SCHEDULE_STATUSES:
                    continue
                rows.append(
                    DiaristAvailabilityResponse(
                        diarist_id=str(schedule.diarist_id),
                        diarist_nome=schedule.diarist.nome if schedule.diarist else "",
                        data=current,
                        horario_inicio=schedule.hora_inicio,
                        horario_fim=schedule.hora_fim,
                        disponivel=False,
                        motivo=f"Já agendada nesta data (status {schedule.status})",
                    )
                )

            current += timedelta(days=1)

        return rows

    # ==================== PERFORMANCE ====================

    async def analyze_performance(
        self,
        diarist_id: UUID,
        data_inicio: date | None = None,
        data_fim: date | None = None,
    ) -> DiaristPerformanceResponse:
        """
        Analisa performance de uma diarista com base em dados reais.

        Sem agendamentos no período => zeros + recomendação explicando a
        insuficiência de dados (nunca inventa tendência/score).
        """
        if not data_inicio:
            data_inicio = date.today() - timedelta(days=90)
        if not data_fim:
            data_fim = date.today()

        diarist = await self.repository.get_by_id(diarist_id)
        if not diarist:
            raise ValueError("Diarista não encontrada")

        metrics = await self._get_schedule_metrics(diarist_id, data_inicio, data_fim)

        pagamentos_result = await self.db.execute(
            select(func.coalesce(func.sum(DiaristPayment.valor_liquido), 0)).where(
                DiaristPayment.diarist_id == diarist_id,
                DiaristPayment.data_referencia >= data_inicio,
                DiaristPayment.data_referencia <= data_fim,
                cast(DiaristPayment.status, String) == PaymentStatus.PAGO.value,
            )
        )
        total_recebido = float(pagamentos_result.scalar() or Decimal("0"))

        tendencia = await self._calculate_trend(diarist_id, data_inicio, data_fim)
        recomendacoes = self._generate_performance_recommendations(metrics)

        return DiaristPerformanceResponse(
            diarist_id=str(diarist_id),
            diarist_nome=diarist.nome,
            periodo=f"{data_inicio.isoformat()} a {data_fim.isoformat()}",
            total_diarias=metrics["total"],
            total_horas=metrics["horas_trabalhadas"],
            taxa_comparecimento=round(metrics["taxa_comparecimento"], 1),
            taxa_pontualidade=round(metrics["taxa_pontualidade"], 1),
            media_avaliacao=float(diarist.avaliacao_media or 0),
            total_recebido=total_recebido,
            tendencia=tendencia,
            recomendacoes=recomendacoes,
        )

    def _generate_performance_recommendations(self, metrics: dict) -> list[str]:
        """Gera recomendações honestas a partir das métricas reais."""
        if metrics["total"] == 0:
            return ["Sem agendamentos no período — dados insuficientes para análise de performance."]

        recommendations = []

        if metrics["taxa_conclusao"] >= 95:
            recommendations.append("Alta confiabilidade — raramente cancela serviços.")
        elif metrics["taxa_conclusao"] < 80:
            recommendations.append("Taxa de cancelamento elevada. Verificar motivos e disponibilidade real.")

        if metrics["concluidos"] > 0:
            if metrics["taxa_pontualidade"] >= 95:
                recommendations.append("Check-in registrado em praticamente todos os serviços concluídos.")
            elif metrics["taxa_pontualidade"] < 80:
                recommendations.append(
                    "Poucos check-ins registrados nos serviços concluídos. Reforçar registro de presença."
                )
        else:
            recommendations.append("Nenhum serviço concluído no período — pontualidade não avaliável.")

        if metrics["faltas"] > 0:
            recommendations.append(f"{metrics['faltas']} falta(s) registrada(s) no período.")

        if metrics["total"] >= 20:
            recommendations.append(f"Profissional com {metrics['total']} agendamentos no período.")

        return recommendations or ["Sem desvios relevantes nas métricas do período."]

    async def _calculate_trend(
        self,
        diarist_id: UUID,
        data_inicio: date,
        data_fim: date,
    ) -> str:
        """Calcula tendência comparando as duas metades do período."""
        mid_date = data_inicio + (data_fim - data_inicio) / 2

        first_half = await self._get_schedule_metrics(diarist_id, data_inicio, mid_date)
        second_half = await self._get_schedule_metrics(diarist_id, mid_date, data_fim)

        if first_half["total"] == 0 and second_half["total"] == 0:
            return "sem_dados"

        rate1 = first_half["taxa_conclusao"]
        rate2 = second_half["taxa_conclusao"]

        if rate2 > rate1 + 5:
            return "melhorando"
        elif rate2 < rate1 - 5:
            return "declinando"
        else:
            return "estavel"

    # ==================== OTIMIZAÇÃO ====================

    async def optimize_schedule(
        self,
        data_inicio: date,
        data_fim: date,
        budget: Decimal | None = None,
        condominio_id: UUID | None = None,
    ) -> ScheduleOptimizationResponse:
        """
        Otimiza agendamentos no período a partir dos dados reais.

        condominio_id é opcional (None = todos os condomínios).
        Sem agendamentos => resposta vazia com recomendação explicativa,
        sem estimativas fabricadas de economia.
        """
        existing_schedules = await self.repository.list_schedules(
            condominio_id=condominio_id,
            data_inicio=data_inicio,
            data_fim=data_fim,
            limit=500,
        )

        if not existing_schedules:
            return ScheduleOptimizationResponse(
                data=data_inicio,
                sugestoes=[],
                conflitos=[],
                recomendacoes=["Sem agendamentos no período — nada a otimizar."],
            )

        all_diarists = await self.repository.list_all(status=DiaristStatus.ATIVO, limit=500)

        distribution = self._analyze_distribution(existing_schedules, all_diarists)
        conflitos = self._find_schedule_conflicts(existing_schedules)
        suggestions = await self._generate_optimization_suggestions(
            schedules=existing_schedules,
            distribution=distribution,
            budget=budget,
            condominio_id=condominio_id,
        )

        recomendacoes = []
        if conflitos:
            recomendacoes.append(
                f"{len(conflitos)} conflito(s) de horário detectado(s) — reagendar antes do período."
            )
        if not suggestions and not conflitos:
            recomendacoes.append("Agenda do período sem desvios detectados nos dados atuais.")
        for s in suggestions:
            recomendacoes.append(s["acao"])

        return ScheduleOptimizationResponse(
            data=data_inicio,
            sugestoes=suggestions,
            conflitos=conflitos,
            recomendacoes=recomendacoes,
        )

    def _analyze_distribution(
        self,
        schedules: list[DiaristSchedule],
        diarists: list[Diarist],
    ) -> dict:
        """Analisa distribuição de trabalho (horas via checkin/checkout reais)."""
        distribution = {}

        for diarist in diarists:
            diarist_schedules = [s for s in schedules if s.diarist_id == diarist.id]
            minutos = sum(
                (s.duracao_minutos or 0)
                for s in diarist_schedules
                if s.status == ScheduleStatus.CONCLUIDO.value
            )
            distribution[str(diarist.id)] = {
                "nome": diarist.nome,
                "total_agendamentos": len(diarist_schedules),
                "horas_totais": round(minutos / 60, 2),
                "valor_total": sum(float(s.valor_final or s.valor_previsto or 0) for s in diarist_schedules),
            }

        return distribution

    def _find_schedule_conflicts(self, schedules: list[DiaristSchedule]) -> list[dict]:
        """Detecta conflitos reais: mesma diarista, mesmo dia, horários sobrepostos."""
        conflicts = []
        active = [s for s in schedules if str(s.status) in _ACTIVE_SCHEDULE_STATUSES]

        by_key: dict[tuple, list[DiaristSchedule]] = {}
        for s in active:
            by_key.setdefault((s.diarist_id, s.data_trabalho), []).append(s)

        for (diarist_id, data_trabalho), items in by_key.items():
            if len(items) < 2:
                continue
            items.sort(key=lambda s: s.hora_inicio)
            for a, b in zip(items, items[1:]):
                if b.hora_inicio < a.hora_fim:
                    conflicts.append(
                        {
                            "diarist_id": str(diarist_id),
                            "data": data_trabalho.isoformat(),
                            "schedule_ids": [str(a.id), str(b.id)],
                            "descricao": (
                                f"Agendamentos sobrepostos: {a.hora_inicio}-{a.hora_fim} "
                                f"e {b.hora_inicio}-{b.hora_fim}"
                            ),
                        }
                    )

        return conflicts

    async def _generate_optimization_suggestions(
        self,
        schedules: list[DiaristSchedule],
        distribution: dict,
        budget: Decimal | None,
        condominio_id: UUID | None,
    ) -> list[dict]:
        """Gera sugestões de otimização a partir dos dados reais."""
        suggestions = []

        # Verificar desbalanceamento (só entre diaristas com agendamentos)
        totals = [d["total_agendamentos"] for d in distribution.values() if d["total_agendamentos"] > 0]
        if len(totals) >= 2:
            avg = sum(totals) / len(totals)
            if max(totals) - min(totals) > avg * 0.5:
                suggestions.append(
                    {
                        "tipo": "rebalanceamento",
                        "descricao": "Distribuição de trabalho desbalanceada entre as diaristas escaladas",
                        "acao": "Redistribuir agendamentos entre diaristas",
                        "impacto": "medio",
                    }
                )

        # Verificar custos vs orçamento informado
        if budget:
            total_cost = sum(float(s.valor_previsto or 0) for s in schedules)
            if Decimal(str(total_cost)) > budget:
                suggestions.append(
                    {
                        "tipo": "reducao_custos",
                        "descricao": f"Custos previstos excedem o orçamento em R$ {total_cost - float(budget):.2f}",
                        "acao": "Considerar diaristas com menor custo ou reduzir frequência",
                        "impacto": "alto",
                    }
                )

        # Verificar diaristas bem avaliadas sem agendamentos no período
        top_diarists = await self.repository.get_top_diarists(condominio_id=condominio_id, limit=5)
        for td in top_diarists:
            dist = distribution.get(str(td["diarist"].id), {})
            if dist.get("total_agendamentos", 0) == 0:
                suggestions.append(
                    {
                        "tipo": "aproveitamento",
                        "descricao": f"{td['diarist'].nome} está disponível mas sem agendamentos no período",
                        "acao": f"Considerar alocar {td['diarist'].nome} (bem avaliada) no período",
                        "impacto": "baixo",
                    }
                )

        return suggestions
