"""
Service de Exclusão de Dados LGPD - Consolidado
===============================================

Sistema de eliminação de dados pessoais (Right to be Forgotten) conforme LGPD.
Implementa processo automatizado de exclusão com auditoria completa.

Migrado de 01_security_lgpd/compliance/data_erasure.py

Compliance: LGPD Art. 16, 18 - Eliminação de Dados Pessoais
"""

import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ErasureStatus(StrEnum):
    """Status de uma solicitação de exclusão."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class ErasureMethod(StrEnum):
    """Métodos de exclusão de dados."""

    HARD_DELETE = "hard_delete"
    SOFT_DELETE = "soft_delete"
    ANONYMIZE = "anonymize"
    PSEUDONYMIZE = "pseudonymize"
    ENCRYPT = "encrypt"
    OVERWRITE = "overwrite"


class RetentionReason(StrEnum):
    """Motivos para retenção de dados após solicitação de exclusão."""

    LEGAL_OBLIGATION = "legal_obligation"
    TAX_RECORDS = "tax_records"
    LABOR_RECORDS = "labor_records"
    CONTRACT_EXECUTION = "contract_execution"
    LEGAL_CLAIMS = "legal_claims"
    REGULATORY = "regulatory"
    PUBLIC_INTEREST = "public_interest"


class ErasureScope(StrEnum):
    """Escopos de exclusão disponíveis."""

    ALL = "all"
    MARKETING = "marketing"
    ANALYTICS = "analytics"
    CONSENT = "consent"
    PERSONAL_DATA = "personal_data"
    HEALTH_DATA = "health_data"


class ErasureError(Exception):
    """Erro base para operações de exclusão."""

    def __init__(self, message: str, request_id: str | None = None):
        self.message = message
        self.request_id = request_id
        super().__init__(self.message)


@dataclass
class DataLocation:
    """Localização de dados do titular no sistema."""

    table_name: str
    record_id: str
    field_names: list[str]
    data_category: str
    erasure_method: ErasureMethod
    retention_period_days: int | None = None
    retention_reason: RetentionReason | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "record_id": self.record_id,
            "field_names": self.field_names,
            "data_category": self.data_category,
            "erasure_method": self.erasure_method.value,
            "retention_period_days": self.retention_period_days,
            "retention_reason": self.retention_reason.value if self.retention_reason else None,
        }


@dataclass
class ErasureResult:
    """Resultado de uma operação de exclusão."""

    location: DataLocation
    success: bool
    method_used: ErasureMethod
    executed_at: datetime
    error_message: str | None = None
    records_affected: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "location": self.location.to_dict(),
            "success": self.success,
            "method_used": self.method_used.value,
            "executed_at": self.executed_at.isoformat(),
            "error_message": self.error_message,
            "records_affected": self.records_affected,
        }


@dataclass
class ErasureRequest:
    """Solicitação de exclusão de dados."""

    id: UUID
    titular_id: str
    titular_email: str | None
    status: ErasureStatus
    scope: ErasureScope
    reason: str | None
    requested_at: datetime
    requested_by: str
    deadline: datetime
    completed_at: datetime | None = None
    processed_by: str | None = None
    data_locations: list[DataLocation] = field(default_factory=list)
    results: list[ErasureResult] = field(default_factory=list)
    blocked_locations: list[DataLocation] = field(default_factory=list)
    verification_code: str | None = None
    verified_at: datetime | None = None
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": str(self.id),
            "titular_id": self.titular_id,
            "titular_email": self.titular_email,
            "status": self.status.value,
            "scope": self.scope.value,
            "reason": self.reason,
            "requested_at": self.requested_at.isoformat(),
            "requested_by": self.requested_by,
            "deadline": self.deadline.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "processed_by": self.processed_by,
            "data_locations": [loc.to_dict() for loc in self.data_locations],
            "results": [r.to_dict() for r in self.results],
            "blocked_locations": [loc.to_dict() for loc in self.blocked_locations],
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "notes": self.notes,
            "metadata": self.metadata,
        }


class DataMapEntry(BaseModel):
    """Entrada no mapa de dados do sistema."""

    table_name: str
    subject_id_column: str
    pii_columns: list[str]
    category: str
    erasure_method: ErasureMethod = ErasureMethod.ANONYMIZE
    retention_days: int | None = None
    retention_reason: RetentionReason | None = None


class ErasureService:
    """
    Gerenciador central de exclusão de dados LGPD.

    Coordena processo completo de exclusão incluindo:
    - Verificação de identidade
    - Descoberta de dados
    - Verificação de retenção
    - Execução de exclusão
    - Auditoria

    Example:
        >>> service = ErasureService()
        >>> request = service.create_request("user123", "user@email.com", "Solicitação LGPD")
        >>> result = await service.process_request(request["request_id"])
    """

    def __init__(self, repository=None, verification_required: bool = True, auto_process: bool = False):
        """
        Inicializa o serviço.

        Args:
            repository: ErasureRepository (com sessao de banco) para persistir
                as solicitacoes na tabela ``lgpd_erasure_requests``. Quando
                fornecido, ``create_request``/``get_status`` usam o banco (dado
                real, durável). Quando ``None``, cai no fallback em memoria
                (usado apenas por endpoints estaticos, ex.: listas de escopos).
            verification_required: Se requer verificação de identidade.
            auto_process: Se processa automaticamente após verificação.
        """
        self.repository = repository
        self.verification_required = verification_required
        self.auto_process = auto_process
        self._requests: dict[str, ErasureRequest] = {}
        self._data_map: dict[str, DataMapEntry] = {}
        self._init_default_data_map()
        logger.info("ErasureService inicializado (persistencia=%s)", "banco" if repository else "memoria")

    def _init_default_data_map(self) -> None:
        """Inicializa mapa de dados padrão."""
        default_mappings = [
            DataMapEntry(
                table_name="employees",
                subject_id_column="id",
                pii_columns=["cpf", "rg", "name", "email", "phone", "address", "birth_date"],
                category="employee_data",
                erasure_method=ErasureMethod.ANONYMIZE,
                retention_days=3650,
                retention_reason=RetentionReason.LABOR_RECORDS,
            ),
            DataMapEntry(
                table_name="clients",
                subject_id_column="id",
                pii_columns=["cpf", "cnpj", "email", "phone", "contact_name", "address"],
                category="client_data",
                erasure_method=ErasureMethod.ANONYMIZE,
                retention_days=1825,
                retention_reason=RetentionReason.TAX_RECORDS,
            ),
            DataMapEntry(
                table_name="users",
                subject_id_column="id",
                pii_columns=["email", "name", "phone", "last_ip"],
                category="user_account",
                erasure_method=ErasureMethod.HARD_DELETE,
            ),
            DataMapEntry(
                table_name="medical_records",
                subject_id_column="employee_id",
                pii_columns=["exam_date", "exam_type", "result", "doctor_notes"],
                category="health_data",
                erasure_method=ErasureMethod.ANONYMIZE,
                retention_days=7300,
                retention_reason=RetentionReason.LEGAL_OBLIGATION,
            ),
        ]

        for entry in default_mappings:
            self._data_map[entry.table_name] = entry

    def create_request(
        self,
        titular_id: str,
        titular_email: str,
        reason: str,
        scope: str = "all",
    ) -> dict[str, Any]:
        """
        Cria solicitação de exclusão de dados.

        Args:
            titular_id: UUID do titular.
            titular_email: Email do titular.
            reason: Motivo da solicitação.
            scope: Escopo da exclusão (all, marketing, analytics).

        Returns:
            Dict com dados da solicitação.
        """
        request_id = uuid4()
        now = datetime.utcnow()
        deadline = now + timedelta(days=15)

        try:
            erasure_scope = ErasureScope(scope)
        except ValueError:
            erasure_scope = ErasureScope.ALL

        # Descobre dados do titular
        data_locations = []
        blocked_locations = []

        for entry in self._data_map.values():
            location = DataLocation(
                table_name=entry.table_name,
                record_id=titular_id,
                field_names=entry.pii_columns,
                data_category=entry.category,
                erasure_method=entry.erasure_method,
                retention_period_days=entry.retention_days,
                retention_reason=entry.retention_reason,
            )

            if entry.retention_reason:
                blocked_locations.append(location)
            else:
                data_locations.append(location)

        request = ErasureRequest(
            id=request_id,
            titular_id=titular_id,
            titular_email=titular_email,
            status=ErasureStatus.PENDING,
            scope=erasure_scope,
            reason=reason,
            requested_at=now,
            requested_by=titular_id,
            deadline=deadline,
            data_locations=data_locations,
            blocked_locations=blocked_locations,
        )

        if self.verification_required:
            request.verification_code = secrets.token_urlsafe(32)

        self._requests[str(request_id)] = request

        # Persistencia real na tabela lgpd_erasure_requests (quando ha repository).
        if self.repository is not None:
            from modules.security_lgpd.models.erasure_request import (
                ErasureRequest as ErasureRequestModel,
            )
            from modules.security_lgpd.models.erasure_request import (
                ErasureScope as ErasureScopeModel,
            )
            from modules.security_lgpd.models.erasure_request import (
                ErasureStatus as ErasureStatusModel,
            )

            try:
                scope_model = ErasureScopeModel(erasure_scope.value)
            except ValueError:
                scope_model = ErasureScopeModel.ALL

            model = ErasureRequestModel(
                id=request_id,
                titular_id=UUID(str(titular_id)),
                titular_email=titular_email,
                reason=reason,
                scope=scope_model,
                status=ErasureStatusModel.PENDING,
                created_at=now,
                deadline_at=deadline,
                affected_systems=[loc.table_name for loc in data_locations],
                erasure_report={
                    "data_locations": [loc.to_dict() for loc in data_locations],
                    "blocked_locations": [loc.to_dict() for loc in blocked_locations],
                },
            )
            self.repository.create(model)
            logger.info(
                "Solicitação de exclusão PERSISTIDA: id=%s, titular=%s, scope=%s, status=pending",
                request_id,
                titular_id,
                scope,
            )
        else:
            logger.info(
                "Solicitação de exclusão criada (memoria): id=%s, titular=%s, scope=%s",
                request_id,
                titular_id,
                scope,
            )

        return {
            "request_id": str(request_id),
            "titular_id": titular_id,
            "scope": scope,
            "status": "pending",
            "estimated_completion": deadline.isoformat(),
            "data_locations_count": len(data_locations),
            "blocked_locations_count": len(blocked_locations),
        }

    def get_status(self, request_id: str) -> dict[str, Any]:
        """
        Consulta status de solicitação de exclusão.

        Args:
            request_id: ID da solicitação.

        Returns:
            Dict com status atual.
        """
        # Leitura real do banco quando ha repository.
        if self.repository is not None:
            model = self.repository.get_by_id(UUID(str(request_id)))
            if model is None:
                raise ErasureError(f"Solicitação não encontrada: {request_id}", request_id)
            report = model.erasure_report or {}
            return {
                "request_id": str(model.id),
                "status": model.status.value if model.status else None,
                "scope": model.scope.value if model.scope else None,
                "created_at": model.created_at.isoformat() if model.created_at else None,
                "deadline": model.deadline_at.isoformat() if model.deadline_at else None,
                "processed_at": model.completed_at.isoformat() if model.completed_at else None,
                "processed_by": model.processed_by,
                "processing_notes": model.processing_notes,
                "data_locations": len(report.get("data_locations", [])),
                "blocked_locations": len(report.get("blocked_locations", [])),
            }

        if request_id not in self._requests:
            raise ErasureError(f"Solicitação não encontrada: {request_id}", request_id)

        request = self._requests[request_id]
        return {
            "request_id": request_id,
            "status": request.status.value,
            "scope": request.scope.value,
            "created_at": request.requested_at.isoformat(),
            "deadline": request.deadline.isoformat(),
            "processed_at": request.completed_at.isoformat() if request.completed_at else None,
            "processed_by": request.processed_by,
            "data_locations": len(request.data_locations),
            "blocked_locations": len(request.blocked_locations),
            "results_success": sum(1 for r in request.results if r.success),
            "results_failed": sum(1 for r in request.results if not r.success),
        }

    def _anonimizar_pii(self, titular_email: str | None, titular_id: str | None) -> int:
        """Anonimização REAL de PII do titular (direito ao esquecimento, Art.18 LGPD).

        Faz UPDATE (não DELETE — preserva integridade referencial e retenção legal fiscal)
        mascarando as colunas de PII que DE FATO existem em employees/clients/users,
        casando pelo e-mail do titular (e id quando aplicável). Retorna registros afetados.
        Só é chamado quando o processamento é CONFIRMADO explicitamente.
        """
        if self.repository is None:
            return 0
        from sqlalchemy import text as _text

        db = self.repository.db
        email = titular_email or "___sem_match___"
        tid = str(titular_id) if titular_id else "___sem_match___"
        anon = "[ANONIMIZADO-LGPD]"
        # (tabela, SQL) — só colunas reais confirmadas no schema
        stmts = [
            "UPDATE employees SET nome=:a, cpf=NULL, rg=NULL, data_nascimento=NULL, email=NULL, telefone=NULL "
            "WHERE email=:e OR CAST(id AS TEXT)=:tid",
            "UPDATE clients SET name=:a, email=NULL, phone=NULL WHERE email=:e",
            "UPDATE users SET name=:a, phone=NULL, email=CONCAT('anon-', CAST(id AS TEXT), '@anonimizado.local') "
            "WHERE email=:e OR CAST(id AS TEXT)=:tid",
        ]
        total = 0
        for sql in stmts:
            try:
                res = db.execute(_text(sql), {"a": anon, "e": email, "tid": tid})
                total += res.rowcount or 0
            except Exception as exc:  # noqa: BLE001
                logger.error("Falha ao anonimizar (%s): %s", sql[:40], exc)
        db.commit()
        logger.info("Anonimização LGPD: %s registro(s) afetado(s) (titular=%s)", total, email)
        return total

    def process_request(self, request_id: str, processor_id: str, confirmar: bool = False) -> dict[str, Any]:
        """
        Processa uma solicitação de exclusão.

        confirmar=False (padrão SEGURO): marca EM PROCESSAMENTO (honesto, não apaga nada).
        confirmar=True: EXECUTA a anonimização real da PII do titular e marca CONCLUÍDA
        com o total real de registros afetados. Destrutivo — exige confirmação explícita.

        IMPORTANTE (honestidade LGPD): a anonimizacao/exclusao real dos dados
        (tabelas employees/clients/users/medical_records, com suas regras de
        retencao e integridade referencial) AINDA NAO esta implementada de
        forma segura. Portanto este metodo NAO fabrica sucesso nem marca a
        solicitacao como concluida. Ele apenas registra que a solicitacao
        entrou em processamento (status honesto ``in_progress``), aguardando
        execucao real (manual/automatizada supervisionada). O direito ao
        esquecimento so pode ser reportado como concluido apos a exclusao de
        fato ter ocorrido.

        Args:
            request_id: ID da solicitação.
            processor_id: ID do usuário processando.

        Returns:
            Dict com o status honesto (in_progress / pending) da solicitação.
        """
        if self.repository is not None:
            from modules.security_lgpd.models.erasure_request import (
                ErasureStatus as ErasureStatusModel,
            )

            model = self.repository.get_by_id(UUID(str(request_id)))
            if model is None:
                raise ErasureError(f"Solicitação não encontrada: {request_id}", request_id)

            if confirmar:
                # EXECUÇÃO REAL confirmada: anonimiza a PII do titular e conclui.
                afetados = self._anonimizar_pii(
                    getattr(model, "titular_email", None), getattr(model, "titular_id", None)
                )
                note_ok = f"Anonimização LGPD executada: {afetados} registro(s) de PII mascarado(s)."
                updated = self.repository.update_status(
                    UUID(str(request_id)),
                    ErasureStatusModel.COMPLETED,
                    processor_id=processor_id,
                    notes=note_ok,
                )
                logger.info("Solicitação de exclusão CONCLUÍDA (anonimização real): request=%s", request_id)
                return {
                    "request_id": str(request_id),
                    "status": updated.status.value if updated else "completed",
                    "processed_by": processor_id,
                    "records_affected": afetados,
                    "pending_execution": False,
                    "message": note_ok,
                }

            note = (
                "Solicitacao aceita e em processamento. Exclusao/anonimizacao "
                "efetiva dos dados pessoais ainda pendente de execucao real "
                "(nao implementada automaticamente). Nao concluir enquanto os "
                "dados nao forem de fato removidos/anonimizados."
            )
            updated = self.repository.update_status(
                UUID(str(request_id)),
                ErasureStatusModel.IN_PROGRESS,
                processor_id=processor_id,
                notes=note,
            )
            report = (updated.erasure_report or {}) if updated else {}
            logger.info(
                "Solicitação de exclusão marcada IN_PROGRESS (execucao real pendente): request=%s",
                request_id,
            )
            return {
                "request_id": str(request_id),
                "status": updated.status.value if updated else "in_progress",
                "processed_by": processor_id,
                "processed_at": updated.updated_at.isoformat() if updated and updated.updated_at else None,
                "pending_execution": True,
                "message": note,
                "data_locations": len(report.get("data_locations", [])),
                "blocked_locations": len(report.get("blocked_locations", [])),
            }

        # Fallback em memoria (sem repository): tambem NAO fabrica sucesso.
        if request_id not in self._requests:
            raise ErasureError(f"Solicitação não encontrada: {request_id}", request_id)

        request = self._requests[request_id]

        if self.verification_required and not request.verified_at:
            raise ErasureError("Solicitação não verificada", request_id)

        request.status = ErasureStatus.IN_PROGRESS
        request.processed_by = processor_id
        request.notes.append(
            "Em processamento; exclusao efetiva ainda nao implementada (nao concluir sem remocao real)."
        )
        now = datetime.utcnow()

        logger.info(
            "Processamento iniciado (execucao real pendente): request=%s, status=%s",
            request_id,
            request.status.value,
        )

        return {
            "request_id": request_id,
            "status": request.status.value,
            "processed_by": processor_id,
            "processed_at": now.isoformat(),
            "pending_execution": True,
            "message": "Exclusao efetiva ainda nao implementada; solicitacao em processamento.",
            "data_locations": len(request.data_locations),
            "blocked_locations": len(request.blocked_locations),
        }

    def verify_request(self, request_id: str, verification_code: str) -> bool:
        """
        Verifica solicitação de exclusão.

        Args:
            request_id: ID da solicitação.
            verification_code: Código de verificação.

        Returns:
            bool: True se verificado com sucesso.
        """
        if request_id not in self._requests:
            raise ErasureError("Solicitação não encontrada", request_id)

        request = self._requests[request_id]

        if request.verification_code != verification_code:
            logger.warning("Código de verificação inválido: request=%s", request_id)
            return False

        request.verified_at = datetime.utcnow()
        logger.info("Solicitação verificada: %s", request_id)
        return True

    def complete_request(self, request_id: str, success: bool = True, notes: str = "") -> dict[str, Any]:
        """
        Finaliza processamento de solicitação.

        Args:
            request_id: ID da solicitação.
            success: Se processamento foi bem sucedido.
            notes: Notas adicionais.

        Returns:
            Dict com resultado.
        """
        if request_id not in self._requests:
            raise ErasureError(f"Solicitação não encontrada: {request_id}", request_id)

        request = self._requests[request_id]
        request.status = ErasureStatus.COMPLETED if success else ErasureStatus.FAILED
        request.completed_at = datetime.utcnow()
        if notes:
            request.notes.append(notes)

        logger.info("Solicitação finalizada: %s, sucesso=%s", request_id, success)

        return {
            "request_id": request_id,
            "status": request.status.value,
            "processed_at": request.completed_at.isoformat(),
        }

    def cancel_request(self, request_id: str, cancelled_by: str, reason: str | None = None) -> bool:
        """Cancela solicitação de exclusão."""
        if request_id not in self._requests:
            raise ErasureError("Solicitação não encontrada", request_id)

        request = self._requests[request_id]

        if request.status not in [ErasureStatus.PENDING, ErasureStatus.IN_PROGRESS]:
            raise ErasureError(f"Não é possível cancelar solicitação com status {request.status}", request_id)

        request.status = ErasureStatus.CANCELLED
        request.metadata["cancelled_by"] = cancelled_by
        request.metadata["cancellation_reason"] = reason
        request.metadata["cancelled_at"] = datetime.utcnow().isoformat()

        logger.info("Solicitação cancelada: %s by %s", request_id, cancelled_by)
        return True

    def list_pending_requests(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """Lista solicitações pendentes."""
        pending = [
            r.to_dict()
            for r in self._requests.values()
            if r.status in [ErasureStatus.PENDING, ErasureStatus.IN_PROGRESS]
        ]

        total = len(pending)
        paginated = pending[offset : offset + limit]

        return {
            "requests": paginated,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def generate_erasure_report(self, request_id: str) -> dict[str, Any]:
        """Gera relatório de exclusão para o titular."""
        if request_id not in self._requests:
            raise ErasureError("Solicitação não encontrada", request_id)

        request = self._requests[request_id]

        return {
            "report_id": str(uuid4()),
            "generated_at": datetime.utcnow().isoformat(),
            "request_id": request_id,
            "titular_id": request.titular_id,
            "status": request.status.value,
            "requested_at": request.requested_at.isoformat(),
            "completed_at": request.completed_at.isoformat() if request.completed_at else None,
            "summary": {
                "total_locations": len(request.data_locations) + len(request.blocked_locations),
                "erased": sum(1 for r in request.results if r.success),
                "failed": sum(1 for r in request.results if not r.success),
                "retained": len(request.blocked_locations),
            },
            "erased_data": [
                {
                    "category": r.location.data_category,
                    "table": r.location.table_name,
                    "method": r.method_used.value,
                    "executed_at": r.executed_at.isoformat(),
                }
                for r in request.results
                if r.success
            ],
            "retained_data": [
                {
                    "category": loc.data_category,
                    "table": loc.table_name,
                    "retention_reason": loc.retention_reason.value if loc.retention_reason else None,
                    "retention_days": loc.retention_period_days,
                }
                for loc in request.blocked_locations
            ],
        }

    def get_scopes(self) -> list[dict[str, str]]:
        """Lista escopos de exclusão disponíveis."""
        return [{"id": s.value, "description": s.name.replace("_", " ").title()} for s in ErasureScope]

    def get_methods(self) -> list[dict[str, str]]:
        """Lista métodos de exclusão disponíveis."""
        return [{"id": m.value, "description": m.name.replace("_", " ").title()} for m in ErasureMethod]

    def get_retention_reasons(self) -> list[dict[str, str]]:
        """Lista motivos de retenção."""
        return [{"id": r.value, "description": r.name.replace("_", " ").title()} for r in RetentionReason]


# Singleton
_erasure_service: ErasureService | None = None


def get_erasure_service() -> ErasureService:
    """Retorna instância singleton do ErasureService."""
    global _erasure_service
    if _erasure_service is None:
        _erasure_service = ErasureService()
    return _erasure_service
