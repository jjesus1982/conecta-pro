"""
Controller do Dashboard de Monitoramento.

Endpoints para visualização de métricas e status das integrações.
"""

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from core.auth.dependencies import CurrentActiveUser

from ..core.contingency import VerificadorDisponibilidade
from ..core.credentials import GerenciadorCertificados, get_vault_client
from ..core.events import get_event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard Monitoramento"])


# ============================================================================
# Schemas
# ============================================================================


class ResumoExtracao(BaseModel):
    """Resumo de extrações do período."""

    total_documentos: int = 0
    documentos_novos: int = 0
    documentos_atualizados: int = 0
    documentos_erro: int = 0
    extracoes_executadas: int = 0
    extracoes_sucesso: int = 0
    extracoes_falha: int = 0
    ultima_extracao: datetime | None = None


class ResumoServico(BaseModel):
    """Resumo por serviço governamental."""

    servico: str
    nome_exibicao: str
    status: str  # online, offline, degraded
    documentos_processados: int = 0
    documentos_erro: int = 0
    ultima_sincronizacao: datetime | None = None
    tempo_medio_resposta_ms: float | None = None
    taxa_sucesso: float = 100.0


class StatusEndpoint(BaseModel):
    """Status de um endpoint."""

    uf: str
    servico: str
    endpoint: str
    disponivel: bool
    tempo_resposta_ms: float | None = None
    ultimo_check: datetime
    falhas_consecutivas: int = 0


class AlertaCertificado(BaseModel):
    """Alerta de certificado expirando."""

    tenant_id: str
    tipo_certificado: str
    dias_restantes: int
    validade_fim: datetime
    severidade: str  # warning, critical


class EventoRecente(BaseModel):
    """Evento recente do sistema."""

    tipo: str
    servico: str | None = None
    uf: str | None = None
    descricao: str
    severidade: str
    timestamp: datetime
    detalhes: dict[str, Any] | None = None


class DashboardResponse(BaseModel):
    """Resposta completa do dashboard."""

    periodo_inicio: datetime
    periodo_fim: datetime
    resumo_geral: ResumoExtracao
    servicos: list[ResumoServico]
    endpoints_indisponiveis: list[StatusEndpoint]
    alertas_certificados: list[AlertaCertificado]
    eventos_recentes: list[EventoRecente]
    atualizado_em: datetime


class MetricasResponse(BaseModel):
    """Métricas detalhadas por período."""

    periodo_inicio: datetime
    periodo_fim: datetime
    documentos_por_dia: dict[str, int]
    documentos_por_servico: dict[str, int]
    erros_por_servico: dict[str, int]
    tempo_medio_por_servico: dict[str, float]


# ============================================================================
# Service Layer
# ============================================================================


class IntegrationStatusItem(BaseModel):
    """Status de uma integração individual."""

    id: str
    name: str
    category: str  # banking, government, hr
    status: str  # online, offline, degraded
    description: str
    last_check: datetime | None = None
    last_sync: datetime | None = None
    response_time_ms: float | None = None
    error_message: str | None = None


class IntegrationStatusResponse(BaseModel):
    """Resposta do status de todas as integrações."""

    total: int
    online: int
    offline: int
    degraded: int
    integrations: list[IntegrationStatusItem]
    checked_at: datetime


