"""
Webhook WhatsApp para o Portal do Cliente.

Recebe mensagens do WhatsApp (Evolution API) e as converte em tickets
de suporte, ou adiciona mensagens a tickets existentes.
"""

import logging
import os
from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from modules.client_portal.services.whatsapp_ia_service import responder_com_ia

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["Portal - WhatsApp"])

WEBHOOK_SECRET = os.getenv("WHATSAPP_WEBHOOK_SECRET", "")
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "")  # numero da empresa, ex: 559212345678


# ============================================================
# Schemas
# ============================================================


class WhatsAppConfigResponse(BaseModel):
    whatsapp_number: str
    enabled: bool
    message: str


# ============================================================
# Helpers
# ============================================================


def _extract_text(payload: dict) -> str | None:
    """Extrai texto de vários tipos de mensagem do Evolution API."""
    try:
        data = payload.get("data", {})
        msg = data.get("message", {})
        return (
            msg.get("conversation")
            or msg.get("extendedTextMessage", {}).get("text")
            or msg.get("imageMessage", {}).get("caption")
            or None
        )
    except Exception:
        return None


def _extract_phone(payload: dict) -> str | None:
    """Extrai número de telefone do remetente."""
    try:
        data = payload.get("data", {})
        key = data.get("key", {})
        remote_jid = key.get("remoteJid", "")
        # remoteJid formato: 5592XXXXXXXX@s.whatsapp.net
        return remote_jid.split("@")[0] if "@" in remote_jid else remote_jid
    except Exception:
        return None


def _is_from_me(payload: dict) -> bool:
    """Verifica se a mensagem foi enviada pela própria empresa (evita loop)."""
    try:
        return payload.get("data", {}).get("key", {}).get("fromMe", False)
    except Exception:
        return False


async def _process_whatsapp_message(payload: dict) -> None:
    """Processa mensagem WhatsApp em background: cria ou atualiza ticket."""
    from core.database.session import SyncSessionLocal

    phone = _extract_phone(payload)
    text = _extract_text(payload)

    if not phone or not text:
        logger.debug("WhatsApp webhook: mensagem sem telefone ou texto — ignorando")
        return

    logger.info("WhatsApp: mensagem de %s: %s", phone, text[:80])

    # IA: primeiro atendente automático (T7-IA §84)
    try:
        _ia = responder_com_ia(mensagem=text, historico=[], cliente_nome="Cliente")
        if _ia["resposta"]:
            _send_whatsapp_reply(phone, _ia["resposta"])
        if _ia["escalar"]:
            logger.info("WhatsApp IA: escalando para humano — %s", _ia.get("motivo_escalada"))
            # Futuro: notificar agente no Chatwoot
        else:
            return  # IA resolveu — não criar ticket
    except Exception as _e:
        logger.warning("WhatsApp IA: falha, continuando fluxo padrão: %s", _e)

    try:
        from sqlalchemy import text as sql_text

        with SyncSessionLocal() as db:
            # Buscar cliente pelo número de WhatsApp
            result = db.execute(
                sql_text("SELECT id, name FROM clients WHERE whatsapp = :phone AND ativo = true LIMIT 1"),
                {"phone": phone},
            ).fetchone()

            if not result:
                # Tentar sem código do país (busca parcial pelo sufixo)
                suffix = phone[-9:] if len(phone) >= 9 else phone
                result = db.execute(
                    sql_text("SELECT id, name FROM clients WHERE whatsapp LIKE :suf AND ativo = true LIMIT 1"),
                    {"suf": f"%{suffix}"},
                ).fetchone()

            if not result:
                logger.info("WhatsApp: telefone %s sem cliente cadastrado", phone)
                _send_whatsapp_reply(
                    phone,
                    "❌ Número não cadastrado no portal Conecta PRO. Entre em contato com sua administradora.",
                )
                return

            client_id = str(result[0])
            client_name = result[1]

            # Verificar se há ticket aberto para este cliente
            ticket_row = db.execute(
                sql_text(
                    "SELECT id, subject FROM client_portal_tickets "
                    "WHERE client_id = :cid AND status IN ('ABERTO','EM_ANDAMENTO') "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"cid": client_id},
            ).fetchone()

            now = datetime.now(UTC)

            if ticket_row and not text.upper().startswith(("CHAMADO ", "#NOVO", "NOVO CHAMADO")):
                # Adicionar mensagem ao ticket existente
                ticket_id = ticket_row[0]
                db.execute(
                    sql_text(
                        "INSERT INTO client_portal_ticket_messages "
                        "(id, ticket_id, sender, content, created_at) "
                        "VALUES (gen_random_uuid(), :tid, 'client', :content, :now)"
                    ),
                    {"tid": ticket_id, "content": text, "now": now},
                )
                db.commit()
                logger.info("WhatsApp: mensagem adicionada ao ticket %s", ticket_id)
                _send_whatsapp_reply(
                    phone,
                    f"✅ Sua mensagem foi adicionada ao chamado #{str(ticket_id)[:8].upper()}. "
                    "Nossa equipe responderá em breve.",
                )
            else:
                # Criar novo ticket
                subject = text[:100] if not text.upper().startswith("CHAMADO ") else text[8:108]
                result2 = db.execute(
                    sql_text(
                        "INSERT INTO client_portal_tickets "
                        "(id, client_id, subject, description, status, priority, source, created_at, updated_at) "
                        "VALUES (gen_random_uuid(), :cid, :subj, :desc, 'ABERTO', 'NORMAL', 'whatsapp', :now, :now) "
                        "RETURNING id"
                    ),
                    {
                        "cid": client_id,
                        "subj": subject[:100],
                        "desc": text,
                        "now": now,
                    },
                )
                new_id = result2.fetchone()[0]
                db.commit()
                logger.info("WhatsApp: novo ticket %s criado para cliente %s", new_id, client_name)
                _send_whatsapp_reply(
                    phone,
                    f"✅ Chamado #{str(new_id)[:8].upper()} aberto com sucesso! "
                    "Nossa equipe entrará em contato em breve.",
                )

    except Exception as exc:
        logger.error("WhatsApp: erro ao processar mensagem: %s", exc, exc_info=True)


def _send_whatsapp_reply(phone: str, message: str) -> None:
    """Envia resposta via Evolution API (best-effort, não lança exceção)."""
    try:
        import httpx

        evolution_url = os.getenv("EVOLUTION_API_URL", "")
        evolution_key = os.getenv("EVOLUTION_API_KEY", "")
        evolution_instance = os.getenv("WHATSAPP_INSTANCE_ID", os.getenv("EVOLUTION_INSTANCE", "conecta-pro"))

        if not evolution_url or not evolution_key:
            logger.debug("Evolution API não configurada — resposta WhatsApp não enviada")
            return

        httpx.post(
            f"{evolution_url}/message/sendText/{evolution_instance}",
            headers={"apikey": evolution_key, "Content-Type": "application/json"},
            json={"number": phone, "text": message},
            timeout=10.0,
        )
    except Exception as exc:
        logger.warning("WhatsApp: falha ao enviar resposta: %s", exc)


# ============================================================
# Endpoints
# ============================================================


