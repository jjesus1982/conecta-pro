"""Modelo AFDRecord - Registro AFD (Arquivo-Fonte de Dados).

Armazena registros no formato AFD conforme Portaria 671 do MTE.
O AFD é o arquivo oficial de ponto que deve ser mantido por 5 anos.
"""

import uuid
from datetime import date, datetime, time
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class AFDRecordType(StrEnum):
    """Tipos de registro AFD conforme Portaria 671."""

    HEADER = "1"  # Cabeçalho do arquivo
    COMPANY_INFO = "2"  # Dados do empregador
    TIME_RECORD = "3"  # Marcação de ponto
    ADJUSTMENT = "4"  # Inclusão/alteração de marcação
    TRAILER = "9"  # Fim do arquivo


class AFDRecord(Base):
    """Modelo de Registro AFD.

    Formato AFD Portaria 671:
    - Tipo 1: Cabeçalho (NSR + tipo + dados REP + data geração)
    - Tipo 2: Empregador (NSR + tipo + CNPJ + CEI + razão social)
    - Tipo 3: Marcação (NSR + tipo + data + hora + PIS)
    - Tipo 4: Ajuste (NSR + tipo + data anterior + hora anterior + data nova + hora nova + PIS)
    - Tipo 9: Trailer (NSR + tipo + quantidade registros)
    """

    __tablename__ = "afd_records"

    # Identificação
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rep_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # NSR - Número Sequencial de Registro
    nsr: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Número Sequencial de Registro (9 dígitos)",
    )

    # Tipo de registro
    record_type: Mapped[str] = mapped_column(
        String(1),
        nullable=False,
        default=AFDRecordType.TIME_RECORD.value,
    )

    # Linha AFD completa
    afd_line: Mapped[str] = mapped_column(
        # frente 01: 400. O leiaute do Anexo I tem linha de 331 (tipo 2) e 302 (tipo 1) —
        # 100 truncava o empregador e o cabeçalho, e o banco já estava em 200.
        String(400),
        nullable=False,
        comment="Linha AFD formatada conforme Portaria 671",
    )

    # Dados parsed (para tipo 3 - marcação)
    record_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )
    record_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
    )
    pis_number: Mapped[str | None] = mapped_column(
        String(12),
        nullable=True,
        index=True,
    )

    # Para tipo 2 - empregador
    cnpj: Mapped[str | None] = mapped_column(
        String(14),
        nullable=True,
    )
    cei: Mapped[str | None] = mapped_column(
        String(12),
        nullable=True,
    )
    company_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    # Para tipo 1 - cabeçalho
    rep_serial: Mapped[str | None] = mapped_column(
        String(17),
        nullable=True,
    )
    rep_manufacturer: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    rep_model: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    generation_date: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    start_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    # Para tipo 4 - ajuste
    original_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    original_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
    )
    adjusted_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    adjusted_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
    )

    # Referência ao evento original
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rep_events.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Hash para integridade
    line_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 da linha AFD para verificação de integridade",
    )

    # Exportação
    is_exported: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    exported_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    export_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    # Validação
    is_valid: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )
    validation_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Auditoria (registros AFD são imutáveis por lei)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    __table_args__ = (
        Index("ix_afd_records_device_nsr", "device_id", "nsr", unique=True),
        Index("ix_afd_records_device_date", "device_id", "record_date"),
        Index("ix_afd_records_pis_date", "pis_number", "record_date"),
        Index("ix_afd_records_type", "record_type"),
    )

    def __repr__(self) -> str:
        return f"<AFDRecord NSR={self.nsr} Type={self.record_type}>"

    @classmethod
    def generate_type1_header(
        cls,
        nsr: int,
        rep_serial: str,
        manufacturer: str,
        model: str,
        start_date: date,
        end_date: date,
    ) -> str:
        """Gera linha AFD tipo 1 (cabeçalho).

        Formato:
        01-09: NSR
        10: Tipo (1)
        11-27: Número de fabricação REP
        28-47: Razão social fabricante (20 chars)
        48-64: Modelo REP (17 chars)
        65-68: Número registro MTE
        69-76: Data inicial (ddmmaaaa)
        77-84: Data final (ddmmaaaa)
        85-96: Data/hora geração (ddmmaaaahhmm)
        """
        now = datetime.utcnow()
        line = (
            f"{str(nsr).zfill(9)}"
            f"1"
            f"{rep_serial[:17].ljust(17)}"
            f"{manufacturer[:20].ljust(20)}"
            f"{model[:17].ljust(17)}"
            f"0000"  # Registro MTE placeholder
            f"{start_date.strftime('%d%m%Y')}"
            f"{end_date.strftime('%d%m%Y')}"
            f"{now.strftime('%d%m%Y%H%M')}"
        )
        return line

    @classmethod
    def generate_type2_company(
        cls,
        nsr: int,
        cnpj: str,
        cei: str,
        company_name: str,
    ) -> str:
        """Gera linha AFD tipo 2 (empregador).

        Formato:
        01-09: NSR
        10: Tipo (2)
        11: Tipo identificador (1=CNPJ, 2=CPF)
        12-25: CNPJ/CPF (14 dígitos)
        26-37: CEI (12 dígitos)
        38-187: Razão social (150 chars)
        """
        line = (
            f"{str(nsr).zfill(9)}"
            f"2"
            f"1"  # CNPJ
            f"{cnpj.zfill(14)[:14]}"
            f"{cei.zfill(12)[:12]}"
            f"{company_name[:150].ljust(150)}"
        )
        return line

    @classmethod
    def generate_type3_record(
        cls,
        nsr: int,
        record_date: date,
        record_time: time,
        pis: str,
    ) -> str:
        """Gera linha AFD tipo 3 (marcação de ponto).

        Formato:
        01-09: NSR
        10: Tipo (3)
        11-18: Data (ddmmaaaa)
        19-22: Hora (hhmm)
        23-34: PIS (12 dígitos)
        """
        line = f"{str(nsr).zfill(9)}3{record_date.strftime('%d%m%Y')}{record_time.strftime('%H%M')}{pis.zfill(12)[:12]}"
        return line

    @classmethod
    def generate_type9_trailer(cls, nsr: int, total_records: int) -> str:
        """Gera linha AFD tipo 9 (trailer).

        Formato:
        01-09: NSR
        10: Tipo (9)
        11-19: Quantidade de registros tipo 3 (9 dígitos)
        """
        line = f"{str(nsr).zfill(9)}9{str(total_records).zfill(9)}"
        return line

    @classmethod
    def parse_afd_line(cls, line: str) -> dict:
        """Parse uma linha AFD e extrai os dados."""
        if len(line) < 10:
            return {"error": "Linha muito curta"}

        nsr = int(line[0:9])
        record_type = line[9]

        result = {
            "nsr": nsr,
            "record_type": record_type,
            "raw_line": line,
        }

        if record_type == "3" and len(line) >= 34:
            # Marcação de ponto
            result["record_date"] = datetime.strptime(line[10:18], "%d%m%Y").date()
            result["record_time"] = datetime.strptime(line[18:22], "%H%M").time()
            result["pis_number"] = line[22:34].strip()

        elif record_type == "1" and len(line) >= 96:
            # Cabeçalho
            result["rep_serial"] = line[10:27].strip()
            result["manufacturer"] = line[27:47].strip()
            result["model"] = line[47:64].strip()
            result["start_date"] = datetime.strptime(line[68:76], "%d%m%Y").date()
            result["end_date"] = datetime.strptime(line[76:84], "%d%m%Y").date()

        elif record_type == "2" and len(line) >= 187:
            # Empregador
            result["cnpj"] = line[11:25].strip()
            result["cei"] = line[25:37].strip()
            result["company_name"] = line[37:187].strip()

        elif record_type == "9" and len(line) >= 19:
            # Trailer
            result["total_records"] = int(line[10:19])

        return result

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "id": str(self.id),
            "device_id": str(self.device_id),
            "nsr": self.nsr,
            "record_type": self.record_type,
            "afd_line": self.afd_line,
            "record_date": self.record_date.isoformat() if self.record_date else None,
            "record_time": self.record_time.isoformat() if self.record_time else None,
            "pis_number": self.pis_number,
            "is_valid": self.is_valid,
            "is_exported": self.is_exported,
        }
