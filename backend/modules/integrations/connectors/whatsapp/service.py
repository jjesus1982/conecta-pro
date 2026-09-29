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

#: Devolvido por `_resolve_jid` quando o WhatsApp RESPONDEU que o número não existe — para
#: separar de `None`, que significa «não deu para perguntar» (rede, chave ausente, timeout).
#: Falha de infra não pode bloquear envio; número morto tem de bloquear.
NUMERO_NAO_EXISTE = "__nao_existe__"


def normalize_phone(phone: str | None) -> str | None:
    """Normaliza para os dígitos DDD+número (remove '+' e DDI 55). Limita a 20 chars
    (`cwi_message_log.phone_canonical` / `leads.phone` são varchar(20)) — phone hostil não quebra.

    ⭐ Mora AQUI, e não no controller, por causa da direção da dependência: o controller já
    importa este módulo, então quem envia pode canonizar sem importar um controller de FastAPI
    dentro do caminho de envio — num worker de celery isso executaria código de módulo que não
    tem nada a ver com mandar mensagem. O controller usa esta mesma função.

    ⚠️ Não duplicar: dois normalizadores divergem na primeira mudança e o mesmo telefone passa
    a existir em dois formatos no log, o que quebra qualquer contagem por pessoa.
    """
    if not phone:
        return None
    digits = "".join(c for c in str(phone) if c.isdigit())
    if digits.startswith("55") and len(digits) > 11:
        digits = digits[2:]
    return digits[:20] or None


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
        # identificador da instância (compat: o endpoint /whatsapp/status lê isto)
        self.instance = os.getenv("WHATSAPP_INSTANCE_ID", "conecta-pro")

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

    async def _resolve_jid(self, phone_e164: str) -> str | None:
        """Resolve o número discável para o JID REAL do WhatsApp via Baileys (on-whatsapp).
        Corrige o 9º dígito: no Brasil o número discável tem o 9 (ex.: +5592 9 8646-5328), mas
        contas antigas (ex.: DDD 92/Manaus) têm o JID SEM o 9 (5592 8646-5328). Sem isso, a
        mensagem vai para um JID inexistente e o Chatwoot fica preso em 'sent' sem entregar.
        Retorna os dígitos do JID real (ex.: '559286465328') ou None (mantém o original)."""
        import os  # noqa: PLC0415

        base = os.getenv("BAILEYS_API_URL", "http://baileys-api:3025").rstrip("/")
        key = os.getenv("BAILEYS_API_KEY", "")  # 08/09/2026: a chave estava chumbada no código
        sender = os.getenv("BAILEYS_COMPANY_PHONE") or os.getenv("WHATSAPP_SENDER") or "+558008804414"
        digits = "".join(c for c in phone_e164 if c.isdigit())
        if not (key and digits):
            return None
        url = f"{base}/connections/{sender}/on-whatsapp"
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    url,
                    json={"jids": [f"{digits}@s.whatsapp.net"]},
                    headers={"x-api-key": key, "Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=12),
                ) as resp,
            ):
                if resp.status != 200:
                    return None
                data = await resp.json()
            # Número vivo:  [{"jid":"559294755577@s.whatsapp.net","exists":true}]
            # Número morto:  []   ← HTTP 200 com lista VAZIA. Medido em 17/09/2026 contra o
            #                       92988887777 da Bianca. O WhatsApp RESPONDEU; a resposta é
            #                       «não existe». A primeira versão desta correção tratava a
            #                       lista vazia como «não consegui perguntar» e deixava passar
            #                       justamente o caso que se queria pegar.
            if isinstance(data, list):
                item = (data[0] or {}) if data else {}
                if item.get("exists") and item.get("jid"):
                    return "".join(c for c in str(item["jid"]).split("@")[0] if c.isdigit()) or None
                # 🔴 O WhatsApp RESPONDEU e disse que este número não existe. Não é o mesmo que
                # «não consegui perguntar»: aqui há resposta, e ela é negativa. Até 17/09/2026
                # os dois casos devolviam None e o envio seguia com o número original — a
                # mensagem morria no caminho e o sistema registrava sucesso.
                #
                # Medido nesse dia: 5 funcionários ATIVOS com número inexistente, 4 deles na
                # cobrança de assinatura que acabara de sair «30 enviados, 0 falhas». Bianca
                # (3 documentos parados), Eidy (2) e Ediwilson (2) nunca receberam nada —
                # nem naquele disparo nem nos anteriores.
                return NUMERO_NAO_EXISTE
            return None
        except Exception as e:  # noqa: BLE001 — nunca bloqueia o envio
            logger.warning("on-whatsapp resolve falhou para %s (segue com o original): %s", digits, e)
            return None

    async def _registrar_saida(self, phone: str, message: str, conv_id, msg_id) -> None:
        """Registra em `cwi_message_log` a mensagem que a casa ACABOU de enviar.

        🔴 MEDIDO EM 29/09/2026: o aviso diário de assinatura saiu às 09:00 para dezenas de
        pessoas e o log de saída guardou **23**. Conferi doze nomes que o monitor mostrou
        recebendo — TELMA, CELIANE, KELLY, VANDERLICE, NAILSON, PAULO, RUAN, BIANCA, DANIEL,
        MATHEUS, EDIWILSON, JONILSON — e **doze de doze não tinham linha nenhuma**. Oito
        minutos depois continuavam 23, então não era atraso: era ausência.

        ⭐ A causa é de família conhecida nesta casa: **o registro estava pendurado no EFEITO,
        não no ATO.** Quem escrevia o log era o *webhook* (`controller.py`, a partir do eco que
        o Chatwoot devolve), e não o envio. Eco que não volta = a empresa falou com um
        funcionário e não tem prova do que disse. Num assunto que é ponto, folha e assinatura,
        o que a casa afirmou a quem é exatamente o que se precisa poder mostrar depois.

        Agora grava-se no ato. Duas propriedades de propósito:

        1. **Idempotente com o eco.** `chatwoot_message_id` tem UNIQUE, então quando o webhook
           chegar com a mesma mensagem ele colide e não duplica. Não há dois registros do
           mesmo fato, e a ordem de chegada deixa de importar.
        2. **`status='sent'` marca a procedência.** O eco grava status nulo; esta linha nasce
           'sent'. É o que permite medir depois **quantas mensagens só existem porque este
           registro passou a ser feito** — sem isso o conserto seria indistinguível do acaso.

        ⚠️ Best-effort de verdade: banco fora do ar não pode calar um envio de WhatsApp. Toda
        exceção morre aqui, e o retorno de `_send_message` não muda em nada.
        """
        try:
            from sqlalchemy import text  # noqa: PLC0415

            from core.database.session import async_session_factory  # noqa: PLC0415

            async with async_session_factory() as db:
                await db.execute(
                    text(
                        "INSERT INTO cwi_message_log "
                        "  (direction, phone_canonical, chatwoot_conversation_id, "
                        "   chatwoot_message_id, content, status) "
                        "VALUES ('out', :fone, :conv, :msg, :txt, 'sent') "
                        "ON CONFLICT (chatwoot_message_id) DO NOTHING"
                    ),
                    {
                        "fone": normalize_phone(phone),
                        "conv": int(conv_id) if conv_id else None,
                        "msg": int(msg_id) if msg_id else None,
                        "txt": message,
                    },
                )
                await db.commit()
        except Exception as e:  # noqa: BLE001 — registro nunca bloqueia o envio
            logger.warning("cwi_message_log: não registrei a saída para %s: %s", phone, e)

    async def _send_message(self, phone: str, message: str) -> dict:
        """Envia mensagem via Chatwoot (contato -> conversa -> mensagem)."""
        if not self.enabled:
            logger.info("WhatsApp desabilitado (WHATSAPP_API_ENABLED=false)")
            return {"status": "disabled", "message": "WhatsApp nao habilitado"}

        if not self.api_token:
            logger.warning("CHATWOOT_API_TOKEN nao configurado")
            return {"status": "error", "message": "Token Chatwoot nao configurado"}

        phone = self._clean_phone(phone)
        # Corrige o 9º dígito: usa o JID real que o WhatsApp reconhece (best-effort).
        resolved = await self._resolve_jid(phone)
        if resolved == NUMERO_NAO_EXISTE:
            logger.warning("WhatsApp: %s não existe — mensagem NÃO enviada", phone)
            return {
                "status": "error",
                "erro": "numero_inexistente",
                "message": f"O número {phone} não existe no WhatsApp. Atualize o telefone no cadastro do colaborador.",
            }
        if resolved and resolved != "".join(c for c in phone if c.isdigit()):
            logger.info("WhatsApp: número %s resolvido para o JID real +%s", phone, resolved)
            phone = f"+{resolved}"
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
                    _msg_id = msg.get("id") if isinstance(msg, dict) else None
                    await self._registrar_saida(phone, message, conv_id, _msg_id)
                    return {
                        "status": "sent",
                        "phone": phone,
                        "conversation_id": conv_id,
                        "message_id": _msg_id,
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

    async def _post_attachment(self, conversation_id: int, file_name: str, file_bytes: bytes) -> bool:
        """Posta anexo (PDF) numa conversa existente — multipart. Best-effort (não levanta)."""
        if not (self.api_token and conversation_id and file_bytes):
            return False
        import mimetypes  # noqa: PLC0415

        ctype = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/messages"
        try:
            form = aiohttp.FormData()
            form.add_field("message_type", "outgoing")
            form.add_field("private", "false")
            form.add_field("attachments[]", file_bytes, filename=file_name, content_type=ctype)
            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    url,
                    data=form,
                    headers={"api_access_token": self.api_token},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp,
            ):
                if resp.status in (200, 201):
                    return True
                logger.error("WhatsApp anexo: HTTP %s (%s)", resp.status, (await resp.text())[:200])
                return False
        except Exception as e:  # noqa: BLE001
            logger.error("WhatsApp anexo conv=%s: %s", conversation_id, e)
            return False

    async def send_with_attachment(self, phone: str, message: str, file_bytes: bytes, file_name: str) -> dict:
        """Envia uma mensagem de texto e, na MESMA conversa, anexa um arquivo (ex.: PDF da proposta)."""
        res = await self._send_message(phone, message)
        if res.get("status") == "sent" and res.get("conversation_id"):
            res["attachment_sent"] = await self._post_attachment(int(res["conversation_id"]), file_name, file_bytes)
        else:
            res["attachment_sent"] = False
        return res

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


# ── Funções de módulo (usadas pela cadência de sequências: growth_services._action_send_whatsapp) ──
async def send_text_message(phone: str, message: str) -> dict:
    """Envia uma mensagem de texto pelo WhatsApp (Chatwoot/Baileys). Wrapper do singleton.
    Antes esta função NÃO existia e o motor de cadência (channel=whatsapp) falhava no import — agora funciona."""
    return await whatsapp_service.send_custom(phone, message)


async def send_text_with_pdf(phone: str, message: str, pdf_bytes: bytes, file_name: str) -> dict:
    """Envia texto + anexo PDF na mesma conversa (ex.: proposta por WhatsApp)."""
    return await whatsapp_service.send_with_attachment(phone, message, pdf_bytes, file_name)
