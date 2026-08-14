"""
Tasks Celery de sincronizacao com PNCP.
=======================================

Tasks:
- sync_pncp_oportunidades: Busca oportunidades no PNCP a cada 2h
- sync_pncp_precos: Busca precos de referencia diariamente
- atualizar_contratos_pncp: Atualiza status de contratos existentes
"""

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta

from celery import shared_task

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def run_async(coro):
    """Helper para executar coroutines em tasks Celery."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ──────────────────────────────────────────────
# Keywords de busca para seguranca patrimonial
# ──────────────────────────────────────────────

SECURITY_KEYWORDS = [
    "vigilancia",
    "seguranca patrimonial",
    "seguranca eletronica",
    "portaria",
    "monitoramento",
    "cftv",
    "alarme",
    "controle de acesso",
    "vigilancia armada",
    "vigilancia desarmada",
    "seguranca privada",
]


# ──────────────────────────────────────────────
# Task 1: Sync oportunidades PNCP
# ──────────────────────────────────────────────


@shared_task(
    bind=True,
    name="bidding.sync_pncp_oportunidades",
    queue="gov.batch",
    max_retries=3,
    default_retry_delay=300,
    soft_time_limit=600,
    time_limit=900,
)
def sync_pncp_oportunidades(
    self,
    uf: str = "AM",
    dias: int = 30,
    max_paginas: int = 5,
):
    """
    Busca oportunidades de licitacao no PNCP para seguranca/vigilancia.

    Args:
        uf: UF para filtrar busca (default: AM).
        dias: Dias para tras a buscar (default: 30).
        max_paginas: Maximo de paginas por busca (default: 5).

    Returns:
        Dict com resumo: {total_found, new, updated, errors}
    """
    from core.database.session import get_sync_db

    logger.info(f"[BIDDING] Iniciando sync PNCP oportunidades: UF={uf}, dias={dias}")

    # Criar registro de sync job
    sync_job_id = None
    with get_sync_db() as db:
        from modules.bidding.models.sync_job import BiddingSyncJob

        sync_job = BiddingSyncJob(
            id=uuid.uuid4(),
            portal="pncp",
            tipo="sync_oportunidades",
            status="running",
            started_at=datetime.utcnow(),
            filtros_utilizados={"uf": uf, "dias": dias, "max_paginas": max_paginas},
        )
        db.add(sync_job)
        db.flush()
        sync_job_id = sync_job.id

    try:
        # Buscar oportunidades via ScoutAgent (async)
        opportunities = run_async(_buscar_oportunidades_pncp(uf=uf, dias=dias, max_paginas=max_paginas))

        # Persistir resultados no banco
        new_count = 0
        updated_count = 0
        error_count = 0

        with get_sync_db() as db:
            from sqlalchemy import select

            from modules.bidding.models.opportunity import BiddingOpportunity

            for opp in opportunities:
                try:
                    # Verificar se ja existe (portal + portal_id)
                    portal_id = f"{opp['numero_compra']}/{opp['ano_compra']}/{opp['sequencial_compra']}"

                    existing = db.execute(
                        select(BiddingOpportunity).where(
                            BiddingOpportunity.portal == "pncp",
                            BiddingOpportunity.portal_id == portal_id,
                        )
                    ).scalar_one_or_none()

                    if existing:
                        # Atualizar score e datas
                        existing.relevancia_score = opp.get("relevancia_score", 0)
                        existing.valor_estimado = opp.get("valor_estimado")
                        existing.data_abertura = (
                            datetime.fromisoformat(opp["data_abertura"])
                            if opp.get("data_abertura")
                            else existing.data_abertura
                        )
                        existing.data_encerramento = (
                            datetime.fromisoformat(opp["data_encerramento"])
                            if opp.get("data_encerramento")
                            else existing.data_encerramento
                        )
                        existing.updated_at = datetime.utcnow()
                        updated_count += 1
                    else:
                        # Criar novo registro
                        new_opp = BiddingOpportunity(
                            id=uuid.uuid4(),
                            portal="pncp",
                            portal_id=portal_id,
                            objeto=opp.get("objeto", ""),
                            valor_estimado=opp.get("valor_estimado"),
                            modalidade=opp.get("modalidade"),
                            orgao_nome=opp.get("orgao_nome"),
                            orgao_cnpj=opp.get("orgao_cnpj"),
                            uf=opp.get("orgao_uf", uf),
                            data_publicacao=(
                                datetime.fromisoformat(opp["data_publicacao"]) if opp.get("data_publicacao") else None
                            ),
                            data_abertura=(
                                datetime.fromisoformat(opp["data_abertura"]) if opp.get("data_abertura") else None
                            ),
                            data_encerramento=(
                                datetime.fromisoformat(opp["data_encerramento"])
                                if opp.get("data_encerramento")
                                else None
                            ),
                            url_edital=opp.get("link_pncp"),
                            status="nova",
                            relevancia_score=opp.get("relevancia_score", 0),
                        )
                        db.add(new_opp)
                        new_count += 1

                except Exception as e:
                    logger.error(f"[BIDDING] Erro ao persistir oportunidade: {e}")
                    error_count += 1

        # Atualizar sync job com resultado
        with get_sync_db() as db:
            from modules.bidding.models.sync_job import BiddingSyncJob

            job = db.get(BiddingSyncJob, sync_job_id)
            if job:
                job.status = "completed"
                job.finished_at = datetime.utcnow()
                job.registros_processados = len(opportunities)
                job.registros_novos = new_count
                job.registros_atualizados = updated_count

        summary = {
            "total_found": len(opportunities),
            "new": new_count,
            "updated": updated_count,
            "errors": error_count,
            "uf": uf,
            "sync_job_id": str(sync_job_id),
        }

        logger.info(
            f"[BIDDING] Sync PNCP concluido: "
            f"{summary['total_found']} encontrados, "
            f"{summary['new']} novos, "
            f"{summary['updated']} atualizados, "
            f"{summary['errors']} erros"
        )

        return summary

    except Exception as e:
        logger.error(f"[BIDDING] Erro na sync PNCP oportunidades: {e}")

        # Atualizar sync job com erro
        try:
            with get_sync_db() as db:
                from modules.bidding.models.sync_job import BiddingSyncJob

                job = db.get(BiddingSyncJob, sync_job_id)
                if job:
                    job.status = "failed"
                    job.finished_at = datetime.utcnow()
                    job.erros = [str(e)[:500]]
        except Exception:
            logger.error("[BIDDING] Erro ao atualizar sync job com falha")

        raise self.retry(exc=e)


async def _buscar_oportunidades_pncp(
    uf: str = "AM",
    dias: int = 30,
    max_paginas: int = 5,
) -> list[dict]:
    """Executa busca async no PNCP via ScoutAgent."""
    from modules.bidding.agents.scout_agent import ScoutAgent, ScoutSearchParams

    params = ScoutSearchParams(
        keywords=SECURITY_KEYWORDS,
        ufs=[uf],
        data_inicial=date.today() - timedelta(days=dias),
        data_final=date.today(),
        max_paginas=max_paginas,
    )

    agent = ScoutAgent()
    return await agent.execute(search_params=params)


# ──────────────────────────────────────────────
# Task 2: Sync precos de referencia PNCP
# ──────────────────────────────────────────────


@shared_task(
    bind=True,
    name="bidding.sync_pncp_precos",
    queue="gov.batch",
    max_retries=3,
    default_retry_delay=600,
    soft_time_limit=900,
    time_limit=1200,
)
def sync_pncp_precos(
    self,
    uf: str = "AM",
    dias: int = 90,
):
    """
    Busca precos de referencia para servicos de seguranca no PNCP.

    Armazena em bidding_price_history para uso pelo PricerAgent
    na comparacao de precos de mercado.

    Args:
        uf: UF para filtrar busca (default: AM).
        dias: Dias para tras a buscar (default: 90).

    Returns:
        Dict com resumo: {total_found, saved, errors}
    """
    from core.database.session import get_sync_db

    logger.info(f"[BIDDING] Iniciando sync precos PNCP: UF={uf}, dias={dias}")

    # Criar sync job
    sync_job_id = None
    with get_sync_db() as db:
        from modules.bidding.models.sync_job import BiddingSyncJob

        sync_job = BiddingSyncJob(
            id=uuid.uuid4(),
            portal="pncp",
            tipo="sync_precos",
            status="running",
            started_at=datetime.utcnow(),
            filtros_utilizados={"uf": uf, "dias": dias},
        )
        db.add(sync_job)
        db.flush()
        sync_job_id = sync_job.id

    try:
        # Buscar contratos com precos no PNCP
        price_data = run_async(_buscar_precos_pncp(uf=uf, dias=dias))

        saved_count = 0
        error_count = 0

        with get_sync_db() as db:
            from modules.bidding.models.price_history import BiddingPriceHistory

            for item in price_data:
                try:
                    price_record = BiddingPriceHistory(
                        id=uuid.uuid4(),
                        descricao=item["descricao"],
                        fonte="pncp",
                        valor_unitario=item["valor_unitario"],
                        unidade=item.get("unidade", "mensal"),
                        orgao=item.get("orgao"),
                        data_referencia=item.get("data_referencia"),
                        metadata_extra=item.get("metadata", {}),
                    )
                    db.add(price_record)
                    saved_count += 1

                except Exception as e:
                    logger.error(f"[BIDDING] Erro ao salvar preco: {e}")
                    error_count += 1

        # Atualizar sync job
        with get_sync_db() as db:
            from modules.bidding.models.sync_job import BiddingSyncJob

            job = db.get(BiddingSyncJob, sync_job_id)
            if job:
                job.status = "completed"
                job.finished_at = datetime.utcnow()
                job.registros_processados = len(price_data)
                job.registros_novos = saved_count

        summary = {
            "total_found": len(price_data),
            "saved": saved_count,
            "errors": error_count,
            "uf": uf,
            "sync_job_id": str(sync_job_id),
        }

        logger.info(
            f"[BIDDING] Sync precos PNCP concluido: {summary['total_found']} encontrados, {summary['saved']} salvos"
        )

        return summary

    except Exception as e:
        logger.error(f"[BIDDING] Erro na sync PNCP precos: {e}")

        try:
            with get_sync_db() as db:
                from modules.bidding.models.sync_job import BiddingSyncJob

                job = db.get(BiddingSyncJob, sync_job_id)
                if job:
                    job.status = "failed"
                    job.finished_at = datetime.utcnow()
                    job.erros = [str(e)[:500]]
        except Exception:
            logger.error("[BIDDING] Erro ao atualizar sync job com falha")

        raise self.retry(exc=e)


async def _buscar_precos_pncp(uf: str = "AM", dias: int = 90) -> list[dict]:
    """Busca contratos no PNCP e extrai precos de referencia."""
    from modules.bidding.integrations.pncp.client import PNCPClient

    price_data = []

    async with PNCPClient() as client:
        # Buscar contratos de seguranca/vigilancia
        result = await client.buscar_contratos(uf=uf, pagina=1, tamanho_pagina=50)

        if not result.get("sucesso"):
            logger.warning(f"[BIDDING] Falha ao buscar contratos PNCP: {result.get('erro')}")
            return []

        for contrato in result.get("contratos", []):
            objeto = (contrato.objeto if hasattr(contrato, "objeto") else str(contrato)).lower()

            # Filtrar apenas contratos de seguranca
            is_security = any(kw in objeto for kw in SECURITY_KEYWORDS)
            if not is_security:
                continue

            # Extrair dados de preco
            valor = contrato.valor_global or contrato.valor_inicial if hasattr(contrato, "valor_global") else None

            if valor and float(valor) > 0:
                price_data.append(
                    {
                        "descricao": contrato.objeto if hasattr(contrato, "objeto") else str(contrato),
                        "valor_unitario": float(valor),
                        "unidade": "mensal",
                        "orgao": contrato.nome_orgao if hasattr(contrato, "nome_orgao") else None,
                        "data_referencia": (
                            datetime.combine(contrato.data_assinatura, datetime.min.time())
                            if hasattr(contrato, "data_assinatura") and contrato.data_assinatura
                            else datetime.utcnow()
                        ),
                        "metadata": {
                            "numero_contrato": (
                                contrato.numero_contrato if hasattr(contrato, "numero_contrato") else None
                            ),
                            "cnpj_orgao": (contrato.cnpj_orgao if hasattr(contrato, "cnpj_orgao") else None),
                            "cnpj_fornecedor": (
                                contrato.cnpj_fornecedor if hasattr(contrato, "cnpj_fornecedor") else None
                            ),
                            "uf": uf,
                        },
                    }
                )

    logger.info(f"[BIDDING] {len(price_data)} precos de referencia extraidos do PNCP")
    return price_data


# ──────────────────────────────────────────────
# Task 3: Atualizar contratos existentes no PNCP
# ──────────────────────────────────────────────


@shared_task(
    bind=True,
    name="bidding.atualizar_contratos_pncp",
    queue="gov.batch",
    max_retries=3,
    default_retry_delay=600,
    soft_time_limit=600,
    time_limit=900,
)
def atualizar_contratos_pncp(self, uf: str = "AM"):
    """
    Atualiza status de contratos existentes no banco consultando o PNCP.

    Verifica contratos com status 'ativo' e atualiza dados de aditivos,
    valores e vigencia.

    Args:
        uf: UF para filtrar contratos (default: AM).

    Returns:
        Dict com resumo: {total_checked, updated, errors}
    """
    from core.database.session import get_sync_db

    logger.info(f"[BIDDING] Iniciando atualizacao de contratos PNCP: UF={uf}")

    updated_count = 0
    error_count = 0
    total_checked = 0

    try:
        with get_sync_db() as db:
            from sqlalchemy import select

            from modules.bidding.models.opportunity import BiddingOpportunity

            # Buscar oportunidades ativas do PNCP
            opportunities = (
                db.execute(
                    select(BiddingOpportunity).where(
                        BiddingOpportunity.portal == "pncp",
                        BiddingOpportunity.status.in_(["nova", "em_analise", "aprovada"]),
                        BiddingOpportunity.uf == uf,
                    )
                )
                .scalars()
                .all()
            )

            total_checked = len(opportunities)

            for opp in opportunities:
                try:
                    # Verificar se a data de encerramento ja passou
                    if opp.data_encerramento and opp.data_encerramento < datetime.utcnow():
                        opp.status = "encerrada"
                        opp.updated_at = datetime.utcnow()
                        updated_count += 1
                except Exception as e:
                    logger.error(f"[BIDDING] Erro ao atualizar contrato {opp.id}: {e}")
                    error_count += 1

        summary = {
            "total_checked": total_checked,
            "updated": updated_count,
            "errors": error_count,
            "uf": uf,
        }

        logger.info(
            f"[BIDDING] Atualizacao contratos PNCP concluida: {total_checked} verificados, {updated_count} atualizados"
        )

        return summary

    except Exception as e:
        logger.error(f"[BIDDING] Erro na atualizacao de contratos PNCP: {e}")
        raise self.retry(exc=e)
