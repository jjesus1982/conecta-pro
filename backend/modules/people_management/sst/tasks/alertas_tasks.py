"""Alertas SST no sistema de notificações INTERNO (sino do Conecta PRO).

Task Celery `sst.alertas_diarios` (beat diário 08:00 America/Manaus) — gera
notificações internas para os usuários ADMIN via notification_queue
(channel_type='push'), o MESMO caminho que o sino do frontend lê em
GET /api/v1/notifications/push. NADA de Telegram.

Alertas (todos por FATO no banco — nunca fabricados):
1. ASOs vencendo em 30 dias (agrupado: "X ASOs vencem em 30d") — diário
2. ASOs JÁ vencidas — resumo SEMANAL (só segunda-feira; anti-spam)
3. CATs com esocial_status em nao_transmitida/erro há mais de 4h
   (prazo legal S-2210 = 1 dia útil!) — diário
4. Fichas de EPI pendentes de assinatura há 7+ dias — diário

Dedupe: por correlation_id (chave estável por tipo de alerta). Se já existe
notificação NÃO-LIDA igual (mesmo título/corpo) para o usuário, não recria;
se os números mudaram, ATUALIZA a existente em vez de empilhar outra.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from uuid import UUID, uuid4

from celery_app import app

logger = logging.getLogger(__name__)

# Mesmo tenant do fallback de get_tenant_id do controller de notificações
# (users não tem coluna tenant_id — o sino sempre consulta este tenant)
_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


def _upsert_notificacao(db, user_id, correlation_id: str, titulo: str, corpo: str,
                        action_url: str | None, prioridade) -> str:
    """Cria (ou atualiza) UMA notificação interna não-lida por chave/usuário.

    Retorna: 'criada' | 'atualizada' | 'igual' (dedupe — nada feito).
    """
    from modules.notifications.models import NotificationQueue, QueueStatus

    content_data = {"action_url": action_url, "custom_data": {"origem": "sst.alertas_diarios"}}

    existente = (
        db.query(NotificationQueue)
        .filter(
            NotificationQueue.tenant_id == _TENANT_ID,
            NotificationQueue.user_id == user_id,
            NotificationQueue.channel_type == "push",
            NotificationQueue.correlation_id == correlation_id,
            NotificationQueue.opened.is_(False),
        )
        .order_by(NotificationQueue.created_at.desc())
        .first()
    )
    if existente is not None:
        if existente.subject == titulo and existente.body == corpo:
            return "igual"  # não recriar notificação igual não-lida (anti-spam)
        existente.subject = titulo
        existente.body = corpo
        existente.content_data = content_data
        existente.created_at = datetime.utcnow()
        return "atualizada"

    db.add(
        NotificationQueue(
            tenant_id=_TENANT_ID,
            notification_id=f"sst-{uuid4().hex[:20]}",
            correlation_id=correlation_id,
            user_id=user_id,
            recipient_type="user",
            recipient_address="push",
            channel_type="push",
            subject=titulo,
            body=corpo,
            content_data=content_data,
            # DELIVERED: notificação interna do sino — nenhum worker de envio
            # deve tentar despachá-la para dispositivo/e-mail
            status=QueueStatus.DELIVERED,
            priority=prioridade,
            trigger_type="scheduled",
            category="sst",
            opened=False,
        )
    )
    return "criada"


def _coletar_alertas(db, incluir_semanais: bool) -> list[dict]:
    """Consulta os FATOS no banco e monta a lista de alertas (sem criar nada)."""
    from sqlalchemy import text

    from modules.notifications.models import QueuePriority

    alertas: list[dict] = []

    # 1. ASOs vencendo nos próximos 30 dias (agrupado) — diário
    vencendo = db.execute(
        text(
            "SELECT count(*) AS regs, count(DISTINCT employee_id) AS funcs "
            "FROM gp_asos WHERE data_validade IS NOT NULL "
            "AND data_validade >= CURRENT_DATE "
            "AND data_validade <= CURRENT_DATE + INTERVAL '30 days'"
        )
    ).mappings().first()
    if vencendo and vencendo["regs"]:
        alertas.append(
            {
                "chave": "sst:asos_vencendo_30d",
                "titulo": f"SST: {vencendo['regs']} ASO(s) vencem em 30 dias",
                "corpo": (
                    f"{vencendo['regs']} ASO(s) de {vencendo['funcs']} funcionário(s) vencem nos "
                    "próximos 30 dias. Agende os exames periódicos (NR-7) para manter o PCMSO em dia."
                ),
                "action_url": "/modulos/gestao-pessoas/saude-ocupacional/exames",
                "prioridade": QueuePriority.NORMAL,
            }
        )

    # 2. ASOs JÁ vencidas — resumo SEMANAL (segunda-feira), anti-spam
    if incluir_semanais:
        vencidas = db.execute(
            text(
                "SELECT count(*) AS regs, count(DISTINCT employee_id) AS funcs "
                "FROM gp_asos WHERE data_validade IS NOT NULL AND data_validade < CURRENT_DATE"
            )
        ).mappings().first()
        if vencidas and vencidas["regs"]:
            alertas.append(
                {
                    "chave": "sst:asos_vencidas_semanal",
                    "titulo": f"SST (semanal): {vencidas['regs']} ASO(s) vencida(s)",
                    "corpo": (
                        f"Resumo semanal: {vencidas['regs']} registro(s) de ASO vencido(s), "
                        f"{vencidas['funcs']} funcionário(s) afetado(s). Use o plano de "
                        "regularização para agendar em lote."
                    ),
                    "action_url": "/modulos/gestao-pessoas/saude-ocupacional/compliance-nr1",
                    "prioridade": QueuePriority.NORMAL,
                }
            )

    # 3. CATs não transmitidas/erro no eSocial há mais de 4h — prazo legal 1 dia útil
    cats = db.execute(
        text(
            "SELECT count(*) AS n, min(created_at) AS mais_antiga FROM gp_cats "
            "WHERE esocial_status IN ('nao_transmitida', 'erro') "
            "AND created_at < now() - INTERVAL '4 hours'"
        )
    ).mappings().first()
    if cats and cats["n"]:
        alertas.append(
            {
                "chave": "sst:cats_esocial_pendentes",
                "titulo": f"URGENTE SST: {cats['n']} CAT(s) sem transmissão ao eSocial",
                "corpo": (
                    f"{cats['n']} CAT(s) com eSocial em 'nao_transmitida'/'erro' há mais de 4h "
                    f"(mais antiga: {cats['mais_antiga']:%d/%m/%Y %H:%M}). PRAZO LEGAL do "
                    "S-2210 é 1 DIA ÚTIL após o acidente — transmita agora."
                ),
                "action_url": "/modulos/gestao-pessoas/saude-ocupacional",
                "prioridade": QueuePriority.CRITICAL,
            }
        )

    # 4. Fichas de EPI pendentes de assinatura há 7+ dias
    fichas = db.execute(
        text(
            "SELECT count(*) AS n FROM sst_fichas_epi "
            "WHERE status = 'pendente_assinatura' "
            "AND created_at < now() - INTERVAL '7 days'"
        )
    ).mappings().first()
    if fichas and fichas["n"]:
        alertas.append(
            {
                "chave": "sst:fichas_epi_pendentes_7d",
                "titulo": f"SST: {fichas['n']} ficha(s) de EPI sem assinatura há 7+ dias",
                "corpo": (
                    f"{fichas['n']} ficha(s) de EPI aguardam assinatura do funcionário há mais "
                    "de 7 dias (NR-6). Cobre a assinatura digital pelo Portal do Funcionário."
                ),
                "action_url": "/modulos/gestao-pessoas/saude-ocupacional/epis",
                "prioridade": QueuePriority.HIGH,
            }
        )

    return alertas


@app.task(name="sst.alertas_diarios")
def alertas_diarios(forcar_semanais: bool = False) -> str:
    """Gera os alertas SST do dia no sino interno dos usuários ADMIN.

    forcar_semanais=True inclui o resumo semanal de ASOs vencidas mesmo fora
    de segunda-feira (para teste manual/prova).
    """
    from sqlalchemy import text

    from core.database.session import get_sync_db

    incluir_semanais = forcar_semanais or date.today().weekday() == 0  # segunda-feira

    try:
        with get_sync_db() as db:
            admins = db.execute(
                text("SELECT id, email FROM users WHERE role = 'admin' AND is_active = true")
            ).mappings().all()
            if not admins:
                return "Nenhum usuário admin ativo — nada a notificar"

            alertas = _coletar_alertas(db, incluir_semanais)
            if not alertas:
                logger.info("sst.alertas_diarios: nenhum alerta hoje (banco sem pendências)")
                return "0 alertas (sem pendências SST no banco)"

            criadas = atualizadas = iguais = 0
            for alerta in alertas:
                for adm in admins:
                    resultado = _upsert_notificacao(
                        db,
                        user_id=adm["id"],
                        correlation_id=alerta["chave"],
                        titulo=alerta["titulo"],
                        corpo=alerta["corpo"],
                        action_url=alerta["action_url"],
                        prioridade=alerta["prioridade"],
                    )
                    if resultado == "criada":
                        criadas += 1
                    elif resultado == "atualizada":
                        atualizadas += 1
                    else:
                        iguais += 1
            db.commit()

            resumo = (
                f"{len(alertas)} alerta(s) SST × {len(admins)} admin(s): "
                f"{criadas} criada(s), {atualizadas} atualizada(s), {iguais} dedupe (não-lidas iguais)"
            )
            logger.info("sst.alertas_diarios concluído: %s", resumo)
            return resumo

    except Exception as exc:
        logger.error("Erro em sst.alertas_diarios: %s", exc)
        return f"Erro: {exc}"
