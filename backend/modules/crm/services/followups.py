"""Follow-ups comerciais do José Luís (WhatsApp/e-mail) — registro, disparo, compliance e inbound.

Tabela crm_followups (append-friendly): cada toque do José Luís (manual ou de cadência) vira uma
linha com canal/status/agendamento/envio e, depois, a resposta do cliente. Compliance embutido:
- opt-out (crm_followup_optout) — respeita "não quero receber".
- horário comercial (America/Manaus, UTC-4 fixo) — não dispara fora da janela.
- anti-spam — limite de toques por deal/telefone numa janela de tempo.

Nenhum SQL "às cegas": todas as tabelas/colunas foram verificadas no schema antes de escrever.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.crm.services.phone import canonical_br, to_e164_br

logger = logging.getLogger(__name__)

# ── Compliance (configurável por env, com defaults seguros) ──────────────────────────────
_MANAUS = timezone(timedelta(hours=-4))  # America/Manaus, sem DST desde 2008
BIZ_START = int(os.getenv("FOLLOWUP_BIZ_START_HOUR", "8"))
BIZ_END = int(os.getenv("FOLLOWUP_BIZ_END_HOUR", "18"))
BIZ_WEEKDAYS = {0, 1, 2, 3, 4}  # seg-sex (sábado/domingo bloqueados — respeito ao descanso do cliente)
ANTISPAM_WINDOW_H = int(os.getenv("FOLLOWUP_ANTISPAM_WINDOW_H", "20"))
ANTISPAM_MAX = int(os.getenv("FOLLOWUP_ANTISPAM_MAX", "1"))  # máx toques por deal/telefone na janela


def now_manaus() -> datetime:
    return datetime.now(_MANAUS)


def within_business_hours(when: datetime | None = None) -> bool:
    w = when or now_manaus()
    return w.weekday() in BIZ_WEEKDAYS and BIZ_START <= w.hour < BIZ_END


def business_hours_label() -> str:
    return f"seg–sex {BIZ_START:02d}h–{BIZ_END:02d}h (Manaus)"


# ── Opt-out ──────────────────────────────────────────────────────────────────────────────
_OPTOUT_TERMS = (
    "nao quero receber",
    "não quero receber",
    "descadastr",
    "sair da lista",
    "parar de receber",
    "remover meu",
    "nao perturbe",
    "não perturbe",
    "pare de me",
)


def detect_optout(texto: str | None) -> bool:
    t = (texto or "").lower()
    return any(term in t for term in _OPTOUT_TERMS)


async def is_opted_out(db: AsyncSession, phone_canonical: str) -> bool:
    if not phone_canonical:
        return False
    row = (
        await db.execute(
            text("SELECT 1 FROM crm_followup_optout WHERE phone_canonical=:p LIMIT 1"), {"p": phone_canonical}
        )
    ).first()
    return bool(row)


async def add_optout(db: AsyncSession, phone_canonical: str, motivo: str | None = None) -> None:
    if not phone_canonical:
        return
    await db.execute(
        text(
            "INSERT INTO crm_followup_optout (phone_canonical, motivo, created_at) "
            "VALUES (:p, :m, now()) ON CONFLICT (phone_canonical) DO NOTHING"
        ),
        {"p": phone_canonical, "m": (motivo or "")[:500]},
    )
    await db.commit()


# ── Anti-spam ──────────────────────────────────────────────────────────────────────────────
async def recent_touch_count(db: AsyncSession, phone_canonical: str, hours: int = ANTISPAM_WINDOW_H) -> int:
    if not phone_canonical:
        return 0
    row = (
        (
            await db.execute(
                text(
                    "SELECT count(*) c FROM crm_followups "
                    "WHERE phone_canonical=:p AND status IN ('enviado','agendado') "
                    "AND enviado_em >= now() - make_interval(hours => :h)"
                ),
                {"p": phone_canonical, "h": hours},
            )
        )
        .mappings()
        .first()
    )
    return int(row["c"]) if row else 0


# ── Resolução de telefone/entidade ──────────────────────────────────────────────────────────
async def resolve_target(
    db: AsyncSession,
    *,
    deal_id: str | None = None,
    cliente: str | None = None,
    lead_id: str | None = None,
    proposal_id: str | None = None,
) -> dict:
    """Resolve (phone_e164, phone_canonical, nome, ids) a partir de deal/cliente/lead/proposta.
    cliente pode ser o id (uuid) ou o CNPJ/documento."""
    out: dict = {
        "deal_id": deal_id,
        "lead_id": lead_id,
        "proposal_id": proposal_id,
        "cliente_id": None,
        "nome": None,
        "phone_e164": None,
        "phone_canonical": None,
        "fonte": None,
    }
    raw_phone = None

    if proposal_id:
        r = (
            (
                await db.execute(
                    text(
                        "SELECT id, number, client_name, client_phone, client_document, opportunity_id "
                        "FROM proposals WHERE id=:id"
                    ),
                    {"id": proposal_id},
                )
            )
            .mappings()
            .first()
        )
        if r:
            out["nome"] = r["client_name"]
            out["deal_id"] = out["deal_id"] or r["opportunity_id"]
            out["numero_proposta"] = r["number"]
            raw_phone = r["client_phone"]
            out["fonte"] = "proposta"
            # se a proposta não tem telefone, tenta o cliente pelo documento
            if not raw_phone and r["client_document"]:
                cliente = cliente or str(r["client_document"])

    if not raw_phone and deal_id:
        r = (
            (
                await db.execute(
                    text(
                        "SELECT id, contact_name, contact_phone, lead_id, company_name FROM opportunities WHERE id=:id"
                    ),
                    {"id": deal_id},
                )
            )
            .mappings()
            .first()
        )
        if r:
            out["nome"] = out["nome"] or r["contact_name"]
            out["lead_id"] = out["lead_id"] or r["lead_id"]
            raw_phone = r["contact_phone"]
            out["fonte"] = out["fonte"] or "deal"
            if not raw_phone and r["lead_id"]:
                lead_id = lead_id or str(r["lead_id"])

    if not raw_phone and cliente:
        s = str(cliente).strip()
        is_uuid = bool(_re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", s))
        if is_uuid:
            r = (
                (
                    await db.execute(
                        text("SELECT id, name, whatsapp, mobile, phone FROM clients WHERE id=:id"), {"id": s}
                    )
                )
                .mappings()
                .first()
            )
        else:
            doc = "".join(c for c in s if c.isdigit())
            r = (
                (
                    await db.execute(
                        text(
                            "SELECT id, name, whatsapp, mobile, phone FROM clients "
                            "WHERE (length(:d) >= 11 AND regexp_replace(coalesce(document_number,''),'\\D','','g')=:d) "
                            "OR name ILIKE :like ORDER BY (name ILIKE :like) DESC LIMIT 1"
                        ),
                        {"d": doc, "like": f"%{s}%"},
                    )
                )
                .mappings()
                .first()
            )
        if r:
            out["cliente_id"] = out["cliente_id"] or r["id"]
            out["nome"] = out["nome"] or r["name"]
            raw_phone = r["whatsapp"] or r["mobile"] or r["phone"]
            out["fonte"] = out["fonte"] or "cliente"

    if not raw_phone and lead_id:
        r = (
            (await db.execute(text("SELECT id, name, phone FROM leads WHERE id=:id"), {"id": lead_id}))
            .mappings()
            .first()
        )
        if r:
            out["lead_id"] = out["lead_id"] or r["id"]
            out["nome"] = out["nome"] or r["name"]
            raw_phone = r["phone"]
            out["fonte"] = out["fonte"] or "lead"

    out["phone_e164"] = to_e164_br(raw_phone)
    out["phone_canonical"] = canonical_br(raw_phone)
    return out


# ── Registro e disparo ──────────────────────────────────────────────────────────────────────
async def register_followup(
    db: AsyncSession,
    *,
    canal: str,
    mensagem: str,
    status: str,
    phone_e164: str | None,
    phone_canonical: str | None,
    deal_id=None,
    cliente_id=None,
    lead_id=None,
    proposal_id=None,
    template: str | None = None,
    agendado_para=None,
    enviado_em=None,
    conversation_id=None,
    message_id=None,
    criado_por: str | None = None,
    detalhe: str | None = None,
) -> dict:
    row = (
        (
            await db.execute(
                text("""
        INSERT INTO crm_followups
          (id, deal_id, cliente_id, lead_id, proposal_id, phone_e164, phone_canonical, canal,
           template, mensagem, status, agendado_para, enviado_em, chatwoot_conversation_id,
           chatwoot_message_id, criado_por, detalhe, created_at, updated_at)
        VALUES
          (gen_random_uuid(), :deal_id, :cliente_id, :lead_id, :proposal_id, :phone_e164,
           :phone_canonical, :canal, :template, :mensagem, :status, :agendado_para, :enviado_em,
           :conv, :msg, :criado_por, :detalhe, now(), now())
        RETURNING id, status, canal, phone_e164, enviado_em, agendado_para
    """),
                {
                    "deal_id": deal_id,
                    "cliente_id": cliente_id,
                    "lead_id": lead_id,
                    "proposal_id": proposal_id,
                    "phone_e164": phone_e164,
                    "phone_canonical": phone_canonical,
                    "canal": canal,
                    "template": template,
                    "mensagem": mensagem,
                    "status": status,
                    "agendado_para": agendado_para,
                    "enviado_em": enviado_em,
                    "conv": conversation_id,
                    "msg": message_id,
                    "criado_por": criado_por,
                    "detalhe": detalhe,
                },
            )
        )
        .mappings()
        .first()
    )
    await db.commit()
    return dict(row) if row else {}


async def send_followup(
    db: AsyncSession,
    *,
    target: dict,
    mensagem: str,
    canal: str = "whatsapp",
    template: str | None = None,
    deal_id=None,
    proposal_id=None,
    criado_por: str | None = None,
    ignore_business_hours: bool = False,
    ignore_antispam: bool = False,
) -> dict:
    """Aplica compliance e dispara o follow-up; registra em crm_followups. Retorna o resultado."""
    phone_e164 = target.get("phone_e164")
    phone_canonical = target.get("phone_canonical")
    deal_id = deal_id or target.get("deal_id")
    proposal_id = proposal_id or target.get("proposal_id")

    if not phone_e164:
        return {
            "enviado": False,
            "motivo": "sem_telefone",
            "detalhe": "Cliente/lead sem WhatsApp válido. Use cadastrar_whatsapp_cliente.",
        }

    if await is_opted_out(db, phone_canonical):
        await register_followup(
            db,
            canal=canal,
            mensagem=mensagem,
            status="cancelado",
            phone_e164=phone_e164,
            phone_canonical=phone_canonical,
            deal_id=deal_id,
            cliente_id=target.get("cliente_id"),
            lead_id=target.get("lead_id"),
            proposal_id=proposal_id,
            template=template,
            criado_por=criado_por,
            detalhe="opt-out",
        )
        return {"enviado": False, "motivo": "opt_out", "detalhe": "Cliente pediu para não receber."}

    if not ignore_business_hours and not within_business_hours():
        await register_followup(
            db,
            canal=canal,
            mensagem=mensagem,
            status="agendado",
            phone_e164=phone_e164,
            phone_canonical=phone_canonical,
            deal_id=deal_id,
            cliente_id=target.get("cliente_id"),
            lead_id=target.get("lead_id"),
            proposal_id=proposal_id,
            template=template,
            criado_por=criado_por,
            agendado_para=now_manaus(),
            detalhe="fora do horário comercial",
        )
        return {
            "enviado": False,
            "motivo": "fora_horario",
            "detalhe": f"Fora do horário comercial ({business_hours_label()}). Registrado como agendado.",
        }

    if not ignore_antispam and await recent_touch_count(db, phone_canonical) >= ANTISPAM_MAX:
        return {
            "enviado": False,
            "motivo": "anti_spam",
            "detalhe": f"Já houve {ANTISPAM_MAX} toque(s) nas últimas {ANTISPAM_WINDOW_H}h. Aguardando.",
        }

    # Disparo real
    from modules.integrations.connectors.whatsapp.service import whatsapp_service

    res = await whatsapp_service.send_custom(phone_e164, mensagem)
    ok = res.get("status") == "sent"
    rec = await register_followup(
        db,
        canal=canal,
        mensagem=mensagem,
        status=("enviado" if ok else "erro"),
        phone_e164=phone_e164,
        phone_canonical=phone_canonical,
        deal_id=deal_id,
        cliente_id=target.get("cliente_id"),
        lead_id=target.get("lead_id"),
        proposal_id=proposal_id,
        template=template,
        enviado_em=(now_manaus() if ok else None),
        conversation_id=res.get("conversation_id"),
        message_id=res.get("message_id"),
        criado_por=criado_por,
        detalhe=(None if ok else str(res.get("status") or res)[:300]),
    )
    return {
        "enviado": ok,
        "followup_id": rec.get("id"),
        "para": phone_e164,
        "status_envio": res.get("status"),
        "conversation_id": res.get("conversation_id"),
        "nome": target.get("nome"),
    }


# ── Consultas ──────────────────────────────────────────────────────────────────────────────
async def list_pending(db: AsyncSession, limit: int = 50) -> list[dict]:
    rows = (
        (
            await db.execute(
                text("""
        SELECT id, deal_id, cliente_id, lead_id, proposal_id, canal, phone_e164, template,
               left(mensagem, 140) AS mensagem, status, agendado_para, detalhe, created_at
        FROM crm_followups WHERE status='agendado'
        ORDER BY COALESCE(agendado_para, created_at) ASC LIMIT :l
    """),
                {"l": limit},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


async def history(db: AsyncSession, deal_id: str, limit: int = 100) -> list[dict]:
    rows = (
        (
            await db.execute(
                text("""
        SELECT id, canal, phone_e164, template, mensagem, status, agendado_para, enviado_em,
               resposta_texto, resposta_em, classificacao, criado_por, created_at
        FROM crm_followups WHERE deal_id=:d ORDER BY created_at ASC LIMIT :l
    """),
                {"d": deal_id, "l": limit},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


async def register_response(
    db: AsyncSession,
    *,
    deal_id: str | None = None,
    followup_id: str | None = None,
    status: str = "respondido",
    classificacao: str | None = None,
    nota: str | None = None,
) -> dict:
    """Registra o retorno do cliente no follow-up mais recente do deal (ou um followup específico)."""
    where = (
        "id=:fid"
        if followup_id
        else "id = (SELECT id FROM crm_followups WHERE deal_id=:d AND status='enviado' ORDER BY enviado_em DESC NULLS LAST LIMIT 1)"
    )
    row = (
        (
            await db.execute(
                text(f"""
        UPDATE crm_followups SET status=:st, classificacao=COALESCE(:cls, classificacao),
               resposta_texto=COALESCE(:nota, resposta_texto), resposta_em=now(), updated_at=now()
        WHERE {where}
        RETURNING id, deal_id, status, classificacao
    """),
                {"fid": followup_id, "d": deal_id, "st": status, "cls": classificacao, "nota": nota},
            )
        )
        .mappings()
        .first()
    )
    await db.commit()
    return dict(row) if row else {}


# ── Inbound (resposta do cliente) — chamado pelo webhook, best-effort ──────────────────────────
_POSITIVE = (
    "sim",
    "quero",
    "fechar",
    "fechado",
    "vamos",
    "pode",
    "aceito",
    "bora",
    "ok",
    "interesse",
    "gostei",
    "assembleia",
    "agendar",
    "visita",
    "contrato",
)
_NEGATIVE = (
    "nao",
    "não",
    "recus",
    "sem interesse",
    "ja resolvi",
    "já resolvi",
    "outro fornecedor",
    "caro",
    "depois",
    "cancel",
)


def classify_reply(texto: str | None) -> str:
    t = (texto or "").lower()
    if detect_optout(t):
        return "recusou"
    pos = any(w in t for w in _POSITIVE)
    neg = any(w in t for w in _NEGATIVE)
    if pos and not neg:
        return "interessado"
    if neg and not pos:
        return "recusou"
    return "duvida"


# Sinais FORTES de fechamento (lead QUENTE) — pingar o Jordan com urgência.
_HOT = (
    "quero fechar",
    "vamos fechar",
    "fechar contrato",
    "pode fechar",
    "fechado",
    "topo",
    "aceito a proposta",
    "aceitei",
    "pode mandar o contrato",
    "manda o contrato",
    "como faço pra contratar",
    "quero contratar",
    "vamos assinar",
    "pode assinar",
    "está aprovado",
    "tá aprovado",
    "aprovado na assembleia",
    "aprovamos",
    "bora fechar",
)


def is_hot_signal(texto: str | None) -> bool:
    t = (texto or "").lower()
    return any(w in t for w in _HOT)


# Pedido EXPLÍCITO de assinar/fechar agora → José Luís pode mandar o link na hora (modelo
# híbrido). Diferente de is_hot_signal (mera intenção de compra, que pede OK do Jordan antes).
_ASSINAR = (
    "como assino",
    "como faço pra assinar",
    "como faco pra assinar",
    "como faço para assinar",
    "onde assino",
    "quero assinar",
    "vou assinar",
    "manda o link",
    "me manda o link",
    "manda pra assinar",
    "manda para assinar",
    "me manda pra assinar",
    "envia o link",
    "manda o contrato pra assinar",
    "como faço pra fechar",
    "como faco pra fechar",
    "como faço pra contratar",
    "como faco pra contratar",
    "como contrato",
    "quero contratar agora",
    "pode mandar o link",
    "manda aí o link",
    "manda ai o link",
    "link de assinatura",
    "como assinar",
    "quero fechar agora",
    "bora assinar",
    "pode mandar pra assinar",
)


def pede_assinatura(texto: str | None) -> bool:
    """True se o cliente PEDIU explicitamente o link/assinar/contratar agora (não só interesse)."""
    t = (texto or "").lower()
    return any(w in t for w in _ASSINAR)


# Sinais de CHURN / insatisfação (cliente da base em risco) — alertar o Jordan na hora.
_CHURN = (
    "quero cancelar",
    "vou cancelar",
    "cancelar o contrato",
    "rescindir",
    "rescisão",
    "encerrar o contrato",
    "encerrar contrato",
    "distrato",
    "não quero mais",
    "nao quero mais",
    "péssimo",
    "pessimo",
    "insatisfeito",
    "insatisfeita",
    "muito ruim",
    "decepcionado",
    "decepcionada",
    "vou trocar de empresa",
    "trocar de fornecedor",
    "estou pensando em sair",
    "não estou satisfeito",
    "nao estou satisfeito",
    "horrível",
    "horrivel",
    "uma vergonha",
)


def is_churn_signal(texto: str | None) -> bool:
    t = (texto or "").lower()
    return any(w in t for w in _CHURN)


# ---------------------------------------------------------------------------
# SITUAÇÕES SENSÍVEIS — quando o José Luís NÃO deve vender/qualificar/seguir a
# cadência, e sim ACOLHER + ESCALAR pro humano. Cada categoria liga uma "trava"
# de comportamento no agente (mensagem de sistema) e, nas críticas, segura o
# envio autônomo (vai pra nota privada / humano aprova) + alerta o Jordan.
# Determinístico (sem custo de modelo) e best-effort.
# ---------------------------------------------------------------------------
_SIT_EMERGENCIA = (
    "assalto",
    "assaltando",
    "roubo em andamento",
    "estão roubando",
    "estao roubando",
    "invasão",
    "invasao",
    "invadindo",
    "invadiram",
    "arrombamento",
    "arrombaram",
    "incêndio",
    "incendio",
    "pegando fogo",
    "fogo no",
    "explosão",
    "explosao",
    "socorro",
    "emergência",
    "emergencia",
    "tem bandido",
    "homem armado",
    "assaltante",
    "sequestro",
    "refém",
    "refem",
    "estão atirando",
    "tiroteio",
    "alagamento",
    "acabaram de",
    "está acontecendo agora",
    "ta acontecendo agora",
    "acontecendo agora",
)
_SIT_JURIDICO = (
    "advogado",
    "advogada",
    "processar",
    "vou processar",
    "processo judicial",
    "ação judicial",
    "acao judicial",
    "na justiça",
    "na justica",
    "notificação extrajudicial",
    "notificacao extrajudicial",
    "procon",
    "reclame aqui",
    "reclameaqui",
    "ministério público",
    "ministerio publico",
    "ministério do trabalho",
    "ministerio do trabalho",
    "reclamação trabalhista",
    "reclamacao trabalhista",
    "trabalhista",
    "lgpd",
    "meus dados pessoais",
    "imprensa",
    "jornalista",
    "reportagem",
    "matéria",
    "vou expor",
    "vou denunciar",
    "denúncia",
    "denuncia",
    "delegacia",
    "boletim de ocorrência",
)
_SIT_COBRANCA = (
    "cobrança indevida",
    "cobranca indevida",
    "cobraram errado",
    "me cobraram",
    "valor errado",
    "boleto errado",
    "boleto duplicado",
    "fatura errada",
    "cobrança duplicada",
    "cobranca duplicada",
    "estorno",
    "reembolso",
    "me estornem",
    "paguei e",
    "já paguei",
    "ja paguei",
    "negativaram",
    "negativar",
    "serasa",
    "spc",
    "cobrando a mais",
    "cobrança a mais",
)
_SIT_WRONG = (
    "número errado",
    "numero errado",
    "quem é você",
    "quem e voce",
    "quem fala",
    "não conheço",
    "nao conheco",
    "não pedi",
    "nao pedi",
    "não solicitei",
    "nao solicitei",
    "não sou cliente",
    "nao sou cliente",
    "parem de me mandar",
    "pare de me mandar",
    "engano",
    "se enganou",
    "não te conheço",
    "nao te conheco",
)
_SIT_RAIVA = (
    "absurdo",
    "descaso",
    "palhaçada",
    "palhacada",
    "vergonha",
    "ninguém resolve",
    "ninguem resolve",
    "cansei",
    "última vez",
    "ultima vez",
    "péssimo atendimento",
    "pessimo atendimento",
    "uma porcaria",
    "que merda",
    "vão à merda",
    "vao a merda",
    "incompetentes",
    "incompetência",
    "incompetencia",
    "enrolação",
    "enrolacao",
    "me ignoram",
    "ninguém me responde",
    "ninguem me responde",
)


def classify_situacao(texto: str | None) -> str:
    """Classifica uma mensagem de ENTRADA numa situação sensível (ou '').

    Retorna a 1ª categoria que casar, por prioridade de gravidade:
    'emergencia' > 'juridico' > 'cobranca' > 'raiva' > 'wrong_number' > ''.
    Usada para travar venda/cadência e (nas críticas) segurar envio autônomo.
    """
    t = (texto or "").lower()
    if not t:
        return ""
    if any(w in t for w in _SIT_EMERGENCIA):
        return "emergencia"
    if any(w in t for w in _SIT_JURIDICO):
        return "juridico"
    if any(w in t for w in _SIT_COBRANCA):
        return "cobranca"
    if any(w in t for w in _SIT_RAIVA):
        return "raiva"
    if any(w in t for w in _SIT_WRONG):
        return "wrong_number"
    return ""


# Categorias que são delicadas demais p/ resposta autônoma do agente: nessas o
# José Luís NÃO envia sozinho — vira nota privada e o humano (Jordan) assume.
SITUACOES_SEGURAR_HUMANO = frozenset({"emergencia", "juridico"})

# Mensagem-trava injetada no agente por categoria (muda o comportamento na hora).
TRAVA_SITUACAO = {
    "emergencia": (
        "⛔ CONTEXTO CRÍTICO — POSSÍVEL EMERGÊNCIA EM CURSO: o cliente relatou algo que pode ser "
        "um incidente em andamento (assalto, invasão, incêndio, emergência). PARE QUALQUER VENDA/"
        "follow-up. NÃO finja despachar viatura/equipe nem diga que 'já resolvi' ou 'já enviei alguém'. "
        "Seja breve e firme: a PRIORIDADE é a pessoa ligar JÁ para o 190 (risco à vida) e acionar a "
        "central/portaria do local. Você pode dizer que vai AVISAR o responsável da Conecta Mais, que "
        "retorna em seguida — mas NUNCA diga ou dê a entender que despachou viatura, equipe ou que "
        "'já resolveu'/'já está a caminho' (você não controla resposta de campo). NÃO peça CNPJ nem "
        "dado nenhum. Acolha com calma. Um humano assume."
    ),
    "juridico": (
        "⛔ CONTEXTO CRÍTICO — ASSUNTO JURÍDICO/INSTITUCIONAL: o cliente mencionou advogado, processo, "
        "Procon, MP, reclamação trabalhista, LGPD, imprensa/jornalista ou denúncia. NÃO discuta o mérito, "
        "NÃO admita nem negue culpa, NÃO dê parecer jurídico, NÃO prometa nada e NÃO entre em debate. "
        "Acolha em UMA frase, com seriedade e respeito, e diga que vai encaminhar ao responsável da Conecta "
        "Mais que cuida disso e que retornará. Nada de venda. Um humano assume."
    ),
    "cobranca": (
        "⚠️ CONTEXTO — QUESTÃO FINANCEIRA/COBRANÇA: o cliente falou de boleto/fatura/cobrança/estorno. "
        "NÃO confirme valores, NÃO admita erro, NÃO prometa estorno/desconto/abatimento. Acolha, diga que "
        "vai encaminhar ao financeiro pra verificar certinho e retornar. Nada de venda agora."
    ),
    "raiva": (
        "⚠️ CONTEXTO — CLIENTE INSATISFEITO/IRRITADO: PARE de vender, de qualificar e de oferecer material. "
        "NÃO rebata, NÃO se justifique demais, NÃO leve pro pessoal. Acolha de verdade em 1–2 frases e "
        "reconheça o incômodo. Se você ainda NÃO sabe qual é o problema, faça UMA pergunta calma pra "
        "entender o que houve (sem virar interrogatório); então comprometa-se a levar a quem resolve e "
        "retornar. O próximo passo é RESOLVER o problema dele, nunca avançar uma venda."
    ),
    "wrong_number": (
        "⚠️ CONTEXTO — PROVÁVEL ENGANO/NÚMERO ERRADO: a pessoa indica que não te conhece ou não pediu contato. "
        "Peça desculpas com leveza em UMA frase, confirme que NÃO vai mais enviar mensagens, e encerre com "
        "cordialidade. NÃO insista, NÃO tente qualificar nem vender."
    ),
}


import re as _re  # noqa: E402

_NPS_RE = _re.compile(r"\b(10|[0-9])\b")


def parse_nps(texto: str | None) -> int | None:
    """Extrai uma nota 0–10 de uma resposta curta (ex.: '9', 'nota 8', 'daria um 7')."""
    if not texto:
        return None
    m = _NPS_RE.search(texto.strip())
    if not m:
        return None
    n = int(m.group(1))
    return n if 0 <= n <= 10 else None


async def link_inbound(db: AsyncSession, phone_canonical: str, content: str | None) -> dict | None:
    """Liga uma mensagem de ENTRADA a um follow-up enviado, classifica e notifica o Jordan.
    Best-effort: qualquer falha é engolida (nunca derruba o webhook). Retorna o follow-up tocado."""
    if not phone_canonical:
        return None
    # Jordan (dono) falando com o José Luís NÃO é resposta de cliente — é modo gerente (tratado no agente).
    try:
        from modules.crm.services.orchestration import is_owner  # noqa: PLC0415

        if is_owner(phone_canonical):
            return None
    except Exception:  # noqa: BLE001
        pass
    try:
        # opt-out tem prioridade
        if detect_optout(content):
            await add_optout(db, phone_canonical, motivo=(content or "")[:200])

        # CHURN/insatisfação: alerta o Jordan NA HORA (qualquer cliente, mesmo sem follow-up ativo).
        if is_churn_signal(content):
            try:
                from modules.crm.services import orchestration as O  # noqa: PLC0415

                nm = phone_canonical
                rn = (
                    await db.execute(
                        text(
                            "SELECT name FROM clients WHERE regexp_replace(coalesce(whatsapp,phone,''),'\\D','','g') LIKE :p "
                            "LIMIT 1"
                        ),
                        {"p": f"%{phone_canonical[-8:]}%"},
                    )
                ).first()
                if rn and rn[0]:
                    nm = rn[0]
                await O.notify_owner(
                    f"🚨🚨 *RISCO DE CHURN* — {nm}\n“{(content or '')[:280]}”\n\n"
                    f"Cliente sinalizou insatisfação/cancelamento. Quer assumir agora pra reverter?"
                )
            except Exception as e:  # noqa: BLE001
                logger.error("alerta churn falhou: %s", e)

        # Match por últimos 8 dígitos: o toque pode ter sido registrado com o 9º dígito e a
        # resposta chega sem ele (JID do WhatsApp) — senão a resposta não liga à proposta.
        _p8 = "".join(c for c in str(phone_canonical) if c.isdigit())[-8:]
        row = (
            (
                await db.execute(
                    text("""
            SELECT id, deal_id, proposal_id, status, template FROM crm_followups
            WHERE right(regexp_replace(coalesce(phone_canonical,''),'\\D','','g'),8)=:p8 AND status='enviado'
            ORDER BY enviado_em DESC NULLS LAST LIMIT 1
        """),
                    {"p8": _p8},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            return None

        # NPS: se o último toque foi uma pesquisa NPS, captura a nota 0–10.
        if (row.get("template") or "") == "nps":
            nota = parse_nps(content)
            await db.execute(
                text(
                    "UPDATE crm_followups SET status='respondido', classificacao=:c, resposta_texto=:t, "
                    "resposta_em=now(), updated_at=now() WHERE id=:id"
                ),
                {"c": (f"nps:{nota}" if nota is not None else "nps:?"), "t": (content or "")[:2000], "id": row["id"]},
            )
            await db.commit()
            try:
                from modules.crm.services import orchestration as O  # noqa: PLC0415

                if nota is not None:
                    cat = "promotor" if nota >= 9 else ("neutro" if nota >= 7 else "detrator")
                    em = "🟢" if nota >= 9 else ("🟡" if nota >= 7 else "🔴")
                    await O.notify_owner(f"{em} *NPS recebido* — nota *{nota}/10* ({cat})\n“{(content or '')[:200]}”")
            except Exception as e:  # noqa: BLE001
                logger.error("notify NPS falhou: %s", e)
            return {"nps": nota, "followup_id": str(row["id"])}

        cls = classify_reply(content)
        await db.execute(
            text("""
            UPDATE crm_followups SET status='respondido', classificacao=:cls,
                   resposta_texto=:txt, resposta_em=now(), updated_at=now() WHERE id=:id
        """),
            {"cls": cls, "txt": (content or "")[:2000], "id": row["id"]},
        )

        # resposta positiva → move o deal para Negociação
        moved = False
        if cls == "interessado" and row["deal_id"]:
            res = await db.execute(
                text("""
                UPDATE opportunities SET stage='negotiation', updated_at=now()
                WHERE id=:d AND stage NOT IN ('closed_won','closed_lost','negotiation')
            """),
                {"d": row["deal_id"]},
            )
            moved = (res.rowcount or 0) > 0
        await db.commit()

        # atualiza o estado da negociação + avisa o Jordan no WhatsApp dele (tempo real)
        nome = phone_canonical
        try:
            from modules.crm.services import orchestration as O  # noqa: PLC0415 (evita import circular)

            await O.marcar_resposta_cliente(db, phone_canonical, cls, content)
            r2 = (
                await db.execute(
                    text(
                        "SELECT cliente_nome FROM crm_negociacao_state "
                        "WHERE right(regexp_replace(coalesce(phone_canonical,''),'\\D','','g'),8)=:p8 "
                        "ORDER BY updated_at DESC LIMIT 1"
                    ),
                    {"p8": _p8},
                )
            ).first()
            if r2 and r2[0]:
                nome = r2[0]
            # fallback: nome da proposta vinculada ao followup
            if (not r2 or not r2[0]) and row.get("proposal_id"):
                rp = (
                    await db.execute(text("SELECT client_name FROM proposals WHERE id=:p"), {"p": row["proposal_id"]})
                ).first()
                if rp and rp[0]:
                    nome = rp[0]
            quente = is_hot_signal(content)
            if quente:
                # 🔥 lead quente: ping URGENTE pro Jordan fechar.
                tem_prop = bool(row.get("proposal_id"))
                acao = (
                    (
                        f"Quer fechar agora? Responde *manda o link do {nome}* que eu envio o link "
                        f"de assinatura digital pra ele fechar na hora. 🤝"
                    )
                    if tem_prop
                    else (
                        f"Quer assumir agora? (responde *assumo o {nome}* que eu te passo o bastão "
                        f"e paro o follow-up automático)"
                    )
                )
                await O.notify_owner(f"🔥🔥 *{nome}* QUER FECHAR!\n“{(content or '')[:280]}”\n\n{acao}")
            else:
                temp = {
                    "interessado": "🟢 morno/quente",
                    "duvida": "🟡 com dúvida",
                    "recusou": "🔴 esfriou/recusou",
                }.get(cls, "🟡")
                await O.notify_owner(
                    f"📨 *{nome}* respondeu — {temp}\n"
                    f"“{(content or '')[:280]}”\n\n"
                    f"Quer que eu continue o acompanhamento ou você assume? (responde aqui)"
                )
        except Exception as e:  # noqa: BLE001
            logger.error("notify_owner inbound falhou (fallback): %s", e)
            await notify_jordan(f"Resposta de cliente {phone_canonical} ({cls}): {(content or '')[:200]}")
        return {
            "followup_id": str(row["id"]),
            "deal_id": str(row["deal_id"]) if row["deal_id"] else None,
            "classificacao": cls,
            "deal_movido": moved,
        }
    except Exception as e:  # noqa: BLE001 — inbound nunca derruba o webhook
        logger.error("link_inbound falhou (ignorada): %s", e)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


# ── Notificação ao Jordan (best-effort: Telegram → log) ──────────────────────────────────────
async def notify_jordan(message: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "") or os.getenv("TELEGRAM_ALERT_CHAT_ID", "")
    if token and chat:
        try:
            import aiohttp  # noqa: PLC0415

            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat, "text": message},
                    timeout=aiohttp.ClientTimeout(total=15),
                )
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("notify_jordan telegram falhou: %s", e)
    logger.info("[NOTIFY JORDAN] %s", message)
    return False
