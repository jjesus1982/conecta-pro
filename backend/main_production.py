"""
ERP Conecta Mais V2.0 - Producao (Modulos Core)
Versao otimizada que carrega apenas modulos estaveis.
"""

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from core.config import settings
from core.logging import configure_logging, logger
from core.rate_limit import limiter

# =============================================================================
# SENTRY INITIALIZATION
# =============================================================================
if settings.sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.redis import RedisIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=f"conecta-pro@{settings.app_version}",
        traces_sample_rate=settings.sentry_traces_sample_rate,
        profiles_sample_rate=settings.sentry_profiles_sample_rate,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            RedisIntegration(),
            CeleryIntegration(),
        ],
        send_default_pii=False,
        attach_stacktrace=True,
    )
    logger.info("Sentry: inicializado")
else:
    if settings.environment == "production":
        logger.warning(
            "SENTRY_DSN nao configurado — erros de producao nao serao monitorados",
            action="sentry_missing",
        )


# =============================================================================
# SECURITY HEADERS MIDDLEWARE
# =============================================================================
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if "/api/" in request.url.path:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response


# Rate limiter importado de core.rate_limit (usa Redis, headers habilitados)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    from core.cache import close_redis, get_redis
    from core.database import close_db

    configure_logging()
    logger.info(f"Iniciando {settings.app_name} v{settings.app_version}")
    logger.info(f"Ambiente: {settings.environment}")

    try:
        await get_redis()
        logger.info("Redis: conectado")
    except Exception as e:
        logger.warning(f"Redis: falha na conexao ({e})")

    # Inicializar ConectaEventBus unificado
    try:
        import asyncio as _asyncio

        from infrastructure.event_bus import event_bus as _event_bus

        await _event_bus.connect()
        _asyncio.create_task(
            _event_bus.start_consuming(
                group_name="conecta-pro",
                consumer_name="main-worker",
            )
        )
        logger.info("ConectaEventBus: iniciado")
    except Exception as e:
        logger.warning(f"ConectaEventBus: falha na inicializacao ({e})")

    # Inicializar GEDEON — orquestrador invisível
    try:
        from modules.gedeon.context.gedeon_context import gedeon_context as _gedeon_context
        from modules.gedeon.gedeon import gedeon

        await _gedeon_context.connect()
        gedeon.registrar_subscribers()
        logger.info("GEDEON: orquestrador ativo — modo invisível")
    except Exception as e:
        logger.warning(f"GEDEON: falha na inicialização ({e})")

    # Propagação bidirecional CCT/cargo → postos/folha/pricing (comunicação entre módulos)
    try:
        from modules.people_management.cct.subscribers import cct_propagation

        cct_propagation.registrar_subscribers()
        logger.info("CCT propagação: subscribers de cargo/CCT ativos (bidirecional)")
    except Exception as e:
        logger.warning(f"CCT propagação: falha ao registrar subscribers ({e})")

    # GDrive: carregar tokens e conectar no startup
    try:
        from modules.gdrive.services.gdrive_service import gdrive_service as _gdrive_service

        status = _gdrive_service.check_status()
        if status.get("configurado") or status.get("conectado"):
            logger.info("GDrive: conectado no startup (%s)", status.get("tipo", ""))
        else:
            # Tentar restaurar tokens do banco se disponíveis
            from sqlalchemy import text as _sa_text

            from core.database import async_session_factory as _asf

            async with _asf() as _db:
                _row = await _db.execute(
                    _sa_text(
                        "SELECT access_token, refresh_token, token_expiry::text "
                        "FROM gdrive_config WHERE is_connected=TRUE LIMIT 1"
                    )
                )
                _linha = _row.mappings().first()
                if _linha:
                    _gdrive_service.conectar_com_tokens(
                        _linha["access_token"],
                        _linha["refresh_token"],
                        _linha.get("token_expiry"),
                    )
                    logger.info("GDrive: tokens restaurados do banco no startup")
                else:
                    logger.info("GDrive: aguardando autorização OAuth2")
    except Exception as _e:
        logger.warning("GDrive startup falhou (não crítico): %s", _e)

    yield

    logger.info("Encerrando aplicacao...")
    try:
        from infrastructure.event_bus import event_bus as _event_bus

        await _event_bus.disconnect()
    except Exception:
        pass
    await close_redis()
    await close_db()
    logger.info("Conexoes fechadas")


_is_production = settings.environment == "production"

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Sistema ERP completo para gestao empresarial",
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
    redirect_slashes=False,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# =============================================================================
# MIDDLEWARES
# =============================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)
app.add_middleware(SecurityHeadersMiddleware)
# Auditoria: registra toda escrita (POST/PUT/PATCH/DELETE) em crm_audit_log (best-effort, não bloqueia).
from core.middleware_audit import AuditMiddleware  # noqa: E402

app.add_middleware(AuditMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=500)
# ProxyHeaders: confia nos headers X-Forwarded-Proto/X-Forwarded-For do nginx
# para que redirects 307 usem https:// em vez de http://
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["127.0.0.1", "::1"])


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }


@app.get("/health/detailed", tags=["Health"])
async def health_check_detailed():
    """
    Health check detalhado para UptimeRobot e monitoramento.
    Verifica: Database, Redis, Celery.
    Retorna: healthy, degraded ou unhealthy.
    """
    from sqlalchemy import text

    from core.cache import get_redis
    from core.database.session import async_session_factory

    checks = {
        "database": {"status": "unknown", "latency_ms": None, "error": None},
        "redis": {"status": "unknown", "latency_ms": None, "error": None},
        "celery": {"status": "unknown", "latency_ms": None, "error": None},
    }

    # Check Database
    try:
        start = time.time()
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        latency = (time.time() - start) * 1000
        checks["database"] = {"status": "healthy", "latency_ms": round(latency, 2), "error": None}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "latency_ms": None, "error": str(e)[:200]}

    # Check Redis
    try:
        start = time.time()
        redis = await get_redis()
        if redis:
            await redis.ping()
            latency = (time.time() - start) * 1000
            checks["redis"] = {"status": "healthy", "latency_ms": round(latency, 2), "error": None}
        else:
            checks["redis"] = {"status": "degraded", "latency_ms": None, "error": "Redis not configured"}
    except Exception as e:
        checks["redis"] = {"status": "unhealthy", "latency_ms": None, "error": str(e)[:200]}

    # Check Celery (via Redis broker)
    try:
        start = time.time()
        import redis as redis_sync

        celery_redis = redis_sync.from_url(settings.redis_url.replace("/1", "/0"))
        celery_redis.ping()
        latency = (time.time() - start) * 1000
        checks["celery"] = {"status": "healthy", "latency_ms": round(latency, 2), "error": None}
        celery_redis.close()
    except Exception as e:
        checks["celery"] = {"status": "degraded", "latency_ms": None, "error": str(e)[:200]}

    # Determine overall status
    statuses = [c["status"] for c in checks.values()]
    if all(s == "healthy" for s in statuses):
        overall = "healthy"
        status_code = 200
    elif "unhealthy" in statuses:
        overall = "unhealthy"
        status_code = 503
    else:
        overall = "degraded"
        status_code = 200

    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall,
            "app": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
            "checks": checks,
            "timestamp": time.time(),
        },
    )


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": f"Bem-vindo ao {settings.app_name}",
        "version": settings.app_version,
        "docs": "/docs",
    }


