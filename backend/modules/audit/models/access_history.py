"""
AccessHistory Model - Histórico de Acessos
Sprint 33: Auditoria e Compliance
"""

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID

from core.database import Base


class AccessType(StrEnum):
    """Tipo de acesso."""

    LOGIN = "login"
    LOGOUT = "logout"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    TOKEN_REFRESH = "token_refresh"  # noqa: S105
    API_ACCESS = "api_access"
    RESOURCE_ACCESS = "resource_access"
    FILE_ACCESS = "file_access"
    ADMIN_ACCESS = "admin_access"
    SUDO = "sudo"
    MFA_CHALLENGE = "mfa_challenge"
    PASSWORD_RESET = "password_reset"  # noqa: S105


class AccessResult(StrEnum):
    """Resultado do acesso."""

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    LOCKED = "locked"
    EXPIRED = "expired"
    MFA_REQUIRED = "mfa_required"
    RATE_LIMITED = "rate_limited"
    SUSPICIOUS = "suspicious"


class DeviceType(StrEnum):
    """Tipo de dispositivo."""

    DESKTOP = "desktop"
    LAPTOP = "laptop"
    MOBILE = "mobile"
    TABLET = "tablet"
    API_CLIENT = "api_client"
    IOT = "iot"
    UNKNOWN = "unknown"


