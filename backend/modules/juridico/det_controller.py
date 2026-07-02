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


@router.post("/coletar")
async def coletar(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Dispara a coleta automática (estado honesto enquanto gov.br OAuth não habilitado)."""
    return await DET.coletar_automatico(db)
