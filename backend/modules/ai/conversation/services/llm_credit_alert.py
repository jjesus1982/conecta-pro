"""Alerta de LLM indisponível/sem crédito → Telegram do Jordan.

Requisito (2026-07-07): "preciso que os meus chats me informem todas as vezes que
estiverem sem crédito, pra eu recarregar". Usado pelos consultores IA (CFO, Jurídico,
GED) no caminho de falha do provider. Trava anti-spam: 1 alerta/hora por origem.
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)

_ULTIMO_ALERTA: dict[str, float] = {}
_INTERVALO_MIN_S = 3600  # 1 alerta/hora por consultor

_PALAVRAS_CREDITO = ("credit", "quota", "billing", "insufficient", "429", "rate limit", "payment")


def _e_erro_de_credito(erro: str) -> bool:
    e = (erro or "").lower()
    return any(p in e for p in _PALAVRAS_CREDITO)


async def alertar_llm_indisponivel(origem: str, erro: str) -> None:
    """Envia alerta Telegram quando um consultor fica sem LLM. Nunca propaga exceção."""
    try:
        agora = time.time()
        if agora - _ULTIMO_ALERTA.get(origem, 0) < _INTERVALO_MIN_S:
            return
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            logger.warning("Alerta LLM: TELEGRAM_BOT_TOKEN/CHAT_ID ausentes")
            return
        credito = _e_erro_de_credito(erro)
        titulo = "💳 SEM CRÉDITO na API" if credito else "⚠️ LLM indisponível"
        msg = (
            f"{titulo} — *{origem}*\n"
            f"O chat está respondendo em modo indisponível.\n"
            f"Erro: `{(erro or 'desconhecido')[:200]}`\n"
            + ("👉 Recarregue os créditos da API para reativar.\n" if credito else "")
            + f"_(anti-spam: próximo alerta desta origem em 1h)_"
        )
        import httpx

        async with httpx.AsyncClient(timeout=10) as cli:
            await cli.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
            )
        _ULTIMO_ALERTA[origem] = agora
        logger.info("Alerta LLM enviado ao Telegram (origem=%s, credito=%s)", origem, credito)
    except Exception as e:  # noqa: BLE001 — alerta nunca pode quebrar o consultor
        logger.warning("Falha ao enviar alerta LLM Telegram: %s", e)