class DashboardService:
    """Serviço de coleta de métricas para o dashboard."""

    SERVICOS = {
        "sefaz_nfe": "NF-e/NFC-e",
        "sefaz_cte": "CT-e",
        "sefaz_mdfe": "MDF-e",
        "esocial": "eSocial",
        "fgts_digital": "FGTS Digital",
        "nfse_manaus": "NFS-e Manaus",
        "receita_federal": "Receita Federal",
        "simples_nacional": "Simples Nacional",
    }

    ALL_INTEGRATIONS = [
        {"id": "inter", "name": "Banco Inter", "category": "banking", "description": "Saldo, extrato, PIX, cobranças"},
        {"id": "govbr", "name": "Gov.br", "category": "government", "description": "Autenticação SSO governo federal"},
        {"id": "sefaz_nfe", "name": "SEFAZ NF-e", "category": "government", "description": "Notas fiscais eletrônicas"},
        {
            "id": "sefaz_cte",
            "name": "SEFAZ CT-e",
            "category": "government",
            "description": "Conhecimento de transporte",
        },
        {
            "id": "sefaz_mdfe",
            "name": "SEFAZ MDF-e",
            "category": "government",
            "description": "Manifesto de documentos fiscais",
        },
        {
            "id": "nfse_manaus",
            "name": "NFS-e Manaus",
            "category": "government",
            "description": "Nota fiscal de serviços (Manaus)",
        },
        {
            "id": "esocial",
            "name": "eSocial",
            "category": "government",
            "description": "Eventos trabalhistas e previdenciários",
        },
        {
            "id": "fgts_digital",
            "name": "FGTS Digital",
            "category": "government",
            "description": "Guias, saldos e rescisões",
        },
        {
            "id": "efd_reinf",
            "name": "EFD-Reinf",
            "category": "government",
            "description": "Escrituração fiscal de retenções",
        },
        {"id": "sped_fiscal", "name": "SPED Fiscal", "category": "government", "description": "EFD-ICMS/IPI"},
        {
            "id": "sped_contabil",
            "name": "SPED Contábil",
            "category": "government",
            "description": "Escrituração contábil digital",
        },
        {"id": "ecac", "name": "e-CAC", "category": "government", "description": "Situação fiscal e certidões"},
        {"id": "dctfweb", "name": "DCTFWeb", "category": "government", "description": "DARFs e declarações"},
        {
            "id": "simples_nacional",
            "name": "Simples Nacional",
            "category": "government",
            "description": "DAS, PGDAS-D, Fator R",
        },
        {
            "id": "receita_federal",
            "name": "Receita Federal",
            "category": "government",
            "description": "Validação CPF/CNPJ",
        },
        {"id": "solides", "name": "Sólides", "category": "hr", "description": "Sincronização RH/DP"},
    ]

    def __init__(self):
        self.event_bus = get_event_bus()
        self.verificador = VerificadorDisponibilidade()

    async def obter_dashboard(self, tenant_id: UUID | None = None, periodo_dias: int = 7) -> DashboardResponse:
        """Obtém dados completos do dashboard."""
        periodo_fim = datetime.utcnow()
        periodo_inicio = periodo_fim - timedelta(days=periodo_dias)

        # Coletar dados
        resumo = await self._obter_resumo_geral(tenant_id, periodo_inicio, periodo_fim)
        servicos = await self._obter_status_servicos(tenant_id, periodo_inicio, periodo_fim)
        endpoints_down = await self._obter_endpoints_indisponiveis()
        alertas_cert = await self._obter_alertas_certificados(tenant_id)
        eventos = await self._obter_eventos_recentes(tenant_id, limite=20)

        return DashboardResponse(
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            resumo_geral=resumo,
            servicos=servicos,
            endpoints_indisponiveis=endpoints_down,
            alertas_certificados=alertas_cert,
            eventos_recentes=eventos,
            atualizado_em=datetime.utcnow(),
        )

    async def _obter_resumo_geral(self, tenant_id: UUID | None, inicio: datetime, fim: datetime) -> ResumoExtracao:
        """Obtém resumo geral das extrações."""
        # Em produção, buscar do banco de dados
        # SELECT COUNT(*), SUM(documentos_novos), ... FROM extracoes WHERE ...

        return ResumoExtracao(
            total_documentos=0,
            documentos_novos=0,
            documentos_atualizados=0,
            documentos_erro=0,
            extracoes_executadas=0,
            extracoes_sucesso=0,
            extracoes_falha=0,
            ultima_extracao=None,
        )

    async def _obter_status_servicos(
        self, tenant_id: UUID | None, inicio: datetime, fim: datetime
    ) -> list[ResumoServico]:
        """
        Obtém status de cada serviço a partir dos SyncLog reais (gov_sync_logs).

        NAO afirma "online/100%" sem checagem: serviços sem registro de
        sincronização são marcados "nao_configurado". O status/taxa refletem
        o último SyncLog observado por serviço.
        """
        # Agregar SyncLog real por serviço
        stats = await self._agregar_sync_logs()

        servicos = []
        for codigo, nome in self.SERVICOS.items():
            info = stats.get(codigo)
            if info is None:
                # Sem sincronização registrada: não há base para afirmar "online"
                servicos.append(
                    ResumoServico(
                        servico=codigo,
                        nome_exibicao=nome,
                        status="nao_configurado",
                        documentos_processados=0,
                        documentos_erro=0,
                        ultima_sincronizacao=None,
                        tempo_medio_resposta_ms=None,
                        taxa_sucesso=0.0,
                    )
                )
                continue

            servicos.append(
                ResumoServico(
                    servico=codigo,
                    nome_exibicao=nome,
                    status=info["status"],
                    documentos_processados=info["processados"],
                    documentos_erro=info["erros"],
                    ultima_sincronizacao=info["ultima_sincronizacao"],
                    tempo_medio_resposta_ms=None,
                    taxa_sucesso=info["taxa_sucesso"],
                )
            )

        return servicos

    async def _agregar_sync_logs(self) -> dict[str, dict[str, Any]]:
        """
        Lê gov_sync_logs e devolve, por serviço, o status derivado do último
        log e agregados de processados/erros. Se a tabela/consulta falhar,
        devolve {} (nenhum serviço marcado online sem base real).
        """
        resultado: dict[str, dict[str, Any]] = {}
        try:
            from sqlalchemy import func, select

            from core.database.session import async_session_factory

            from ..models.sync_models import SyncLog

            async with async_session_factory() as db:
                # Agregados por serviço
                agg_stmt = select(
                    SyncLog.servico,
                    func.sum(SyncLog.registros_processados),
                    func.sum(SyncLog.registros_erro),
                    func.max(SyncLog.inicio_execucao),
                ).group_by(SyncLog.servico)
                agg_rows = (await db.execute(agg_stmt)).all()

                for servico, processados, erros, ultima in agg_rows:
                    resultado[servico] = {
                        "processados": int(processados or 0),
                        "erros": int(erros or 0),
                        "ultima_sincronizacao": ultima,
                        "status": "desconhecido",
                        "taxa_sucesso": 0.0,
                    }

                # Status derivado do ULTIMO log de cada serviço
                for servico in list(resultado.keys()):
                    last_stmt = (
                        select(SyncLog.status)
                        .where(SyncLog.servico == servico)
                        .order_by(SyncLog.inicio_execucao.desc())
                        .limit(1)
                    )
                    last_status = (await db.execute(last_stmt)).scalar_one_or_none()
                    status_map = {
                        "sucesso": ("online", 100.0),
                        "parcial": ("degraded", 50.0),
                        "erro": ("offline", 0.0),
                        "pendente": ("desconhecido", 0.0),
                        "executando": ("desconhecido", 0.0),
                    }
                    val = getattr(last_status, "value", last_status)
                    st, taxa = status_map.get(str(val), ("desconhecido", 0.0))
                    resultado[servico]["status"] = st
                    resultado[servico]["taxa_sucesso"] = taxa
        except Exception as e:
            logger.warning(f"Falha ao agregar gov_sync_logs (status marcado como desconhecido): {e}")
            return {}

        return resultado

    async def _obter_endpoints_indisponiveis(self) -> list[StatusEndpoint]:
        """Lista endpoints atualmente indisponíveis."""
        indisponiveis = []

        # Verificar apenas AM (UF da empresa) para evitar timeout em múltiplas UFs
        ufs_verificar = ["AM"]

        for uf in ufs_verificar:
            try:
                resultado = await self.verificador.verificar_endpoint(uf, "nfe")

                if not resultado.disponivel:
                    indisponiveis.append(
                        StatusEndpoint(
                            uf=uf,
                            servico="nfe",
                            endpoint=resultado.endpoint or "N/A",
                            disponivel=False,
                            tempo_resposta_ms=resultado.tempo_resposta_ms,
                            ultimo_check=datetime.utcnow(),
                            falhas_consecutivas=getattr(resultado, "falhas_consecutivas", 0) or 0,
                        )
                    )
            except Exception as e:
                logger.warning(f"Erro verificando endpoint {uf}/nfe: {e}")
                indisponiveis.append(
                    StatusEndpoint(
                        uf=uf,
                        servico="nfe",
                        endpoint="N/A",
                        disponivel=False,
                        tempo_resposta_ms=None,
                        ultimo_check=datetime.utcnow(),
                        falhas_consecutivas=0,
                    )
                )

        return indisponiveis

    async def _obter_alertas_certificados(self, tenant_id: UUID | None) -> list[AlertaCertificado]:
        """Lista certificados próximos da expiração."""
        alertas = []

        try:
            vault = get_vault_client()
            cert_manager = GerenciadorCertificados(vault)

            # Em produção, buscar tenants do banco
            if tenant_id:
                certificados = await cert_manager.listar_certificados(tenant_id)

                for cert in certificados:
                    if cert.alerta_expiracao:
                        alertas.append(
                            AlertaCertificado(
                                tenant_id=str(tenant_id),
                                tipo_certificado=cert.tipo.value,
                                dias_restantes=cert.dias_restantes,
                                validade_fim=cert.validade_fim,
                                severidade="critical" if cert.dias_restantes <= 7 else "warning",
                            )
                        )
        except Exception as e:
            logger.error(f"Erro ao verificar certificados: {e}")

        return alertas

    async def _obter_eventos_recentes(self, tenant_id: UUID | None, limite: int = 20) -> list[EventoRecente]:
        """Lista eventos recentes do sistema."""
        eventos = []

        # Em produção, buscar do banco de eventos
        # SELECT * FROM eventos ORDER BY timestamp DESC LIMIT ...

        return eventos

    async def obter_metricas(self, tenant_id: UUID | None, periodo_dias: int = 30) -> MetricasResponse:
        """Obtém métricas detalhadas para gráficos."""
        periodo_fim = datetime.utcnow()
        periodo_inicio = periodo_fim - timedelta(days=periodo_dias)

        # Em produção, agregar dados do banco por dia/serviço
        documentos_por_dia = {}
        documentos_por_servico = dict.fromkeys(self.SERVICOS.keys(), 0)
        erros_por_servico = dict.fromkeys(self.SERVICOS.keys(), 0)
        tempo_medio_por_servico = dict.fromkeys(self.SERVICOS.keys(), 0.0)

        return MetricasResponse(
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            documentos_por_dia=documentos_por_dia,
            documentos_por_servico=documentos_por_servico,
            erros_por_servico=erros_por_servico,
            tempo_medio_por_servico=tempo_medio_por_servico,
        )

    # ============================================================================
    # Endpoints
    # ============================================================================

    async def obter_status_integracoes(self) -> IntegrationStatusResponse:
        """
        Obtém status de todas as integrações.

        Só afirma "online" com base em checagem real: SEFAZ NF-e via
        VerificadorDisponibilidade; demais serviços gov via SyncLog real
        (gov_sync_logs). Integrações sem verificação/log são marcadas
        "nao_configurado" — NUNCA "online" sem base.
        """
        integrations = []
        now = datetime.utcnow()

        # Status derivado dos SyncLog reais (por serviço)
        stats = await self._agregar_sync_logs()

        for intg in self.ALL_INTEGRATIONS:
            # Sem base de verificação = nao_configurado (não afirmar online)
            status = "nao_configurado"
            response_time = None
            error_msg = None
            last_check = now
            last_sync = None

            try:
                if intg["id"] == "sefaz_nfe":
                    resultado = await self.verificador.verificar_endpoint("AM", "nfe")
                    status = "online" if resultado.disponivel else "degraded"
                    if not resultado.disponivel:
                        error_msg = resultado.erro
                    response_time = resultado.tempo_resposta_ms
                elif intg["id"] in self.SERVICOS:
                    info = stats.get(intg["id"])
                    if info is not None:
                        status = info["status"]
                        last_sync = info["ultima_sincronizacao"]
                    # sem SyncLog -> permanece "nao_configurado"
            except Exception as e:
                status = "degraded"
                error_msg = str(e)

            integrations.append(
                IntegrationStatusItem(
                    id=intg["id"],
                    name=intg["name"],
                    category=intg["category"],
                    status=status,
                    description=intg["description"],
                    last_check=last_check,
                    last_sync=last_sync,
                    response_time_ms=response_time,
                    error_message=error_msg,
                )
            )

        online = sum(1 for i in integrations if i.status == "online")
        offline = sum(1 for i in integrations if i.status == "offline")
        degraded = sum(1 for i in integrations if i.status == "degraded")

        return IntegrationStatusResponse(
            total=len(integrations),
            online=online,
            offline=offline,
            degraded=degraded,
            integrations=integrations,
            checked_at=now,
        )


