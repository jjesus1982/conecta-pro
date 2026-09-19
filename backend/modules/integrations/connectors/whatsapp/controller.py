"""
WhatsApp Controller — Endpoints REST para envio de mensagens.
"""

import asyncio
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
from core.llm_client import novo_cliente
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


async def _match_or_create_lead(
    db: AsyncSession, phone_canonical: str, name: str | None, texto: str | None = None
) -> str | None:
    """Dedup por telefone normalizado em leads.phone; cria Lead se novo.

    `texto` é o conteúdo da mensagem que disparou a criação — como só criamos quando o
    contato ainda não tem lead, ela é a PRIMEIRA mensagem e carrega o pré-preenchido do
    link wa.me, de onde sai a origem (atribuição de marketing). Sem marcador -> whatsapp.
    """
    # Lock por telefone (advisory transacional): serializa criação concorrente do mesmo
    # contato (2 webhooks simultâneos) -> evita lead duplicado. Auto-libera no commit/rollback.
    try:
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:p)::bigint)"), {"p": phone_canonical})
    except Exception:  # noqa: BLE001 — sem lock é pior, mas não fatal
        pass
    from modules.crm.models.lead import LeadSource
    from modules.crm.repositories.lead_repository import LeadRepository
    from modules.crm.schemas.lead import LeadCreate

    # Dedup via find_duplicate (match_key_br: DDD + 8 últimos dígitos). O SELECT anterior
    # exigia igualdade EXATA dos dígitos — o mesmo contato chegando com/sem nono dígito ou
    # com DDI virava lead novo. Regra agora é a mesma dos outros 9 caminhos.
    existente = await LeadRepository(db).find_duplicate(phone=phone_canonical)
    if existente:
        return str(existente.id)

    from .agent_service import _atribuicao_do_texto

    atrib = _atribuicao_do_texto(texto)
    origem = atrib["source"]
    lead_name = (name or "").strip() or f"WhatsApp {phone_canonical}"
    repo = LeadRepository(db)
    new_id: str | None = None
    try:
        lead = await repo.create(
            LeadCreate(
                name=lead_name[:255],
                email=None,
                phone=phone_canonical,
                source=LeadSource(origem),
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
                    "(gen_random_uuid(),:n,:p,:src,'new',0,0,0,true,now(),now()) RETURNING id"
                ),
                {"n": lead_name[:255], "p": phone_canonical, "src": origem},
            )
        ).scalar()
        new_id = str(lid) if lid else None

    # UTM da campanha, quando o link trouxe `[c:<slug>]`. UPDATE separado de propósito:
    # o LeadCreate não tem esses campos e mexer nele rippla nos 10 pontos de criação de
    # lead. Best-effort — atribuição nunca impede o lead de nascer nem a resposta de sair.
    if new_id and atrib.get("utm_campaign"):
        try:
            await db.execute(
                text(
                    "UPDATE leads SET utm_campaign=:c, utm_source=:s, utm_medium=:m, updated_at=now() "
                    "WHERE id=:i AND utm_campaign IS NULL"  # 1º toque manda: não sobrescreve atribuição
                ),
                {"c": atrib["utm_campaign"], "s": atrib["utm_source"], "m": atrib["utm_medium"], "i": new_id},
            )
            await db.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning("Webhook: UTM não gravada p/ lead=%s: %s", new_id, e)

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


async def _visita_ctx_da_conversa(conv_id: int | None) -> dict | None:
    """empresa/serviço da visita aberta desta conversa — ou None. Nunca levanta.

    É este contexto que faz a VISÃO trocar de olho: sem visita, legenda de atendimento;
    com visita, diagnóstico de projetista. Ver `_prompt_visao`.
    """
    if not conv_id:
        return None
    try:
        import re as _re  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
        from modules.integrations.connectors.whatsapp.agent_service import (  # noqa: PLC0415
            _visita_aberta,
        )

        async with async_session_factory() as db:
            v = await _visita_aberta(db, int(conv_id))
            if not v:
                return None
            md = str(v.get("conteudo_md") or "")
            pega = lambda k: (_re.search(rf"\[{k}:([a-z_]+)\]", md) or [None, None])[1]  # noqa: E731
            return {"id": v["id"], "cliente": v.get("cliente_nome"), "empresa": pega("empresa"), "tipo": pega("tipo")}
    except Exception:  # noqa: BLE001
        logger.exception("[visita] não consegui ler o contexto da visita — visão segue com o prompt de atendimento")
        return None


#: Tetos do vídeo, por env — cada quadro é UMA chamada de visão, e vídeo de 10 min com
#: detecção de cena renderia dezenas. 8 é o meio do intervalo que o desenho previu (8-12).
_VIDEO_MAX_QUADROS = int(os.getenv("AGENT_VIDEO_MAX_QUADROS", "8"))
#: Largura do quadro. Mandar 4K para a visão é desperdício: ela reduz de qualquer jeito.
_VIDEO_LARGURA = int(os.getenv("AGENT_VIDEO_LARGURA", "768"))
#: Limiar de mudança de cena do ffmpeg (0-1). 0.3 separa ambientes (portaria, garagem,
#: hall) sem picar a mesma parede três vezes, que é o que intervalo fixo faria.
_VIDEO_CENA = os.getenv("AGENT_VIDEO_CENA", "0.30")


