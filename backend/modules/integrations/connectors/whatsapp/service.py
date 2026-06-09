"""
WhatsApp Service — Chatwoot (Baileys) integration.

Migrado de Evolution API para Chatwoot em 2026-06-05.
Envio de kits documentais, alertas de certidoes e notificacoes
para clientes via WhatsApp, usando a Application API do Chatwoot
(que entrega via Baileys). Mantem as mesmas assinaturas publicas.
"""

import json
import logging
import os

import aiohttp

logger = logging.getLogger(__name__)

MONTH_NAMES = [
    "Janeiro",
    "Fevereiro",
    "Marco",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]


def _read_secret_file(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except Exception:  # noqa: BLE001
        return ""


class WhatsAppService:
    """Servico de envio de mensagens via Chatwoot (Application API)."""

    def __init__(self) -> None:
        # Defaults seguros embutidos (rede interna). Token via env ou arquivo.
        self.base_url = os.getenv("CHATWOOT_BASE_URL", "http://chatwoot-fazerai:3000").rstrip("/")
        self.account_id = os.getenv("CHATWOOT_ACCOUNT_ID", "1")
        self.inbox_id = int(os.getenv("CHATWOOT_INBOX_ID", "1"))
        self.api_token = os.getenv("CHATWOOT_API_TOKEN", "") or _read_secret_file("/app/.chatwoot_token")
        self.enabled = os.getenv("WHATSAPP_API_ENABLED", "false").lower() == "true"

    def _clean_phone(self, phone: str) -> str:
        """Normaliza para E.164 com DDI 55 (ex.: +5592...)."""
        clean = "".join(c for c in phone if c.isdigit())
        if not clean.startswith("55"):
            clean = f"55{clean}"
        return f"+{clean}"

    def _headers(self) -> dict:
        return {
            "api_access_token": self.api_token,
            "Content-Type": "application/json",
        }

    async def _api(
        self, session: aiohttp.ClientSession, method: str, path: str, body: dict | None = None
    ) -> tuple[int, dict]:
        url = f"{self.base_url}/api/v1/accounts/{self.account_id}{path}"
        async with session.request(
            method,
            url,
            json=body,
            headers=self._headers(),
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            text = await resp.text()
            try:
                data = json.loads(text) if text else {}
            except json.JSONDecodeError:
                data = {"raw": text[:200]}
            return resp.status, data

    async def _resolve_contact(self, session: aiohttp.ClientSession, phone: str) -> tuple[int | None, str | None]:
        """Retorna (contact_id, source_id) do inbox; cria contato se necessario."""
        # 1) tenta criar
        status, data = await self._api(
            session,
            "POST",
            "/contacts",
            {"inbox_id": self.inbox_id, "name": phone, "phone_number": phone},
        )
        if status in (200, 201):
            payload = data.get("payload", data)
            contact = payload.get("contact", payload)
            contact_id = contact.get("id")
            source_id = (payload.get("contact_inbox") or {}).get("source_id")
            if contact_id and source_id:
                return contact_id, source_id
            cid = contact_id
        else:
            cid = None

        # 2) ja existe (422) ou faltou source_id -> busca
        digits = phone.replace("+", "")
        s2, sr = await self._api(session, "GET", f"/contacts/search?q={digits}")
        plist = sr.get("payload", []) if isinstance(sr, dict) else []
        if plist:
            cid = plist[0].get("id", cid)
        if not cid:
            return None, None

        # 3) source_id via contactable_inboxes
        s3, ci = await self._api(session, "GET", f"/contacts/{cid}/contactable_inboxes")
        items = ci.get("payload", ci) if isinstance(ci, dict) else ci
        if isinstance(items, list):
            for it in items:
                if (it.get("inbox") or {}).get("id") == self.inbox_id:
                    return cid, it.get("source_id")
        return cid, None

    async def _send_message(self, phone: str, message: str) -> dict:
        """Envia mensagem via Chatwoot (contato -> conversa -> mensagem)."""
        if not self.enabled:
            logger.info("WhatsApp desabilitado (WHATSAPP_API_ENABLED=false)")
            return {"status": "disabled", "message": "WhatsApp nao habilitado"}

        if not self.api_token:
            logger.warning("CHATWOOT_API_TOKEN nao configurado")
            return {"status": "error", "message": "Token Chatwoot nao configurado"}

        phone = self._clean_phone(phone)
        try:
            async with aiohttp.ClientSession() as session:
                contact_id, source_id = await self._resolve_contact(session, phone)
                if not (contact_id and source_id):
                    logger.error("Nao resolveu contato/source_id para %s", phone)
                    return {"status": "error", "message": "contato nao resolvido"}

                # cria conversa (reusa a do contato_inbox se ja houver)
                cs, conv = await self._api(
                    session,
                    "POST",
                    "/conversations",
                    {
                        "source_id": source_id,
                        "inbox_id": self.inbox_id,
                        "contact_id": contact_id,
                    },
                )
                conv_id = conv.get("id") if isinstance(conv, dict) else None
                if not conv_id:
                    logger.error("Falha ao criar conversa %s: %s", cs, conv)
                    return {"status": "error", "code": cs, "data": conv}

                ms, msg = await self._api(
                    session,
                    "POST",
                    f"/conversations/{conv_id}/messages",
                    {"content": message, "message_type": "outgoing"},
                )
                if ms in (200, 201):
                    logger.info("WhatsApp(Chatwoot) enviado para %s", phone)
                    return {
                        "status": "sent",
                        "phone": phone,
                        "conversation_id": conv_id,
                        "message_id": msg.get("id") if isinstance(msg, dict) else None,
                    }
                logger.error("Erro WhatsApp(Chatwoot) %s: %s", ms, msg)
                return {"status": "error", "code": ms, "data": msg}
        except Exception as e:  # noqa: BLE001
            logger.error("Excecao WhatsApp(Chatwoot): %s", e)
            return {"status": "exception", "error": str(e)}

    async def assign_team(self, conversation_id: int, team_id: int) -> dict:
        """Atribui a conversa a um TIME no Chatwoot (transferência por setor). Best-effort."""
        if not self.api_token:
            logger.warning("CHATWOOT_API_TOKEN nao configurado — assign_team abortado")
            return {"status": "error", "message": "Token Chatwoot nao configurado"}
        try:
            async with aiohttp.ClientSession() as session:
                st, data = await self._api(
                    session,
                    "POST",
                    f"/conversations/{conversation_id}/assignments",
                    {"team_id": team_id},
                )
                if st in (200, 201):
                    logger.info("Chatwoot: conversa %s atribuida ao time %s", conversation_id, team_id)
                    return {"status": "assigned", "conversation_id": conversation_id, "team_id": team_id}
                logger.error("Chatwoot assign_team falhou %s: %s", st, data)
                return {"status": "error", "code": st, "data": data}
        except Exception as e:  # noqa: BLE001
            logger.error("Chatwoot assign_team excecao conv=%s: %s", conversation_id, e)
            return {"status": "exception", "error": str(e)}

    async def send_kit_notification(
        self,
        phone: str,
        client_name: str,
        month: int,
        year: int,
        documents_count: int,
        portal_url: str | None = None,
    ) -> dict:
        """Notifica cliente sobre kit mensal disponivel."""
        mes = MONTH_NAMES[month - 1] if 1 <= month <= 12 else str(month)
        message = (
            f"\U0001f3e2 *Conecta Mais — Seguranca e Tecnologia*\n\n"
            f"Ola! O kit documental de *{mes}/{year}* "
            f"esta disponivel para *{client_name}*.\n\n"
            f"\U0001f4c4 *{documents_count} documentos* incluidos:\n"
            f"• Contracheques\n"
            f"• Folhas de ponto\n"
            f"• Certidoes\n"
            f"• NFS-e\n\n"
        )
        if portal_url:
            message += f"\U0001f517 Acesse: {portal_url}\n\n"
        message += (
            "Em caso de duvidas, entre em contato:\n"
            "\U0001f4de (92) 9348-5518\n"
            "\U0001f4e7 contato@conectamaistech.com.br"
        )
        return await self._send_message(phone, message)

    async def send_certificate_alert(
        self,
        phone: str,
        client_name: str,
        certificate_type: str,
        expiry_date: str,
        days_remaining: int,
    ) -> dict:
        """Alerta sobre certidao vencendo."""
        emoji = "\U0001f534" if days_remaining <= 7 else "\U0001f7e1"
        urgency = "URGENTE" if days_remaining <= 7 else "ATENCAO"
        message = (
            f"{emoji} *{urgency} — Conecta Mais*\n\n"
            f"A certidao *{certificate_type}* de *{client_name}* "
            f"vence em *{days_remaining} dias* ({expiry_date}).\n\n"
            f"Por favor, providencie a renovacao.\n\n"
            f"\U0001f4de (92) 9348-5518"
        )
        return await self._send_message(phone, message)

    async def send_nfse_notification(
        self,
        phone: str,
        client_name: str,
        nfse_number: str,
        value: float,
        month: int,
        year: int,
    ) -> dict:
        """Notifica emissao de NFS-e."""
        mes = MONTH_NAMES[month - 1] if 1 <= month <= 12 else str(month)
        message = (
            f"\U0001f4cb *NFS-e Emitida — Conecta Mais*\n\n"
            f"Cliente: *{client_name}*\n"
            f"NFS-e nº: *{nfse_number}*\n"
            f"Competencia: *{mes}/{year}*\n"
            f"Valor: *R$ {value:,.2f}*\n\n"
            f"A nota fiscal esta disponivel no portal.\n"
            f"\U0001f4de (92) 9348-5518"
        )
        return await self._send_message(phone, message)

    async def send_custom(self, phone: str, message: str) -> dict:
        """Envia mensagem customizada."""
        return await self._send_message(phone, message)

    async def check_status(self) -> dict:
        """Verifica conectividade/credencial na API do Chatwoot."""
        if not self.enabled:
            return {"online": False, "reason": "disabled"}
        if not self.api_token:
            return {"online": False, "reason": "no_token"}
        try:
            async with aiohttp.ClientSession() as session:
                status, _ = await self._api(session, "GET", f"/conversations?inbox_id={self.inbox_id}&status=open")
                if status == 200:
                    return {"online": True, "provider": "chatwoot/baileys"}
                return {"online": False, "code": status}
        except Exception as e:  # noqa: BLE001
            return {"online": False, "error": str(e)}


whatsapp_service = WhatsAppService()
