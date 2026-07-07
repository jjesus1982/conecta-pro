"""Repository para gerenciamento de Diaristas."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from modules.operacional.diaristas.models.diarist import (
    AssignmentStatus,
    Diarist,
    DiaristAssignment,
    DiaristEvaluation,
    DiaristPayment,
    DiaristSchedule,
    DiaristStatus,
    DiaristType,
    PaymentStatus,
    ScheduleStatus,
)


class DiaristRepository:
    """Repository para operações de Diarista."""

    def __init__(self, db: AsyncSession):
        """Inicializa o repository."""
        self.db = db

    # ==================== DIARIST CRUD ====================

    async def create(self, diarist: Diarist) -> Diarist:
        """Cria uma nova diarista."""
        self.db.add(diarist)
        await self.db.commit()
        await self.db.refresh(diarist)
        return diarist

    async def get_by_id(self, diarist_id: UUID) -> Diarist | None:
        """Busca diarista por ID."""
        result = await self.db.execute(select(Diarist).where(Diarist.id == diarist_id))
        return result.scalar_one_or_none()

    async def get_by_cpf(self, cpf: str) -> Diarist | None:
        """Busca diarista por CPF."""
        result = await self.db.execute(select(Diarist).where(Diarist.cpf == cpf))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Diarist | None:
        """Busca diarista por email."""
        result = await self.db.execute(select(Diarist).where(Diarist.email == email))
        return result.scalar_one_or_none()

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        status: DiaristStatus | None = None,
        tipo: DiaristType | None = None,
        search: str | None = None,
    ) -> list[Diarist]:
        """Lista diaristas com filtros."""
        query = select(Diarist).where(Diarist.ativo.is_(True))

        if status:
            query = query.where(Diarist.status == status.value)

        if tipo:
            query = query.where(Diarist.tipos_servico.any(tipo.value))

        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Diarist.nome.ilike(search_term),
                    Diarist.cpf.ilike(search_term),
                    Diarist.email.ilike(search_term),
                )
            )

        query = query.order_by(Diarist.nome).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        status: DiaristStatus | None = None,
        tipo: DiaristType | None = None,
    ) -> int:
        """Conta diaristas com filtros."""
        query = select(func.count(Diarist.id))

        if status:
            query = query.where(Diarist.status == status)

        if tipo:
            query = query.where(Diarist.tipos_servico.contains([tipo]))

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def update(self, diarist: Diarist) -> Diarist:
        """Atualiza diarista."""
        await self.db.commit()
        await self.db.refresh(diarist)
        return diarist

    async def delete(self, diarist_id: UUID) -> bool:
        """Remove diarista (soft delete)."""
        diarist = await self.get_by_id(diarist_id)
        if diarist:
            diarist.ativo = False
            diarist.status = DiaristStatus.INATIVO
            await self.db.commit()
            return True
        return False

    # ==================== DISPONIBILIDADE ====================

    async def get_available_diarists(
        self,
        data: date,
        tipo: DiaristType | None = None,
    ) -> list[Diarist]:
        """Busca diaristas disponíveis em uma data."""
        weekday_pt = self.WEEKDAY_MAP.get(data.weekday(), "")

        query = select(Diarist).where(
            Diarist.status == DiaristStatus.ATIVO.value,
            Diarist.ativo.is_(True),
        )
        if weekday_pt:
            query = query.where(Diarist.dias_disponiveis.any(weekday_pt))

        if tipo:
            query = query.where(Diarist.tipos_servico.contains([tipo]))

        # Excluir diaristas já alocadas nesta data
        subquery = select(DiaristSchedule.diarist_id).where(
            DiaristSchedule.data_trabalho == data,
            cast(DiaristSchedule.status, String).in_(
                [
                    "AGENDADO",
                    "CONFIRMADO",
                    "EM_ANDAMENTO",
                ]
            ),
        )

        query = query.where(~Diarist.id.in_(subquery))
        query = query.order_by(Diarist.avaliacao_media.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # Mapeamento de dias da semana (ingles -> portugues)
    WEEKDAY_MAP = {
        0: "segunda",
        1: "terca",
        2: "quarta",
        3: "quinta",
        4: "sexta",
        5: "sabado",
        6: "domingo",
    }

    async def check_availability(
        self,
        diarist_id: UUID,
        data: date,
    ) -> bool:
        """Verifica se diarista está disponível em uma data."""
        diarist = await self.get_by_id(diarist_id)
        if not diarist or diarist.status != DiaristStatus.ATIVO.value:
            return False

        weekday_pt = self.WEEKDAY_MAP.get(data.weekday(), "")
        if weekday_pt not in (diarist.dias_disponiveis or []):
            return False

        # Verificar se já tem agendamento
        existing_result = await self.db.execute(
            select(DiaristSchedule).where(
                DiaristSchedule.diarist_id == diarist_id,
                DiaristSchedule.data_trabalho == data,
                cast(DiaristSchedule.status, String).in_(
                    [
                        "AGENDADO",
                        "CONFIRMADO",
                        "EM_ANDAMENTO",
                    ]
                ),
            )
        )
        existing = existing_result.scalar_one_or_none()

        return existing is None

    # ==================== ASSIGNMENT CRUD ====================

    async def create_assignment(self, assignment: DiaristAssignment) -> DiaristAssignment:
        """Cria uma alocação."""
        self.db.add(assignment)
        await self.db.commit()
        await self.db.refresh(assignment)
        return assignment

    async def get_assignment_by_id(self, assignment_id: UUID) -> DiaristAssignment | None:
        """Busca alocação por ID."""
        result = await self.db.execute(
            select(DiaristAssignment)
            .options(joinedload(DiaristAssignment.diarist))
            .where(DiaristAssignment.id == assignment_id)
        )
        return result.scalars().first()

    async def list_assignments(
        self,
        diarist_id: UUID | None = None,
        condominio_id: UUID | None = None,
        status: AssignmentStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[DiaristAssignment]:
        """Lista alocações com filtros."""
        query = select(DiaristAssignment).options(joinedload(DiaristAssignment.diarist))

        if diarist_id:
            query = query.where(DiaristAssignment.diarist_id == diarist_id)

        if condominio_id:
            query = query.where(DiaristAssignment.condominio_id == condominio_id)

        if status:
            query = query.where(DiaristAssignment.status == status)

        result = await self.db.execute(query.order_by(DiaristAssignment.created_at.desc()).offset(skip).limit(limit))
        return list(result.scalars().all())

    async def update_assignment(self, assignment: DiaristAssignment) -> DiaristAssignment:
        """Atualiza alocação."""
        await self.db.commit()
        await self.db.refresh(assignment)
        return assignment

    async def cancel_assignment(self, assignment_id: UUID) -> bool:
        """Cancela uma alocação."""
        assignment = await self.get_assignment_by_id(assignment_id)
        if assignment:
            assignment.status = AssignmentStatus.CANCELADO
            await self.db.commit()
            return True
        return False

    # ==================== SCHEDULE CRUD ====================

    async def create_schedule(self, schedule: DiaristSchedule) -> DiaristSchedule:
        """Cria um agendamento."""
        self.db.add(schedule)
        await self.db.commit()
        await self.db.refresh(schedule)
        return schedule

    async def get_schedule_by_id(self, schedule_id: UUID) -> DiaristSchedule | None:
        """Busca agendamento por ID."""
        result = await self.db.execute(
            select(DiaristSchedule)
            .options(
                joinedload(DiaristSchedule.diarist),
                joinedload(DiaristSchedule.assignment),
            )
            .where(DiaristSchedule.id == schedule_id)
        )
        return result.scalars().first()

    async def list_schedules(
        self,
        diarist_id: UUID | None = None,
        condominio_id: UUID | None = None,
        data_inicio: date | None = None,
        data_fim: date | None = None,
        status: ScheduleStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[DiaristSchedule]:
        """Lista agendamentos com filtros."""
        query = select(DiaristSchedule).options(joinedload(DiaristSchedule.diarist))

        if diarist_id:
            query = query.where(DiaristSchedule.diarist_id == diarist_id)

        if condominio_id:
            query = query.where(DiaristSchedule.condominio_id == condominio_id)

        if data_inicio:
            query = query.where(DiaristSchedule.data_trabalho >= data_inicio)

        if data_fim:
            query = query.where(DiaristSchedule.data_trabalho <= data_fim)

        if status:
            status_str = status.value if hasattr(status, "value") else str(status)
            query = query.where(cast(DiaristSchedule.status, String) == status_str)

        query = query.order_by(DiaristSchedule.data_trabalho.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_schedules_by_date(
        self,
        data: date,
        condominio_id: UUID | None = None,
    ) -> list[DiaristSchedule]:
        """Busca agendamentos de uma data específica."""
        query = (
            select(DiaristSchedule)
            .options(joinedload(DiaristSchedule.diarist))
            .where(DiaristSchedule.data_trabalho == data)
        )

        if condominio_id:
            query = query.where(DiaristSchedule.condominio_id == condominio_id)

        result = await self.db.execute(query.order_by(DiaristSchedule.hora_inicio))
        return list(result.scalars().all())

    async def update_schedule(self, schedule: DiaristSchedule) -> DiaristSchedule:
        """Atualiza agendamento."""
        await self.db.commit()
        await self.db.refresh(schedule)
        return schedule

    async def register_checkin(
        self,
        schedule_id: UUID,
        hora_checkin: datetime,
        latitude: Decimal | None = None,
        longitude: Decimal | None = None,
    ) -> DiaristSchedule | None:
        """Registra check-in."""
        schedule = await self.get_schedule_by_id(schedule_id)
        if schedule and schedule.status in [
            ScheduleStatus.AGENDADO,
            ScheduleStatus.CONFIRMADO,
        ]:
            schedule.checkin_real = hora_checkin
            schedule.checkin_latitude = latitude
            schedule.checkin_longitude = longitude
            schedule.status = ScheduleStatus.EM_ANDAMENTO
            await self.db.commit()
            await self.db.refresh(schedule)
            return schedule
        return None

    async def register_checkout(
        self,
        schedule_id: UUID,
        hora_checkout: datetime,
        latitude: Decimal | None = None,
        longitude: Decimal | None = None,
    ) -> DiaristSchedule | None:
        """Registra check-out."""
        schedule = await self.get_schedule_by_id(schedule_id)
        if schedule and schedule.status == ScheduleStatus.EM_ANDAMENTO:
            schedule.checkout_real = hora_checkout
            schedule.checkout_latitude = latitude
            schedule.checkout_longitude = longitude
            schedule.status = ScheduleStatus.CONCLUIDO
            await self.db.commit()
            await self.db.refresh(schedule)
            return schedule
        return None

    # ==================== PAYMENT CRUD ====================

    async def create_payment(self, payment: DiaristPayment) -> DiaristPayment:
        """Cria um pagamento."""
        self.db.add(payment)
        await self.db.commit()
        await self.db.refresh(payment)
        return payment

    async def get_payment_by_id(self, payment_id: UUID) -> DiaristPayment | None:
        """Busca pagamento por ID."""
        result = await self.db.execute(
            select(DiaristPayment).options(joinedload(DiaristPayment.diarist)).where(DiaristPayment.id == payment_id)
        )
        return result.scalars().first()

    async def list_payments(
        self,
        diarist_id: UUID | None = None,
        condominio_id: UUID | None = None,
        status: PaymentStatus | None = None,
        data_inicio: date | None = None,
        data_fim: date | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[DiaristPayment]:
        """Lista pagamentos com filtros."""
        query = select(DiaristPayment).options(joinedload(DiaristPayment.diarist))

        if diarist_id:
            query = query.where(DiaristPayment.diarist_id == diarist_id)

        if condominio_id:
            query = query.where(DiaristPayment.condominio_id == condominio_id)

        if status:
            query = query.where(DiaristPayment.status == status)

        if data_inicio:
            query = query.where(DiaristPayment.data_referencia >= data_inicio)

        if data_fim:
            query = query.where(DiaristPayment.data_referencia <= data_fim)

        query = query.order_by(DiaristPayment.data_referencia.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_pending_payments(
        self,
        condominio_id: UUID | None = None,
    ) -> list[DiaristPayment]:
        """Busca pagamentos pendentes."""
        query = (
            select(DiaristPayment)
            .options(joinedload(DiaristPayment.diarist))
            .where(DiaristPayment.status == PaymentStatus.PENDENTE)
        )

        if condominio_id:
            query = query.where(DiaristPayment.condominio_id == condominio_id)

        result = await self.db.execute(query.order_by(DiaristPayment.data_vencimento))
        return list(result.scalars().all())

    async def update_payment(self, payment: DiaristPayment) -> DiaristPayment:
        """Atualiza pagamento."""
        await self.db.commit()
        await self.db.refresh(payment)
        return payment

    async def mark_payment_as_paid(
        self,
        payment_id: UUID,
        data_pagamento: date,
        comprovante: str | None = None,
    ) -> DiaristPayment | None:
        """Marca pagamento como pago."""
        payment = await self.get_payment_by_id(payment_id)
        if payment and payment.status == PaymentStatus.PENDENTE:
            payment.status = PaymentStatus.PAGO
            payment.data_pagamento = data_pagamento
            payment.comprovante_url = comprovante
            await self.db.commit()
            await self.db.refresh(payment)
            return payment
        return None

    # ==================== EVALUATION CRUD ====================

    async def create_evaluation(self, evaluation: DiaristEvaluation) -> DiaristEvaluation:
        """Cria uma avaliação."""
        self.db.add(evaluation)
        await self.db.commit()
        await self.db.refresh(evaluation)

        # Atualizar média da diarista
        await self._update_diarist_rating(evaluation.diarist_id)

        return evaluation

    async def get_evaluation_by_id(self, evaluation_id: UUID) -> DiaristEvaluation | None:
        """Busca avaliação por ID."""
        result = await self.db.execute(select(DiaristEvaluation).where(DiaristEvaluation.id == evaluation_id))
        return result.scalars().first()

    async def list_evaluations(
        self,
        diarist_id: UUID | None = None,
        schedule_id: UUID | None = None,
        nota_minima: int | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[DiaristEvaluation]:
        """Lista avaliações com filtros."""
        query = select(DiaristEvaluation)

        if diarist_id:
            query = query.where(DiaristEvaluation.diarist_id == diarist_id)

        if schedule_id:
            query = query.where(DiaristEvaluation.schedule_id == schedule_id)

        if nota_minima:
            query = query.where(DiaristEvaluation.nota_geral >= nota_minima)

        query = query.order_by(DiaristEvaluation.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_evaluation_by_schedule(self, schedule_id: UUID) -> DiaristEvaluation | None:
        """Busca avaliação de um agendamento."""
        result = await self.db.execute(select(DiaristEvaluation).where(DiaristEvaluation.schedule_id == schedule_id))
        return result.scalars().first()

    async def _update_diarist_rating(self, diarist_id: UUID) -> None:
        """Atualiza média de avaliação da diarista."""
        result = await self.db.execute(
            select(
                func.avg(DiaristEvaluation.nota_geral).label("media"),
                func.count(DiaristEvaluation.id).label("total"),
            ).where(DiaristEvaluation.diarist_id == diarist_id)
        )
        row = result.first()

        if row and row.media:
            diarist_result = await self.db.execute(select(Diarist).where(Diarist.id == diarist_id))
            diarist = diarist_result.scalars().first()
            if diarist:
                diarist.avaliacao_media = Decimal(str(row.media))
                diarist.total_avaliacoes = row.total
                await self.db.commit()

    # ==================== MÉTRICAS E ESTATÍSTICAS ====================

    async def get_diarist_metrics(
        self,
        diarist_id: UUID,
        data_inicio: date | None = None,
        data_fim: date | None = None,
    ) -> dict:
        """Calcula métricas da diarista."""
        if not data_inicio:
            data_inicio = date.today() - timedelta(days=30)
        if not data_fim:
            data_fim = date.today()

        # Agendamentos no período
        schedules_result = await self.db.execute(
            select(DiaristSchedule).where(
                DiaristSchedule.diarist_id == diarist_id,
                DiaristSchedule.data_trabalho >= data_inicio,
                DiaristSchedule.data_trabalho <= data_fim,
            )
        )
        schedules = list(schedules_result.scalars().all())

        total_agendamentos = len(schedules)
        concluidos = sum(1 for s in schedules if s.status == ScheduleStatus.CONCLUIDO)
        cancelados = sum(1 for s in schedules if s.status == ScheduleStatus.CANCELADO)

        # Horas trabalhadas — DiaristSchedule NÃO tem coluna/atributo
        # horas_trabalhadas; o real é a property duracao_minutos
        # (checkin_real/checkout_real). Sem check-in/out registrado → 0.
        horas_trabalhadas = sum(
            (Decimal(s.duracao_minutos) / Decimal(60))
            for s in schedules
            if s.status == ScheduleStatus.CONCLUIDO and s.duracao_minutos is not None
        ) or Decimal("0")

        # Taxa de pontualidade
        pontuais = sum(1 for s in schedules if s.teve_checkin)
        taxa_pontualidade = (pontuais / concluidos * 100) if concluidos > 0 else 0

        # Pagamentos
        pagamentos_result = await self.db.execute(
            select(func.sum(DiaristPayment.valor_liquido)).where(
                DiaristPayment.diarist_id == diarist_id,
                DiaristPayment.data_referencia >= data_inicio,
                DiaristPayment.data_referencia <= data_fim,
                DiaristPayment.status == PaymentStatus.PAGO,
            )
        )
        pagamentos = pagamentos_result.scalar() or Decimal("0")

        return {
            "periodo": {"inicio": data_inicio, "fim": data_fim},
            "agendamentos": {
                "total": total_agendamentos,
                "concluidos": concluidos,
                "cancelados": cancelados,
                "taxa_conclusao": (concluidos / total_agendamentos * 100 if total_agendamentos > 0 else 0),
            },
            "horas_trabalhadas": float(horas_trabalhadas),
            "taxa_pontualidade": round(taxa_pontualidade, 1),
            "valor_recebido": float(pagamentos),
        }

    async def get_condominio_statistics(
        self,
        condominio_id: UUID | None = None,
        data_inicio: date | None = None,
        data_fim: date | None = None,
    ) -> dict:
        """Estatísticas de diaristas (global ou por condomínio)."""
        if not data_inicio:
            data_inicio = date.today() - timedelta(days=30)
        if not data_fim:
            data_fim = date.today()

        # Total de diaristas ativas.
        # Sem condominio_id (visão geral), contar direto na tabela diarists —
        # contar via diarist_assignments (tabela sem vínculos ativos) dava
        # total_diaristas=0 com 5 diaristas ativas reais no banco.
        if condominio_id:
            diaristas_query = select(func.count(func.distinct(DiaristAssignment.diarist_id))).where(
                DiaristAssignment.ativo.is_(True),
                DiaristAssignment.condominio_id == condominio_id,
            )
        else:
            diaristas_query = select(func.count(Diarist.id)).where(
                Diarist.ativo.is_(True),
                Diarist.status == DiaristStatus.ATIVO.value,
            )
        diaristas_result = await self.db.execute(diaristas_query)
        total_diaristas = diaristas_result.scalar() or 0

        # Agendamentos
        schedules_query = select(DiaristSchedule).where(
            DiaristSchedule.data_trabalho >= data_inicio,
            DiaristSchedule.data_trabalho <= data_fim,
        )
        if condominio_id:
            schedules_query = schedules_query.where(DiaristSchedule.condominio_id == condominio_id)
        schedules_result = await self.db.execute(schedules_query)
        schedules = list(schedules_result.scalars().all())

        total_agendamentos = len(schedules)
        concluidos = sum(1 for s in schedules if s.status == ScheduleStatus.CONCLUIDO)

        # Gastos
        gastos_query = select(func.sum(DiaristPayment.valor_liquido)).where(
            DiaristPayment.data_referencia >= data_inicio,
            DiaristPayment.data_referencia <= data_fim,
        )
        if condominio_id:
            gastos_query = gastos_query.where(DiaristPayment.condominio_id == condominio_id)
        gastos_result = await self.db.execute(gastos_query)
        gastos = gastos_result.scalar() or Decimal("0")

        # Média de avaliações
        eval_query = (
            select(func.avg(DiaristEvaluation.nota_geral))
            .join(DiaristSchedule)
            .where(
                DiaristSchedule.data_trabalho >= data_inicio,
                DiaristSchedule.data_trabalho <= data_fim,
            )
        )
        if condominio_id:
            eval_query = eval_query.where(DiaristSchedule.condominio_id == condominio_id)
        media_result = await self.db.execute(eval_query)
        media_avaliacoes = media_result.scalar()

        return {
            "periodo": {"inicio": data_inicio, "fim": data_fim},
            "total_diaristas": total_diaristas,
            "agendamentos": {
                "total": total_agendamentos,
                "concluidos": concluidos,
                "taxa_conclusao": (concluidos / total_agendamentos * 100 if total_agendamentos > 0 else 0),
            },
            "gastos_total": float(gastos),
            "media_avaliacoes": round(float(media_avaliacoes or 0), 2),
        }

    async def get_top_diarists(
        self,
        condominio_id: UUID | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Retorna ranking das melhores diaristas."""
        query = (
            select(
                Diarist,
                func.count(DiaristSchedule.id).label("total_servicos"),
            )
            .join(DiaristSchedule)
            .where(
                Diarist.status == DiaristStatus.ATIVO,
                cast(DiaristSchedule.status, String) == "CONCLUIDO",
            )
            .group_by(Diarist.id)
        )

        if condominio_id:
            query = query.where(DiaristSchedule.condominio_id == condominio_id)

        query = query.order_by(
            Diarist.avaliacao_media.desc(),
            func.count(DiaristSchedule.id).desc(),
        ).limit(limit)

        results_exec = await self.db.execute(query)
        results = results_exec.all()

        return [
            {
                "diarist": diarist,
                "total_servicos": total,
                "avaliacao_media": float(diarist.avaliacao_media or 0),
            }
            for diarist, total in results
        ]
