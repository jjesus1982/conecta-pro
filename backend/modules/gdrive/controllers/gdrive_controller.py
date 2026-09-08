"""
GDrive Controller — Operação Conecta-Drive
Endpoints para status, autorização OAuth2 e envio de kits ao Google Drive.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gdrive", tags=["GDrive - Operação Conecta-Drive"])


# ── HELPERS ────────────────────────────────────────────────────────────────────


def _drive_service(db: AsyncSession):
    """Instancia o GoogleDriveService com sessão assíncrona."""
    from modules.people_management.ged.services.google_drive_service import (
        GoogleDriveService,
    )

    return GoogleDriveService(db)


# ── STATUS ─────────────────────────────────────────────────────────────────────


@router.get("/status")
async def gdrive_status(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verifica se o Google Drive está conectado e retorna o status da integração."""
    from sqlalchemy import text as _sa_text

    # Primário: OAuth2 tokens no banco (gdrive_config)
    try:
        row = (
            (
                await db.execute(
                    _sa_text("SELECT owner_email, is_connected FROM gdrive_config WHERE is_connected = TRUE LIMIT 1")
                )
            )
            .mappings()
            .first()
        )
        if row:
            email = row["owner_email"] or ""
            return {
                "conectado": True,
                "email": email,
                "nome": email,
                "tipo": "oauth2",
                "credenciais_configuradas": True,
                "mensagem": f"Google Drive conectado via OAuth2 ({email})",
                "acao": None,
            }
    except Exception as exc:
        logger.warning("gdrive_status: erro ao ler gdrive_config: %s", exc)

    # Fallback: service account (arquivo JSON)
    svc = _drive_service(db)
    creds = await svc.check_credentials()
    return {
        "conectado": creds.get("configured", False),
        "email": None,
        "nome": None,
        "tipo": "service_account",
        "credenciais_configuradas": creds.get("credentials_file_exists", False),
        "mensagem": creds.get("message", ""),
        "acao": None if creds.get("configured") else "autorizar",
    }


# ── AUTORIZAR ──────────────────────────────────────────────────────────────────


@router.post("/kits/{client_id}/{competencia}/enviar-email")
async def enviar_kit_email(
    client_id: str,
    competencia: str,
    destinatario: str | None = None,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    body: dict | None = Body(None),
):
    """
    Enviar kit por e-mail.
    Link para kits > 10MB, anexos para menores.
    08/09/2026: o redesign manda `destinatario` no corpo JSON — aceita query e corpo.
    """
    from modules.gdrive.services.email_kit_service import email_kit_service

    if not destinatario and isinstance(body, dict):
        destinatario = (body.get("destinatario") or "").strip() or None
    resultado = email_kit_service.enviar_kit_por_email(
        client_id=client_id,
        competencia=competencia,
        destinatario_override=destinatario,
    )

    # G2: Atualizar sent_at após envio bem-sucedido
    if resultado.get("sucesso"):
        await db.execute(
            text(
                "UPDATE ged_document_kits "
                "SET sent_at = NOW(), sent_method = 'email', sent_to = :email "
                "WHERE client_id = :client_id "
                "AND DATE_TRUNC('month', reference_month) = "
                "DATE_TRUNC('month', :competencia::date)"
            ),
            {
                "client_id": client_id,
                "competencia": f"{competencia}-01",
                "email": resultado.get("destinatario", ""),
            },
        )
        await db.commit()

    return resultado


