"""Consultor Comercial (CMO IA) — motor do chat ancorado nos dados reais do CRM.

Clona o padrão do Consultor GED / CFO IA / Consultor Jurídico (chat + anexo +
histórico + contexto REAL), aplicado ao domínio COMERCIAL: funil de vendas,
conversão, MRR, ticket médio e cross-sell da Conecta Mais (segurança
patrimonial, Manaus-AM).

Doutrina: a IA assiste; o gestor decide. NUNCA inventa dado — todo número vem
do banco (leads, opportunities, proposals, client_contracts, clients).
Geração via HUB dos consultores (melhor modelo + fallback + memória compartilhada).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

AREAS_VALIDAS = {"pipeline", "propostas", "clientes", "estrategia"}

DISCLAIMER = (
    "Consultor Comercial IA — as informações vêm dos dados reais do ERP "
    "(leads, oportunidades, propostas, contratos). Números de mercado externos "
    "não estão no sistema; a decisão comercial final é do gestor."
)

MSG_INDISPONIVEL = (
    "Consultor Comercial indisponível — configurar. O provedor de LLM não está "
    "acessível no momento. Os dados do painel abaixo continuam reais; a análise "
    "por IA volta assim que a integração for ajustada."
)

_GATILHOS_ESCALONAR = (
    "desconto", "cancelamento", "cancelar contrato", "rescis", "inadimpl",
    "churn", "jurídic", "juridic", "multa", "reajuste", "renegoci",
    "exclusividade", "concorrente levou",
)

ESTAGIOS_ABERTOS_EXCLUIR = ("closed_won", "closed_lost")

_ROTULOS_ESTAGIO = {
    "new": "Novo",
    "qualified": "Qualificado",
    "proposal": "Proposta",
    "negotiation": "Negociação",
    "closed_won": "Ganho",
    "closed_lost": "Perdido",
}

_ddl_ok = False


async def _ensure_schema(db: AsyncSession) -> None:
    """Cria a tabela de consultas do CMO se não existir (idempotente)."""
    global _ddl_ok
    if _ddl_ok:
        return
    existe = (
        await db.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'comercial_consultas'"
            )
        )
    ).scalar_one()
    if not existe:
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS comercial_consultas (
                    id             BIGSERIAL PRIMARY KEY,
                    area           VARCHAR(20)  NOT NULL,
                    pergunta       TEXT         NOT NULL,
                    resposta       TEXT         NOT NULL,
                    escalonar      BOOLEAN      NOT NULL DEFAULT FALSE,
                    disclaimer     TEXT         NOT NULL,
                    contexto_usado JSONB        NOT NULL DEFAULT '{}'::jsonb,
                    created_by     VARCHAR(64),
                    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
                )
                """
            )
        )
        await db.commit()
    _ddl_ok = True


