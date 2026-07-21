"""Ativação do Ponto — painel + DISPARO do link de primeiro acesso (RH/DP).

Os 50 CLT nunca logaram. Esta tela mostra o status de ativação de cada um e permite
DISPARAR o link `/primeiro-acesso` por e-mail (todos têm) e WhatsApp (os que têm telefone).
O link é o mesmo p/ todos (o CPF identifica). `dry_run=true` só mostra os alvos, não envia.

Segurança: envio a pessoas reais = ação do Jordan (o botão). Read-only lista; POST envia.
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_active_user
from core.config import settings
from core.database.session import get_sync_db_dependency
from core.models import User

router = APIRouter(prefix="/ativacao-ponto", tags=["RH - Ativação do Ponto"])

_COHORT = (
    "status='ativo' AND coalesce(is_homologacao,false)=false "
    "AND (tipo_contrato='clt' OR tipo_contrato IS NULL) AND (tipo_contrato IS DISTINCT FROM 'pj')"
)


def _link() -> str:
    base = (getattr(settings, "FRONTEND_URL", None) or "https://erp.conectamais.pro").rstrip("/")
    return f"{base}/primeiro-acesso"


def _e164(tel: str | None) -> str | None:
    d = re.sub(r"\D", "", tel or "")
    if not d:
        return None
    if d.startswith("55") and len(d) >= 12:
        return d
    if len(d) in (10, 11):
        return "55" + d
    return d if len(d) >= 12 else None


def _primeiro_nome(nome: str | None) -> str:
    return (nome or "").strip().split(" ")[0].title() if nome else "colega"


def _msg_texto(nome: str, link: str) -> str:
    return (
        f"📲 *Conecta PRO — Ponto pelo celular*\n\n"
        f"Olá, {_primeiro_nome(nome)}! Agora o ponto é registrado pelo nosso sistema. "
        f"Faça seu primeiro acesso:\n\n👉 {link}\n\n"
        f"São 3 passos: 1) CPF  2) Complete seu cadastro  3) Cadastre seu rosto.\n"
        f"Sua senha é o seu próprio CPF. Não sabe o PIS? Pode deixar em branco.\n"
        f"Qualquer dúvida, chame o RH. 🙏"
    )


def _msg_html(nome: str, link: str) -> str:
    return (
        f"<div style='font-family:Arial,sans-serif;font-size:15px;color:#1e293b'>"
        f"<p>Olá, <b>{_primeiro_nome(nome)}</b>!</p>"
        f"<p>Agora o ponto é registrado pelo nosso sistema, o <b>Conecta PRO</b>. "
        f"Faça seu primeiro acesso pelo celular:</p>"
        f"<p><a href='{link}' style='background:#F26522;color:#fff;padding:12px 20px;"
        f"border-radius:10px;text-decoration:none;font-weight:bold'>Fazer meu primeiro acesso</a></p>"
        f"<p style='font-size:13px;color:#64748b'>ou acesse: {link}</p>"
        f"<p><b>3 passos:</b> 1) CPF · 2) Complete seu cadastro · 3) Cadastre seu rosto.<br>"
        f"Sua senha é o seu próprio CPF. Não sabe o PIS? Pode deixar em branco.</p>"
        f"<p style='font-size:13px;color:#64748b'>Qualquer dúvida, chame o RH.</p></div>"
    )


@router.get("")
def listar(
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Lista os 50 CLT com status de ativação + canais disponíveis."""
    rows = db.execute(
        text(
            f"SELECT CAST(id AS TEXT) AS id, nome, email, "
            f"  nullif(trim(coalesce(celular, telefone)),'') AS fone, "
            f"  (face_descriptor IS NOT NULL) AS tem_rosto, "
            f"  ponto_convite_enviado_em, posto_atual_nome "
            f"FROM employees WHERE {_COHORT} ORDER BY nome"
        )
    ).mappings().all()
    itens = []
    n_ativados = n_pendentes = 0
    for r in rows:
        ativado = bool(r["tem_rosto"])
        n_ativados += 1 if ativado else 0
        n_pendentes += 0 if ativado else 1
        itens.append({
            "id": r["id"], "nome": r["nome"], "posto": r["posto_atual_nome"],
            "email": r["email"], "tem_email": bool(r["email"]),
            "tem_whatsapp": bool(_e164(r["fone"])),
            "ativado": ativado,
            "status": "Ativado" if ativado else "Pendente",
            "convite_enviado_em": r["ponto_convite_enviado_em"].isoformat() if r["ponto_convite_enviado_em"] else None,
        })
    return {
        "link": _link(),
        "total": len(itens), "ativados": n_ativados, "pendentes": n_pendentes,
        "funcionarios": itens,
    }


class DispararBody(BaseModel):
    employee_ids: list[str] | None = None   # None = todos os PENDENTES
    canais: list[str] = ["email", "whatsapp"]
    dry_run: bool = False


