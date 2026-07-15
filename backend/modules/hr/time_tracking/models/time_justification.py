"""Modelo TimeJustification - Justificativas de Ponto.

Gerencia justificativas para atrasos, faltas, saídas antecipadas
e outras ocorrências relacionadas ao ponto eletrônico.
"""

import uuid
from datetime import date, datetime, time, timedelta
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class JustificationType(StrEnum):
    """Tipo de justificativa."""

    ATRASO = "atraso"
    SAIDA_ANTECIPADA = "saida_antecipada"
    FALTA = "falta"
    FALTA_PARCIAL = "falta_parcial"
    ESQUECIMENTO_MARCACAO = "esquecimento_marcacao"
    PROBLEMA_BIOMETRIA = "problema_biometria"
    PROBLEMA_SISTEMA = "problema_sistema"
    TRABALHO_EXTERNO = "trabalho_externo"
    REUNIAO_EXTERNA = "reuniao_externa"
    TREINAMENTO = "treinamento"
    CONSULTA_MEDICA = "consulta_medica"
    EXAME = "exame"
    ACOMPANHAMENTO_FAMILIAR = "acompanhamento_familiar"
    LICENCA_MEDICA = "licenca_medica"
    LICENCA_MATERNIDADE = "licenca_maternidade"
    LICENCA_PATERNIDADE = "licenca_paternidade"
    LICENCA_CASAMENTO = "licenca_casamento"
    LICENCA_OBITO = "licenca_obito"
    LICENCA_DOACAO_SANGUE = "licenca_doacao_sangue"
    LICENCA_ELEITORAL = "licenca_eleitoral"
    ACIDENTE_TRABALHO = "acidente_trabalho"
    TRANSPORTE = "transporte"
    INTEMPERIE = "intemperie"
    OUTRO = "outro"


class JustificationStatus(StrEnum):
    """Status da justificativa."""

    RASCUNHO = "rascunho"
    PENDENTE = "pendente"
    EM_ANALISE = "em_analise"
    APROVADA = "aprovada"
    APROVADA_PARCIAL = "aprovada_parcial"
    REJEITADA = "rejeitada"
    CANCELADA = "cancelada"
    EXPIRADA = "expirada"


class JustificationCategory(StrEnum):
    """Categoria da justificativa."""

    PESSOAL = "pessoal"
    SAUDE = "saude"
    TRABALHO = "trabalho"
    LEGAL = "legal"
    SISTEMA = "sistema"
    OUTRO = "outro"


