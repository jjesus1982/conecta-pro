"""
Controller REST para integração Sólides DP.
Sprint 33: Integration Framework

Endpoints para:
- Recebimento de webhooks do Sólides
- Configuração da integração
- Monitoramento e status
- Acionamento de sincronização
- Gerenciamento de conflitos
- Logs de sincronização
"""

import hashlib
import hmac
import logging
import os
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    status,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user
from core.database.session import get_sync_db_dependency
from modules.integrations.connectors.solides.models import (
    SolidesIntegrationConfig,
)
from modules.integrations.connectors.solides.webhook_handler import SolidesWebhookHandler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/solides", tags=["Solides Integration"])


def _get_condominio_id(current_user: Any, db: Session | None = None) -> UUID:
    """
    Retorna condominio_id do usuario ou busca o unico condominio existente.

    Em sistemas single-tenant, o User nao tem condominio_id.
    Busca da tabela solides_integration_config ou usa o primeiro condominio.
    """
    cid = getattr(current_user, "condominio_id", None)
    if cid:
        return cid

    # Single-tenant: buscar condominio unico
    if db:
        config = db.query(SolidesIntegrationConfig).first()
        if config:
            return config.condominio_id

        # Fallback: buscar de solides_employees
        from sqlalchemy import text

        result = db.execute(text("SELECT DISTINCT condominio_id FROM solides_employees LIMIT 1"))
        row = result.first()
        if row:
            return row[0]

    # Ultimo fallback: condominio conhecido
    return UUID("615bbcf6-f473-48aa-a304-43eaea9bfaf7")


# ==================== FUNÇÕES UTILITÁRIAS ====================


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Valida assinatura HMAC SHA256 do webhook.

    Args:
        payload: Body raw da requisição em bytes
        signature: Assinatura recebida no header
        secret: Secret configurado para validação

    Returns:
        True se a assinatura for válida, False caso contrário

    Note:
        Usa hmac.compare_digest para prevenir timing attacks.
        Suporta assinaturas com ou sem prefixo 'sha256='.
    """
    if not secret:
        logger.warning("[Solides Webhook] Secret não configurado")
        return False

    if not signature:
        logger.warning("[Solides Webhook] Assinatura não fornecida")
        return False

    # Remove prefixo sha256= se presente
    if signature.startswith("sha256="):
        signature = signature[7:]

    # Calcula HMAC SHA256
    expected = hmac.new(key=secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256).hexdigest()

    # Comparação segura contra timing attacks
    return hmac.compare_digest(expected.lower(), signature.lower())


def get_webhook_secret() -> str:
    """
    Obtém o secret do webhook da variável de ambiente.

    Returns:
        String do secret ou string vazia se não configurado.
    """
    return os.getenv("SOLIDES_WEBHOOK_SECRET", "")


# ==================== SCHEMAS ====================


class SolidesConfigRequest(BaseModel):
    """Schema para configurar integração Sólides."""

    api_token: str = Field(..., min_length=10, description="Token de API do Sólides (Basic Auth base64)")
    sync_direction: str = Field(
        default="solides_to_conecta",
        description="Direção da sincronização: solides_to_conecta, conecta_to_solides, bidirectional",
    )
    conflict_strategy: str = Field(
        default="most_recent", description="Estratégia de conflito: solides_wins, conecta_wins, most_recent, manual"
    )
    enabled_entities: list[str] = Field(
        default=["colaboradores", "departamentos", "cargos", "ocorrencias", "absenteismos"],
        description="Entidades habilitadas para sincronização",
    )
    incremental_sync_interval_minutes: int = Field(
        default=15, ge=5, le=60, description="Intervalo em minutos para sincronização incremental"
    )
    auto_create_departments: bool = Field(
        default=True, description="Criar departamentos automaticamente se não existirem"
    )
    auto_create_positions: bool = Field(default=True, description="Criar cargos automaticamente se não existirem")
    webhook_enabled: bool = Field(default=True, description="Habilitar recebimento de webhooks")


class SolidesConfigResponse(BaseModel):
    """Resposta com configuração atual da integração."""

    is_enabled: bool
    is_connected: bool
    sync_direction: str | None = None
    conflict_strategy: str | None = None
    enabled_entities: list[str] = Field(default_factory=list)
    last_health_check_at: datetime | None = None
    last_health_check_status: bool | None = None


class SyncTriggerRequest(BaseModel):
    """Request para disparar sincronização manual."""

    entity_types: list[str] | None = Field(
        default=None, description="Tipos de entidade a sincronizar (None = todas habilitadas)"
    )
    full_sync: bool = Field(default=False, description="Se True, executa sincronização completa")
    force: bool = Field(default=False, description="Se True, ignora verificações de intervalo mínimo")


class SyncTriggerResponse(BaseModel):
    """Resposta do disparo de sincronização."""

    success: bool
    message: str
    task_id: str | None = None
    sync_type: str
    entity_types: list[str] | None = None


class SyncStatusResponse(BaseModel):
    """Status atual da sincronização."""

    connected: bool
    api_latency_ms: int | None = None
    entities: dict[str, Any] = Field(default_factory=dict)
    pending_conflicts: int = 0
    last_full_sync_at: datetime | None = None
    last_incremental_sync_at: datetime | None = None
    webhook_enabled: bool = False


class ConflictResponse(BaseModel):
    """Conflito de sincronização."""

    id: str
    entity_type: str
    entity_id: str
    solides_id: str
    status: str
    changed_fields: list[str] = Field(default_factory=list)
    detected_at: datetime
    solides_data: dict[str, Any]
    conecta_data: dict[str, Any]


class ConflictResolutionRequest(BaseModel):
    """Request para resolver conflito manualmente."""

    strategy: str = Field(..., description="Estratégia: solides_wins, conecta_wins, most_recent, manual")
    resolution_notes: str | None = Field(default=None, max_length=500, description="Notas sobre a resolução")
    manual_data: dict[str, Any] | None = Field(
        default=None, description="Dados para resolução manual (quando strategy=manual)"
    )


class SyncLogResponse(BaseModel):
    """Log de sincronização."""

    id: str
    sync_type: str
    entity_type: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: int | None = None
    total_processed: int = 0
    created_count: int = 0
    updated_count: int = 0
    error_count: int = 0


class WebhookResponse(BaseModel):
    """Resposta do endpoint de webhook."""

    status: str
    message: str | None = None
    webhook_id: str | None = None
    event_type: str | None = None


class IntegrationStatusResponse(BaseModel):
    """Status completo da integração."""

    healthy: bool
    connected: bool
    latency_ms: int | None = None
    message: str | None = None
    last_sync_at: datetime | None = None
    pending_items: int = 0


class SolidesEmployeeResponse(BaseModel):
    """Schema de resposta para colaborador do Sólides."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    solides_id: str
    nome: str
    email: str | None = None
    cpf: str | None = None
    matricula: str | None = None
    cargo_nome: str | None = None
    departamento_nome: str | None = None
    situacao: str | None = None
    telefone: str | None = None
    celular: str | None = None
    data_admissao: datetime | None = None
    foto_url: str | None = None


