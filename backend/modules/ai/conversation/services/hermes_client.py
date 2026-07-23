"""Fase 5.2a.2 — cliente do backend ao sidecar Hermes (agente autônomo local, NousResearch).

Espelha o padrão de degradação graciosa de `embedding_local.py`: nunca propaga exceção
de rede pro caminho normal sem que o CHAMADOR decida — aqui o chamador (consultor_hub.gerar)
trata `HermesIndisponivel` e cai de volta na MODEL_CHAIN (OpenAI/Claude) atual.

`hermes_disponivel()` cacheia o resultado por ~30s pra não bater no Hermes a cada chamada
de `gerar()` (que pode ser bem frequente nos 8 consultores — embora hoje só a rota
origem=="executivo" chegue aqui).
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx

HERMES_URL = os.getenv("HERMES_LOCAL_URL", "http://conecta-pro-hermes:8642")
HERMES_API_KEY = os.getenv("HERMES_API_KEY", "")

_DISPONIVEL_TTL = 30.0  # segundos
_cache_disponivel: bool | None = None
_cache_ts: float = 0.0


class HermesIndisponivel(Exception):
    """Levantada quando o Hermes não responde, responde erro, ou dá timeout.
    O chamador (consultor_hub.gerar) captura e degrada pro caminho atual."""


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if HERMES_API_KEY:
        h["Authorization"] = f"Bearer {HERMES_API_KEY}"
    return h


async def hermes_disponivel() -> bool:
    """True se o Hermes respondeu 200 em GET /v1/models nos últimos ~30s (cache);
    senão, verifica de novo agora. Nunca levanta — falha de rede = False."""
    global _cache_disponivel, _cache_ts
    agora = time.monotonic()
    if _cache_disponivel is not None and (agora - _cache_ts) < _DISPONIVEL_TTL:
        return _cache_disponivel
    ok = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{HERMES_URL}/v1/models", headers=_headers())
            ok = r.status_code == 200
    except Exception:  # noqa: BLE001 — rede fora do ar, timeout, DNS, etc.
        ok = False
    _cache_disponivel = ok
    _cache_ts = agora
    return ok


async def perguntar_hermes(
    messages: list[dict], system_prompt: str, model: str = "gpt-5",
) -> tuple[str, dict[str, Any]]:
    """POST /v1/chat/completions (formato OpenAI) no Hermes local.

    Retorna (texto, meta) no MESMO shape de consultor_hub.gerar() — {"model":...} pelo
    menos — pra ser drop-in no ponto de retorno. Em qualquer falha, levanta
    HermesIndisponivel (o chamador degrada pro caminho atual)."""
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{HERMES_URL}/v1/chat/completions", headers=_headers(), json=payload,
            )
            if r.status_code != 200:
                raise HermesIndisponivel(f"Hermes HTTP {r.status_code}: {r.text[:200]}")
            data = r.json()
    except HermesIndisponivel:
        raise
    except Exception as e:  # noqa: BLE001 — timeout, conexão recusada, JSON inválido, etc.
        raise HermesIndisponivel(str(e)[:200]) from e

    try:
        texto = (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as e:
        raise HermesIndisponivel(f"resposta Hermes em formato inesperado: {e}") from e

    if not texto:
        raise HermesIndisponivel("Hermes devolveu resposta vazia")

    tokens = (data.get("usage") or {}).get("total_tokens")
    return texto, {"provider": "hermes", "model": data.get("model", model), "tokens": tokens}
