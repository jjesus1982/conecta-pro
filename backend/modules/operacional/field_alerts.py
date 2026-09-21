"""Alertas de campo (ocorrências operacionais) — SEM CANAL DE ENVIO desde 11/08/2026.

Este módulo mandava para o Telegram. O Jordan apagou e bloqueou os dois bots, as
credenciais saíram do `.env`, e em 20/09/2026 o corpo morto que ainda guardava a URL da
API foi removido daqui.

⚠️ O QUE ISSO SIGNIFICA HOJE, para ninguém descobrir tarde: `enviar_telegram()` devolve
`False` e escreve o texto no log. A ocorrência GRAVE e a GRAVÍSSIMA continuam sendo
registradas no banco normalmente — o que não acontece mais é alguém ser AVISADO na hora.

O canal da casa é o SINO (`communication_notifications`), que é onde todo o resto do
sistema avisa e onde as tarefas do José Luís já escrevem. Ligar o aviso de ocorrência
gravíssima nele é decisão do dono, não conserto técnico: por isso ficou fora deste commit.
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)

_ULTIMO_ALERTA: dict[str, float] = {}
_INTERVALO_MIN_S = 60  # 1 msg por (posto+severidade) a cada 60s

_EMOJI_SEVERIDADE = {"grave": "⚠️", "gravissima": "🚨"}


async def enviar_telegram(texto: str, chat_id: str | None = None) -> bool:
    """DESATIVADA (11/08/2026) — o Telegram saiu do Conecta PRO.

    O Jordan apagou e bloqueou os dois bots (Conecta PRO Monitor e Conecta PRO Alertas);
    as credenciais saíram do `.env`. A função continua existindo e devolvendo `False`
    porque vários pontos a chamam — apagá-la quebraria chamador que não tem nada a ver
    com o bot. O texto vai para o log, então nada se perde em silêncio.

    Se o aviso voltar a fazer falta, o canal da casa é o **SINO**
    (`communication_notifications`), que é o que as tarefas do José Luís já usam.
    """
    logger.info("[telegram removido] alerta de campo não enviado: %s", (texto or "")[:200])
    return False


async def alertar_ocorrencia(
    codigo: str,
    titulo: str,
    severidade: str,
    posto_nome: str,
    autor: str,
    descricao: str,
) -> None:
    """Alerta Telegram para ocorrência grave/gravíssima. Best-effort, nunca lança."""
    try:
        sev = (severidade or "").strip().lower()
        if sev not in ("grave", "gravissima"):
            return  # leve/moderada não alertam

        # Anti-spam: 1 msg por (posto+severidade) a cada 60s
        chave = f"{posto_nome}|{sev}"
        agora = time.time()
        if agora - _ULTIMO_ALERTA.get(chave, 0) < _INTERVALO_MIN_S:
            return
        _ULTIMO_ALERTA[chave] = agora

        emoji = _EMOJI_SEVERIDADE.get(sev, "⚠️")
        msg = (
            f"{emoji} *Ocorrência {sev.upper()}* — `{codigo}`\n"
            f"📍 Posto: *{posto_nome or 'não informado'}*\n"
            f"📝 {titulo}\n"
            f"👤 Registrada por: {autor}\n"
            f"{(descricao or '')[:200]}"
        )

        # grave e gravíssima → chat operacional (fallback: chat Jordan)
        await enviar_telegram(msg)

        # gravíssima → também o chat do Jordan, sem duplicar se for o mesmo chat
        if sev == "gravissima":
            chat_jordan = os.getenv("TELEGRAM_CHAT_ID", "")
            destino_padrao = os.getenv("TELEGRAM_CHAT_ID_OPERACIONAL") or chat_jordan
            if chat_jordan and chat_jordan != destino_padrao:
                await enviar_telegram(msg, chat_id=chat_jordan)
    except Exception as e:  # noqa: BLE001
        logger.warning("Falha em alertar_ocorrencia (best-effort): %s", e)
