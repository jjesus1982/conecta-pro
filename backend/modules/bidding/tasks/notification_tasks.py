"""
Tasks Celery de notificacoes e monitoramento de certidoes.
==========================================================

Tasks:
- verificar_certidoes_vencimento: Verifica certidoes a cada 6h
- notificar_oportunidade_nova: Despacha notificacao de nova oportunidade
- notificar_prazo_edital: Notifica prazos criticos de editais
- notificar_resultado_pipeline: Envia resultado do pipeline de analise
"""

import asyncio
import logging
from datetime import datetime

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


#: O sino é `communication_notifications`. Os quatro pontos deste arquivo escreviam em
#: `notifications`, que NÃO EXISTE — e errado em quatro dimensões de uma vez: tabela
#: inexistente, coluna `message` (é `body`), coluna `priority` (não existe) e sem
#: `tenant_id`/`user_id`, que são NOT NULL. Resultado medido em 14/08/2026:
#:
#:     ProgrammingError: relation "notifications" does not exist
#:
#: três tarefas de licitação mortas desde 11/08 — sincronizar oportunidades do PNCP,
#: sincronizar preços e VERIFICAR VENCIMENTO DE CERTIDÃO. A última é a que dói: o vigia que
#: avisaria que a CND vai vencer morria antes de avisar, e a falha dele virava mais uma
#: linha de ruído no sino, escondendo o resto.
#:
#: Nenhuma trava pega isto: nome de tabela em SQL cru não é chamada a método inexistente
#: nem literal fora do vocabulário de uma coluna. Só quebra em runtime, longe de plateia.
_SQL_SINO_BIDDING = """
    INSERT INTO communication_notifications
        (id, tenant_id, user_id, title, body, type, reference_type,
         action_url, extra_data, is_active, sent_at, created_at)
    VALUES (gen_random_uuid(), :uid, :uid, :title, :body, 'alerta', :ref,
            '/redesign', CAST(:extra AS jsonb), true, NOW(), NOW())
    ON CONFLICT DO NOTHING
"""


def _publicar_no_sino(db, titulo: str, corpo: str, ref: str, chave: str) -> int:
    """Publica um alerta para cada admin ativo. Devolve quantos receberam.

    Reusa `_SQL_DESTINATARIOS` de `task_falha` — é a definição canônica de "quem recebe
    alerta do sistema", e ela já exclui a conta de serviço do MCP (robô recebendo alerta é
    ruído que treina gente a ignorar o sino).

    `chave` entra na `idempotency_key`, que tem índice único por usuário: publicar de novo no
    mesmo dia não duplica. Sem ela, uma tarefa de 6 em 6 horas escreveria a mesma certidão
    quatro vezes por dia.
    """
    import json

    from sqlalchemy import text

    from modules.notifications.task_falha import _SQL_DESTINATARIOS

    destinatarios = [r[0] for r in db.execute(text(_SQL_DESTINATARIOS)).fetchall()]
    if not destinatarios:
        logger.warning("[BIDDING] alerta '%s' sem admin ativo para avisar", titulo)
        return 0
    extra = json.dumps({
        "idempotency_key": chave, "origem": ref,
        "familia": "licitacao", "severidade": "critico",
    })
    for uid in destinatarios:
        db.execute(text(_SQL_SINO_BIDDING),
                   {"uid": uid, "title": titulo, "body": corpo, "ref": ref, "extra": extra})
    return len(destinatarios)


# ──────────────────────────────────────────────
# Task: Verificar certidoes e documentos
# ──────────────────────────────────────────────


