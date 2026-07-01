"""
PONTO Agent - Ponto Eletronico.
Batida facial, geolocalizacao, offline-first, justificativas.
"""

import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from ..core.events import Event, GPEventTypes
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


# ==========================================
# ENUMS E DATACLASSES
# ==========================================


class ClockPunchType(StrEnum):
    ENTRADA = "entrada"
    SAIDA_ALMOCO = "saida_almoco"
    RETORNO_ALMOCO = "retorno_almoco"
    SAIDA = "saida"


class ClockPunchStatus(StrEnum):
    NORMAL = "normal"
    ATRASO = "atraso"
    ANTECIPADO = "antecipado"
    FORA_LOCAL = "fora_local"
    OFFLINE = "offline"
    SYNC_OK = "sync_ok"
    SYNC_ERROR = "sync_error"


class JustificationCategory(StrEnum):
    TRANSITO = "transito"
    SAUDE = "saude"
    FAMILIAR = "familiar"
    TRANSPORTE_PUBLICO = "transporte_publico"
    ACIDENTE = "acidente"
    OUTRO = "outro"


class JustificationStatus(StrEnum):
    PENDENTE = "pendente"
    APROVADA = "aprovada"
    REJEITADA = "rejeitada"


@dataclass
class GeoLocation:
    latitude: float
    longitude: float
    accuracy: float = 0.0
    dentro_geofence: bool = True


@dataclass
class FacialResult:
    match: bool
    confidence: float
    liveness_check: bool = True
    foto_capturada: str | None = None


@dataclass
class ClockPunch:
    employee_id: str
    punch_type: ClockPunchType
    timestamp: str
    location: GeoLocation | None = None
    facial: FacialResult | None = None
    status: ClockPunchStatus = ClockPunchStatus.NORMAL
    punch_id: str = field(default_factory=lambda: str(uuid4()))
    device_type: str = "web"
    is_offline: bool = False
    justification_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "punch_id": self.punch_id,
            "employee_id": self.employee_id,
            "punch_type": self.punch_type.value,
            "timestamp": self.timestamp,
            "status": self.status.value,
            "device_type": self.device_type,
            "is_offline": self.is_offline,
            "justification_id": self.justification_id,
        }
        if self.location:
            data["location"] = asdict(self.location)
        if self.facial:
            data["facial"] = {
                "match": self.facial.match,
                "confidence": self.facial.confidence,
                "liveness_check": self.facial.liveness_check,
            }
        return data


@dataclass
class Justification:
    employee_id: str
    punch_id: str
    justification_type: str  # "atraso" ou "falta"
    reason: str
    category: JustificationCategory
    justification_id: str = field(default_factory=lambda: str(uuid4()))
    attachments: list[dict[str, Any]] = field(default_factory=list)
    status: JustificationStatus = JustificationStatus.PENDENTE
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    reviewed_by: str | None = None
    reviewed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "justification_id": self.justification_id,
            "employee_id": self.employee_id,
            "punch_id": self.punch_id,
            "type": self.justification_type,
            "reason": self.reason,
            "category": self.category.value,
            "attachments": self.attachments,
            "status": self.status.value,
            "created_at": self.created_at,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
        }


# ==========================================
# SKILLS
# ==========================================


class FacialSkill:
    """Reconhecimento facial com face-api.js (validacao server-side)."""

    DEFAULT_THRESHOLD = 0.6

    def validate_facial(
        self,
        captured_descriptor: list[float],
        stored_descriptor: list[float],
        threshold: float = None,
    ) -> FacialResult:
        """Valida reconhecimento facial comparando descritores."""
        if threshold is None:
            threshold = self.DEFAULT_THRESHOLD

        if not captured_descriptor or not stored_descriptor:
            return FacialResult(match=False, confidence=0.0, liveness_check=False)

        # Distancia euclidiana entre descritores
        distance = self._euclidean_distance(captured_descriptor, stored_descriptor)

        # Confianca inversamente proporcional a distancia
        confidence = max(0.0, 1.0 - distance)
        match = distance < threshold

        return FacialResult(match=match, confidence=round(confidence, 4), liveness_check=True)

    def _euclidean_distance(self, a: list[float], b: list[float]) -> float:
        """Calcula distancia euclidiana entre dois vetores."""
        if len(a) != len(b):
            return 1.0
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=False)))


