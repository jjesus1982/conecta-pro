"""
Service de Auditoria LGPD - Consolidado
=======================================

Sistema de logging de auditoria para compliance LGPD com
rastreabilidade completa de acesso a dados pessoais.

Migrado de 01_security_lgpd/audit/audit_logger.py

Compliance: LGPD Art. 37, 49 - Registro de Operações de Tratamento
"""

import asyncio
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

# Context variable para rastreamento de requisição
_request_context: ContextVar[dict[str, Any] | None] = ContextVar("request_context", default=None)


class AuditAction(StrEnum):
    """Ações auditáveis no sistema."""

    # Operações de dados
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXPORT = "export"
    IMPORT = "import"
    # Autenticação
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PASSWORD_CHANGE = "password_change"  # noqa: S105
    PASSWORD_RESET = "password_reset"  # noqa: S105
    MFA_ENABLED = "mfa_enabled"
    MFA_DISABLED = "mfa_disabled"
    # Autorização
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_REVOKED = "permission_revoked"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_REMOVED = "role_removed"
    ACCESS_DENIED = "access_denied"
    # LGPD
    CONSENT_GRANTED = "consent_granted"
    CONSENT_WITHDRAWN = "consent_withdrawn"
    DATA_ACCESS_REQUEST = "data_access_request"
    DATA_ERASURE_REQUEST = "data_erasure_request"
    DATA_PORTABILITY = "data_portability"
    PII_ACCESSED = "pii_accessed"
    PII_MODIFIED = "pii_modified"
    # Sistema
    CONFIG_CHANGE = "config_change"
    SYSTEM_ERROR = "system_error"
    SECURITY_ALERT = "security_alert"
    BACKUP_CREATED = "backup_created"
    BACKUP_RESTORED = "backup_restored"
    # Criptografia
    ENCRYPT = "encrypt"
    DECRYPT = "decrypt"
    MASK = "mask"
    ERASURE = "erasure"


