"""
Controller — Puxador de guias do Drive (pacote mensal Portte/Onvio).

POST /fiscal/guias-drive/sync    → varre a pasta do Drive e sincroniza tudo
GET  /fiscal/guias-drive/status  → última visão do que há na pasta + processados

NOTA: sem `from __future__ import annotations` de propósito — ele transforma as
anotações em strings e, junto com CurrentActiveUser = Annotated["User", Depends(...)]
(forward-ref), o FastAPI perde o Depends e passa a exigir current_user como query (422).
"""

import json
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import text as _sqltext
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from core.auth.dependencies import CurrentActiveUser, get_current_user
from core.database.session import get_db

router = APIRouter(prefix="/guias-drive", tags=["Fiscal - Guias do Drive (Portte/Onvio)"])


def _localizar_pdf_guia(obligacao_id: str) -> tuple[str | None, str, str | None]:
    """Acha o PDF real da guia (cache local ou baixa do Drive por drive_file_id).
    Retorna (caminho, nome_arquivo, erro)."""
    import json
    import os

    from sqlalchemy import text as _sql

    from core.database.session import SyncSessionLocal
    from modules.fiscal_contabil.obrigacoes.guias_drive_service import GUIAS_STORAGE

    db = SyncSessionLocal()
    try:
        row = db.execute(
            _sql("SELECT tipo, nome, observacoes FROM fiscal_obligations WHERE id = :id"),
            {"id": obligacao_id},
        ).first()
    finally:
        db.close()
    if not row:
        return None, "", "obrigação não encontrada"
    try:
        obs = json.loads(row[2]) if row[2] and row[2].strip().startswith("{") else {}
    except Exception:  # noqa: BLE001
        obs = {}
    fid = obs.get("drive_file_id")
    nome = obs.get("arquivo") or f"{row[0] or 'guia'}.pdf"
    if not fid:
        return None, nome, "esta guia não tem PDF associado (não veio do Drive)"
    # 1) cache local (o puxador já baixou)
    for base, _dirs, files in os.walk(GUIAS_STORAGE):
        for f in files:
            if fid in f and f.lower().endswith(".pdf"):
                return os.path.join(base, f), nome, None
    # 2) baixa do Drive on-demand
    from modules.gdrive.services.gdrive_service import GDriveService

    svc = GDriveService()
    if not svc.esta_conectado():
        return None, nome, "Google Drive não conectado"
    dest = os.path.join(GUIAS_STORAGE, "_cache", f"{fid}__{nome}")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if not (os.path.exists(dest) or svc.baixar_arquivo(fid, dest)):
        return None, nome, "falha ao baixar o PDF do Drive"
    return dest, nome, None


@router.get("/pdf/{obligacao_id}", summary="Ver/baixar o PDF real da guia")
async def guia_pdf(
    obligacao_id: str,
    current_user: CurrentActiveUser,
    download: bool = Query(False, description="1 = força download; 0 = abre inline p/ visualizar"),
) -> Any:
    """Serve o PDF oficial da guia (o mesmo baixado do Drive). Inline p/ visualizar na tela,
    ?download=1 p/ baixar o arquivo."""
    caminho, nome, erro = await run_in_threadpool(_localizar_pdf_guia, obligacao_id)
    if erro:
        raise HTTPException(status_code=404, detail=erro)
    disp = "attachment" if download else "inline"
    return FileResponse(
        caminho, media_type="application/pdf",
        headers={"Content-Disposition": f'{disp}; filename="{nome}"'},
    )


def _localizar_pdf_onvio(fonte: str, guia_id: str) -> tuple[str | None, str, str | None]:
    """PDF real de uma guia FGTS/INSS puxada do Onvio (fgts_guias/inss_guias.arquivo_pdf).
    Read-only; o caminho vem do nosso puller (não de input do usuário), e mesmo assim é
    validado para ficar sob /app/uploads (anti-traversal). Retorna (caminho, nome, erro)."""
    import os

    from core.database.session import SyncSessionLocal

    tabela = {"fgts": "fgts_guias", "inss": "inss_guias"}.get(fonte)
    if not tabela:
        return None, "", "fonte inválida (use fgts ou inss)"
    db = SyncSessionLocal()
    try:
        row = db.execute(
            _sqltext(f"SELECT arquivo_pdf, coalesce(mes_ref, 'guia') FROM {tabela} WHERE id = :id"),
            {"id": guia_id},
        ).first()
    except Exception:  # noqa: BLE001 — id inválido (não-uuid) etc. → trata como não encontrado
        return None, "", "guia não encontrada"
    finally:
        db.close()
    if not row or not row[0]:
        return None, "", "guia não encontrada ou sem PDF"
    caminho = os.path.realpath(row[0])
    base = os.path.realpath("/app/uploads")
    if not caminho.startswith(base + os.sep) or not os.path.exists(caminho):
        return None, "", "arquivo da guia não encontrado no sistema"
    nome = f"guia_{fonte}_{(str(row[1]) or '').replace('/', '-').replace(' ', '')}.pdf"
    return caminho, nome, None


