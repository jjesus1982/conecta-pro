"""TTS neural para o chat flutuante — a voz do navegador soava robótica demais.

`speechSynthesis` usa a voz do sistema operacional; em Linux/Windows ela é sofrível.
Aqui geramos o áudio com `edge-tts` (vozes neurais pt-BR, sem chave de API e sem custo)
e devolvemos o MP3 pronto para o `<audio>` tocar.

⚠️ PRIVACIDADE — a única coisa que sai daqui é o TEXTO A FALAR, que vai para o serviço de
voz da Microsoft. Para "temos nove postos ativos" é inofensivo; para uma resposta com nome
e CPF de colaborador, NÃO é. Por isso: cap de tamanho, sem log do conteúdo, e a rota exige
usuário autenticado. Quando o volume justificar, trocar por TTS local (Kokoro/Coqui) e o
frontend não muda — o contrato desta rota continua o mesmo.
"""
from __future__ import annotations

import io
import logging
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.auth.dependencies import CurrentActiveUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/consultores/voz", tags=["Consultores — Voz (TTS)"])

# Vozes neurais pt-BR do edge-tts. Antonio = masculina; as outras, femininas.
VOZES = {"antonio": "pt-BR-AntonioNeural", "francisca": "pt-BR-FranciscaNeural",
         "thalita": "pt-BR-ThalitaMultilingualNeural"}
PADRAO = "pt-BR-FranciscaNeural"
LIMITE = 1200          # ~1min30 de fala: acima disso ninguém ouve até o fim


class FalarIn(BaseModel):
    texto: str = Field(..., min_length=1, max_length=4000)
    voz: str = Field("francisca", max_length=20)
    velocidade: int = Field(0, ge=-30, le=30, description="% sobre a velocidade natural")


def _limpar(t: str) -> str:
    """Tira o que não se lê em voz alta: markdown, URL, emoji, tabela."""
    t = re.sub(r"https?://\S+", "link", t)
    t = re.sub(r"[*_`#>|]+", " ", t)
    t = re.sub(r"[\U0001F300-\U0001FAFF☀-➿]", "", t)   # emoji
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()[:LIMITE]


@router.post("/falar")
async def falar(payload: FalarIn, current_user: CurrentActiveUser):
    """Texto → MP3 com voz neural pt-BR. Devolve audio/mpeg pronto para tocar."""
    texto = _limpar(payload.texto)
    if not texto:
        raise HTTPException(status_code=400, detail="Nada a falar depois da limpeza do texto.")
    try:
        import edge_tts  # noqa: PLC0415
    except ImportError:
        # Degradação honesta: o front volta pra voz do navegador em vez de ficar mudo.
        raise HTTPException(status_code=503, detail="TTS indisponível no servidor (edge-tts ausente).")

    voz = VOZES.get((payload.voz or "").strip().lower(), PADRAO)
    rate = f"{payload.velocidade:+d}%"
    buf = io.BytesIO()
    try:
        com = edge_tts.Communicate(texto, voz, rate=rate)
        async for chunk in com.stream():
            if chunk.get("type") == "audio":
                buf.write(chunk["data"])
    except Exception as e:  # noqa: BLE001
        logger.error("voz/falar: sintese falhou (%s chars): %s", len(texto), e)  # nunca logar o texto
        raise HTTPException(status_code=502, detail="Não consegui gerar o áudio agora.")

    if not buf.tell():
        raise HTTPException(status_code=502, detail="A síntese devolveu áudio vazio.")
    buf.seek(0)
    return StreamingResponse(buf, media_type="audio/mpeg",
                             headers={"Cache-Control": "no-store"})