# =============================================================================
# API ROUTER - CARREGAMENTO VIA 9 MÓDULOS ORGANIZADOS
# Reorganização: 35 módulos → 9 módulos (2026-03-11)
# API URLs inalteradas — apenas imports reorganizados
# =============================================================================
from fastapi import APIRouter, Depends
from core.auth.dependencies import require_permission

# Blindagem do backend Financeiro (2026-07-14): só quem tem module:financeiro (admin=Jordan/Pyetra
# passam automático) acessa as APIs de dinheiro. Antes o backend usava só "usuário logado".
_FIN_GATE = Depends(require_permission("module:financeiro"))
_FISCAL_GATE = Depends(require_permission("module:fiscal"))

api_router = APIRouter(prefix="/api/v1")

# Health — expõe /api/v1/health para varredura automatizada
try:
    from core.controllers.health_controller import router as _health_router

    api_router.include_router(_health_router)
except Exception:
    pass


@api_router.get("/health", tags=["Health"], include_in_schema=False)
async def api_v1_health():
    """Alias /api/v1/health → mesma resposta do /health."""
    return {"status": "healthy", "version": "2.0.0"}


# Auth - importacao direta (fora dos módulos)
try:
    import importlib.util

    spec = importlib.util.spec_from_file_location("auth", "/app/api/v1/endpoints/auth.py")
    auth_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(auth_module)
    auth_router = auth_module.router
    api_router.include_router(auth_router)
    logger.info("Modulo Auth: OK")
except Exception as e:
    logger.warning(f"Modulo Auth: {e}")

# Users - gerenciamento de usuarios (admin)
try:
    spec = importlib.util.spec_from_file_location("users", "/app/api/v1/endpoints/users.py")
    users_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(users_module)
    users_router = users_module.router
    api_router.include_router(users_router)
    logger.info("Modulo Users: OK")
except Exception as e:
    logger.warning(f"Modulo Users: {e}")


# =============================================================================
# 1. COMERCIAL (crm + clients + bidding + services)
# =============================================================================
try:
    from modules.comercial import (
        bidding_agent_router,
        bidding_contract_router,
        bidding_document_router,
        bidding_erp_router,
        bidding_proposal_router,
        bidding_sync_router,
        bidding_tender_router,
        client_router,
        crm_commission_router,
        crm_contract_router,
        crm_dashboard_router,
        crm_lead_router,
        crm_opportunity_router,
        crm_proposal_router,
        service_router,
    )
    from modules.crm.controllers.client_controller import (
        router as crm_client_router,
    )

    # CRM
    api_router.include_router(crm_client_router, prefix="/crm", tags=["CRM - Clientes"])
    api_router.include_router(crm_lead_router, prefix="/crm", tags=["CRM - Leads"])
    api_router.include_router(crm_opportunity_router, prefix="/crm", tags=["CRM - Oportunidades"])
    api_router.include_router(crm_proposal_router, prefix="/crm", tags=["CRM - Propostas"])
    api_router.include_router(crm_contract_router, prefix="/crm", tags=["CRM - Contratos"])
    api_router.include_router(crm_commission_router, prefix="/crm", tags=["CRM - Comissoes"])
    api_router.include_router(crm_dashboard_router, prefix="/crm", tags=["CRM - Dashboard"])
    # CRM Enrichment (BrasilAPI proxy — CNPJ, CEP, Taxas)
    from modules.crm.controllers.enrichment_controller import router as crm_enrichment_router

    api_router.include_router(crm_enrichment_router, prefix="/crm", tags=["CRM - Enrichment"])
    # CRM Contacts + Activities + 360°
    from modules.crm.controllers.contact_controller import router as crm_contact_router

    api_router.include_router(crm_contact_router, prefix="/crm", tags=["CRM - Contatos & 360"])
    # CRM Growth (9 features HubSpot-like: catálogo, sequências, workflows, forms, agendamento,
    # segmentos, propriedades custom, scoring configurável, forecast)
    from modules.crm.controllers.growth_controller import router as crm_growth_router

    api_router.include_router(crm_growth_router, prefix="/crm", tags=["CRM - Growth"])
    # Marketing
    from modules.crm.controllers.marketing_controller import router as mkt_router

    api_router.include_router(mkt_router, tags=["Marketing"])
    # Clients
    api_router.include_router(client_router, tags=["Clients - Cadastro"])
    # Bidding (Licitações — sem certidões, movidas para fiscal_contabil)
    api_router.include_router(bidding_tender_router, prefix="/bidding", tags=["Bidding - Editais"])
    api_router.include_router(bidding_document_router, prefix="/bidding", tags=["Bidding - Documentos"])
    api_router.include_router(bidding_proposal_router, prefix="/bidding", tags=["Bidding - Propostas"])
    api_router.include_router(bidding_contract_router, prefix="/bidding", tags=["Bidding - Contratos"])
    api_router.include_router(bidding_agent_router, prefix="/bidding", tags=["Bidding - AI Agents"])
    api_router.include_router(bidding_sync_router, prefix="/bidding", tags=["Bidding - Sincronizacao"])
    api_router.include_router(bidding_erp_router, prefix="/bidding", tags=["Bidding - Integracao ERP"])
    # Services
    api_router.include_router(service_router, tags=["Services - Servicos"])
    logger.info("Modulo Comercial: OK (CRM + Clients + Bidding + Services)")
except Exception as e:
    logger.warning(f"Modulo Comercial: {e}")


