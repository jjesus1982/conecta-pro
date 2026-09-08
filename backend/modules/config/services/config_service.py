"""
ConfigService - Serviço principal de Configurações e Multi-tenant
Sprint 35: Configurações e Multi-tenant
"""
# pylint: disable=too-many-public-methods,too-many-locals

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from modules.config.models import (
    ConfigScope,
    FeatureFlag,
    FlagStatus,
    FlagType,
    NotificationChannel,
    NotificationTemplate,
    NotificationType,
    RolloutStrategy,
    SettingCategory,
    SettingType,
    SystemConfig,
    TemplateStatus,
    Tenant,
    TenantPlan,
    TenantSettings,
    TenantStatus,
    TenantType,
)
from modules.config.repositories import ConfigRepository
from modules.config.schemas import (
    ConfigDashboard,
    FeatureFlagCreate,
    FeatureFlagGradualRollout,
    FeatureFlagUpdate,
    NotificationTemplateCreate,
    NotificationTemplateUpdate,
    SystemConfigCreate,
    SystemConfigUpdate,
    TenantAddressUpdate,
    TenantCreate,
    TenantDashboard,
    TenantPlanUpdate,
    TenantSettingsCreate,
    TenantSettingsUpdate,
    TenantUpdate,
)

logger = logging.getLogger(__name__)