class GeoSkill:
    """Geolocalizacao e geofence."""

    EARTH_RADIUS_KM = 6371.0

    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calcula distancia em metros entre dois pontos (Haversine)."""
        lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
        lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)

        dlat = lat2_r - lat1_r
        dlon = lon2_r - lon1_r

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return self.EARTH_RADIUS_KM * c * 1000  # metros

    def check_geofence(
        self,
        employee_lat: float,
        employee_lon: float,
        posto_lat: float,
        posto_lon: float,
        raio_metros: float = 200.0,
    ) -> dict[str, Any]:
        """Verifica se funcionario esta dentro do geofence do posto."""
        distance = self.calculate_distance(employee_lat, employee_lon, posto_lat, posto_lon)
        dentro = distance <= raio_metros

        return {
            "dentro_geofence": dentro,
            "distancia_metros": round(distance, 2),
            "raio_permitido": raio_metros,
        }


class ClockSkill:
    """Registro de batidas de ponto."""

    TOLERANCIA_MINUTOS = 10
    DEBOUNCE_SEGUNDOS = 30

    def determinar_tipo_batida(self, batidas_do_dia: list[ClockPunch]) -> ClockPunchType:
        """Determina o tipo da proxima batida baseado nas anteriores."""
        count = len(batidas_do_dia)
        if count == 0:
            return ClockPunchType.ENTRADA
        elif count == 1:
            return ClockPunchType.SAIDA_ALMOCO
        elif count == 2:
            return ClockPunchType.RETORNO_ALMOCO
        else:
            return ClockPunchType.SAIDA

    def verificar_atraso(
        self,
        horario_batida: datetime,
        horario_esperado: datetime,
        tolerancia_min: int = None,
    ) -> dict[str, Any]:
        """Verifica se houve atraso."""
        if tolerancia_min is None:
            tolerancia_min = self.TOLERANCIA_MINUTOS

        diff = (horario_batida - horario_esperado).total_seconds() / 60

        return {
            "atrasado": diff > tolerancia_min,
            "minutos_diferenca": round(diff, 1),
            "tolerancia": tolerancia_min,
        }

    def verificar_debounce(self, ultima_batida: datetime | None, agora: datetime) -> bool:
        """Verifica se ja passou tempo suficiente desde ultima batida."""
        if ultima_batida is None:
            return True
        diff = (agora - ultima_batida).total_seconds()
        return diff >= self.DEBOUNCE_SEGUNDOS

    def calcular_horas_trabalhadas(self, batidas: list[ClockPunch]) -> dict[str, Any]:
        """Calcula total de horas trabalhadas no dia."""
        if len(batidas) < 2:
            return {"horas_totais": 0.0, "completo": False}

        timestamps = []
        for b in sorted(batidas, key=lambda x: x.timestamp):
            timestamps.append(datetime.fromisoformat(b.timestamp))

        horas_totais = 0.0
        for i in range(0, len(timestamps) - 1, 2):
            if i + 1 < len(timestamps):
                diff = (timestamps[i + 1] - timestamps[i]).total_seconds() / 3600
                horas_totais += diff

        return {
            "horas_totais": round(horas_totais, 2),
            "completo": len(batidas) >= 4,
            "batidas": len(batidas),
        }


class OfflineSkill:
    """Gerenciamento de batidas offline."""

    MAX_PENDING = 500
    SYNC_BATCH_SIZE = 20

    def validate_offline_punch(self, punch_data: dict[str, Any]) -> dict[str, Any]:
        """Valida uma batida que veio do modo offline."""
        errors = []

        if not punch_data.get("employee_id"):
            errors.append("employee_id obrigatorio")
        if not punch_data.get("timestamp"):
            errors.append("timestamp obrigatorio")
        if not punch_data.get("punch_type"):
            errors.append("punch_type obrigatorio")

        # Valida que timestamp nao e muito antigo (max 7 dias)
        if punch_data.get("timestamp"):
            try:
                ts = datetime.fromisoformat(punch_data["timestamp"])
                age_days = (datetime.utcnow() - ts).days
                if age_days > 7:
                    errors.append("batida com mais de 7 dias")
            except (ValueError, TypeError):
                errors.append("timestamp invalido")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
        }

    def prepare_sync_batch(self, pending_punches: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """Divide batidas pendentes em batches para sync."""
        # Ordena por timestamp
        sorted_punches = sorted(pending_punches, key=lambda x: x.get("timestamp", ""))

        batches = []
        for i in range(0, len(sorted_punches), self.SYNC_BATCH_SIZE):
            batches.append(sorted_punches[i : i + self.SYNC_BATCH_SIZE])

        return batches

    def check_duplicate(
        self,
        punch: dict[str, Any],
        existing_punches: list[dict[str, Any]],
    ) -> bool:
        """Verifica se batida e duplicata."""
        for existing in existing_punches:
            if (
                existing.get("employee_id") == punch.get("employee_id")
                and existing.get("timestamp") == punch.get("timestamp")
                and existing.get("punch_type") == punch.get("punch_type")
            ):
                return True
        return False


class JustifySkill:
    """Gestao de justificativas de atraso/falta."""

    VALID_CATEGORIES = [c.value for c in JustificationCategory]

    def create_justification(
        self,
        employee_id: str,
        punch_id: str,
        justification_type: str,
        reason: str,
        category: str,
        attachments: list[dict] | None = None,
    ) -> Justification:
        """Cria uma justificativa."""
        if category not in self.VALID_CATEGORIES:
            raise ValueError(f"Categoria invalida: {category}")
        if justification_type not in ("atraso", "falta"):
            raise ValueError(f"Tipo invalido: {justification_type}")
        if not reason or len(reason) < 5:
            raise ValueError("Justificativa deve ter pelo menos 5 caracteres")

        return Justification(
            employee_id=employee_id,
            punch_id=punch_id,
            justification_type=justification_type,
            reason=reason,
            category=JustificationCategory(category),
            attachments=attachments or [],
        )

    def approve(self, justification: Justification, reviewer_id: str) -> Justification:
        """Aprova uma justificativa."""
        justification.status = JustificationStatus.APROVADA
        justification.reviewed_by = reviewer_id
        justification.reviewed_at = datetime.utcnow().isoformat()
        return justification

    def reject(self, justification: Justification, reviewer_id: str) -> Justification:
        """Rejeita uma justificativa."""
        justification.status = JustificationStatus.REJEITADA
        justification.reviewed_by = reviewer_id
        justification.reviewed_at = datetime.utcnow().isoformat()
        return justification


# ==========================================
# PONTO AGENT
# ==========================================


class PontoAgent(BaseAgent):
    """
    Agent do Ponto Eletronico.

    Responsabilidades:
    - Registrar batidas (facial + geo)
    - Gerenciar modo offline
    - Sincronizar batidas
    - Detectar atrasos e faltas
    - Gerenciar justificativas
    """

    AGENT_NAME = "PONTO_AGENT"
    AGENT_VERSION = "1.0.0"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.register_skill("FACIAL", FacialSkill())
        self.register_skill("GEO", GeoSkill())
        self.register_skill("CLOCK", ClockSkill())
        self.register_skill("OFFLINE", OfflineSkill())
        self.register_skill("JUSTIFY", JustifySkill())

    @property
    def handled_events(self) -> list[str]:
        return [
            GPEventTypes.FUNCIONARIO_ADMITIDO,
            GPEventTypes.FUNCIONARIO_DEMITIDO,
            GPEventTypes.ESCALA_PUBLICADA,
            GPEventTypes.SYNC_INICIADO,
            GPEventTypes.FUNCIONARIO_FOTO_ATUALIZADA,
        ]

    async def _process_event(self, event: Event) -> None:
        handlers = {
            GPEventTypes.FUNCIONARIO_ADMITIDO: self._on_funcionario_admitido,
            GPEventTypes.FUNCIONARIO_DEMITIDO: self._on_funcionario_demitido,
            GPEventTypes.ESCALA_PUBLICADA: self._on_escala_publicada,
            GPEventTypes.SYNC_INICIADO: self._on_sync_iniciado,
        }
        handler = handlers.get(event.event_type)
        if handler:
            await handler(event)

    async def _on_funcionario_admitido(self, event: Event) -> None:
        logger.info(f"PONTO: Habilitando batida para {event.payload.get('employee_id')}")

    async def _on_funcionario_demitido(self, event: Event) -> None:
        logger.info(f"PONTO: Desabilitando batida para {event.payload.get('employee_id')}")

    async def _on_escala_publicada(self, event: Event) -> None:
        logger.info("PONTO: Escala recebida, atualizando horarios esperados")

    async def _on_sync_iniciado(self, event: Event) -> None:
        logger.info("PONTO: Sync de batidas offline iniciado")
        await self.emit_event(
            event_type=GPEventTypes.PONTO_SYNC_CONCLUIDO,
            payload={"batidas_sincronizadas": 0},
            affected_modules=["DP"],
        )

    async def registrar_batida(
        self,
        employee_id: str,
        punch_type: ClockPunchType,
        location: GeoLocation | None = None,
        facial: FacialResult | None = None,
        is_offline: bool = False,
        device_type: str = "web",
    ) -> ClockPunch:
        """Registra uma batida de ponto."""
        punch = ClockPunch(
            employee_id=employee_id,
            punch_type=punch_type,
            timestamp=datetime.utcnow().isoformat(),
            location=location,
            facial=facial,
            device_type=device_type,
            is_offline=is_offline,
        )

        # Verificar geofence
        if location and not location.dentro_geofence:
            punch.status = ClockPunchStatus.FORA_LOCAL

        if is_offline:
            punch.status = ClockPunchStatus.OFFLINE

        # Emitir evento de batida
        await self.emit_event(
            event_type=GPEventTypes.PONTO_BATIDO,
            payload=punch.to_dict(),
            affected_modules=["DP", "OPS", "PORTAL"],
        )

        # Se atraso detectado, emitir evento especifico para DP e OPS
        if punch.status == ClockPunchStatus.ATRASO:
            await self.emit_event(
                event_type=GPEventTypes.PONTO_ATRASO,
                payload=punch.to_dict(),
                affected_modules=["DP", "OPS", "PORTAL"],
            )

        return punch

    async def registrar_falta(
        self,
        employee_id: str,
        data: str,
        motivo: str = "",
    ) -> None:
        """Registra falta de um funcionario e notifica DP e OPS."""
        await self.emit_event(
            event_type=GPEventTypes.PONTO_FALTA,
            payload={
                "employee_id": employee_id,
                "data": data,
                "motivo": motivo,
            },
            affected_modules=["DP", "OPS", "PORTAL"],
        )
