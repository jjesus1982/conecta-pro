"""
Modelos das 9 features de crescimento do CRM (HubSpot-like):
catálogo de produtos, sequências, workflows, formulários, agendamento, segmentos,
propriedades customizadas, scoring configurável e forecast/metas.

Tabelas novas, sem FK rígida (segue o padrão dos models novos do CRM — robustez > integridade
referencial estrita, p/ o log/automação nunca quebrar o fluxo principal).
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


def _id() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))


# ---------------- 4) Catálogo de produtos/serviços (SKU) ----------------
class CrmProduct(Base, TimestampMixin):
    __tablename__ = "crm_products"
    id: Mapped[str] = _id()
    sku: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="un")
    unit_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    is_recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    service_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# ---------------- 1) Sequências/cadências ----------------
class CrmSequence(Base, TimestampMixin):
    __tablename__ = "crm_sequences"
    id: Mapped[str] = _id()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="email")
    steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CrmSequenceEnrollment(Base, TimestampMixin):
    __tablename__ = "crm_sequence_enrollments"
    id: Mapped[str] = _id()
    sequence_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    lead_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_step_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------- 2) Workflows / automação ----------------
class CrmWorkflow(Base, TimestampMixin):
    __tablename__ = "crm_workflows"
    id: Mapped[str] = _id()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_event: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    actions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CrmWorkflowRun(Base):
    __tablename__ = "crm_workflow_runs"
    id: Mapped[str] = _id()
    workflow_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------- 3) Formulários ----------------
class CrmForm(Base, TimestampMixin):
    __tablename__ = "crm_forms"
    id: Mapped[str] = _id()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    fields: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    redirect_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="website")
    submit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CrmFormSubmission(Base):
    __tablename__ = "crm_form_submissions"
    id: Mapped[str] = _id()
    form_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    lead_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------- 5) Agendamento ----------------
class CrmBookingLink(Base, TimestampMixin):
    __tablename__ = "crm_booking_links"
    id: Mapped[str] = _id()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    weekly_availability: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CrmBooking(Base, TimestampMixin):
    __tablename__ = "crm_bookings"
    id: Mapped[str] = _id()
    booking_link_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    lead_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)


# ---------------- 6) Segmentos ----------------
class CrmSegment(Base, TimestampMixin):
    __tablename__ = "crm_segments"
    id: Mapped[str] = _id()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    entity: Mapped[str] = mapped_column(String(30), nullable=False, default="lead")
    filters: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# ---------------- 7) Propriedades customizadas ----------------
class CrmCustomProperty(Base, TimestampMixin):
    __tablename__ = "crm_custom_properties"
    id: Mapped[str] = _id()
    entity: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    field_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    options: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# ---------------- 8) Lead scoring configurável ----------------
class CrmScoringRule(Base, TimestampMixin):
    __tablename__ = "crm_scoring_rules"
    id: Mapped[str] = _id()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    field: Mapped[str] = mapped_column(String(60), nullable=False)
    operator: Mapped[str] = mapped_column(String(20), nullable=False, default="eq")
    value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# ---------------- 9) Forecast / metas ----------------
class CrmQuota(Base, TimestampMixin):
    __tablename__ = "crm_quotas"
    id: Mapped[str] = _id()
    seller_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    seller_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    target_value: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
