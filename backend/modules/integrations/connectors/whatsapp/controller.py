"""
WhatsApp Controller — Endpoints REST para envio de mensagens.
"""

import hmac
import json
import logging
import os
import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser, CurrentUserId
from core.database import get_db
from modules.integrations.connectors.whatsapp import agent_service
from modules.integrations.connectors.whatsapp.service import (
    _read_secret_file,
    whatsapp_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp - Evolution API"])


# === Schemas ===


class WhatsAppStatusResponse(BaseModel):
    online: bool
    instance: str
    enabled: bool
    details: dict = {}


class SendKitNotificationRequest(BaseModel):
    phone: str = Field(..., description="Telefone com DDD")
    client_name: str
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2024, le=2030)
    documents_count: int = Field(ge=0, default=0)
    portal_url: str | None = None


class SendCertAlertRequest(BaseModel):
    phone: str
    client_name: str
    certificate_type: str
    expiry_date: str
    days_remaining: int


class SendNfseRequest(BaseModel):
    phone: str
    client_name: str
    nfse_number: str
    value: float
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2024, le=2030)


class SendCustomRequest(BaseModel):
    phone: str
    message: str = Field(..., min_length=1, max_length=4096)


class SendResponse(BaseModel):
    success: bool
    status: str
    phone: str | None = None
    message: str | None = None
    data: dict = {}


# === Endpoints ===


@router.get("/status", response_model=WhatsAppStatusResponse)
async def get_whatsapp_status(current_user: CurrentActiveUser) -> WhatsAppStatusResponse:
    """Verifica status da conexao WhatsApp/Evolution API."""
    result = await whatsapp_service.check_status()
    return WhatsAppStatusResponse(
        online=result.get("online", False),
        instance=whatsapp_service.instance,
        enabled=whatsapp_service.enabled,
        details=result,
    )


@router.post("/send/kit-notification", response_model=SendResponse)
async def send_kit_notification(
    request: SendKitNotificationRequest,
    user_id: CurrentUserId,
    current_user: CurrentActiveUser,
) -> SendResponse:
    """Envia notificacao de kit documental via WhatsApp."""
    result = await whatsapp_service.send_kit_notification(
        phone=request.phone,
        client_name=request.client_name,
        month=request.month,
        year=request.year,
        documents_count=request.documents_count,
        portal_url=request.portal_url,
    )
    return SendResponse(
        success=result.get("status") == "sent",
        status=result.get("status", "unknown"),
        phone=result.get("phone"),
        data=result,
    )


@router.post("/send/certificate-alert", response_model=SendResponse)
async def send_certificate_alert(
    request: SendCertAlertRequest,
    user_id: CurrentUserId,
    current_user: CurrentActiveUser,
) -> SendResponse:
    """Envia alerta de certidao vencendo via WhatsApp."""
    result = await whatsapp_service.send_certificate_alert(
        phone=request.phone,
        client_name=request.client_name,
        certificate_type=request.certificate_type,
        expiry_date=request.expiry_date,
        days_remaining=request.days_remaining,
    )
    return SendResponse(
        success=result.get("status") == "sent",
        status=result.get("status", "unknown"),
        phone=result.get("phone"),
        data=result,
    )


@router.post("/send/nfse-notification", response_model=SendResponse)
async def send_nfse_notification(
    request: SendNfseRequest,
    user_id: CurrentUserId,
    current_user: CurrentActiveUser,
) -> SendResponse:
    """Envia notificacao de NFS-e emitida via WhatsApp."""
    result = await whatsapp_service.send_nfse_notification(
        phone=request.phone,
        client_name=request.client_name,
        nfse_number=request.nfse_number,
        value=request.value,
        month=request.month,
        year=request.year,
    )
    return SendResponse(
        success=result.get("status") == "sent",
        status=result.get("status", "unknown"),
        phone=result.get("phone"),
        data=result,
    )


@router.post("/send/custom", response_model=SendResponse)
async def send_custom_message(
    request: SendCustomRequest,
    user_id: CurrentUserId,
    current_user: CurrentActiveUser,
) -> SendResponse:
    """Envia mensagem customizada via WhatsApp."""
    result = await whatsapp_service.send_custom(
        phone=request.phone,
        message=request.message,
    )
    return SendResponse(
        success=result.get("status") == "sent",
        status=result.get("status", "unknown"),
        phone=result.get("phone"),
        data=result,
    )


