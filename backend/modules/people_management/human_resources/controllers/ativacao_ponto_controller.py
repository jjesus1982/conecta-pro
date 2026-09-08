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


def _base_url() -> str:
    return (getattr(settings, "FRONTEND_URL", None) or "https://erp.conectamais.pro").rstrip("/")


def _link() -> str:
    return f"{_base_url()}/primeiro-acesso"


def _link_login() -> str:
    return f"{_base_url()}/login"


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


# 🔴 QUEM JA TEM CONTA NAO PODE RECEBER O TEXTO DE PRIMEIRO ACESSO.
# Em 23/08/2026 a Erika e a Kelly receberam "faca seu primeiro acesso: 1) CPF ... 3) cadastre
# seu rosto" — e as duas ja tinham conta E rosto desde 21/07 e 12/08. Pior: a tela de /login
# pede E-MAIL e senha, e a mensagem nao dizia o e-mail em lugar nenhum. Elas cairiam no login
# sem saber o que digitar.
#
# E ha uma armadilha a mais: 20 funcionarios ativos tem DUAS contas — a pessoal (ativa) e uma
# @conectamais.pro (INATIVA, sobra da carga inicial). Quem tentar a corporativa nao entra.
# Por isso a mensagem diz o e-mail exato da conta ativa, nao "seu e-mail".


def _msg_login_texto(nome: str, email: str, link: str) -> str:
    return (
        f"✅ *Conecta PRO — sua conta já está pronta*\n\n"
        f"Olá, {_primeiro_nome(nome)}! Você *não* precisa fazer o primeiro acesso nem "
        f"cadastrar o rosto de novo.\n\nEntre direto por aqui:\n👉 {link}\n\n"
        f"*E-mail:* {email}\n"
        f"*Senha:* seu CPF, só os números (sem ponto e sem traço)\n\n"
        f"Depois de entrar, o ponto fica em *Meu Espaço*.\n"
        f"Qualquer dúvida, chame o RH. 🙏"
    )


def _msg_login_html(nome: str, email: str, link: str) -> str:
    return (
        f"<div style='font-family:Arial,sans-serif;font-size:15px;color:#1e293b'>"
        f"<p>Olá, <b>{_primeiro_nome(nome)}</b>!</p>"
        f"<p>Você <b>não</b> precisa fazer o primeiro acesso nem cadastrar o rosto de novo — "
        f"sua conta já está pronta.</p>"
        f"<p><a href='{link}' style='background:#F26522;color:#fff;padding:12px 20px;"
        f"border-radius:10px;text-decoration:none;font-weight:bold'>Entrar no Conecta PRO</a></p>"
        f"<p style='font-size:13px;color:#64748b'>ou acesse: {link}</p>"
        f"<table style='border-collapse:collapse;margin:14px 0'>"
        f"<tr><td style='padding:6px 14px 6px 0;color:#64748b'>E-mail</td><td><b>{email}</b></td></tr>"
        f"<tr><td style='padding:6px 14px 6px 0;color:#64748b'>Senha</td>"
        f"<td><b>seu CPF, só os números</b> (sem ponto e sem traço)</td></tr></table>"
        f"<p>Depois de entrar, o ponto fica em <b>Meu Espaço</b>.</p>"
        f"<p style='font-size:13px;color:#64748b'>Qualquer dúvida, chame o RH.</p></div>"
    )