class TimeJustification(Base):
    """Modelo de Justificativa de Ponto.

    Permite ao funcionário justificar ocorrências no ponto,
    como atrasos, faltas e esquecimentos de marcação.
    """

    __tablename__ = "time_justifications"

    # Identificação
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)

    # Funcionário
    employee_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    employee_name: Mapped[str] = mapped_column(String(200), nullable=False)
    employee_registration: Mapped[str | None] = mapped_column(String(50))
    department_id: Mapped[str | None] = mapped_column(String(50))
    department_name: Mapped[str | None] = mapped_column(String(100))

    # Tipo e status
    justification_type: Mapped[JustificationType] = mapped_column(String(40), default=JustificationType.OUTRO)
    category: Mapped[JustificationCategory] = mapped_column(String(20), default=JustificationCategory.PESSOAL)
    status: Mapped[JustificationStatus] = mapped_column(String(20), default=JustificationStatus.PENDENTE)

    # Período
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    is_full_day: Mapped[bool] = mapped_column(Boolean, default=True)
    days_count: Mapped[int] = mapped_column(Integer, default=1)
    hours_count: Mapped[int] = mapped_column(Integer, default=0)  # Em minutos
    minutes_justified: Mapped[int] = mapped_column(Integer, default=0)

    # Descrição
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    detailed_reason: Mapped[str | None] = mapped_column(Text)

    # Documentos anexos
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False)
    attachments: Mapped[list[dict] | None] = mapped_column(JSONB, default=list)
    # Formato: [{"name": "atestado.pdf", "url": "...", "type": "application/pdf", "size": 12345}]

    # CID (para atestados médicos)
    cid_code: Mapped[str | None] = mapped_column(String(10))
    cid_description: Mapped[str | None] = mapped_column(String(200))
    medical_certificate_number: Mapped[str | None] = mapped_column(String(50))
    doctor_name: Mapped[str | None] = mapped_column(String(200))
    doctor_crm: Mapped[str | None] = mapped_column(String(20))
    clinic_name: Mapped[str | None] = mapped_column(String(200))

    # Registros de ponto vinculados
    time_entry_ids: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=list)

    # Análise
    analyzed_by_id: Mapped[str | None] = mapped_column(String(50))
    analyzed_by_name: Mapped[str | None] = mapped_column(String(200))
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Aprovação
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_by_id: Mapped[str | None] = mapped_column(String(50))
    approved_by_name: Mapped[str | None] = mapped_column(String(200))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    approval_notes: Mapped[str | None] = mapped_column(Text)

    # Aprovação em níveis
    approval_level: Mapped[int] = mapped_column(Integer, default=1)
    max_approval_level: Mapped[int] = mapped_column(Integer, default=1)
    # Formato: [{"level": 1, "approver_id": "...", "approver_name": "...",
    #            "status": "approved", "at": "..."}]
    approval_history: Mapped[list[dict] | None] = mapped_column(JSONB, default=list)

    # Rejeição
    rejected_by_id: Mapped[str | None] = mapped_column(String(50))
    rejected_by_name: Mapped[str | None] = mapped_column(String(200))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime)
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    # Aprovação parcial
    partial_approved_days: Mapped[int | None] = mapped_column(Integer)
    partial_approved_minutes: Mapped[int | None] = mapped_column(Integer)
    partial_approval_notes: Mapped[str | None] = mapped_column(Text)

    # Recorrência (para justificativas que se repetem)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence_pattern: Mapped[str | None] = mapped_column(String(50))
    recurrence_end_date: Mapped[date | None] = mapped_column(Date)
    parent_justification_id: Mapped[str | None] = mapped_column(String(50))

    # Abono
    grants_paid_leave: Mapped[bool] = mapped_column(Boolean, default=False)
    affects_dsr: Mapped[bool] = mapped_column(Boolean, default=True)
    deducts_from_vacation: Mapped[bool] = mapped_column(Boolean, default=False)

    # Prazo
    deadline_for_submission: Mapped[datetime | None] = mapped_column(DateTime)
    is_late_submission: Mapped[bool] = mapped_column(Boolean, default=False)
    late_submission_days: Mapped[int] = mapped_column(Integer, default=0)

    # Verificação (para RH)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by_id: Mapped[str | None] = mapped_column(String(50))
    verified_by_name: Mapped[str | None] = mapped_column(String(200))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    verification_notes: Mapped[str | None] = mapped_column(Text)

    # Jornada
    work_schedule_id: Mapped[str | None] = mapped_column(String(50))

    # Local
    condominium_id: Mapped[str | None] = mapped_column(String(50), index=True)
    condominium_name: Mapped[str | None] = mapped_column(String(200))

    # Observações e metadados
    notes: Mapped[str | None] = mapped_column(Text)
    internal_notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSONB, default=list)
    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Controle
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_id: Mapped[str | None] = mapped_column(String(50))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Índices
    __table_args__ = (
        Index("ix_time_just_employee_date", "employee_id", "start_date"),
        Index("ix_time_just_status_date", "status", "start_date"),
        Index("ix_time_just_type_status", "justification_type", "status"),
    )

    def __init__(self, **kwargs) -> None:
        """Inicializa a justificativa."""
        super().__init__(**kwargs)
        if not self.code:
            self.code = self._generate_code()
        self._calculate_period()
        self._set_category()
        self._check_late_submission()

    def _generate_code(self) -> str:
        """Gera código único da justificativa."""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")[:16]
        return f"JUS-{timestamp}"

    def _calculate_period(self) -> None:
        """Calcula dias e horas do período."""
        if not self.start_date or not self.end_date:
            return

        delta = self.end_date - self.start_date
        self.days_count = delta.days + 1

        if not self.is_full_day and self.start_time and self.end_time:
            start_dt = datetime.combine(self.start_date, self.start_time)
            end_dt = datetime.combine(self.start_date, self.end_time)
            diff = end_dt - start_dt
            self.hours_count = int(diff.total_seconds() / 60)
            self.minutes_justified = self.hours_count

    def _set_category(self) -> None:
        """Define categoria baseada no tipo."""
        health_types = [
            JustificationType.CONSULTA_MEDICA,
            JustificationType.EXAME,
            JustificationType.LICENCA_MEDICA,
            JustificationType.ACIDENTE_TRABALHO,
            JustificationType.ACOMPANHAMENTO_FAMILIAR,
        ]
        legal_types = [
            JustificationType.LICENCA_MATERNIDADE,
            JustificationType.LICENCA_PATERNIDADE,
            JustificationType.LICENCA_CASAMENTO,
            JustificationType.LICENCA_OBITO,
            JustificationType.LICENCA_DOACAO_SANGUE,
            JustificationType.LICENCA_ELEITORAL,
        ]
        work_types = [
            JustificationType.TRABALHO_EXTERNO,
            JustificationType.REUNIAO_EXTERNA,
            JustificationType.TREINAMENTO,
        ]
        system_types = [
            JustificationType.PROBLEMA_BIOMETRIA,
            JustificationType.PROBLEMA_SISTEMA,
        ]

        if self.justification_type in health_types:
            self.category = JustificationCategory.SAUDE
        elif self.justification_type in legal_types:
            self.category = JustificationCategory.LEGAL
        elif self.justification_type in work_types:
            self.category = JustificationCategory.TRABALHO
        elif self.justification_type in system_types:
            self.category = JustificationCategory.SISTEMA
        else:
            self.category = JustificationCategory.PESSOAL

    def _check_late_submission(self) -> None:
        """Verifica se é submissão tardia."""
        if not self.start_date:
            return

        # Prazo padrão: 48h após a ocorrência
        deadline = datetime.combine(self.start_date, time(23, 59)) + timedelta(hours=48)

        self.deadline_for_submission = deadline

        if datetime.utcnow() > deadline:
            self.is_late_submission = True
            delta = datetime.utcnow() - deadline
            self.late_submission_days = delta.days

    def submit(self) -> None:
        """Submete a justificativa para aprovação."""
        self.status = JustificationStatus.PENDENTE
        self.submitted_at = datetime.utcnow()
        self._check_late_submission()

    def start_analysis(
        self,
        analyzer_id: str,
        analyzer_name: str,
    ) -> None:
        """Inicia análise da justificativa.

        Args:
            analyzer_id: ID do analisador
            analyzer_name: Nome do analisador
        """
        self.status = JustificationStatus.EM_ANALISE
        self.analyzed_by_id = analyzer_id
        self.analyzed_by_name = analyzer_name
        self.analyzed_at = datetime.utcnow()

    def approve(
        self,
        approved_by_id: str,
        approved_by_name: str,
        notes: str = None,
    ) -> None:
        """Aprova a justificativa.

        Args:
            approved_by_id: ID do aprovador
            approved_by_name: Nome do aprovador
            notes: Observações
        """
        self.status = JustificationStatus.APROVADA
        self.approved_by_id = approved_by_id
        self.approved_by_name = approved_by_name
        self.approved_at = datetime.utcnow()
        self.approval_notes = notes

        # Registra no histórico
        if not self.approval_history:
            self.approval_history = []

        self.approval_history.append(
            {
                "level": self.approval_level,
                "approver_id": approved_by_id,
                "approver_name": approved_by_name,
                "status": "approved",
                "notes": notes,
                "at": datetime.utcnow().isoformat(),
            }
        )

    def approve_partial(
        self,
        approved_by_id: str,
        approved_by_name: str,
        approved_days: int = None,
        approved_minutes: int = None,
        notes: str = None,
    ) -> None:
        """Aprova parcialmente a justificativa.

        Args:
            approved_by_id: ID do aprovador
            approved_by_name: Nome do aprovador
            approved_days: Dias aprovados
            approved_minutes: Minutos aprovados
            notes: Observações
        """
        self.status = JustificationStatus.APROVADA_PARCIAL
        self.approved_by_id = approved_by_id
        self.approved_by_name = approved_by_name
        self.approved_at = datetime.utcnow()
        self.partial_approved_days = approved_days
        self.partial_approved_minutes = approved_minutes
        self.partial_approval_notes = notes

    def reject(
        self,
        rejected_by_id: str,
        rejected_by_name: str,
        reason: str,
    ) -> None:
        """Rejeita a justificativa.

        Args:
            rejected_by_id: ID de quem rejeitou
            rejected_by_name: Nome de quem rejeitou
            reason: Motivo da rejeição
        """
        self.status = JustificationStatus.REJEITADA
        self.rejected_by_id = rejected_by_id
        self.rejected_by_name = rejected_by_name
        self.rejected_at = datetime.utcnow()
        self.rejection_reason = reason

    def escalate(self) -> None:
        """Escalona para próximo nível de aprovação."""
        if self.approval_level < self.max_approval_level:
            self.approval_level += 1
            self.status = JustificationStatus.PENDENTE

    def verify(
        self,
        verified_by_id: str,
        verified_by_name: str,
        notes: str = None,
    ) -> None:
        """Verifica a justificativa (RH).

        Args:
            verified_by_id: ID do verificador
            verified_by_name: Nome do verificador
            notes: Observações
        """
        self.is_verified = True
        self.verified_by_id = verified_by_id
        self.verified_by_name = verified_by_name
        self.verified_at = datetime.utcnow()
        self.verification_notes = notes

    def add_attachment(
        self,
        name: str,
        url: str,
        file_type: str,
        size: int,
    ) -> None:
        """Adiciona anexo.

        Args:
            name: Nome do arquivo
            url: URL do arquivo
            file_type: Tipo MIME
            size: Tamanho em bytes
        """
        if not self.attachments:
            self.attachments = []

        self.attachments.append(
            {
                "name": name,
                "url": url,
                "type": file_type,
                "size": size,
                "uploaded_at": datetime.utcnow().isoformat(),
            }
        )
        self.has_attachments = True

    def set_medical_info(
        self,
        cid_code: str = None,
        cid_description: str = None,
        certificate_number: str = None,
        doctor_name: str = None,
        doctor_crm: str = None,
        clinic_name: str = None,
    ) -> None:
        """Define informações médicas.

        Args:
            cid_code: Código CID
            cid_description: Descrição do CID
            certificate_number: Número do atestado
            doctor_name: Nome do médico
            doctor_crm: CRM do médico
            clinic_name: Nome da clínica
        """
        self.cid_code = cid_code
        self.cid_description = cid_description
        self.medical_certificate_number = certificate_number
        self.doctor_name = doctor_name
        self.doctor_crm = doctor_crm
        self.clinic_name = clinic_name

    def link_time_entries(self, entry_ids: list[str]) -> None:
        """Vincula registros de ponto.

        Args:
            entry_ids: IDs dos registros de ponto
        """
        if not self.time_entry_ids:
            self.time_entry_ids = []
        self.time_entry_ids.extend(entry_ids)

    def cancel(self, reason: str = None) -> None:
        """Cancela a justificativa.

        Args:
            reason: Motivo do cancelamento
        """
        self.status = JustificationStatus.CANCELADA
        if reason:
            self.notes = f"Cancelada: {reason}"

    def soft_delete(self) -> None:
        """Soft delete da justificativa."""
        self.is_deleted = True
        self.status = JustificationStatus.CANCELADA

    @property
    def is_pending(self) -> bool:
        """Verifica se está pendente."""
        return self.status in [
            JustificationStatus.PENDENTE,
            JustificationStatus.EM_ANALISE,
        ]

    @property
    def is_approved(self) -> bool:
        """Verifica se está aprovada."""
        return self.status in [
            JustificationStatus.APROVADA,
            JustificationStatus.APROVADA_PARCIAL,
        ]

    @property
    def requires_medical_docs(self) -> bool:
        """Verifica se requer documentos médicos."""
        return self.justification_type in [
            JustificationType.CONSULTA_MEDICA,
            JustificationType.EXAME,
            JustificationType.LICENCA_MEDICA,
            JustificationType.ACIDENTE_TRABALHO,
        ]

    @property
    def is_legal_leave(self) -> bool:
        """Verifica se é licença legal."""
        return self.category == JustificationCategory.LEGAL

    @property
    def period_display(self) -> str:
        """Retorna período formatado."""
        if self.start_date == self.end_date:
            if self.is_full_day:
                return self.start_date.strftime("%d/%m/%Y")
            start_str = self.start_date.strftime("%d/%m/%Y")
            time_str = f"{self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')}"
            return f"{start_str} {time_str}"
        return f"{self.start_date.strftime('%d/%m/%Y')} a {self.end_date.strftime('%d/%m/%Y')}"

    @property
    def type_display(self) -> str:
        """Retorna tipo para exibição."""
        display_map = {
            JustificationType.ATRASO: "Atraso",
            JustificationType.SAIDA_ANTECIPADA: "Saída Antecipada",
            JustificationType.FALTA: "Falta",
            JustificationType.FALTA_PARCIAL: "Falta Parcial",
            JustificationType.ESQUECIMENTO_MARCACAO: "Esquecimento de Marcação",
            JustificationType.PROBLEMA_BIOMETRIA: "Problema Biometria",
            JustificationType.PROBLEMA_SISTEMA: "Problema do Sistema",
            JustificationType.TRABALHO_EXTERNO: "Trabalho Externo",
            JustificationType.REUNIAO_EXTERNA: "Reunião Externa",
            JustificationType.TREINAMENTO: "Treinamento",
            JustificationType.CONSULTA_MEDICA: "Consulta Médica",
            JustificationType.EXAME: "Exame",
            JustificationType.ACOMPANHAMENTO_FAMILIAR: "Acompanhamento Familiar",
            JustificationType.LICENCA_MEDICA: "Licença Médica",
            JustificationType.LICENCA_MATERNIDADE: "Licença Maternidade",
            JustificationType.LICENCA_PATERNIDADE: "Licença Paternidade",
            JustificationType.LICENCA_CASAMENTO: "Licença Casamento",
            JustificationType.LICENCA_OBITO: "Licença Óbito",
            JustificationType.LICENCA_DOACAO_SANGUE: "Doação de Sangue",
            JustificationType.LICENCA_ELEITORAL: "Licença Eleitoral",
            JustificationType.ACIDENTE_TRABALHO: "Acidente de Trabalho",
            JustificationType.TRANSPORTE: "Problema de Transporte",
            JustificationType.INTEMPERIE: "Intempérie",
            JustificationType.OUTRO: "Outro",
        }
        return display_map.get(self.justification_type, self.justification_type.value)

    @property
    def status_display(self) -> str:
        """Retorna status para exibição."""
        display_map = {
            JustificationStatus.RASCUNHO: "Rascunho",
            JustificationStatus.PENDENTE: "Pendente",
            JustificationStatus.EM_ANALISE: "Em Análise",
            JustificationStatus.APROVADA: "Aprovada",
            JustificationStatus.APROVADA_PARCIAL: "Aprovada Parcialmente",
            JustificationStatus.REJEITADA: "Rejeitada",
            JustificationStatus.CANCELADA: "Cancelada",
            JustificationStatus.EXPIRADA: "Expirada",
        }
        return display_map.get(self.status, self.status.value if hasattr(self.status, "value") else str(self.status))

    def __repr__(self) -> str:
        """Representação do objeto."""
        return f"<TimeJustification {self.code}: {self.employee_name} {self.type_display} {self.period_display}>"
