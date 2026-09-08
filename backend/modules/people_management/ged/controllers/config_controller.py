"""
GED Config Controller — endpoints de configuração do módulo GED.
Usado pela página configuracoes/page.tsx.
"""

import logging
import os

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["GED - Configurações"])

CREDENTIALS_PATH = os.environ.get(
    "GOOGLE_DRIVE_CREDENTIALS",
    "/opt/conecta-pro/config/google_drive_credentials.json",
)


_AGENDAMENTO_PADRAO = {"enabled": False, "cron_expression": "0 8 5 * *", "description": "Todo dia 5 às 08h", "last_run": None}



@router.get("/drive")
async def get_drive_config(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retorna configuração atual do Google Drive."""
    from modules.people_management.ged.services.google_drive_service import (
        GoogleDriveService,
    )

    svc = GoogleDriveService(db)
    creds = await svc.check_credentials()
    return {
        "connected": creds.get("configured", False),
        "folder_id": "",
        "email": "",
        "credentials_file_exists": creds.get("credentials_file_exists", False),
        "message": creds.get("message", ""),
    }


@router.post("/drive")
async def save_drive_config(
    current_user=Depends(get_current_user),
):
    """Salva configuração do Drive — NUNCA gravou nada (revisão 08/09/2026); 410 até existir persistência."""
    from fastapi import HTTPException

    raise HTTPException(status_code=410, detail="Configuração do Drive não é persistida por aqui; a conexão é por credencial no servidor.")


@router.post("/drive/connect")
async def connect_drive(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Inicia conexão com Google Drive."""
    from modules.people_management.ged.services.google_drive_service import (
        GoogleDriveService,
    )

    svc = GoogleDriveService(db)
    creds = await svc.check_credentials()
    if creds.get("configured"):
        return {"connected": True, "message": "Google Drive já conectado"}
    return {
        "connected": False,
        "message": ("Faça upload das credenciais em /opt/conecta-pro/config/google_drive_credentials.json"),
        "url_autorizacao": "/modulos/gestao-pessoas/ged/configuracoes",
    }


@router.delete("/drive/disconnect")
async def disconnect_drive(
    current_user=Depends(get_current_user),
):
    """Desconecta o Google Drive (renomeia a credencial). Diz a verdade quando não há o que desconectar."""
    if os.path.exists(CREDENTIALS_PATH):
        try:
            os.rename(CREDENTIALS_PATH, CREDENTIALS_PATH + ".bak")
            return {"disconnected": True}
        except OSError as exc:
            return {"disconnected": False, "message": f"Não consegui renomear a credencial: {exc}"}
    return {"disconnected": False, "message": f"Nenhuma credencial em {CREDENTIALS_PATH} neste servidor — nada a desconectar."}


async def _ler_agendamento(db: AsyncSession) -> dict:
    import json as _json

    from sqlalchemy import text as _t

    row = (await db.execute(_t("SELECT valor FROM system_configs WHERE chave = 'ged.agendamento'"))).first()
    if not row or not row[0]:
        return dict(_AGENDAMENTO_PADRAO)
    try:
        return {**_AGENDAMENTO_PADRAO, **_json.loads(row[0])}
    except (TypeError, ValueError):
        return dict(_AGENDAMENTO_PADRAO)


async def _gravar_agendamento(db: AsyncSession, dados: dict) -> dict:
    import json as _json

    from sqlalchemy import text as _t

    atual = await _ler_agendamento(db)
    novo = {**atual, **{k: v for k, v in dados.items() if k in _AGENDAMENTO_PADRAO}}
    await db.execute(_t(
        "INSERT INTO system_configs (id, chave, nome, valor, scope, valor_type, priority, cache_ttl_seconds, ativo, created_at, updated_at) "
        "VALUES (gen_random_uuid(), 'ged.agendamento', 'GED · agendamento do envio', :v, 'global', 'json', 'normal', 0, true, now(), now()) "
        "ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, updated_at = now()"), {"v": _json.dumps(novo)})
    await db.commit()
    return novo


@router.get("/schedule")
async def get_schedule(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retorna configuração de agendamento automático — persistida em system_configs (chave ged.agendamento).
    Era um literal fixo enquanto o POST dizia 'salvo' sem gravar (revisão 08/09/2026)."""
    return await _ler_agendamento(db)


@router.post("/schedule")
async def save_schedule(
    payload: dict = Body(default={}),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Salva configuração de agendamento (enabled, cron_expression, description) em system_configs."""
    novo = await _gravar_agendamento(db, payload or {})
    return {"ok": True, "message": "Agendamento salvo", **novo}
