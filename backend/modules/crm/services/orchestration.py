"""Orquestração José Luís ↔ Jordan — o José Luís vira o braço-direito de vendas do dono.

- Envio de proposta COMPLETO (e-mail + WhatsApp, citando o e-mail).
- Acompanhamento: registra o estado da negociação por proposta (responsavel jose_luis|jordan).
- Atualiza o Jordan no WhatsApp dele (tempo real) + resumo diário + lembretes de pendência (3d→1x/dia).
- Comandos do dono em linguagem natural (modo gerente do agente): status, pendentes, assumir, devolver,
  reenviar, lembrar.

Número do dono (Jordan): JID real do WhatsApp é 559286465328 (sem o 9); o discável tem o 9. O
webhook grava phone_canonical SEM o DDI 55 → '9286465328'. Aceitamos as duas formas por segurança.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.crm.services import followups as F
from modules.crm.services.phone import canonical_br, to_e164_br

logger = logging.getLogger(__name__)

_MANAUS = timezone(timedelta(hours=-4))

# Jordan: e164 discável (com 9) e os canônicos aceitos (com e sem o 9, sem DDI).
OWNER_E164 = os.getenv("OWNER_WHATSAPP", "+5592986465328")
_OWNER_CANON = {
    c
    for c in {
        canonical_br(OWNER_E164),
        "9286465328",
        "92986465328",
        canonical_br(os.getenv("OWNER_WHATSAPP_ALT", "")) or "",
    }
    if c
}
OWNER_NAME = os.getenv("OWNER_NAME", "Jordan")
REMINDER_AFTER_DAYS = int(os.getenv("OWNER_REMINDER_AFTER_DAYS", "3"))


def now_manaus() -> datetime:
    return datetime.now(_MANAUS)


def is_owner(phone_canonical: str | None) -> bool:
    """True se o telefone (canônico, sem 55) é do Jordan — com ou sem o 9."""
    if not phone_canonical:
        return False
    c = "".join(ch for ch in str(phone_canonical) if ch.isdigit())
    if c.startswith("55") and len(c) > 11:
        c = c[2:]
    return c in _OWNER_CANON


# ── Notificação ao dono (José Luís fala com o Jordan no WhatsApp) ─────────────────────────
async def notify_owner(message: str) -> bool:
    """Manda uma mensagem do José Luís para o WhatsApp do Jordan (com resolução de JID).
    Fallback: Telegram/log (followups.notify_jordan)."""
    try:
        from modules.integrations.connectors.whatsapp.service import whatsapp_service

        res = await whatsapp_service.send_custom(OWNER_E164, message)
        if res.get("status") == "sent":
            return True
    except Exception as e:  # noqa: BLE001
        logger.error("notify_owner WhatsApp falhou: %s", e)
    return await F.notify_jordan(message)


# ── Estado da negociação ──────────────────────────────────────────────────────────────────
async def upsert_negociacao(
    db: AsyncSession,
    *,
    proposal_id,
    cliente_id=None,
    deal_id=None,
    lead_id=None,
    phone_canonical=None,
    cliente_nome=None,
    proposta_enviada_em=None,
    responsavel="jose_luis",
) -> dict:
    row = (
        (
            await db.execute(
                text("""
        INSERT INTO crm_negociacao_state
          (id, proposal_id, cliente_id, deal_id, lead_id, phone_canonical, cliente_nome,
           responsavel, proposta_enviada_em, created_at, updated_at)
        VALUES (gen_random_uuid(), :pid, :cid, :did, :lid, :ph, :nome, :resp, :env, now(), now())
        ON CONFLICT (proposal_id) DO UPDATE SET
          cliente_id=COALESCE(EXCLUDED.cliente_id, crm_negociacao_state.cliente_id),
          deal_id=COALESCE(EXCLUDED.deal_id, crm_negociacao_state.deal_id),
          phone_canonical=COALESCE(EXCLUDED.phone_canonical, crm_negociacao_state.phone_canonical),
          cliente_nome=COALESCE(EXCLUDED.cliente_nome, crm_negociacao_state.cliente_nome),
          proposta_enviada_em=COALESCE(EXCLUDED.proposta_enviada_em, crm_negociacao_state.proposta_enviada_em),
          updated_at=now()
        RETURNING id, proposal_id, cliente_nome, responsavel
    """),
                {
                    "pid": proposal_id,
                    "cid": cliente_id,
                    "did": deal_id,
                    "lid": lead_id,
                    "ph": phone_canonical,
                    "nome": cliente_nome,
                    "resp": responsavel,
                    "env": proposta_enviada_em,
                },
            )
        )
        .mappings()
        .first()
    )
    await db.commit()
    return dict(row) if row else {}


async def _resolve_negociacao(db: AsyncSession, alvo: str) -> dict | None:
    """Acha a negociação por nome do cliente (ILIKE), CNPJ, proposal number/id ou deal_id.
    Se não houver estado ainda, busca a PROPOSTA real no CRM e cria o estado na hora — assim o
    José Luís enxerga toda proposta montada/enviada, não só as que passaram pelo novo envio."""
    a = (alvo or "").strip()
    if not a:
        return None
    # 1) estado já existente
    r = (
        (
            await db.execute(
                text("""
        SELECT n.* FROM crm_negociacao_state n LEFT JOIN proposals p ON p.id=n.proposal_id
        WHERE p.number ILIKE :a OR n.proposal_id::text=:a OR n.deal_id::text=:a
           OR n.cliente_nome ILIKE :like
        ORDER BY n.updated_at DESC LIMIT 1
    """),
                {"a": a, "like": f"%{a}%"},
            )
        )
        .mappings()
        .first()
    )
    if r:
        return dict(r)
    # 2) sem estado: acha a PROPOSTA real (por número, nome do cliente ou CNPJ) e cria o estado
    doc = "".join(c for c in a if c.isdigit())
    p = (
        (
            await db.execute(
                text("""
        SELECT id, number, client_name, client_phone, client_document, opportunity_id, status, created_at
        FROM proposals
        WHERE is_active=true AND (number ILIKE :a OR client_name ILIKE :like
              OR (length(:doc) >= 11 AND regexp_replace(coalesce(client_document,''),'\\D','','g')=:doc))
        ORDER BY created_at DESC LIMIT 1
    """),
                {"a": a, "like": f"%{a}%", "doc": doc},
            )
        )
        .mappings()
        .first()
    )
    if not p:
        return None
    enviada = p["created_at"] if p["status"] in ("sent", "accepted") else None
    return (
        await upsert_negociacao(
            db,
            proposal_id=str(p["id"]),
            deal_id=str(p["opportunity_id"]) if p["opportunity_id"] else None,
            phone_canonical=canonical_br(p["client_phone"]),
            cliente_nome=p["client_name"],
            proposta_enviada_em=enviada,
        )
        or None
    )


async def set_responsavel(db: AsyncSession, alvo: str, responsavel: str) -> dict:
    """'jordan' = dono assume (pausa a cadência). 'jose_luis' = José Luís reassume."""
    neg = await _resolve_negociacao(db, alvo)
    if not neg:
        return {"ok": False, "motivo": "negociação não encontrada", "alvo": alvo}
    await db.execute(
        text("UPDATE crm_negociacao_state SET responsavel=:r, updated_at=now() WHERE id=:id"),
        {"r": responsavel, "id": neg["id"]},
    )
    # pausa/reativa a cadência de WhatsApp do lead, se houver.
    # 'jose_luis' = José Luís acompanha (cadência ativa). 'jordan'/'fechado' = pausa tudo.
    if neg.get("lead_id"):
        ativa = responsavel == "jose_luis"
        await db.execute(
            text("UPDATE crm_sequence_enrollments SET status=:s, updated_at=now() WHERE lead_id=:l AND status=:from"),
            {"s": ("active" if ativa else "paused"), "l": neg["lead_id"], "from": ("paused" if ativa else "active")},
        )
    await db.commit()
    return {"ok": True, "cliente": neg.get("cliente_nome"), "responsavel": responsavel}


# ── Consultas gerenciais (modo gerente do agente) ──────────────────────────────────────────
async def painel_negociacoes(db: AsyncSession, limit: int = 30) -> list[dict]:
    """Painel = TODAS as propostas abertas do CRM (montadas/enviadas) + o estado do acompanhamento."""
    rows = (
        (
            await db.execute(
                text("""
        SELECT p.number AS proposta, p.client_name AS cliente, p.status AS proposta_status,
               p.total AS valor, to_char(p.created_at,'DD/MM') AS criada,
               COALESCE(n.responsavel, 'jose_luis') AS responsavel,
               to_char(n.last_client_reply_at,'DD/MM HH24:MI') AS ultima_resposta, n.ultimo_status,
               (SELECT classificacao FROM crm_followups f WHERE f.proposal_id=p.id
                 AND classificacao IS NOT NULL ORDER BY resposta_em DESC NULLS LAST LIMIT 1) AS classificacao
        FROM proposals p LEFT JOIN crm_negociacao_state n ON n.proposal_id = p.id
        WHERE p.is_active=true AND p.status IN ('draft','sent')
          AND COALESCE(n.responsavel,'jose_luis') <> 'fechado'
        ORDER BY (p.status='sent') DESC, p.created_at DESC LIMIT :l
    """),
                {"l": limit},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


async def status_cliente(db: AsyncSession, alvo: str) -> dict:
    """Status de um cliente: lê a PROPOSTA real (montada/enviada/aceita) + acompanhamento + toques."""
    a = (alvo or "").strip()
    doc = "".join(c for c in a if c.isdigit())
    p = (
        (
            await db.execute(
                text("""
        SELECT id, number, client_name, status, total, to_char(created_at,'DD/MM/YYYY') AS criada,
               opportunity_id
        FROM proposals WHERE is_active=true AND (number ILIKE :a OR client_name ILIKE :like
              OR (length(:doc) >= 11 AND regexp_replace(coalesce(client_document,''),'\\D','','g')=:doc))
        ORDER BY created_at DESC LIMIT 1
    """),
                {"a": a, "like": f"%{a}%", "doc": doc},
            )
        )
        .mappings()
        .first()
    )
    if not p:
        return {
            "encontrado": False,
            "alvo": alvo,
            "dica": "Não achei proposta desse cliente no CRM. Confirme o nome ou o número da proposta.",
        }
    neg = (
        (
            await db.execute(
                text(
                    "SELECT responsavel, to_char(last_client_reply_at,'DD/MM HH24:MI') AS ultima_resposta, ultimo_status "
                    "FROM crm_negociacao_state WHERE proposal_id=:p"
                ),
                {"p": p["id"]},
            )
        )
        .mappings()
        .first()
    )
    h = (
        (
            await db.execute(
                text("""
        SELECT canal, status, classificacao, to_char(enviado_em,'DD/MM HH24:MI') AS enviado,
               left(coalesce(resposta_texto,''),120) AS resposta
        FROM crm_followups WHERE proposal_id=:p ORDER BY created_at DESC LIMIT 6
    """),
                {"p": p["id"]},
            )
        )
        .mappings()
        .all()
    )
    return {
        "encontrado": True,
        "cliente": p["client_name"],
        "proposta": p["number"],
        "proposta_status": p["status"],
        "valor": float(p["total"] or 0),
        "criada": p["criada"],
        "responsavel": (neg["responsavel"] if neg else "jose_luis"),
        "ultima_resposta": (neg["ultima_resposta"] if neg else None),
        "ultimo_status": (neg["ultimo_status"] if neg else None),
        "toques": [dict(x) for x in h],
    }


async def pendentes_sem_resposta(db: AsyncSession, dias: int = REMINDER_AFTER_DAYS) -> list[dict]:
    """Propostas ENVIADAS (status sent) sem resposta do cliente — lê o CRM real."""
    rows = (
        (
            await db.execute(
                text("""
        SELECT p.client_name AS cliente_nome, p.number AS proposta,
               to_char(p.created_at,'DD/MM') AS enviada,
               EXTRACT(DAY FROM now() - COALESCE(n.proposta_enviada_em, p.created_at))::int AS dias
        FROM proposals p LEFT JOIN crm_negociacao_state n ON n.proposal_id=p.id
        WHERE p.is_active=true AND p.status='sent'
          AND COALESCE(n.responsavel,'jose_luis')='jose_luis'
          AND n.last_client_reply_at IS NULL
          AND COALESCE(n.proposta_enviada_em, p.created_at) <= now() - make_interval(days => :d)
        ORDER BY COALESCE(n.proposta_enviada_em, p.created_at) ASC
    """),
                {"d": dias},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


# ── Visão total do funil (modo gerente: pipeline, leads, contratos, retrato executivo) ─────
_STAGE_PROB = {
    "qualification": 0.1,
    "needs_analysis": 0.25,
    "proposal": 0.5,
    "negotiation": 0.75,
    "closed_won": 1.0,
    "closed_lost": 0.0,
}
_STAGE_LABEL = {
    "qualification": "Qualificação",
    "needs_analysis": "Análise",
    "proposal": "Proposta",
    "negotiation": "Negociação",
}


async def resumo_pipeline(db: AsyncSession) -> dict:
    """Funil aberto por estágio + previsão ponderada + ganho no mês + meta do mês."""
    rows = (
        (
            await db.execute(
                text("""
        SELECT stage, count(*) AS deals, COALESCE(SUM(value),0) AS total
        FROM opportunities WHERE is_active=true AND stage NOT IN ('closed_won','closed_lost')
        GROUP BY stage
    """)
            )
        )
        .mappings()
        .all()
    )
    estagios, aberto, ponderado = [], 0.0, 0.0
    for r in rows:
        prob = _STAGE_PROB.get(r["stage"], 0.2)
        w = float(r["total"]) * prob
        aberto += float(r["total"])
        ponderado += w
        estagios.append(
            {
                "estagio": _STAGE_LABEL.get(r["stage"], r["stage"]),
                "deals": r["deals"],
                "valor": round(float(r["total"]), 2),
                "ponderado": round(w, 2),
            }
        )
    won = (
        (
            await db.execute(
                text("""
        SELECT COALESCE(SUM(value),0) v, count(*) c FROM opportunities
        WHERE stage='closed_won' AND EXTRACT(MONTH FROM updated_at)=EXTRACT(MONTH FROM now())
          AND EXTRACT(YEAR FROM updated_at)=EXTRACT(YEAR FROM now())
    """)
            )
        )
        .mappings()
        .first()
    )
    meta = (
        (
            await db.execute(
                text("""
        SELECT COALESCE(SUM(target_value),0) t, COALESCE(MAX(target_count),0) c FROM crm_quotas
        WHERE period_year=EXTRACT(YEAR FROM now()) AND period_month=EXTRACT(MONTH FROM now())
    """)
            )
        )
        .mappings()
        .first()
    )
    meta_val = float(meta["t"]) if meta else 0.0
    ganho = float(won["v"]) if won else 0.0
    # Forecast com WIN-RATE HISTÓRICO: usa a taxa real de ganho; se a amostra de deals fechados
    # for pequena (< 8), mantém a probabilidade fixa por estágio (mais segura) e sinaliza.
    fechados = (
        (
            await db.execute(
                text(
                    "SELECT count(*) FILTER (WHERE stage='closed_won') w, count(*) FILTER (WHERE stage='closed_lost') l "
                    "FROM opportunities WHERE is_active"
                )
            )
        )
        .mappings()
        .first()
    )
    w, lo = (fechados["w"] or 0), (fechados["l"] or 0)
    amostra = w + lo
    win_rate = round(w / amostra, 3) if amostra else None
    if amostra >= 8 and win_rate is not None:
        prev_winrate = round(aberto * win_rate, 2)
        base = "win-rate histórico"
    else:
        prev_winrate = round(ponderado, 2)
        base = "probabilidade por estágio (amostra de fechados insuficiente p/ win-rate)"
    return {
        "estagios": estagios,
        "total_aberto": round(aberto, 2),
        "previsao_ponderada": round(ponderado, 2),
        "win_rate_historico_pct": round(win_rate * 100, 1) if win_rate is not None else None,
        "amostra_fechados": amostra,
        "previsao_winrate": prev_winrate,
        "previsao_base": base,
        "ganho_mes": round(ganho, 2),
        "contratos_ganhos_mes": (won["c"] if won else 0),
        "meta_mes": round(meta_val, 2),
        "atingimento_pct": round(ganho / meta_val * 100, 1) if meta_val else None,
        "meta_contratos": (int(meta["c"]) if meta else 0),
    }


# ── Funil UNIFICADO (primeiro contato → fechamento), calculado dos dados existentes ──────
_FUNIL_ORDEM = ["novo", "qualificando", "visita", "proposta", "negociacao", "ganho", "perdido"]
_FUNIL_LABEL = {
    "novo": "Novo contato",
    "qualificando": "Qualificando",
    "visita": "Visita agendada",
    "proposta": "Proposta enviada",
    "negociacao": "Negociação",
    "ganho": "Ganho",
    "perdido": "Perdido",
}
_FUNIL_ATIVOS = ("novo", "qualificando", "visita", "proposta", "negociacao")
_OPP_STAGE_FUNIL = {
    "qualification": "qualificando",
    "needs_analysis": "qualificando",
    "proposal": "proposta",
    "negotiation": "negociacao",
    "closed_won": "ganho",
    "closed_lost": "perdido",
}


async def funil_comercial(db: AsyncSession) -> dict:
    """Funil UNIFICADO do primeiro contato ao fechamento (leads de conversa + deals), calculado
    dos dados que já existem — SEM migration, SEM coluna nova (zero drift). Mostra quantos e
    quanto em cada etapa, o GARGALO e QUEM está parado (acionável: nome, telefone, dias)."""
    itens: list[dict] = []  # {nome, telefone, estagio, valor, dias}

    # 1) Oportunidades (deals): estágio direto do funil de vendas
    # tel: o deal raramente tem contact_phone -> cai pro telefone do lead vinculado, e desse
    # pro telefone do follow-up da proposta (pra o "cutucar" ter sempre um número quando existir).
    opps = (
        (
            await db.execute(
                text(
                    "SELECT o.stage, COALESCE(o.value,0) AS valor, "
                    "COALESCE(NULLIF(o.company_name,''), NULLIF(o.contact_name,''), 'Sem nome') AS nome, "
                    "COALESCE(NULLIF(o.contact_phone,''), NULLIF(l.phone,''), f.phone_canonical) AS tel, "
                    "EXTRACT(EPOCH FROM (now() - o.updated_at))/86400 AS dias "
                    "FROM opportunities o "
                    "LEFT JOIN leads l ON l.id = o.lead_id "
                    "LEFT JOIN LATERAL (SELECT phone_canonical FROM crm_followups "
                    "  WHERE deal_id = o.id AND phone_canonical IS NOT NULL "
                    "  ORDER BY created_at DESC LIMIT 1) f ON true "
                    "WHERE o.is_active"
                )
            )
        )
        .mappings()
        .all()
    )
    for o in opps:
        itens.append(
            {
                "nome": o["nome"],
                "telefone": o["tel"],
                "estagio": _OPP_STAGE_FUNIL.get(o["stage"], "qualificando"),
                "valor": float(o["valor"]),
                "dias": int(o["dias"] or 0),
            }
        )

    # 2) Leads SEM oportunidade: estágio pela conversa (visita > qualificando > novo)
    com_visita = set(
        (
            await db.execute(
                text(
                    "SELECT DISTINCT lead_id FROM visitas WHERE lead_id IS NOT NULL AND COALESCE(ativo,true)=true "
                    "AND upper(coalesce(status,'')) NOT IN ('CANCELADA','CANCELADO')"
                )
            )
        )
        .scalars()
        .all()
    )
    leads = (
        (
            await db.execute(
                text(
                    "SELECT l.id, COALESCE(NULLIF(l.name,''), NULLIF(l.company,''), l.phone, 'Lead') AS nome, "
                    "l.phone AS tel, l.status, l.qualificacao, COALESCE(l.expected_value,0) AS valor, "
                    "EXTRACT(EPOCH FROM (now() - COALESCE(l.last_contact_at, l.updated_at, l.created_at)))/86400 AS dias "
                    "FROM leads l WHERE l.is_active "
                    "AND NOT EXISTS (SELECT 1 FROM opportunities o WHERE o.lead_id=l.id)"
                )
            )
        )
        .mappings()
        .all()
    )
    for l in leads:
        if l["id"] in com_visita:
            est = "visita"
        elif l["status"] == "qualified" or l["qualificacao"]:
            est = "qualificando"
        else:
            est = "novo"
        itens.append(
            {
                "nome": l["nome"],
                "telefone": l["tel"],
                "estagio": est,
                "valor": float(l["valor"]),
                "dias": int(l["dias"] or 0),
            }
        )

    etapas = []
    for est in _FUNIL_ORDEM:
        grupo = [i for i in itens if i["estagio"] == est]
        parados = sorted([i for i in grupo if est in _FUNIL_ATIVOS], key=lambda x: -x["dias"])
        etapas.append(
            {
                "estagio": est,
                "label": _FUNIL_LABEL[est],
                "qtd": len(grupo),
                "valor": round(sum(i["valor"] for i in grupo), 2),
                "parados_7d": sum(1 for i in parados if i["dias"] >= 7),
                "top_parados": [{"nome": i["nome"], "telefone": i["telefone"], "dias": i["dias"]} for i in parados[:3]],
            }
        )

    ativos = [i for i in itens if i["estagio"] in _FUNIL_ATIVOS]
    ativas_qtd = [
        (e["estagio"], e["label"], e["qtd"]) for e in etapas if e["estagio"] in _FUNIL_ATIVOS and e["qtd"] > 0
    ]
    gargalo = max(ativas_qtd, key=lambda x: x[2]) if ativas_qtd else None
    mais_parados = sorted(ativos, key=lambda x: -x["dias"])[:5]
    return {
        "etapas": etapas,
        "ativos_total": len(ativos),
        "valor_ativo": round(sum(i["valor"] for i in ativos), 2),
        "gargalo": ({"estagio": gargalo[0], "label": gargalo[1], "qtd": gargalo[2]} if gargalo else None),
        "mais_parados": [
            {"nome": i["nome"], "telefone": i["telefone"], "estagio": _FUNIL_LABEL[i["estagio"]], "dias": i["dias"]}
            for i in mais_parados
        ],
        "ganhos": sum(1 for i in itens if i["estagio"] == "ganho"),
        "perdidos": sum(1 for i in itens if i["estagio"] == "perdido"),
    }


async def resumo_leads(db: AsyncSession, dias: int = 7) -> dict:
    """Leads: novos no período, por status, e os mais recentes sem virar proposta."""
    tot = (
        (
            await db.execute(
                text("""
        SELECT count(*) FILTER (WHERE created_at >= now() - make_interval(days => :d)) AS novos,
               count(*) FILTER (WHERE status='new') AS abertos,
               count(*) FILTER (WHERE status='qualified') AS qualificados,
               count(*) AS total
        FROM leads WHERE is_active=true
    """),
                {"d": dias},
            )
        )
        .mappings()
        .first()
    )
    recentes = (
        (
            await db.execute(
                text("""
        SELECT name, COALESCE(source,'—') AS origem, status,
               to_char(created_at,'DD/MM') AS criado
        FROM leads WHERE is_active=true ORDER BY created_at DESC LIMIT 8
    """)
            )
        )
        .mappings()
        .all()
    )
    return {
        "novos_periodo": tot["novos"],
        "dias": dias,
        "abertos": tot["abertos"],
        "qualificados": tot["qualificados"],
        "total": tot["total"],
        "recentes": [dict(r) for r in recentes],
    }


async def resumo_contratos(db: AsyncSession) -> dict:
    """Contratos ativos, MRR total e os que vencem nos próximos 60 dias."""
    d = (
        (
            await db.execute(
                text("""
        SELECT count(*) FILTER (WHERE status='active') AS ativos,
               COALESCE(SUM(monthly_value) FILTER (WHERE status='active'),0) AS mrr
        FROM contracts WHERE is_active=true
    """)
            )
        )
        .mappings()
        .first()
    )
    vencendo = (
        (
            await db.execute(
                text("""
        SELECT contract_number, name, to_char(end_date,'DD/MM/YYYY') AS vence,
               COALESCE(monthly_value,0) AS mensal
        FROM contracts WHERE is_active=true AND status='active' AND end_date IS NOT NULL
          AND end_date <= now() + interval '60 days'
        ORDER BY end_date ASC LIMIT 10
    """)
            )
        )
        .mappings()
        .all()
    )
    return {"ativos": d["ativos"], "mrr": round(float(d["mrr"]), 2), "vencendo_60d": [dict(r) for r in vencendo]}


async def resumo_executivo(db: AsyncSession) -> dict:
    """Retrato da casa: pipeline + propostas + leads + contratos + pendências, num lugar só."""
    pipe = await resumo_pipeline(db)
    leads = await resumo_leads(db)
    contr = await resumo_contratos(db)
    pend = await pendentes_sem_resposta(db)
    props = (
        (
            await db.execute(
                text("""
        SELECT count(*) FILTER (WHERE status='draft') AS montadas,
               count(*) FILTER (WHERE status='sent') AS enviadas
        FROM proposals WHERE is_active=true
    """)
            )
        )
        .mappings()
        .first()
    )
    return {
        "pipeline": {
            "total_aberto": pipe["total_aberto"],
            "previsao_ponderada": pipe["previsao_ponderada"],
            "ganho_mes": pipe["ganho_mes"],
            "meta_mes": pipe["meta_mes"],
            "atingimento_pct": pipe["atingimento_pct"],
        },
        "propostas": {"montadas": props["montadas"], "enviadas": props["enviadas"], "sem_resposta": len(pend)},
        "leads": {"novos_semana": leads["novos_periodo"], "abertos": leads["abertos"]},
        "contratos": {"ativos": contr["ativos"], "mrr": contr["mrr"], "vencendo_60d": len(contr["vencendo_60d"])},
    }


# ── FASE 1: Analytics comercial / Financeiro / What-if ─────────────────────────────────────
async def relatorio_comercial(db: AsyncSession) -> dict:
    """Raio-x de vendas: win/loss, conversão do funil, motivos de perda, ROI por canal, ranking MRR."""
    wl = (
        (
            await db.execute(
                text("""
        SELECT count(*) FILTER (WHERE stage='closed_won') AS ganhos,
               COALESCE(SUM(value) FILTER (WHERE stage='closed_won'),0) AS valor_ganho,
               count(*) FILTER (WHERE stage='closed_lost') AS perdidos,
               COALESCE(SUM(value) FILTER (WHERE stage='closed_lost'),0) AS valor_perdido
        FROM opportunities WHERE is_active=true
    """)
            )
        )
        .mappings()
        .first()
    )
    ganhos, perdidos = (wl["ganhos"] or 0), (wl["perdidos"] or 0)
    win_rate = round(ganhos / (ganhos + perdidos) * 100, 1) if (ganhos + perdidos) else None
    motivos = [
        dict(r)
        for r in (
            await db.execute(
                text("""
        SELECT COALESCE(NULLIF(trim(loss_reason),''),'(não informado)') AS motivo, count(*) AS qtd
        FROM opportunities WHERE is_active=true AND stage='closed_lost'
        GROUP BY 1 ORDER BY 2 DESC LIMIT 8
    """)
            )
        )
        .mappings()
        .all()
    ]
    funil = (
        (
            await db.execute(
                text("""
        SELECT (SELECT count(*) FROM leads WHERE is_active) AS leads,
               (SELECT count(*) FROM leads WHERE is_active AND status='qualified') AS qualificados,
               (SELECT count(*) FROM opportunities WHERE is_active) AS oportunidades,
               (SELECT count(*) FROM opportunities WHERE is_active AND stage='closed_won') AS ganhos
    """)
            )
        )
        .mappings()
        .first()
    )
    conv_lead_opp = round((funil["oportunidades"] or 0) / funil["leads"] * 100, 1) if funil["leads"] else None
    conv_opp_won = round((funil["ganhos"] or 0) / funil["oportunidades"] * 100, 1) if funil["oportunidades"] else None
    roi_canal = [
        dict(r)
        for r in (
            await db.execute(
                text("""
        SELECT COALESCE(NULLIF(l.source,''),'(direto)') AS canal, count(DISTINCT l.id) AS leads,
               count(DISTINCT o.id) FILTER (WHERE o.stage='closed_won') AS ganhos,
               COALESCE(SUM(o.value) FILTER (WHERE o.stage='closed_won'),0) AS valor_ganho
        FROM leads l LEFT JOIN opportunities o ON o.lead_id=l.id AND o.is_active
        WHERE l.is_active GROUP BY 1 ORDER BY leads DESC LIMIT 8
    """)
            )
        )
        .mappings()
        .all()
    ]
    ranking = [
        dict(r)
        for r in (
            await db.execute(
                text("""
        SELECT cl.name AS cliente, COALESCE(SUM(c.monthly_value),0) AS mrr
        FROM contracts c JOIN clients cl ON cl.id=c.client_id
        WHERE c.is_active AND c.status='active' GROUP BY cl.name ORDER BY mrr DESC LIMIT 5
    """)
            )
        )
        .mappings()
        .all()
    ]
    ciclo = (
        await db.execute(
            text("""
        SELECT ROUND(AVG(EXTRACT(EPOCH FROM (updated_at - created_at))/86400)::numeric,1) AS dias
        FROM opportunities WHERE is_active AND stage='closed_won'
    """)
        )
    ).scalar()
    return {
        "win_loss": {
            "ganhos": ganhos,
            "valor_ganho": round(float(wl["valor_ganho"]), 2),
            "perdidos": perdidos,
            "valor_perdido": round(float(wl["valor_perdido"]), 2),
            "win_rate_pct": win_rate,
        },
        "motivos_perda": motivos,
        "funil": {
            "leads": funil["leads"],
            "qualificados": funil["qualificados"],
            "oportunidades": funil["oportunidades"],
            "ganhos": funil["ganhos"],
            "conversao_lead_oportunidade_pct": conv_lead_opp,
            "conversao_oportunidade_ganho_pct": conv_opp_won,
        },
        "roi_por_canal": roi_canal,
        "ranking_clientes_mrr": [{"cliente": r["cliente"], "mrr": round(float(r["mrr"]), 2)} for r in ranking],
        "ciclo_medio_dias": float(ciclo) if ciclo is not None else None,
    }


async def resumo_financeiro(db: AsyncSession) -> dict:
    """Retrato financeiro real: MRR, recebíveis, inadimplência, caixa do mês, faturamento NFS-e."""
    mrr = (
        await db.execute(
            text("SELECT COALESCE(SUM(monthly_value),0) FROM contracts WHERE is_active AND status='active'")
        )
    ).scalar()
    receb = (
        (
            await db.execute(
                text("""
        SELECT COALESCE(SUM(expected_amount),0) AS previsto,
               COALESCE(SUM(expected_amount) FILTER (WHERE due_date < now()::date),0) AS vencido,
               count(*) FILTER (WHERE due_date < now()::date) AS qtd_vencidos
        FROM cashflow_entries WHERE ativo AND entry_type='entrada' AND status='previsto'
    """)
            )
        )
        .mappings()
        .first()
    )
    mes = (
        (
            await db.execute(
                text("""
        SELECT COALESCE(SUM(realized_amount) FILTER (WHERE entry_type='entrada'),0) AS entradas,
               COALESCE(SUM(realized_amount) FILTER (WHERE entry_type='saida'),0) AS saidas
        FROM cashflow_entries WHERE ativo AND status='realizado'
          AND realized_date >= date_trunc('month', now())
    """)
            )
        )
        .mappings()
        .first()
    )
    nfse = (
        (
            await db.execute(
                # [Veracidade] Fonte autoritativa = nfse_emitidas_nacional (77 notas
                # jan-jun / R$1.428.413,04 = razão 3.1.1.01). `nfses` so tinha jan-fev
                # (27 notas / R$542k) -> total do dashboard CRM subvalorizado.
                text("""
        SELECT count(*) AS qtd, COALESCE(SUM(valor_servicos),0) AS total,
               COALESCE(SUM(valor_servicos) FILTER (WHERE data_emissao >= date_trunc('month', now())),0) AS mes
        FROM nfse_emitidas_nacional
    """)
            )
        )
        .mappings()
        .first()
    )
    mrr_v = float(mrr or 0)
    ent, sai = float(mes["entradas"] or 0), float(mes["saidas"] or 0)
    return {
        "mrr": round(mrr_v, 2),
        "mrr_anualizado": round(mrr_v * 12, 2),
        "recebiveis_previstos": round(float(receb["previsto"]), 2),
        "inadimplencia": round(float(receb["vencido"]), 2),
        "titulos_vencidos": receb["qtd_vencidos"],
        "caixa_mes": {"entradas": round(ent, 2), "saidas": round(sai, 2), "saldo": round(ent - sai, 2)},
        "faturamento_nfse": {
            "total": round(float(nfse["total"]), 2),
            "mes": round(float(nfse["mes"]), 2),
            "qtd": nfse["qtd"],
        },
    }


async def simular_fechamento(
    db: AsyncSession, deals: list[str] | None = None, estagio: str | None = "negotiation"
) -> dict:
    """What-if: se fechar estes deals (ou todos de um estágio), como fica ganho/meta/MRR potencial."""
    if deals:
        rows = (
            (
                await db.execute(
                    text(
                        "SELECT id, COALESCE(title, company_name) AS nome, value FROM opportunities "
                        "WHERE is_active AND id::text = ANY(:ids)"
                    ),
                    {"ids": deals},
                )
            )
            .mappings()
            .all()
        )
    else:
        rows = (
            (
                await db.execute(
                    text(
                        "SELECT id, COALESCE(title, company_name) AS nome, value FROM opportunities "
                        "WHERE is_active AND stage=:s"
                    ),
                    {"s": estagio},
                )
            )
            .mappings()
            .all()
        )
    soma = sum(float(r["value"] or 0) for r in rows)
    pipe = await resumo_pipeline(db)
    ganho_atual = pipe["ganho_mes"]
    meta = pipe["meta_mes"]
    return {
        "deals_considerados": [{"nome": r["nome"], "valor": round(float(r["value"] or 0), 2)} for r in rows],
        "valor_total_a_fechar": round(soma, 2),
        "ganho_mes_atual": ganho_atual,
        "ganho_mes_projetado": round(ganho_atual + soma, 2),
        "meta_mes": meta,
        "atingimento_atual_pct": round(ganho_atual / meta * 100, 1) if meta else None,
        "atingimento_projetado_pct": round((ganho_atual + soma) / meta * 100, 1) if meta else None,
    }


# ── FASE 3: Cross-sell data-driven / Radar de frios / Reativação ───────────────────────────
# Categorias inferidas do NOME do contrato (dados reais), e o complemento natural de cada uma.
_CAT_KEYWORDS = {
    "portaria_presencial": ["portaria", "agente", "agp"],
    "portaria_remota": ["remota", "monitoramento", "remoto"],
    "cftv": ["cftv", "câmera", "camera", "seg. eletr", "segurança eletr", "seguranca eletr"],
    "controle_acesso": ["controle de acesso", "facial", "acesso", "tag", "rfid"],
    "limpeza": ["limpeza", "serv. gerais", "serviços gerais", "servicos gerais", "asg"],
    "manutencao": ["manutenção", "manutencao", "preventiva"],
    "piscina": ["piscina"],
    "jardinagem": ["jardin"],
    "alarme": ["alarme"],
}
_CROSS_SELL = [
    (
        "portaria_presencial",
        "portaria_remota",
        "tem portaria presencial — vale apresentar a portaria remota híbrida (economia de até ~35% mantendo a segurança)",
    ),
    (
        "portaria_presencial",
        "cftv",
        "tem portaria mas não consta CFTV — câmeras inteligentes reforçam a segurança e a rastreabilidade",
    ),
    (
        "cftv",
        "controle_acesso",
        "tem CFTV mas não controle de acesso — facial/TAG fecha o ciclo (quem entrou e com qual autorização)",
    ),
    (
        "portaria_remota",
        "controle_acesso",
        "tem portaria remota — controle de acesso facial potencializa a operação remota",
    ),
    ("limpeza", "piscina", "tem limpeza/serviços gerais — pode incluir tratamento de piscina"),
    ("limpeza", "jardinagem", "tem serviços gerais — jardinagem é um complemento natural"),
    (
        "cftv",
        "manutencao",
        "tem CFTV — contrato de manutenção preventiva evita falhas e prolonga a vida dos equipamentos",
    ),
]


def _categorias_de(nomes: list[str]) -> set[str]:
    txt = " ".join(nomes).lower()
    return {cat for cat, kws in _CAT_KEYWORDS.items() if any(k in txt for k in kws)}


async def sugerir_cross_sell(db: AsyncSession, cnpj_ou_id: str) -> dict:
    """A partir dos contratos REAIS do cliente, sugere o serviço complementar que falta."""
    a = (cnpj_ou_id or "").strip()
    doc = "".join(c for c in a if c.isdigit())
    cli = (
        (
            await db.execute(
                text("""
        SELECT id, name FROM clients WHERE id::text=:a
           OR regexp_replace(coalesce(document_number,''),'\\D','','g')=:doc OR name ILIKE :like
        LIMIT 1"""),
                {"a": a, "doc": doc, "like": f"%{a}%"},
            )
        )
        .mappings()
        .first()
    )
    if not cli:
        return {"encontrado": False, "busca": cnpj_ou_id}
    nomes = [
        r[0]
        for r in (
            await db.execute(
                text("SELECT name FROM contracts WHERE client_id=:c AND is_active AND status='active'"),
                {"c": cli["id"]},
            )
        ).all()
    ]
    tem = _categorias_de(nomes)
    sugestoes = [{"servico": dst, "pitch": pitch} for src, dst, pitch in _CROSS_SELL if src in tem and dst not in tem]
    return {
        "encontrado": True,
        "cliente": cli["name"],
        "contratos": nomes,
        "ja_tem": sorted(tem),
        "sugestoes": sugestoes[:4],
    }


async def leads_frios(db: AsyncSession, dias: int = 14, limit: int = 30) -> list[dict]:
    """Leads que esfriaram: sem interação há >= N dias, ainda abertos, com telefone, não convertidos."""
    rows = (
        (
            await db.execute(
                text("""
        SELECT l.id, l.name, COALESCE(NULLIF(l.source,''),'(direto)') AS origem, l.score,
               to_char(COALESCE(l.last_contact_at, l.updated_at, l.created_at),'DD/MM') AS ultimo,
               EXTRACT(DAY FROM now() - COALESCE(l.last_contact_at, l.updated_at, l.created_at))::int AS dias_parado
        FROM leads l
        WHERE l.is_active AND l.status IN ('new','qualified')
          AND COALESCE(l.last_contact_at, l.updated_at, l.created_at) <= now() - make_interval(days => :d)
          AND COALESCE(NULLIF(regexp_replace(coalesce(l.phone,''),'\\D','','g'),''), NULL) IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM opportunities o WHERE o.lead_id=l.id AND o.stage='closed_won')
        ORDER BY dias_parado DESC LIMIT :l
    """),
                {"d": dias, "l": limit},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


async def reativar_lead(db: AsyncSession, ref: str, mensagem: str | None = None, confirmar: bool = True) -> dict:
    """Reengaja um lead frio por WhatsApp (comando do Jordan autoriza). Respeita opt-out/horário."""
    a = (ref or "").strip()
    lead = (
        (
            await db.execute(
                text(
                    "SELECT id, name, phone FROM leads WHERE id::text=:a OR name ILIKE :like "
                    "ORDER BY updated_at DESC LIMIT 1"
                ),
                {"a": a, "like": f"%{a}%"},
            )
        )
        .mappings()
        .first()
    )
    if not lead:
        return {"ok": False, "motivo": "lead não encontrado"}
    e164 = to_e164_br(lead["phone"])
    if not e164:
        return {"ok": False, "motivo": "lead sem WhatsApp válido"}
    nome = (lead["name"] or "").split()[0] if lead["name"] else "tudo bem"
    msg = mensagem or (
        f"Olá, {nome}! 😊 Aqui é o José Luís, da Conecta Mais. Passando pra saber se "
        f"você ainda tem interesse em conversar sobre segurança/portaria pro seu condomínio. "
        f"Posso ajudar em algo? — José Luís · Conecta Mais"
    )
    target = {
        "phone_e164": e164,
        "phone_canonical": canonical_br(e164),
        "nome": lead["name"],
        "lead_id": str(lead["id"]),
        "cliente_id": None,
        "deal_id": None,
    }
    if not confirmar:
        return {"preview": True, "lead": lead["name"], "telefone": e164, "mensagem": msg}
    res = await F.send_followup(
        db,
        target=target,
        mensagem=msg,
        canal="whatsapp",
        template="reativacao",
        criado_por="reativacao",
        ignore_antispam=True,
    )
    if res.get("enviado"):
        await db.execute(
            text("UPDATE leads SET last_contact_at=now(), updated_at=now() WHERE id=:id"), {"id": lead["id"]}
        )
        await db.commit()
    return {"ok": res.get("enviado"), "lead": lead["name"], "para": e164, "detalhe": res.get("detalhe")}


# ── FASE 4: NPS pós-venda ──────────────────────────────────────────────────────────────────
async def marcar_enviada(db: AsyncSession, ref: str) -> dict:
    """Marca uma proposta como ENVIADA (sem reenviar) — quando o envio foi por fora do ciclo.
    Entra no painel/acompanhamento. ref = número da proposta, nome do cliente ou CNPJ."""
    a = (ref or "").strip()
    doc = "".join(c for c in a if c.isdigit())
    p = (
        (
            await db.execute(
                text("""
        SELECT id, number, client_name, client_phone, opportunity_id, status, created_at
        FROM proposals WHERE is_active AND (number ILIKE :a OR id::text=:a OR client_name ILIKE :like
              OR (length(:doc) >= 11 AND regexp_replace(coalesce(client_document,''),'\\D','','g')=:doc))
        ORDER BY created_at DESC LIMIT 1"""),
                {"a": a, "like": f"%{a}%", "doc": doc},
            )
        )
        .mappings()
        .first()
    )
    if not p:
        return {"ok": False, "motivo": "proposta não encontrada", "ref": ref}
    if p["status"] in ("accepted",):
        return {"ok": False, "motivo": f"proposta já está '{p['status']}'", "proposta": p["number"]}
    await db.execute(
        text(
            "UPDATE proposals SET status='sent', sent_at=COALESCE(sent_at, created_at), updated_at=now() WHERE id=:id"
        ),
        {"id": p["id"]},
    )
    if p["opportunity_id"]:
        await db.execute(
            text(
                "UPDATE opportunities SET stage='negotiation', updated_at=now() "
                "WHERE id=:d AND stage NOT IN ('closed_won','closed_lost','negotiation')"
            ),
            {"d": p["opportunity_id"]},
        )
    await db.commit()
    await upsert_negociacao(
        db,
        proposal_id=str(p["id"]),
        deal_id=str(p["opportunity_id"]) if p["opportunity_id"] else None,
        phone_canonical=canonical_br(p["client_phone"]),
        cliente_nome=p["client_name"],
        proposta_enviada_em=p["created_at"],
        responsavel="jose_luis",
    )
    return {
        "ok": True,
        "proposta": p["number"],
        "cliente": p["client_name"],
        "obs": "marcada como enviada (sem reenvio ao cliente) e entrou no acompanhamento",
    }


async def enviar_nps(db: AsyncSession, ref: str, confirmar: bool = False) -> dict:
    """Envia uma pesquisa NPS (0–10) por WhatsApp a um cliente. A resposta é capturada no inbound."""
    target = await F.resolve_target(db, cliente=ref)
    if not target.get("phone_e164"):
        return {"ok": False, "motivo": "cliente sem WhatsApp válido. Use cadastrar_whatsapp_cliente."}
    nome = (target.get("nome") or "").split()[0] if target.get("nome") else "tudo bem"
    msg = (
        f"Olá, {nome}! 😊 Aqui é o José Luís, da Conecta Mais. Numa escala de *0 a 10*, "
        f"o quanto você recomendaria a Conecta Mais a um amigo ou outro condomínio? "
        f"Sua resposta nos ajuda muito a melhorar! 🙏"
    )
    if not confirmar:
        return {
            "preview": True,
            "cliente": target.get("nome"),
            "telefone": target.get("phone_e164"),
            "mensagem": msg,
            "aviso": "Reenvie com confirmar=true para enviar a pesquisa NPS.",
        }
    # cliente_id é lido de target dentro do send_followup (não é kwarg dele).
    res = await F.send_followup(
        db, target=target, mensagem=msg, canal="whatsapp", template="nps", criado_por="nps", ignore_antispam=True
    )
    return {"ok": res.get("enviado"), "cliente": target.get("nome"), "para": target.get("phone_e164")}


async def resumo_nps(db: AsyncSession) -> dict:
    """Resumo NPS: notas recebidas, % promotores/neutros/detratores e o NPS (-100 a +100)."""
    rows = (
        await db.execute(
            text("""
        SELECT classificacao FROM crm_followups
        WHERE template='nps' AND classificacao LIKE 'nps:%' AND classificacao <> 'nps:?'
    """)
        )
    ).all()
    notas = []
    for r in rows:
        try:
            notas.append(int(str(r[0]).split(":")[1]))
        except (ValueError, IndexError):
            continue
    if not notas:
        return {
            "respostas": 0,
            "nps": None,
            "info": "Nenhuma resposta de NPS ainda. Use enviar_nps para pesquisar clientes.",
        }
    prom = sum(1 for n in notas if n >= 9)
    det = sum(1 for n in notas if n <= 6)
    neu = len(notas) - prom - det
    nps = round((prom - det) / len(notas) * 100)
    return {
        "respostas": len(notas),
        "media": round(sum(notas) / len(notas), 1),
        "promotores": prom,
        "neutros": neu,
        "detratores": det,
        "nps": nps,
    }


# ── FECHAMENTO DO CICLO: heartbeat, métricas, ficha viva, estado ───────────────────────────
async def get_state(db: AsyncSession, chave: str) -> str | None:
    r = (await db.execute(text("SELECT valor FROM crm_system_state WHERE chave=:k"), {"k": chave})).first()
    return r[0] if r else None


async def set_state(db: AsyncSession, chave: str, valor: str) -> None:
    await db.execute(
        text(
            "INSERT INTO crm_system_state (chave, valor, updated_at) VALUES (:k, :v, now()) "
            "ON CONFLICT (chave) DO UPDATE SET valor=:v, updated_at=now()"
        ),
        {"k": chave, "v": valor},
    )
    await db.commit()


async def diagnostico_ciclo(db: AsyncSession) -> dict:
    """Heartbeat do ciclo Cowork↔Conecta PRO↔WhatsApp: cada elo está de pé?"""
    itens = {}
    # WhatsApp/Chatwoot online
    try:
        from modules.integrations.connectors.whatsapp.service import whatsapp_service

        st = await whatsapp_service.check_status()
        itens["whatsapp"] = {"ok": bool(st.get("online")), "detalhe": st.get("reason") or st.get("provider")}
    except Exception as e:  # noqa: BLE001
        itens["whatsapp"] = {"ok": False, "detalhe": str(e)[:80]}
    # Agente José Luís ligado
    ag_on = os.getenv("AGENT_ENABLED", "false").lower() == "true"
    itens["agente"] = {"ok": ag_on, "detalhe": f"modo={os.getenv('AGENT_MODE', 'copilot')}"}
    # Webhook recebendo (última mensagem de entrada)
    r = (
        await db.execute(
            text("SELECT EXTRACT(EPOCH FROM now() - max(created_at))/3600 FROM cwi_message_log WHERE direction='in'")
        )
    ).scalar()
    horas = float(r) if r is not None else None
    itens["webhook_inbound"] = {
        "ok": (horas is not None),
        "ultima_entrada_horas": round(horas, 1) if horas is not None else None,
    }
    # Banco/cadência (estamos consultando -> DB ok; cadência: enrollments ativos)
    enr = (await db.execute(text("SELECT count(*) FROM crm_sequence_enrollments WHERE status='active'"))).scalar()
    itens["cadencia"] = {"ok": True, "enrollments_ativos": int(enr or 0)}
    criticos_ok = itens["whatsapp"]["ok"] and itens["agente"]["ok"]
    return {"saudavel": criticos_ok, "itens": itens}


async def metricas_jose_luis(db: AsyncSession) -> dict:
    """Funil/desempenho do José Luís no ciclo (dados reais)."""
    leads = (
        (
            await db.execute(
                text("""
        SELECT count(*) total, count(*) FILTER (WHERE source='whatsapp') AS por_whatsapp,
               count(*) FILTER (WHERE created_at >= now() - interval '30 days') AS ult_30d
        FROM leads WHERE is_active""")
            )
        )
        .mappings()
        .first()
    )
    fu = (
        (
            await db.execute(
                text("""
        SELECT count(*) FILTER (WHERE status='enviado') AS enviados,
               count(*) FILTER (WHERE status='respondido') AS respondidos,
               count(*) FILTER (WHERE classificacao='interessado') AS interessados
        FROM crm_followups""")
            )
        )
        .mappings()
        .first()
    )
    visitas = (await db.execute(text("SELECT count(*) FROM crm_visit_reports"))).scalar()
    negs = (
        (
            await db.execute(
                text("""
        SELECT count(*) FILTER (WHERE responsavel='jose_luis') AS jose,
               count(*) FILTER (WHERE responsavel='jordan') AS jordan,
               count(*) FILTER (WHERE responsavel='fechado') AS fechadas
        FROM crm_negociacao_state""")
            )
        )
        .mappings()
        .first()
    )
    enviados = fu["enviados"] or 0
    taxa = round((fu["respondidos"] or 0) / enviados * 100, 1) if enviados else None
    nps = await resumo_nps(db)
    return {
        "leads": {"total": leads["total"], "captados_whatsapp": leads["por_whatsapp"], "novos_30d": leads["ult_30d"]},
        "follow_ups": {
            "enviados": enviados,
            "respondidos": fu["respondidos"] or 0,
            "interessados": fu["interessados"] or 0,
            "taxa_resposta_pct": taxa,
        },
        "visitas_registradas": int(visitas or 0),
        "negociacoes": {
            "acompanhando": negs["jose"] or 0,
            "com_jordan": negs["jordan"] or 0,
            "encerradas": negs["fechadas"] or 0,
        },
        "nps": nps.get("nps"),
    }


# ── Ficha viva do cliente (anotações compartilhadas Cowork ↔ José Luís) ─────────────────────
async def _resolve_cliente_ref(db: AsyncSession, ref: str) -> dict:
    """Acha um cliente por id/CNPJ/nome e devolve {cliente_id, cliente_nome, phone_canonical}."""
    a = (ref or "").strip()
    doc = "".join(c for c in a if c.isdigit())
    r = (
        (
            await db.execute(
                text("""
        SELECT id, name, COALESCE(whatsapp, mobile, phone) AS fone FROM clients
        WHERE id::text=:a OR regexp_replace(coalesce(document_number,''),'\\D','','g')=:doc
              OR name ILIKE :like
        ORDER BY (name ILIKE :like) DESC LIMIT 1"""),
                {"a": a, "doc": doc, "like": f"%{a}%"},
            )
        )
        .mappings()
        .first()
    )
    if r:
        return {"cliente_id": str(r["id"]), "cliente_nome": r["name"], "phone_canonical": canonical_br(r["fone"])}
    return {"cliente_id": None, "cliente_nome": ref, "phone_canonical": None}


async def anotar_cliente(db: AsyncSession, ref: str, nota: str, autor: str | None = None) -> dict:
    info = await _resolve_cliente_ref(db, ref)
    row = (
        (
            await db.execute(
                text("""
        INSERT INTO crm_client_notes (id, cliente_id, cliente_ref, cliente_nome, phone_canonical, nota, autor, created_at)
        VALUES (gen_random_uuid(), :cid, :ref, :nome, :ph, :nota, :autor, now())
        RETURNING id"""),
                {
                    "cid": info["cliente_id"],
                    "ref": ref,
                    "nome": info["cliente_nome"],
                    "ph": info["phone_canonical"],
                    "nota": nota[:4000],
                    "autor": autor,
                },
            )
        )
        .mappings()
        .first()
    )
    await db.commit()
    return {"ok": True, "id": str(row["id"]), "cliente": info["cliente_nome"]}


async def ficha_cliente(db: AsyncSession, ref: str) -> dict:
    """Ficha viva: dados + anotações + último status de negociação/atendimento do cliente."""
    info = await _resolve_cliente_ref(db, ref)
    notas = [
        dict(r)
        for r in (
            await db.execute(
                text("""
        SELECT to_char(created_at,'DD/MM/YYYY HH24:MI') AS quando, COALESCE(autor,'—') AS autor,
               nota FROM crm_client_notes
        WHERE (cliente_id = :cid AND :cid IS NOT NULL) OR cliente_ref ILIKE :like OR cliente_nome ILIKE :like
        ORDER BY created_at DESC LIMIT 20"""),
                {"cid": info["cliente_id"], "like": f"%{ref}%"},
            )
        )
        .mappings()
        .all()
    ]
    neg = (
        (
            await db.execute(
                text("""
        SELECT cliente_nome, responsavel, ultimo_status FROM crm_negociacao_state
        WHERE cliente_id=:cid OR cliente_nome ILIKE :like ORDER BY updated_at DESC LIMIT 1"""),
                {"cid": info["cliente_id"], "like": f"%{ref}%"},
            )
        )
        .mappings()
        .first()
    )
    return {
        "cliente": info["cliente_nome"],
        "cliente_id": info["cliente_id"],
        "negociacao": (dict(neg) if neg else None),
        "anotacoes": notas,
    }


async def notas_por_telefone(db: AsyncSession, phone_canonical: str, limit: int = 8) -> list[str]:
    """Anotações de um cliente pelo telefone (p/ o José Luís usar no atendimento)."""
    if not phone_canonical:
        return []
    rows = (
        await db.execute(
            text("""
        SELECT nota FROM crm_client_notes WHERE phone_canonical=:p ORDER BY created_at DESC LIMIT :l"""),
            {"p": phone_canonical, "l": limit},
        )
    ).all()
    return [r[0] for r in rows]


# ── Lembretes do dono ("me lembra amanhã de X") ────────────────────────────────────────────
async def agendar_lembrete(db: AsyncSession, quando: datetime, texto: str) -> dict:
    row = (
        (
            await db.execute(
                text(
                    "INSERT INTO crm_owner_reminder (id, quando, texto, created_at) "
                    "VALUES (gen_random_uuid(), :q, :t, now()) RETURNING id"
                ),
                {"q": quando, "t": texto[:1000]},
            )
        )
        .mappings()
        .first()
    )
    await db.commit()
    return {"ok": True, "id": str(row["id"]) if row else None, "quando": quando.isoformat()}


async def followup_em_lote(db: AsyncSession, mensagem: str | None = None, confirmar: bool = False) -> dict:
    """Dá um toque em TODOS os clientes com proposta enviada sem resposta. confirmar=false = preview."""
    pend = await pendentes_sem_resposta(db)
    if not confirmar:
        return {
            "preview": True,
            "qtd": len(pend),
            "clientes": [{"cliente": p["cliente_nome"], "proposta": p["proposta"], "dias": p["dias"]} for p in pend],
            "aviso": "Reenvie com confirmar=true para o José Luís dar um toque em todos (respeita opt-out/horário).",
        }
    enviados, falhas = 0, []
    for p in pend:
        prop = (
            (
                await db.execute(
                    text(
                        "SELECT id, number, client_name, client_phone, client_document FROM proposals "
                        "WHERE is_active AND number=:n LIMIT 1"
                    ),
                    {"n": p["proposta"]},
                )
            )
            .mappings()
            .first()
        )
        if not prop:
            continue
        tgt = await F.resolve_target(db, proposal_id=str(prop["id"]))
        nome = (prop["client_name"] or "").split()[0] if prop["client_name"] else "tudo bem"
        msg = mensagem or (
            f"Olá, {nome}! 😊 Aqui é o José Luís, da Conecta Mais. O Jordan Jesus, do nosso "
            f"time comercial, lhe enviou a proposta {prop['number']} — passei pra saber se "
            f"você teve a chance de ver, e se posso esclarecer alguma dúvida ou te mandar um "
            f"material de apoio (catálogo, vídeos). Fico à disposição! — José Luís · Conecta Mais"
        )
        res = await F.send_followup(
            db,
            target=tgt,
            mensagem=msg,
            canal="whatsapp",
            template="lote",
            proposal_id=str(prop["id"]),
            criado_por="lote",
            ignore_antispam=True,
        )
        if res.get("enviado"):
            enviados += 1
        else:
            falhas.append({"cliente": prop["client_name"], "motivo": res.get("motivo")})
    if enviados:
        await notify_owner(f"📨 Toque em lote enviado para {enviados} cliente(s) com proposta pendente.")
    return {"enviados": enviados, "total": len(pend), "falhas": falhas}


# ── Vínculo com inbound: marca resposta do cliente na negociação ───────────────────────────
async def marcar_resposta_cliente(
    db: AsyncSession, phone_canonical: str, classificacao: str, texto: str | None
) -> None:
    """Atualiza a negociação quando o cliente responde (chamado pelo inbound)."""
    try:
        await db.execute(
            text("""
            UPDATE crm_negociacao_state SET last_client_reply_at=now(),
                   ultimo_status=:st, updated_at=now()
            WHERE phone_canonical=:p AND responsavel <> 'fechado'
        """),
            {"p": phone_canonical, "st": f"{classificacao}: {(texto or '')[:140]}"},
        )
        await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.error("marcar_resposta_cliente falhou: %s", e)
        await db.rollback()