# === Webhook de ENTRADA (Chatwoot -> backend) — Fase 2 ===


def _normalize_phone(phone: str | None) -> str | None:
    """Normaliza para os digitos DDD+numero (remove '+' e DDI 55). Limita a 20 chars
    (cwi_message_log.phone_canonical / leads.phone sao varchar(20)) — phone hostil nao quebra."""
    if not phone:
        return None
    digits = "".join(c for c in str(phone) if c.isdigit())
    if digits.startswith("55") and len(digits) > 11:
        digits = digits[2:]
    return digits[:20] or None


def _safe_int(v) -> int | None:
    """Coage para int de forma tolerante (id do Chatwoot hostil/ausente -> None, sem 500)."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


async def _match_or_create_lead(db: AsyncSession, phone_canonical: str, name: str | None) -> str | None:
    """Dedup por telefone normalizado em leads.phone; cria Lead (source=whatsapp) se novo."""
    # Lock por telefone (advisory transacional): serializa criação concorrente do mesmo
    # contato (2 webhooks simultâneos) -> evita lead duplicado. Auto-libera no commit/rollback.
    try:
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:p)::bigint)"), {"p": phone_canonical})
    except Exception:  # noqa: BLE001 — sem lock é pior, mas não fatal
        pass
    row = (
        await db.execute(
            text(
                "SELECT id FROM leads "
                "WHERE regexp_replace(coalesce(phone, ''), '\\D', '', 'g') = :p "
                "AND is_active = true LIMIT 1"
            ),
            {"p": phone_canonical},
        )
    ).first()
    if row:
        return str(row[0])

    from modules.crm.models.lead import LeadSource
    from modules.crm.repositories.lead_repository import LeadRepository
    from modules.crm.schemas.lead import LeadCreate

    lead_name = (name or "").strip() or f"WhatsApp {phone_canonical}"
    repo = LeadRepository(db)
    new_id: str | None = None
    try:
        lead = await repo.create(
            LeadCreate(
                name=lead_name[:255],
                email=None,
                phone=phone_canonical,
                source=LeadSource.WHATSAPP,
            )
        )
        new_id = lead.id
    except Exception as e:  # noqa: BLE001
        # O validator do LeadCreate exige 10-15 dígitos; um phone hostil/atípico (8 ou >15)
        # faria o lead NUNCA ser criado (silencioso). Fallback: INSERT cru (lenient) p/ a
        # entrada sempre ter um lead vinculado — consistente com a auto-cura.
        logger.warning("Webhook: LeadCreate rejeitou phone=%s (%s) — INSERT cru de fallback", phone_canonical, e)
        lid = (
            await db.execute(
                text(
                    "INSERT INTO leads (id,name,phone,source,status,score,probability,"
                    "expected_value,is_active,created_at,updated_at) VALUES "
                    "(gen_random_uuid(),:n,:p,'whatsapp','new',0,0,0,true,now(),now()) RETURNING id"
                ),
                {"n": lead_name[:255], "p": phone_canonical},
            )
        ).scalar()
        new_id = str(lid) if lid else None

    # Conversions API (Meta): avisa a Meta do lead NOVO. Best-effort, dorme sem token.
    if new_id:
        try:
            from modules.integrations.connectors.meta.capi import send_lead_event

            await send_lead_event(phone=phone_canonical, lead_id=new_id)
        except Exception as e:  # noqa: BLE001
            logger.debug("Meta CAPI: ignorado (%s)", e)
    return new_id


# Limite de download de audio (anti-abuso); voice do WhatsApp fica na casa de KB.
_AUDIO_MAX_BYTES = 16 * 1024 * 1024
_audio_payload_logged = False  # loga o payload bruto de attachments 1x p/ calibrar formato


async def _transcrever_audio_attachments(data: dict) -> str | None:
    """STT best-effort: acha attachment de audio, baixa do Chatwoot e transcreve (Whisper).

    Retorna "🎤 [áudio transcrito]: <texto>" ou None. NUNCA levanta excecao —
    qualquer falha loga e retorna None (webhook segue com content vazio, como hoje).
    """
    global _audio_payload_logged  # noqa: PLW0603
    try:
        attachments = data.get("attachments") or []
        if not attachments:
            return None

        if not _audio_payload_logged:
            _audio_payload_logged = True
            logger.info(
                "Webhook Chatwoot: payload attachments (1a ocorrencia, calibracao): %s",
                json.dumps(attachments, ensure_ascii=False, default=str)[:800],
            )

        # LOCALIZACAO (pin do WhatsApp): Chatwoot entrega file_type=location com
        # coordinates_lat/long. Nao precisa baixar nada — vira endereco da visita.
        for cand in attachments:
            ftype = str(cand.get("file_type", "")).lower()
            lat = cand.get("coordinates_lat")
            lng = cand.get("coordinates_long")
            if ftype == "location" or (lat is not None and lng is not None):
                if lat is None or lng is None:
                    continue
                titulo = str(cand.get("fallback_title") or "").strip()
                extra = f" — {titulo}" if titulo else ""
                return (
                    f"📍 [localização recebida — use como endereço da visita, não peça "
                    f"rua/número de novo]: https://www.google.com/maps?q={lat},{lng} "
                    f"(coordenadas {lat},{lng}){extra}"
                )

        # Seleciona o 1o attachment de tipo conhecido e classifica:
        # audio | video (Whisper transcreve a fala) | image (visao) | doc (PDF/DOCX/TXT)
        att, kind = None, None
        for cand in attachments:
            ftype = str(cand.get("file_type", "")).lower()
            ctype = str(cand.get("content_type", "")).lower()
            url_l = str(cand.get("data_url") or cand.get("file_url") or "").lower()
            if ftype == "audio" or "audio" in ctype:
                att, kind = cand, "audio"
            elif ftype == "video" or "video" in ctype:
                att, kind = cand, "video"
            elif ftype == "image" or "image" in ctype:
                att, kind = cand, "image"
            elif ftype == "file" or any(
                url_l.split("?")[0].endswith(e)
                for e in (".pdf", ".docx", ".txt", ".xlsx", ".xlsm", ".xls", ".pptx", ".csv")
            ):
                att, kind = cand, "doc"
            if att:
                break
        if not att:
            return None

        data_url = att.get("data_url") or att.get("file_url") or ""
        if not data_url:
            logger.warning("Webhook Chatwoot: attachment (%s) sem data_url", kind)
            return None
        if not data_url.startswith("http"):
            base = os.getenv("CHATWOOT_BASE_URL", "http://chatwoot-fazerai:3000").rstrip("/")
            data_url = f"{base}/{data_url.lstrip('/')}"

        nome_arquivo = os.path.basename(data_url.split("?")[0]) or f"anexo.{kind}"
        ext = os.path.splitext(nome_arquivo)[1].lower().lstrip(".")
        if kind in ("audio", "video"):
            # extensao que o Whisper reconhece (voice WhatsApp = ogg/opus; video = mp4/webm)
            if ext not in ("ogg", "oga", "mp3", "m4a", "wav", "webm", "mp4", "mpga", "mpeg", "flac"):
                ext = "mp4" if kind == "video" else "ogg"
            if ext == "oga":
                ext = "ogg"

        import aiohttp  # noqa: PLC0415 — lazy, padrao da casa

        headers = {"api_access_token": os.getenv("CHATWOOT_API_TOKEN", "")}
        async with (
            aiohttp.ClientSession() as session,
            session.get(data_url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp,
        ):
            if resp.status != 200:
                logger.warning("Webhook Chatwoot: download de audio HTTP %s (%s)", resp.status, data_url[:120])
                return None
            if resp.content_length and resp.content_length > _AUDIO_MAX_BYTES:
                logger.warning("Webhook Chatwoot: audio excede %sMB — ignorado", _AUDIO_MAX_BYTES // 1048576)
                return None
            # Lê o CORPO COMPLETO em chunks. (resp.content.read(N) faz leitura PARCIAL em arquivos
            # multi-chunk -> documento TRUNCADO: DOCX vira "not a zip", PDF/PPTX/XLSX vêm vazios.
            # Áudio/imagem menores passavam por sorte. Cap de tamanho mantido.)
            audio_bytes = b""
            async for _chunk in resp.content.iter_chunked(65536):
                audio_bytes += _chunk
                if len(audio_bytes) > _AUDIO_MAX_BYTES:
                    logger.warning("Webhook Chatwoot: anexo excede %sMB — ignorado", _AUDIO_MAX_BYTES // 1048576)
                    return None
        if not audio_bytes:
            return None

        from openai import AsyncOpenAI  # noqa: PLC0415 — lazy, mesma chave do agente

        # timeout explícito: STT/visão roda no caminho síncrono do webhook; sem teto, um
        # anexo problemático seguraria o handler (default SDK 600s) e o Chatwoot reentregaria.
        _stt_to = float(os.getenv("AGENT_OPENAI_TIMEOUT", "90") or 90)
        client = AsyncOpenAI(timeout=_stt_to)

        # ===== IMAGEM: descreve via visao do modelo =====
        if kind == "image":
            import base64  # noqa: PLC0415

            mime = "image/png" if ext == "png" else "image/jpeg"
            b64 = base64.b64encode(audio_bytes).decode()
            vis = await client.chat.completions.create(
                model=os.getenv("OPENAI_AGENT_MODEL", "gpt-5.1"),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Descreva esta imagem enviada por um cliente num atendimento de "
                                    "seguranca/portaria (Conecta Mais, Manaus). Foque no que importa p/ "
                                    "o atendimento: equipamento/defeito, local, documento, fachada etc. "
                                    "Maximo 4 frases, em portugues."
                                ),
                            },
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                        ],
                    }
                ],
                max_completion_tokens=220,
            )
            desc = (vis.choices[0].message.content or "").strip()
            if not desc:
                return None
            logger.info("Webhook Chatwoot: imagem descrita (%s chars)", len(desc))
            return f"🖼 [imagem recebida]: {desc}"

        # ===== DOCUMENTO: extrai texto (PDF/DOCX/TXT) =====
        if kind == "doc":
            texto_doc = ""
            try:
                if ext == "pdf" or audio_bytes[:4] == b"%PDF":
                    import fitz  # noqa: PLC0415 — PyMuPDF

                    with fitz.open(stream=audio_bytes, filetype="pdf") as pdf:
                        texto_doc = "\n".join(p.get_text() for p in pdf[:8])  # ate 8 paginas
                elif ext == "docx":
                    import io  # noqa: PLC0415

                    from docx import Document  # noqa: PLC0415

                    d = Document(io.BytesIO(audio_bytes))
                    texto_doc = "\n".join(p.text for p in d.paragraphs)
                elif ext in ("txt", "csv"):
                    texto_doc = audio_bytes.decode("utf-8", errors="replace")
                elif ext in ("xlsx", "xlsm", "xls") or audio_bytes[:2] == b"PK" and "spreadsheet" in ctype:
                    import io  # noqa: PLC0415

                    from openpyxl import load_workbook  # noqa: PLC0415

                    wb = load_workbook(io.BytesIO(audio_bytes), read_only=True, data_only=True)
                    partes = []
                    for ws in wb.worksheets[:5]:
                        partes.append(f"[planilha: {ws.title}]")
                        for i, row in enumerate(ws.iter_rows(values_only=True)):
                            if i >= 300:
                                break
                            cells = [str(c) for c in row if c is not None]
                            if cells:
                                partes.append(" | ".join(cells))
                    texto_doc = "\n".join(partes)
                elif ext == "pptx" or (audio_bytes[:2] == b"PK" and "presentation" in ctype):
                    import io  # noqa: PLC0415

                    from pptx import Presentation  # noqa: PLC0415

                    prs = Presentation(io.BytesIO(audio_bytes))
                    partes = []
                    for si, slide in enumerate(prs.slides):
                        if si >= 40:
                            break
                        for shape in slide.shapes:
                            if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
                                partes.append(shape.text_frame.text.strip())
                    texto_doc = "\n".join(partes)
            except Exception as e:  # noqa: BLE001
                logger.warning("Webhook Chatwoot: falha ao extrair doc %s: %s", nome_arquivo, e)
                return None
            texto_doc = " ".join(texto_doc.split())[:9000]
            if not texto_doc:
                return None
            logger.info("Webhook Chatwoot: doc '%s' extraido (%s chars)", nome_arquivo, len(texto_doc))
            return f"📎 [arquivo recebido '{nome_arquivo}' — conteúdo]: {texto_doc}"

        # ===== AUDIO/VIDEO: Whisper transcreve a fala =====
        tr = await client.audio.transcriptions.create(
            model="whisper-1",
            file=(f"audio.{ext}", audio_bytes),
            language="pt",
            temperature=0,
            # Vies de vocabulario: portugues de Manaus + termos do negocio + bairros.
            # Reduz erros como "parque dez" -> "Parque Delhi".
            prompt=(
                "Atendimento da Conecta Mais em Manaus, Amazonas. Termos: agente de "
                "portaria, AGP, portaria remota, condominio, sindico, CFTV, cameras, "
                "controle de acesso, visita tecnica, orcamento, posto 24 horas. "
                "Bairros de Manaus: Parque Dez de Novembro, Adrianopolis, Aleixo, "
                "Cidade Nova, Compensa, Flores, Ponta Negra, Centro, Japiim, Coroado, "
                "Dom Pedro, Alvorada, Tarumã, Vieiralves, Nossa Senhora das Gracas. "
                "Datas no formato dia e mes, por exemplo: doze de junho."
            ),
        )
        texto = (getattr(tr, "text", "") or "").strip()
        if not texto:
            logger.info("Webhook Chatwoot: transcricao vazia para %s", data_url[:120])
            return None
        logger.info("Webhook Chatwoot: %s transcrito (%s chars)", kind, len(texto))
        if kind == "video":
            return f"🎥 [vídeo recebido — fala transcrita]: {texto}"
        return f"🎤 [áudio transcrito]: {texto}"
    except Exception as e:  # noqa: BLE001 — best-effort: midia nunca derruba o webhook
        logger.error("Webhook Chatwoot: falha ao processar midia (segue sem conteudo): %s", e)
        return None


@router.get("/agent/dashboard")
async def agent_dashboard(
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    dias: int = 14,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Dashboard do José Luís: conversas, mensagens, leads e conversoes por dia."""
    dias = max(1, min(dias, 90))
    por_dia = (
        await db.execute(
            text(
                """
                SELECT d::date AS dia,
                  (SELECT count(*) FROM cwi_message_log m WHERE m.created_at::date=d::date AND m.direction='in')  AS msgs_recebidas,
                  (SELECT count(*) FROM cwi_message_log m WHERE m.created_at::date=d::date AND m.direction='drf') AS respostas_geradas,
                  (SELECT count(DISTINCT m.chatwoot_conversation_id) FROM cwi_message_log m
                    WHERE m.created_at::date=d::date AND m.direction IN ('in','out'))                              AS conversas_ativas,
                  (SELECT count(*) FROM leads l WHERE l.created_at::date=d::date AND l.source='whatsapp')          AS leads_novos,
                  (SELECT count(*) FROM visitas v WHERE v.created_at::date=d::date AND v.lead_id IS NOT NULL)      AS visitas_solicitadas,
                  (SELECT count(*) FROM ordens_servico s WHERE s.created_at::date=d::date
                    AND s.ticket_sistema='whatsapp')                                                                AS os_abertas
                FROM generate_series(current_date - (:dias - 1) * interval '1 day', current_date, interval '1 day') d
                ORDER BY d DESC
                """
            ),
            {"dias": dias},
        )
    ).fetchall()
    totais = (
        await db.execute(
            text(
                """
                SELECT
                  (SELECT count(*) FROM leads WHERE source='whatsapp')                                  AS leads_whatsapp_total,
                  (SELECT count(*) FROM leads WHERE source='whatsapp' AND status='converted')           AS leads_convertidos,
                  (SELECT count(DISTINCT chatwoot_conversation_id) FROM cwi_message_log
                    WHERE chatwoot_conversation_id IS NOT NULL)                                          AS conversas_total,
                  (SELECT count(*) FROM cwi_message_log WHERE direction='drf')                           AS respostas_geradas_total,
                  (SELECT count(*) FROM cwi_message_log WHERE direction='mem')                           AS memorias_de_cliente,
                  (SELECT count(*) FROM visitas WHERE lead_id IS NOT NULL)                               AS visitas_de_leads,
                  (SELECT count(*) FROM ordens_servico WHERE ticket_sistema='whatsapp') AS os_abertas_pelo_agente
                """
            )
        )
    ).first()
    # Métricas de funil/qualificação + conversas frias (onde os leads esfriam)
    metr = (
        await db.execute(
            text(
                """
                SELECT
                  count(*) FILTER (WHERE source='whatsapp') AS leads,
                  count(*) FILTER (WHERE source='whatsapp' AND qualificacao ? 'segmento') AS qualificados,
                  count(*) FILTER (WHERE source='whatsapp' AND coalesce(notes,'') ILIKE '%CNPJ%') AS com_cnpj,
                  count(*) FILTER (WHERE source='whatsapp' AND EXISTS(SELECT 1 FROM visitas v WHERE v.lead_id=leads.id)) AS com_visita,
                  count(*) FILTER (WHERE source='whatsapp' AND
                    (CASE WHEN qualificacao->>'score_lead' ~ '^[0-9]+$'
                          THEN (qualificacao->>'score_lead')::int ELSE 0 END) >= 60) AS quentes
                FROM leads
                """
            )
        )
    ).first()
    frias = (
        await db.execute(
            text(
                """
                SELECT count(*) FROM (
                  SELECT chatwoot_conversation_id FROM cwi_message_log
                  WHERE direction IN ('in','out') AND chatwoot_conversation_id IS NOT NULL
                  GROUP BY chatwoot_conversation_id
                  HAVING max(created_at) < now() - interval '2 days'
                     AND max(created_at) > now() - interval '30 days'
                ) t
                """
            )
        )
    ).scalar()
    # A/B de abordagens (variante = conversa par(A)/ímpar(B)); conversão = chegou a visita
    ab = (
        await db.execute(
            text(
                """
                SELECT (m.chatwoot_conversation_id % 2) AS v,
                       count(DISTINCT m.chatwoot_conversation_id) AS conversas,
                       count(DISTINCT vi.id) AS visitas
                FROM cwi_message_log m
                LEFT JOIN leads l ON regexp_replace(coalesce(l.phone,''),'\\D','','g') = m.phone_canonical
                LEFT JOIN visitas vi ON vi.lead_id = l.id
                WHERE m.chatwoot_conversation_id IS NOT NULL AND m.direction IN ('in','out')
                GROUP BY (m.chatwoot_conversation_id % 2)
                """
            )
        )
    ).fetchall()
    ab_map = {int(v): {"conversas": c, "visitas": vis} for v, c, vis in ab}

    def _taxa(num, den):
        return round(num / den * 100, 1) if den else 0.0

    return {
        "agente": "José Luís",
        "periodo_dias": dias,
        "totais": {
            "conversas": totais[2],
            "respostas_geradas": totais[3],
            "leads_whatsapp": totais[0],
            "leads_convertidos": totais[1],
            "memorias_de_cliente": totais[4],
            "visitas_solicitadas": totais[5],
            "os_abertas_pelo_agente": totais[6],
        },
        "metricas": {
            "taxa_qualificacao_pct": _taxa(metr[1], metr[0]),
            "conversas_frias": frias or 0,
            "leads_quentes": metr[4],
            "funil": {
                "leads": metr[0],
                "qualificados": metr[1],
                "com_cnpj": metr[2],
                "com_visita": metr[3],
            },
        },
        "ab_test": {
            "A_cnpj_cedo": {
                **ab_map.get(0, {"conversas": 0, "visitas": 0}),
                "taxa_visita_pct": _taxa(ab_map.get(0, {}).get("visitas", 0), ab_map.get(0, {}).get("conversas", 0)),
            },
            "B_necessidade_primeiro": {
                **ab_map.get(1, {"conversas": 0, "visitas": 0}),
                "taxa_visita_pct": _taxa(ab_map.get(1, {}).get("visitas", 0), ab_map.get(1, {}).get("conversas", 0)),
            },
        },
        "por_dia": [
            {
                "dia": str(r[0]),
                "mensagens_recebidas": r[1],
                "respostas_geradas": r[2],
                "conversas_ativas": r[3],
                "leads_novos": r[4],
                "visitas_solicitadas": r[5],
                "os_abertas": r[6],
            }
            for r in por_dia
        ],
    }


