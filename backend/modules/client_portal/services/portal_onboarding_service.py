"""Portal do Cliente — Onboarding/adoção de síndicos.

Provisiona (ou reseta) o acesso e ENTREGA as credenciais:
- e-mail de boas-vindas SÓ para endereço real do síndico (nunca alias interno
  @conectamais.pro — cairia na própria caixa da Conecta, não do cliente);
- para alias interno, devolve as credenciais na resposta para o Jordan entregar
  pelo canal certo (WhatsApp do síndico, impresso), sem enviar às cegas.

100% honesto: informa o motivo de cada e-mail não enviado; nunca fabrica entrega.
"""

from __future__ import annotations

import logging
import secrets
import string

from passlib.hash import bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PORTAL_URL = "https://erp.conectamais.pro/area-cliente/login"
# domínios internos: e-mail aqui NÃO é do síndico — não enviar credencial
_DOMINIOS_INTERNOS = ("conectamais.pro", "conectamaistech.com.br", "conectamais.com.br")


def _senha_temporaria(n: int = 10) -> str:
    alfabeto = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(n))


def _email_e_do_sindico(email: str | None) -> bool:
    if not email or "@" not in email:
        return False
    dominio = email.rsplit("@", 1)[1].strip().lower()
    return dominio not in _DOMINIOS_INTERNOS


def _html_boas_vindas(nome_cond: str, username: str, senha: str) -> str:
    return (
        "<div style='font-family:sans-serif;max-width:560px;margin:auto'>"
        "<h2 style='color:#4338ca'>Bem-vindo ao Portal do Cliente — Conecta Mais</h2>"
        f"<p>Olá! O portal do <strong>{nome_cond}</strong> já está disponível. "
        "Nele você acompanha, com total transparência: a equipe alocada e a presença "
        "no seu condomínio, as visitas da nossa gestão (com fotos), os documentos "
        "mensais (kits) com aprovação digital, notas fiscais e chamados de suporte.</p>"
        "<table style='margin:18px 0;border-collapse:collapse'>"
        f"<tr><td style='padding:6px 12px;color:#6b7280'>Endereço</td><td style='padding:6px 12px'><a href='{PORTAL_URL}'>{PORTAL_URL}</a></td></tr>"
        f"<tr><td style='padding:6px 12px;color:#6b7280'>Usuário</td><td style='padding:6px 12px'><strong>{username}</strong></td></tr>"
        f"<tr><td style='padding:6px 12px;color:#6b7280'>Senha temporária</td><td style='padding:6px 12px'><strong>{senha}</strong></td></tr>"
        "</table>"
        f"<p><a href='{PORTAL_URL}' style='background:#4338ca;color:#fff;padding:11px 20px;border-radius:8px;text-decoration:none'>Acessar o portal</a></p>"
        "<p style='color:#6b7280;font-size:13px'>Recomendamos trocar a senha no primeiro acesso, em Configurações. "
        "Qualquer dúvida, fale com o José Luís (assistente do portal) ou abra um chamado.</p>"
        "<hr style='border:none;border-top:1px solid #e5e7eb'>"
        "<p style='color:#6b7280;font-size:13px'>José Luís · Conecta Mais Patrimonial · Portal do Cliente</p></div>"
    )


async def onboard_cliente(
    db: AsyncSession,
    client_id: str,
    enviar_email: bool = True,
    email_override: str | None = None,
) -> dict:
    """Provisiona/reseta o acesso e entrega as credenciais pelo canal certo."""
    row = (
        await db.execute(
            text("SELECT id::text, name, cnpj, contact_email, portal_access_enabled FROM ged_clients WHERE id = :cid"),
            {"cid": client_id},
        )
    ).mappings().first()
    if not row:
        return {"ok": False, "erro": "cliente não encontrado"}

    cnpj_clean = "".join(c for c in (row["cnpj"] or "") if c.isdigit())
    username = cnpj_clean or f"client_{client_id[:8]}"
    senha = _senha_temporaria()
    await db.execute(
        text(
            "UPDATE ged_clients SET portal_access_enabled = true, portal_username = :u, "
            "portal_password_hash = :h, updated_at = NOW() WHERE id = :cid"
        ),
        {"u": username, "h": bcrypt.hash(senha), "cid": client_id},
    )

    destino = email_override or row["contact_email"]
    email_real = _email_e_do_sindico(destino)
    enviou = False
    motivo = None

    if enviar_email and email_real:
        try:
            from core.mailer import send_email

            enviou = await send_email(
                destino,
                "Seu acesso ao Portal do Cliente — Conecta Mais",
                _html_boas_vindas(row["name"], username, senha),
            )
            if not enviou:
                motivo = "SMTP retornou falha"
        except Exception as exc:  # noqa: BLE001
            motivo = f"erro no envio: {exc}"
            logger.warning("Onboarding e-mail falhou p/ %s: %s", row["name"], exc)
    elif not email_real:
        motivo = f"e-mail cadastrado é interno/ausente ({destino or 'vazio'}) — entregar credenciais manualmente ao síndico"

    await db.execute(
        text(
            "INSERT INTO portal_access_logs (client_id, action, details, created_at) "
            "VALUES (:cid,'provision', :d, NOW())"
        ),
        {"cid": client_id, "d": f"Onboarding: e-mail {'enviado a '+destino if enviou else 'NÃO enviado ('+str(motivo)+')'}"},
    )
    await db.commit()

    return {
        "ok": True,
        "client_id": client_id,
        "condominio": row["name"],
        "portal_username": username,
        "senha_temporaria": senha,  # visível só aqui
        "portal_url": PORTAL_URL,
        "email_destino": destino,
        "email_enviado": enviou,
        "entrega_manual": not enviou,
        "motivo": motivo,
    }


async def onboard_nao_logados(
    db: AsyncSession, enviar_email: bool = True
) -> dict:
    """Onboarding em lote: todos os clientes habilitados que NUNCA logaram."""
    clientes = (
        await db.execute(
            text(
                """SELECT g.id::text FROM ged_clients g
                   WHERE g.portal_access_enabled
                     AND NOT EXISTS (SELECT 1 FROM client_portal_sessions s WHERE s.client_id = g.id)
                   ORDER BY g.name"""
            )
        )
    ).all()
    resultados = []
    for (cid,) in clientes:
        resultados.append(await onboard_cliente(db, cid, enviar_email=enviar_email))
    enviados = sum(1 for r in resultados if r.get("email_enviado"))
    manuais = [r for r in resultados if r.get("entrega_manual")]
    return {
        "total": len(resultados),
        "emails_enviados": enviados,
        "entrega_manual": len(manuais),
        "resultados": resultados,
    }
