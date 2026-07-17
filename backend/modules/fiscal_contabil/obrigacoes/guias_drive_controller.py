"""
Controller — Puxador de guias do Drive (pacote mensal Portte/Onvio).

POST /fiscal/guias-drive/sync    → varre a pasta do Drive e sincroniza tudo
GET  /fiscal/guias-drive/status  → última visão do que há na pasta + processados

NOTA: sem `from __future__ import annotations` de propósito — ele transforma as
anotações em strings e, junto com CurrentActiveUser = Annotated["User", Depends(...)]
(forward-ref), o FastAPI perde o Depends e passa a exigir current_user como query (422).
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from core.auth.dependencies import CurrentActiveUser

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
