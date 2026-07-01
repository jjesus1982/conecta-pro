"""Pydantic schemas para Ponto Eletronico."""

from typing import Any

from pydantic import BaseModel, Field


class GeoLocationSchema(BaseModel):
    latitude: float
    longitude: float
    accuracy: float = 0.0


class FacialSchema(BaseModel):
    match: bool
    confidence: float
    liveness_check: bool = True
    foto_base64: str | None = None


class PunchCreate(BaseModel):
    """Schema para criar uma batida de ponto."""

    employee_id: str | int
    punch_type: str = Field(..., description="entrada|saida_almoco|retorno_almoco|saida")
    timestamp: str | None = None
    location: GeoLocationSchema | None = None
    facial: FacialSchema | None = None
    device_type: str = "web"
    is_offline: bool = False
    posto_id: str | int | None = None


class PunchResponse(BaseModel):
    """Resposta de batida registrada."""

    punch_id: str
    employee_id: str | int
    punch_type: str | None = None
    punch_timestamp: str | None = None
    status: str | None = None
    facial_match: bool | None = None
    facial_confidence: float | None = None
    dentro_geofence: bool | None = None
    distancia_posto_metros: float | None = None
    is_offline: bool = False
    message: str = "Ponto registrado"

    model_config = {"from_attributes": True}


class PunchSyncRequest(BaseModel):
    """Request para sincronizar batidas offline."""

    punches: list[PunchCreate]


class PunchSyncResponse(BaseModel):
    """Resposta de sincronizacao."""

    total_received: int
    total_synced: int
    total_duplicates: int
    total_errors: int
    errors: list[dict[str, Any]] = []


class JustificationCreate(BaseModel):
    """Schema para criar justificativa."""

    employee_id: str
    punch_id: str | None = None
    justification_type: str = Field(..., description="atraso|falta")
    reason: str = Field(..., min_length=5)
    category: str = Field(..., description="transito|saude|familiar|transporte_publico|acidente|outro")
    attachments: list[dict[str, Any]] = []


class JustificationResponse(BaseModel):
    """Resposta de justificativa."""

    justification_id: str
    employee_id: str
    type: str
    reason: str
    category: str
    status: str
    created_at: str | None = None
    reviewed_by: str | None = None

    model_config = {"from_attributes": True}


class JustificationReview(BaseModel):
    """Schema para revisar justificativa."""

    action: str = Field(..., description="aprovar|rejeitar")
    reviewer_id: str
    notes: str | None = None


class DailyPunchesResponse(BaseModel):
    """Batidas de um dia."""

    employee_id: str  # [Ponto loop] era int — employee_id e UUID
    date: str
    punches: list[dict[str, Any]]
    total_horas: float
    completo: bool


class MonthlyClosingResponse(BaseModel):
    """Resposta de fechamento mensal."""

    employee_id: str  # [Ponto loop] era int — employee_id e UUID
    month: int
    year: int
    total_horas_trabalhadas: float = 0.0
    total_horas_extras_50: float = 0.0
    total_horas_extras_100: float = 0.0
    total_faltas: int = 0
    total_atrasos_minutos: float = 0.0
    fechado: bool = False

    model_config = {"from_attributes": True}