class RiskLevel(StrEnum):
    """Nível de risco."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AccessHistory(Base):
    """
    Model para histórico de acessos.
    Registra todos os acessos ao sistema para segurança e auditoria.
    """

    __tablename__ = "access_history"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Identificação
    session_id = Column(String(100), nullable=True)
    request_id = Column(String(50), nullable=True)

    # Tipo e Resultado
    access_type = Column(Enum(AccessType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    result = Column(Enum(AccessResult, values_callable=lambda x: [e.value for e in x]), nullable=False)

    # Usuário
    user_id = Column(UUID(as_uuid=True), nullable=True)
    user_email = Column(String(255), nullable=True)
    user_name = Column(String(200), nullable=True)
    user_role = Column(String(100), nullable=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=True)

    # Autenticação
    auth_method = Column(String(50), nullable=True)
    auth_provider = Column(String(100), nullable=True)
    mfa_used = Column(Boolean, nullable=False, default=False)
    mfa_method = Column(String(50), nullable=True)

    # Recurso acessado
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    resource_path = Column(String(500), nullable=True)
    http_method = Column(String(10), nullable=True)
    action = Column(String(100), nullable=True)

    # Contexto de rede
    ip_address = Column(INET, nullable=True)
    ip_type = Column(String(20), nullable=True)
    ip_reputation = Column(String(50), nullable=True)
    proxy_detected = Column(Boolean, nullable=False, default=False)
    vpn_detected = Column(Boolean, nullable=False, default=False)
    tor_detected = Column(Boolean, nullable=False, default=False)

    # Geolocalização
    geo_country = Column(String(100), nullable=True)
    geo_country_code = Column(String(3), nullable=True)
    geo_region = Column(String(100), nullable=True)
    geo_city = Column(String(100), nullable=True)
    geo_latitude = Column(String(20), nullable=True)
    geo_longitude = Column(String(20), nullable=True)
    geo_timezone = Column(String(50), nullable=True)
    geo_isp = Column(String(200), nullable=True)

    # Dispositivo
    device_type = Column(
        Enum(DeviceType, values_callable=lambda x: [e.value for e in x]), nullable=True, default=DeviceType.UNKNOWN
    )
    device_fingerprint = Column(String(64), nullable=True)
    device_id = Column(String(100), nullable=True)
    device_name = Column(String(200), nullable=True)
    device_trusted = Column(Boolean, nullable=False, default=False)

    # User Agent
    user_agent = Column(String(500), nullable=True)
    browser_name = Column(String(100), nullable=True)
    browser_version = Column(String(50), nullable=True)
    os_name = Column(String(100), nullable=True)
    os_version = Column(String(50), nullable=True)

    # Risco
    risk_level = Column(
        Enum(RiskLevel, values_callable=lambda x: [e.value for e in x]), nullable=True, default=RiskLevel.LOW
    )
    risk_score = Column(Integer, nullable=True)
    risk_factors = Column(JSONB, nullable=True)
    anomaly_detected = Column(Boolean, nullable=False, default=False)
    anomaly_type = Column(String(100), nullable=True)

    # Falha
    failure_reason = Column(String(200), nullable=True)
    failure_code = Column(String(50), nullable=True)
    attempts_count = Column(Integer, nullable=True)
    locked_until = Column(DateTime, nullable=True)

    # Contexto
    context = Column(JSONB, nullable=True)
    headers = Column(JSONB, nullable=True)
    response_time_ms = Column(Integer, nullable=True)

    # Alertas
    alert_triggered = Column(Boolean, nullable=False, default=False)
    alert_ids = Column(JSONB, nullable=True)
    requires_review = Column(Boolean, nullable=False, default=False)
    reviewed_by = Column(UUID(as_uuid=True), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_notes = Column(Text, nullable=True)

    # Metadados
    extra_metadata = Column(JSONB, nullable=True)
    tags = Column(JSONB, nullable=True)

    # Timestamp
    accessed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Índices
    __table_args__ = (
        Index("ix_access_history_session_id", "session_id"),
        Index("ix_access_history_user_id", "user_id"),
        Index("ix_access_history_access_type", "access_type"),
        Index("ix_access_history_result", "result"),
        Index("ix_access_history_ip_address", "ip_address"),
        Index("ix_access_history_device_fingerprint", "device_fingerprint"),
        Index("ix_access_history_risk_level", "risk_level"),
        Index("ix_access_history_accessed_at", "accessed_at"),
        Index("ix_access_history_requires_review", "requires_review"),
        Index("ix_access_history_anomaly_detected", "anomaly_detected"),
        Index("ix_access_history_user_type_date", "user_id", "access_type", "accessed_at"),
        Index("ix_access_history_ip_date", "ip_address", "accessed_at"),
    )

    def __repr__(self) -> str:
        return f"<AccessHistory {self.access_type.value} - {self.result.value}>"

    @classmethod
    def create_login(
        cls, user_id: str, user_email: str, ip_address: str, result: AccessResult, **kwargs
    ) -> "AccessHistory":
        """Cria registro de login."""
        return cls(
            access_type=AccessType.LOGIN,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            result=result,
            **kwargs,
        )

    @classmethod
    def create_api_access(
        cls,
        user_id: str | None,
        resource_path: str,
        http_method: str,
        ip_address: str,
        result: AccessResult,
        response_time_ms: int | None = None,
        **kwargs,
    ) -> "AccessHistory":
        """Cria registro de acesso API."""
        return cls(
            access_type=AccessType.API_ACCESS,
            user_id=user_id,
            resource_path=resource_path,
            http_method=http_method,
            ip_address=ip_address,
            result=result,
            response_time_ms=response_time_ms,
            **kwargs,
        )

    def calculate_risk(self) -> None:
        """Calcula nível de risco baseado em fatores."""
        factors = []
        score = 0

        if self.tor_detected:
            factors.append("tor_network")
            score += 30

        if self.vpn_detected:
            factors.append("vpn_detected")
            score += 10

        if self.proxy_detected:
            factors.append("proxy_detected")
            score += 10

        if self.result == AccessResult.FAILURE:
            factors.append("failed_access")
            score += 15

        if self.result == AccessResult.DENIED:
            factors.append("access_denied")
            score += 20

        if self.attempts_count and self.attempts_count > 3:
            factors.append("multiple_attempts")
            score += 25

        if self.anomaly_detected:
            factors.append("anomaly")
            score += 30

        if not self.device_trusted:
            factors.append("untrusted_device")
            score += 5

        self.risk_factors = factors
        self.risk_score = min(score, 100)

        if score >= 70:
            self.risk_level = RiskLevel.CRITICAL
        elif score >= 50:
            self.risk_level = RiskLevel.HIGH
        elif score >= 25:
            self.risk_level = RiskLevel.MEDIUM
        else:
            self.risk_level = RiskLevel.LOW

    def flag_anomaly(self, anomaly_type: str) -> None:
        """Marca como anomalia."""
        self.anomaly_detected = True
        self.anomaly_type = anomaly_type
        self.requires_review = True
        self.calculate_risk()

    def trigger_alert(self, alert_ids: list) -> None:
        """Registra alertas disparados."""
        self.alert_triggered = True
        self.alert_ids = alert_ids
        self.requires_review = True

    def complete_review(self, reviewer_id: str, notes: str | None = None) -> None:
        """Completa revisão."""
        self.requires_review = False
        self.reviewed_by = reviewer_id
        self.reviewed_at = datetime.utcnow()
        if notes:
            self.review_notes = notes

    def mark_device_trusted(self) -> None:
        """Marca dispositivo como confiável."""
        self.device_trusted = True
        self.calculate_risk()

    @property
    def is_successful(self) -> bool:
        """Verifica se foi acesso bem-sucedido."""
        return self.result == AccessResult.SUCCESS

    @property
    def is_suspicious(self) -> bool:
        """Verifica se é acesso suspeito."""
        return (
            self.result == AccessResult.SUSPICIOUS
            or self.anomaly_detected
            or self.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        )

    @property
    def is_from_new_location(self) -> bool:
        """Verifica se é de nova localização."""
        if not self.metadata:
            return False
        return self.metadata.get("new_location", False)

    @property
    def is_from_new_device(self) -> bool:
        """Verifica se é de novo dispositivo."""
        if not self.metadata:
            return False
        return self.metadata.get("new_device", False)

    @property
    def needs_attention(self) -> bool:
        """Verifica se precisa atenção."""
        return self.requires_review or self.alert_triggered or self.risk_level == RiskLevel.CRITICAL
