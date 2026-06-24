"""Model de batida de ponto."""

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID

try:
    from core.database import Base
except ImportError:  # pragma: no cover
    from sqlalchemy.orm import declarative_base

    Base = declarative_base()


class ClockPunchType(enum.StrEnum):
    ENTRADA = "entrada"
    SAIDA_ALMOCO = "saida_almoco"
    RETORNO_ALMOCO = "retorno_almoco"
    SAIDA = "saida"


class ClockPunchStatus(enum.StrEnum):
    NORMAL = "normal"
    ATRASO = "atraso"
    ANTECIPADO = "antecipado"
    FORA_LOCAL = "fora_local"
    OFFLINE = "offline"
    SYNC_OK = "sync_ok"
    SYNC_ERROR = "sync_error"


class ClockPunchModel(Base):
    """Batida de ponto eletronico."""

    __tablename__ = "gp_clock_punches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    punch_id = Column(String(36), unique=True, nullable=False, index=True)
    # Coluna no banco é uuid; as_uuid=False mantém o valor como str no Python
    # (corrige 500 "operator does not exist: uuid = character varying" no espelho/batidas)
    employee_id = Column(UUID(as_uuid=False), nullable=False, index=True)

    # Tipo e timestamp (varchar no banco, nao enum PG)
    punch_type = Column(String(20), nullable=False)
    punch_timestamp = Column(DateTime, nullable=False, index=True)
    server_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Status (varchar no banco)
    status = Column(String(20), nullable=False, default="normal")

    # Reconhecimento facial
    facial_match = Column(Boolean, nullable=True)
    facial_confidence = Column(Float, nullable=True)
    facial_liveness = Column(Boolean, nullable=True)
    foto_capturada_url = Column(String(500), nullable=True)

    # Geolocalizacao
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    accuracy = Column(Float, nullable=True)
    dentro_geofence = Column(Boolean, nullable=True)
    distancia_posto_metros = Column(Float, nullable=True)

    # Dispositivo
    device_type = Column(String(20), nullable=False, default="web")
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)

    # Offline
    is_offline = Column(Boolean, nullable=False, default=False)
    synced_at = Column(DateTime, nullable=True)
    sync_attempts = Column(Integer, nullable=False, default=0)

    # Posto
    posto_id = Column(String(36), nullable=True)
    posto_nome = Column(String(255), nullable=True)

    # Justificativa (se atraso/falta)
    justification_id = Column(String(36), nullable=True)

    # Auditoria
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)
    created_by = Column(String(36), nullable=True)

    __table_args__ = (
        Index("ix_gp_punch_employee_date", "employee_id", "punch_timestamp"),
        Index("ix_gp_punch_offline", "is_offline", "synced_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "punch_id": self.punch_id,
            "employee_id": self.employee_id,
            "punch_type": self.punch_type,
            "punch_timestamp": self.punch_timestamp.isoformat() if self.punch_timestamp else None,
            "status": self.status,
            "facial_match": self.facial_match,
            "facial_confidence": self.facial_confidence,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "dentro_geofence": self.dentro_geofence,
            "device_type": self.device_type,
            "is_offline": self.is_offline,
            "posto_id": self.posto_id,
            "justification_id": self.justification_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