class ConfigService:
    """Serviço para configurações e multi-tenant."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repository = ConfigRepository(db)

    # ==================== Tenant ====================

    async def create_tenant(self, data: TenantCreate) -> Tenant:
        """Cria novo tenant."""
        tenant = Tenant(
            codigo=data.codigo,
            nome=data.nome,
            nome_fantasia=data.nome_fantasia,
            descricao=data.descricao,
            tenant_type=TenantType(data.tenant_type),
            status=TenantStatus.TRIAL,
            plan=TenantPlan(data.plan),
            cnpj=data.cnpj,
            email=data.email,
            telefone=data.telefone,
            celular=data.celular,
            website=data.website,
            max_usuarios=data.max_usuarios,
            max_storage_gb=data.max_storage_gb,
            max_api_calls_month=10000,
        )

        if data.trial_days and data.trial_days > 0:
            tenant.trial_ends_at = datetime.utcnow() + timedelta(days=data.trial_days)

        result = await self.repository.create_tenant(tenant)
        logger.info("Tenant criado: %s", result.codigo)
        return result

    async def get_tenant(self, tenant_id: UUID) -> Tenant | None:
        """Busca tenant por ID."""
        return await self.repository.get_tenant_by_id(tenant_id)

    async def get_tenant_by_codigo(self, codigo: str) -> Tenant | None:
        """Busca tenant por código."""
        return await self.repository.get_tenant_by_codigo(codigo)

    async def get_tenant_by_domain(self, domain: str) -> Tenant | None:
        """Busca tenant por domínio."""
        return await self.repository.get_tenant_by_domain(domain)

    async def list_tenants(
        self,
        skip: int = 0,
        limit: int = 100,
        status: str = None,
        plan: str = None,
        tenant_type: str = None,
        search: str = None,
    ) -> tuple[list[Tenant], int]:
        """Lista tenants."""
        status_enum = TenantStatus(status) if status else None
        plan_enum = TenantPlan(plan) if plan else None
        type_enum = TenantType(tenant_type) if tenant_type else None
        return await self.repository.list_tenants(
            skip=skip, limit=limit, status=status_enum, plan=plan_enum, tenant_type=type_enum, search=search
        )

    async def update_tenant(self, tenant_id: UUID, data: TenantUpdate) -> Tenant | None:
        """Atualiza tenant."""
        tenant = await self.repository.get_tenant_by_id(tenant_id)
        if not tenant:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(tenant, field, value)

        return await self.repository.update_tenant(tenant)

    async def update_tenant_plan(self, tenant_id: UUID, data: TenantPlanUpdate) -> Tenant | None:
        """Atualiza plano do tenant."""
        tenant = await self.repository.get_tenant_by_id(tenant_id)
        if not tenant:
            return None

        limits = {}
        if data.max_usuarios:
            limits["max_usuarios"] = data.max_usuarios
        if data.max_storage_gb:
            limits["max_storage_gb"] = data.max_storage_gb
        if data.max_api_calls_month:
            limits["max_api_calls_month"] = data.max_api_calls_month

        tenant.upgrade_plan(TenantPlan(data.plan), limits)
        return await self.repository.update_tenant(tenant)

    async def update_tenant_address(self, tenant_id: UUID, data: TenantAddressUpdate) -> Tenant | None:
        """Atualiza endereço do tenant."""
        tenant = await self.repository.get_tenant_by_id(tenant_id)
        if not tenant:
            return None

        tenant.set_address(
            logradouro=data.logradouro,
            numero=data.numero,
            complemento=data.complemento,
            bairro=data.bairro,
            cidade=data.cidade,
            estado=data.estado,
            cep=data.cep,
        )
        return await self.repository.update_tenant(tenant)

    async def activate_tenant(self, tenant_id: UUID) -> Tenant | None:
        """Ativa tenant."""
        tenant = await self.repository.get_tenant_by_id(tenant_id)
        if not tenant:
            return None
        tenant.activate()
        return await self.repository.update_tenant(tenant)

    async def suspend_tenant(self, tenant_id: UUID, reason: str = None) -> Tenant | None:
        """Suspende tenant."""
        tenant = await self.repository.get_tenant_by_id(tenant_id)
        if not tenant:
            return None
        tenant.suspend(reason)
        return await self.repository.update_tenant(tenant)

    async def cancel_tenant(self, tenant_id: UUID) -> Tenant | None:
        """Cancela tenant."""
        tenant = await self.repository.get_tenant_by_id(tenant_id)
        if not tenant:
            return None
        tenant.cancel()
        return await self.repository.update_tenant(tenant)

    async def convert_trial(self, tenant_id: UUID, plan: str = "starter") -> Tenant | None:
        """Converte trial para plano pago."""
        tenant = await self.repository.get_tenant_by_id(tenant_id)
        if not tenant:
            return None
        tenant.convert_from_trial(TenantPlan(plan))
        return await self.repository.update_tenant(tenant)

    async def enable_feature(self, tenant_id: UUID, feature: str) -> Tenant | None:
        """Habilita feature para tenant."""
        tenant = await self.repository.get_tenant_by_id(tenant_id)
        if not tenant:
            return None
        tenant.enable_feature(feature)
        return await self.repository.update_tenant(tenant)

    async def disable_feature(self, tenant_id: UUID, feature: str) -> Tenant | None:
        """Desabilita feature para tenant."""
        tenant = await self.repository.get_tenant_by_id(tenant_id)
        if not tenant:
            return None
        tenant.disable_feature(feature)
        return await self.repository.update_tenant(tenant)

    async def delete_tenant(self, tenant_id: UUID) -> bool:
        """Remove tenant."""
        return await self.repository.delete_tenant(tenant_id)

    # ==================== TenantSettings ====================

    async def create_setting(self, data: TenantSettingsCreate) -> TenantSettings:
        """Cria configuração de tenant."""
        setting = TenantSettings.create_setting(
            tenant_id=data.tenant_id,
            chave=data.chave,
            nome=data.nome,
            category=SettingCategory(data.category),
            setting_type=SettingType(data.setting_type),
            valor_default=data.valor_default,
            required=data.required,
            visible=data.visible,
            editable=data.editable,
            group=data.group,
        )
        if data.valor:
            setting.valor = data.valor

        return await self.repository.create_setting(setting)

    async def get_setting(self, setting_id: UUID) -> TenantSettings | None:
        """Busca configuração por ID."""
        return await self.repository.get_setting_by_id(setting_id)

    async def get_setting_by_key(self, tenant_id: UUID, chave: str) -> TenantSettings | None:
        """Busca configuração por chave."""
        return await self.repository.get_setting_by_key(tenant_id, chave)

    async def get_setting_value(self, tenant_id: UUID, chave: str, default: Any = None) -> Any:
        """Retorna valor de configuração."""
        setting = await self.repository.get_setting_by_key(tenant_id, chave)
        if not setting:
            return default
        return setting.typed_value or default

    async def list_tenant_settings(
        self, tenant_id: UUID, category: str = None, group: str = None, visible: bool = None
    ) -> tuple[list[TenantSettings], int]:
        """Lista configurações do tenant."""
        category_enum = SettingCategory(category) if category else None
        return await self.repository.list_tenant_settings(
            tenant_id=tenant_id, category=category_enum, group=group, visible=visible
        )

    async def update_setting(
        self, setting_id: UUID, data: TenantSettingsUpdate, modified_by: UUID = None
    ) -> TenantSettings | None:
        """Atualiza configuração."""
        setting = await self.repository.get_setting_by_id(setting_id)
        if not setting:
            return None

        if data.valor is not None:
            is_valid, error = setting.validate_value(data.valor)
            if not is_valid:
                raise ValueError(error)
            setting.set_value(data.valor, modified_by)

        update_data = data.model_dump(exclude_unset=True, exclude={"valor"})
        for field, value in update_data.items():
            setattr(setting, field, value)

        return await self.repository.update_setting(setting)

    async def set_setting_value(
        self, tenant_id: UUID, chave: str, valor: Any, modified_by: UUID = None
    ) -> TenantSettings | None:
        """Define valor de configuração."""
        setting = await self.repository.get_setting_by_key(tenant_id, chave)
        if not setting:
            return None
        setting.set_value(valor, modified_by)
        return await self.repository.update_setting(setting)

    async def reset_setting(self, setting_id: UUID, modified_by: UUID = None) -> TenantSettings | None:
        """Reseta configuração para valor padrão."""
        setting = await self.repository.get_setting_by_id(setting_id)
        if not setting:
            return None
        setting.reset_to_default(modified_by)
        return await self.repository.update_setting(setting)

    async def delete_setting(self, setting_id: UUID) -> bool:
        """Remove configuração."""
        return await self.repository.delete_setting(setting_id)

    # ==================== SystemConfig ====================

    async def create_system_config(self, data: SystemConfigCreate) -> SystemConfig:
        """Cria configuração global."""
        config = SystemConfig.create_config(
            chave=data.chave,
            nome=data.nome,
            valor_type=data.valor_type,
            scope=ConfigScope(data.scope),
            descricao=data.descricao,
            cacheable=data.cacheable,
            cache_ttl_seconds=data.cache_ttl_seconds,
            override_allowed=data.override_allowed,
            admin_only=data.admin_only,
            category=data.category,
            group=data.group,
        )
        if data.valor:
            config.valor = data.valor

        return await self.repository.create_system_config(config)

    async def get_system_config(self, config_id: UUID) -> SystemConfig | None:
        """Busca configuração global por ID."""
        return await self.repository.get_system_config_by_id(config_id)

    async def get_system_config_by_key(self, chave: str) -> SystemConfig | None:
        """Busca configuração global por chave."""
        return await self.repository.get_system_config_by_key(chave)

    async def get_system_config_value(self, chave: str, default: Any = None) -> Any:
        """Retorna valor de configuração global."""
        config = await self.repository.get_system_config_by_key(chave)
        if not config:
            return default
        return config.typed_value or default

    async def list_system_configs(
        self, scope: str = None, category: str = None, admin_only: bool = None, skip: int = 0, limit: int = 100
    ) -> tuple[list[SystemConfig], int]:
        """Lista configurações globais."""
        scope_enum = ConfigScope(scope) if scope else None
        return await self.repository.list_system_configs(
            scope=scope_enum, category=category, admin_only=admin_only, skip=skip, limit=limit
        )

    async def update_system_config(
        self, config_id: UUID, data: SystemConfigUpdate, modified_by: UUID = None
    ) -> SystemConfig | None:
        """Atualiza configuração global."""
        config = await self.repository.get_system_config_by_id(config_id)
        if not config:
            return None

        if data.valor is not None:
            is_valid, error = config.validate_value(data.valor)
            if not is_valid:
                raise ValueError(error)
            config.set_value(data.valor, modified_by)

        update_data = data.model_dump(exclude_unset=True, exclude={"valor"})
        for field, value in update_data.items():
            setattr(config, field, value)

        return await self.repository.update_system_config(config)

    async def delete_system_config(self, config_id: UUID) -> bool:
        """Remove configuração global."""
        return await self.repository.delete_system_config(config_id)

    # ==================== FeatureFlag ====================

    async def create_feature_flag(self, data: FeatureFlagCreate) -> FeatureFlag:
        """Cria feature flag."""
        flag = FeatureFlag(
            codigo=data.codigo,
            nome=data.nome,
            descricao=data.descricao,
            flag_type=data.flag_type,
            status=FlagStatus(data.status),
            rollout_strategy=RolloutStrategy(data.rollout_strategy),
            rollout_percentage=data.rollout_percentage,
            category=data.category,
            owner_team=data.owner_team,
            jira_ticket=data.jira_ticket,
        )
        return await self.repository.create_feature_flag(flag)

    async def get_feature_flag(self, flag_id: UUID) -> FeatureFlag | None:
        """Busca feature flag por ID."""
        return await self.repository.get_feature_flag_by_id(flag_id)

    async def get_feature_flag_by_codigo(self, codigo: str) -> FeatureFlag | None:
        """Busca feature flag por código."""
        return await self.repository.get_feature_flag_by_codigo(codigo)

    async def list_feature_flags(
        self,
        status: str = None,
        flag_type: str = None,
        category: str = None,
        owner_team: str = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[FeatureFlag], int]:
        """Lista feature flags."""
        status_enum = FlagStatus(status) if status else None
        type_enum = None
        if flag_type:
            type_enum = FlagType(flag_type)
        return await self.repository.list_feature_flags(
            status=status_enum, flag_type=type_enum, category=category, owner_team=owner_team, skip=skip, limit=limit
        )

    async def update_feature_flag(self, flag_id: UUID, data: FeatureFlagUpdate) -> FeatureFlag | None:
        """Atualiza feature flag."""
        flag = await self.repository.get_feature_flag_by_id(flag_id)
        if not flag:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(flag, field, value)

        return await self.repository.update_feature_flag(flag)

    async def enable_flag(self, flag_id: UUID) -> FeatureFlag | None:
        """Habilita feature flag."""
        flag = await self.repository.get_feature_flag_by_id(flag_id)
        if not flag:
            return None
        flag.enable()
        return await self.repository.update_feature_flag(flag)

    async def disable_flag(self, flag_id: UUID) -> FeatureFlag | None:
        """Desabilita feature flag."""
        flag = await self.repository.get_feature_flag_by_id(flag_id)
        if not flag:
            return None
        flag.disable()
        return await self.repository.update_feature_flag(flag)

    async def set_flag_percentage(self, flag_id: UUID, percentage: float) -> FeatureFlag | None:
        """Define percentual de rollout."""
        flag = await self.repository.get_feature_flag_by_id(flag_id)
        if not flag:
            return None
        flag.set_percentage(percentage)
        return await self.repository.update_feature_flag(flag)

    async def start_gradual_rollout(self, flag_id: UUID, data: FeatureFlagGradualRollout) -> FeatureFlag | None:
        """Inicia rollout gradual."""
        flag = await self.repository.get_feature_flag_by_id(flag_id)
        if not flag:
            return None
        flag.start_gradual_rollout(
            start_percentage=data.start_percentage, end_percentage=data.end_percentage, duration_days=data.duration_days
        )
        return await self.repository.update_feature_flag(flag)

    async def enable_flag_for_tenant(self, flag_id: UUID, tenant_id: str) -> FeatureFlag | None:
        """Habilita flag para tenant específico."""
        flag = await self.repository.get_feature_flag_by_id(flag_id)
        if not flag:
            return None
        flag.enable_for_tenant(tenant_id)
        return await self.repository.update_feature_flag(flag)

    async def disable_flag_for_tenant(self, flag_id: UUID, tenant_id: str) -> FeatureFlag | None:
        """Desabilita flag para tenant específico."""
        flag = await self.repository.get_feature_flag_by_id(flag_id)
        if not flag:
            return None
        flag.disable_for_tenant(tenant_id)
        return await self.repository.update_feature_flag(flag)

    async def evaluate_flag(
        self, codigo: str, tenant_id: str = None, user_id: str = None, attributes: dict[str, Any] = None
    ) -> tuple[bool, str | None]:
        """Avalia feature flag."""
        flag = await self.repository.get_feature_flag_by_codigo(codigo)
        if not flag:
            return False, None
        enabled, variant = flag.evaluate(tenant_id, user_id, attributes)
        await self.repository.update_feature_flag(flag)
        return enabled, variant

    async def delete_feature_flag(self, flag_id: UUID) -> bool:
        """Remove feature flag."""
        return await self.repository.delete_feature_flag(flag_id)

    # ==================== NotificationTemplate ====================

    async def create_notification_template(self, data: NotificationTemplateCreate) -> NotificationTemplate:
        """Cria template de notificação."""
        template = NotificationTemplate(
            tenant_id=data.tenant_id,
            codigo=data.codigo,
            nome=data.nome,
            descricao=data.descricao,
            channel_id=None,
            notification_type=data.notification_type,
            status=TemplateStatus.RASCUNHO,
            email_subject=data.email_subject,
            email_body_html=data.email_body_html,
            email_body_text=data.email_body_text,
            sms_body=data.sms_body,
            push_title=data.push_title,
            push_body=data.push_body,
            in_app_title=data.in_app_title,
            in_app_body=data.in_app_body,
            language=data.language,
            category=data.category,
        )
        return await self.repository.create_notification_template(template)

    async def get_notification_template(self, template_id: UUID) -> NotificationTemplate | None:
        """Busca template por ID."""
        return await self.repository.get_notification_template_by_id(template_id)

    async def get_notification_template_by_codigo(self, tenant_id: UUID, codigo: str) -> NotificationTemplate | None:
        """Busca template por código."""
        return await self.repository.get_notification_template_by_codigo(tenant_id, codigo)

    async def list_notification_templates(
        self,
        tenant_id: UUID = None,
        channel: str = None,
        notification_type: str = None,
        status: str = None,
        category: str = None,
        include_global: bool = True,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[NotificationTemplate], int]:
        """Lista templates."""
        channel_enum = NotificationChannel(channel) if channel else None
        type_enum = None
        if notification_type:
            type_enum = NotificationType(notification_type)
        status_enum = TemplateStatus(status) if status else None

        return await self.repository.list_notification_templates(
            tenant_id=tenant_id,
            channel=channel_enum,
            notification_type=type_enum,
            status=status_enum,
            category=category,
            include_global=include_global,
            skip=skip,
            limit=limit,
        )

    async def update_notification_template(
        self, template_id: UUID, data: NotificationTemplateUpdate
    ) -> NotificationTemplate | None:
        """Atualiza template."""
        template = await self.repository.get_notification_template_by_id(template_id)
        if not template:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(template, field, value)

        template.increment_version()
        return await self.repository.update_notification_template(template)

    async def activate_template(self, template_id: UUID) -> NotificationTemplate | None:
        """Ativa template."""
        template = await self.repository.get_notification_template_by_id(template_id)
        if not template:
            return None
        template.activate()
        return await self.repository.update_notification_template(template)

    async def deactivate_template(self, template_id: UUID) -> NotificationTemplate | None:
        """Desativa template."""
        template = await self.repository.get_notification_template_by_id(template_id)
        if not template:
            return None
        template.deactivate()
        return await self.repository.update_notification_template(template)

    async def render_template(self, template_id: UUID, variables: dict[str, Any]) -> dict[str, Any]:
        """Renderiza template com variáveis."""
        template = await self.repository.get_notification_template_by_id(template_id)
        if not template:
            return {}

        is_valid, missing = template.validate_variables(variables)
        if not is_valid:
            raise ValueError(f"Variáveis faltando: {', '.join(missing)}")

        return template.render(variables)

    async def clone_template(self, template_id: UUID, new_codigo: str = None) -> NotificationTemplate | None:
        """Clona template."""
        template = await self.repository.get_notification_template_by_id(template_id)
        if not template:
            return None

        clone = template.clone(new_codigo)
        return await self.repository.create_notification_template(clone)

    async def delete_notification_template(self, template_id: UUID) -> bool:
        """Remove template."""
        return await self.repository.delete_notification_template(template_id)

    # ==================== Dashboard ====================

    async def get_config_dashboard(self) -> ConfigDashboard:
        """Retorna dashboard de configurações."""
        # O tipo `tenantstatus` não existe neste banco (sem migração): o painel inteiro caía
        # com 500 por causa do bloco de tenants. Sem tenants, painel parcial (07/09/2026).
        from sqlalchemy.exc import DBAPIError, ProgrammingError

        try:
            stats = await self.repository.get_config_dashboard_stats()
            recent = await self.repository.get_recent_tenants(5)
        except (ProgrammingError, DBAPIError):
            await self.db.rollback()
            stats = {"total_tenants": 0, "active_tenants": 0, "trial_tenants": 0, "suspended_tenants": 0,
                     "total_configs": 0, "total_feature_flags": 0, "active_feature_flags": 0,
                     "total_notification_templates": 0}
            recent = []

        return ConfigDashboard(
            total_tenants=stats["total_tenants"],
            active_tenants=stats["active_tenants"],
            trial_tenants=stats["trial_tenants"],
            suspended_tenants=stats["suspended_tenants"],
            total_configs=stats["total_configs"],
            total_feature_flags=stats["total_feature_flags"],
            active_feature_flags=stats["active_feature_flags"],
            total_notification_templates=stats["total_notification_templates"],
            recent_tenants=[{"id": str(t.id), "nome": t.nome, "status": t.status.value} for t in recent],
            feature_flags_stats={"total": stats["total_feature_flags"], "active": stats["active_feature_flags"]},
        )

    async def get_tenant_dashboard(self, tenant_id: UUID) -> TenantDashboard | None:
        """Retorna dashboard do tenant."""
        tenant = await self.repository.get_tenant_by_id(tenant_id)
        if not tenant:
            return None

        settings, _ = await self.repository.list_tenant_settings(tenant_id)
        templates, _ = await self.repository.list_notification_templates(tenant_id=tenant_id, include_global=False)

        flags_enabled = 0
        if tenant.features_enabled:
            flags_enabled = len(tenant.features_enabled)

        return TenantDashboard(
            tenant=tenant,
            settings_count=len(settings),
            feature_flags_enabled=flags_enabled,
            notification_templates=len(templates),
            storage_usage_percent=tenant.storage_usage_percent,
            users_usage_percent=tenant.users_usage_percent,
            api_usage_percent=tenant.api_usage_percent,
        )