async def _quadros_do_video(video_bytes: bytes, ext: str, visita_ctx=None) -> str:
    """Extrai quadros por MUDANÇA DE CENA e devolve o que a visão enxergou neles.

    ⚠️ Roda SÓ no worker da fila (`whatsapp.analisar_midia`), nunca no webhook: são N
    chamadas de visão em série e o handler HTTP não sobrevive a isso — foi a lição de uma
    foto que segurou o webhook por 93,8s.

    Arquivo temporário com limpeza garantida no `finally`, e o vídeo NÃO fica inteiro em
    memória mais do que o necessário: esta casa tem histórico de OOM e o worker passou a
    decodificar vídeo.
    """
    import asyncio as _a  # noqa: PLC0415
    import base64 as _b64  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    if not shutil.which("ffmpeg"):
        logger.warning("Webhook Chatwoot: ffmpeg AUSENTE — vídeo entrega só a fala")
        return ""

    tmp = tempfile.mkdtemp(prefix="jl_video_")
    try:
        entrada = os.path.join(tmp, f"in.{(ext or 'mp4')[:4]}")
        with open(entrada, "wb") as f:
            f.write(video_bytes)

        async def _ffmpeg(vf: str, n: int, prefixo: str) -> int:
            proc = await _a.create_subprocess_exec(
                "ffmpeg",
                "-nostdin",
                "-loglevel",
                "error",
                "-i",
                entrada,
                "-vf",
                vf,
                "-vsync",
                "vfr",
                "-frames:v",
                str(n),
                os.path.join(tmp, prefixo + "%02d.jpg"),
                stdout=_a.subprocess.DEVNULL,
                stderr=_a.subprocess.PIPE,
            )
            try:
                await _a.wait_for(proc.communicate(), timeout=120)
            except TimeoutError:
                proc.kill()
                logger.warning("Webhook Chatwoot: ffmpeg estourou 120s")
            return len([x for x in os.listdir(tmp) if x.startswith(prefixo)])

        # ⭐ HÍBRIDO: corte de cena + PISO TEMPORAL. E o piso não é precaução — é o que
        # de fato funciona para o modo de filmar do Jordan. MEDIDO em 28/08/2026 com o
        # vídeo REAL dele (The Sun, 30,9s, ele caminhando e narrando):
        #     limiar 0.30 -> 0 quadros · 0.15 -> 0 quadros · 0.08 -> 1 quadro
        #     piso de 1 a cada 5s -> 6 quadros
        # Ele CAMINHA filmando: não há corte, há variação gradual. A detecção de cena
        # sozinha — que era o meu desenho — entregaria ZERO e o vídeo seguiria valendo só
        # pela fala, que é exatamente o problema de que a gente acabou de sair.
        # Cena continua primeiro porque, quando existe corte, ele marca o momento CERTO.
        n_cena = await _ffmpeg(f"select='gt(scene,{_VIDEO_CENA})',scale={_VIDEO_LARGURA}:-2", _VIDEO_MAX_QUADROS, "q_")
        if n_cena < _VIDEO_MAX_QUADROS:
            # Preenche o resto pelo relógio. Intervalo derivado da DURAÇÃO para cobrir o
            # vídeo inteiro em vez de amontoar no começo.
            dur = 0.0
            try:
                pr = await _a.create_subprocess_exec(
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=nw=1:nk=1",
                    entrada,
                    stdout=_a.subprocess.PIPE,
                    stderr=_a.subprocess.DEVNULL,
                )
                out, _ = await _a.wait_for(pr.communicate(), timeout=30)
                dur = float((out or b"0").decode().strip() or 0)
            except Exception:  # noqa: BLE001
                dur = 0.0
            faltam = _VIDEO_MAX_QUADROS - n_cena
            intervalo = max(2.0, dur / max(faltam, 1)) if dur > 0 else 5.0
            await _ffmpeg(f"fps=1/{intervalo:.2f},scale={_VIDEO_LARGURA}:-2", faltam, "t_")

        quadros = sorted(x for x in os.listdir(tmp) if x.startswith(("q_", "t_")))
        if not quadros:
            logger.warning("Webhook Chatwoot: nenhum quadro extraído do vídeo")
            return ""
        logger.info("Webhook Chatwoot: vídeo -> %s por cena + %s por tempo", n_cena, len(quadros) - n_cena)

        from core.llm_client import modelo_visao  # noqa: PLC0415

        cli = novo_cliente(origem="whatsapp.visao.video", timeout=float(os.getenv("AGENT_OPENAI_TIMEOUT", "90")))
        vistos = []
        for i, nome in enumerate(quadros[:_VIDEO_MAX_QUADROS], 1):
            with open(os.path.join(tmp, nome), "rb") as f:
                b64 = _b64.b64encode(f.read()).decode()
            try:
                r = await cli.chat.completions.create(
                    model=modelo_visao(),
                    # ⚠️ `visita_ctx` VEM POR PARÂMETRO: com visita aberta o quadro vira
                    # diagnóstico de projetista (700 tokens); sem ela, legenda curta. Se eu
                    # tivesse deixado o nome global aqui, todo quadro de vídeo seria legenda
                    # genérica — a diferença entre "um corredor" e "ponto cego no acesso
                    # lateral, sem infraestrutura de energia".
                    max_completion_tokens=(700 if visita_ctx else 220),
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": _prompt_visao(visita_ctx)},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                            ],
                        }
                    ],
                )
                d = (r.choices[0].message.content or "").strip()
                if d:
                    vistos.append(f"[cena {i}] {d}")
            except Exception as e:  # noqa: BLE001 — um quadro ruim não perde o vídeo
                logger.warning("Webhook Chatwoot: quadro %s do vídeo falhou: %s", i, str(e)[:90])
        logger.info("Webhook Chatwoot: vídeo -> %s quadro(s), %s descrito(s)", len(quadros), len(vistos))
        return " ".join(vistos)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def _transcrever_audio_attachments(data: dict, conv_id: int | None = None) -> str | None:
    """STT best-effort: acha attachment de audio, baixa do Chatwoot e transcreve (Whisper).

    Retorna "🎤 [áudio transcrito]: <texto>" ou None. NUNCA levanta excecao —
    qualquer falha loga e retorna None (webhook segue com content vazio, como hoje).
    """
    global _audio_payload_logged  # noqa: PLW0603
    try:
        attachments = data.get("attachments") or []
        if not attachments:
            return None
        _visita_ctx = await _visita_ctx_da_conversa(conv_id)
        _e_func = await _e_funcionario_da_conversa(conv_id) if not _visita_ctx else False

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
                logger.warning("Webhook Chatwoot: download de %s HTTP %s (%s)", kind, resp.status, data_url[:120])
                return f"📎 [{kind} recebido — não consegui baixar o arquivo (HTTP {resp.status})]"
            # ⚠️ 28/08/2026 — ANEXO GRANDE DEIXOU DE SUMIR EM SILÊNCIO. O teto de 16 MB
            # foi dimensionado para ÁUDIO; os vídeos da visita do Jordan vieram com 3,6 a
            # 7,7 MB e passaram raspando. Um vídeo de 2 minutos passa de 16 MB, e até aqui
            # ele era descartado sem uma palavra: o Jordan filmaria o levantamento inteiro
            # e nada apareceria no relatório, sem erro em lugar nenhum.
            # É o terceiro irmão do `if not texto: return None` — a família que engole
            # mídia calada.
            if resp.content_length and resp.content_length > _AUDIO_MAX_BYTES:
                logger.warning("Webhook Chatwoot: %s excede %sMB — ignorado", kind, _AUDIO_MAX_BYTES // 1048576)
                return (
                    f"📎 [{kind} recebido — NÃO analisado: passa de "
                    f"{_AUDIO_MAX_BYTES // 1048576} MB. Peça um trecho mais curto.]"
                )
            # Lê o CORPO COMPLETO em chunks. (resp.content.read(N) faz leitura PARCIAL em arquivos
            # multi-chunk -> documento TRUNCADO: DOCX vira "not a zip", PDF/PPTX/XLSX vêm vazios.
            # Áudio/imagem menores passavam por sorte. Cap de tamanho mantido.)
            audio_bytes = b""
            async for _chunk in resp.content.iter_chunked(65536):
                audio_bytes += _chunk
                if len(audio_bytes) > _AUDIO_MAX_BYTES:
                    logger.warning("Webhook Chatwoot: anexo excede %sMB — ignorado", _AUDIO_MAX_BYTES // 1048576)
                    return (
                        f"📎 [{kind} recebido — NÃO analisado: passa de "
                        f"{_AUDIO_MAX_BYTES // 1048576} MB. Peça um trecho mais curto.]"
                    )
        if not audio_bytes:
            return None

        # timeout explícito: STT/visão roda no caminho síncrono do webhook; sem teto, um
        # anexo problemático seguraria o handler (default SDK 600s) e o Chatwoot reentregaria.
        # ⚠️ 28/08/2026 — TETO PRÓPRIO PARA A MÍDIA, e o número é medido. O Jordan mandou
        # 43 arquivos de uma vez ("aloprei logo, pra testar se presta mesmo"): 40 fotos
        # descritas, ZERO falhas — mas a visão levou **32,3s de média e 75,7s no pior
        # caso**, contra um teto de 90s. Margem de 14 segundos.
        #
        # Os 32s não são lentidão do fornecedor: são o custo do laudo COMPLETO (≈840 chars
        # de diagnóstico + ≈2.300 de raciocínio). O meu 1,2s isolado media outra coisa —
        # uma legenda de 80 tokens.
        #
        # A análise saiu do webhook e vive na FILA, então esperar mais não segura ninguém:
        # o WhatsApp já recebeu 200. Estourar o teto, sim, custa a foto.
        _stt_to = float(os.getenv("AGENT_MIDIA_TIMEOUT", os.getenv("AGENT_OPENAI_TIMEOUT", "90")) or 90)
        client = novo_cliente(origem="whatsapp.stt", timeout=_stt_to, servico="audio")

        # ===== IMAGEM: descreve via visao do modelo =====
        if kind == "image":
            import base64  # noqa: PLC0415

            mime = "image/png" if ext == "png" else "image/jpeg"
            b64 = base64.b64encode(audio_bytes).decode()
            from core.llm_client import modelo_visao  # noqa: PLC0415

            # 🔴 28/08/2026 — A VISÃO NUNCA FUNCIONOU, e a causa é esta linha. O `client`
            # acima nasce com `servico="audio"`, e `llm_client.py:239` manda serviço que
            # não é "chat" para a base da OPENAI de propósito (Whisper só existe lá).
            # Reusar esse cliente aqui pedia à OpenAI um modelo da DeepSeek:
            #   404 — "The model `deepseek-v4-flash-vision-exp` does not exist"
            # 32 fotos do Jordan falharam assim, ao vivo, e a visita do The Sun ficou com
            # `achados: 0`. O modelo EXISTE e responde — o que estava errado era o endereço.
            #
            # ⚠️ Como se descobre: o MESMO modelo, no MESMO container, devolvia 400
            # ("imagem não suportada") pelo cliente de chat e 404 pelo cliente de áudio.
            # Dois erros diferentes para a mesma chamada = a diferença está no cliente,
            # não no modelo. Conferir o nome contra a lista de modelos não denuncia isso:
            # o id está lá.
            cliente_visao = novo_cliente(origem="whatsapp.visao", timeout=_stt_to)
            vis = await cliente_visao.chat.completions.create(
                # modelo de VISÃO: o de texto pode recusar imagem com HTTP 400
                model=modelo_visao(),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (_prompt_visao(_visita_ctx, funcionario=_e_func)),
                            },
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                        ],
                    }
                ],
                # O diagnóstico é mais longo que a legenda — e é ele que vira achado.
                max_completion_tokens=(700 if _visita_ctx else 220),
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
        # ⭐ O NOME DO CLIENTE DA VISITA ENTRA NO VIÉS (28/08/2026). Sem ele o Whisper
        # transcreveu "The Sun" como "Dessan" — e esse nome vira título de proposta. O
        # `_visita_ctx` já viajava até aqui para a visão; usar no ouvido custa uma linha.
        _cli_visita = ((_visita_ctx or {}).get("cliente_nome") or "").strip()
        _vies = (
            "Atendimento da Conecta Mais em Manaus, Amazonas. Termos: agente de "
            "portaria, AGP, portaria remota, condominio, sindico, CFTV, cameras, "
            "controle de acesso, visita tecnica, orcamento, posto 24 horas. "
            "Bairros de Manaus: Parque Dez de Novembro, Adrianopolis, Aleixo, "
            "Cidade Nova, Compensa, Flores, Ponta Negra, Centro, Japiim, Coroado, "
            "Dom Pedro, Alvorada, Tarumã, Vieiralves, Nossa Senhora das Gracas. "
            "Datas no formato dia e mes, por exemplo: doze de junho."
            + (f" Cliente desta visita: {_cli_visita}." if _cli_visita else "")
        )
        tr = await client.audio.transcriptions.create(
            model="whisper-1",
            file=(f"audio.{ext}", audio_bytes),
            language="pt",
            temperature=0,
            # Vies de vocabulario: portugues de Manaus + termos do negocio + bairros.
            # Reduz erros como "parque dez" -> "Parque Delhi".
            prompt=_vies,
        )
        texto = (getattr(tr, "text", "") or "").strip()

        # 🔴 O WHISPER ECOA O PRÓPRIO PROMPT quando o áudio é mudo ou ininteligível.
        # Medido em 28/08/2026: um vídeo do Jordan gravou como FALA dele
        # "Atendimento da Conecta Mais em Manaus, agente de portaria, AGP, portaria
        # remota, condominio," — que é o NOSSO viés, palavra por palavra.
        # Isso é FABRICAÇÃO entrando no levantamento: um achado dizendo que ele falou o
        # que nunca falou, num documento que ele assina. Melhor vídeo só com imagem do
        # que vídeo com fala inventada.
        if texto:
            _pal_vies = set(re.findall(r"\w{4,}", _vies.lower()))
            _pal_txt = re.findall(r"\w{4,}", texto.lower())
            if _pal_txt:
                _sobrep = sum(1 for w in _pal_txt if w in _pal_vies) / len(_pal_txt)
                if _sobrep > 0.8:
                    logger.warning(
                        "Webhook Chatwoot: transcrição é ECO do prompt de viés "
                        "(%.0f%% de sobreposição) — refazendo SEM viés",
                        _sobrep * 100,
                    )
                    # ⭐ 11/09/2026 — DESCARTAR NÃO ERA SUFICIENTE. Descartar protege contra
                    # fabricação, e isso continua valendo; mas quem falou ficou sem resposta.
                    # Medido no primeiro dia da pesquisa de ponto: o ELIZIEL respondeu por
                    # ÁUDIO de 10 KB (2 segundos, provavelmente "sim, estou conseguindo"), o
                    # eco disparou, o texto virou vazio e ele recebeu "não consegui abrir o
                    # conteúdo". A resposta dele à pesquisa se perdeu.
                    # O viés existe para acertar vocabulário (bairro, AGP, nome de cliente) —
                    # num áudio curto ele é justamente o que faz o Whisper ecoar. Então a
                    # segunda tentativa vai SEM viés: perde o vocabulário, ganha o que a
                    # pessoa disse. E se ecoar de novo, aí sim descarta.
                    texto = ""
                    try:
                        _tr2 = await client.audio.transcriptions.create(
                            model="whisper-1",
                            file=(f"audio.{ext}", audio_bytes),
                            language="pt",
                            temperature=0,
                        )
                        _t2 = (getattr(_tr2, "text", "") or "").strip()
                        _p2 = re.findall(r"\w{4,}", _t2.lower())
                        _s2 = (sum(1 for w in _p2 if w in _pal_vies) / len(_p2)) if _p2 else 1.0
                        if _t2 and _s2 <= 0.8:
                            texto = _t2
                            logger.info("Webhook Chatwoot: 2ª tentativa SEM viés recuperou %s caracteres", len(_t2))
                        else:
                            logger.warning(
                                "Webhook Chatwoot: 2ª tentativa também ecoou ou veio "
                                "vazia — aí é áudio mudo mesmo, descartado"
                            )
                    except Exception as _e2:  # noqa: BLE001 — a 2ª tentativa é bônus
                        logger.warning("Webhook Chatwoot: 2ª tentativa sem viés falhou: %s", _e2)

        # O Whisper REPETE trechos em áudio curto. Mesmo vídeo trouxe "Vídeo, garagem 2…"
        # duas vezes na mesma transcrição. Sentença repetida vira uma só, na ordem.
        if texto:
            _vistas, _limpo = set(), []
            for _fr in re.split(r"(?<=[.!?])\s+", texto):
                _ch = _fr.strip().lower()
                if len(_ch) > 12 and _ch in _vistas:
                    continue
                _vistas.add(_ch)
                _limpo.append(_fr.strip())
            texto = " ".join(x for x in _limpo if x)

        if not texto and kind != "video":
            logger.info("Webhook Chatwoot: transcricao vazia para %s", data_url[:120])
            return None
        if texto:
            logger.info("Webhook Chatwoot: %s transcrito (%s chars)", kind, len(texto))

        if kind == "video":
            # ⭐ 28/08/2026 — O VÍDEO PASSA A SER VISTO, não só ouvido. Até aqui os quadros
            # não eram olhados por ninguém: um vídeo mudo percorrendo as câmeras do
            # condomínio produzia exatamente nada, e o Jordan achava que tinha mandado
            # informação. A ideia é dele ("temos /watch no VPS, não dá pra expandir?") e o
            # trabalho é pequeno porque DUAS das três peças já eram nossas: o Whisper acima
            # e o mesmo olho da foto abaixo. Faltava só extrair quadro.
            visto = await _quadros_do_video(audio_bytes, ext, _visita_ctx)
            partes = []
            if texto:
                partes.append(f"FALA: {texto}")
            if visto:
                partes.append(f"IMAGENS: {visto}")
            if not partes:
                return None
            # UM bloco só, de propósito: o relatório precisa da fala e da imagem juntas.
            # Dois eventos separados no histórico fariam o agente tratá-los como coisas
            # diferentes, e é o mesmo instante da visita.
            return "🎥 [vídeo recebido]: " + " · ".join(partes)
        return f"🎤 [áudio transcrito]: {texto}"
    except Exception as e:  # noqa: BLE001 — best-effort: midia nunca derruba o webhook
        logger.error("Webhook Chatwoot: falha ao processar midia (segue sem conteudo): %s", e)
        # ⚠️ 28/08/2026 — a CAUSA precisa sobreviver a este `except`. Ele engole de
        # propósito (anexo ruim não derruba o webhook), e por isso quem chama só sabe
        # "deu None". Sem esta marca, "a conta está sem crédito" chegava ao Jordan como
        # "não consegui interpretar o conteúdo" — e ele tentaria reenviar a foto para
        # sempre, achando que o arquivo era ruim.
        try:
            from modules.integrations.connectors.whatsapp import tasks as _t  # noqa: PLC0415

            _msg = str(e).lower()
            _t._ULTIMO_ERRO["sem_credito"] = "credit" in _msg or "insufficient_quota" in _msg or "billing" in _msg
        except Exception:  # noqa: BLE001
            pass
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
        # ⭐ 19/09/2026 — MEDIR ANTES DE CONSTRUIR. O Jordan pediu a confirmação de entrega
        # ("os dois tracinhos") para decidir se uma mensagem chegou, e descobrimos que ela
        # NÃO EXISTE no banco: `cwi_message_log.status` está vazio nas 2.201 saídas, porque
        # este `return` descarta todo evento que não seja `message_created` — e é em
        # `message_updated` que o Chatwoot manda a mudança de status.
        #
        # Só que ninguém sabe se ele manda: o descarte era MUDO. Esta linha não muda
        # comportamento nenhum, só anota o que chega, para a decisão de gravar entrega vir
        # de dado e não de suposição. São ~59 webhooks/dia; o volume de log é irrelevante.
        _ev = data.get("event")
        logger.info("Webhook Chatwoot ignorado: event=%s status=%s", _ev, data.get("status"))
        return {"status": "ignored", "event": _ev}

    # Ignora notas privadas (rascunho do agente, notas internas do atendente):
    # nao loga nem reprocessa — evita poluir o historico e gerar loop.
    if data.get("private"):
        return {"status": "ignored_private"}

    msg_id = _safe_int(data.get("id"))
    from modules.integrations.connectors.whatsapp.tasks import (  # noqa: PLC0415
        MARCA_ANALISE as _MARCA_ANALISE,
    )

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
    _midia_enfileirada = 0
    if direction == "in" and data.get("attachments"):
        # ⭐ 28/08/2026 — a análise SAIU do webhook. Medido: foto ~1,2s, mas o único vídeo
        # que o Jordan mandou levou 93,8s e devolveu ZERO — acima do teto de 90s do
        # caminho. E a rotina diária dele passa a ser mandar as fotos e vídeos da visita.
        #
        # Aqui só marcamos o lugar; a descrição chega depois, pela task, que COMPLETA esta
        # mesma linha do log. A marca não é enfeite: sem ela o agente leria a mensagem sem
        # sinal de que veio anexo.
        _n = len([x for x in (data.get("attachments") or []) if x])
        content = f"{content}\n{_MARCA_ANALISE}" if content else _MARCA_ANALISE
        _midia_enfileirada = _n
        # (A colagem na VISITA ABERTA mudou de lugar: acontece na task, depois da
        # análise. O motivo é o mesmo de sempre — o Jordan em campo manda 15 fotos
        # seguidas e a foto que ninguém anotar é justamente a que faz falta.)

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
            # ⏱️ TETO. 31/08/2026: o Chatwoot corta o webhook em 5s (`Net::ReadTimeout`) e
            # devolve 499 ao nginx — a mensagem do Jordan simplesmente NÃO CHEGAVA, com
            # tudo verde dos dois lados. Medido: `_match_or_create_lead` levava **2,28s**
            # sozinho, e somado ao resto do handler estourava o corte. Os webhooks que
            # funcionavam eram de SAÍDA, que não passam por aqui — por isso o canal parecia
            # vivo enquanto a entrada estava morta.
            #
            # Casar lead é ACESSÓRIO; registrar a mensagem e enfileirar é o essencial.
            # Perder o vínculo de lead custa um campo; perder a mensagem custa a conversa.
            # ponytail: teto aqui resolve hoje — o certo é mover para a fila, como já foi
            # feito com a análise de mídia.
            # 11/09/2026 — QUEM É DA CASA NÃO VIRA LEAD. Medido nas 2.074 mensagens: dos 98
            # números que falaram com o José Luís, 64 são de FUNCIONÁRIOS e 25 já tinham virado
            # lead. O caminho de identidade era só este, e ele ou casa um lead ou CRIA um.
            #
            # Um porteiro perguntando do ponto não pode virar oportunidade no funil — e foi assim
            # que o Rene, agente de portaria do Villa Dei Fiori, ouviu "me confirma o CNPJ do
            # condomínio" depois de dizer que não conseguia assinar os documentos dele.
            from .identidade import quem_e

            _ident = await asyncio.wait_for(quem_e(db, phone_canonical), timeout=1.0)
            if _ident.e_da_casa:
                logger.info("Webhook: %s é %s (%s) — não crio lead", phone_canonical, _ident.tipo, _ident.nome)
            else:
                lead_id = await asyncio.wait_for(_match_or_create_lead(db, phone_canonical, name, content), timeout=1.5)
        except TimeoutError:
            logger.error(
                "Webhook Chatwoot: casamento de lead passou de 1,5s — SEGUINDO SEM "
                "ele para não estourar o timeout do Chatwoot (fone=%s)",
                phone_canonical,
            )
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
    # A análise da mídia é enfileirada DEPOIS do insert: a task completa a linha que
    # acabou de ser gravada, e por isso ela precisa existir.
    if _midia_enfileirada and conv_id:
        try:
            from core.cache.redis import get_redis  # noqa: PLC0415
            from modules.integrations.connectors.whatsapp.tasks import (  # noqa: PLC0415
                analisar_midia,
            )

            # Contador da rajada: enquanto > 0, `processar_incoming` ADIA. É a trava que
            # impede o agente de responder sobre uma foto que ainda não foi vista — e ele
            # DIRIA que viu, que é pior do que demorar.
            _r = await get_redis()
            _pend = await _r.incr(f"jl:midia:conv:{conv_id}")
            await _r.expire(f"jl:midia:conv:{conv_id}", 1800)
            # ⭐ RAJADA GRANDE AVISA NA HORA. Medido em 28/08: 43 anexos × ~32s cada, com
            # 2 em paralelo, dá ~11 minutos até a resposta. Sem uma palavra nesse intervalo,
            # o Jordan lê como travado — que é exatamente o que ele leu hoje de manhã, e
            # naquele dia ELE ESTAVA CERTO. Silêncio parcial e silêncio total parecem iguais
            # de fora.
            # Uma mensagem só, na 8ª: antes disso a resposta chega rápido e o aviso vira
            # ruído. A flag impede repetir a cada anexo da mesma rajada.
            if _pend == 8 and not await _r.get(f"jl:avisei:conv:{conv_id}"):
                await _r.set(f"jl:avisei:conv:{conv_id}", "1", ex=1800)
                from modules.integrations.connectors.whatsapp.agent_service import (  # noqa: PLC0415
                    _post_public_reply,
                )

                await _post_public_reply(
                    conv_id,
                    "Recebi um lote grande de arquivos e estou analisando um por um — cada "
                    "foto vira um diagnóstico, então leva alguns minutos. Pode continuar "
                    "mandando; eu respondo com tudo quando terminar. 👍",
                )
            analisar_midia.apply_async(args=[conv_id, msg_id, data, phone_canonical], queue="webhooks", priority=8)
        except Exception as e:  # noqa: BLE001
            logger.error(
                "Webhook: não consegui enfileirar a mídia (%s) — analisando INLINE, que é lento mas não perde", e
            )
            midia = await _transcrever_audio_attachments(data, conv_id)
            if midia:
                await db.execute(
                    text(
                        "UPDATE cwi_message_log SET content = replace(content, :m, :t) WHERE chatwoot_message_id = :i"
                    ),
                    {"m": _MARCA_ANALISE, "t": midia[:20000], "i": msg_id},
                )
                await db.commit()
                await _midia_para_visita_aberta(conv_id, midia)

    if direction == "in" and conv_id and agent_service.agent_enabled():
        # ⭐ 28/08/2026 — ERA `background_tasks.add_task(...)`, e foi assim que o Jordan
        # mandou SEIS mensagens e um PDF às 16:14 e não recebeu nada. `BackgroundTasks`
        # roda DENTRO deste processo, depois do 200 que já saiu para o Chatwoot: o deploy
        # troca o container, a tarefa morre sem log, e o Chatwoot nunca reenvia porque
        # recebeu 200. Cinco bakes naquele dia = cinco janelas de silêncio.
        #
        # Agora vai para fila DURÁVEL (Redis), sobrevive à troca de container e é
        # reentregue se o worker morrer no meio.
        try:
            from modules.integrations.connectors.whatsapp.tasks import (  # noqa: PLC0415
                processar_incoming_task,
            )

            processar_incoming_task.apply_async(args=[conv_id, phone_canonical], queue="webhooks", priority=8)
        except Exception as e:  # noqa: BLE001
            # Redis fora do ar não pode calar o agente: cai no comportamento antigo, que é
            # pior mas não é nada. E o AVISO fica no log — falha silenciosa aqui é
            # exatamente o defeito que este bloco existe para consertar.
            logger.error("Webhook: fila indisponível (%s) — caindo para BackgroundTasks, que NÃO sobrevive a deploy", e)
            background_tasks.add_task(agent_service.processar_incoming, conv_id, phone_canonical)

    return {"status": "ok", "direction": direction, "lead_id": lead_id, "message_id": msg_id}


