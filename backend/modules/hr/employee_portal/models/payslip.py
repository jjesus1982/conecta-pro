"""Model para contracheques/holerites.

Mapeado para a tabela hr_payslips criada na migration sprint21_001.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class PaySlipStatus(StrEnum):
    """Status do contracheque.

    Os dois últimos foram acrescentados em 13/08/2026 porque JÁ EXISTIAM no mundo e o enum
    é que estava desatualizado — a coluna é `String(20)`, então nada impedia:
      • `contested`: 5 linhas em produção, gravadas pela contestação do próprio funcionário;
      • `paid`: gravado por `folha_payment_service` (`UPDATE hr_payslips SET status='paid'`)
        quando o PIX da folha liquida.
    Nenhum dos dois estava na lista de visíveis do portal. Efeito medido: quem contestava o
    holerite PERDIA o acesso ao documento que contestou, e quem recebia perdia o do mês pago.
    """

    DRAFT = "draft"  # Rascunho (em processamento)
    GENERATED = "generated"  # Gerado (aguardando aprovação)
    APPROVED = "approved"  # Aprovado (pronto para visualização)
    PUBLISHED = "published"  # Publicado (visível para funcionário)
    RECTIFIED = "rectified"  # Retificado (houve correção)
    CONTESTED = "contested"  # Contestado pelo funcionário — continua visível PARA ELE
    PAID = "paid"  # Liquidado via PIX da folha — continua visível
    CANCELLED = "cancelled"  # Cancelado / substituído por publicação posterior


# Um lugar só decide o que o funcionário enxerga no portal. Antes cada método repetia
# `[PUBLISHED, RECTIFIED]` na mão, e os dois status acima ficaram de fora dos quatro.
#
# A lista é POSITIVA de propósito: com uma negativa (`status <> 'cancelled'`), qualquer
# status novo nasceria visível — inclusive rascunho de folha ainda não conferida.
VISIVEL_AO_FUNCIONARIO: tuple[str, ...] = (
    PaySlipStatus.PUBLISHED.value,
    PaySlipStatus.RECTIFIED.value,
    PaySlipStatus.CONTESTED.value,
    PaySlipStatus.PAID.value,
)


class PaySlipType(StrEnum):
    """Tipo de contracheque."""

    MONTHLY = "monthly"  # Mensal (normal)
    BIWEEKLY = "biweekly"  # Quinzenal
    ADVANCE = "advance"  # Adiantamento
    THIRTEENTH_1ST = "thirteenth_1st"  # 13º - 1ª parcela
    THIRTEENTH_2ND = "thirteenth_2nd"  # 13º - 2ª parcela
    VACATION = "vacation"  # Férias
    VACATION_BONUS = "vacation_bonus"  # 1/3 férias
    TERMINATION = "termination"  # Rescisão
    PLR = "plr"  # Participação nos Lucros
    BONUS = "bonus"  # Bônus
    COMPLEMENTARY = "complementary"  # Complementar


class PaySlip(Base):
    """Contracheque/Holerite do funcionário.

    Mapeado para hr_payslips (sprint21_001).
    """

    __tablename__ = "hr_payslips"

    # Chave primária
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referências (sem FK declarada — tabela foi criada sem constraints)
    condominio_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    employee_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Identificação
    payslip_code = Column(String(50), nullable=False, index=True)
    payslip_type = Column(String(30), nullable=False, server_default="monthly")
    status = Column(String(20), nullable=False, server_default="draft", index=True)

    # Período de referência
    reference_year = Column(Integer, nullable=False)
    reference_month = Column(Integer, nullable=False)  # 1-12
    reference_period = Column(String(7), nullable=False)  # YYYY-MM
    payment_date = Column(Date, nullable=True)
    competence_start = Column(Date, nullable=True)
    competence_end = Column(Date, nullable=True)

    # Valores totais
    base_salary = Column(Numeric(12, 2), nullable=False, server_default="0")
    total_earnings = Column(Numeric(12, 2), nullable=False, server_default="0")
    total_deductions = Column(Numeric(12, 2), nullable=False, server_default="0")
    net_salary = Column(Numeric(12, 2), nullable=False, server_default="0")

    # Detalhamento JSONB
    # earnings: [{"code": "001", "description": "Salário Base", "reference": 30, "value": 5000.00}, ...]
    # deductions: [{"code": "101", "description": "INSS", "reference": 14, "value": 500.00}, ...]
    earnings = Column(JSONB, nullable=False, server_default="[]")
    deductions = Column(JSONB, nullable=False, server_default="[]")
    informative = Column(JSONB, nullable=False, server_default="{}")
    bank_info = Column(JSONB, nullable=True)

    # Bases de cálculo
    inss_base = Column(Numeric(12, 2), nullable=True)
    inss_value = Column(Numeric(12, 2), nullable=True)
    irrf_base = Column(Numeric(12, 2), nullable=True)
    irrf_value = Column(Numeric(12, 2), nullable=True)
    fgts_base = Column(Numeric(12, 2), nullable=True)
    fgts_value = Column(Numeric(12, 2), nullable=True)

    # Visualização pelo funcionário
    first_viewed_at = Column(DateTime(timezone=True), nullable=True)
    view_count = Column(Integer, nullable=False, server_default="0")
    last_viewed_at = Column(DateTime(timezone=True), nullable=True)
    download_count = Column(Integer, nullable=False, server_default="0")
    last_download_at = Column(DateTime(timezone=True), nullable=True)

    # Ciência
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by_ip = Column(String(50), nullable=True)

    # Contestação
    contested_at = Column(DateTime(timezone=True), nullable=True)
    contest_reason = Column(Text, nullable=True)
    contest_resolved_at = Column(DateTime(timezone=True), nullable=True)
    contest_resolution = Column(Text, nullable=True)

    # PDF e arquivo
    pdf_path = Column(String(500), nullable=True)
    pdf_generated_at = Column(DateTime(timezone=True), nullable=True)
    pdf_hash = Column(String(64), nullable=True)

    # Publicação
    published_at = Column(DateTime(timezone=True), nullable=True)
    published_by = Column(UUID(as_uuid=True), nullable=True)

    # Integração com sistemas externos
    external_id = Column(String(100), nullable=True)
    source_system = Column(String(50), nullable=True)
    import_batch_id = Column(UUID(as_uuid=True), nullable=True)

    # Auditoria
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (Index("ix_hr_payslips_period", "reference_year", "reference_month"),)

    def __repr__(self) -> str:
        return f"<PaySlip {self.payslip_code}>"

    @property
    def reference_period_fmt(self) -> str:
        """Retorna período formatado (MM/YYYY)."""
        return f"{self.reference_month:02d}/{self.reference_year}"

    @property
    def is_published(self) -> bool:
        """Verifica se está publicado."""
        return self.status == PaySlipStatus.PUBLISHED.value

    @property
    def is_viewable(self) -> bool:
        """Verifica se pode ser visualizado pelo funcionário."""
        return self.status in [
            PaySlipStatus.PUBLISHED.value,
            PaySlipStatus.RECTIFIED.value,
        ]

    @property
    def contested(self) -> bool:
        """Verifica se está contestado."""
        return self.contested_at is not None

    @property
    def can_contest(self) -> bool:
        """Verifica se pode ser contestado."""
        return self.is_viewable and not self.contested and not self.acknowledged_at

    def record_view(self) -> None:
        """Registra visualização do contracheque."""
        now = datetime.utcnow()
        if not self.first_viewed_at:
            self.first_viewed_at = now
        self.last_viewed_at = now
        self.view_count = (self.view_count or 0) + 1

    def record_download(self) -> None:
        """Registra download do contracheque."""
        now = datetime.utcnow()
        self.last_download_at = now
        self.download_count = (self.download_count or 0) + 1

    def to_summary(self) -> dict:
        """Retorna resumo para listagem."""
        return {
            "id": str(self.id),
            "payslip_code": self.payslip_code,
            "payslip_type": self.payslip_type,
            "reference_period": self.reference_period_fmt,
            "payment_date": self.payment_date.isoformat() if self.payment_date else None,
            "net_salary": float(self.net_salary),
            "status": self.status,
            "viewed": self.first_viewed_at is not None,
            "downloaded": self.last_download_at is not None,
            "acknowledged": self.acknowledged_at is not None,
            "contested": self.contested,
        }

    # Alias para retrocompatibilidade com código que usava gross_salary
    @property
    def gross_salary(self) -> Numeric:
        """Alias para base_salary (compatibilidade)."""
        return self.base_salary