@shared_task(
    bind=True,
    name="bidding.verificar_certidoes_vencimento",
    queue="gov.batch",
    max_retries=2,
    default_retry_delay=600,
    soft_time_limit=300,
    time_limit=600,
)
def verificar_certidoes_vencimento(
    self,
    cnpj: str = "35.710.481/0001-03",
    documentos: list[dict] | None = None,
):
    """
    Verifica vencimento de certidoes e documentos usando SentinelAgent.

    Cria notificacoes para documentos vencendo ou vencidos.

    Args:
        cnpj: CNPJ da empresa a verificar.
        documentos: Lista de documentos com datas (override).
                    Cada dict: {"tipo": str, "data_emissao": str, "data_validade": str}

    Returns:
        Dict: {total_checked, alertas_criticos, alertas_urgentes, apto_licitar}
    """
    from core.database.session import get_sync_db

    logger.info(f"[BIDDING] Verificando certidoes para CNPJ {cnpj}")

    try:
        # Executar SentinelAgent (async)
        result = run_async(_verificar_certidoes(cnpj=cnpj, documentos=documentos))

        alertas_criticos = len(result.get("alertas_criticos", []))
        alertas_urgentes = len(result.get("alertas_urgentes", []))
        alertas_atencao = len(result.get("alertas_atencao", []))

        # Persistir notificacoes no banco para alertas criticos e urgentes
        if alertas_criticos > 0 or alertas_urgentes > 0:
            dia = datetime.utcnow().strftime("%Y-%m-%d")
            with get_sync_db() as db:
                # Um alerta por severidade por dia, com TODAS as certidões daquela faixa
                # dentro. Uma linha por certidão encheria o sino com quatro cópias diárias
                # do mesmo problema — que é exatamente o ruído que fez as tarefas mortas do
                # GEDEON passarem três dias despercebidas.
                for faixa, titulo in (("alertas_criticos", "Certidão CRÍTICA — Licitações"),
                                      ("alertas_urgentes", "Certidão URGENTE — Licitações")):
                    alertas = result.get(faixa, [])
                    if not alertas:
                        continue
                    _publicar_no_sino(
                        db,
                        titulo=f"{titulo} ({len(alertas)})",
                        corpo="\n".join(str(a) for a in alertas),
                        ref="bidding_certidao",
                        chave=f"bidding_certidao:{faixa}:{cnpj}:{dia}",
                    )
                db.commit()

        summary = {
            "total_checked": result.get("total_documentos", 0),
            "alertas_criticos": alertas_criticos,
            "alertas_urgentes": alertas_urgentes,
            "alertas_atencao": alertas_atencao,
            "apto_licitar": result.get("apto_licitar", False),
            "cnpj": cnpj,
        }

        logger.info(
            f"[BIDDING] Verificacao certidoes concluida: "
            f"{summary['total_checked']} verificados, "
            f"{alertas_criticos} criticos, "
            f"{alertas_urgentes} urgentes, "
            f"apto={summary['apto_licitar']}"
        )

        return summary

    except Exception as e:
        logger.error(f"[BIDDING] Erro na verificacao de certidoes: {e}")
        raise self.retry(exc=e)


async def _verificar_certidoes(
    cnpj: str = "35.710.481/0001-03",
    documentos: list[dict] | None = None,
) -> dict:
    """Executa SentinelAgent para verificar certidoes."""
    from modules.bidding.agents.sentinel_agent import SentinelAgent

    agent = SentinelAgent()
    return await agent.execute(documentos=documentos, cnpj=cnpj)


# ──────────────────────────────────────────────
# Task: Notificar nova oportunidade encontrada
# ──────────────────────────────────────────────


@shared_task(
    bind=True,
    name="bidding.notificar_oportunidade_nova",
    queue="gov.batch",
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=120,
    time_limit=180,
)
def notificar_oportunidade_nova(
    self,
    opportunity_id: str,
    objeto: str,
    valor_estimado: float | None = None,
    orgao_nome: str | None = None,
    relevancia_score: float = 0,
):
    """
    Despacha notificacao de nova oportunidade de licitacao encontrada.

    Args:
        opportunity_id: UUID da oportunidade.
        objeto: Descricao do objeto licitado.
        valor_estimado: Valor estimado da licitacao.
        orgao_nome: Nome do orgao licitante.
        relevancia_score: Score de relevancia (0-100).

    Returns:
        Dict: {notified, channels}
    """
    from core.database.session import get_sync_db

    logger.info(f"[BIDDING] Notificando nova oportunidade: {opportunity_id}")

    try:
        priority = "high" if relevancia_score >= 80 else "normal" if relevancia_score >= 50 else "low"

        valor_fmt = f"R$ {valor_estimado:,.2f}" if valor_estimado else "Nao informado"

        message = (
            f"Nova oportunidade de licitacao encontrada!\n"
            f"Orgao: {orgao_nome or 'Nao informado'}\n"
            f"Objeto: {objeto[:200]}\n"
            f"Valor estimado: {valor_fmt}\n"
            f"Relevancia: {relevancia_score:.0f}%"
        )

        with get_sync_db() as db:
            # A chave é a OPORTUNIDADE, não o dia: a mesma licitação não avisa duas vezes,
            # e duas licitações no mesmo dia continuam sendo dois avisos.
            _publicar_no_sino(
                db,
                titulo="Nova oportunidade de licitação",
                corpo=message,
                ref="bidding_oportunidade",
                chave=f"bidding_oportunidade:{opportunity_id}",
            )
            db.commit()

        logger.info(f"[BIDDING] Notificacao enviada: oportunidade {opportunity_id}, prioridade={priority}")

        return {
            "notified": True,
            "channels": ["database"],
            "priority": priority,
            "opportunity_id": opportunity_id,
        }

    except Exception as e:
        logger.error(f"[BIDDING] Erro ao notificar oportunidade: {e}")
        raise self.retry(exc=e)


# ──────────────────────────────────────────────
# Task: Notificar prazo critico de edital
# ──────────────────────────────────────────────