dashboard_service = DashboardService()


@router.get("/status", response_model=IntegrationStatusResponse)
async def obter_status_integracoes(current_user: CurrentActiveUser):
    """
    Status de TODAS as integrações externas do sistema.

    Retorna status (online/offline/degraded), tempo de resposta e erros
    para cada integração: Banking (Inter), Government (SEFAZ, Gov.br, etc.), HR (Sólides).
    """
    try:
        return await dashboard_service.obter_status_integracoes()
    except Exception as e:
        logger.error(f"Erro ao obter status das integrações: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao verificar integrações")


@router.get("/", response_model=DashboardResponse)
async def obter_dashboard(
    current_user: CurrentActiveUser,
    tenant_id: str | None = Query(None, description="ID do tenant"),
    dias: int = Query(7, ge=1, le=90, description="Período em dias"),
):
    """
    Obtém visão geral do dashboard de monitoramento.

    Inclui:
    - Resumo de extrações do período
    - Status de cada serviço governamental
    - Endpoints indisponíveis
    - Alertas de certificados
    - Eventos recentes
    """
    try:
        tid = UUID(tenant_id) if tenant_id else None
        return await dashboard_service.obter_dashboard(tid, dias)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"ID de tenant inválido: {e}")
    except Exception as e:
        logger.error(f"Erro ao obter dashboard: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao carregar dashboard")