# =============================================================================
# 2. OPERAÇÕES (operacional + campo)
# =============================================================================
try:
    from modules.operacoes import (
        allocation_router,
        announcement_router,
        banco_horas_alias,
        checklist_router,
        communication_router,
        diarist_fiscal_router,
        diarist_router,
        disciplinary_router,
        employee_router,
        ferias_alias,
        inspection_round_router,
        kpi_trends_router,
        notification_router,
        occurrence_router,
        shift_handover_router,
        team_evaluation_router,
        triage_router,
        presence_router,
        post_orders_router,
        ocorrencias_alias,
        operacional_ai_router,
        operacional_dashboard_router,
        operacional_ws_router,
        ordem_servico_router,
        post_router,
        reports_router,
        scale_router,
        scale_template_router,
        scale_templates_alias,
        shift_router,
        substitution_router,
        time_bank_router,
        vacation_router,
        visita_router,
    )

    # Core
    api_router.include_router(post_router, prefix="/operacional", tags=["Operacional - Postos"])
    api_router.include_router(scale_router, prefix="/operacional", tags=["Operacional - Escalas"])
    api_router.include_router(scale_template_router, prefix="/operacional", tags=["Operacional - Templates de Escalas"])
    api_router.include_router(shift_router, prefix="/operacional", tags=["Operacional - Turnos"])
    api_router.include_router(allocation_router, prefix="/operacional", tags=["Operacional - Alocacoes"])
    api_router.include_router(employee_router, prefix="/operacional", tags=["Operacional - Funcionarios"])
    api_router.include_router(substitution_router, prefix="/operacional", tags=["Operacional - Substituicoes"])
    api_router.include_router(time_bank_router, prefix="/operacional", tags=["Operacional - Banco de Horas"])
    api_router.include_router(reports_router, prefix="/operacional", tags=["Operacional - Relatorios"])
    api_router.include_router(kpi_trends_router, prefix="/operacional", tags=["Operacional - KPI Trends"])
    api_router.include_router(occurrence_router, prefix="/operacional", tags=["Operacional - Ocorrencias"])
    # Diaristas
    api_router.include_router(diarist_router, prefix="/operacional", tags=["Operacional - Diaristas"])
    api_router.include_router(
        diarist_fiscal_router, prefix="/operacional/diaristas/fiscal", tags=["Operacional - Diaristas Fiscal"]
    )
    # Disciplinary
    api_router.include_router(
        disciplinary_router, prefix="/operacional", tags=["Operacional - Medidas Administrativas"]
    )
    # Inspection Rounds
    api_router.include_router(
        inspection_round_router, prefix="/operacional/rondas", tags=["Operacional - Rondas de Inspecao"]
    )
    # Communication
    api_router.include_router(communication_router, prefix="/operacional", tags=["Operacional - Comunicacao"])
    # Vacations
    api_router.include_router(vacation_router, prefix="/operacional", tags=["Operacional - Férias"])
    api_router.include_router(shift_handover_router, prefix="/operacional", tags=["Operacional - Passagem de Turno"])
    api_router.include_router(team_evaluation_router, prefix="/operacional", tags=["Operacional - Avaliação de Equipe"])
    api_router.include_router(triage_router, prefix="/operacional", tags=["Operacional - Triagem"])
    # Fase 2 do enxugamento (2026-07-09): rotas que só existiam no espelho /people-management/operations
    from modules.operacional.controllers.dashboard_controller import router as dashboard_unificado_router
    from modules.people_management.operations.controllers.scale_optimizer_controller import (
        router as scale_optimizer_router,
    )

    api_router.include_router(dashboard_unificado_router, prefix="/operacional/unificado", tags=["Operacional - Visão Unificada"])
    api_router.include_router(scale_optimizer_router, prefix="/operacional", tags=["Operacional - Otimização de Escalas"])
    api_router.include_router(presence_router, prefix="/operacional", tags=["Operacional - Presença"])
    # Grade por pessoa + fluxo falta→substituto (2026-07-10)
    from modules.operacional.controllers.falta_substituto_controller import router as falta_substituto_router
    from modules.operacional.controllers.grade_controller import router as grade_router
    api_router.include_router(falta_substituto_router, prefix="/operacional", tags=["Operacional - Falta e Substituto"])
    api_router.include_router(grade_router, prefix="/operacional", tags=["Operacional - Grade por pessoa"])
    api_router.include_router(post_orders_router, prefix="/operacional", tags=["Operacional - Instruções de Posto"])
    # AI
    api_router.include_router(operacional_ai_router, prefix="/operacional", tags=["Operacional - AI"])
    # WebSocket
    api_router.include_router(operacional_ws_router, prefix="/operacional", tags=["Operacional - WebSocket"])
    # Campo
    api_router.include_router(ordem_servico_router, prefix="/campo/os", tags=["Campo - Ordens de Servico"])
    api_router.include_router(visita_router, prefix="/campo/visitas", tags=["Campo - Visitas"])
    api_router.include_router(checklist_router, prefix="/campo/checklists", tags=["Campo - Checklists"])
    # Campo — service (dashboard/technicians/tickets) + monitoring; estavam só no api/v1 fallback (telas davam 404)
    try:
        from modules.campo import campo_service_router as _campo_svc
        from modules.campo import monitoring_router as _campo_mon

        api_router.include_router(_campo_svc, tags=["Campo - Serviços"])  # router já tem prefix /campo
        api_router.include_router(_campo_mon, prefix="/campo", tags=["Campo - Monitoramento"])
    except Exception as _ce:
        logger.warning("campo_service/monitoring nao montado: %s", _ce)
    # --- Dashboard operacional ---
    api_router.include_router(operacional_dashboard_router, prefix="/operacional", tags=["Operacional - Dashboard"])
    # --- Aliases PT-BR (frontend compatibility — redirects) ---
    api_router.include_router(banco_horas_alias, prefix="/operacional", tags=["Operacional - Banco Horas (alias)"])
    api_router.include_router(ocorrencias_alias, prefix="/operacional", tags=["Operacional - Ocorrencias (alias)"])
    api_router.include_router(ferias_alias, prefix="/operacional", tags=["Operacional - Ferias (alias)"])
    api_router.include_router(
        scale_templates_alias, prefix="/operacional", tags=["Operacional - Scale Templates (alias)"]
    )
    # --- Comunicados e Notificações (direto, sem /comunicacao/) ---
    api_router.include_router(announcement_router, prefix="/operacional", tags=["Operacional - Comunicados"])
    api_router.include_router(notification_router, prefix="/operacional", tags=["Operacional - Notificacoes"])
    logger.info("Modulo Operacoes: OK (Operacional + Campo)")
except Exception as e:
    logger.warning(f"Modulo Operacoes: {e}")


