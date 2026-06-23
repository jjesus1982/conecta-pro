"""
Tasks de Sincronização com Serviços Governamentais.

Implementa tarefas Celery para extração automática.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from uuid import UUID

from celery import shared_task

from core.database import engine

from ..extractors.orchestrator import (
    ConfiguracaoExtracao,
    TipoServico,
    get_orchestrator,
)

logger = logging.getLogger(__name__)


def run_async(coro):
    """Helper para executar coroutines em tasks Celery."""
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
    bind=True,
    name="government_integrations.tasks.sync.sincronizar_nfe",
    queue="gov.sefaz.nfe",
    max_retries=3,
    default_retry_delay=300,
)
def sincronizar_nfe(
    self,
    tenant_id: str,
    cnpjs: list[str] | None = None,
    ufs: list[str] | None = None,
    dias: int = 30,
):
    """
    Sincroniza NF-e da SEFAZ.

    Args:
        tenant_id: ID do tenant
        cnpjs: CNPJs a consultar
        ufs: UFs para consulta
        dias: Dias para trás a consultar
    """
    logger.info(f"Iniciando sincronização NF-e: {tenant_id}")

    try:
        config = ConfiguracaoExtracao(
            servicos=[TipoServico.SEFAZ_NFE],
            data_inicio=datetime.utcnow() - timedelta(days=dias),
            data_fim=datetime.utcnow(),
            cnpjs=cnpjs,
            ufs=ufs,
            modo_incremental=True,
        )

        resultado = run_async(get_orchestrator().iniciar_extracao(UUID(tenant_id), config))

        return resultado.to_dict()

    except Exception as e:
        logger.error(f"Erro na sincronização NF-e: {e}")
        raise self.retry(exc=e)


@shared_task(
    bind=True,
    name="government_integrations.tasks.sync.sincronizar_esocial",
    queue="gov.esocial",
    max_retries=3,
    default_retry_delay=300,
)
def sincronizar_esocial(
    self,
    tenant_id: str,
    cnpjs: list[str] | None = None,
    competencia: str | None = None,
):
    """
    Sincroniza eventos do eSocial.

    Args:
        tenant_id: ID do tenant
        cnpjs: CNPJs a consultar
        competencia: Competência específica (AAAA-MM)
    """
    logger.info(f"Iniciando sincronização eSocial: {tenant_id}")

    try:
        if competencia:
            ano, mes = competencia.split("-")
            data_inicio = datetime(int(ano), int(mes), 1)
            data_fim = datetime(int(ano), int(mes) + 1, 1) - timedelta(days=1)
        else:
            data_fim = datetime.utcnow()
            data_inicio = data_fim - timedelta(days=30)

        config = ConfiguracaoExtracao(
            servicos=[TipoServico.ESOCIAL],
            data_inicio=data_inicio,
            data_fim=data_fim,
            cnpjs=cnpjs,
            modo_incremental=True,
        )

        resultado = run_async(get_orchestrator().iniciar_extracao(UUID(tenant_id), config))

        return resultado.to_dict()

    except Exception as e:
        logger.error(f"Erro na sincronização eSocial: {e}")
        raise self.retry(exc=e)


@shared_task(
    bind=True,
    name="government_integrations.tasks.sync.sincronizar_fgts",
    queue="gov.fgts",
    max_retries=3,
    default_retry_delay=300,
)
def sincronizar_fgts(
    self,
    tenant_id: str,
    cnpjs: list[str] | None = None,
    competencias: list[str] | None = None,
):
    """
    Sincroniza guias do FGTS Digital.

    Args:
        tenant_id: ID do tenant
        cnpjs: CNPJs a consultar
        competencias: Lista de competências (AAAAMM)
    """
    logger.info(f"Iniciando sincronização FGTS: {tenant_id}")

    try:
        if competencias:
            # Usar período das competências informadas
            datas = [datetime.strptime(c, "%Y%m") for c in competencias]
            data_inicio = min(datas)
            data_fim = max(datas) + timedelta(days=31)
        else:
            data_fim = datetime.utcnow()
            data_inicio = data_fim - timedelta(days=90)

        config = ConfiguracaoExtracao(
            servicos=[TipoServico.FGTS_DIGITAL],
            data_inicio=data_inicio,
            data_fim=data_fim,
            cnpjs=cnpjs,
            modo_incremental=True,
        )

        resultado = run_async(get_orchestrator().iniciar_extracao(UUID(tenant_id), config))

        return resultado.to_dict()

    except Exception as e:
        logger.error(f"Erro na sincronização FGTS: {e}")
        raise self.retry(exc=e)


@shared_task(
    bind=True,
    name="government_integrations.tasks.sync.sincronizar_nfse",
    queue="gov.nfse",
    max_retries=3,
    default_retry_delay=300,
)
def sincronizar_nfse(
    self,
    tenant_id: str,
    cnpjs: list[str] | None = None,
    dias: int = 30,
):
    """
    Sincroniza NFS-e de Manaus.

    Args:
        tenant_id: ID do tenant
        cnpjs: CNPJs a consultar
        dias: Dias para trás a consultar
    """
    logger.info(f"Iniciando sincronização NFS-e: {tenant_id}")

    try:
        config = ConfiguracaoExtracao(
            servicos=[TipoServico.NFSE_MANAUS],
            data_inicio=datetime.utcnow() - timedelta(days=dias),
            data_fim=datetime.utcnow(),
            cnpjs=cnpjs,
            modo_incremental=True,
        )

        resultado = run_async(get_orchestrator().iniciar_extracao(UUID(tenant_id), config))

        return resultado.to_dict()

    except Exception as e:
        logger.error(f"Erro na sincronização NFS-e: {e}")
        raise self.retry(exc=e)


@shared_task(
    bind=True,
    name="government_integrations.tasks.sync.sincronizar_nfse_entrada",
    queue="gov.nfse",
    max_retries=3,
    default_retry_delay=300,
)
def sincronizar_nfse_entrada(
    self,
    data_inicio: str | None = None,
    data_fim: str | None = None,
):
    """
    Sincroniza NFS-e RECEBIDAS (onde nosso CNPJ é tomador) via Portal Nacional.
    Agendado automaticamente pelo Celery beat (diariamente às 06:30).
    """
    logger.info("Iniciando sincronização NFS-e entrada (Portal Nacional)")
    try:
        from modules.government_integrations.services.nfse_entrada_sync_service import (
            NFSeEntradaSyncService,
        )

        svc = NFSeEntradaSyncService()
        resultado = svc.buscar_nfse_recebidas(data_inicio, data_fim)
        logger.info("NFS-e entrada sync concluído: %s", resultado)
        return resultado
    except Exception as exc:
        logger.error("Erro na sincronização NFS-e entrada: %s", exc)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name="government_integrations.tasks.sync.sincronizar_nfe_entrada",
    queue="gov.sefaz.nfe",
    max_retries=3,
    default_retry_delay=300,
)
def sincronizar_nfe_entrada(
    self,
    ultimo_nsu: str = "0",
):
    """
    Sincroniza NF-e RECEBIDAS (onde nosso CNPJ é destinatário) via SEFAZ DistribuicaoDFe.
    Agendado automaticamente pelo Celery beat (a cada 2 horas).
    """
    logger.info("Iniciando sincronização NF-e entrada (SEFAZ DistribuicaoDFe)")
    try:
        from modules.government_integrations.services.nfe_entrada_sync_service import (
            NFEEntradaSyncService,
        )

        svc = NFEEntradaSyncService()
        resultado = svc.buscar_nfe_recebidas(ultimo_nsu=ultimo_nsu)
        logger.info("NF-e entrada sync concluído: %s", resultado)
        return resultado
    except Exception as exc:
        logger.error("Erro na sincronização NF-e entrada: %s", exc)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name="government_integrations.tasks.sync.sincronizar_rfb",
    queue="gov.batch",
    max_retries=3,
    default_retry_delay=600,
)
def sincronizar_rfb(
    self,
    tenant_id: str,
    cnpjs: list[str],
):
    """
    Sincroniza dados da Receita Federal.

    Args:
        tenant_id: ID do tenant
        cnpjs: CNPJs a consultar
    """
    logger.info(f"Iniciando sincronização RFB: {tenant_id}")

    try:
        config = ConfiguracaoExtracao(
            servicos=[TipoServico.RECEITA_FEDERAL],
            cnpjs=cnpjs,
            modo_incremental=False,  # Sempre consulta completa
        )

        resultado = run_async(get_orchestrator().iniciar_extracao(UUID(tenant_id), config))

        return resultado.to_dict()

    except Exception as e:
        logger.error(f"Erro na sincronização RFB: {e}")
        raise self.retry(exc=e)


@shared_task(
    bind=True,
    name="government_integrations.tasks.sync.sincronizar_todos",
    queue="gov.batch",
    max_retries=2,
    soft_time_limit=1800,
    time_limit=3600,
)
def sincronizar_todos(
    self,
    tenant_id: str,
    cnpjs: list[str] | None = None,
    servicos: list[str] | None = None,
):
    """
    Sincroniza todos os serviços governamentais.

    Args:
        tenant_id: ID do tenant
        cnpjs: CNPJs a consultar
        servicos: Lista de serviços (opcional, default = todos)
    """
    logger.info(f"Iniciando sincronização completa: {tenant_id}")

    try:
        # Mapear serviços
        if servicos:
            tipos_servico = [TipoServico(s) for s in servicos if s in [t.value for t in TipoServico]]
        else:
            tipos_servico = [
                TipoServico.SEFAZ_NFE,
                TipoServico.ESOCIAL,
                TipoServico.FGTS_DIGITAL,
                TipoServico.NFSE_MANAUS,
            ]

        config = ConfiguracaoExtracao(
            servicos=tipos_servico,
            data_inicio=datetime.utcnow() - timedelta(days=30),
            data_fim=datetime.utcnow(),
            cnpjs=cnpjs,
            modo_incremental=True,
            processar_em_paralelo=True,
            max_workers=3,
        )

        resultado = run_async(get_orchestrator().iniciar_extracao(UUID(tenant_id), config))

        return resultado.to_dict()

    except Exception as e:
        logger.error(f"Erro na sincronização completa: {e}")
        raise self.retry(exc=e)


# Tasks de batch para múltiplos tenants


@shared_task(
    name="government_integrations.tasks.batch.sincronizar_todos_tenants",
    queue="gov.batch",
)
def sincronizar_todos_tenants(servico: str = "sefaz_nfe"):
    """
    Enfileira sincronização para todos os tenants ativos.

    Usado pelo scheduler para sincronização periódica.
    """
    logger.info(f"Enfileirando sincronização {servico} para todos os tenants")

    # Em produção, buscar lista de tenants do banco
    # Por ora, exemplo com tenant fixo
    tenants = [
        # Buscar do banco: SELECT id FROM tenants WHERE ativo = TRUE
    ]

    tasks_map = {
        "sefaz_nfe": sincronizar_nfe,
        "esocial": sincronizar_esocial,
        "fgts": sincronizar_fgts,
        "nfse": sincronizar_nfse,
    }

    task_func = tasks_map.get(servico, sincronizar_nfe)

    for tenant_id in tenants:
        task_func.delay(str(tenant_id))

    return {"enfileirados": len(tenants), "servico": servico}