@router.get("/metricas", response_model=MetricasResponse)
async def obter_metricas(
    current_user: CurrentActiveUser,
    tenant_id: str | None = Query(None, description="ID do tenant"),
    dias: int = Query(30, ge=1, le=365, description="Período em dias"),
):
    """
    Obtém métricas detalhadas para gráficos.

    Retorna dados agregados por dia e por serviço.
    """
    try:
        tid = UUID(tenant_id) if tenant_id else None
        return await dashboard_service.obter_metricas(tid, dias)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"ID de tenant inválido: {e}")
    except Exception as e:
        logger.error(f"Erro ao obter métricas: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao carregar métricas")


@router.get("/endpoints", response_model=list[StatusEndpoint])
async def listar_status_endpoints(current_user: CurrentActiveUser):
    """
    Lista status de todos os endpoints governamentais.

    Mostra disponibilidade atual de cada endpoint por UF.
    """
    try:
        return await dashboard_service._obter_endpoints_indisponiveis()
    except Exception as e:
        logger.error(f"Erro ao listar endpoints: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao verificar endpoints")


@router.get("/certificados/alertas", response_model=list[AlertaCertificado])
async def listar_alertas_certificados(
    current_user: CurrentActiveUser,
    tenant_id: str | None = Query(None, description="ID do tenant"),
):
    """
    Lista alertas de certificados próximos da expiração.
    """
    try:
        tid = UUID(tenant_id) if tenant_id else None
        return await dashboard_service._obter_alertas_certificados(tid)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"ID de tenant inválido: {e}")
    except Exception as e:
        logger.error(f"Erro ao verificar certificados: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao verificar certificados")


