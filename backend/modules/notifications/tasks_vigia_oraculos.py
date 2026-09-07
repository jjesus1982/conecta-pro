"""Alarme de AUSÊNCIA da varredura dos oráculos.

O problema que isto fecha: a varredura só avisa quando acha vermelho. Se o cron do host não
disparar — job removido, script sem permissão, backend fora do ar, servidor reiniciado — o
sino fica em silêncio, e silêncio passa a significar duas coisas opostas: "tudo verde" e
"nunca rodou". Foi exatamente essa ambiguidade que deixou 59 oráculos apodrecerem sem
ninguém notar, e seria irônico reproduzi-la no mecanismo criado para acabar com ela.

**Mora no Celery de propósito.** Quem vigia não pode depender do mesmo mecanismo que vigia:
a varredura é cron do host, este vigia é beat do Celery. Um cron quebrado não silencia os
dois. É barato — uma consulta, sem subprocesso — então não repete o erro de OOM que tirou a
varredura de dentro do worker.

Tolerância de 30h: a varredura é diária às 05:00, então 30h dá folga para um deploy que
adiou a rodada da noite sem gritar por causa de algumas horas.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

from celery import shared_task
from sqlalchemy import text

logger = logging.getLogger(__name__)

_CHAVE_BATIDA = "oraculos.ultima_varredura"

#: Diária à 00:00 + folga para um deploy ter adiado a rodada da noite.
_TOLERANCIA = timedelta(hours=30)


@shared_task(name="orq.checar_varredura_ausente")
def checar_varredura_ausente() -> dict:
    """Toca o sino se a varredura não rodou dentro da tolerância. Silencioso se rodou."""
    from core.database.session import SyncSessionLocal
    from modules.notifications.task_falha import _SQL_DESTINATARIOS, _SQL_SINO

    agora = datetime.now(UTC)
    with SyncSessionLocal() as db:
        bruto = db.execute(text("SELECT valor FROM system_configs WHERE chave = :c"),
                           {"c": _CHAVE_BATIDA}).scalar()

        ultima = None
        if bruto:
            try:
                ultima = datetime.fromisoformat(json.loads(bruto)["em"])
            except Exception as exc:  # noqa: BLE001 — batida ilegível conta como ausência
                logger.warning("[vigia] batida ilegível (%s) — tratando como ausente", exc)

        if ultima and agora - ultima <= _TOLERANCIA:
            horas = round((agora - ultima).total_seconds() / 3600, 1)
            logger.info("[vigia] varredura rodou há %sh — nada a fazer", horas)
            return {"ok": True, "ha_horas": horas}

        # Ausência. Dedup por dia, mesma mecânica de task_falha e da própria varredura.
        if ultima is None:
            quando = "nunca registrou uma varredura"
            atraso = "desconhecido"
        else:
            horas = round((agora - ultima).total_seconds() / 3600, 1)
            quando = f"a última varredura foi há {horas}h"
            atraso = f"{horas}h"

        dia = agora.strftime("%Y-%m-%d")
        corpo = (
            f"A varredura dos oráculos deveria rodar todo dia à 00:00, e {quando}.\n\n"
            f"Isto NÃO quer dizer que o sistema está com problema — quer dizer que ninguém "
            f"está mais conferindo. Enquanto a varredura não rodar, o silêncio do sino não "
            f"prova mais nada: divergência entre o que a tela mostra e o que o banco tem "
            f"passaria despercebida.\n\n"
            f"Onde olhar: /var/log/conecta-oraculos.log (cabeçalho por execução), "
            f"`crontab -l | grep oraculos`, e se o conecta-pro-backend está de pé.\n"
            f"Rodar à mão: /opt/conecta-pro/scripts/oraculos_diarios.sh"
        )
        extra = json.dumps({
            "idempotency_key": f"oraculos_ausentes:{dia}",
            "origem": "vigia_oraculos", "familia": "sistema", "severidade": "critico",
            "atraso": atraso,
        })
        destinatarios = [r[0] for r in db.execute(text(_SQL_DESTINATARIOS)).fetchall()]
        for uid in destinatarios:
            db.execute(text(_SQL_SINO), {
                "uid": uid, "title": "Ninguém está conferindo os oráculos",
                "body": corpo, "extra": extra})
        db.commit()

    logger.warning("[vigia] varredura ausente (%s) — sino tocado para %s destinatário(s)",
                   atraso, len(destinatarios))
    return {"ok": False, "atraso": atraso, "avisados": len(destinatarios)}
