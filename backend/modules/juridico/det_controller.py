"""Monitoramento DET — endpoints. Status do certificado, ingestão de comunicação e coleta."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db

from modules.juridico import det_service as DET
from modules.juridico import processos_service as PS

router = APIRouter(prefix="/juridico/det", tags=["Jurídico - Monitoramento DET"])


@router.get("/status")
async def status(current_user=Depends(get_current_active_user)):
    """Estado real da conexão com o DET (certificado A1 + modo de operação)."""
    return DET.status_conexao()


class ComunicacaoTextoIn(BaseModel):
    texto: str


@router.post("/comunicacao")
async def ingerir_texto(
    payload: ComunicacaoTextoIn,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Ingere uma comunicação do DET (texto colado) e a trata automaticamente."""
    res = await DET.processar_comunicacao(
        db, texto=payload.texto, origem="ingestao_assistida",
        user_id=str(getattr(current_user, "id", None)))
    if not res.get("ok"):
        raise HTTPException(status_code=422, detail=res.get("mensagem", "Falha ao processar"))
    return res


@router.post("/comunicacao/upload")
async def ingerir_upload(
    arquivo: UploadFile = File(...),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Ingere a comunicação do DET a partir do PDF baixado do portal."""
    data = await arquivo.read()
    texto = PS.extrair_texto_pdf(data) if (arquivo.filename or "").lower().endswith(".pdf") else data.decode("utf-8", "ignore")
    if len(texto.strip()) < 30:
        raise HTTPException(status_code=422, detail="Não foi possível extrair texto do arquivo.")
    res = await DET.processar_comunicacao(
        db, texto=texto, origem="ingestao_assistida",
        user_id=str(getattr(current_user, "id", None)))
    if not res.get("ok"):
        raise HTTPException(status_code=422, detail=res.get("mensagem", "Falha ao processar"))
    return res


@router.get("/comunicacoes")
async def listar(
    limit: int = 50,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return {"comunicacoes": await DET.listar_comunicacoes(db, limit=limit)}


import os as _os2  # noqa: E402

from fastapi import Header  # noqa: E402

_DET_ROBO_TOKEN = _os2.environ.get("DET_ROBO_TOKEN", "conecta-det-robo-2026")


@router.post("/ingest-robo")
async def ingest_robo(
    payload: dict,
    x_robo_token: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
):
    """Endpoint INTERNO — o robô empurra as mensagens lidas do DET (auto-coleta periódica).

    Sem auth de usuário (rede interna), protegido por token compartilhado.
    """
    if x_robo_token != _DET_ROBO_TOKEN:
        raise HTTPException(status_code=403, detail="token inválido")
    novos = await DET.registrar_do_robo(db, payload.get("mensagens") or [])
    await db.commit()
    return {"ok": True, "registradas": novos}


@router.post("/coletar")
async def coletar(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Dispara a coleta automática (estado honesto enquanto gov.br OAuth não habilitado)."""
    return await DET.coletar_automatico(db)


# ── Robô Playwright (login supervisionado via noVNC + coleta headless) ────────
import os as _os

import httpx as _httpx

ROBOT_URL = _os.environ.get("DET_ROBOT_URL", "http://conecta-pro-det-robot:8099")
NOVNC_URL = "/det-vnc/vnc.html?autoconnect=1&resize=scale&path=det-vnc/websockify"


@router.post("/robo/login")
async def robo_login(current_user=Depends(get_current_active_user)):
    """Inicia o login supervisionado do robô (sobe o navegador no noVNC)."""
    try:
        async with _httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{ROBOT_URL}/login/iniciar")
            data = r.json()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": f"Robô indisponível: {e}"}
    data["novnc_url"] = NOVNC_URL
    return data


@router.get("/robo/status")
async def robo_status(current_user=Depends(get_current_active_user)):
    """Status do robô (logado? sessão salva?)."""
    try:
        async with _httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{ROBOT_URL}/login/status")
            return {**r.json(), "novnc_url": NOVNC_URL}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": f"Robô indisponível: {e}", "disponivel": False}


@router.post("/robo/coletar")
async def robo_coletar(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Coleta a caixa do DET (robô) e REGISTRA as mensagens no ERP."""
    try:
        async with _httpx.AsyncClient(timeout=180) as c:
            r = await c.post(f"{ROBOT_URL}/coletar")
            data = r.json()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": f"Robô indisponível: {e}"}
    novos = 0
    if data.get("ok") and data.get("mensagens"):
        try:
            novos = await DET.registrar_do_robo(db, data["mensagens"])
            await db.commit()
        except Exception as e:  # noqa: BLE001
            data["registro_erro"] = str(e)
    data["registradas_no_erp"] = novos
    return data
