"""
Service PCMSO (NR-7) - Programa de Controle Medico de Saude Ocupacional
=======================================================================

Logica de negocio para exames medicos e ASO.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from modules.health_occupational.models.pcmso import (
    ASO,
    ComplementaryExam,
    ExamStatus,
    MedicalExam,
)
from modules.health_occupational.schemas.pcmso import (
    ASORequest,
    ASOUpdateRequest,
    ComplementaryExamRequest,
    MedicalExamRequest,
    MedicalExamUpdateRequest,
)

logger = logging.getLogger(__name__)


class PCMSOService:
    """Service para gerenciamento de exames medicos (PCMSO - NR-7)."""

    def __init__(self, db: Session | None = None):
        self.db = db

    # ==========================================================================
    # Medical Exam Operations
    # ==========================================================================

    def schedule_exam(self, request: MedicalExamRequest, created_by: UUID | None = None) -> MedicalExam:
        """
        Agenda exame medico ocupacional.

        Args:
            request: Dados do agendamento.
            created_by: UUID do usuario que criou.

        Returns:
            MedicalExam: Exame agendado.
        """
        exam = MedicalExam(
            funcionario_id=request.funcionario_id,
            tipo_exame=request.tipo_exame,
            status=ExamStatus.AGENDADO.value,
            funcao=request.funcao,
            setor=request.setor,
            riscos=request.riscos,
            data_agendamento=request.data_agendamento,
            hora_agendamento=request.hora_agendamento,
            local_realizacao=request.local_realizacao,
            exames_complementares=request.exames_complementares,
            observacoes=request.observacoes,
            created_by=created_by,
        )

        self.db.add(exam)
        self.db.commit()
        self.db.refresh(exam)

        # Publish event (fire-and-forget, non-blocking)
        try:
            import asyncio

            from infrastructure.message_bus.events import Event, EventType, publish_event

            event = Event(
                type=EventType.EXAME_AGENDADO,
                source="health_occupational.pcmso_service",
                data={
                    "exame_id": str(exam.id),
                    "funcionario_id": str(exam.funcionario_id),
                    "tipo_exame": exam.tipo_exame,
                    "data_agendamento": exam.data_agendamento.isoformat() if exam.data_agendamento else None,
                    "funcao": exam.funcao,
                    "setor": exam.setor,
                },
            )
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(publish_event(event))
            else:
                asyncio.run(publish_event(event))
        except Exception as _pub_err:
            logger.warning("Falha ao publicar evento EXAME_AGENDADO: %s", _pub_err)

        logger.info(
            "Exame agendado: funcionario=%s, tipo=%s, data=%s",
            request.funcionario_id,
            request.tipo_exame,
            request.data_agendamento,
        )

        return exam

    def update_exam(self, exam_id: UUID, request: MedicalExamUpdateRequest) -> MedicalExam | None:
        """
        Atualiza exame medico.

        Args:
            exam_id: ID do exame.
            request: Dados para atualizacao.

        Returns:
            MedicalExam atualizado ou None se nao encontrado.
        """
        exam = self.db.query(MedicalExam).filter(MedicalExam.id == exam_id).first()
        if not exam:
            return None

        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(exam, field, value)

        self.db.commit()
        self.db.refresh(exam)

        logger.info("Exame atualizado: id=%s", exam_id)
        return exam

    def get_exam(self, exam_id: UUID) -> MedicalExam | None:
        """Busca exame por ID."""
        return self.db.query(MedicalExam).filter(MedicalExam.id == exam_id).first()

    def list_employee_exams(
        self,
        funcionario_id: UUID,
        status_filter: str | None = None,
        tipo_filter: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> dict[str, Any]:
        """
        Lista exames de um funcionario.

        Args:
            funcionario_id: UUID do funcionario.
            status_filter: Filtro por status.
            tipo_filter: Filtro por tipo.
            page: Pagina.
            size: Itens por pagina.

        Returns:
            Dict com exames e metadados.
        """
        query = self.db.query(MedicalExam).filter(MedicalExam.funcionario_id == funcionario_id)

        if status_filter:
            query = query.filter(MedicalExam.status == status_filter)

        if tipo_filter:
            query = query.filter(MedicalExam.tipo_exame == tipo_filter)

        total = query.count()
        exams = query.order_by(MedicalExam.data_agendamento.desc()).offset((page - 1) * size).limit(size).all()

        return {
            "items": exams,
            "total": total,
            "page": page,
            "size": size,
        }

    def list_pending_exams(self, days_ahead: int = 30) -> list[MedicalExam]:
        """Lista exames pendentes nos proximos dias."""
        limit_date = date.today() + timedelta(days=days_ahead)

        return (
            self.db.query(MedicalExam)
            .filter(
                MedicalExam.status.in_([ExamStatus.AGENDADO.value, ExamStatus.CONFIRMADO.value]),
                MedicalExam.data_agendamento <= limit_date,
            )
            .order_by(MedicalExam.data_agendamento)
            .all()
        )

    def confirm_exam(self, exam_id: UUID) -> MedicalExam | None:
        """Confirma agendamento de exame."""
        exam = self.get_exam(exam_id)
        if not exam:
            return None

        exam.status = ExamStatus.CONFIRMADO.value
        self.db.commit()
        self.db.refresh(exam)
        return exam

    def complete_exam(self, exam_id: UUID) -> MedicalExam | None:
        """Marca exame como realizado."""
        exam = self.get_exam(exam_id)
        if not exam:
            return None

        exam.status = ExamStatus.REALIZADO.value
        exam.data_realizacao = datetime.utcnow()
        self.db.commit()
        self.db.refresh(exam)
        return exam

    def cancel_exam(self, exam_id: UUID, motivo: str | None = None) -> MedicalExam | None:
        """Cancela exame."""
        exam = self.get_exam(exam_id)
        if not exam:
            return None

        exam.status = ExamStatus.CANCELADO.value
        if motivo:
            exam.observacoes = f"{exam.observacoes or ''}\nCancelado: {motivo}".strip()

        self.db.commit()
        self.db.refresh(exam)
        return exam

    # ==========================================================================
    # ASO Operations
    # ==========================================================================

    def emit_aso(self, request: ASORequest) -> ASO:
        """
        Emite ASO (Atestado de Saude Ocupacional).

        Args:
            request: Dados do ASO.

        Returns:
            ASO emitido.

        Raises:
            ValueError: Se exame nao encontrado ou invalido.
        """
        exam = self.get_exam(request.exame_id)
        if not exam:
            raise ValueError(f"Exame {request.exame_id} nao encontrado")

        if exam.status != ExamStatus.REALIZADO.value:
            raise ValueError("Exame deve estar realizado para emitir ASO")

        # Verificar se ja existe ASO para este exame
        existing = self.db.query(ASO).filter(ASO.exame_id == request.exame_id).first()
        if existing:
            raise ValueError("ASO ja emitido para este exame")

        # Calcular data de vencimento
        data_vencimento = date.today() + timedelta(days=request.validade_dias)

        # Gerar numero do ASO
        numero_aso = self._generate_aso_number()

        aso = ASO(
            exame_id=request.exame_id,
            resultado=request.resultado,
            restricoes=request.restricoes or [],
            validade_dias=request.validade_dias,
            data_vencimento=data_vencimento,
            medico_responsavel=request.medico_responsavel,
            crm=request.crm,
            uf_crm=request.uf_crm,
            numero_aso=numero_aso,
            assinatura_medico=True,
        )

        self.db.add(aso)
        self.db.commit()
        self.db.refresh(aso)

        try:
            import asyncio

            from infrastructure.message_bus.events import Event, EventType, publish_event

            event = Event(
                type=EventType.ASO_EMITIDO,
                source="health_occupational.pcmso_service",
                data={
                    "aso_id": str(aso.id),
                    "exame_id": str(aso.exame_id),
                    "numero_aso": aso.numero_aso,
                    "resultado": aso.resultado,
                    "data_vencimento": aso.data_vencimento.isoformat() if aso.data_vencimento else None,
                },
            )
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(publish_event(event))
            else:
                asyncio.run(publish_event(event))
        except Exception as _pub_err:
            logger.warning("Falha ao publicar evento ASO_EMITIDO: %s", _pub_err)

        logger.info(
            "ASO emitido: numero=%s, exame=%s, resultado=%s",
            numero_aso,
            request.exame_id,
            request.resultado,
        )

        return aso

    def get_aso(self, aso_id: UUID) -> ASO | None:
        """Busca ASO por ID."""
        return self.db.query(ASO).filter(ASO.id == aso_id).first()

    def get_aso_by_exam(self, exam_id: UUID) -> ASO | None:
        """Busca ASO pelo exame."""
        return self.db.query(ASO).filter(ASO.exame_id == exam_id).first()

    def list_expiring_asos(self, days: int = 30) -> list[dict[str, Any]]:
        """
        Lista ASOs com vencimento proximo.

        Args:
            days: Dias de antecedencia.

        Returns:
            Lista de ASOs a vencer.
        """
        if not self.db:
            return []

        from sqlalchemy import text

        try:
            rows = self.db.execute(
                text(
                    "SELECT a.id as aso_id, e.funcionario_id, a.resultado, "
                    "a.data_vencimento, a.medico_responsavel, a.crm, e.tipo_exame "
                    "FROM health_asos a "
                    "JOIN health_medical_exams e ON a.exame_id = e.id "
                    "WHERE a.ativo = true AND a.cancelado = false "
                    "AND a.data_vencimento BETWEEN current_date AND current_date + :days * interval '1 day' "
                    "ORDER BY a.data_vencimento"
                ),
                {"days": days},
            ).fetchall()

            return [
                {
                    "aso_id": str(row.aso_id),
                    "funcionario_id": str(row.funcionario_id),
                    "resultado": row.resultado,
                    "data_vencimento": row.data_vencimento.isoformat() if row.data_vencimento else None,
                    "medico": row.medico_responsavel,
                    "crm": row.crm,
                    "tipo_exame": row.tipo_exame,
                }
                for row in rows
            ]
        except Exception as e:
            logger.error("Erro ao listar ASOs vencendo: %s", e)
            return []

    def update_aso(self, aso_id: UUID, request: ASOUpdateRequest) -> ASO | None:
        """Atualiza ASO."""
        aso = self.get_aso(aso_id)
        if not aso:
            return None

        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(aso, field, value)

        if request.assinatura_funcionario:
            aso.data_assinatura_funcionario = datetime.utcnow()

        self.db.commit()
        self.db.refresh(aso)
        return aso

    def cancel_aso(self, aso_id: UUID, motivo: str) -> ASO | None:
        """Cancela ASO."""
        aso = self.get_aso(aso_id)
        if not aso:
            return None

        aso.cancelado = True
        aso.ativo = False
        aso.motivo_cancelamento = motivo

        self.db.commit()
        self.db.refresh(aso)

        logger.info("ASO cancelado: id=%s, motivo=%s", aso_id, motivo)
        return aso

    def _generate_aso_number(self) -> str:
        """Gera numero sequencial de ASO."""
        year = date.today().year
        count = self.db.query(ASO).filter(ASO.data_emissao >= datetime(year, 1, 1)).count()
        return f"ASO-{year}-{count + 1:06d}"

    # ==========================================================================
    # Complementary Exam Operations
    # ==========================================================================

    def add_complementary_exam(self, request: ComplementaryExamRequest) -> ComplementaryExam:
        """Adiciona exame complementar."""
        exam = ComplementaryExam(
            exame_principal_id=request.exame_principal_id,
            nome=request.nome,
            codigo=request.codigo,
            laboratorio=request.laboratorio,
        )

        self.db.add(exam)
        self.db.commit()
        self.db.refresh(exam)
        return exam

    def list_complementary_exams(self, exam_id: UUID) -> list[ComplementaryExam]:
        """Lista exames complementares de um exame principal."""
        return self.db.query(ComplementaryExam).filter(ComplementaryExam.exame_principal_id == exam_id).all()

    # ==========================================================================
    # Statistics
    # ==========================================================================

    def get_statistics(self) -> dict[str, Any]:
        """Retorna estatisticas do PCMSO."""
        if not self.db:
            return {
                "total_exames_ano": 0,
                "exames_pendentes": 0,
                "exames_realizados": 0,
                "asos_vencendo_30_dias": 0,
            }

        from sqlalchemy import text

        try:
            total_exams = (
                self.db.execute(
                    text(
                        "SELECT count(*) FROM gp_asos WHERE extract(year from data_agendamento) = extract(year from current_date)"
                    )
                ).scalar()
                or 0
            )

            pending_exams = (
                self.db.execute(
                    text("SELECT count(*) FROM gp_asos WHERE status IN ('agendado', 'confirmado')")
                ).scalar()
                or 0
            )

            completed_exams = (
                self.db.execute(
                    text(
                        "SELECT count(*) FROM gp_asos WHERE status = 'realizado' AND extract(year from data_realizacao) = extract(year from current_date)"
                    )
                ).scalar()
                or 0
            )

            expiring_asos = (
                self.db.execute(
                    text(
                        "SELECT count(*) FROM gp_asos WHERE data_validade BETWEEN current_date AND current_date + interval '30 days'"
                    )
                ).scalar()
                or 0
            )

            return {
                "total_exames_ano": total_exams,
                "exames_pendentes": pending_exams,
                "exames_realizados": completed_exams,
                "asos_vencendo_30_dias": expiring_asos,
            }
        except Exception as e:
            logger.error("Erro ao consultar estatisticas PCMSO: %s", e)
            return {
                "total_exames_ano": 0,
                "exames_pendentes": 0,
                "exames_realizados": 0,
                "asos_vencendo_30_dias": 0,
            }