class SolidesEmployeeListResponse(BaseModel):
    """Schema para listagem paginada de colaboradores do Sólides."""

    items: list[SolidesEmployeeResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ==================== ENDPOINT DE WEBHOOK (PÚBLICO) ====================


@router.post(
    "/webhook",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Receber webhook do Sólides",
    description="""
    Endpoint para receber webhooks do Sólides DP.

    **Eventos suportados:**
    - `novo_colaborador` / `employee.created`: Novo colaborador cadastrado
    - `edicao_colaborador` / `employee.updated`: Colaborador atualizado
    - `demissao_colaborador` / `employee.terminated`: Colaborador demitido
    - `nova_ocorrencia`: Nova ocorrência registrada
    - `novo_absenteismo`: Novo absenteísmo registrado
    - `nova_resposta_pesquisa`: Resposta em pesquisa
    - `novo_curriculo`: Novo currículo recebido
    - `nova_inscricao`: Nova inscrição em vaga
    - `mudanca_etapa`: Mudança de etapa em processo seletivo

    **Validação de assinatura:**
    - Header `X-Solides-Signature` ou `X-Webhook-Signature`
    - HMAC SHA256 com secret configurado em `SOLIDES_WEBHOOK_SECRET`
    - Formato: `sha256=<hash>` ou apenas `<hash>`

    **Retorno rápido:**
    - Sempre retorna 200 OK rapidamente
    - Processamento ocorre de forma assíncrona via fila
    """,
    responses={
        200: {"description": "Webhook recebido com sucesso"},
        400: {"description": "Payload inválido"},
        401: {"description": "Assinatura inválida"},
        500: {"description": "Erro interno no processamento"},
    },
)
async def receive_webhook(
    request: Request,
    db: Session = Depends(get_sync_db_dependency),
    x_solides_signature: str | None = Header(
        default=None, alias="X-Solides-Signature", description="Assinatura HMAC SHA256 do payload"
    ),
    x_webhook_signature: str | None = Header(
        default=None, alias="X-Webhook-Signature", description="Assinatura alternativa HMAC SHA256"
    ),
    x_request_id: str | None = Header(
        default=None, alias="X-Request-ID", description="ID único da requisição para rastreamento"
    ),
) -> WebhookResponse:
    """
    Endpoint para receber webhooks do Sólides DP.

    O processamento é feito de forma assíncrona para garantir
    resposta rápida ao Sólides (evita timeout/retry desnecessário).
    """
    # Ler body raw para validação de assinatura
    try:
        body = await request.body()
    except Exception as e:
        logger.error(f"[Solides Webhook] Erro ao ler body: {e}")
        return WebhookResponse(status="error", message="Erro ao ler requisição")

    # Validar assinatura HMAC
    webhook_secret = get_webhook_secret()
    signature = x_solides_signature or x_webhook_signature

    if webhook_secret:
        if not signature:
            logger.warning(
                f"[Solides Webhook] Requisição sem assinatura "
                f"(request_id={x_request_id}, ip={request.client.host if request.client else 'unknown'})"
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Assinatura do webhook não fornecida")

        if not verify_webhook_signature(body, signature, webhook_secret):
            logger.warning(
                f"[Solides Webhook] Assinatura inválida "
                f"(request_id={x_request_id}, ip={request.client.host if request.client else 'unknown'})"
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Assinatura do webhook inválida")

        logger.debug("[Solides Webhook] Assinatura validada com sucesso")
    else:
        logger.warning(
            "[Solides Webhook] SOLIDES_WEBHOOK_SECRET não configurado - validação de assinatura desabilitada"
        )

    # Parse do payload JSON
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"[Solides Webhook] JSON inválido: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload JSON inválido")

    # Extrair tipo de evento (suporta diferentes formatos)
    event_type = payload.get("event") or payload.get("type") or payload.get("event_type") or "unknown"

    # Headers para logging/rastreamento
    headers = {
        "X-Solides-Signature": x_solides_signature or "",
        "X-Webhook-Signature": x_webhook_signature or "",
        "X-Request-ID": x_request_id or "",
        "Content-Type": request.headers.get("Content-Type", ""),
        "User-Agent": request.headers.get("User-Agent", ""),
    }

    # IP de origem
    client_ip = None
    if request.client:
        client_ip = request.client.host
    # Verificar headers de proxy
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()

    logger.info(f"[Solides Webhook] Recebido evento '{event_type}' (request_id={x_request_id}, ip={client_ip})")

    # Processar via handler
    try:
        handler = SolidesWebhookHandler(db, async_processing=True)

        result = await handler.handle_webhook(
            event_type=event_type,
            payload=payload,
            headers=headers,
            raw_body=body,
            request_id=x_request_id,
            ip_address=client_ip,
        )

        return WebhookResponse(
            status=result.get("status", "received"),
            message=result.get("message"),
            webhook_id=result.get("webhook_id"),
            event_type=event_type,
        )

    except Exception as e:
        logger.error(f"[Solides Webhook] Erro no processamento: {e}", exc_info=True)
        # Retorna 200 mesmo em erro para evitar retry do Sólides
        # O erro foi logado para investigação
        return WebhookResponse(status="error", message="Erro interno - evento será reprocessado", event_type=event_type)


# ==================== ENDPOINT DE STATUS (PÚBLICO PARA HEALTH CHECK) ====================


# ==================== ENDPOINTS DE SINCRONIZAÇÃO ====================


# ==================== ENDPOINTS DE LOGS ====================


# ==================== ENDPOINTS DE CONFIGURAÇÃO ====================


# ==================== ENDPOINTS DE CONFLITOS ====================


# ==================== ENDPOINT DE HEALTH CHECK ====================


@router.post("/beneficios/sync", status_code=200, tags=["Solides - Benefícios GED"])
def solides_beneficios_sync(
    mes_ref: str | None = Query(None, description="Mês MM.YYYY — sem valor: todos os meses"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
):
    """
    Sincroniza pedidos de benefícios VT/VA Sólides.

    1. Tenta API Sólides (benefit-orders) — retorna [] se endpoint 404
    2. Fallback: cria solides_benefit_orders a partir das inter_transactions SOLIDES
       (PIX lump-sum ao CNPJ Sólides/SWAP IP S.A.)

    Nota: A API Sólides (Tangerino) não expõe endpoint de benefit-orders (apenas HR/DP).
    O breakdown por funcionário requer upload do relatório Sólides (PDF/CSV).
    """
    from modules.integrations.connectors.solides.benefit_service import SolidesBenefitService

    svc = SolidesBenefitService(db)
    result = svc.sync_benefit_orders(mes_ref=mes_ref)
    match_result = svc.match_inter_transactions()
    result["match_inter"] = match_result
    return result


@router.post("/beneficios/vincular-kits", status_code=200, tags=["Solides - Benefícios GED"])
def solides_beneficios_vincular_kits(
    mes_ref: str | None = Query(None, description="Mês MM.YYYY — sem valor: todos os meses"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
):
    """
    Vincula itens de pedidos Sólides ao kit GED de cada funcionário.

    Requer solides_benefit_order_items populados com employee_id e CPF.
    Sem a API de benefit-orders, items ficam vazios e nenhum slot é vinculado.
    """
    from modules.integrations.connectors.solides.benefit_service import SolidesBenefitService

    svc = SolidesBenefitService(db)
    return svc.vincular_kits(mes_ref=mes_ref)