@router.post("/kits/{client_id}/{competencia}/montar")
async def montar_kit_drive(
    client_id: str,
    competencia: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Montar kit completo no Google Drive.
    Cria pastas, faz upload de cada documento, gera link compartilhável.
    """
    from sqlalchemy import text as sa_text

    from modules.gdrive.services.kit_drive_service import kit_drive_service

    row = (
        (
            await db.execute(
                sa_text("SELECT tipo_kit FROM gedeon_kit_config WHERE client_id::text = :cid LIMIT 1"),
                {"cid": client_id},
            )
        )
        .mappings()
        .first()
    )
    tipo_kit = row["tipo_kit"] if row else "maos_de_obra"
    resultado = await kit_drive_service.montar_kit_no_drive(client_id, competencia, tipo_kit)
    return resultado


@router.get("/portal/{client_id}/kits")
async def portal_kits_cliente(
    client_id: str,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Kits do cliente para exibir no portal.
    Autenticacao por token de sessao do portal (client_portal_sessions).
    Retorna historico dos ultimos 24 meses com share_link do Drive.
    """

    # Validar token do portal
    try:
        r_token = await db.execute(
            text(
                "SELECT client_id FROM client_portal_sessions "
                "WHERE token = :token "
                "AND expires_at > NOW() "
                "AND client_id::text = :client_id "
                "LIMIT 1"
            ),
            {"token": token, "client_id": client_id},
        )
        valid = r_token.scalar_one_or_none()
    except Exception:
        valid = None
    if not valid:
        raise HTTPException(status_code=401, detail="Token invalido ou expirado")

    rows = await db.execute(
        text(
            "SELECT competencia, total_docs, share_link, status, created_at::text "
            "FROM gdrive_kits "
            "WHERE client_id = :client_id "
            "AND status = 'concluido' "
            "ORDER BY competencia DESC "
            "LIMIT 24"
        ),
        {"client_id": client_id},
    )

    kits = []
    for row in rows.fetchall():
        competencia, total_docs, share_link, status, criado_em = row
        if share_link:
            kits.append(
                {
                    "competencia": competencia,
                    "total_docs": int(total_docs or 0),
                    "share_link": share_link,
                    "status": status or "concluido",
                    "criado_em": criado_em or "",
                }
            )

    return {"total": len(kits), "kits": kits}


# ── OAUTH2 ─────────────────────────────────────────────────────────────────────


import json as _json  # noqa: E402

from fastapi.responses import RedirectResponse as _Redirect  # noqa: E402
from sqlalchemy import text as _text  # noqa: E402

from core.database import get_session as _get_session  # noqa: E402
from modules.gdrive.services.gdrive_service import gdrive_service as _gdrive  # noqa: E402


@router.get("/oauth/callback")
async def gdrive_oauth_callback(
    code: str | None = None,
    db: AsyncSession = Depends(_get_session),
    state: str | None = None,
    error: str | None = None,
) -> _Redirect:
    """Callback OAuth2 — recebe código, troca por tokens e salva no banco."""
    base = "https://erp.conectamais.pro/modulos/gestao-pessoas/ged/configuracoes"
    if error or not code:
        logger.error("GDrive OAuth erro: %s", error)
        return _Redirect(url=f"{base}?gdrive=erro")
    try:
        tokens = _gdrive.trocar_codigo_por_token(code)
        at = tokens["access_token"]
        rt = tokens.get("refresh_token") or ""
        import os as _os
        from datetime import datetime as _dt

        # asyncpg exige datetime, não string ISO — converter antes do INSERT
        _exp_raw = tokens.get("expiry")
        if isinstance(_exp_raw, str):
            try:
                exp: _dt | None = _dt.fromisoformat(_exp_raw)
            except ValueError:
                exp = None
        elif isinstance(_exp_raw, _dt):
            exp = _exp_raw
        else:
            exp = None

        await db.execute(_text("DELETE FROM gdrive_config"))
        await db.execute(
            _text(
                "INSERT INTO gdrive_config "
                "(owner_email, access_token, refresh_token, token_expiry, "
                "is_connected, scopes, root_folder_id, kits_folder_id) "
                "VALUES (:email, :at, :rt, :exp, TRUE, :scopes, :root, :kits)"
            ),
            {
                "email": _os.environ.get("GDRIVE_OWNER_EMAIL", "jordansjesus@gmail.com"),
                "at": at,
                "rt": rt,
                "exp": exp,
                "scopes": _json.dumps(tokens.get("scopes", [])),
                "root": _os.environ.get("GDRIVE_ROOT_FOLDER_ID", ""),
                "kits": _os.environ.get("GDRIVE_KITS_FOLDER_ID", ""),
            },
        )
        await db.commit()
        _gdrive.conectar_com_tokens(at, rt, exp)
        logger.info("GDrive: OAuth2 concluído — tokens salvos")
        return _Redirect(url=f"{base}?gdrive=conectado")
    except Exception as exc:
        logger.error("GDrive callback erro: %s", exc, exc_info=True)
        return _Redirect(url=f"{base}?gdrive=erro")


@router.post("/desconectar")
async def gdrive_desconectar(
    db: AsyncSession = Depends(_get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Desconectar o Google Drive e limpar tokens do banco."""
    try:
        await db.execute(
            _text(
                "UPDATE gdrive_config SET is_connected = FALSE, "
                "access_token = NULL, refresh_token = NULL, updated_at = NOW()"
            )
        )
        await db.commit()
        _gdrive._service = None
        _gdrive._initialized = False
        return {"status": "desconectado"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/autorizar")
async def gdrive_autorizar_get(
    _user: dict = Depends(get_current_user),
) -> dict:
    """GET — gerar URL OAuth2 para autorizar o Google Drive via navegador."""
    from modules.gdrive.services.gdrive_service import gdrive_service as _gds

    try:
        url = _gds.gerar_url_autorizacao()
        return {"url_autorizacao": url, "instrucao": "Acesse a URL para autorizar"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar URL: {exc}")