# =============================================================================
# 3. TÉCNICO (equipment + document_kits)
# =============================================================================
try:
    from modules.tecnico import (
        comodato_router,
        document_kit_router,
        documents_router,
        equipment_maintenance_router,
        equipment_router,
        installation_router,
    )

    api_router.include_router(equipment_router, tags=["Equipment"])
    api_router.include_router(installation_router, tags=["Equipment - Instalacoes"])
    api_router.include_router(equipment_maintenance_router, tags=["Equipment - Manutencao"])
    api_router.include_router(comodato_router, tags=["Equipment - Comodato"])
    api_router.include_router(document_kit_router, tags=["Document Kits"])
    if documents_router:
        api_router.include_router(documents_router, tags=["Document Intelligence"])
        logger.info("Modulo Tecnico: OK (Equipment + Document Kits + Documents/OCR)")
    else:
        logger.info("Modulo Tecnico: OK (Equipment + Document Kits)")
except Exception as e:
    logger.warning(f"Modulo Tecnico: {e}")

# Document Kits - Operational Integration (carregamento separado por dependência apscheduler)
try:
    from modules.document_kits.controllers.operational_controller import router as operational_router

    api_router.include_router(operational_router)
    logger.info("Modulo Document Kits Operational: OK")
except Exception as e:
    logger.warning(f"Modulo Document Kits Operational: {e}")


# =============================================================================
# 4. PESSOAS (recruitment + retention + reimbursement + ged)
# =============================================================================
try:
    from modules.pessoas import (
        climate_router,
        ged_config_router,
        ged_document_router,
        ged_folder_router,
        ged_share_router,
        ged_signature_router,
        ged_stats_router,
        ged_tag_router,
        ged_version_router,
        onboarding_router,
        profile_router,
        recruitment_router,
        reimbursement_router,
        turnover_router,
    )

    # Recruitment
    api_router.include_router(recruitment_router, tags=["Recruitment - Recrutamento e Selecao"])
    # Recrutamento (módulo candidatos/vagas/entrevistas/candidaturas) — estava só no api/v1 fallback (telas davam 404)
    try:
        from modules.recruitment import router as _recrutamento_router

        api_router.include_router(_recrutamento_router, tags=["Recrutamento - Candidatos/Vagas/Entrevistas"])
    except Exception as _re:
        logger.warning("recrutamento aggregator nao montado: %s", _re)
    # Retention
    api_router.include_router(onboarding_router, tags=["Retention - Onboarding"])
    api_router.include_router(profile_router, tags=["Retention - Operational Profile"])
    api_router.include_router(climate_router, tags=["Retention - Climate Survey"])
    api_router.include_router(turnover_router, tags=["Retention - Turnover Prediction"])
    # Reimbursement
    api_router.include_router(reimbursement_router, prefix="/reimbursements", tags=["Reimbursement - Reembolsos"])
    # GED
    api_router.include_router(ged_folder_router, prefix="/ged", tags=["GED - Pastas"])
    api_router.include_router(ged_document_router, prefix="/ged", tags=["GED - Documentos"])
    api_router.include_router(ged_version_router, prefix="/ged", tags=["GED - Versoes"])
    api_router.include_router(ged_share_router, prefix="/ged", tags=["GED - Compartilhamentos"])
    api_router.include_router(ged_tag_router, prefix="/ged", tags=["GED - Tags"])
    api_router.include_router(ged_signature_router, prefix="/ged", tags=["GED - Assinaturas"])
    api_router.include_router(ged_stats_router, prefix="/ged", tags=["GED - Estatísticas"])
    api_router.include_router(ged_config_router, prefix="/ged", tags=["GED - Config & Reports"])
    try:
        from modules.ged.controllers.ged_integration_controller import router as ged_integration_router

        api_router.include_router(ged_integration_router, prefix="/ged", tags=["GED - Integracao"])
    except ImportError:
        logger.warning("Modulo GED Integration: falha ao importar (ImportError)")
    try:
        from modules.ged.controllers.ged_certidoes_controller import router as ged_certidoes_router

        api_router.include_router(ged_certidoes_router, prefix="/ged", tags=["GED - Certidões"])
        logger.info("Modulo GED Certidoes: OK")
    except Exception as e:
        logger.warning(f"Modulo GED Certidoes: {e}")
    logger.info("Modulo Pessoas: OK (Recruitment + Retention + Reimbursement + GED + Integracao)")
except Exception as e:
    logger.warning(f"Modulo Pessoas: {e}")

# CCT 2026 SINDECOMPRESTS
try:
    from modules.people_management.hr.controllers.cct_controller import router as cct_router

    api_router.include_router(cct_router, prefix="/people-management/hr", tags=["CCT 2026 SINDECOMPRESTS"])
    logger.info("Modulo CCT 2026 SINDECOMPRESTS: OK")
except Exception as e:
    logger.warning(f"Modulo CCT: {e}")

# GED Auto-Assemble + Dashboard (standalone, fora de people_management p/ evitar import circular)
try:
    from modules.ged.controllers.auto_assemble_controller import router as ged_auto_assemble_router

    api_router.include_router(ged_auto_assemble_router, prefix="/ged", tags=["GED - Auto-Assemble"])
    logger.info("Modulo GED Auto-Assemble: OK")
except Exception as e:
    logger.warning(f"Modulo GED Auto-Assemble: {e}")

# NFS-e e Dashboard Financeiro
try:
    from modules.ged.controllers.nfse_controller import router as nfse_router

    api_router.include_router(nfse_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["NFS-e - Faturamento"])
    logger.info("Modulo NFS-e Faturamento: OK")
except Exception as e:
    logger.warning(f"Modulo NFS-e Faturamento: {e}")