def _read_webhook_secret() -> str:
    """Segredo esperado: env (futuro rebuild) ou arquivo (docker cp no container atual)."""
    return os.getenv("WHATSAPP_WEBHOOK_SECRET", "") or _read_secret_file("/app/.whatsapp_webhook_secret")


# Extração de coordenadas de links/textos de mapa (Google Maps, Apple, geo:, lat,lng cru).
_MAPS_URL_RE = re.compile(
    r"https?://[^\s]*(?:google\.[^/\s]+/maps|maps\.google|maps\.app\.goo\.gl|goo\.gl/maps|"
    r"maps\.apple\.com|waze\.com)[^\s]*",
    re.I,
)
_LATLNG_PATTERNS = [
    re.compile(r"@(-?\d{1,3}\.\d{3,}),(-?\d{1,3}\.\d{3,})"),
    re.compile(r"!3d(-?\d{1,3}\.\d{3,})!4d(-?\d{1,3}\.\d{3,})"),
    re.compile(r"[?&](?:q|ll|center|destination|sll|daddr)=(-?\d{1,3}\.\d{3,}),(-?\d{1,3}\.\d{3,})", re.I),
    re.compile(r"[?&]ll=(-?\d{1,3}\.\d{3,}),(-?\d{1,3}\.\d{3,})", re.I),
    re.compile(r"geo:(-?\d{1,3}\.\d{3,}),(-?\d{1,3}\.\d{3,})", re.I),
]
_RAW_LATLNG_RE = re.compile(r"(?<![\d.])(-?\d{1,2}\.\d{4,})\s*,\s*(-?\d{1,3}\.\d{4,})(?![\d.])")


