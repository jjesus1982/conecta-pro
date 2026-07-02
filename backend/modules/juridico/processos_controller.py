"""Processos & Defesa — o Escritório Jurídico IA recebe um processo, investiga o ERP
inteiro e monta a análise de defesa fundamentada no dado real.

Endpoints:
  POST /juridico/processos            (JSON: texto colado do processo)
  POST /juridico/processos/upload     (multipart: PDF do processo)
  GET  /juridico/processos            (lista)
  GET  /juridico/processos/{id}       (detalhe)
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db

from modules.juridico import processos_service as PS

router = APIRouter(prefix="/juridico/processos", tags=["Jurídico - Processos & Defesa"])


class ProcessoTextoIn(BaseModel):
    texto: str
    numero: str | None = None
    tipo: str | None = "trabalhista"
    employee_id: str | None = None  # opcional: força o sujeito quando o nome for ambíguo


@router.post("")
async def analisar_por_texto(
    payload: ProcessoTextoIn,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Analisa um processo a partir do texto colado."""
    res = await PS.analisar_processo(
        db, texto=payload.texto, numero=payload.numero, tipo=payload.tipo,
        user_id=str(getattr(current_user, "id", None)), employee_hint=payload.employee_id,
    )
    if not res.get("ok"):
        raise HTTPException(status_code=422, detail=res.get("mensagem", "Falha na análise"))
    return res


@router.post("/upload")
async def analisar_por_upload(
    arquivo: UploadFile = File(...),
    numero: str | None = Form(None),
    tipo: str | None = Form("trabalhista"),
    employee_id: str | None = Form(None),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Analisa um processo a partir do PDF enviado (extrai o texto e investiga o ERP)."""
    data = await arquivo.read()
    texto = PS.extrair_texto_pdf(data) if (arquivo.filename or "").lower().endswith(".pdf") else data.decode("utf-8", "ignore")
    if len(texto.strip()) < 40 and not employee_id:
        raise HTTPException(status_code=422, detail="Não foi possível extrair texto do arquivo (PDF pode ser imagem/escaneado sem OCR).")
    res = await PS.analisar_processo(
        db, texto=texto, numero=numero, tipo=tipo,
        user_id=str(getattr(current_user, "id", None)), employee_hint=employee_id,
    )
    if not res.get("ok"):
        raise HTTPException(status_code=422, detail=res.get("mensagem", "Falha na análise"))
    return res


@router.get("")
async def listar(
    limit: int = 50,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return {"processos": await PS.listar_processos(db, limit=limit)}


@router.get("/{id}")
async def obter(
    id: str,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    p = await PS.obter_processo(db, id)
    if not p:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    return p


class EnvioCQBIn(BaseModel):
    confirmar: bool = False
    destinatario: str | None = None  # default: contato@cqbadvogados.com.br


@router.post("/{id}/enviar-cqb")
async def enviar_cqb(
    id: str,
    payload: EnvioCQBIn,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Encaminha o processo (dossiê + defesa) ao CQB Advogados por e-mail.

    confirmar=false → prévia (não envia). confirmar=true → envia de fato
    (remetente noreply@conectamais.pro, destino contato@cqbadvogados.com.br).
    """
    res = await PS.preparar_ou_enviar_cqb(db, id, confirmar=payload.confirmar, destinatario=payload.destinatario)
    if not res.get("ok"):
        raise HTTPException(status_code=422, detail=res.get("mensagem", "Falha no encaminhamento"))
    return res