# Financial Overview (endpoints para /modulos/financeiro page)
try:
    from modules.ged.controllers.financial_overview_controller import router as fin_overview_router

    api_router.include_router(fin_overview_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial Overview"])
    logger.info("Modulo Financial Overview: OK")
except Exception as e:
    logger.warning(f"Modulo Financial Overview: {e}")

# GED Kit PDFs: geração, ZIP, email
try:
    from modules.ged.controllers.kit_pdf_controller import router as kit_pdf_router

    api_router.include_router(kit_pdf_router, prefix="/ged", tags=["GED - Kit PDFs"])
    logger.info("Modulo GED Kit PDFs: OK")
except Exception as e:
    logger.warning(f"Modulo GED Kit PDFs: {e}")

# GED Kit Real (anatomia auditada Google Drive)
try:
    from modules.ged.controllers.kit_real_controller import router as kit_real_router

    api_router.include_router(kit_real_router, prefix="/ged", tags=["GED - Kit Real"])
    logger.info("Modulo GED Kit Real: OK")
except Exception as e:
    logger.warning(f"Modulo GED Kit Real: {e}")

# GED Coleta Automatica (D4 — config, run manual, historico)
try:
    from modules.people_management.ged.controllers.coleta_automatica_controller import (
        router as ged_coleta_router,
    )

    api_router.include_router(ged_coleta_router, prefix="/ged", tags=["GED - Coleta Automatica"])
    logger.info("Modulo GED Coleta Automatica: OK")
except Exception as e:
    logger.warning(f"Modulo GED Coleta Automatica: {e}")

# Saude Ocupacional (NR-4, NR-6, NR-7, NR-9)
try:
    from modules.health_occupational import router as health_occupational_router

    api_router.include_router(health_occupational_router, tags=["Health - Saude Ocupacional"])
    logger.info("Modulo Saude Ocupacional: OK (PCMSO + PPRA + EPI)")
except Exception as e:
    logger.warning(f"Modulo Saude Ocupacional: {e}")


# =============================================================================
# 5. FINANCEIRO (financial completo)
# =============================================================================
try:
    from modules.financeiro import (
        accounting_router,
        bank_account_router,
        bank_reconciliation_router,
        bank_transaction_router,
        bi_dashboard_router,
        billing_rule_router,
        cashflow_router,
        customer_router,
        financial_ai_router,
        fiscal_router,
        inventory_router,
        nfse_entrada_router,
        payable_router,
        purchase_router,
        receivable_category_router,
        receivable_router,
        relatorios_router,
        supplier_router,
    )

    api_router.include_router(accounting_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial - Contabilidade"])
    api_router.include_router(supplier_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial - Fornecedores"])
    api_router.include_router(payable_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial - Contas a Pagar"])
    api_router.include_router(customer_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial - Clientes"])
    api_router.include_router(receivable_category_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial - Categorias"])
    api_router.include_router(receivable_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial - Contas a Receber"])
    api_router.include_router(billing_rule_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial - Regras de Cobranca"])
    api_router.include_router(bank_account_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial - Contas Bancarias"])
    api_router.include_router(bank_transaction_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial - Transacoes"])
    api_router.include_router(bank_reconciliation_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial - Conciliacao"])
    api_router.include_router(cashflow_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial - Fluxo de Caixa"])
    api_router.include_router(purchase_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial - Compras"])
    api_router.include_router(inventory_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial - Estoque"])
    api_router.include_router(fiscal_router, dependencies=[_FISCAL_GATE], prefix="/financial", tags=["Financial - Fiscal/Tributário"])
    # ALIAS de compat: o client GERADO do frontend (orval, a partir do openapi de dev/main.py)
    # chama /financial/fiscal/fiscal/* (prefixo dobrado). Em produção só existia o single e a
    # tela Gestão Fiscal 404-ava. Servimos o dobrado TAMBÉM, mesmo gate, até regenerar o client.
    api_router.include_router(
        fiscal_router, dependencies=[_FISCAL_GATE], prefix="/financial/fiscal",
        tags=["Financial - Fiscal/Tributário (alias client gerado)"], include_in_schema=False,
    )
    api_router.include_router(financial_ai_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial AI"])
    api_router.include_router(relatorios_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial - Relatórios"])
    api_router.include_router(bi_dashboard_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial - BI Dashboard"])
    if nfse_entrada_router:
        api_router.include_router(nfse_entrada_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial - NFS-e Entrada"])
    logger.info("Modulo Financeiro: OK (18 routers)")
except Exception as e:
    logger.warning(f"Modulo Financeiro: {e}")

# Justificativas Fiscais — Saídas Sem NF (Lucro Real)
try:
    from modules.financial.controllers.justificativa_controller import (
        router as justificativa_router,
    )

    api_router.include_router(justificativa_router, dependencies=[_FIN_GATE], tags=["Justificativas Fiscais"])
    logger.info("Justificativas Fiscais: OK")
except Exception as _e:
    logger.warning(f"Justificativas Fiscais: {_e}")

# Dashboard Financeiro — KPIs + Cashflow Forecast + BI Overview
try:
    from modules.financial.controllers.financial_dashboard_controller import (
        router as financial_dashboard_router,
    )

    api_router.include_router(financial_dashboard_router, dependencies=[_FIN_GATE], tags=["Financial Dashboard"])
    logger.info("Financial Dashboard: OK (dashboard + cashflow/forecast + bi/overview)")
except Exception as _e:
    logger.warning(f"Financial Dashboard: {_e}")

# Custeio ABC + Precificação — CCT SINDECOMPRESTS 2026
try:
    from modules.financial.controllers.custeio_controller import router as custeio_router
    from modules.financial.controllers.precificacao_controller import router as precificacao_router

    api_router.include_router(custeio_router, dependencies=[_FIN_GATE], tags=["Financial - Custeio ABC"])
    api_router.include_router(precificacao_router, tags=["Financial - Precificação"])
    logger.info("Custeio ABC + Precificação: OK")
except Exception as _e:
    logger.warning(f"Custeio ABC + Precificação: {_e}")

# Cobrança PIX Recorrente — MRR Clientes Conecta Mais
try:
    from modules.financial.controllers.recurring_billing_controller import (
        router as recurring_billing_router,
    )

    api_router.include_router(
        recurring_billing_router, dependencies=[_FIN_GATE], prefix="/financial", tags=["Financial - Cobrança Recorrente PIX"]
    )
    logger.info("Cobrança Recorrente PIX: OK")
except Exception as _e:
    logger.warning(f"Cobrança Recorrente PIX: {_e}")

# Conciliação Automática Inter × Notas
try:
    from modules.financial.controllers.auto_reconciliation_controller import (
        router as auto_reconciliation_router,
    )

    api_router.include_router(
        auto_reconciliation_router,
        dependencies=[_FIN_GATE],
        prefix="/financial",
        tags=["Financial - Conciliação Automática Inter"],
    )
    logger.info("Conciliação Automática Inter: OK")
except Exception as _e:
    logger.warning(f"Conciliação Automática: {_e}")

# MCP Financial Server — 8 ferramentas via HTTP REST
try:
    from modules.financial.controllers.mcp_financial_controller import (
        router as mcp_financial_router,
    )

    api_router.include_router(mcp_financial_router, tags=["MCP Financial"])
    logger.info("MCP Financial Server: OK (8 ferramentas)")
except Exception as _e:
    logger.warning(f"MCP Financial Server: {_e}")


# =============================================================================
# 6. FISCAL/CONTÁBIL (empresas + fiscal + government)
# =============================================================================
try:
    from modules.fiscal_contabil import (
        bidding_certificate_router,
        bookkeeper_router,
        dominio_router,
        empresas_dashboard_router,
        empresas_router,
        government_integrations_router,
        migrador_router,
        nfse_multi_router,
        obrigacoes_router,
        statements_router,
    )

    # Empresas Multi-CNPJ
    api_router.include_router(empresas_router, tags=["Empresas - Multi-CNPJ"])
    api_router.include_router(migrador_router, prefix="/empresas", tags=["Migrador de Contratos"])
    api_router.include_router(obrigacoes_router, prefix="/empresas", tags=["Obrigações Multi-Empresa"])
    api_router.include_router(empresas_dashboard_router, prefix="/empresas", tags=["Dashboard Multi-Empresa"])
    api_router.include_router(dominio_router, tags=["Domínio TOTVS"])
    api_router.include_router(bookkeeper_router, tags=["Escrituração Contábil"])
    api_router.include_router(statements_router, tags=["Demonstrativos Financeiros"])
    # Fiscal
    api_router.include_router(nfse_multi_router, prefix="/fiscal", tags=["Fiscal - NFS-e Multi-Empresa"])
    # Government
    api_router.include_router(government_integrations_router, tags=["Government"])
    # Certidões (CNDs) — movido de comercial/bidding
    api_router.include_router(bidding_certificate_router, prefix="/bidding", tags=["Certidões - CNDs"])
    logger.info("Modulo Fiscal/Contabil: OK (Empresas + Fiscal + Government + Certidoes)")
except Exception as e:
    logger.warning(f"Modulo Fiscal/Contabil: {e}")

# NF-e Entrada (compras de fornecedores) — bloco isolado
try:
    from modules.fiscal_contabil.notas_fiscais.nfe.entrada_controller import (
        router as _nfe_entrada_router,
    )

    api_router.include_router(_nfe_entrada_router, prefix="/fiscal", tags=["NF-e Entrada/Compras"])
    logger.info("NF-e Entrada: OK (upload-xml + listar + estoque + sync-sefaz)")
except Exception as _e:
    logger.warning(f"NF-e Entrada: {_e}")

# NF-e Produto/Saída (emissão via SEFAZ-AM) — bloco isolado
try:
    from modules.fiscal_contabil.notas_fiscais.nfe.controller import (
        router as _nfe_emissao_router,
    )

    api_router.include_router(_nfe_emissao_router, prefix="/fiscal", tags=["NF-e Produto"])
    logger.info("NF-e Produto: OK (emitir + listar + status + sefaz-status)")
except Exception as _e:
    logger.warning(f"NF-e Produto: {_e}")

# Dashboard Fiscal-Financeiro (DRE + NFS-e + NF-e + Folha + Fluxo + Estoque)
try:
    from modules.financial.controllers.fiscal_dashboard_controller import (
        router as _fiscal_dash_router,
    )

    api_router.include_router(_fiscal_dash_router, tags=["Dashboard Fiscal"])
    logger.info("Dashboard Fiscal: OK (DRE + NFS-e + NF-e + Folha + Fluxo + Estoque)")
except Exception as _e:
    logger.warning(f"Dashboard Fiscal: {_e}")

# Government Integrations — bloco isolado (evita dependência do bidding/operacional.ai)
try:
    from modules.government_integrations import government_integrations_router as _gov_router

    api_router.include_router(_gov_router, tags=["Government"])
    logger.info("Government Integrations: OK (NFS-e Nacional + Manaus + eSocial + FGTS + SEFAZ)")
except Exception as e:
    logger.warning(f"Government Integrations (isolado): {e}")


# =============================================================================
# 7. INTELIGÊNCIA (analytics + reports + monitoring + search)
# =============================================================================
try:
    from modules.inteligencia import (
        analytics_router,
        executive_dashboard_router,
        monitoring_router,
        report_router,
    )

    api_router.include_router(executive_dashboard_router, prefix="/analytics", tags=["Analytics - Executive Dashboard"])
    api_router.include_router(analytics_router, tags=["Analytics - Predictive"])
    api_router.include_router(report_router, tags=["Reports - Relatorios"])
    api_router.include_router(monitoring_router, tags=["Monitoring"])
    # Intelligence Hub — desabilitado (bloqueia startup com workers pesados)
    # Para reativar: resolver inicializacao sincrona em intelligence_hub/__init__.py
    logger.info("Modulo Inteligencia: OK (Analytics + Reports + Monitoring)")
except Exception as e:
    logger.warning(f"Modulo Inteligencia: {e}")

# OpenClaw — Multi-Agent alert response system
try:
    from modules.ai.openclaw.controller import router as openclaw_router

    api_router.include_router(openclaw_router, prefix="/ai", tags=["AI - OpenClaw Alert Response"])
    logger.info("Modulo OpenClaw: OK (Alert webhook + Remediation)")
except Exception as e:
    logger.warning(f"Modulo OpenClaw: {e}")


# =============================================================================
# 8. GESTÃO (config + audit + notifications + mobile + workflows + integrations)
# =============================================================================
try:
    from modules.gestao import (
        audit_router,
        banking_router,
        config_router,
        connector_router,
        integration_router,
        intelligent_notification_router,
        mobile_router,
        notification_router,
        push_notification_router,
        solides_router,
        whatsapp_router,
        workflow_router,
    )

    # Config
    api_router.include_router(config_router, tags=["Config - Configuracoes"])
    # Audit
    api_router.include_router(audit_router, tags=["Audit - Auditoria"])
    # Notifications
    api_router.include_router(notification_router, prefix="", tags=["Notifications - Hub"])
    api_router.include_router(
        intelligent_notification_router, prefix="/notifications", tags=["Notifications - Intelligent"]
    )
    api_router.include_router(push_notification_router, prefix="/notifications", tags=["Notifications - Push"])
    # Mobile
    api_router.include_router(mobile_router, tags=["Mobile - API Nativa"])
    # Workflows
    api_router.include_router(workflow_router, prefix="/workflows", tags=["Workflows"])
    # Integrations
    api_router.include_router(integration_router, tags=["Integrations - API Gateway"])
    api_router.include_router(connector_router, tags=["Integrations - Conectores"])
    api_router.include_router(solides_router, prefix="/integrations", tags=["Integrations - Sólides RH/DP"])
    api_router.include_router(banking_router, dependencies=[_FIN_GATE], prefix="/integrations", tags=["Integrations - Banking"])
    # D6 — Inter endpoints consolidados (/financeiro/inter/)
    try:
        from modules.integrations.inter.inter_controller import router as _inter_d6_router

        api_router.include_router(_inter_d6_router, dependencies=[_FIN_GATE])
        logger.info("D6 Inter controller: OK")
    except Exception as _e:
        logger.warning(f"D6 Inter controller: {_e}")
    try:
        from modules.integrations.inter.payment_controller import router as _inter_d7_router

        api_router.include_router(_inter_d7_router, dependencies=[_FIN_GATE])
        logger.info("D7 Inter payment controller: OK")
    except Exception as _e:
        logger.warning(f"D7 Inter payment controller: {_e}")
    # Banking Payments (DARF + barcode + lote)
    try:
        from modules.integrations.banking.controllers.payment_controller import (
            router as _payment_router,
        )

        api_router.include_router(_payment_router, dependencies=[_FIN_GATE], tags=["Banking — Pagamentos"])
        logger.info("Banking Payments: OK (barcode + DARF + lote)")
    except Exception as _e:
        logger.warning(f"Banking Payments: {_e}")
    # WhatsApp (Evolution API)
    if whatsapp_router:
        api_router.include_router(whatsapp_router, tags=["WhatsApp - Evolution API"])
    logger.info("Modulo Gestao: OK (Config + Audit + Notifications + Mobile + Workflows + Integrations + WhatsApp)")
except Exception as e:
    logger.warning(f"Modulo Gestao: {e}")


# 9. CADASTROS - reservado para dados mestres (módulo futuro)
# Importações serão adicionadas conforme refatoração avançar


# =============================================================================
# 10. GESTÃO DE PESSOAS (people_management: DP + RH + Operations + Portal)
# =============================================================================
try:
    from modules.people_management import router as people_management_router

    api_router.include_router(people_management_router)
    logger.info("Modulo People Management: OK (DP + RH + Operations + Portal + GED)")
except Exception as e:
    logger.warning(f"Modulo People Management: {e}")


# =============================================================================
# 11. AREA DO CLIENTE (client_portal: Auth + Kits + Chamados)
# =============================================================================
try:
    from modules.client_portal import router as client_portal_router

    api_router.include_router(client_portal_router)
    logger.info("Modulo Client Portal: OK (Auth + Kits + Tickets)")
except Exception as e:
    logger.warning(f"Modulo Client Portal: {e}")


# =============================================================================
# 12. CCT 2026 — SINDECOMPRESTS/SINDICOND-AM
# =============================================================================
try:
    from modules.cct import router as cct_router

    api_router.include_router(cct_router)
    logger.info("Modulo CCT 2026: OK (Salarios + Beneficios + Jornadas + Compliance + Rescisao + Feriados)")
except Exception as e:
    logger.warning(f"Modulo CCT 2026: {e}")


# =============================================================================
# 13. CCT DB ADMIN — Admin endpoints para gerenciar CCT no banco
# =============================================================================
try:
    from modules.people_management.cct.controllers.admin_cct_controller import (
        router as admin_cct_router,
    )

    api_router.include_router(admin_cct_router, prefix="/people-management")
    logger.info("Admin CCT DB: OK (CRUD convenções, cargos, feriados, benefícios)")
except Exception as e:
    logger.warning(f"Admin CCT DB: {e}")


# =============================================================================
# 14. DP PAYSLIPS — Endpoint para DP publicar contracheques
# =============================================================================
try:
    from modules.people_management.employee_portal.controllers.dp_payslips_controller import (
        payroll_router as dp_payroll_router,
    )
    from modules.people_management.employee_portal.controllers.dp_payslips_controller import (
        router as dp_payslips_router,
    )

    api_router.include_router(dp_payslips_router, prefix="/people-management")
    api_router.include_router(dp_payroll_router, prefix="/people-management")
    logger.info("DP Payslips: OK (criar/publicar/importar contracheques + pay-batch PIX)")
except Exception as e:
    logger.warning(f"DP Payslips: {e}")


try:
    from modules.gedeon.controllers.gedeon_controller import router as gedeon_router

    api_router.include_router(gedeon_router)
    logger.info("GEDEON: router registrado (/gedeon)")
except Exception as e:
    logger.warning(f"GEDEON router: {e}")

try:
    from modules.gedeon.controllers.kit_controller import router as gedeon_kit_router

    api_router.include_router(gedeon_kit_router)
    logger.info("GEDEON Kits: router registrado (/gedeon/kits)")
except Exception as e:
    logger.warning(f"GEDEON Kits router: {e}")

try:
    from modules.gedeon.controllers.orquestrador_controller import router as gedeon_orq_router

    api_router.include_router(gedeon_orq_router)
    logger.info("GEDEON Montagem: router registrado (/gedeon/kits/montagem|painel)")
except Exception as e:
    logger.warning(f"GEDEON Montagem router: {e}")

try:
    from modules.gedeon.controllers.cnd_controller import router as gedeon_cnd_router

    api_router.include_router(gedeon_cnd_router)
    logger.info("GEDEON CND: router registrado (/gedeon/cnd/emitir|status|pdf)")
except Exception as e:
    logger.warning(f"GEDEON CND router: {e}")

try:
    from modules.gedeon.onvio.controllers.onvio_controller import router as onvio_router

    api_router.include_router(onvio_router)
    logger.info("GEDEON Onvio: router registrado (/onvio)")
except Exception as e:
    logger.warning(f"GEDEON Onvio router: {e}")

try:
    from modules.gedeon.controllers.onvio_controller import router as onvio_stats_router

    api_router.include_router(onvio_stats_router)
    logger.info("GEDEON Onvio Stats: router registrado (/onvio/stats)")
except Exception as e:
    logger.warning(f"GEDEON Onvio Stats router: {e}")

# GEDEON — Consultor GED IA (chat de kits + intercorrências do mês, padrão CFO/Jurídico)
try:
    from modules.gedeon.controllers.consultor_controller import router as gedeon_consultor_router

    api_router.include_router(gedeon_consultor_router)
    logger.info("GEDEON Consultor GED IA: router registrado (/gedeon/consultor)")
except Exception as e:
    logger.warning(f"GEDEON Consultor router: {e}")

# ── Time de Consultores IA por módulo (hub compartilhado: memória + conversa cruzada) ──
try:
    from modules.crm.controllers.consultor_cmo_controller import router as consultor_cmo_router

    api_router.include_router(consultor_cmo_router)
    logger.info("Consultor CMO: router registrado (/comercial/consultor)")
except Exception as e:
    logger.warning(f"Consultor CMO router: {e}")

try:
    from modules.operacional.controllers.consultor_coo_controller import router as consultor_coo_router

    api_router.include_router(consultor_coo_router)
    logger.info("Consultor COO: router registrado (/operacional/consultor)")
except Exception as e:
    logger.warning(f"Consultor COO router: {e}")

try:
    from modules.people_management.controllers.consultor_chro_controller import router as consultor_chro_router

    api_router.include_router(consultor_chro_router)
    logger.info("Consultor CHRO: router registrado (/rh/consultor)")
except Exception as e:
    logger.warning(f"Consultor CHRO router: {e}")

try:
    from modules.fiscal.controllers.consultor_fiscal_controller import router as consultor_fiscal_router

    api_router.include_router(consultor_fiscal_router)
    logger.info("Consultor Fiscal: router registrado (/fiscal/consultor)")
except Exception as e:
    logger.warning(f"Consultor Fiscal router: {e}")

try:
    from modules.config.controllers.consultor_ceo_controller import router as consultor_ceo_router

    api_router.include_router(consultor_ceo_router)
    logger.info("Consultor CEO: router registrado (/gestao/consultor)")
except Exception as e:
    logger.warning(f"Consultor CEO router: {e}")

try:
    from modules.gdrive.controllers.gdrive_controller import router as gdrive_router

    api_router.include_router(gdrive_router)
    logger.info("GDrive: router registrado (/gdrive)")
except Exception as e:
    logger.warning(f"GDrive router: {e}")

try:
    from modules.integrations.banking.controllers.webhook_controller import (
        router as _webhook_router,
    )

    api_router.include_router(_webhook_router, tags=["Webhooks — Inter"])
    logger.info("Webhooks Inter: OK (pix + boleto + configurar + status)")
except Exception as _e:
    logger.warning(f"Webhooks Inter: {_e}")

try:
    from modules.juridico.skills_controller import router as juridico_skills_router

    api_router.include_router(juridico_skills_router)
    logger.info("Jurídico Skills: OK (089, 090, 092, 095, 253, 305, 318)")
except Exception as _e:
    logger.warning(f"Jurídico Skills: {_e}")

try:
    from modules.juridico.contracts_controller import router as juridico_contratos_router

    api_router.include_router(juridico_contratos_router)
    logger.info("Jurídico — Central de Contratos: OK")
except Exception as _e:
    logger.warning(f"Jurídico — Central de Contratos: {_e}")

# Escritório Jurídico IA — Consultor, Pareceres/Análise, Riscos, Escritório/ROI, Hub/Prazos
for _mod, _label in [
    ("modules.juridico.consultor_controller", "Consultor IA"),
    ("modules.juridico.documentos_controller", "Pareceres/Análise"),
    ("modules.juridico.riscos_controller", "Riscos"),
    ("modules.juridico.escritorio_controller", "Escritório/ROI"),
    ("modules.juridico.hub_controller", "Hub/Prazos"),
    ("modules.juridico.context_controller", "Contexto/Discovery cross-módulo"),
    ("modules.juridico.processos_controller", "Processos & Defesa (intake)"),
    ("modules.juridico.conhecimento_controller", "Base de Conhecimento & Playbook"),
    ("modules.juridico.det_controller", "Monitoramento DET"),
]:
    try:
        import importlib

        _m = importlib.import_module(_mod)
        api_router.include_router(_m.router)
        logger.info("Jurídico — %s: OK", _label)
    except Exception as _e:  # noqa: BLE001
        logger.warning("Jurídico — %s: %s", _label, _e)

# Financeiro — CFO IA (consultor financeiro ancorado nos números reais do ERP)
try:
    import importlib as _il_cfo

    _cfo_mod = _il_cfo.import_module("modules.financial.cfo_controller")
    api_router.include_router(_cfo_mod.router, dependencies=[_FIN_GATE])
    logger.info("Financeiro — CFO IA: OK")
except Exception as _e:  # noqa: BLE001
    logger.warning("Financeiro — CFO IA: %s", _e)

# Financeiro — Pagamentos de diaristas (elo Operacional→Financeiro: escala vira lote a pagar)
try:
    import importlib as _il_pgd

    _pgd_mod = _il_pgd.import_module("modules.financial.pagamentos_diaristas_controller")
    api_router.include_router(_pgd_mod.router, dependencies=[_FIN_GATE])
    logger.info("Financeiro — Pagamentos Diaristas: OK")
except Exception as _e:  # noqa: BLE001
    logger.warning("Financeiro — Pagamentos Diaristas: %s", _e)

# Financeiro — Agenda de beneficiários PIX (favoritos: digitar nome → carrega a chave)
try:
    import importlib as _il_ben

    _ben_mod = _il_ben.import_module("modules.financial.beneficiarios_controller")
    api_router.include_router(_ben_mod.router, dependencies=[_FIN_GATE])
    logger.info("Financeiro — Agenda Beneficiários: OK")
except Exception as _e:  # noqa: BLE001
    logger.warning("Financeiro — Agenda Beneficiários: %s", _e)

# Operacional — Diárias (modelo da planilha: cadastros + lançamento c/ valor automático + resumo dia 15)
try:
    import importlib as _il_dia

    _dia_mod = _il_dia.import_module("modules.operacional.diaristas.diarias_controller")
    api_router.include_router(_dia_mod.router)
    logger.info("Operacional — Diárias: OK")
except Exception as _e:  # noqa: BLE001
    logger.warning("Operacional — Diárias: %s", _e)

# Incluir router principal
try:
    from modules.scheduler.controllers import router as _scheduler_router

    api_router.include_router(_scheduler_router, tags=["Scheduler - Agendamento"])  # router já tem prefix /scheduler
except Exception as _e:
    logger.warning("scheduler_router nao montado: %s", _e)

# Assinatura Universal — motor central de assinatura eletrônica (funcionário/empresa/cliente)
try:
    from modules.signatures.controllers import signature_router as _universal_signature_router

    api_router.include_router(_universal_signature_router)  # router já tem prefix /signatures
    logger.info("Módulo Assinatura Universal: OK")
except Exception as _e:  # noqa: BLE001
    logger.warning("Assinatura Universal nao montado: %s", _e)

app.include_router(api_router)

logger.info("=== API CONECTA PRO INICIADA (14 módulos) ===")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main_production:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
