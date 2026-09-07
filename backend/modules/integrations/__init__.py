"""
Module: integrations
Description: Modulo de Integracoes - API Gateway, Webhooks, Banking, Email, WhatsApp, Conectores

DEPRECATED: Use 'modules.gestao' instead for router imports.
Deprecation date: 2026-03-11. Removal target: 2026-05-11.

Estrutura modular:
- models/: Modelos SQLAlchemy para persistencia
- schemas/: Schemas Pydantic para validacao
- services/: Logica de negocio
- controllers/: Endpoints FastAPI
- repositories/: Acesso a dados
- connectors/: Conectores para sistemas externos (Sprint 33)
- sync/: Engine de sincronizacao (Sprint 33)
- banking/: Integracao Open Banking (BB, Itau, Bradesco)
- email/: Automacoes e campanhas de email
- whatsapp/: Automacoes e chatbot WhatsApp
"""

import warnings

warnings.warn(
    "Importing from 'modules.integrations' is deprecated. "
    "Use 'modules.gestao' for router access. "
    "This module will be removed after 2026-05-11.",
    DeprecationWarning,
    stacklevel=2,
)

from fastapi import APIRouter  # noqa: E402

# Re-export submodulos - Banking (Open Banking)
from modules.integrations.banking import (  # noqa: E402
    AccountBalance,
    AccountType,
    BankCode,
    BankCredentials,
    BankingAdapterError,
    BankingService,
    BankStatement,
    BankTransaction,
    BBAdapter,
    BradescoAdapter,
    ItauAdapter,
    PaymentRequest,
    PaymentResponse,
    PaymentStatus,
    PixKey,
    TransactionType,
)

# Importa routers dos controllers
from modules.integrations.controllers import connector_router, integration_router  # noqa: E402

# E-mail legado (modules/integrations/email) em quarentena desde 07/09/2026: 6 modelos sem tabela
# (email_*), nenhuma rota, nenhum consumidor. O envio real é core.mailer.

# Re-export models
from modules.integrations.models import (  # noqa: E402
    AccountStatus,
    APIEndpoint,
    APIKey,
    APIKeyScope,
    APIKeyStatus,
    APIKeyType,
    AuthType,
    ConnectorType,
    EndpointCategory,
    EndpointStatus,
    ExternalSystem,
    HTTPMethod,
    IDMap,
    IntegrationAccount,
    IntegrationLog,
    LogLevel,
    LogStatus,
    LogType,
    RateLimitType,
    SyncDirection,
    SyncEntityType,
    SyncOperationType,
    SyncPriority,
    SyncQueue,
    SyncRun,
    SyncRunMode,
    SyncRunStatus,
    SyncRunTrigger,
    SyncState,
    SyncStatus,
    WebhookAuthType,
    WebhookConfig,
    WebhookEvent,
    WebhookFormat,
    WebhookStatus,
)

# Re-export repositories
from modules.integrations.repositories import (  # noqa: E402
    ConnectorRepository,
    IntegrationRepository,
)

# Re-export schemas
from modules.integrations.schemas import (  # noqa: E402
    APIEndpointBase,
    APIEndpointCreate,
    APIEndpointList,
    APIEndpointResponse,
    APIEndpointUpdate,
    APIKeyBase,
    APIKeyCreate,
    APIKeyCreateResponse,
    APIKeyList,
    APIKeyResponse,
    APIKeyRevokeRequest,
    APIKeyUpdate,
    IntegrationDashboard,
    IntegrationHealthCheck,
    IntegrationLogFilter,
    IntegrationLogList,
    IntegrationLogResponse,
    SyncQueueBase,
    SyncQueueBatchCreate,
    SyncQueueCreate,
    SyncQueueFilter,
    SyncQueueList,
    SyncQueueResponse,
    SyncQueueStats,
    SyncQueueUpdate,
    WebhookConfigBase,
    WebhookConfigCreate,
    WebhookConfigList,
    WebhookConfigResponse,
    WebhookConfigUpdate,
    WebhookTestRequest,
    WebhookTestResponse,
)

# Re-export services
from modules.integrations.services import (  # noqa: E402
    ConnectorService,
    IntegrationService,
    WebhookService,
)

# WhatsApp legado (modules/integrations/whatsapp) foi para a quarentena em 07/09/2026: 4 modelos sem
# tabela (wa_*), controllers nunca montados, nenhum consumidor fora deste agregador — que
# ninguém importa. O WhatsApp vivo é modules/integrations/connectors/whatsapp (cwi_message_log).

__all__ = [
    # Routers
    "integrations_router",
    "router",
    "integration_router",
    "connector_router",
    # ==================== Core Models ====================
    # API Endpoint
    "APIEndpoint",
    "HTTPMethod",
    "EndpointCategory",
    "EndpointStatus",
    "RateLimitType",
    # API Key
    "APIKey",
    "APIKeyType",
    "APIKeyStatus",
    "APIKeyScope",
    # Webhook Config
    "WebhookConfig",
    "WebhookEvent",
    "WebhookStatus",
    "WebhookFormat",
    "WebhookAuthType",
    # Integration Log
    "IntegrationLog",
    "LogType",
    "LogLevel",
    "LogStatus",
    # Sync Queue
    "SyncQueue",
    "SyncDirection",
    "SyncPriority",
    "SyncStatus",
    "SyncEntityType",
    "SyncOperationType",
    "ExternalSystem",
    # Sprint 33: Integration Framework Models
    "IntegrationAccount",
    "ConnectorType",
    "AuthType",
    "AccountStatus",
    "SyncRun",
    "SyncRunStatus",
    "SyncRunMode",
    "SyncRunTrigger",
    "SyncState",
    "IDMap",
    # ==================== Core Schemas ====================
    # API Endpoint
    "APIEndpointBase",
    "APIEndpointCreate",
    "APIEndpointUpdate",
    "APIEndpointResponse",
    "APIEndpointList",
    # API Key
    "APIKeyBase",
    "APIKeyCreate",
    "APIKeyCreateResponse",
    "APIKeyUpdate",
    "APIKeyResponse",
    "APIKeyList",
    "APIKeyRevokeRequest",
    # Webhook
    "WebhookConfigBase",
    "WebhookConfigCreate",
    "WebhookConfigUpdate",
    "WebhookConfigResponse",
    "WebhookConfigList",
    "WebhookTestRequest",
    "WebhookTestResponse",
    # Integration Log
    "IntegrationLogResponse",
    "IntegrationLogList",
    "IntegrationLogFilter",
    # Sync Queue
    "SyncQueueBase",
    "SyncQueueCreate",
    "SyncQueueBatchCreate",
    "SyncQueueUpdate",
    "SyncQueueResponse",
    "SyncQueueList",
    "SyncQueueFilter",
    "SyncQueueStats",
    # Dashboard
    "IntegrationDashboard",
    "IntegrationHealthCheck",
    # ==================== Core Services ====================
    "IntegrationService",
    "WebhookService",
    "ConnectorService",
    # ==================== Core Repositories ====================
    "IntegrationRepository",
    "ConnectorRepository",
    # ==================== Banking Submodule ====================
    "BankingService",
    "BBAdapter",
    "ItauAdapter",
    "BradescoAdapter",
    "BankCode",
    "AccountType",
    "TransactionType",
    "PaymentStatus",
    "BankCredentials",
    "AccountBalance",
    "BankTransaction",
    "BankStatement",
    "PaymentRequest",
    "PaymentResponse",
    "PixKey",
    "BankingAdapterError",
    ]

__version__ = "1.0.0"
