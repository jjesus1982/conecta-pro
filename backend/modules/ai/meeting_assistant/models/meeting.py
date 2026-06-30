"""
Meeting Model - Sprint 49.

Define modelos para reuniões e participantes.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base


class MeetingStatusEnum(StrEnum):
    """Status da reunião."""

    SCHEDULED = "SCHEDULED"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    RESCHEDULED = "RESCHEDULED"
    NO_SHOW = "NO_SHOW"


class MeetingTypeEnum(StrEnum):
    """Tipo de reunião."""

    INTERNAL = "INTERNAL"
    EXTERNAL = "EXTERNAL"
    ONE_ON_ONE = "ONE_ON_ONE"
    TEAM = "TEAM"
    ALL_HANDS = "ALL_HANDS"
    INTERVIEW = "INTERVIEW"
    CLIENT = "CLIENT"
    BOARD = "BOARD"
    STANDUP = "STANDUP"
    RETROSPECTIVE = "RETROSPECTIVE"
    PLANNING = "PLANNING"
    REVIEW = "REVIEW"
    TRAINING = "TRAINING"
    WORKSHOP = "WORKSHOP"
    WEBINAR = "WEBINAR"
    OTHER = "OTHER"


class ParticipantStatusEnum(StrEnum):
    """Status do participante."""

    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    TENTATIVE = "TENTATIVE"
    NO_RESPONSE = "NO_RESPONSE"


class ParticipantRoleEnum(StrEnum):
    """Papel do participante."""

    ORGANIZER = "ORGANIZER"
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    PRESENTER = "PRESENTER"
    NOTE_TAKER = "NOTE_TAKER"
    OBSERVER = "OBSERVER"


class RecurrenceTypeEnum(StrEnum):
    """Tipo de recorrência."""

    NONE = "NONE"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"
    CUSTOM = "CUSTOM"


class Meeting(Base):
    """Modelo de Reunião."""

    __tablename__ = "ai_meetings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_code = Column(String(50), unique=True, nullable=False)
    title = Column(String(300), nullable=False)
    description = Column(Text)

    # Tipo e status
    meeting_type = Column(
        Enum(MeetingTypeEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=MeetingTypeEnum.INTERNAL,
    )
    status = Column(
        Enum(MeetingStatusEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=MeetingStatusEnum.SCHEDULED,
    )

    # Agendamento
    scheduled_start = Column(DateTime, nullable=False)
    scheduled_end = Column(DateTime, nullable=False)
    actual_start = Column(DateTime)
    actual_end = Column(DateTime)
    duration_minutes = Column(Integer, nullable=False)
    timezone = Column(String(50), default="America/Sao_Paulo")

    # Localização
    location = Column(String(500))
    is_virtual = Column(Boolean, default=True)
    virtual_link = Column(String(1000))
    virtual_platform = Column(String(100))  # Zoom, Teams, Meet, etc.
    room_id = Column(String(100))  # ID da sala física

    # Recorrência
    is_recurring = Column(Boolean, default=False)
    recurrence_type = Column(
        Enum(RecurrenceTypeEnum, values_callable=lambda x: [e.value for e in x]), default=RecurrenceTypeEnum.NONE
    )
    recurrence_pattern = Column(JSONB, default={})
    recurrence_end_date = Column(DateTime)
    parent_meeting_id = Column(UUID(as_uuid=True), ForeignKey("ai_meetings.id"))
    occurrence_number = Column(Integer)

    # Organização
    organizer_id = Column(UUID(as_uuid=True), nullable=False)
    organizer_name = Column(String(200))
    organizer_email = Column(String(200))
    department = Column(String(100))
    project_id = Column(UUID(as_uuid=True))

    # Agenda e preparação
    agenda = Column(JSONB, default=[])  # Lista de itens da agenda
    objectives = Column(JSONB, default=[])  # Objetivos da reunião
    preparation_notes = Column(Text)
    attachments = Column(JSONB, default=[])

    # Após a reunião
    meeting_notes = Column(Text)
    action_items = Column(JSONB, default=[])  # Itens de ação
    decisions = Column(JSONB, default=[])  # Decisões tomadas

    # IA e automação
    ai_suggested = Column(Boolean, default=False)
    ai_suggestion_reason = Column(Text)
    auto_schedule_enabled = Column(Boolean, default=False)
    smart_reminder_sent = Column(Boolean, default=False)
    sentiment_score = Column(Float)  # Análise de sentimento pós-reunião
    effectiveness_score = Column(Float)  # Score de efetividade

    # Notificações
    reminder_minutes = Column(ARRAY(Integer), default=[15, 60, 1440])  # 15min, 1h, 1dia
    notifications_sent = Column(JSONB, default={})

    # Tags e categorias
    tags = Column(ARRAY(String(50)), default=[])
    category = Column(String(100))
    priority = Column(Integer, default=50)

    # Metadados
    external_calendar_id = Column(String(200))  # ID no Google/Outlook
    sync_status = Column(String(50))
    last_synced_at = Column(DateTime)
    extra_metadata = Column(JSONB, default={})

    # Timestamps
    created_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ativo = Column(Boolean, default=True)

    # Relationships
    participants = relationship("MeetingParticipant", back_populates="meeting")
    notes = relationship("MeetingNote", back_populates="meeting")
    summaries = relationship("MeetingSummary", back_populates="meeting")

    def start_meeting(self):
        """Inicia a reunião."""
        self.status = MeetingStatusEnum.IN_PROGRESS
        self.actual_start = datetime.utcnow()

    def end_meeting(self, notes: str = None):
        """Finaliza a reunião."""
        self.status = MeetingStatusEnum.COMPLETED
        self.actual_end = datetime.utcnow()
        if notes:
            self.meeting_notes = notes

    def cancel_meeting(self, reason: str = None):
        """Cancela a reunião."""
        self.status = MeetingStatusEnum.CANCELLED
        if reason:
            self.extra_metadata = self.extra_metadata or {}
            self.extra_metadata["cancellation_reason"] = reason

    def reschedule(self, new_start: datetime, new_end: datetime):
        """Reagenda a reunião."""
        self.status = MeetingStatusEnum.RESCHEDULED
        self.extra_metadata = self.extra_metadata or {}
        self.extra_metadata["previous_schedule"] = {
            "start": self.scheduled_start.isoformat() if self.scheduled_start else None,
            "end": self.scheduled_end.isoformat() if self.scheduled_end else None,
        }
        self.scheduled_start = new_start
        self.scheduled_end = new_end
        self.duration_minutes = int((new_end - new_start).total_seconds() / 60)

    def add_agenda_item(self, title: str, duration_minutes: int = None, presenter: str = None):
        """Adiciona item à agenda."""
        if self.agenda is None:
            self.agenda = []
        self.agenda.append(
            {
                "title": title,
                "duration_minutes": duration_minutes,
                "presenter": presenter,
                "order": len(self.agenda) + 1,
            }
        )

    def add_action_item(self, description: str, assignee_id: str, due_date: datetime = None):
        """Adiciona item de ação."""
        if self.action_items is None:
            self.action_items = []
        self.action_items.append(
            {
                "description": description,
                "assignee_id": assignee_id,
                "due_date": due_date.isoformat() if due_date else None,
                "status": "pending",
                "created_at": datetime.utcnow().isoformat(),
            }
        )

    def add_decision(self, decision: str, made_by: str = None):
        """Registra decisão tomada."""
        if self.decisions is None:
            self.decisions = []
        self.decisions.append({"decision": decision, "made_by": made_by, "recorded_at": datetime.utcnow().isoformat()})


class MeetingParticipant(Base):
    """Modelo de Participante de Reunião."""

    __tablename__ = "ai_meeting_participants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id = Column(UUID(as_uuid=True), ForeignKey("ai_meetings.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)

    # Informações do participante
    name = Column(String(200), nullable=False)
    email = Column(String(200), nullable=False)
    phone = Column(String(50))
    department = Column(String(100))
    company = Column(String(200))  # Para participantes externos

    # Papel e status
    role = Column(
        Enum(ParticipantRoleEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ParticipantRoleEnum.REQUIRED,
    )
    status = Column(
        Enum(ParticipantStatusEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ParticipantStatusEnum.PENDING,
    )

    # Resposta
    response_date = Column(DateTime)
    response_note = Column(Text)

    # Presença
    attended = Column(Boolean)
    joined_at = Column(DateTime)
    left_at = Column(DateTime)
    attendance_duration_minutes = Column(Integer)

    # Comunicação
    invitation_sent = Column(Boolean, default=False)
    invitation_sent_at = Column(DateTime)
    reminder_sent = Column(Boolean, default=False)
    reminder_sent_at = Column(DateTime)

    # Preferências
    preferred_notification_method = Column(String(50))  # email, sms, push
    calendar_synced = Column(Boolean, default=False)

    # Metadados
    extra_metadata = Column(JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    meeting = relationship("Meeting", back_populates="participants")

    def accept(self, note: str = None):
        """Aceita o convite."""
        self.status = ParticipantStatusEnum.ACCEPTED
        self.response_date = datetime.utcnow()
        if note:
            self.response_note = note

    def decline(self, note: str = None):
        """Recusa o convite."""
        self.status = ParticipantStatusEnum.DECLINED
        self.response_date = datetime.utcnow()
        if note:
            self.response_note = note

    def mark_tentative(self, note: str = None):
        """Marca como tentativo."""
        self.status = ParticipantStatusEnum.TENTATIVE
        self.response_date = datetime.utcnow()
        if note:
            self.response_note = note

    def record_attendance(self, attended: bool, joined_at: datetime = None, left_at: datetime = None):
        """Registra presença."""
        self.attended = attended
        self.joined_at = joined_at
        self.left_at = left_at
        if joined_at and left_at:
            self.attendance_duration_minutes = int((left_at - joined_at).total_seconds() / 60)


class MeetingNote(Base):
    """Modelo de Notas de Reunião."""

    __tablename__ = "ai_meeting_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id = Column(UUID(as_uuid=True), ForeignKey("ai_meetings.id"), nullable=False)
    author_id = Column(UUID(as_uuid=True), nullable=False)
    author_name = Column(String(200))

    # Conteúdo
    content = Column(Text, nullable=False)
    content_type = Column(String(50), default="text")  # text, markdown, html
    is_private = Column(Boolean, default=False)

    # Categorização
    note_type = Column(String(50))  # action, decision, discussion, question
    agenda_item_index = Column(Integer)  # Relacionado a qual item da agenda

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    meeting = relationship("Meeting", back_populates="notes")


class MeetingSummary(Base):
    """Modelo de Resumo de Reunião (gerado por IA)."""

    __tablename__ = "ai_meeting_summaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id = Column(UUID(as_uuid=True), ForeignKey("ai_meetings.id"), nullable=False)

    # Resumo
    summary = Column(Text, nullable=False)
    key_points = Column(JSONB, default=[])  # Pontos principais
    action_items = Column(JSONB, default=[])  # Itens de ação extraídos
    decisions = Column(JSONB, default=[])  # Decisões identificadas
    next_steps = Column(JSONB, default=[])  # Próximos passos

    # Análise
    topics_discussed = Column(JSONB, default=[])  # Tópicos discutidos
    participant_contributions = Column(JSONB, default={})  # Contribuições por participante
    sentiment_analysis = Column(JSONB, default={})  # Análise de sentimento
    keywords = Column(ARRAY(String(50)), default=[])

    # IA
    ai_model = Column(String(100))
    ai_confidence = Column(Float)
    generation_time_seconds = Column(Float)

    # Status
    is_reviewed = Column(Boolean, default=False)
    reviewed_by = Column(UUID(as_uuid=True))
    reviewed_at = Column(DateTime)
    is_published = Column(Boolean, default=False)
    published_at = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    meeting = relationship("Meeting", back_populates="summaries")

    def review(self, reviewer_id: uuid.UUID):
        """Marca como revisado."""
        self.is_reviewed = True
        self.reviewed_by = reviewer_id
        self.reviewed_at = datetime.utcnow()

    def publish(self):
        """Publica o resumo."""
        self.is_published = True
        self.published_at = datetime.utcnow()
