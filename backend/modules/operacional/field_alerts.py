"""Alertas Telegram de campo (ocorrências operacionais).

Padrão seguido: modules/ai/conversation/services/llm_credit_alert.py
(httpx.AsyncClient timeout=10, POST api.telegram.org sendMessage com
parse_mode Markdown, try/except que só loga, anti-spam por dict em memória).

Destino:
- 'grave'      → chat operacional (TELEGRAM_CHAT_ID_OPERACIONAL; fallback TELEGRAM_CHAT_ID).
- 'gravissima' → chat operacional + chat do Jordan (TELEGRAM_CHAT_ID), sem duplicar
                 se ambos forem o mesmo chat.
- demais severidades → não envia.

Anti-spam: máx 1 mensagem por (posto+severidade) a cada 60s.
Best-effort: NUNCA lança exceção — alerta jamais pode quebrar o registro da ocorrência.
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
    """Envia mensagem Telegram. Best-effort: nunca lança, retorna False em falha.

    Default de destino: TELEGRAM_CHAT_ID_OPERACIONAL; se ausente, TELEGRAM_CHAT_ID.
    """
    try:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        destino = chat_id or os.getenv("TELEGRAM_CHAT_ID_OPERACIONAL") or os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not destino:
            logger.warning("Alerta de campo: TELEGRAM_BOT_TOKEN/chat_id ausentes — alerta não enviado")
            return False

        import httpx

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as cli:
            resp = await cli.post(
                url,
                json={"chat_id": destino, "text": texto, "parse_mode": "Markdown"},
            )
            if resp.status_code == 400:
                # Markdown malformado (caracteres especiais) → reenviar como texto puro
                resp = await cli.post(
                    url, json={"chat_id": destino, "text": texto, "disable_web_page_preview": True}
                )
        if resp.status_code != 200:
            logger.warning("Alerta de campo Telegram falhou (HTTP %s)", resp.status_code)
            return False
        return True
    except Exception as e:  # noqa: BLE001 — alerta nunca pode quebrar o fluxo
        logger.warning("Falha ao enviar alerta Telegram de campo: %s", e)
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