@router.get("/guia-onvio/{fonte}/{guia_id}/pdf", summary="PDF real da guia FGTS/INSS (Onvio)")
async def guia_onvio_pdf(
    fonte: str,
    guia_id: str,
    current_user: CurrentActiveUser,
    download: bool = Query(False, description="1 = força download; 0 = abre inline"),
) -> Any:
    """Serve o PDF da guia FGTS/INSS puxada do Onvio (arquivo_pdf em disco). Leitura."""
    caminho, nome, erro = await run_in_threadpool(_localizar_pdf_onvio, fonte, guia_id)
    if erro:
        raise HTTPException(status_code=404, detail=erro)
    disp = "attachment" if download else "inline"
    return FileResponse(
        caminho, media_type="application/pdf",
        headers={"Content-Disposition": f'{disp}; filename="{nome}"'},
    )


@router.post("/{obligacao_id}/preparar-pagamento", status_code=201, summary="Preparar pagamento da guia (gate OTP)")
async def preparar_pagamento_guia(
    obligacao_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Any:
    """Prepara o pagamento da guia via Banco Inter (status='preparado', SEM mover dinheiro).
    A saída de dinheiro SÓ ocorre depois de: gerar-otp → aprovar(OTP humano) → executar,
    no fluxo já existente /financeiro/inter/payments/{id}/*. Categoria 'imposto'."""
    from modules.integrations.inter.services.payment_service import InterPaymentService, PaymentError

    row = (await db.execute(_sqltext(
        "SELECT tipo, nome, competencia_mes, competencia_ano, valor_devido, "
        "observacoes, status FROM fiscal_obligations WHERE id = :id AND active = true"
    ), {"id": obligacao_id})).mappings().first()
    if not row:
        raise HTTPException(404, "guia não encontrada")
    if (row["status"] or "").lower() in ("cumprida", "paga", "pago"):
        raise HTTPException(409, "esta guia já consta como paga/cumprida")
    valor = float(row["valor_devido"] or 0)
    if valor <= 0:
        raise HTTPException(422, "guia sem valor a pagar")
    try:
        obs = json.loads(row["observacoes"]) if row["observacoes"] and row["observacoes"].strip().startswith("{") else {}
    except Exception:  # noqa: BLE001
        obs = {}
    barras = obs.get("codigo_barras")
    pix = obs.get("pix_copia_cola") or obs.get("pix_copia_e_cola")
    if barras:
        payment_type, destinatario = "boleto", {"codigo_barras": barras}
    elif pix:
        payment_type, destinatario = "pix", {"pix_copia_e_cola": pix}
    else:
        raise HTTPException(422, "esta guia não tem código de barras nem PIX — pague pelo PDF no app do banco")
    comp = f"{int(row['competencia_mes']):02d}/{row['competencia_ano']}" if row["competencia_mes"] else ""
    svc = InterPaymentService(db)
    try:
        res = await svc.preparar(
            payment_type=payment_type,
            destinatario=destinatario,
            valor=valor,
            data_pagamento=date.today(),
            prepared_by=str(current_user.id),
            observacoes=f"Guia fiscal {row['tipo']} {comp} — {row['nome']} | obrigacao={obligacao_id}",
            categoria="imposto",
        )
    except PaymentError as exc:
        raise HTTPException(400, str(exc)) from exc
    if isinstance(res, dict):
        res["obligacao_id"] = obligacao_id
        res["descricao"] = f"{row['nome']} — {comp}".strip(" —")
        res["payment_type"] = payment_type
    return res


@router.post("/sync", summary="Puxar guias/parcelamentos da pasta do Drive")
async def sync_guias(
    current_user: CurrentActiveUser,
    forcar: bool = Query(False, description="Reprocessa PDFs já sincronizados"),
) -> Any:
    """Baixa e classifica os PDFs do pacote mensal, atualizando fiscal_obligations."""
    from modules.fiscal_contabil.obrigacoes.guias_drive_service import sync_guias_drive

    return await run_in_threadpool(sync_guias_drive, forcar)


@router.get("/status", summary="Status da pasta de guias no Drive")
async def status_guias(current_user: CurrentActiveUser) -> Any:
    """Lista o que existe na pasta (sem baixar) e o que já foi processado."""
    from modules.fiscal_contabil.obrigacoes.guias_drive_service import GUIAS_DRIVE_ROOT
    from modules.gdrive.services.gdrive_service import GDriveService

    def _status() -> dict[str, Any]:
        svc = GDriveService()
        if not svc.esta_conectado():
            return {"ok": False, "erro": "Google Drive não conectado"}
        raiz = svc.listar_arquivos(GUIAS_DRIVE_ROOT)
        pastas = {}
        for p in raiz:
            if p.get("mimeType") == "application/vnd.google-apps.folder":
                pastas[p["name"]] = [
                    {"nome": a["name"], "modificado": a.get("modifiedTime")}
                    for a in svc.listar_arquivos(p["id"])
                    if a.get("mimeType") == "application/pdf"
                ]
        soltos = [f["name"] for f in raiz if f.get("mimeType") == "application/pdf"]
        return {"ok": True, "raiz": GUIAS_DRIVE_ROOT, "pastas": pastas, "pdfs_na_raiz": soltos}

    return await run_in_threadpool(_status)