# ─────────────────────────────────────────────────────────────────────────────
# PANORAMA — fotografia comercial real (funil, propostas, contratos, MRR)
# ─────────────────────────────────────────────────────────────────────────────
async def panorama(db: AsyncSession) -> dict[str, Any]:
    await _ensure_schema(db)

    # Leads: total, novos 30 dias, por status
    lead_tot = (
        await db.execute(
            text(
                "SELECT count(*) AS total, "
                "count(*) FILTER (WHERE created_at >= now() - interval '30 days') AS novos_30d "
                "FROM leads WHERE COALESCE(is_active, true)"
            )
        )
    ).first()
    leads_status = {
        r.status: r.qtd
        for r in (
            await db.execute(
                text(
                    "SELECT status, count(*) AS qtd FROM leads "
                    "WHERE COALESCE(is_active, true) GROUP BY status ORDER BY 2 DESC"
                )
            )
        ).fetchall()
    }

    # Oportunidades: pipeline ABERTO por estágio (count + valor), ativos apenas
    estagios = [
        {
            "estagio": r.stage,
            "rotulo": _ROTULOS_ESTAGIO.get(r.stage, r.stage),
            "qtd": r.qtd,
            "valor": float(r.valor or 0),
        }
        for r in (
            await db.execute(
                text(
                    "SELECT stage, count(*) AS qtd, COALESCE(sum(value),0) AS valor "
                    "FROM opportunities WHERE is_active "
                    "AND stage NOT IN ('closed_won','closed_lost') "
                    "GROUP BY stage ORDER BY 3 DESC"
                )
            )
        ).fetchall()
    ]
    ganhas = (
        await db.execute(
            text(
                "SELECT count(*) AS qtd, COALESCE(sum(value),0) AS valor "
                "FROM opportunities WHERE is_active AND stage = 'closed_won' "
                "AND COALESCE(actual_close_date, updated_at::date) >= (now() - interval '90 days')::date"
            )
        )
    ).first()

    # Propostas: enviadas / aceitas nos últimos 90 dias + retrato por status
    props = (
        await db.execute(
            text(
                "SELECT count(*) FILTER (WHERE sent_at >= now() - interval '90 days') AS enviadas_90d, "
                "count(*) FILTER (WHERE status = 'accepted' "
                "  AND COALESCE(responded_at, updated_at) >= now() - interval '90 days') AS aceitas_90d "
                "FROM proposals WHERE COALESCE(is_active, true)"
            )
        )
    ).first()
    props_status = {
        r.status: r.qtd
        for r in (
            await db.execute(
                text(
                    "SELECT status, count(*) AS qtd FROM proposals "
                    "WHERE COALESCE(is_active, true) GROUP BY status"
                )
            )
        ).fetchall()
    }

    # Contratos ativos + MRR (sum monthly_value) — status é ENUM, cast p/ texto
    contratos = (
        await db.execute(
            text(
                "SELECT count(*) AS ativos, "
                "round(COALESCE(sum(monthly_value),0)::numeric, 2) AS mrr "
                "FROM client_contracts WHERE status::text = 'active'"
            )
        )
    ).first()

    # Clientes ativos — status é ENUM, cast p/ texto
    clientes_ativos = (
        await db.execute(
            text("SELECT count(*) FROM clients WHERE status::text = 'active'")
        )
    ).scalar_one()

    mrr = float(contratos.mrr or 0)
    ativos = int(contratos.ativos or 0)
    pipeline_valor = sum(e["valor"] for e in estagios)
    pipeline_qtd = sum(e["qtd"] for e in estagios)

    return {
        "leads": {
            "total": lead_tot.total,
            "novos_30d": lead_tot.novos_30d,
            "por_status": leads_status,
        },
        "pipeline": {
            "aberto_qtd": pipeline_qtd,
            "aberto_valor": round(pipeline_valor, 2),
            "por_estagio": estagios,
            "ganhas_90d": {"qtd": ganhas.qtd, "valor": float(ganhas.valor or 0)},
        },
        "propostas": {
            "enviadas_90d": props.enviadas_90d,
            "aceitas_90d": props.aceitas_90d,
            "por_status": props_status,
        },
        "contratos": {"ativos": ativos, "mrr": mrr},
        "clientes_ativos": clientes_ativos,
        "ticket_medio_mrr": round(mrr / ativos, 2) if ativos else None,
        # NPS de cliente: não existe tabela no schema atual — omitido com fonte
        # marcada em vez de inventar (doutrina: nunca fabricar dado).
        "nps": {"disponivel": False, "fonte": "sem tabela de NPS de cliente no schema"},
        "fonte": "leads + opportunities + proposals + client_contracts + clients (dados reais do CRM)",
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CHAT — pergunta ancorada no contexto comercial real
# ─────────────────────────────────────────────────────────────────────────────
def _bloco_grupo() -> str:
    from modules.empresas.services.contexto_grupo import bloco_contexto_grupo

    return bloco_contexto_grupo()


_REGRAS_COMUNS = _bloco_grupo() + """
Você é o CMO (diretor comercial) do GRUPO CONECTA MAIS (estrutura acima; \
contratos novos nascem na empresa do serviço: mão de obra=Patrimonial, \
eletrônica/portaria remota=Eletrônica), empresa de \
segurança patrimonial de Manaus-AM (portaria humanizada e remota, vigilância \
eletrônica, principalmente para condomínios). Sua missão: funil de vendas, taxa de \
conversão, MRR, ticket médio e cross-sell na base atual.
REGRAS INEGOCIÁVEIS:
- NUNCA invente número, cliente, lead ou proposta. Use APENAS o contexto real fornecido.
- Se a informação não está no contexto, diga claramente "não está registrado no sistema".
- Valores em reais (BRL). MRR = receita recorrente mensal contratada.
- Responda em Markdown curto: ## Resposta direta, ## Situação real (números do contexto), \
## Próximos passos (checklist acionável), ## Atenção (riscos/oportunidades).
- Decisões sensíveis (desconto agressivo, cancelamento, reajuste, cláusula jurídica) \
devem ser sinalizadas para validação do gestor."""

_LENTES = {
    "pipeline": "FOCO: funil de vendas — leads por status, oportunidades abertas por estágio (quantidade e valor), gargalos de conversão e o que atacar primeiro para mover o funil.",
    "propostas": "FOCO: propostas comerciais — enviadas vs aceitas (taxa de conversão), propostas paradas em rascunho ou sem resposta, follow-up e o que fazer para fechar.",
    "clientes": "FOCO: base de clientes e contratos — clientes ativos, MRR, ticket médio, concentração de receita, oportunidades de cross-sell (ex.: cliente de portaria sem segurança eletrônica) e risco de churn.",
    "estrategia": "FOCO: estratégia comercial — leitura executiva do funil + MRR + conversão; metas, priorização de segmentos (condomínios em Manaus), precificação e crescimento sustentável.",
}


def _detectar_escalonamento(pergunta: str, resposta: str) -> bool:
    alvo = f"{pergunta} {resposta}".lower()
    return any(g in alvo for g in _GATILHOS_ESCALONAR)


def _montar_contexto(pano: dict[str, Any]) -> str:
    linhas = [
        "=== PANORAMA COMERCIAL REAL (agora) ===",
        f"Leads: {pano['leads']['total']} no total | {pano['leads']['novos_30d']} novos nos últimos 30 dias",
        "Leads por status: " + (", ".join(f"{k}={v}" for k, v in pano["leads"]["por_status"].items()) or "nenhum"),
        "",
        f"Pipeline ABERTO: {pano['pipeline']['aberto_qtd']} oportunidades | R$ {pano['pipeline']['aberto_valor']:.2f}",
    ]
    for e in pano["pipeline"]["por_estagio"]:
        linhas.append(f"- {e['rotulo']} ({e['estagio']}): {e['qtd']} oportunidade(s) | R$ {e['valor']:.2f}")
    g = pano["pipeline"]["ganhas_90d"]
    linhas += [
        f"Ganhas nos últimos 90 dias: {g['qtd']} | R$ {g['valor']:.2f}",
        "",
        f"Propostas (90 dias): enviadas={pano['propostas']['enviadas_90d']} | aceitas={pano['propostas']['aceitas_90d']}",
        "Propostas por status: " + (", ".join(f"{k}={v}" for k, v in pano["propostas"]["por_status"].items()) or "nenhuma"),
        "",
        f"Contratos ativos: {pano['contratos']['ativos']} | MRR contratado: R$ {pano['contratos']['mrr']:.2f}",
        f"Clientes ativos: {pano['clientes_ativos']}"
        + (f" | Ticket médio (MRR/contrato): R$ {pano['ticket_medio_mrr']:.2f}" if pano.get("ticket_medio_mrr") else ""),
        "NPS de cliente: não registrado no sistema (sem tabela) — não usar número de NPS.",
    ]
    return "\n".join(linhas)


async def consultar(
    db: AsyncSession, *, area: str, pergunta: str,
    user_id: str | None = None, anexo_texto: str | None = None, anexo_nome: str | None = None,
) -> dict[str, Any]:
    await _ensure_schema(db)
    area_n = (area or "").strip().lower()
    if area_n not in AREAS_VALIDAS:
        raise ValueError(f"Área inválida '{area}'. Válidas: {', '.join(sorted(AREAS_VALIDAS))}")

    pano = await panorama(db)
    system_prompt = f"{_REGRAS_COMUNS}\n\n{_LENTES[area_n]}\n\n{_montar_contexto(pano)}"

    user_content = (pergunta or "").strip() or "Faça um diagnóstico comercial da empresa agora."
    if (anexo_texto or "").strip():
        user_content += (
            f"\n\n=== DOCUMENTO ANEXADO{f' ({anexo_nome})' if anexo_nome else ''} ===\n"
            f"{anexo_texto.strip()[:14000]}\n=== FIM DO DOCUMENTO ===\n\n"
            "Analise o documento acima à luz da pergunta e do panorama comercial real."
        )

    resposta_texto: str | None = None
    llm_meta: dict[str, Any] = {}
    try:
        from modules.ai.conversation.services import consultor_hub as _hub

        _extra = await _hub.contexto_compartilhado(db, "comercial", pergunta)
        _conversa = await _hub.conversa_recente(db, "comercial")
        if _extra:
            system_prompt = f"{system_prompt}\n\n{_extra}"
        if _conversa:
            system_prompt = f"{system_prompt}\n\n{_conversa}"

        from modules.ai.conversation.services.consultor_conhecimento_service import contexto_para_prompt
        system_prompt = system_prompt + contexto_para_prompt("comercial", pergunta)

        resposta_texto, llm_meta = await _hub.gerar(
            messages=[{"role": "user", "content": user_content}],
            system_prompt=system_prompt, max_tokens=2500, temperature=0.2,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Consultor Comercial (CMO): LLM indisponível: %s", e)
        from modules.ai.conversation.services.llm_credit_alert import alertar_llm_indisponivel
        await alertar_llm_indisponivel("Consultor Comercial (CMO)", str(e))

    if not resposta_texto:
        return {
            "resposta": MSG_INDISPONIVEL, "escalonar": False, "disclaimer": DISCLAIMER,
            "id": None, "indisponivel": True, "panorama": pano,
        }

    escalonar = _detectar_escalonamento(pergunta, resposta_texto)
    import json as _json

    row = (
        await db.execute(
            text(
                "INSERT INTO comercial_consultas "
                "(area, pergunta, resposta, escalonar, disclaimer, contexto_usado, created_by) "
                "VALUES (:a, :p, :r, :e, :d, CAST(:ctx AS jsonb), :by) RETURNING id"
            ),
            {
                "a": area_n, "p": user_content[:8000], "r": resposta_texto,
                "e": escalonar, "d": DISCLAIMER,
                "ctx": _json.dumps({"panorama": pano, "llm": llm_meta}, default=str),
                "by": user_id,
            },
        )
    ).first()
    await db.commit()

    # aprendizado permanente (best-effort, nunca quebra o chat)
    from modules.ai.conversation.services import consultor_hub as _hub_aprender
    await _hub_aprender.aprender(db, "comercial", pergunta or "", resposta_texto)

    return {
        "resposta": resposta_texto, "escalonar": escalonar, "disclaimer": DISCLAIMER,
        "id": row.id if row else None, "indisponivel": False, "panorama": pano,
    }


async def listar_consultas(db: AsyncSession, *, area: str | None = None, limit: int = 50) -> list[dict]:
    await _ensure_schema(db)
    where, params = "", {"lim": limit}
    if area:
        where = "WHERE area = :a"; params["a"] = area.strip().lower()
    rows = (
        await db.execute(
            text(
                "SELECT id, area, pergunta, resposta, escalonar, created_at "
                f"FROM comercial_consultas {where} ORDER BY created_at DESC LIMIT :lim"
            ),
            params,
        )
    ).fetchall()
    return [
        {**dict(r._mapping), "created_at": str(r.created_at), "pergunta": r.pergunta[:300]}
        for r in rows
    ]
