"""
TemplateService - Servico de Templates de Documentos Disciplinares.

Author: Conecta PRO Team
Date: 2026-01-18
Quality Score Target: 99+/100
"""

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import logger
from modules.operacional.disciplinary.models import DisciplinaryTemplate
from modules.operacional.disciplinary.models.disciplinary_template import DEFAULT_TEMPLATES
from modules.operacional.disciplinary.repositories import TemplateRepository
from modules.operacional.disciplinary.schemas import (
    TemplateCreate,
    TemplateListResponse,
    TemplateResponse,
    TemplateUpdate,
)


class TemplateServiceError(Exception):
    """Excecao base para erros do servico de templates."""

    pass


class TemplateNotFoundError(TemplateServiceError):
    """Template nao encontrado."""

    pass


class TemplateService:
    """
    Servico para gestao de templates de documentos disciplinares.

    Permite criar, atualizar e gerenciar templates com placeholders
    para geracao automatica de documentos.
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Inicializa o servico.

        Args:
            db: Sessao async do SQLAlchemy
        """
        self.db = db
        self.repo = TemplateRepository(db)

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
        template = await self.repo.create(data, tenant_id, created_by)

        logger.info(
            f"Template criado: {template.name}",
            extra={
                "template_id": template.id,
                "action_type": template.action_type,
                "tenant_id": tenant_id,
            },
        )

        return template

    async def get_by_id(self, template_id: str, tenant_id: str) -> DisciplinaryTemplate:
        """
        Busca template por ID.

        Args:
            template_id: ID do template
            tenant_id: ID do tenant

        Returns:
            Template

        Raises:
            TemplateNotFoundError: Se nao encontrado
        """
        template = await self.repo.get_by_id(template_id, tenant_id)
        if not template:
            raise TemplateNotFoundError(f"Template {template_id} nao encontrado")
        return template

    async def get_default(self, tenant_id: str, action_type: str) -> DisciplinaryTemplate | None:
        """
        Busca template padrao para um tipo.

        Args:
            tenant_id: ID do tenant
            action_type: Tipo da medida

        Returns:
            Template padrao ou None
        """
        return await self.repo.get_default(tenant_id, action_type)

    async def list(
        self,
        tenant_id: str,
        action_type: str | None = None,
    ) -> TemplateListResponse:
        """
        Lista templates.

        Args:
            tenant_id: ID do tenant
            action_type: Filtrar por tipo

        Returns:
            Lista de templates
        """
        templates = await self.repo.list(tenant_id, action_type)

        return TemplateListResponse(
            items=[TemplateResponse.model_validate(t) for t in templates],
            total=len(templates),
        )

    async def update(
        self,
        template_id: str,
        tenant_id: str,
        data: TemplateUpdate,
    ) -> DisciplinaryTemplate:
        """
        Atualiza um template.

        Args:
            template_id: ID do template
            tenant_id: ID do tenant
            data: Dados para atualizacao

        Returns:
            Template atualizado

        Raises:
            TemplateNotFoundError: Se nao encontrado
        """
        template = await self.repo.update(template_id, tenant_id, data)
        if not template:
            raise TemplateNotFoundError(f"Template {template_id} nao encontrado")

        logger.info(
            f"Template atualizado: {template.name}",
            extra={"template_id": template.id, "tenant_id": tenant_id},
        )

        return template

    async def delete(self, template_id: str, tenant_id: str) -> bool:
        """
        Remove um template (soft delete).

        Args:
            template_id: ID do template
            tenant_id: ID do tenant

        Returns:
            True se removido

        Raises:
            TemplateNotFoundError: Se nao encontrado
        """
        deleted = await self.repo.delete(template_id, tenant_id)
        if not deleted:
            raise TemplateNotFoundError(f"Template {template_id} nao encontrado")

        logger.info(
            f"Template removido: {template_id}",
            extra={"tenant_id": tenant_id},
        )

        return True

    async def initialize_defaults(self, tenant_id: str, created_by: str | None = None) -> int:
        """
        Inicializa templates padrao para um tenant.

        Cria os templates padrao se ainda nao existirem.

        Args:
            tenant_id: ID do tenant
            created_by: ID do usuario criador

        Returns:
            Quantidade de templates criados
        """
        created_count = 0

        for action_type, template_data in DEFAULT_TEMPLATES.items():
            # Verificar se ja existe template padrao para este tipo
            existing = await self.repo.get_default(tenant_id, action_type)
            if existing:
                logger.debug(
                    f"Template padrao ja existe para {action_type}",
                    extra={"tenant_id": tenant_id},
                )
                continue

            # Criar template
            from modules.operacional.disciplinary.schemas import DisciplinaryActionType

            create_data = TemplateCreate(
                action_type=DisciplinaryActionType(action_type),
                name=template_data["name"],
                description=template_data["description"],
                content=template_data["content"],
                is_default=True,
            )

            await self.repo.create(create_data, tenant_id, created_by)
            created_count += 1

            logger.info(
                f"Template padrao criado: {template_data['name']}",
                extra={"tenant_id": tenant_id, "action_type": action_type},
            )

        return created_count

    def get_available_placeholders(self) -> dict[str, str]:
        """
        Retorna placeholders disponiveis.

        Returns:
            Dicionario com placeholders e descricoes
        """
        return DisciplinaryTemplate.get_available_placeholders()

    def preview_render(self, content: str, sample_context: dict[str, str] | None = None) -> str:
        """
        Pre-visualiza renderizacao de template.

        Args:
            content: Conteudo do template
            sample_context: Contexto de exemplo

        Returns:
            Texto renderizado
        """
        if not sample_context:
            sample_context = {
                "employee_name": "JOAO DA SILVA",
                "employee_cpf": "123.456.789-00",
                "employee_position": "Porteiro",
                "employee_admission_date": "01/01/2020",
                "incident_date": "15/01/2026",
                "application_date": "18/01/2026",
                "reason_description": "Descricao do motivo da medida disciplinar.",
                "reason_category_display": "Falta Injustificada",
                "company_name": "EMPRESA EXEMPLO LTDA",
                "company_cnpj": "00.000.000/0001-00",
                "suspension_days": "3",
                "suspension_start_date": "20/01/2026",
                "suspension_end_date": "22/01/2026",
                "witness_1_name": "TESTEMUNHA UM",
                "witness_1_cpf": "111.111.111-11",
                "witness_2_name": "TESTEMUNHA DOIS",
                "witness_2_cpf": "222.222.222-22",
                "previous_warnings": "2",
                "previous_suspensions": "0",
                "city": "Manaus",
                "state": "AM",
                "current_date": "18/01/2026",
                "post_name": "Posto Centro",
                "client_name": "Cliente Exemplo",
            }

        result = content
        for key, value in sample_context.items():
            placeholder = f"{{{{{key}}}}}"
            result = result.replace(placeholder, value)

        return result


def get_template_service(db: AsyncSession) -> TemplateService:
    """
    Factory para criar instancia do servico.

    Args:
        db: Sessao do banco de dados

    Returns:
        Instancia do TemplateService
    """
    return TemplateService(db)
