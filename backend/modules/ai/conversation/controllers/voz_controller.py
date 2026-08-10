"""TTS do chat flutuante — voz da OpenAI (mesmo motor do gpt-realtime).

Histórico curto: 1º a voz do navegador (`speechSynthesis`) — robótica, usa a voz do SO.
2º edge-tts — neural, mas mandava o texto para a Microsoft, um terceiro NOVO. Agora
`gpt-4o-mini-tts`, que além de soar melhor **não amplia a exposição de dados**: o texto
já passa pela OpenAI no motor do chat (run_engine). Um fornecedor a menos no caminho.

O diferencial do gpt-4o-mini-tts é `instructions`: dá para dirigir o TOM ("como um colega
de trabalho, sem entonação de locutor") em vez de só escolher uma voz pronta.

Ordem de tentativa (nenhuma falha deixa o usuário mudo):
  OpenAI gpt-4o-mini-tts → edge-tts → (no front) voz do navegador.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.auth.dependencies import CurrentActiveUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/consultores/voz", tags=["Consultores — Voz (TTS)"])

MODELO = "gpt-4o-mini-tts"
# Vozes da OpenAI que soam bem em pt-BR (testadas por amostra com o Jordan).
VOZES_OPENAI = {"coral", "nova", "verse", "sage", "alloy", "echo", "shimmer", "ballad", "ash"}
PADRAO = os.getenv("VOZ_TTS_PADRAO", "verse")   # Jordan escolheu "verse" (expressiva).
# Fica no BACKEND de proposito: trocar a voz vira restart, nao rebuild do frontend.
# Direção de atuação: é isto que tira o sotaque de locutor de propaganda.
TOM = ("Fale em português do Brasil, natural e direto, como um colega de trabalho experiente "
       "conversando. Ritmo normal, sem entonação de locutor, sem entusiasmo artificial. "
       "Números e valores ditos como se fala no dia a dia.")
LIMITE = 1200          # ~1min30 de fala: acima disso ninguém ouve até o fim
VOZES_EDGE = {"francisca": "pt-BR-FranciscaNeural", "antonio": "pt-BR-AntonioNeural",
              "thalita": "pt-BR-ThalitaMultilingualNeural"}


class FalarIn(BaseModel):
    texto: str = Field(..., min_length=1, max_length=4000)
    voz: str = Field(PADRAO, max_length=20)
    velocidade: float = Field(1.0, ge=0.5, le=1.5)


def _limpar(t: str) -> str:
    """Tira o que não se lê em voz alta: markdown, URL, emoji, separador de tabela."""
    t = re.sub(r"https?://\S+", "link", t)
    t = re.sub(r"[*_`#>|]+", " ", t)
    t = re.sub(r"[\U0001F300-\U0001FAFF☀-➿]", "", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()[:LIMITE]


def _openai_tts(texto: str, voz: str, velocidade: float) -> bytes | None:
    """gpt-4o-mini-tts. Devolve None (em vez de estourar) p/ cair no fallback."""
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        return None
    body = json.dumps({
        "model": MODELO,
        "voice": voz if voz in VOZES_OPENAI else PADRAO,
        "input": texto,
        "instructions": TOM,
        "speed": velocidade,
        "response_format": "mp3",
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=30).read() or None
    except Exception as e:  # noqa: BLE001
        logger.warning("voz/falar: OpenAI TTS falhou (%s chars): %s", len(texto), e)  # nunca o texto
        return None


async def _edge_tts(texto: str) -> bytes | None:
    """Reserva: neural pt-BR sem chave. Só entra se a OpenAI falhar."""
    try:
        import edge_tts  # noqa: PLC0415
    except ImportError:
        return None
    try:
        import io
        buf = io.BytesIO()
        async for ch in edge_tts.Communicate(texto, VOZES_EDGE["francisca"], rate="+4%").stream():
            if ch.get("type") == "audio":
                buf.write(ch["data"])
        return buf.getvalue() or None
    except Exception as e:  # noqa: BLE001
        logger.warning("voz/falar: edge-tts (reserva) falhou: %s", e)
        return None


@router.post("/falar")
async def falar(payload: FalarIn, current_user: CurrentActiveUser):
    """Texto → MP3. OpenAI primeiro; edge-tts como reserva."""
    texto = _limpar(payload.texto)
    if not texto:
        raise HTTPException(status_code=400, detail="Nada a falar depois da limpeza do texto.")

    audio = _openai_tts(texto, (payload.voz or PADRAO).strip().lower(), payload.velocidade)
    origem = "openai"
    if not audio:
        audio = await _edge_tts(texto)
        origem = "edge"
    if not audio:
        raise HTTPException(status_code=502, detail="Não consegui gerar o áudio agora.")

    return Response(content=audio, media_type="audio/mpeg",
                    headers={"Cache-Control": "no-store", "X-Voz-Origem": origem})