@router.get("")
def listar(
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Lista os 50 CLT com status de ativação + canais disponíveis."""
    rows = (
        db.execute(
            text(
                f"SELECT CAST(id AS TEXT) AS id, nome, email, "
                f"  nullif(trim(coalesce(celular, telefone)),'') AS fone, "
                f"  (face_descriptor IS NOT NULL) AS tem_rosto, "
                f"  ponto_convite_enviado_em, posto_atual_nome "
                f"FROM employees WHERE {_COHORT} ORDER BY nome"
            )
        )
        .mappings()
        .all()
    )
    itens = []
    n_ativados = n_pendentes = 0
    for r in rows:
        ativado = bool(r["tem_rosto"])
        n_ativados += 1 if ativado else 0
        n_pendentes += 0 if ativado else 1
        itens.append(
            {
                "id": r["id"],
                "nome": r["nome"],
                "posto": r["posto_atual_nome"],
                "email": r["email"],
                "tem_email": bool(r["email"]),
                "tem_whatsapp": bool(_e164(r["fone"])),
                "ativado": ativado,
                "status": "Ativado" if ativado else "Pendente",
                "convite_enviado_em": r["ponto_convite_enviado_em"].isoformat()
                if r["ponto_convite_enviado_em"]
                else None,
            }
        )
    return {
        "link": _link(),
        "total": len(itens),
        "ativados": n_ativados,
        "pendentes": n_pendentes,
        "funcionarios": itens,
    }


class DispararBody(BaseModel):
    employee_ids: list[str] | None = None  # None = todos os PENDENTES
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
    rows = (
        db.execute(
            text(
                f"SELECT CAST(id AS TEXT) AS id, nome, email, "
                f"  nullif(trim(coalesce(celular,telefone)),'') AS fone, "
                f"  (face_descriptor IS NOT NULL) AS tem_rosto, "
                # e-mail da conta ATIVA — nao o do cadastro. 20 pessoas tem tambem uma
                # @conectamais.pro inativa, e quem tenta a corporativa nao entra.
                f"  (SELECT u.email FROM users u WHERE CAST(u.employee_id AS TEXT)=CAST(employees.id AS TEXT) "
                f"     AND u.is_active ORDER BY u.last_login DESC NULLS LAST LIMIT 1) AS email_login "
                f"FROM employees WHERE {cond} ORDER BY nome"
            ),
            params,
        )
        .mappings()
        .all()
    )

    from core.mailer import send_email
    from modules.integrations.connectors.whatsapp.service import send_text_message

    resultados = []
    for r in rows:
        alvo = {"id": r["id"], "nome": r["nome"], "email": None, "whatsapp": None}
        fone = _e164(r["fone"])
        # Quem ja tem conta ATIVA e rosto nao faz primeiro acesso — recebe COMO ENTRAR,
        # com o e-mail exato da conta, porque a tela de /login pede e-mail e senha.
        ja_tem_conta = bool(r["tem_rosto"]) and bool(r["email_login"])
        alvo["modo"] = "login" if ja_tem_conta else "primeiro_acesso"
        destino = _link_login() if ja_tem_conta else link
        alvo["link"] = destino
        login_email = r["email_login"] or r["email"]
        assunto = (
            "Conecta PRO — como entrar (e-mail + CPF)" if ja_tem_conta else "Conecta PRO — Seu primeiro acesso ao ponto"
        )
        corpo_html = _msg_login_html(r["nome"], login_email, destino) if ja_tem_conta else _msg_html(r["nome"], destino)
        corpo_texto = (
            _msg_login_texto(r["nome"], login_email, destino) if ja_tem_conta else _msg_texto(r["nome"], destino)
        )
        if "email" in canais and r["email"]:
            alvo["email"] = r["email"]
            if not dry_run:
                try:
                    ok = await send_email(r["email"], assunto, corpo_html)
                    alvo["email_ok"] = bool(ok)
                except Exception as e:  # noqa: BLE001
                    alvo["email_ok"] = False
                    alvo["email_erro"] = str(e)[:120]
        if "whatsapp" in canais and fone:
            alvo["whatsapp"] = fone
            if not dry_run:
                try:
                    await send_text_message(fone, corpo_texto)
                    alvo["whatsapp_ok"] = True
                except Exception as e:  # noqa: BLE001
                    alvo["whatsapp_ok"] = False
                    alvo["whatsapp_erro"] = str(e)[:120]
        if not dry_run and (alvo["email"] or alvo["whatsapp"]):
            db.execute(
                text("UPDATE employees SET ponto_convite_enviado_em=now() WHERE CAST(id AS TEXT)=:i"), {"i": r["id"]}
            )
        resultados.append(alvo)
    if not dry_run:
        db.commit()
    return {
        "dry_run": dry_run,
        "link": link,
        "total": len(resultados),
        "com_email": sum(1 for a in resultados if a["email"]),
        "com_whatsapp": sum(1 for a in resultados if a["whatsapp"]),
        "resultados": resultados,
    }


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
    a = (
        db.execute(
            text(
                f"SELECT count(*) AS total, "
                f"  count(*) FILTER (WHERE face_descriptor IS NOT NULL) AS com_rosto, "
                f"  count(*) FILTER (WHERE primeiro_acesso_em IS NOT NULL) AS primeiro_acesso, "
                f"  count(*) FILTER (WHERE primeiro_acesso_em IS NOT NULL AND face_descriptor IS NULL) AS rosto_pendente, "
                f"  count(*) FILTER (WHERE primeiro_acesso_em::date = {hoje}) AS ativados_hoje "
                f"FROM employees WHERE {_COHORT}"
            )
        )
        .mappings()
        .first()
    )
    ativacao = dict(a)
    ativacao["pendentes"] = int(ativacao["total"]) - int(ativacao["primeiro_acesso"])

    b = (
        db.execute(
            text(
                f"SELECT count(*) AS total, count(DISTINCT employee_id) AS funcionarios, "
                f"  count(*) FILTER (WHERE device_type = 'contingencia') AS contingencia, "
                f"  count(*) FILTER (WHERE status = 'pending_contingencia') AS pendente_validar, "
                f"  count(*) FILTER (WHERE lower(coalesce(punch_type,'')) LIKE 'entrada%') AS entradas, "
                f"  count(*) FILTER (WHERE lower(coalesce(punch_type,'')) LIKE 'saida%' OR lower(coalesce(punch_type,'')) LIKE 'saída%') AS saidas "
                f"FROM gp_clock_punches WHERE punch_timestamp::date = {hoje} "
                f"  AND coalesce(device_type,'') NOT IN ('tangerino','web') "
                f"  AND employee_id IN (SELECT id FROM employees WHERE {_COHORT})"
            )
        )
        .mappings()
        .first()
    )

    feed = (
        db.execute(
            text(
                f"SELECT e.nome, p.punch_type, p.device_type, p.status, "
                f"  to_char(p.punch_timestamp, 'HH24:MI') AS hora "
                f"FROM gp_clock_punches p JOIN employees e ON e.id = p.employee_id "
                f"WHERE p.punch_timestamp::date = {hoje} "
                f"  AND coalesce(p.device_type,'') NOT IN ('tangerino','web') "
                f"  AND p.employee_id IN (SELECT id FROM employees WHERE {_COHORT}) "
                f"ORDER BY p.punch_timestamp DESC LIMIT 15"
            )
        )
        .mappings()
        .all()
    )

    # Padrão aprendido — MESMA fonte do painel público (`ponto/coorte_ponto.py`). O DP
    # precisa ver isto aqui dentro, não só no link sem login: é aqui que ele corrige o
    # cadastro do posto quando a divergência aparecer.
    from modules.people_management.ponto.coorte_ponto import (  # noqa: PLC0415
        APRENDIZADO_DESDE,
        HORAS_ENTRE_TURNOS,
        SQL_PADRAO_BATIDAS,
        montar_aprendizado,
    )

    # O `_COHORT` deste módulo não qualifica as colunas (`status=`, não `e.status=`), e o
    # SQL do padrão faz JOIN com `posts` — sem o alias, `status` fica ambíguo. Qualifico
    # aqui em vez de mexer no `_COHORT`, que é usado por outras cinco queries sem JOIN.
    _coorte_e = (
        _COHORT.replace("status=", "e.status=")
        .replace("coalesce(is_homologacao", "coalesce(e.is_homologacao")
        .replace("(tipo_contrato=", "(e.tipo_contrato=")
        .replace("tipo_contrato IS", "e.tipo_contrato IS")
    )
    padrao = (
        db.execute(
            text(SQL_PADRAO_BATIDAS.format(coorte=_coorte_e)),
            {"desde": APRENDIZADO_DESDE, "horas_turno": HORAS_ENTRE_TURNOS},
        )
        .mappings()
        .all()
    )
    aprendizado = montar_aprendizado(padrao)

    agora = db.execute(text("SELECT to_char(now() AT TIME ZONE 'America/Manaus', 'HH24:MI:SS')")).scalar()
    return {
        "ativacao": ativacao,
        "batidas_hoje": dict(b),
        "feed": [dict(x) for x in feed],
        "aprendizado": aprendizado,
        "alertas": aprendizado["alertas"],
        "atualizado_em": agora,
    }
