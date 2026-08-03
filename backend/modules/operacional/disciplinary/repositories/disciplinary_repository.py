"""
Repositories para o modulo de Medidas Administrativas.

Implementa acesso a dados para:
- DisciplinaryAction
- DisciplinaryTemplate
- DigitalSignature

Author: Conecta PRO Team
Date: 2026-01-18
Quality Score Target: 99+/100
"""

from __future__ import annotations

import builtins
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import logger
from modules.operacional.disciplinary.models import (
    DigitalSignature,
    DisciplinaryAction,
    DisciplinaryActionStatus,
    DisciplinaryActionType,
    DisciplinaryTemplate,
)
from modules.operacional.disciplinary.schemas import (
    DisciplinaryActionCreate,
    DisciplinaryActionUpdate,
    DisciplinaryFilter,
    DisciplinaryStats,
    SignatureCreate,
    TemplateCreate,
    TemplateUpdate,
)


class DisciplinaryRepository:
    """
    Repository para operacoes CRUD de DisciplinaryAction.

    Implementa todas as operacoes de banco de dados para medidas
    disciplinares, incluindo filtros avancados e estatisticas.
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Inicializa o repository.

        Args:
            db: Sessao async do SQLAlchemy
        """
        self.db = db

    async def _generate_code(self, action_type: str, tenant_id: str) -> str:
        """
        Gera codigo unico para a medida disciplinar.

        Formato: {PREFIXO}-{ANO}-{SEQUENCIAL:05d}
        Exemplos: ADV-2026-00001, SUS-2026-00001, JCA-2026-00001

        Args:
            action_type: Tipo da medida
            tenant_id: ID do tenant

        Returns:
            Codigo unico gerado
        """
        prefix_map = {
            DisciplinaryActionType.ADVERTENCIA_VERBAL.value: "ADV",
            DisciplinaryActionType.ADVERTENCIA_ESCRITA.value: "ADV",
            DisciplinaryActionType.SUSPENSAO.value: "SUS",
            DisciplinaryActionType.DEMISSAO_JUSTA_CAUSA.value: "JCA",
        }
        prefix = prefix_map.get(action_type, "MED")
        year = datetime.now().year

        # MAX GLOBAL do sequencial p/ prefixo+ano (a constraint `code` é UNIQUE global, não
        # per-tenant). COUNT per-tenant colidia entre tenants e com gaps de deleção; MAX global
        # do sufixo numérico garante código único e robusto a gaps.
        result = await self.db.execute(
            text("SELECT COALESCE(MAX(CAST(split_part(code,'-',3) AS INTEGER)),0) "
                 "FROM disciplinary_actions WHERE code LIKE :p"),
            {"p": f"{prefix}-{year}-%"})
        max_seq = int(result.scalar() or 0)

        return f"{prefix}-{year}-{max_seq + 1:05d}"

    async def create(
        self,
        data: DisciplinaryActionCreate,
        tenant_id: str,
        created_by: str | None = None,
    ) -> DisciplinaryAction:
        """
        Cria uma nova medida disciplinar.

        Args:
            data: Dados da medida
            tenant_id: ID do tenant
            created_by: ID do usuario criador

        Returns:
            Medida disciplinar criada
        """
        code = await self._generate_code(data.action_type.value, tenant_id)

        # Busca historico do funcionario
        previous_warnings, previous_suspensions = await self._get_employee_history(tenant_id, data.employee_id)

        action = DisciplinaryAction(
            id=str(uuid4()),
            code=code,
            tenant_id=tenant_id,
            action_type=data.action_type.value,
            status=DisciplinaryActionStatus.RASCUNHO.value,
            employee_id=data.employee_id,
            employee_name=data.employee_name,
            employee_cpf=data.employee_cpf,
            employee_position=data.employee_position,
            employee_admission_date=data.employee_admission_date,
            post_id=data.post_id,
            client_id=data.client_id,
            reason_category=data.reason_category.value,
            reason_description=data.reason_description,
            occurrence_id=data.occurrence_id,
            incident_date=data.incident_date,
            suspension_start_date=data.suspension_start_date,
            suspension_end_date=data.suspension_end_date,
            suspension_days=data.suspension_days,
            witness_1_name=data.witness_1_name,
            witness_1_cpf=data.witness_1_cpf,
            witness_2_name=data.witness_2_name,
            witness_2_cpf=data.witness_2_cpf,
            document_template_id=data.document_template_id,
            requires_approval=data.requires_approval,
            previous_warnings_count=previous_warnings,
            previous_suspensions_count=previous_suspensions,
            created_by=created_by,
        )

        self.db.add(action)
        await self.db.commit()
        await self.db.refresh(action)

        logger.info(
            f"Medida disciplinar criada: {action.code}",
            extra={
                "action_id": action.id,
                "action_type": action.action_type,
                "employee_id": action.employee_id,
                "tenant_id": tenant_id,
            },
        )

        return action

    async def _get_employee_history(self, tenant_id: str, employee_id: str) -> tuple[int, int]:
        """
        Busca historico disciplinar do funcionario.

        Args:
            tenant_id: ID do tenant
            employee_id: ID do funcionario

        Returns:
            Tupla (advertencias, suspensoes)
        """
        warnings_result = await self.db.execute(
            select(func.count(DisciplinaryAction.id)).where(
                and_(
                    DisciplinaryAction.tenant_id == tenant_id,
                    DisciplinaryAction.employee_id == employee_id,
                    DisciplinaryAction.is_active.is_(True),
                    DisciplinaryAction.status == DisciplinaryActionStatus.APLICADA.value,
                    DisciplinaryAction.action_type.in_(
                        [
                            DisciplinaryActionType.ADVERTENCIA_VERBAL.value,
                            DisciplinaryActionType.ADVERTENCIA_ESCRITA.value,
                        ]
                    ),
                )
            )
        )
        warnings = warnings_result.scalar() or 0

        suspensions_result = await self.db.execute(
            select(func.count(DisciplinaryAction.id)).where(
                and_(
                    DisciplinaryAction.tenant_id == tenant_id,
                    DisciplinaryAction.employee_id == employee_id,
                    DisciplinaryAction.is_active.is_(True),
                    DisciplinaryAction.status == DisciplinaryActionStatus.APLICADA.value,
                    DisciplinaryAction.action_type == DisciplinaryActionType.SUSPENSAO.value,
                )
            )
        )
        suspensions = suspensions_result.scalar() or 0

        return warnings, suspensions

    async def get_by_id(self, action_id: str, tenant_id: str) -> DisciplinaryAction | None:
        """
        Busca medida disciplinar por ID.

        Args:
            action_id: ID da medida
            tenant_id: ID do tenant

        Returns:
            Medida disciplinar ou None
        """
        result = await self.db.execute(
            select(DisciplinaryAction).where(
                and_(
                    DisciplinaryAction.id == action_id,
                    DisciplinaryAction.tenant_id == tenant_id,
                    DisciplinaryAction.is_active.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str, tenant_id: str) -> DisciplinaryAction | None:
        """
        Busca medida disciplinar por codigo.

        Args:
            code: Codigo da medida
            tenant_id: ID do tenant

        Returns:
            Medida disciplinar ou None
        """
        result = await self.db.execute(
            select(DisciplinaryAction).where(
                and_(
                    DisciplinaryAction.code == code,
                    DisciplinaryAction.tenant_id == tenant_id,
                    DisciplinaryAction.is_active.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        tenant_id: str,
        filters: DisciplinaryFilter | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[builtins.list[DisciplinaryAction], int]:
        """
        Lista medidas disciplinares com filtros e paginacao.

        Args:
            tenant_id: ID do tenant
            filters: Filtros de busca
            page: Pagina atual (1-indexed)
            page_size: Itens por pagina

        Returns:
            Tupla (lista de medidas, total)
        """
        base_condition = and_(
            DisciplinaryAction.tenant_id == tenant_id,
            DisciplinaryAction.is_active.is_(True),
        )

        query = select(DisciplinaryAction).where(base_condition)
        count_query = select(func.count(DisciplinaryAction.id)).where(base_condition)

        if filters:
            query = self._apply_filters(query, filters)
            count_query = self._apply_filters(count_query, filters)

        # Total
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginacao e ordenacao
        query = query.order_by(DisciplinaryAction.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        actions = list(result.scalars().all())

        return actions, total

    def _apply_filters(self, query: Any, filters: DisciplinaryFilter) -> Any:
        """
        Aplica filtros a query.

        Args:
            query: Query base
            filters: Filtros a aplicar

        Returns:
            Query com filtros aplicados
        """
        if filters.action_type:
            query = query.where(DisciplinaryAction.action_type == filters.action_type.value)

        if filters.status:
            query = query.where(DisciplinaryAction.status == filters.status.value)

        if filters.reason_category:
            query = query.where(DisciplinaryAction.reason_category == filters.reason_category.value)

        if filters.employee_id:
            query = query.where(DisciplinaryAction.employee_id == filters.employee_id)

        if filters.post_id:
            query = query.where(DisciplinaryAction.post_id == filters.post_id)

        if filters.client_id:
            query = query.where(DisciplinaryAction.client_id == filters.client_id)

        if filters.incident_date_from:
            query = query.where(DisciplinaryAction.incident_date >= filters.incident_date_from)

        if filters.incident_date_to:
            query = query.where(DisciplinaryAction.incident_date <= filters.incident_date_to)

        if filters.created_at_from:
            query = query.where(DisciplinaryAction.created_at >= filters.created_at_from)

        if filters.created_at_to:
            query = query.where(DisciplinaryAction.created_at <= filters.created_at_to)

        if filters.search:
            search_term = f"%{filters.search}%"
            query = query.where(
                or_(
                    DisciplinaryAction.code.ilike(search_term),
                    DisciplinaryAction.employee_name.ilike(search_term),
                    DisciplinaryAction.reason_description.ilike(search_term),
                )
            )

        return query

    async def update(
        self,
        action_id: str,
        tenant_id: str,
        data: DisciplinaryActionUpdate,
    ) -> DisciplinaryAction | None:
        """
        Atualiza uma medida disciplinar.

        Args:
            action_id: ID da medida
            tenant_id: ID do tenant
            data: Dados para atualizacao

        Returns:
            Medida atualizada ou None
        """
        action = await self.get_by_id(action_id, tenant_id)
        if not action:
            return None

        if not action.can_be_edited:
            logger.warning(
                f"Tentativa de editar medida em status invalido: {action.code}",
                extra={"action_id": action_id, "status": action.status},
            )
            return None

        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if hasattr(value, "value"):  # Enum
                setattr(action, field, value.value)
            else:
                setattr(action, field, value)

        action.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(action)

        logger.info(
            f"Medida disciplinar atualizada: {action.code}",
            extra={"action_id": action.id, "tenant_id": tenant_id},
        )

        return action

    async def delete(self, action_id: str, tenant_id: str) -> bool:
        """
        Soft delete de medida disciplinar.

        Args:
            action_id: ID da medida
            tenant_id: ID do tenant

        Returns:
            True se deletado
        """
        action = await self.get_by_id(action_id, tenant_id)
        if not action:
            return False

        action.is_active = False
        action.status = DisciplinaryActionStatus.CANCELADA.value
        action.updated_at = datetime.utcnow()

        await self.db.commit()

        logger.info(
            f"Medida disciplinar deletada (soft): {action.code}",
            extra={"action_id": action.id, "tenant_id": tenant_id},
        )

        return True

    async def update_status(
        self,
        action_id: str,
        tenant_id: str,
        new_status: DisciplinaryActionStatus,
        **kwargs: Any,
    ) -> DisciplinaryAction | None:
        """
        Atualiza status de uma medida disciplinar.

        Args:
            action_id: ID da medida
            tenant_id: ID do tenant
            new_status: Novo status
            **kwargs: Campos adicionais para atualizar

        Returns:
            Medida atualizada ou None
        """
        action = await self.get_by_id(action_id, tenant_id)
        if not action:
            return None

        old_status = action.status
        action.status = new_status.value

        for key, value in kwargs.items():
            if hasattr(action, key):
                setattr(action, key, value)

        action.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(action)

        logger.info(
            f"Status da medida {action.code} alterado: {old_status} -> {new_status.value}",
            extra={"action_id": action.id, "tenant_id": tenant_id},
        )

        return action

    async def get_by_employee(
        self,
        employee_id: str,
        tenant_id: str,
        include_inactive: bool = False,
    ) -> builtins.list[DisciplinaryAction]:
        """
        Lista todas as medidas de um funcionario.

        Args:
            employee_id: ID do funcionario
            tenant_id: ID do tenant
            include_inactive: Se inclui inativos

        Returns:
            Lista de medidas
        """
        conditions = [
            DisciplinaryAction.tenant_id == tenant_id,
            DisciplinaryAction.employee_id == employee_id,
        ]

        if not include_inactive:
            conditions.append(DisciplinaryAction.is_active.is_(True))

        result = await self.db.execute(
            select(DisciplinaryAction).where(and_(*conditions)).order_by(DisciplinaryAction.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_pending_approval(self, tenant_id: str) -> builtins.list[DisciplinaryAction]:
        """
        Lista medidas pendentes de aprovacao.

        Args:
            tenant_id: ID do tenant

        Returns:
            Lista de medidas pendentes
        """
        result = await self.db.execute(
            select(DisciplinaryAction)
            .where(
                and_(
                    DisciplinaryAction.tenant_id == tenant_id,
                    DisciplinaryAction.is_active.is_(True),
                    DisciplinaryAction.status == DisciplinaryActionStatus.PENDENTE_APROVACAO.value,
                )
            )
            .order_by(DisciplinaryAction.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_stats(self, tenant_id: str) -> DisciplinaryStats:
        """
        Obtem estatisticas de medidas disciplinares.

        Args:
            tenant_id: ID do tenant

        Returns:
            Estatisticas
        """
        base_condition = and_(
            DisciplinaryAction.tenant_id == tenant_id,
            DisciplinaryAction.is_active.is_(True),
        )

        # Total
        total_result = await self.db.execute(select(func.count(DisciplinaryAction.id)).where(base_condition))
        total = total_result.scalar() or 0

        # Por tipo
        type_result = await self.db.execute(
            select(DisciplinaryAction.action_type, func.count(DisciplinaryAction.id))
            .where(base_condition)
            .group_by(DisciplinaryAction.action_type)
        )
        by_type = dict(type_result.all())

        # Por status
        status_result = await self.db.execute(
            select(DisciplinaryAction.status, func.count(DisciplinaryAction.id))
            .where(base_condition)
            .group_by(DisciplinaryAction.status)
        )
        by_status = dict(status_result.all())

        # Por categoria de motivo
        category_result = await self.db.execute(
            select(DisciplinaryAction.reason_category, func.count(DisciplinaryAction.id))
            .where(base_condition)
            .group_by(DisciplinaryAction.reason_category)
        )
        by_reason_category = dict(category_result.all())

        # Pendentes de aprovacao
        pending_approval = by_status.get(DisciplinaryActionStatus.PENDENTE_APROVACAO.value, 0)

        # Pendentes de assinatura
        pending_signature = by_status.get(DisciplinaryActionStatus.PENDENTE_ASSINATURA.value, 0)

        # Aplicadas este mes
        today = date.today()
        first_day_of_month = today.replace(day=1)
        applied_month_result = await self.db.execute(
            select(func.count(DisciplinaryAction.id)).where(
                and_(
                    base_condition,
                    DisciplinaryAction.status == DisciplinaryActionStatus.APLICADA.value,
                    DisciplinaryAction.application_date >= first_day_of_month,
                )
            )
        )
        applied_this_month = applied_month_result.scalar() or 0

        # Aplicadas este ano
        first_day_of_year = today.replace(month=1, day=1)
        applied_year_result = await self.db.execute(
            select(func.count(DisciplinaryAction.id)).where(
                and_(
                    base_condition,
                    DisciplinaryAction.status == DisciplinaryActionStatus.APLICADA.value,
                    DisciplinaryAction.application_date >= first_day_of_year,
                )
            )
        )
        applied_this_year = applied_year_result.scalar() or 0

        # Funcionarios com advertencias
        employees_warnings_result = await self.db.execute(
            select(func.count(func.distinct(DisciplinaryAction.employee_id))).where(
                and_(
                    base_condition,
                    DisciplinaryAction.status == DisciplinaryActionStatus.APLICADA.value,
                    DisciplinaryAction.action_type.in_(
                        [
                            DisciplinaryActionType.ADVERTENCIA_VERBAL.value,
                            DisciplinaryActionType.ADVERTENCIA_ESCRITA.value,
                        ]
                    ),
                )
            )
        )
        employees_with_warnings = employees_warnings_result.scalar() or 0

        # Funcionarios com suspensoes
        employees_suspensions_result = await self.db.execute(
            select(func.count(func.distinct(DisciplinaryAction.employee_id))).where(
                and_(
                    base_condition,
                    DisciplinaryAction.status == DisciplinaryActionStatus.APLICADA.value,
                    DisciplinaryAction.action_type == DisciplinaryActionType.SUSPENSAO.value,
                )
            )
        )
        employees_with_suspensions = employees_suspensions_result.scalar() or 0

        return DisciplinaryStats(
            total=total,
            by_type=by_type,
            by_status=by_status,
            by_reason_category=by_reason_category,
            pending_approval=pending_approval,
            pending_signature=pending_signature,
            applied_this_month=applied_this_month,
            applied_this_year=applied_this_year,
            employees_with_warnings=employees_with_warnings,
            employees_with_suspensions=employees_with_suspensions,
        )


class TemplateRepository:
    """Repository para operacoes CRUD de DisciplinaryTemplate."""

    def __init__(self, db: AsyncSession) -> None:
        """
        Inicializa o repository.

        Args:
            db: Sessao async do SQLAlchemy
        """
        self.db = db

    async def create(
        self,
        data: TemplateCreate,
        tenant_id: str,
        created_by: str | None = None,
    ) -> DisciplinaryTemplate:
        """
        Cria um novo template.

        Args:
            data: Dados do template
            tenant_id: ID do tenant
            created_by: ID do usuario criador

        Returns:
            Template criado
        """
        # Se for default, remove flag de outros templates do mesmo tipo
        if data.is_default:
            await self._unset_default(tenant_id, data.action_type.value)

        template = DisciplinaryTemplate(
            id=str(uuid4()),
            tenant_id=tenant_id,
            action_type=data.action_type.value,
            name=data.name,
            description=data.description,
            content=data.content,
            is_default=data.is_default,
            created_by=created_by,
        )

        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)

        logger.info(
            f"Template criado: {template.name}",
            extra={"template_id": template.id, "tenant_id": tenant_id},
        )

        return template

    async def _unset_default(self, tenant_id: str, action_type: str) -> None:
        """Remove flag is_default de templates do mesmo tipo."""
        result = await self.db.execute(
            select(DisciplinaryTemplate).where(
                and_(
                    DisciplinaryTemplate.tenant_id == tenant_id,
                    DisciplinaryTemplate.action_type == action_type,
                    DisciplinaryTemplate.is_default.is_(True),
                )
            )
        )
        templates = result.scalars().all()
        for template in templates:
            template.is_default = False

    async def get_by_id(self, template_id: str, tenant_id: str) -> DisciplinaryTemplate | None:
        """
        Busca template por ID.

        Args:
            template_id: ID do template
            tenant_id: ID do tenant

        Returns:
            Template ou None
        """
        result = await self.db.execute(
            select(DisciplinaryTemplate).where(
                and_(
                    DisciplinaryTemplate.id == template_id,
                    DisciplinaryTemplate.tenant_id == tenant_id,
                    DisciplinaryTemplate.is_active.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_default(self, tenant_id: str, action_type: str) -> DisciplinaryTemplate | None:
        """
        Busca template padrao para um tipo de medida.

        Args:
            tenant_id: ID do tenant
            action_type: Tipo da medida

        Returns:
            Template padrao ou None
        """
        result = await self.db.execute(
            select(DisciplinaryTemplate).where(
                and_(
                    DisciplinaryTemplate.tenant_id == tenant_id,
                    DisciplinaryTemplate.action_type == action_type,
                    DisciplinaryTemplate.is_default.is_(True),
                    DisciplinaryTemplate.is_active.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        tenant_id: str,
        action_type: str | None = None,
    ) -> builtins.list[DisciplinaryTemplate]:
        """
        Lista templates.

        Args:
            tenant_id: ID do tenant
            action_type: Filtrar por tipo (opcional)

        Returns:
            Lista de templates
        """
        conditions = [
            DisciplinaryTemplate.tenant_id == tenant_id,
            DisciplinaryTemplate.is_active.is_(True),
        ]

        if action_type:
            conditions.append(DisciplinaryTemplate.action_type == action_type)

        result = await self.db.execute(
            select(DisciplinaryTemplate)
            .where(and_(*conditions))
            .order_by(DisciplinaryTemplate.action_type, DisciplinaryTemplate.name)
        )
        return list(result.scalars().all())

    async def update(
        self,
        template_id: str,
        tenant_id: str,
        data: TemplateUpdate,
    ) -> DisciplinaryTemplate | None:
        """
        Atualiza um template.

        Args:
            template_id: ID do template
            tenant_id: ID do tenant
            data: Dados para atualizacao

        Returns:
            Template atualizado ou None
        """
        template = await self.get_by_id(template_id, tenant_id)
        if not template:
            return None

        update_data = data.model_dump(exclude_unset=True)

        # Se esta setando como default, remove de outros
        if update_data.get("is_default"):
            await self._unset_default(tenant_id, template.action_type)

        for field, value in update_data.items():
            setattr(template, field, value)

        template.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(template)

        logger.info(
            f"Template atualizado: {template.name}",
            extra={"template_id": template.id, "tenant_id": tenant_id},
        )

        return template

    async def delete(self, template_id: str, tenant_id: str) -> bool:
        """
        Soft delete de template.

        Args:
            template_id: ID do template
            tenant_id: ID do tenant

        Returns:
            True se deletado
        """
        template = await self.get_by_id(template_id, tenant_id)
        if not template:
            return False

        template.is_active = False
        template.updated_at = datetime.utcnow()

        await self.db.commit()

        logger.info(
            f"Template deletado (soft): {template.name}",
            extra={"template_id": template.id, "tenant_id": tenant_id},
        )

        return True


class SignatureRepository:
    """Repository para operacoes CRUD de DigitalSignature."""

    def __init__(self, db: AsyncSession) -> None:
        """
        Inicializa o repository.

        Args:
            db: Sessao async do SQLAlchemy
        """
        self.db = db

    async def create(
        self,
        data: SignatureCreate,
        tenant_id: str,
    ) -> DigitalSignature:
        """
        Cria uma nova assinatura digital.

        Args:
            data: Dados da assinatura
            tenant_id: ID do tenant

        Returns:
            Assinatura criada
        """
        signature = DigitalSignature(
            id=str(uuid4()),
            tenant_id=tenant_id,
            signer_id=data.signer_id,
            signer_type=data.signer_type.value,
            signer_name=data.signer_name,
            signer_cpf=data.signer_cpf,
            signer_email=data.signer_email,
            document_type=data.document_type,
            document_id=data.document_id,
            signature_data=data.signature_data,
            signature_hash=data.signature_hash,
            ip_address=data.ip_address,
            user_agent=data.user_agent,
            latitude=data.latitude,
            longitude=data.longitude,
            geolocation_accuracy=data.geolocation_accuracy,
            validated_at=datetime.utcnow(),
        )

        self.db.add(signature)
        await self.db.commit()
        await self.db.refresh(signature)

        logger.info(
            "Assinatura digital criada",
            extra={
                "signature_id": signature.id,
                "signer_type": signature.signer_type,
                "document_id": signature.document_id,
                "tenant_id": tenant_id,
            },
        )

        return signature

    async def get_by_id(self, signature_id: str, tenant_id: str) -> DigitalSignature | None:
        """
        Busca assinatura por ID.

        Args:
            signature_id: ID da assinatura
            tenant_id: ID do tenant

        Returns:
            Assinatura ou None
        """
        result = await self.db.execute(
            select(DigitalSignature).where(
                and_(
                    DigitalSignature.id == signature_id,
                    DigitalSignature.tenant_id == tenant_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_document(self, document_type: str, document_id: str, tenant_id: str) -> list[DigitalSignature]:
        """
        Lista assinaturas de um documento.

        Args:
            document_type: Tipo do documento
            document_id: ID do documento
            tenant_id: ID do tenant

        Returns:
            Lista de assinaturas
        """
        result = await self.db.execute(
            select(DigitalSignature)
            .where(
                and_(
                    DigitalSignature.tenant_id == tenant_id,
                    DigitalSignature.document_type == document_type,
                    DigitalSignature.document_id == document_id,
                )
            )
            .order_by(DigitalSignature.created_at.asc())
        )
        return list(result.scalars().all())

    async def invalidate(self, signature_id: str, tenant_id: str, reason: str) -> DigitalSignature | None:
        """
        Invalida uma assinatura.

        Args:
            signature_id: ID da assinatura
            tenant_id: ID do tenant
            reason: Motivo da invalidacao

        Returns:
            Assinatura invalidada ou None
        """
        signature = await self.get_by_id(signature_id, tenant_id)
        if not signature:
            return None

        signature.invalidate(reason)

        await self.db.commit()
        await self.db.refresh(signature)

        logger.info(
            f"Assinatura invalidada: {signature_id}",
            extra={"reason": reason, "tenant_id": tenant_id},
        )

        return signature