async def _midia_para_visita_aberta(conversation_id: int | None, midia: str) -> None:
    """Cola a mídia recebida na visita aberta desta conversa, como ACHADO tipado.

    Só faz efeito quando há visita aberta (o dono chamou `abrir_visita`). Fora disso é
    no-op silencioso — mídia de conversa com cliente não vira registro de visita.

    NUNCA levanta: o webhook tem de devolver 200. Uma falha aqui perde UMA anotação;
    uma exceção perderia a mensagem inteira e o Chatwoot reentregaria em laço.

    O `tipo` sai do prefixo que `_transcrever_audio_attachments` já coloca — a estrutura
    de `achados` (array de {tipo, descricao}) sempre teve 'foto' entre os tipos; o que
    faltava era alguém preencher.
    """
    if not conversation_id or not midia:
        return
    tipo = (
        "foto"
        if midia.startswith("🖼")
        else "local"
        if midia.startswith("📍")
        else "audio"
        if midia.startswith("🎤")
        else "video"
        if midia.startswith("🎬")
        else "documento"
    )
    try:
        from core.database import async_session_factory  # noqa: PLC0415
        from modules.crm.services.visit_reports import adicionar_achados  # noqa: PLC0415
        from modules.integrations.connectors.whatsapp.agent_service import (  # noqa: PLC0415
            _visita_aberta,
        )

        async with async_session_factory() as db:
            v = await _visita_aberta(db, int(conversation_id))
            if not v:
                return
            # Guarda o texto JÁ EXTRAÍDO, não o link: o link do Chatwoot expira e o
            # relatório ficaria com uma referência morta. O que serve no relatório é o
            # que a foto MOSTRA, e isso a visão já produziu.
            # O serviço já aceita {tipo, descricao} — é assim que se declara o tipo, e
            # não com um parâmetro `tipo=` que ele nunca teve. Passar string vira 'nota'
            # e a foto perderia a natureza no relatório.
            await adicionar_achados(db, str(v["id"]), [{"tipo": tipo, "descricao": midia}])
            logger.info("[visita] mídia (%s) anexada à visita %s", tipo, v["id"])
    except Exception:  # noqa: BLE001
        logger.exception("[visita] falha ao anexar mídia à visita aberta — a mensagem segue normalmente")