def _extrair_coords(texto: str) -> tuple[str, str] | None:
    for pat in _LATLNG_PATTERNS:
        m = pat.search(texto)
        if m:
            return m.group(1), m.group(2)
    m = _RAW_LATLNG_RE.search(texto)
    if m:
        return m.group(1), m.group(2)
    return None


async def _resolver_localizacao(content: str) -> str | None:
    """Resolve link de mapa / coordenadas no texto -> endereço real (geocodificação reversa).
    Segue redirect de link curto (maps.app.goo.gl) e consulta o Nominatim (OpenStreetMap, grátis).
    Retorna a linha "📍 [...]" para anexar ao content, ou None se não houver localização."""
    import aiohttp  # noqa: PLC0415

    coords = _extrair_coords(content)
    url_m = _MAPS_URL_RE.search(content)
    # link curto sem coords visíveis -> segue o redirect p/ a URL completa
    if not coords and url_m:
        url = url_m.group(0)
        try:
            async with (
                aiohttp.ClientSession() as s,
                s.get(
                    url,
                    allow_redirects=True,
                    timeout=aiohttp.ClientTimeout(total=12),
                    headers={"User-Agent": "Mozilla/5.0 ConectaMais/1.0"},
                ) as r,
            ):
                final = str(r.url)
                coords = _extrair_coords(final)
                if not coords:
                    body = (await r.text())[:6000]
                    coords = _extrair_coords(body)
        except Exception as e:  # noqa: BLE001
            logger.warning("resolver_localizacao: redirect falhou: %s", e)
    if not coords and not url_m:
        return None
    if not coords:
        # tem link mas não deu p/ extrair coords -> ao menos marca como localização
        return "📍 [localização recebida pelo cliente — use como endereço da visita, não peça rua/número de novo]"

    lat, lng = coords
    endereco = None
    try:
        nomi = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/reverse")
        async with (
            aiohttp.ClientSession() as s,
            s.get(
                nomi,
                params={"lat": lat, "lon": lng, "format": "json", "zoom": "18", "accept-language": "pt-BR"},
                headers={"User-Agent": "ConectaMais-JoseLuis/1.0 (contato@conectamais.pro)"},
                timeout=aiohttp.ClientTimeout(total=12),
            ) as r,
        ):
            if r.status == 200:
                d = await r.json()
                endereco = d.get("display_name")
    except Exception as e:  # noqa: BLE001
        logger.warning("resolver_localizacao: nominatim falhou: %s", e)

    link = f"https://www.google.com/maps?q={lat},{lng}"
    if endereco:
        logger.info("Webhook Chatwoot: localização resolvida -> %s", endereco[:80])
        return (
            f"📍 [localização resolvida — use como endereço da visita, NÃO peça rua/número de "
            f"novo]: {endereco} · coords {lat},{lng} · {link}"
        )
    return f"📍 [localização — coords {lat},{lng} · {link}] (use como endereço da visita)"


