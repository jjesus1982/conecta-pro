"""
Tasks de Monitoramento e Manutenção.

Verifica disponibilidade de endpoints, certificados e reprocessa falhas.
"""

import asyncio
import logging
from datetime import datetime

from celery import shared_task

from core.database import engine

from ..core.contingency import (
    MATRIZ_CONTINGENCIA_NFE,
    ComutadorEndpoints,
    VerificadorDisponibilidade,
)
from ..core.credentials import (
    GerenciadorCertificados,
    get_vault_client,
)
from ..core.events import (
    EventoSistema,
    TipoEvento,
    get_event_bus,
)

logger = logging.getLogger(__name__)


def run_async(coro):
    """Helper para executar coroutines."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        # Dispõe o pool async NO MESMO loop antes de fechá-lo — senão as conexões
        # asyncpg ficam órfãs e acumulam como idle no Postgres (leak do celery-batch).
        try:
            loop.run_until_complete(engine.dispose())
        finally:
            loop.close()


@shared_task(
    name="government_integrations.tasks.monitoring.verificar_disponibilidade",
    queue="gov.batch",
)
def verificar_disponibilidade():
    """
    Verifica disponibilidade de todos os endpoints governamentais.

    Executa a cada 5 minutos para detectar indisponibilidades.
    """
    logger.info("Iniciando verificação de disponibilidade")

    async def _verificar():
        verificador = VerificadorDisponibilidade()
        comutador = ComutadorEndpoints()
        event_bus = get_event_bus()

        resultados = []
        alertas = []

        # Verificar endpoints NF-e
        for uf in MATRIZ_CONTINGENCIA_NFE.keys():
            resultado = await verificador.verificar_endpoint(uf, "nfe")
            resultados.append(resultado)

            if resultado.disponivel:
                await comutador.registrar_sucesso(uf, "nfe", resultado.tempo_resposta_ms)
            else:
                await comutador.registrar_falha(uf, "nfe", resultado.erro or "Indisponível")
                alertas.append(
                    {
                        "uf": uf,
                        "servico": "nfe",
                        "erro": resultado.erro,
                    }
                )

            # Pequeno delay entre verificações
            await asyncio.sleep(0.5)

        # Gerar relatório
        relatorio = verificador.gerar_relatorio(resultados)

        # Publicar eventos de alerta
        for alerta in alertas:
            await event_bus.publicar(
                EventoSistema(
                    tipo_evento=TipoEvento.ENDPOINT_INDISPONIVEL,
                    servico=alerta["servico"],
                    uf=alerta["uf"],
                    descricao=f"Endpoint indisponível: {alerta['erro']}",
                    severidade="warning",
                )
            )

        return relatorio

    resultado = run_async(_verificar())

    logger.info(
        f"Verificação concluída: {resultado['resumo']['disponiveis']}/"
        f"{resultado['resumo']['total']} endpoints disponíveis"
    )

    return resultado


@shared_task(
    name="government_integrations.tasks.monitoring.verificar_certificados",
    queue="gov.batch",
)
def verificar_certificados():
    """
    Verifica certificados próximos da expiração.

    Executa a cada 6 horas para alertar sobre certificados expirando.
    """
    logger.info("Iniciando verificação de certificados")

    async def _verificar():
        vault = get_vault_client()
        cert_manager = GerenciadorCertificados(vault)
        event_bus = get_event_bus()

        alertas = []

        # Em produção, buscar lista de tenants
        # Por ora, verificação simplificada
        tenants = []  # SELECT id FROM tenants WHERE ativo = TRUE

        for tenant_id in tenants:
            certificados = await cert_manager.listar_certificados(tenant_id)

            for cert in certificados:
                if cert.alerta_expiracao:
                    alertas.append(
                        {
                            "tenant_id": str(tenant_id),
                            "tipo": cert.tipo.value,
                            "dias_restantes": cert.dias_restantes,
                            "validade_fim": cert.validade_fim.isoformat(),
                        }
                    )

                    # Publicar evento
                    await event_bus.publicar(
                        EventoSistema(
                            tipo_evento=TipoEvento.CERTIFICADO_EXPIRANDO,
                            tenant_id=tenant_id,
                            servico=cert.tipo.value,
                            descricao=f"Certificado expira em {cert.dias_restantes} dias",
                            detalhes={
                                "validade_fim": cert.validade_fim.isoformat(),
                                "dias_restantes": cert.dias_restantes,
                            },
                            severidade="warning" if cert.dias_restantes > 7 else "critical",
                        )
                    )

        return {
            "verificados": len(tenants),
            "alertas": alertas,
            "timestamp": datetime.utcnow().isoformat(),
        }

    resultado = run_async(_verificar())

    if resultado["alertas"]:
        logger.warning(f"Certificados expirando: {len(resultado['alertas'])}")

    return resultado


@shared_task(
    name="government_integrations.tasks.reprocess.reprocessar_falhas",
    queue="gov.batch",
)
def reprocessar_falhas(_max_items: int = 100):
    """
    Reprocessa documentos que falharam anteriormente.

    Executa a cada 15 minutos para tentar novamente itens da fila.
    """
    logger.info("Iniciando reprocessamento de falhas")

    async def _reprocessar():
        # Em produção, usar sessão do banco real
        # fila = FilaReprocessamento(db_session)

        processados = 0
        sucesso = 0
        falhas = 0

        # Buscar itens pendentes
        # pendentes = await fila.obter_pendentes(limite=max_items)

        # for item in pendentes:
        #     try:
        #         # Reprocessar conforme tipo
        #         resultado = await _processar_item(item)
        #         if resultado:
        #             await fila.marcar_sucesso(item.id)
        #             sucesso += 1
        #         else:
        #             await fila.marcar_falha(item.id, "Falha no reprocessamento")
        #             falhas += 1
        #     except Exception as e:
        #         await fila.marcar_falha(item.id, str(e))
        #         falhas += 1
        #
        #     processados += 1

        return {
            "processados": processados,
            "sucesso": sucesso,
            "falhas": falhas,
            "timestamp": datetime.utcnow().isoformat(),
        }

    resultado = run_async(_reprocessar())

    logger.info(f"Reprocessamento concluído: {resultado['sucesso']} sucesso, {resultado['falhas']} falhas")

    return resultado


@shared_task(
    name="government_integrations.tasks.maintenance.limpar_cache",
    queue="gov.batch",
)
def limpar_cache():
    """
    Limpa caches e dados temporários antigos.

    Executa diariamente para manutenção.
    """
    logger.info("Iniciando limpeza de cache")

    async def _limpar():
        vault = get_vault_client()
        vault.limpar_cache()

        # Outras limpezas...

        return {
            "vault_cache": "limpo",
            "timestamp": datetime.utcnow().isoformat(),
        }

    resultado = run_async(_limpar())
    return resultado


@shared_task(
    name="government_integrations.tasks.maintenance.limpar_historico",
    queue="gov.batch",
)
def limpar_historico(dias_retencao: int = 365):
    """
    Remove registros antigos do histórico.

    Mantém conformidade com políticas de retenção.
    """
    logger.info(f"Iniciando limpeza de histórico (retenção: {dias_retencao} dias)")

    async def _limpar():
        # Em produção, usar sessão do banco
        # removidos = await db.execute(...)

        return {
            "dias_retencao": dias_retencao,
            "registros_removidos": 0,
            "timestamp": datetime.utcnow().isoformat(),
        }

    resultado = run_async(_limpar())
    return resultado


@shared_task(
    name="government_integrations.tasks.monitoring.gerar_relatorio_diario",
    queue="gov.batch",
)
def gerar_relatorio_diario():
    """
    Gera relatório diário de operações.
    """
    logger.info("Gerando relatório diário")

    async def _gerar():
        # Coletar estatísticas do dia
        hoje = datetime.utcnow().date()

        relatorio = {
            "data": str(hoje),
            "documentos_processados": {
                "nfe": 0,
                "cte": 0,
                "nfse": 0,
                "esocial": 0,
                "fgts": 0,
            },
            "erros": [],
            "endpoints_indisponiveis": [],
            "certificados_expirando": [],
        }

        # Em produção, buscar dados reais do banco

        return relatorio

    resultado = run_async(_gerar())

    logger.info(f"Relatório diário gerado para {resultado['data']}")
    return resultado