class AuditSeverity(StrEnum):
    """Níveis de severidade de eventos."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ResourceType(StrEnum):
    """Tipos de recursos auditados."""

    USER = "user"
    EMPLOYEE = "employee"
    CLIENT = "client"
    CONTRACT = "contract"
    DOCUMENT = "document"
    REPORT = "report"
    CONFIGURATION = "configuration"
    PERMISSION = "permission"
    CONSENT = "consent"
    MEDICAL_RECORD = "medical_record"
    PAYROLL = "payroll"
    SYSTEM = "system"
    DATA = "data"
    AUDIT = "audit"


@dataclass
class AuditContext:
    """Contexto de uma operação auditada."""

    request_id: str
    user_id: str | None = None
    user_email: str | None = None
    user_role: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    session_id: str | None = None
    tenant_id: str | None = None
    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "user_email": self.user_email,
            "user_role": self.user_role,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "correlation_id": self.correlation_id,
        }


@dataclass
class AuditEntry:
    """Entrada de log de auditoria."""

    id: UUID
    timestamp: datetime
    action: AuditAction
    severity: AuditSeverity
    resource_type: ResourceType
    resource_id: str | None
    context: AuditContext
    description: str
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    pii_fields_accessed: list[str] = field(default_factory=list)
    success: bool = True
    error_message: str | None = None
    duration_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    previous_hash: str | None = None
    hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "timestamp": self.timestamp.isoformat(),
            "action": self.action.value,
            "severity": self.severity.value,
            "resource_type": self.resource_type.value,
            "resource_id": self.resource_id,
            "context": self.context.to_dict(),
            "description": self.description,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "pii_fields_accessed": self.pii_fields_accessed,
            "success": self.success,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            "hash": self.hash,
        }

    def to_json(self) -> str:
        """Serializa para JSON."""
        return json.dumps(self.to_dict(), default=str, ensure_ascii=False)


class AuditStoreInterface(ABC):
    """Interface abstrata para armazenamento de logs."""

    @abstractmethod
    async def store(self, entry: AuditEntry) -> bool:
        """Armazena entrada de auditoria."""
        pass

    @abstractmethod
    async def query(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        user_id: str | None = None,
        resource_type: ResourceType | None = None,
        action: AuditAction | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEntry]:
        """Consulta logs de auditoria."""
        pass


class InMemoryAuditStore(AuditStoreInterface):
    """Armazenamento em memória para desenvolvimento."""

    def __init__(self, max_entries: int = 10000):
        self._entries: list[AuditEntry] = []
        self._max_entries = max_entries
        self._lock = asyncio.Lock()
        self._last_hash = "0" * 64

    def _calculate_hash(self, entry: AuditEntry) -> str:
        """Calcula hash do evento para hash chain."""
        content = f"{self._last_hash}{entry.timestamp.isoformat()}{entry.action.value}{entry.resource_id}"
        return hashlib.sha256(content.encode()).hexdigest()

    async def store(self, entry: AuditEntry) -> bool:
        async with self._lock:
            entry.previous_hash = self._last_hash
            entry.hash = self._calculate_hash(entry)
            self._last_hash = entry.hash

            self._entries.append(entry)
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries :]
            return True

    async def query(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        user_id: str | None = None,
        resource_type: ResourceType | None = None,
        action: AuditAction | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEntry]:
        async with self._lock:
            results = self._entries.copy()

            if start_date:
                results = [e for e in results if e.timestamp >= start_date]
            if end_date:
                results = [e for e in results if e.timestamp <= end_date]
            if user_id:
                results = [e for e in results if e.context.user_id == user_id]
            if resource_type:
                results = [e for e in results if e.resource_type == resource_type]
            if action:
                results = [e for e in results if e.action == action]

            results.sort(key=lambda x: x.timestamp, reverse=True)
            return results[offset : offset + limit]

    async def verify_chain_integrity(self) -> dict[str, Any]:
        """Verifica integridade da cadeia de hashes."""
        async with self._lock:
            if not self._entries:
                return {"valid": True, "total_logs": 0, "message": "Cadeia vazia"}

            previous_hash = "0" * 64
            for i, entry in enumerate(self._entries):
                if entry.previous_hash != previous_hash:
                    return {
                        "valid": False,
                        "total_logs": len(self._entries),
                        "error_at": i,
                        "message": f"Hash inconsistente no log {i}",
                    }
                previous_hash = entry.hash

            return {
                "valid": True,
                "total_logs": len(self._entries),
                "message": "Cadeia íntegra",
            }


class DatabaseAuditStore(AuditStoreInterface):
    """Armazenamento de logs de auditoria em banco (``lgpd_audit_logs``).

    Persiste cada ``AuditEntry`` na tabela ``lgpd_audit_logs`` via
    ``AuditRepository``, garantindo durabilidade e compartilhamento entre
    workers (ao contrario do ``InMemoryAuditStore``).

    As operacoes do repository sao sincronas (SQLAlchemy ORM classico); por
    isso rodamos cada chamada em thread (``asyncio.to_thread``) para nao
    bloquear o event loop e usamos uma sessao sincrona propria por operacao.
    """

    def __init__(self):
        # Import tardio para evitar dependencia circular / custo de import.
        from core.database.session import SyncSessionLocal

        self._session_factory = SyncSessionLocal

    def _map_action(self, action: "AuditAction"):
        """Mapeia a AuditAction do service para a do model (subconjunto)."""
        from modules.security_lgpd.models.audit_log import AuditAction as ModelAction

        valid = {a.value for a in ModelAction}
        return ModelAction(action.value) if action.value in valid else ModelAction.READ

    def _map_resource_type(self, resource_type: "ResourceType"):
        """Mapeia o ResourceType do service para o do model (subconjunto)."""
        from modules.security_lgpd.models.audit_log import ResourceType as ModelResource

        valid = {r.value for r in ModelResource}
        return ModelResource(resource_type.value) if resource_type.value in valid else ModelResource.DATA

    def _map_severity(self, severity: "AuditSeverity"):
        from modules.security_lgpd.models.audit_log import AuditSeverity as ModelSeverity

        valid = {s.value for s in ModelSeverity}
        return ModelSeverity(severity.value) if severity.value in valid else ModelSeverity.INFO

    def _store_sync(self, entry: "AuditEntry") -> bool:
        from modules.security_lgpd.models.audit_log import AuditLog
        from modules.security_lgpd.repositories.audit_repository import AuditRepository

        session = self._session_factory()
        try:
            repo = AuditRepository(session)
            previous_hash = repo.get_last_hash()
            content = (
                f"{previous_hash or ('0' * 64)}"
                f"{entry.timestamp.isoformat()}{entry.action.value}{entry.resource_id}"
            )
            event_hash = hashlib.sha256(content.encode()).hexdigest()
            entry.previous_hash = previous_hash
            entry.hash = event_hash

            details = dict(entry.metadata or {})
            details["description"] = entry.description
            if entry.pii_fields_accessed:
                details["pii_fields_accessed"] = entry.pii_fields_accessed
            if entry.success is not None:
                details["success"] = entry.success
            if entry.error_message:
                details["error_message"] = entry.error_message

            log = AuditLog(
                id=entry.id,
                action=self._map_action(entry.action),
                resource_type=self._map_resource_type(entry.resource_type),
                resource_id=str(entry.resource_id) if entry.resource_id else "-",
                user_id=str(entry.context.user_id) if entry.context.user_id else "system",
                severity=self._map_severity(entry.severity),
                details=details,
                ip_address=entry.context.ip_address,
                user_agent=entry.context.user_agent,
                created_at=entry.timestamp,
                event_hash=event_hash,
                previous_hash=previous_hash,
            )
            repo.create(log)
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    async def store(self, entry: "AuditEntry") -> bool:
        return await asyncio.to_thread(self._store_sync, entry)

    def _query_sync(
        self,
        start_date: datetime | None,
        end_date: datetime | None,
        user_id: str | None,
        resource_type: "ResourceType | None",
        action: "AuditAction | None",
        limit: int,
        offset: int,
    ) -> list["AuditEntry"]:
        from modules.security_lgpd.repositories.audit_repository import AuditRepository

        session = self._session_factory()
        try:
            repo = AuditRepository(session)
            rt = self._map_resource_type(resource_type) if resource_type else None
            act = self._map_action(action) if action else None
            rows = repo.query(
                action=act,
                resource_type=rt,
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=offset,
            )
            entries: list[AuditEntry] = []
            for row in rows:
                details = dict(row.details or {})
                entries.append(
                    AuditEntry(
                        id=row.id,
                        timestamp=row.created_at,
                        action=AuditAction(row.action.value)
                        if row.action.value in [a.value for a in AuditAction]
                        else AuditAction.READ,
                        severity=AuditSeverity(row.severity.value)
                        if row.severity and row.severity.value in [s.value for s in AuditSeverity]
                        else AuditSeverity.INFO,
                        resource_type=ResourceType(row.resource_type.value)
                        if row.resource_type.value in [r.value for r in ResourceType]
                        else ResourceType.DATA,
                        resource_id=row.resource_id,
                        context=AuditContext(
                            request_id=str(row.id),
                            user_id=row.user_id,
                            ip_address=row.ip_address,
                            user_agent=row.user_agent,
                        ),
                        description=details.get("description", ""),
                        pii_fields_accessed=details.get("pii_fields_accessed", []),
                        success=details.get("success", True),
                        error_message=details.get("error_message"),
                        metadata=details,
                        previous_hash=row.previous_hash,
                        hash=row.event_hash,
                    )
                )
            return entries
        finally:
            session.close()

    async def query(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        user_id: str | None = None,
        resource_type: "ResourceType | None" = None,
        action: "AuditAction | None" = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list["AuditEntry"]:
        return await asyncio.to_thread(
            self._query_sync, start_date, end_date, user_id, resource_type, action, limit, offset
        )


class AuditService:
    """
    Logger de auditoria centralizado para compliance LGPD.

    Registra todas as operações relevantes com contexto completo
    para rastreabilidade e conformidade legal.

    Example:
        >>> audit = AuditService(store)
        >>> await audit.log(
        ...     action=AuditAction.READ,
        ...     resource_type=ResourceType.EMPLOYEE,
        ...     resource_id="emp123",
        ...     description="Visualização de dados do funcionário",
        ...     pii_fields=["cpf", "salary"]
        ... )
    """

    def __init__(
        self,
        store: AuditStoreInterface | None = None,
        app_name: str = "conecta-pro",
        enable_console_output: bool = False,
        mask_pii_in_logs: bool = True,
    ):
        """
        Inicializa o logger de auditoria.

        Args:
            store: Backend de armazenamento.
            app_name: Nome da aplicação.
            enable_console_output: Se imprime logs no console.
            mask_pii_in_logs: Se mascara PII nos valores logados.
        """
        # Por padrao, persiste em banco (lgpd_audit_logs). O store em memoria
        # so e usado se explicitamente injetado (ex.: testes).
        self.store = store or DatabaseAuditStore()
        self.app_name = app_name
        self.enable_console = enable_console_output
        self.mask_pii = mask_pii_in_logs
        self._pii_fields = {
            "cpf",
            "cnpj",
            "rg",
            "email",
            "phone",
            "password",
            "salary",
            "bank_account",
            "credit_card",
            "address",
            "birth_date",
            "health_data",
            "biometric",
        }
        logger.info("AuditService inicializado para %s", app_name)

    def set_context(self, **kwargs) -> None:
        """Define contexto da requisição atual."""
        ctx = (_request_context.get() or {}).copy()
        ctx.update(kwargs)
        _request_context.set(ctx)

    def get_context(self) -> AuditContext:
        """Recupera contexto da requisição atual."""
        ctx = _request_context.get() or {}
        return AuditContext(
            request_id=ctx.get("request_id", str(uuid4())),
            user_id=ctx.get("user_id"),
            user_email=ctx.get("user_email"),
            user_role=ctx.get("user_role"),
            ip_address=ctx.get("ip_address"),
            user_agent=ctx.get("user_agent"),
            session_id=ctx.get("session_id"),
            tenant_id=ctx.get("tenant_id"),
            correlation_id=ctx.get("correlation_id"),
        )

    def clear_context(self) -> None:
        """Limpa contexto da requisição."""
        _request_context.set({})

    def _mask_pii_values(self, data: dict[str, Any] | None) -> dict[str, Any] | None:
        """Mascara valores PII nos dados."""
        if not data or not self.mask_pii:
            return data

        masked = data.copy()
        for key in masked:
            if key.lower() in self._pii_fields:
                value = masked[key]
                if isinstance(value, str) and len(value) > 4:
                    masked[key] = value[:2] + "*" * (len(value) - 4) + value[-2:]
                else:
                    masked[key] = "****"
        return masked

    async def log(
        self,
        action: AuditAction,
        resource_type: ResourceType,
        description: str,
        resource_id: str | None = None,
        severity: AuditSeverity = AuditSeverity.INFO,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
        pii_fields: list[str] | None = None,
        success: bool = True,
        error_message: str | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Registra evento de auditoria."""
        entry = AuditEntry(
            id=uuid4(),
            timestamp=datetime.utcnow(),
            action=action,
            severity=severity,
            resource_type=resource_type,
            resource_id=resource_id,
            context=self.get_context(),
            description=description,
            old_value=self._mask_pii_values(old_value),
            new_value=self._mask_pii_values(new_value),
            pii_fields_accessed=pii_fields or [],
            success=success,
            error_message=error_message,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )

        await self.store.store(entry)

        if self.enable_console:
            self._console_output(entry)

        return entry

    def _console_output(self, entry: AuditEntry) -> None:
        """Imprime entrada no console."""
        level_map = {
            AuditSeverity.DEBUG: logging.DEBUG,
            AuditSeverity.INFO: logging.INFO,
            AuditSeverity.WARNING: logging.WARNING,
            AuditSeverity.ERROR: logging.ERROR,
            AuditSeverity.CRITICAL: logging.CRITICAL,
        }
        log_level = level_map.get(entry.severity, logging.INFO)
        logger.log(
            log_level,
            "[AUDIT] %s | %s | %s:%s | %s | user=%s",
            entry.action.value,
            entry.severity.value,
            entry.resource_type.value,
            entry.resource_id or "-",
            entry.description,
            entry.context.user_id or "anonymous",
        )

    # Métodos de conveniência
    async def log_login(
        self, user_id: str, user_email: str, success: bool = True, failure_reason: str | None = None
    ) -> AuditEntry:
        """Log de tentativa de login."""
        return await self.log(
            action=AuditAction.LOGIN if success else AuditAction.LOGIN_FAILED,
            resource_type=ResourceType.USER,
            resource_id=user_id,
            description=f"Login {'bem sucedido' if success else 'falhou'}: {user_email}",
            severity=AuditSeverity.INFO if success else AuditSeverity.WARNING,
            success=success,
            error_message=failure_reason,
            metadata={"email": user_email},
        )

    async def log_logout(self, user_id: str) -> AuditEntry:
        """Log de logout."""
        return await self.log(
            action=AuditAction.LOGOUT,
            resource_type=ResourceType.USER,
            resource_id=user_id,
            description="Usuário deslogado",
        )

    async def log_data_access(
        self, resource_type: ResourceType, resource_id: str, description: str, pii_fields: list[str] | None = None
    ) -> AuditEntry:
        """Log de acesso a dados."""
        action = AuditAction.PII_ACCESSED if pii_fields else AuditAction.READ
        return await self.log(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            pii_fields=pii_fields,
        )

    async def log_data_modification(
        self,
        resource_type: ResourceType,
        resource_id: str,
        description: str,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
        pii_fields: list[str] | None = None,
    ) -> AuditEntry:
        """Log de modificação de dados."""
        action = AuditAction.PII_MODIFIED if pii_fields else AuditAction.UPDATE
        return await self.log(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            old_value=old_value,
            new_value=new_value,
            pii_fields=pii_fields,
        )

    async def log_consent_change(self, subject_id: str, action_type: str, purposes: list[str]) -> AuditEntry:
        """Log de alteração de consentimento."""
        action = AuditAction.CONSENT_GRANTED if action_type == "granted" else AuditAction.CONSENT_WITHDRAWN
        return await self.log(
            action=action,
            resource_type=ResourceType.CONSENT,
            resource_id=subject_id,
            description=f"Consentimento {action_type} para: {', '.join(purposes)}",
            metadata={"purposes": purposes},
        )

    async def log_security_event(
        self, description: str, severity: AuditSeverity = AuditSeverity.WARNING, metadata: dict[str, Any] | None = None
    ) -> AuditEntry:
        """Log de evento de segurança."""
        return await self.log(
            action=AuditAction.SECURITY_ALERT,
            resource_type=ResourceType.SYSTEM,
            description=description,
            severity=severity,
            metadata=metadata,
        )

    # Métodos de consulta
    async def query(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        user_id: str | None = None,
        resource_type: ResourceType | None = None,
        action: AuditAction | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEntry]:
        """Consulta logs de auditoria."""
        return await self.store.query(
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            resource_type=resource_type,
            action=action,
            limit=limit,
            offset=offset,
        )

    async def get_user_activity(self, user_id: str, days: int = 30) -> list[AuditEntry]:
        """Recupera atividade de um usuário."""
        start_date = datetime.utcnow() - timedelta(days=days)
        return await self.query(start_date=start_date, user_id=user_id, limit=1000)

    async def get_pii_access_report(self, start_date: datetime, end_date: datetime) -> dict[str, Any]:
        """Gera relatório de acesso a PII."""
        entries = await self.query(
            start_date=start_date, end_date=end_date, action=AuditAction.PII_ACCESSED, limit=10000
        )

        report = {
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "total_access_events": len(entries),
            "unique_users": len({e.context.user_id for e in entries if e.context.user_id}),
            "by_resource_type": {},
            "by_pii_field": {},
            "by_user": {},
        }

        for entry in entries:
            rt = entry.resource_type.value
            report["by_resource_type"][rt] = report["by_resource_type"].get(rt, 0) + 1
            for pii_field in entry.pii_fields_accessed:
                report["by_pii_field"][pii_field] = report["by_pii_field"].get(pii_field, 0) + 1
            user = entry.context.user_id or "anonymous"
            report["by_user"][user] = report["by_user"].get(user, 0) + 1

        return report

    async def verify_chain_integrity(self) -> dict[str, Any]:
        """Verifica integridade da cadeia de hashes."""
        if isinstance(self.store, InMemoryAuditStore):
            return await self.store.verify_chain_integrity()
        return {"valid": True, "message": "Verificação disponível apenas para InMemoryStore"}

    # Métodos síncronos para compatibilidade
    def log_event(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        user_id: str,
        details: dict[str, Any] | None = None,
        severity: str = "info",
    ) -> dict[str, Any]:
        """Registra evento de auditoria (síncrono - compatibilidade)."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()

        self.set_context(user_id=user_id)

        try:
            entry = loop.run_until_complete(
                self.log(
                    action=AuditAction(action) if action in [a.value for a in AuditAction] else AuditAction.READ,
                    resource_type=ResourceType(resource_type)
                    if resource_type in [r.value for r in ResourceType]
                    else ResourceType.DATA,
                    resource_id=resource_id,
                    description=f"{action} em {resource_type}:{resource_id}",
                    metadata=details or {},
                    severity=AuditSeverity(severity)
                    if severity in [s.value for s in AuditSeverity]
                    else AuditSeverity.INFO,
                )
            )
            return {
                "log_id": str(entry.id),
                "action": action,
                "resource_type": resource_type,
                "timestamp": entry.timestamp.isoformat(),
                "hash": entry.hash[:16] + "..." if entry.hash else None,
            }
        finally:
            self.clear_context()

    def query_logs(
        self,
        resource_type: str | None = None,
        user_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Consulta eventos de auditoria (síncrono - compatibilidade)."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()

        rt = ResourceType(resource_type) if resource_type and resource_type in [r.value for r in ResourceType] else None
        entries = loop.run_until_complete(
            self.query(
                start_date=start_date, end_date=end_date, user_id=user_id, resource_type=rt, limit=limit, offset=offset
            )
        )

        return {"logs": [e.to_dict() for e in entries], "total": len(entries), "limit": limit, "offset": offset}

    def get_actions(self) -> list[dict[str, str]]:
        """Lista ações de auditoria disponíveis."""
        return [{"id": a.value, "description": a.name.replace("_", " ").title()} for a in AuditAction]

    def get_resource_types(self) -> list[dict[str, str]]:
        """Lista tipos de recurso auditados."""
        return [{"id": r.value, "description": r.name.replace("_", " ").title()} for r in ResourceType]


# Decorador para auditoria automática
def audit_action(
    action: AuditAction, resource_type: ResourceType, description_template: str, pii_fields: list[str] | None = None
):
    """Decorador para auditoria automática de funções."""

    def decorator(func):
        async def wrapper(*args, **kwargs):
            audit = get_audit_service()
            start_time = datetime.utcnow()
            resource_id = kwargs.get("resource_id") or kwargs.get("id") or (args[0] if args else None)

            try:
                result = await func(*args, **kwargs)
                duration = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                await audit.log(
                    action=action,
                    resource_type=resource_type,
                    resource_id=str(resource_id) if resource_id else None,
                    description=description_template.format(resource_id=resource_id),
                    pii_fields=pii_fields,
                    success=True,
                    duration_ms=duration,
                )
                return result
            except Exception as e:
                duration = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                await audit.log(
                    action=action,
                    resource_type=resource_type,
                    resource_id=str(resource_id) if resource_id else None,
                    description=description_template.format(resource_id=resource_id),
                    severity=AuditSeverity.ERROR,
                    success=False,
                    error_message=str(e),
                    duration_ms=duration,
                )
                raise

        return wrapper

    return decorator


# Singleton
_audit_service: AuditService | None = None


def get_audit_service() -> AuditService:
    """Retorna instância singleton do AuditService."""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service


def init_audit_service(
    store: AuditStoreInterface | None = None, app_name: str = "conecta-pro", enable_console: bool = False
) -> AuditService:
    """Inicializa o AuditService singleton."""
    global _audit_service
    _audit_service = AuditService(store, app_name, enable_console)
    return _audit_service