async def _disparar(db: Session, ids: list[str] | None, canais: list[str], dry_run: bool) -> dict[str, Any]:
    link = _link()
    cond = _COHORT
    params: dict[str, Any] = {}
    if ids:
        cond += " AND CAST(id AS TEXT) = ANY(:ids)"
        params["ids"] = ids
    else:
        cond += " AND face_descriptor IS NULL"  # padrão: só os pendentes
    rows = db.execute(
        text(f"SELECT CAST(id AS TEXT) AS id, nome, email, nullif(trim(coalesce(celular,telefone)),'') AS fone "
             f"FROM employees WHERE {cond} ORDER BY nome"),
        params,
    ).mappings().all()

    from core.mailer import send_email
    from modules.integrations.connectors.whatsapp.service import send_text_message

    resultados = []
    for r in rows:
        alvo = {"id": r["id"], "nome": r["nome"], "email": None, "whatsapp": None}
        fone = _e164(r["fone"])
        if "email" in canais and r["email"]:
            alvo["email"] = r["email"]
            if not dry_run:
                try:
                    ok = await send_email(r["email"], "Conecta PRO — Seu primeiro acesso ao ponto", _msg_html(r["nome"], link))
                    alvo["email_ok"] = bool(ok)
                except Exception as e:  # noqa: BLE001
                    alvo["email_ok"] = False
                    alvo["email_erro"] = str(e)[:120]
        if "whatsapp" in canais and fone:
            alvo["whatsapp"] = fone
            if not dry_run:
                try:
                    await send_text_message(fone, _msg_texto(r["nome"], link))
                    alvo["whatsapp_ok"] = True
                except Exception as e:  # noqa: BLE001
                    alvo["whatsapp_ok"] = False
                    alvo["whatsapp_erro"] = str(e)[:120]
        if not dry_run and (alvo["email"] or alvo["whatsapp"]):
            db.execute(text("UPDATE employees SET ponto_convite_enviado_em=now() WHERE CAST(id AS TEXT)=:i"), {"i": r["id"]})
        resultados.append(alvo)
    if not dry_run:
        db.commit()
    return {
        "dry_run": dry_run, "link": link, "total": len(resultados),
        "com_email": sum(1 for a in resultados if a["email"]),
        "com_whatsapp": sum(1 for a in resultados if a["whatsapp"]),
        "resultados": resultados,
    }


@router.post("/disparar")
async def disparar(
    body: DispararBody,
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Dispara o link de primeiro acesso (e-mail + WhatsApp). `dry_run=true` só simula."""
    if not body.canais:
        raise HTTPException(status_code=422, detail="Escolha ao menos um canal (email/whatsapp).")
    return await _disparar(db, body.employee_ids, body.canais, body.dry_run)


@router.post("/{employee_id}/reenviar")
async def reenviar(
    employee_id: str,
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Reenvia o link a UMA pessoa (cobrar quem ainda não fez)."""
    return await _disparar(db, [employee_id], ["email", "whatsapp"], dry_run=False)


@router.get("/monitor")
def monitor(
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Painel AO VIVO do rollout: adesão (ativação/rosto/contingência), batidas de hoje
    e feed das últimas atividades. Tudo é FATO no banco (nunca estimado)."""
    hoje = "(now() AT TIME ZONE 'America/Manaus')::date"
    a = db.execute(text(
        f"SELECT count(*) AS total, "
        f"  count(*) FILTER (WHERE face_descriptor IS NOT NULL) AS com_rosto, "
        f"  count(*) FILTER (WHERE primeiro_acesso_em IS NOT NULL) AS primeiro_acesso, "
        f"  count(*) FILTER (WHERE primeiro_acesso_em IS NOT NULL AND face_descriptor IS NULL) AS rosto_pendente, "
        f"  count(*) FILTER (WHERE primeiro_acesso_em::date = {hoje}) AS ativados_hoje "
        f"FROM employees WHERE {_COHORT}"
    )).mappings().first()
    ativacao = dict(a)
    ativacao["pendentes"] = int(ativacao["total"]) - int(ativacao["primeiro_acesso"])

    b = db.execute(text(
        f"SELECT count(*) AS total, count(DISTINCT employee_id) AS funcionarios, "
        f"  count(*) FILTER (WHERE device_type = 'contingencia') AS contingencia, "
        f"  count(*) FILTER (WHERE status = 'pending_contingencia') AS pendente_validar, "
        f"  count(*) FILTER (WHERE lower(coalesce(punch_type,'')) LIKE 'entrada%') AS entradas, "
        f"  count(*) FILTER (WHERE lower(coalesce(punch_type,'')) LIKE 'saida%' OR lower(coalesce(punch_type,'')) LIKE 'saída%') AS saidas "
        f"FROM gp_clock_punches WHERE punch_timestamp::date = {hoje} "
        f"  AND employee_id IN (SELECT id FROM employees WHERE {_COHORT})"
    )).mappings().first()

    feed = db.execute(text(
        f"SELECT e.nome, p.punch_type, p.device_type, p.status, "
        f"  to_char(p.punch_timestamp, 'HH24:MI') AS hora "
        f"FROM gp_clock_punches p JOIN employees e ON e.id = p.employee_id "
        f"WHERE p.punch_timestamp::date = {hoje} "
        f"  AND p.employee_id IN (SELECT id FROM employees WHERE {_COHORT}) "
        f"ORDER BY p.punch_timestamp DESC LIMIT 15"
    )).mappings().all()

    agora = db.execute(text("SELECT to_char(now() AT TIME ZONE 'America/Manaus', 'HH24:MI:SS')")).scalar()
    return {
        "ativacao": ativacao,
        "batidas_hoje": dict(b),
        "feed": [dict(x) for x in feed],
        "atualizado_em": agora,
    }
