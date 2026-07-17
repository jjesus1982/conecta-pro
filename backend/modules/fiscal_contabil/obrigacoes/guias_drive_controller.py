"""
Controller — Puxador de guias do Drive (pacote mensal Portte/Onvio).

POST /fiscal/guias-drive/sync    → varre a pasta do Drive e sincroniza tudo
GET  /fiscal/guias-drive/status  → última visão do que há na pasta + processados

NOTA: sem `from __future__ import annotations` de propósito — ele transforma as
anotações em strings e, junto com CurrentActiveUser = Annotated["User", Depends(...)]
(forward-ref), o FastAPI perde o Depends e passa a exigir current_user como query (422).
"""

from typing import Any

from fastapi import APIRouter, Query
from starlette.concurrency import run_in_threadpool

from core.auth.dependencies import CurrentActiveUser

router = APIRouter(prefix="/guias-drive", tags=["Fiscal - Guias do Drive (Portte/Onvio)"])


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