@router.post("/webhook")
async def chatwoot_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Recebe eventos do Chatwoot (sem JWT). Loga entrada+saida e cria Lead na entrada.

    Autenticacao por token na URL (`?token=<segredo>`), pois o Chatwoot nao assina
    os webhooks. Idempotente por chatwoot_message_id (UNIQUE em cwi_message_log).
    """
    body = await request.body()

    expected = _read_webhook_secret()
    if expected:
        token = request.query_params.get("token", "")
        if not hmac.compare_digest(token, expected):
            logger.warning("Webhook Chatwoot: token invalido")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido")

    try:
        data = json.loads(body)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload invalido")

    if data.get("event") != "message_created":
        return {"status": "ignored", "event": data.get("event")}

    # Ignora notas privadas (rascunho do agente, notas internas do atendente):
    # nao loga nem reprocessa — evita poluir o historico e gerar loop.
    if data.get("private"):
        return {"status": "ignored_private"}

    msg_id = _safe_int(data.get("id"))
    content = data.get("content")
    mtype = str(data.get("message_type", ""))
    direction = "in" if mtype in ("incoming", "0") else "out"
    conv = data.get("conversation") or {}
    conv_id = _safe_int(conv.get("id") or data.get("conversation_id"))
    sender = data.get("sender") or {}
    meta_sender = (conv.get("meta") or {}).get("sender") or {}
    phone = sender.get("phone_number") or meta_sender.get("phone_number")
    name = sender.get("name") or meta_sender.get("name")
    phone_canonical = _normalize_phone(phone)

    # MULTIMIDIA best-effort: audio/video (Whisper), imagem (visao), documento (PDF/DOCX).
    # O conteudo extraido vira/integra o content (o agente le content do log; fluxo intocado).
    # Com legenda + anexo, combina os dois. Falha -> segue como antes. Nao bloqueia o 200.
    if direction == "in" and data.get("attachments"):
        midia = await _transcrever_audio_attachments(data)
        if midia:
            content = f"{content}\n{midia}" if content else midia

    # Cliente/Jordan colou um link de mapa / coordenadas no TEXTO (não como pin):
    # RESOLVE de verdade — segue o redirect do link curto, extrai as coordenadas e
    # geocodifica reverso (endereço real). Best-effort; falha -> só marca como localização.
    if direction == "in" and content and "📍" not in content:
        try:
            loc = await _resolver_localizacao(content)
            if loc:
                content = f"{content}\n{loc}"
        except Exception as e:  # noqa: BLE001 — nunca derruba o webhook
            logger.error("Webhook Chatwoot: resolver localização falhou: %s", e)

    lead_id = None
    if direction == "in" and phone_canonical:
        try:
            lead_id = await _match_or_create_lead(db, phone_canonical, name)
        except Exception as e:  # noqa: BLE001 — log nunca deve falhar por causa do lead
            logger.error("Webhook Chatwoot: falha ao criar/achar lead: %s", e)

    # INSERT do log protegido: payload hostil (tipo inesperado, tamanho) NUNCA pode dar 500
    # (senão o Chatwoot reenvia o mesmo payload venenoso em loop). Best-effort, como o resto.
    try:
        await db.execute(
            text(
                "INSERT INTO cwi_message_log "
                "(direction, phone_canonical, chatwoot_conversation_id, chatwoot_message_id, content, lead_id, status) "
                "VALUES (:direction, :phone, :conv, :msg, :content, :lead, :status) "
                "ON CONFLICT (chatwoot_message_id) DO NOTHING"
            ),
            {
                "direction": direction,
                "phone": phone_canonical,
                "conv": conv_id,
                "msg": msg_id,
                "content": (content[:30000] if isinstance(content, str) else content),
                "lead": lead_id,
                "status": (str(data.get("status"))[:20] if data.get("status") is not None else None),
            },
        )
        await db.commit()
    except Exception as e:  # noqa: BLE001 — log nunca derruba o webhook (evita loop de reentrega)
        logger.error("Webhook Chatwoot: falha ao gravar log (ignorada): %s", e)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass

    # Resposta a um follow-up do José Luís: liga ao deal, classifica e notifica o Jordan.
    # Best-effort (não derruba o webhook). Opt-out é tratado dentro de link_inbound.
    if direction == "in" and phone_canonical:
        try:
            from modules.crm.services.followups import link_inbound

            await link_inbound(db, phone_canonical, content if isinstance(content, str) else None)
        except Exception as e:  # noqa: BLE001 — follow-up nunca derruba o webhook
            logger.error("Webhook: link_inbound follow-up falhou (ignorada): %s", e)

    # Em mensagem de ENTRADA, agenda o agente em background (nao bloqueia o 200).
    # AGENT_MODE=copilot -> nota privada + rascunho (humano aprova). AGENT_MODE=autonomous
    # -> RESPONDE PUBLICO ao cliente (com guards: grupo/atribuída/transferida -> nao envia).
    # Draft sempre logado em cwi_message_log. So roda se AGENT_ENABLED=true.
    if direction == "in" and conv_id and agent_service.agent_enabled():
        background_tasks.add_task(agent_service.processar_incoming, conv_id, phone_canonical)

    return {"status": "ok", "direction": direction, "lead_id": lead_id, "message_id": msg_id}