async def _e_funcionario_da_conversa(conv_id: int | None) -> bool:
    """Quem mandou a foto é da casa? Decide o OLHO da visão, não o conteúdo da resposta.

    O print que o porteiro manda é uma TELA com mensagem de erro; descrevê-lo como
    "equipamento/defeito, local, fachada" devolve "captura de tela de um aplicativo" e
    perde justamente a frase que resolve o caso.
    """
    if not conv_id:
        return False
    try:
        from core.database import async_session_factory  # noqa: PLC0415

        from .identidade import quem_e  # noqa: PLC0415

        async with async_session_factory() as db:
            fone = (
                await db.execute(
                    text(
                        "SELECT phone_canonical FROM cwi_message_log WHERE chatwoot_conversation_id=:c "
                        "AND phone_canonical IS NOT NULL ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"c": conv_id},
                )
            ).scalar()
            try:
                from modules.crm.services.orchestration import is_owner  # noqa: PLC0415

                if is_owner(fone):
                    return False  # o dono tem employee_id; o olho dele é o da visita
            except Exception:  # noqa: BLE001
                pass
            return (await quem_e(db, fone)).tipo == "funcionario"
    except Exception:  # noqa: BLE001 — visão não pode cair por causa da identidade
        return False


def _prompt_visao(visita_ctx: dict | None, funcionario: bool = False) -> str:
    """O que perguntar à VISÃO. Legenda quando é atendimento; DIAGNÓSTICO quando é visita.

    ⭐ Este é o ponto em que a foto deixa de ser enfeite. O prompt anterior era "Descreva
    esta imagem... máximo 4 frases" — e o Jordan, de pé num condomínio fotografando um
    rack, recebia uma legenda. Visão é a ferramenta mais forte que existe aqui e estava
    sendo usada como quem descreve foto de perfil.

    Numa VISITA ABERTA o olho muda: projetista de segurança eletrônica olhando o local,
    comparando com o PADRÃO DA CASA — que não é norma genérica, é o que as propostas dele
    sempre têm (DPS e aterramento por rack em TODOS os projetos, gabinete IP66 em ponto
    externo, organização e identificação de rack, poste antivandal onde não há onde fixar).

    A última regra é a que impede fabricação: o que não dá para ver, ele DIZ que não dá.
    Foto tremida não vira laudo.
    """
    if funcionario and not visita_ctx:
        # 11/09/2026 — o print do ponto. A ERIKA: "Não consigo registrar meu ponto pelo app
        # conecta pro. Desde o início". O que resolve o caso está ESCRITO na tela dela.
        return (
            "Esta imagem foi enviada por um FUNCIONÁRIO da Conecta Mais (porteiro, "
            "vigilante, ASG) — quase sempre é o PRINT de uma tela do celular. "
            "TRANSCREVA LITERALMENTE toda mensagem de erro, aviso, botão e horário "
            "que aparecerem, entre aspas. Depois, em uma frase, diga o que a tela "
            "mostra (ex.: 'app do ponto recusou o reconhecimento facial'). Se houver "
            "documento (atestado, receita, comprovante), diga o tipo, a data e o "
            "período. Não invente o que não estiver legível: diga 'não dá para ler'."
        )
    if not visita_ctx:
        return (
            "Descreva esta imagem enviada por um cliente num atendimento de "
            "seguranca/portaria (Conecta Mais, Manaus). Foque no que importa p/ o "
            "atendimento: equipamento/defeito, local, documento, fachada etc. "
            "Maximo 4 frases, em portugues."
        )

    emp = visita_ctx.get("empresa") or "indefinida"
    srv = visita_ctx.get("tipo") or "indefinido"
    return (
        "Você é PROJETISTA DE SEGURANÇA ELETRÔNICA da Conecta Mais (Manaus/AM) olhando "
        f"esta foto durante uma VISITA TÉCNICA em andamento (empresa: {emp}, serviço: "
        f"{srv}). Não descreva a foto — DIAGNOSTIQUE o que ela mostra, em português, "
        "assim:\n"
        "1. O QUE EXISTE: equipamento, infraestrutura, estado de conservação. Se der para "
        "ler marca/modelo/quantidade, diga.\n"
        "2. O QUE FALTA pelo padrão da casa (só o que a FOTO permite afirmar): DPS e "
        "aterramento por rack; gabinete IP66 em ponto externo; organização e "
        "identificação de cabo; cabeamento estruturado em vez de coaxial; poste "
        "antivandal onde não há onde fixar; nobreak.\n"
        "3. RISCO VISÍVEL: ponto cego, cabo exposto, acesso desprotegido, improviso "
        "elétrico, oxidação.\n"
        "4. IMPLICA NO ORÇAMENTO: que itens isso puxa (ex.: 'rack sem DPS → DPS + kit de "
        "aterramento').\n"
        "REGRA DURA: o que a foto NÃO permite ver, diga 'não dá para ver na foto'. Não "
        "presuma marca, quantidade nem estado que não esteja visível — este texto vira "
        "achado de visita e pode virar item de proposta."
    )