@shared_task(
    bind=True,
    name="bidding.notificar_prazo_edital",
    queue="gov.batch",
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=120,
    time_limit=180,
)
def notificar_prazo_edital(
    self,
    tender_id: str,
    numero_edital: str,
    data_abertura: str,
    dias_restantes: int,
):
    """
    Notifica prazos criticos de editais em andamento.

    Args:
        tender_id: UUID do tender.
        numero_edital: Numero do edital.
        data_abertura: Data de abertura ISO format.
        dias_restantes: Dias restantes ate a abertura.

    Returns:
        Dict: {notified, priority}
    """
    from core.database.session import get_sync_db

    logger.info(f"[BIDDING] Notificando prazo edital {numero_edital}: {dias_restantes} dias restantes")

    try:
        if dias_restantes <= 1:
            priority = "critical"
            title = "URGENTE: Edital abre AMANHA!"
        elif dias_restantes <= 3:
            priority = "high"
            title = f"Edital abre em {dias_restantes} dias"
        elif dias_restantes <= 7:
            priority = "normal"
            title = f"Edital abre em {dias_restantes} dias"
        else:
            priority = "low"
            title = f"Lembrete: edital abre em {dias_restantes} dias"

        message = f"Edital: {numero_edital}\nData de abertura: {data_abertura}\nDias restantes: {dias_restantes}"

        with get_sync_db() as db:
            # Prazo muda de faixa conforme o dia se aproxima (30d → 7d → amanhã), e cada
            # faixa merece um aviso novo. Por isso a chave leva edital + dias restantes.
            _publicar_no_sino(
                db,
                titulo=title,
                corpo=message,
                ref="bidding_prazo",
                chave=f"bidding_prazo:{numero_edital}:{dias_restantes}",
            )
            db.commit()

        logger.info(f"[BIDDING] Notificacao prazo enviada: {numero_edital}, prioridade={priority}")

        return {
            "notified": True,
            "priority": priority,
            "tender_id": tender_id,
            "dias_restantes": dias_restantes,
        }

    except Exception as e:
        logger.error(f"[BIDDING] Erro ao notificar prazo edital: {e}")
        raise self.retry(exc=e)


# ──────────────────────────────────────────────
# Task: Notificar resultado do pipeline de analise
# ──────────────────────────────────────────────


@shared_task(
    bind=True,
    name="bidding.notificar_resultado_pipeline",
    queue="gov.batch",
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=120,
    time_limit=180,
)
def notificar_resultado_pipeline(
    self,
    tender_id: str | None = None,
    numero_edital: str | None = None,
    recomendacao: str | None = None,
    score: float = 0,
    preco_mensal: float | None = None,
):
    """
    Envia notificacao com resultado do pipeline de analise.

    Args:
        tender_id: UUID do tender.
        numero_edital: Numero do edital.
        recomendacao: Recomendacao (PARTICIPAR/NAO_PARTICIPAR/AVALIAR).
        score: Score de viabilidade.
        preco_mensal: Preco mensal estimado.

    Returns:
        Dict: {notified, priority}
    """
    from core.database.session import get_sync_db

    logger.info(f"[BIDDING] Notificando resultado pipeline: edital={numero_edital}, rec={recomendacao}")

    try:
        if recomendacao == "PARTICIPAR" and score >= 70:
            priority = "high"
            title = f"RECOMENDADO: Participar edital {numero_edital or 'N/I'}"
        elif recomendacao == "NAO_PARTICIPAR":
            priority = "normal"
            title = f"NAO recomendado: Edital {numero_edital or 'N/I'}"
        else:
            priority = "normal"
            title = f"Analise concluida: Edital {numero_edital or 'N/I'}"

        preco_fmt = f"R$ {preco_mensal:,.2f}" if preco_mensal else "Nao calculado"

        message = (
            f"Pipeline de analise concluido!\n"
            f"Edital: {numero_edital or 'N/I'}\n"
            f"Recomendacao: {recomendacao or 'N/I'}\n"
            f"Score: {score:.0f}/100\n"
            f"Preco mensal estimado: {preco_fmt}"
        )

        with get_sync_db() as db:
            # Quinto ponto do mesmo defeito — não estava no diagnóstico, que listava quatro.
            # Por isso a troca foi feita na FAMÍLIA (um publicador só) e não linha a linha.
            _publicar_no_sino(
                db,
                titulo=title,
                corpo=message,
                ref="bidding_pipeline",
                chave=f"bidding_pipeline:{numero_edital or 'sem-numero'}:{score:.0f}",
            )
            db.commit()

        logger.info(f"[BIDDING] Notificacao resultado pipeline enviada: {numero_edital}")

        return {
            "notified": True,
            "priority": priority,
            "tender_id": tender_id,
            "recomendacao": recomendacao,
        }

    except Exception as e:
        logger.error(f"[BIDDING] Erro ao notificar resultado pipeline: {e}")
        raise self.retry(exc=e)
