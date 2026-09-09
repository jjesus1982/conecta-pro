"""
Condominium Model - Cadastro de Condomínios
Sprint 30: Cadastro de Clientes/Condomínios

NOTA: Este model foi sincronizado com o banco de dados real em 28/03/2026.
Colunas correspondem EXATAMENTE ao schema da tabela condominiums.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.clients.models.client import Client
    from modules.clients.models.unit import Unit


class CondominiumType(StrEnum):
    """Tipo de condominio - valores sincronizados com banco."""

    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    MIXED = "mixed"
    INDUSTRIAL = "industrial"
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    SUBDIVISION = "subdivision"


class CondominiumStatus(StrEnum):
    """Status do condominio - valores sincronizados com banco."""

    # 09/09/2026: alinhado ao enum REAL do banco (condominium_status_enum: prospect, implantation, active,
    # suspended, cancelled). O modelo dizia "implementing"/"inactive"/"closed" e TODO INSERT de condomínio caía
    # com InvalidTextRepresentation — cadastrar condomínio pela tela estava impossível.
    PROSPECT = "prospect"
    IMPLANTATION = "implantation"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"
    # apelidos antigos (código que ainda cita) → valores do banco
    IMPLEMENTING = "implantation"
    INACTIVE = "suspended"
    CLOSED = "cancelled"


class AdministrationType(StrEnum):
    """Tipo de administração."""

    # 09/09/2026: alinhado ao enum REAL do banco (administration_type_enum: self_managed, administrator,
    # property_manager, hybrid). O modelo gravava "administradora" e o INSERT caía.
    SELF_MANAGED = "self_managed"
    ADMINISTRATOR = "administrator"
    PROPERTY_MANAGER = "property_manager"
    HYBRID = "hybrid"
    # apelidos antigos → valores do banco
    PROPRIA = "self_managed"
    ADMINISTRADORA = "administrator"
    SINDICO_PROFISSIONAL = "property_manager"
    AUTOGESTAO = "self_managed"


class Condominium(Base):
    """
    Model de Condomínio — sincronizado com banco real.

    Representa um condomínio gerenciado pelo cliente.
    Um cliente pode ter múltiplos condomínios.
    """

    __tablename__ = "condominiums"

    # Identificação
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(20), unique=True, nullable=False, index=True)

    # Dados básicos
    name = Column(String(200), nullable=False)
    trading_name = Column(String(200), nullable=True)
    cnpj = Column(String(18), nullable=True, index=True)
    condominium_type = Column("condominium_type", String(30), nullable=False)
    status = Column("status", String(30), nullable=False, default="implantation")
    administration_type = Column("administration_type", String(40), nullable=True, default="administrator")

    # Endereço
    address_street = Column(String(255), nullable=True)
    address_number = Column(String(20), nullable=True)
    address_complement = Column(String(100), nullable=True)
    address_neighborhood = Column(String(100), nullable=True)
    address_city = Column(String(100), nullable=True)
    address_state = Column(String(2), nullable=True)
    address_zipcode = Column(String(10), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Características físicas
    total_units = Column(Integer, nullable=True, default=0)
    total_towers = Column(Integer, nullable=True)
    total_floors = Column(Integer, nullable=True)
    total_parking_spaces = Column(Integer, nullable=True)
    total_common_areas = Column(Integer, nullable=True)
    built_area = Column(Float, nullable=True)
    total_area = Column(Float, nullable=True)
    construction_year = Column(Integer, nullable=True)

    # Áreas comuns
    has_pool = Column(Boolean, nullable=False, default=False)
    has_gym = Column(Boolean, nullable=False, default=False)
    has_party_room = Column(Boolean, nullable=False, default=False)
    has_playground = Column(Boolean, nullable=False, default=False)
    has_sports_court = Column(Boolean, nullable=False, default=False)
    has_sauna = Column(Boolean, nullable=False, default=False)
    has_barbecue = Column(Boolean, nullable=False, default=False)
    has_garden = Column(Boolean, nullable=False, default=False)
    amenities = Column(JSONB, nullable=True)

    # Segurança
    has_cctv = Column(Boolean, nullable=False, default=False)
    has_access_control = Column(Boolean, nullable=False, default=False)
    has_intercom = Column(Boolean, nullable=False, default=False)
    has_24h_security = Column(Boolean, nullable=False, default=False)
    has_electric_fence = Column(Boolean, nullable=False, default=False)
    has_alarm = Column(Boolean, nullable=False, default=False)
    total_cameras = Column(Integer, nullable=True, default=0)
    total_access_points = Column(Integer, nullable=True, default=1)

    # Síndico
    syndic_name = Column(String(100), nullable=True)
    syndic_email = Column(String(255), nullable=True)
    syndic_phone = Column(String(20), nullable=True)
    syndic_cpf = Column(String(14), nullable=True)
    syndic_mandate_start = Column(Date, nullable=True)
    syndic_mandate_end = Column(Date, nullable=True)

    # Administradora
    administrator_name = Column(String(200), nullable=True)
    administrator_cnpj = Column(String(18), nullable=True)
    administrator_email = Column(String(255), nullable=True)
    administrator_phone = Column(String(20), nullable=True)

    # Dados operacionais
    implantation_start_date = Column(Date, nullable=True)
    implantation_end_date = Column(Date, nullable=True)
    activation_date = Column(Date, nullable=True)

    # Metadata
    notes = Column(Text, nullable=True)
    tags = Column(JSONB, nullable=True)
    extra_metadata = Column("metadata", JSONB, nullable=True)

    # Flags — banco usa 'ativo' não 'is_active'
    ativo = Column(Boolean, nullable=False, default=True)

    # Auditoria
    created_at = Column(DateTime, nullable=False, server_default="now()")
    updated_at = Column(DateTime, nullable=False, server_default="now()", onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Relacionamentos
    client: "Client" = relationship("Client", back_populates="condominiums")
    units: list["Unit"] = relationship("Unit", back_populates="condominium", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Condominium(id={self.id}, code={self.code}, name={self.name})>"

    # Properties computadas (não são colunas)
    @property
    def is_active(self) -> bool:
        """Alias para ativo."""
        return bool(self.ativo)

    @property
    def full_address(self) -> str:
        """Endereço completo."""
        parts = []
        if self.address_street:
            addr = self.address_street
            if self.address_number:
                addr += f", {self.address_number}"
            if self.address_complement:
                addr += f" - {self.address_complement}"
            parts.append(addr)
        if self.address_neighborhood:
            parts.append(self.address_neighborhood)
        if self.address_city and self.address_state:
            parts.append(f"{self.address_city}/{self.address_state}")
        if self.address_zipcode:
            parts.append(f"CEP: {self.address_zipcode}")
        return ", ".join(parts)

    @property
    def occupied_units(self) -> int:
        """Quantidade de unidades ocupadas."""
        if not self.units:
            return 0
        return sum(1 for u in self.units if getattr(u, "is_occupied", False))

    @property
    def occupancy_rate(self) -> float:
        """Taxa de ocupação."""
        if not self.total_units or self.total_units == 0:
            return 0.0
        return (self.occupied_units / self.total_units) * 100

    @property
    def security_level(self) -> str:
        """Nível de segurança baseado nos recursos."""
        score = 0
        if self.has_24h_security:
            score += 3
        if self.has_cctv:
            score += 2
        if self.has_access_control:
            score += 2
        if self.has_electric_fence:
            score += 1
        if self.has_alarm:
            score += 1
        if self.has_intercom:
            score += 1
        if score >= 8:
            return "alto"
        elif score >= 5:
            return "medio"
        elif score >= 2:
            return "basico"
        return "minimo"

    @property
    def amenities_count(self) -> int:
        """Quantidade de áreas de lazer."""
        count = 0
        for attr in [
            "has_pool",
            "has_gym",
            "has_party_room",
            "has_playground",
            "has_sports_court",
            "has_barbecue",
            "has_sauna",
            "has_garden",
        ]:
            if getattr(self, attr, False):
                count += 1
        return count

    @property
    def syndic_mandate_active(self) -> bool:
        """Verifica se o mandato do síndico está ativo."""
        if not self.syndic_mandate_start:
            return False
        today = date.today()
        if self.syndic_mandate_end and today > self.syndic_mandate_end:
            return False
        return today >= self.syndic_mandate_start

    @property
    def is_premium(self) -> bool:
        """Placeholder — premium via metadata ou tags."""
        return False

    @property
    def plus_enabled(self) -> bool:
        """Placeholder — plus via metadata."""
        return False

    def activate(self) -> None:
        """Ativa o condominio."""
        self.status = CondominiumStatus.ACTIVE
        self.ativo = True
        if not self.activation_date:
            self.activation_date = date.today()
        self.updated_at = datetime.utcnow()

    def deactivate(self) -> None:
        """Desativa o condominio."""
        self.status = CondominiumStatus.INACTIVE
        self.ativo = False
        self.updated_at = datetime.utcnow()

    def suspend(self, reason: str | None = None) -> None:
        """Suspende o condominio."""
        self.status = CondominiumStatus.SUSPENDED
        if reason:
            self.notes = f"{self.notes or ''}\n[SUSPENSO] {datetime.now()}: {reason}".strip()
        self.updated_at = datetime.utcnow()

    def start_implantation(self) -> None:
        """Inicia implantacao."""
        self.status = CondominiumStatus.IMPLEMENTING
        self.implantation_start_date = date.today()
        self.updated_at = datetime.utcnow()

    def finish_implantation(self) -> None:
        """Finaliza implantacao e ativa."""
        self.implantation_end_date = date.today()
        self.activation_date = date.today()
        self.status = CondominiumStatus.ACTIVE
        self.ativo = True
        self.updated_at = datetime.utcnow()

    def update_syndic(
        self,
        name: str,
        phone: str | None = None,
        email: str | None = None,
        cpf: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> None:
        """Atualiza dados do síndico."""
        self.syndic_name = name
        self.syndic_phone = phone
        self.syndic_email = email
        self.syndic_cpf = cpf
        self.syndic_mandate_start = start_date or date.today()
        self.syndic_mandate_end = end_date
        self.updated_at = datetime.utcnow()

    @staticmethod
    def generate_code(client_code: str, sequence: int) -> str:
        """Gera código do condomínio: C<nº do cliente>-<seq> (ex.: C00014-001).

        09/09/2026: era f"{client_code}-COND-{seq:03d}" = 23 caracteres com o código de cliente
        CLI-AAAA-NNNNN; a coluna é varchar(20) → nenhum condomínio nascia por este caminho.
        """
        return f"C{client_code.split('-')[-1]}-{sequence:03d}"
