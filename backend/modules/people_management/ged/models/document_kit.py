"""
Modelo GedDocumentKit — Kit Documental Mensal.

Cada kit agrupa todos os documentos trabalhistas e fiscais de um mês
de referência para um determinado cliente (condomínio/administradora).
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class KitStatus(StrEnum):
    """Status do kit documental."""

    EM_MONTAGEM = "em_montagem"
    COMPLETO = "completo"
    ENVIADO = "enviado"
    CONFERIDO = "conferido"
    APROVADO = "aprovado"


class KitSendMethod(StrEnum):
    """Método de envio do kit."""

    EMAIL = "email"
    GOOGLE_DRIVE = "google_drive"
    PORTAL = "portal"
    IMPRESSO = "impresso"


class GedDocumentKit(Base):
    """Kit documental mensal por cliente.

    Agrupa contracheques, folhas de ponto, certidões negativas,
    guias e demais documentos trabalhistas/fiscais de um mês.
    """

    __tablename__ = "ged_document_kits"
    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "reference_month",
            name="uq_ged_kit_client_month",
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    client_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="FK para ged_clients.id",
    )
    reference_month: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="Mês de referência (primeiro dia do mês)",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default=KitStatus.EM_MONTAGEM,
        nullable=False,
        index=True,
    )

    # Contadores
    total_employees: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Quantidade de funcionários alocados no cliente neste mês",
    )
    total_documents: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Quantidade total de documentos esperados no kit",
    )
    documents_signed: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Quantidade de documentos já assinados/finalizados",
    )
    completion_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Percentual de completude do kit (0.00 a 100.00)",
    )

    # Envio
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Data/hora do envio ao cliente",
    )
    sent_method: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="Método de envio: email, google_drive, portal, impresso",
    )
    sent_to: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Destinatário(s) do envio (e-mail ou nome)",
    )

    # Aprovação
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    approved_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Nome de quem aprovou o kit",
    )

    # Arquivos
    zip_file_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Caminho do arquivo ZIP consolidado",
    )
    google_drive_link: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Link da pasta no Google Drive",
    )

    # Observações
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<GedDocumentKit(id={self.id}, client_id={self.client_id}, "
            f"month={self.reference_month}, status={self.status})>"
        )

    @property
    def percentual_assinado(self) -> Decimal:
        """Quanto do kit já está ASSINADO. É progresso de assinatura, NÃO é completude."""
        if not self.total_documents:
            return Decimal("0.00")
        return Decimal(str(round(((self.documents_signed or 0) / self.total_documents) * 100, 2)))

    def recalculate_completion(self) -> None:
        """Só o STATUS, derivado do percentual que a régua do contrato gravou.

        🔴 10/09/2026 — até hoje este método fazia `documents_signed / total_documents` e escrevia o
        resultado em `completion_percentage`. Isso responde "quanto do kit está ASSINADO", que é
        outra pergunta: um kit COMPLETO e não assinado lia 0%.

        Pior: `build_kit_for_client` chamava isto no FIM da montagem, DEPOIS da régua do contrato
        (`completude_slots.recalcular_kit_async`, os 10 blocos). A fórmula errada rodava por último e
        vencia. Medido em 08/2026: 11 kits anunciando 12,5% de média; recalculados pela régua certa,
        80,9% — e o Michelangelo, 100% com os 10 blocos cobertos por arquivo de verdade.

        Essa é a cadeia que o próprio `completude_slots` descreve e que trava o módulo: completude
        falsa → o kit nunca chega a 100% → ninguém aprova → nada é enviado → **o cliente continua
        cobrando na mão.** 55 kits montados, ZERO aprovados, UM enviado em oito meses.

        Quem escreve `completion_percentage` agora é UMA função só. Aqui fica o que sempre foi deste
        objeto: a transição de status.
        """
        if self.completion_percentage >= Decimal("100.00") and self.status == KitStatus.EM_MONTAGEM:
            self.status = KitStatus.COMPLETO
        elif self.completion_percentage < Decimal("100.00") and self.status == KitStatus.COMPLETO:
            # 09/09: o kit do Village bateu 100% com só 5 CNDs, ganhou 62 vagas na remontagem e ficou "Completo" a 7%
            self.status = KitStatus.EM_MONTAGEM
