"""
Controller de Gerenciamento de Acessos — Portal do Cliente.

Endpoints admin para provisionar, ativar/desativar e auditar acessos
de clientes ao portal.
"""

import logging
import secrets
import string
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from passlib.hash import bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/access-management", tags=["Portal - Gerenciamento Admin"])


def _generate_temp_password(length: int = 12) -> str:
    """Gera senha temporária segura com alta complexidade."""
    alpha = string.ascii_letters + string.digits + "!@#$%"
    while True:
        pw = "".join(secrets.choice(alpha) for _ in range(length))
        # Garantir pelo menos 1 maiúscula, 1 minúscula, 1 dígito, 1 especial
        if (
            any(c.isupper() for c in pw)
            and any(c.islower() for c in pw)
            and any(c.isdigit() for c in pw)
            and any(c in "!@#$%" for c in pw)
        ):
            return pw


@router.get("")
async def list_client_access(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista todos os clientes com status de acesso ao portal."""
    result = await db.execute(
        text(
            "SELECT c.id, c.name, c.cnpj, c.contact_email, "
            "c.portal_access_enabled, c.portal_username, "
            "c.created_at, "
            "(SELECT MAX(l.created_at) FROM portal_access_logs l WHERE l.client_id = c.id) AS ultimo_acesso "
            "FROM ged_clients c ORDER BY c.name"
        )
    )
    rows = result.mappings().all()
    return [
        {
            "client_id": str(r["id"]),
            "nome": r["name"],
            "cnpj": r["cnpj"] or "—",
            "email": r["contact_email"] or "—",
            "portal_ativo": r["portal_access_enabled"],
            "portal_username": r["portal_username"] or "—",
            "ultimo_acesso": r["ultimo_acesso"].isoformat() if r["ultimo_acesso"] else None,
            "data_criacao": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


@router.post("/{client_id}/provision")
async def provision_access(
    client_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Cria ou reseta acesso do cliente ao portal.

    Gera senha temporária segura e habilita acesso.
    A senha é retornada uma única vez — não é possível recuperá-la depois.
    """
    # Verificar se cliente existe
    result = await db.execute(
        text("SELECT id, name, cnpj FROM ged_clients WHERE id = :cid"),
        {"cid": client_id},
    )
    client = result.mappings().first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Gerar credenciais
    cnpj_clean = (client["cnpj"] or "").replace(".", "").replace("/", "").replace("-", "")
    username = cnpj_clean if cnpj_clean else f"client_{client_id[:8]}"
    temp_password = _generate_temp_password()
    password_hash = bcrypt.hash(temp_password)

    # Atualizar no banco
    await db.execute(
        text(
            "UPDATE ged_clients SET "
            "portal_access_enabled = true, "
            "portal_username = :username, "
            "portal_password_hash = :hash, "
            "updated_at = NOW() "
            "WHERE id = :cid"
        ),
        {"username": username, "hash": password_hash, "cid": client_id},
    )

    # Registrar log
    await db.execute(
        text(
            "INSERT INTO portal_access_logs (client_id, action, details, created_at) "
            "VALUES (:cid,'provision', :details, NOW())"
        ),
        {"cid": client_id, "action": "provision", "details": f"Acesso provisionado por admin. Username: {username}"},
    )
    await db.commit()

    logger.info("Portal provisionado para cliente %s (username: %s)", client["name"], username)

    return {
        "client_id": str(client["id"]),
        "nome": client["name"],
        "cnpj": client["cnpj"],
        "portal_username": username,
        "senha_temporaria": temp_password,
        "portal_url": "https://erp.conectamais.pro/area-cliente/login",
        "primeiro_acesso": True,
        "instrucoes": "Envie estas credenciais ao cliente. A senha é visível apenas neste momento.",
    }


@router.post("/{client_id}/toggle")
async def toggle_access(
    client_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Ativa ou desativa acesso do cliente ao portal."""
    result = await db.execute(
        text("SELECT id, name, portal_access_enabled FROM ged_clients WHERE id = :cid"),
        {"cid": client_id},
    )
    client = result.mappings().first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    new_status = not client["portal_access_enabled"]
    await db.execute(
        text("UPDATE ged_clients SET portal_access_enabled = :status, updated_at = NOW() WHERE id = :cid"),
        {"status": new_status, "cid": client_id},
    )

    action = "ativado" if new_status else "desativado"
    await db.execute(
        text(
            "INSERT INTO portal_access_logs (client_id, action, details, created_at) "
            "VALUES (:cid,:action, :details, NOW())"
        ),
        {"cid": client_id, "action": f"toggle_{action}", "details": f"Acesso {action} por admin"},
    )
    await db.commit()

    return {"client_id": client_id, "nome": client["name"], "portal_ativo": new_status, "acao": action}


@router.get("/{client_id}/logs")
async def access_logs(
    client_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Histórico de acessos e ações do portal de um cliente."""
    result = await db.execute(
        text(
            "SELECT id, action, details, ip_address, user_agent, created_at "
            "FROM portal_access_logs WHERE client_id = :cid "
            "ORDER BY created_at DESC LIMIT 50"
        ),
        {"cid": client_id},
    )
    rows = result.mappings().all()
    return {
        "client_id": client_id,
        "total": len(rows),
        "logs": [
            {
                "id": str(r["id"]),
                "acao": r["action"],
                "detalhes": r["details"],
                "ip": r["ip_address"],
                "dispositivo": r["user_agent"],
                "data": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
    }


@router.post("/{client_id}/preview-token")
async def generate_preview_token(
    client_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Gera token temporário de 15min para admin visualizar o portal como cliente."""
    result = await db.execute(
        text("SELECT id, name, cnpj FROM ged_clients WHERE id = :cid"),
        {"cid": client_id},
    )
    client = result.mappings().first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # JWT REAL do portal (igual ao login) p/ o admin visualizar como o cliente — 30 min.
    from datetime import UTC, datetime, timedelta
    from urllib.parse import quote
    from uuid import uuid4

    import jwt as pyjwt

    from modules.client_portal.services.auth_service import ALGORITHM, SECRET_KEY

    now = datetime.now(UTC)
    exp = now + timedelta(minutes=30)
    payload = {
        "sub": str(client_id),
        "username": client["cnpj"] or "preview",
        "type": "portal",
        "preview": True,
        "iat": now.timestamp(),
        "exp": exp.timestamp(),
        "jti": str(uuid4()),
    }
    preview_token = pyjwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    # sessão ativa (validate_token exige sessão ativa casando o token)
    await db.execute(
        text(
            "INSERT INTO client_portal_sessions (id, client_id, token, expires_at, is_active, created_at) "
            "VALUES (gen_random_uuid(), :cid, :token, :exp, true, NOW())"
        ),
        {"cid": client_id, "token": preview_token, "exp": exp},
    )
    await db.commit()

    nome = client["name"]
    return {
        "client_id": client_id,
        "nome": nome,
        "preview_url": f"https://erp.conectamais.pro/area-cliente/preview?t={preview_token}&n={quote(nome)}",
        "expira_em": "30 minutos",
        "aviso": "MODO PREVIEW — Você está visualizando como cliente",
    }


@router.post("/resumo-mensal/disparar", summary="Disparar resumo mensal (admin)")
async def disparar_resumo_mensal(
    current_user: CurrentActiveUser,
    client_id: str | None = None,
    competencia: str | None = None,
    enviar_email: bool = False,
    email_override: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Dispara o resumo mensal sob demanda: um cliente (com override de e-mail p/
    teste) ou todos. A caixa do portal recebe sempre; e-mail conforme flags."""
    from modules.client_portal.services import portal_resumo_service as rs

    if client_id:
        return await rs.enviar_resumo_cliente(
            db, client_id, competencia, enviar_email=enviar_email, email_override=email_override
        )
    return await rs.enviar_resumo_todos(db, competencia)


@router.post("/{client_id}/onboard", summary="Onboarding: provisiona + entrega credenciais")
async def onboard_cliente_endpoint(
    client_id: str,
    current_user: CurrentActiveUser,
    enviar_email: bool = True,
    email_override: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Provisiona/reseta o acesso e envia boas-vindas (só p/ e-mail real do síndico;
    alias interno → credenciais devolvidas p/ entrega manual)."""
    from modules.client_portal.services import portal_onboarding_service as ob

    return await ob.onboard_cliente(db, client_id, enviar_email=enviar_email, email_override=email_override)


@router.post("/onboard/nao-logados", summary="Onboarding em lote dos que nunca logaram")
async def onboard_nao_logados_endpoint(
    current_user: CurrentActiveUser,
    enviar_email: bool = True,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Provisiona e entrega credenciais a todos os clientes habilitados sem nenhum login."""
    from modules.client_portal.services import portal_onboarding_service as ob

    return await ob.onboard_nao_logados(db, enviar_email=enviar_email)
