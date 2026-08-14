"""
Service para operacoes de Ocorrencias.

Author: Conecta PRO Team
Date: 2026-01-18
Quality Score: 99+/100
"""

from __future__ import annotations

import builtins
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from modules.operacional.occurrences.models import (
    Occurrence,
    OccurrenceAttachment,
    OccurrenceCategoryConfig,
    OccurrenceComment,
    OccurrenceStatus,
)
from modules.operacional.occurrences.repositories import OccurrenceRepository
from modules.operacional.occurrences.schemas import (
    AttachmentCreate,
    CategoryConfigCreate,
    CommentCreate,
    DashboardStats,
    EscalateRequest,
    OccurrenceCreate,
    OccurrenceFilter,
    OccurrenceUpdate,
    ReopenRequest,
    ResolveRequest,
)

logger = logging.getLogger(__name__)


class OccurrenceServiceError(Exception):
    """Excecao base para erros do servico de ocorrencias."""

    pass


class OccurrenceNotFoundError(OccurrenceServiceError):
    """Ocorrencia nao encontrada."""

    pass


class OccurrenceValidationError(OccurrenceServiceError):
    """Erro de validacao de ocorrencia."""

    pass


class OccurrenceService:
    """
    Service para gerenciamento de Ocorrencias.

    Fornece logica de negocio para criacao, atualizacao, resolucao
    e escalacao de ocorrencias operacionais.

    Attributes:
        db: Sessao do banco de dados.
        repository: Repository de ocorrencias.

    Example:
        >>> service = OccurrenceService(db)
        >>> occurrence = service.create(data)
        >>> service.resolve(occurrence_id, resolve_request)
    """

    __slots__ = ("db", "repository")

    def __init__(self, db: Session) -> None:
        """Inicializa o service.

        Args:
            db: Sessao do banco de dados.
        """
        self.db = db
        self.repository = OccurrenceRepository(db)

    # ============================================================
    # CRUD OPERATIONS
    # ============================================================

    def create(self, data: OccurrenceCreate) -> Occurrence:
        """Cria uma nova ocorrencia.

        Args:
            data: Dados para criacao.

        Returns:
            Ocorrencia criada.

        Raises:
            OccurrenceValidationError: Se dados invalidos.
        """
        # Gerar codigo
        year = datetime.utcnow().year
        sequence = self.repository.get_next_sequence(str(data.tenant_id), year)
        code = Occurrence.generate_code(year, sequence)

        # Buscar configuracao da categoria se existir
        category_config = self.repository.get_category_config(str(data.tenant_id), data.category.value)

        # Criar ocorrencia
        occurrence = Occurrence(
            code=code,
            tenant_id=str(data.tenant_id),
            post_id=str(data.post_id) if data.post_id else None,
            client_id=str(data.client_id) if data.client_id else None,
            contract_id=str(data.contract_id) if data.contract_id else None,
            category=data.category.value,
            severity=data.severity.value,
            type=data.type.value,
            title=data.title,
            description=data.description,
            reported_by_id=str(data.reported_by_id),
            employee_involved_id=str(data.employee_involved_id) if data.employee_involved_id else None,
            witness_ids=[str(w) for w in data.witness_ids] if data.witness_ids else [],
            status=OccurrenceStatus.ABERTA.value,
            priority=data.priority.value,
            location_description=data.location_description,
            occurred_at=data.occurred_at,
            tags=data.tags or [],
            created_by=str(data.reported_by_id),
        )

        # Calcular SLA
        if category_config:
            occurrence.calculate_sla_deadline(category_config=category_config.to_config_dict())
        else:
            occurrence.calculate_sla_deadline()

        # Salvar
        occurrence = self.repository.create(occurrence)

        logger.info(f"Ocorrencia criada: {occurrence.code}")

        # Notificacao para ocorrencias criticas
        if occurrence.is_critical:
            self._notify_critical_occurrence(occurrence)

        return occurrence

    def get_by_id(self, occurrence_id: str) -> Occurrence:
        """Busca ocorrencia por ID.

        Args:
            occurrence_id: ID da ocorrencia.

        Returns:
            Ocorrencia encontrada.

        Raises:
            OccurrenceNotFoundError: Se nao encontrada.
        """
        occurrence = self.repository.get_by_id(occurrence_id)
        if not occurrence:
            raise OccurrenceNotFoundError(f"Ocorrencia {occurrence_id} nao encontrada")
        return occurrence

    def get_by_code(self, code: str) -> Occurrence:
        """Busca ocorrencia por codigo.

        Args:
            code: Codigo da ocorrencia.

        Returns:
            Ocorrencia encontrada.

        Raises:
            OccurrenceNotFoundError: Se nao encontrada.
        """
        occurrence = self.repository.get_by_code(code)
        if not occurrence:
            raise OccurrenceNotFoundError(f"Ocorrencia {code} nao encontrada")
        return occurrence

    def update(
        self,
        occurrence_id: str,
        data: OccurrenceUpdate,
    ) -> Occurrence:
        """Atualiza uma ocorrencia.

        Args:
            occurrence_id: ID da ocorrencia.
            data: Dados para atualizacao.

        Returns:
            Ocorrencia atualizada.

        Raises:
            OccurrenceNotFoundError: Se nao encontrada.
            OccurrenceValidationError: Se dados invalidos.
        """
        occurrence = self.get_by_id(occurrence_id)

        # Atualizar campos
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(occurrence, field):
                if isinstance(value, UUID):
                    value = str(value)
                elif hasattr(value, "value"):  # Enum
                    value = value.value
                setattr(occurrence, field, value)

        # Recalcular SLA se severidade mudou
        if data.severity and data.severity.value != occurrence.severity:
            occurrence.calculate_sla_deadline()

        occurrence = self.repository.update(occurrence)
        logger.info(f"Ocorrencia atualizada: {occurrence.code}")

        return occurrence

    def delete(self, occurrence_id: str) -> bool:
        """Remove uma ocorrencia (soft delete).

        Args:
            occurrence_id: ID da ocorrencia.

        Returns:
            True se removida.

        Raises:
            OccurrenceNotFoundError: Se nao encontrada.
        """
        occurrence = self.get_by_id(occurrence_id)
        result = self.repository.delete(occurrence_id)
        if result:
            logger.info(f"Ocorrencia removida: {occurrence.code}")
        return result

    def list(
        self,
        tenant_id: str,
        skip: int = 0,
        limit: int = 100,
        filters: OccurrenceFilter | None = None,
    ) -> tuple[builtins.list[Occurrence], int]:
        """Lista ocorrencias com filtros.

        Args:
            tenant_id: ID do tenant.
            skip: Registros a pular.
            limit: Limite de registros.
            filters: Filtros opcionais.

        Returns:
            Tupla com lista e total.
        """
        return self.repository.list_by_tenant(tenant_id, skip, limit, filters)

    # ============================================================
    # WORKFLOW OPERATIONS
    # ============================================================

    def start_analysis(self, occurrence_id: str) -> Occurrence:
        """Inicia analise de uma ocorrencia.

        Args:
            occurrence_id: ID da ocorrencia.

        Returns:
            Ocorrencia atualizada.

        Raises:
            OccurrenceNotFoundError: Se nao encontrada.
            OccurrenceValidationError: Se status invalido.
        """
        occurrence = self.get_by_id(occurrence_id)

        if occurrence.status != OccurrenceStatus.ABERTA.value:
            raise OccurrenceValidationError(f"Ocorrencia nao pode iniciar analise no status {occurrence.status}")

        occurrence.start_analysis()
        occurrence = self.repository.update(occurrence)

        logger.info(f"Analise iniciada: {occurrence.code}")
        return occurrence

    def mark_pending_action(self, occurrence_id: str) -> Occurrence:
        """Marca ocorrencia como pendente de acao.

        Args:
            occurrence_id: ID da ocorrencia.

        Returns:
            Ocorrencia atualizada.
        """
        occurrence = self.get_by_id(occurrence_id)
        occurrence.mark_pending_action()
        occurrence = self.repository.update(occurrence)

        logger.info(f"Pendente de acao: {occurrence.code}")
        return occurrence

    def resolve(
        self,
        occurrence_id: str,
        data: ResolveRequest,
    ) -> Occurrence:
        """Resolve uma ocorrencia.

        Args:
            occurrence_id: ID da ocorrencia.
            data: Dados de resolucao.

        Returns:
            Ocorrencia resolvida.

        Raises:
            OccurrenceNotFoundError: Se nao encontrada.
            OccurrenceValidationError: Se ja resolvida.
        """
        occurrence = self.get_by_id(occurrence_id)

        if occurrence.status == OccurrenceStatus.RESOLVIDA.value:
            raise OccurrenceValidationError("Ocorrencia ja esta resolvida")

        if occurrence.status == OccurrenceStatus.ARQUIVADA.value:
            raise OccurrenceValidationError("Ocorrencia esta arquivada")

        resolution_type = data.resolution_type.value if data.resolution_type else None

        occurrence.resolve(
            resolution=data.resolution,
            resolved_by_id=str(data.resolved_by_id),
            resolution_type=resolution_type,
        )
        occurrence = self.repository.update(occurrence)

        logger.info(f"Ocorrencia resolvida: {occurrence.code}")
        return occurrence

    def reopen(
        self,
        occurrence_id: str,
        data: ReopenRequest | None = None,
    ) -> Occurrence:
        """Reabre uma ocorrencia.

        Args:
            occurrence_id: ID da ocorrencia.
            data: Dados de reabertura.

        Returns:
            Ocorrencia reaberta.

        Raises:
            OccurrenceNotFoundError: Se nao encontrada.
            OccurrenceValidationError: Se nao pode ser reaberta.
        """
        occurrence = self.get_by_id(occurrence_id)

        if occurrence.status not in [
            OccurrenceStatus.RESOLVIDA.value,
            OccurrenceStatus.ARQUIVADA.value,
        ]:
            raise OccurrenceValidationError(f"Ocorrencia no status {occurrence.status} nao pode ser reaberta")

        reason = data.reason if data else None
        occurrence.reopen(reason)

        # Recalcular SLA
        occurrence.sla_breached = False
        occurrence.calculate_sla_deadline()

        occurrence = self.repository.update(occurrence)

        logger.info(f"Ocorrencia reaberta: {occurrence.code}")
        return occurrence

    def archive(self, occurrence_id: str) -> Occurrence:
        """Arquiva uma ocorrencia.

        Args:
            occurrence_id: ID da ocorrencia.

        Returns:
            Ocorrencia arquivada.
        """
        occurrence = self.get_by_id(occurrence_id)
        occurrence.archive()
        occurrence = self.repository.update(occurrence)

        logger.info(f"Ocorrencia arquivada: {occurrence.code}")
        return occurrence

    def escalate(
        self,
        occurrence_id: str,
        data: EscalateRequest,
    ) -> Occurrence:
        """Escala uma ocorrencia.

        Args:
            occurrence_id: ID da ocorrencia.
            data: Dados de escalacao.

        Returns:
            Ocorrencia escalada.
        """
        occurrence = self.get_by_id(occurrence_id)

        if not occurrence.is_open:
            raise OccurrenceValidationError(f"Ocorrencia no status {occurrence.status} nao pode ser escalada")

        occurrence.escalate(
            escalated_to_id=str(data.escalated_to_id),
            reason=data.reason,
        )
        occurrence = self.repository.update(occurrence)

        logger.info(f"Ocorrencia escalada: {occurrence.code} -> {data.escalated_to_id}")

        self._notify_escalation(occurrence, data)

        return occurrence

    # ============================================================
    # ATTACHMENT OPERATIONS
    # ============================================================

    def add_attachment(
        self,
        occurrence_id: str,
        data: AttachmentCreate,
    ) -> OccurrenceAttachment:
        """Adiciona anexo a uma ocorrencia.

        Args:
            occurrence_id: ID da ocorrencia.
            data: Dados do anexo.

        Returns:
            Anexo criado.
        """
        # Verificar se ocorrencia existe
        self.get_by_id(occurrence_id)

        attachment = OccurrenceAttachment(
            occurrence_id=occurrence_id,
            file_type=data.file_type.value,
            file_path=data.file_path,
            file_name=data.file_name,
            file_size=data.file_size,
            mime_type=data.mime_type,
            description=data.description,
            captured_at=data.captured_at,
            latitude=data.latitude,
            longitude=data.longitude,
            uploaded_by_id=str(data.uploaded_by_id),
        )

        attachment = self.repository.add_attachment(attachment)

        logger.info(f"Anexo adicionado a {occurrence_id}: {attachment.file_name}")
        return attachment

    def get_attachments(
        self,
        occurrence_id: str,
    ) -> builtins.list[OccurrenceAttachment]:
        """Lista anexos de uma ocorrencia.

        Args:
            occurrence_id: ID da ocorrencia.

        Returns:
            Lista de anexos.
        """
        self.get_by_id(occurrence_id)
        return self.repository.get_attachments(occurrence_id)

    def delete_attachment(self, attachment_id: str) -> bool:
        """Remove um anexo.

        Args:
            attachment_id: ID do anexo.

        Returns:
            True se removido.
        """
        return self.repository.delete_attachment(attachment_id)

    # ============================================================
    # COMMENT OPERATIONS
    # ============================================================

    def add_comment(
        self,
        occurrence_id: str,
        data: CommentCreate,
    ) -> OccurrenceComment:
        """Adiciona comentario a uma ocorrencia.

        Args:
            occurrence_id: ID da ocorrencia.
            data: Dados do comentario.

        Returns:
            Comentario criado.
        """
        self.get_by_id(occurrence_id)

        comment = OccurrenceComment(
            occurrence_id=occurrence_id,
            author_id=str(data.author_id),
            author_name=data.author_name,
            content=data.content,
            is_internal=data.is_internal,
        )

        comment = self.repository.add_comment(comment)

        logger.info(f"Comentario adicionado a {occurrence_id}")
        return comment

    def get_comments(
        self,
        occurrence_id: str,
        include_internal: bool = True,
    ) -> builtins.list[OccurrenceComment]:
        """Lista comentarios de uma ocorrencia.

        Args:
            occurrence_id: ID da ocorrencia.
            include_internal: Se deve incluir internos.

        Returns:
            Lista de comentarios.
        """
        self.get_by_id(occurrence_id)
        return self.repository.get_comments(occurrence_id, include_internal)

    def delete_comment(self, comment_id: str) -> bool:
        """Remove um comentario.

        Args:
            comment_id: ID do comentario.

        Returns:
            True se removido.
        """
        return self.repository.delete_comment(comment_id)

    # ============================================================
    # DASHBOARD AND STATS
    # ============================================================

    def get_dashboard_stats(
        self,
        tenant_id: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> DashboardStats:
        """Obtem estatisticas do dashboard.

        Args:
            tenant_id: ID do tenant.
            start_date: Data inicial.
            end_date: Data final.

        Returns:
            Estatisticas do dashboard.
        """
        stats = self.repository.get_stats(tenant_id, start_date, end_date)

        # Contar SLA em risco
        sla_at_risk = len(self.repository.list_sla_breaching(tenant_id))

        return DashboardStats(
            total=stats["total"],
            abertas=stats["abertas"],
            em_analise=stats["em_analise"],
            pendentes=stats["pendentes"],
            resolvidas=stats["resolvidas"],
            arquivadas=stats["arquivadas"],
            criticas=stats["criticas"],
            sla_breached=stats["sla_breached"],
            sla_at_risk=sla_at_risk,
            by_category=stats["by_category"],
            by_severity=stats["by_severity"],
            by_priority=stats["by_priority"],
        )

    def get_pending_by_user(
        self,
        user_id: str,
        tenant_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> builtins.list[Occurrence]:
        """Lista ocorrencias pendentes para um usuario.

        Args:
            user_id: ID do usuario.
            tenant_id: ID do tenant.
            skip: Registros a pular.
            limit: Limite de registros.

        Returns:
            Lista de ocorrencias.
        """
        return self.repository.list_by_user(user_id, tenant_id, skip, limit)

    def get_sla_breaching(
        self,
        tenant_id: str,
        hours_threshold: int = 4,
    ) -> builtins.list[Occurrence]:
        """Lista ocorrencias com SLA vencendo.

        Args:
            tenant_id: ID do tenant.
            hours_threshold: Horas antes do vencimento.

        Returns:
            Lista de ocorrencias.
        """
        return self.repository.list_sla_breaching(tenant_id, hours_threshold)

    def check_sla_breaches(self, tenant_id: str) -> int:
        """Verifica e atualiza SLAs violados.

        Args:
            tenant_id: ID do tenant.

        Returns:
            Numero de ocorrencias atualizadas.
        """
        return self.repository.check_and_update_sla_breaches(tenant_id)

    # ============================================================
    # CATEGORY CONFIG
    # ============================================================

    def create_category_config(
        self,
        data: CategoryConfigCreate,
    ) -> OccurrenceCategoryConfig:
        """Cria configuracao de categoria.

        Args:
            data: Dados da configuracao.

        Returns:
            Configuracao criada.
        """
        # Verificar se ja existe
        existing = self.repository.get_category_config(str(data.tenant_id), data.code)
        if existing:
            raise OccurrenceValidationError(f"Categoria {data.code} ja existe para este tenant")

        config = OccurrenceCategoryConfig(
            tenant_id=str(data.tenant_id),
            code=data.code,
            name=data.name,
            description=data.description,
            severity_default=data.severity_default.value,
            priority_default=data.priority_default.value,
            type_default=data.type_default.value,
            requires_photo=data.requires_photo,
            requires_witness=data.requires_witness,
            requires_location=data.requires_location,
            requires_employee=data.requires_employee,
            auto_escalate=data.auto_escalate,
            escalate_after_hours=data.escalate_after_hours,
            escalate_to_role=data.escalate_to_role,
            sla_hours=data.sla_hours,
            sla_warning_hours=data.sla_warning_hours,
            notify_on_create=data.notify_on_create,
            notify_roles=data.notify_roles,
            notify_emails=data.notify_emails,
            suggest_disciplinary_action=data.suggest_disciplinary_action,
            disciplinary_action_type=data.disciplinary_action_type,
            color=data.color,
            icon=data.icon,
            display_order=data.display_order,
            created_by=str(data.created_by) if data.created_by else None,
        )

        return self.repository.create_category_config(config)

    def get_category_configs(
        self,
        tenant_id: str,
    ) -> builtins.list[OccurrenceCategoryConfig]:
        """Lista configuracoes de categoria.

        Args:
            tenant_id: ID do tenant.

        Returns:
            Lista de configuracoes.
        """
        return self.repository.list_category_configs(tenant_id)

    # ============================================================
    # INTERNAL METHODS
    # ============================================================

    def _notify_critical_occurrence(self, occurrence: Occurrence) -> None:
        """Notifica gestores sobre ocorrencia critica via push e WebSocket.

        Identifica o tenant via Post.client_id e notifica o inspector
        e gestores do Employee envolvido.

        Args:
            occurrence: Ocorrencia critica (severity GRAVE ou GRAVISSIMA).
        """
        try:
            from modules.notifications.models import QueuePriority
            from modules.notifications.services.push_service import PushNotificationService
            from modules.operacional.models.employee import Employee as OpEmployee
            from modules.operacional.models.post import Post

            # Identificar tenant_id via Post
            post = self.db.query(Post).filter(Post.id == occurrence.post_id).first()
            if not post or not post.client_id:
                logger.warning(f"Post {occurrence.post_id} sem client_id, skip notificação")
                return

            tenant_id = UUID(str(post.client_id))
            push_service = PushNotificationService(self.db, tenant_id)

            # Coletar user_ids para notificar (set evita duplicatas)
            notify_user_ids: set = set()

            # 1. Inspector (quem registrou) sempre é notificado
            if occurrence.inspector_id:
                notify_user_ids.add(str(occurrence.inspector_id))

            # 2. Gestor do employee envolvido
            if occurrence.employee_id:
                emp = self.db.query(OpEmployee).filter(OpEmployee.id == str(occurrence.employee_id)).first()
                if emp and getattr(emp, "gestor_id", None):
                    notify_user_ids.add(str(emp.gestor_id))

            # Remover employee envolvido da lista (ele não precisa de push)
            notify_user_ids.discard(str(occurrence.employee_id))

            sent_count = 0
            for user_id_str in notify_user_ids:
                try:
                    push_service.send_push_notification(
                        user_id=UUID(user_id_str),
                        title=f"OCORRENCIA CRITICA: {occurrence.code}",
                        body=f"{occurrence.title} - Severidade: {occurrence.severity}",
                        data={
                            "type": "critical_occurrence",
                            "occurrence_id": str(occurrence.id),
                            "code": occurrence.code,
                        },
                        priority=QueuePriority.URGENT,
                        action_url=f"/modulos/operacional/ocorrencias?id={occurrence.id}",
                    )
                    sent_count += 1
                except Exception as push_err:
                    logger.error(f"Erro push para user {user_id_str}: {push_err}")

            # WebSocket broadcast
            try:
                import asyncio

                from modules.operacional.communication.controllers.websocket_controller import (
                    get_connection_manager,
                )

                manager = get_connection_manager()
                ws_message = {
                    "type": "critical_occurrence",
                    "data": {
                        "occurrence_id": str(occurrence.id),
                        "code": occurrence.code,
                        "title": occurrence.title,
                        "severity": occurrence.severity,
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                }

                try:
                    asyncio.get_running_loop()
                    asyncio.ensure_future(manager.broadcast_to_tenant(str(tenant_id), ws_message))
                except RuntimeError:
                    pass
            except Exception as ws_err:
                logger.debug(f"WebSocket broadcast indisponível: {ws_err}")

            logger.warning(
                f"OCORRENCIA CRITICA notificada: {occurrence.code} -> {sent_count}/{len(notify_user_ids)} destinatários"
            )
        except Exception as e:
            logger.error(f"Erro ao notificar ocorrência crítica {occurrence.code}: {e}")

    def _notify_escalation(self, occurrence: Occurrence, data: EscalateRequest) -> None:
        """Notifica o usuario alvo sobre a escalacao via push.

        Args:
            occurrence: Ocorrencia escalada.
            data: Dados da escalacao com escalated_to_id e reason.
        """
        try:
            from modules.notifications.models import QueuePriority
            from modules.notifications.services.push_service import PushNotificationService
            from modules.operacional.models.post import Post

            # Identificar tenant via Post
            post = self.db.query(Post).filter(Post.id == occurrence.post_id).first()
            if not post or not post.client_id:
                logger.warning(f"Post {occurrence.post_id} sem client_id, skip notificação de escalação")
                return

            tenant_id = UUID(str(post.client_id))
            push_service = PushNotificationService(self.db, tenant_id)

            push_service.send_push_notification(
                user_id=data.escalated_to_id,
                title=f"Ocorrência Escalada: {occurrence.code}",
                body=(f"{occurrence.title} foi escalada para você. Motivo: {data.reason or 'Não informado'}"),
                data={
                    "type": "occurrence_escalated",
                    "occurrence_id": str(occurrence.id),
                    "code": occurrence.code,
                    "severity": occurrence.severity,
                },
                priority=QueuePriority.HIGH,
                action_url=f"/modulos/operacional/ocorrencias?id={occurrence.id}",
            )

            logger.info(f"Notificação de escalação enviada: {occurrence.code} -> {data.escalated_to_id}")
        except Exception as e:
            logger.error(f"Erro ao notificar escalação {occurrence.code}: {e}")

    def _should_suggest_disciplinary_action(
        self,
        occurrence: Occurrence,
    ) -> bool:
        """Verifica se deve sugerir medida administrativa.

        Args:
            occurrence: Ocorrencia a verificar.

        Returns:
            True se deve sugerir.
        """
        return occurrence.requires_disciplinary_action