@router.get("/eventos", response_model=list[EventoRecente])
async def listar_eventos_recentes(
    current_user: CurrentActiveUser,
    tenant_id: str | None = Query(None, description="ID do tenant"),
    limite: int = Query(50, ge=1, le=200, description="Limite de eventos"),
):
    """
    Lista eventos recentes do sistema.

    Inclui alertas, erros e notificações.
    """
    try:
        tid = UUID(tenant_id) if tenant_id else None
        return await dashboard_service._obter_eventos_recentes(tid, limite)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"ID de tenant inválido: {e}")
    except Exception as e:
        logger.error(f"Erro ao listar eventos: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao carregar eventos")


@router.post("/endpoints/{uf}/{servico}/verificar", status_code=201)
async def verificar_endpoint(uf: str, current_user: CurrentActiveUser, servico: str):
    """
    Força verificação de disponibilidade de um endpoint específico.
    """
    try:
        verificador = VerificadorDisponibilidade()
        resultado = await verificador.verificar_endpoint(uf.upper(), servico)

        return {
            "uf": uf.upper(),
            "servico": servico,
            "disponivel": resultado.disponivel,
            "tempo_resposta_ms": resultado.tempo_resposta_ms,
            "erro": resultado.erro,
            "verificado_em": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Erro ao verificar endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao verificar endpoint: {e}"
        )
