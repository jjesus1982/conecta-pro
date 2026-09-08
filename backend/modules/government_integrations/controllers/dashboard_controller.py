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
        "nfse_manaus": "NFS-e Manaus (histórico até 12/2025 — emissão migrou para o ADN)",
        "nfse_nacional": "NFS-e Nacional (ADN)",
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

    # Evidência REAL por serviço: (tabela/consulta do último sinal, consulta de volume em 30 dias).
    # `gov_sync_logs` (SyncLog) NUNCA existiu no banco — modelo sem migration (checar_tabela_fantasma,
    # t6, 07/09/2026) — e este painel devolvia "nao_configurado" para tudo, todo dia, em WARNING.
    # O que prova que uma integração está viva é a linha que ela grava: checkpoint de NSU,
    # nota sincronizada, evento do eSocial, guia do FGTS, certidão atualizada, extrato do banco.
    # (último sinal, volume 30d, dias para "online", dias para "degraded"). Cadência importa:
    # extrato e NFS-e chegam todo dia; guia de FGTS, DAS, certidão e evento do eSocial são
    # mensais — 20 dias sem guia nova é o normal, não "offline".
    CADENCIA: dict[str, tuple[int, int]] = {
        "fgts_digital": (40, 60), "simples_nacional": (40, 60), "receita_federal": (40, 60),
        "esocial": (40, 60), "sefaz_nfe": (8, 30),
    }
    EVIDENCIA: dict[str, tuple[str, str]] = {
        "nfse_nacional": ("SELECT max(updated_at) FROM fiscal_nsu_checkpoint WHERE tipo = 'nfse_adn'",
                          "SELECT count(*) FROM nfse_emitidas_nacional WHERE created_at >= now() - interval '30 days'"),
        "sefaz_nfe": ("SELECT max(updated_at) FROM nfe_dist_nsu",
                      "SELECT count(*) FROM nfe_entradas WHERE created_at >= now() - interval '30 days'"),
        "esocial": ("SELECT max(updated_at) FROM esocial_eventos_espelho",
                    "SELECT count(*) FROM esocial_eventos_espelho WHERE updated_at >= now() - interval '30 days'"),
        "fgts_digital": ("SELECT max(created_at) FROM fgts_guias",
                         "SELECT count(*) FROM fgts_guias WHERE created_at >= now() - interval '30 days'"),
        "receita_federal": ("SELECT max(updated_at) FROM ged_certidoes WHERE document_type IN ('certidao_negativa_federal','certidao_negativa_inss')",
                            "SELECT count(*) FROM ged_certidoes WHERE updated_at >= now() - interval '30 days'"),
        "simples_nacional": ("SELECT max(updated_at) FROM fiscal_obligations WHERE tipo = 'DAS'",
                             "SELECT count(*) FROM fiscal_obligations WHERE tipo = 'DAS' AND updated_at >= now() - interval '30 days'"),
        "inter": ("SELECT max(bt.created_at) FROM bank_transactions bt JOIN bank_accounts ba ON ba.id = bt.bank_account_id WHERE ba.bank_code = '077'",
                  "SELECT count(*) FROM bank_transactions bt JOIN bank_accounts ba ON ba.id = bt.bank_account_id WHERE ba.bank_code = '077' AND bt.created_at >= now() - interval '30 days'"),
        "solides": ("SELECT max(created_at) FROM gp_clock_punches WHERE device_type = 'tangerino'",
                    "SELECT count(*) FROM gp_clock_punches WHERE device_type = 'tangerino' AND created_at >= now() - interval '30 days'"),
    }

    async def _agregar_sync_logs(self) -> dict[str, dict[str, Any]]:
        """Status por serviço a partir da EVIDÊNCIA real (tabela que a integração grava).

        online = último sinal há < 2 dias · degraded = < 8 dias · offline = mais velho.
        Serviço sem fonte de evidência (CT-e, MDF-e, gov.br, SPED, eCAC…) fica fora do
        dict e o chamador o marca "nao_configurado" — nunca "online" sem base.
        """
        resultado: dict[str, dict[str, Any]] = {}
        try:
            from sqlalchemy import text

            from core.database.session import async_session_factory

            async with async_session_factory() as db:
                for servico, (sql_ultimo, sql_volume) in self.EVIDENCIA.items():
                    try:
                        ultimo = (await db.execute(text(sql_ultimo))).scalar()
                        volume = int((await db.execute(text(sql_volume))).scalar() or 0)
                    except Exception as exc:  # noqa: BLE001 — uma fonte quebrada não cala as outras
                        await db.rollback()
                        logger.warning("evidência de %s indisponível: %s", servico, exc)
                        continue
                    if ultimo is None:
                        continue
                    if getattr(ultimo, "tzinfo", None) is not None:
                        ultimo = ultimo.replace(tzinfo=None)
                    idade = datetime.utcnow() - ultimo
                    on, deg = self.CADENCIA.get(servico, (2, 8))
                    if idade.days < on:
                        st, taxa = "online", 100.0
                    elif idade.days < deg:
                        st, taxa = "degraded", 50.0
                    else:
                        st, taxa = "offline", 0.0
                    resultado[servico] = {
                        "processados": volume, "erros": 0, "ultima_sincronizacao": ultimo,
                        "status": st, "taxa_sucesso": taxa,
                    }
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Falha ao agregar evidência das integrações (status marcado como desconhecido): {e}")
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
                elif intg["id"] in self.EVIDENCIA:
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


