"""Consultor de Pessoas (CHRO IA) — DP + RH ancorado nos dados reais do ERP.

Clona o padrão do Consultor GED / CFO IA (chat + anexo + histórico + contexto REAL),
aplicado ao domínio de Gestão de Pessoas: folha, ponto, benefícios/SST e movimentação
(admissões, férias, rescisões).

PERSONA: CHRO/DP da Conecta Mais Eletrônica (segurança patrimonial, Manaus-AM).
Base legal: CLT + CCT SINDECOMPRESTS AM000613/2025 — somos AGENTES DE PORTARIA
(NÃO vigilância armada); piso da categoria 2026 = R$ 1.670,00 (nunca o mínimo federal
como base salarial); escalas 12x36; VT/VR por escala; ASOs e EPIs obrigatórios.

REGRA DURA: dado trabalhista/legal NUNCA se inventa. Todo número vem do banco;
o que não está registrado é dito como "não registrado no sistema".
Geração via HUB dos consultores (melhor modelo + fallback + memória compartilhada).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

AREAS_VALIDAS = {"folha", "ponto", "beneficios_sst", "movimentacao"}

DISCLAIMER = (
    "Consultor de Pessoas IA — as informações vêm dos dados reais do ERP "
    "(funcionários, folha, ponto, ASOs, EPIs, férias, rescisões). Questões "
    "trabalhistas sensíveis devem ser validadas com o jurídico/contabilidade "
    "antes de qualquer ato formal; a decisão final é do gestor."
)

MSG_INDISPONIVEL = (
    "Consultor de Pessoas indisponível — configurar. O provedor de LLM não está "
    "acessível no momento. Os dados do painel abaixo continuam reais; a análise "
    "por IA volta assim que a integração for ajustada."
)

# Gatilhos que exigem validação humana (jurídico/contabilidade) antes de agir
_GATILHOS_ESCALONAR = (
    "justa causa", "rescis", "demiss", "estabilidade", "gestante", "grávida",
    "gravida", "acidente", "cat ", "afastamento", "inss", "assédio", "assedio",
    "sindicato", "greve", "processo", "reclamatória", "reclamatoria", "esocial",
    "multa", "fgts atras", "não recolh", "nao recolh", "insalubr", "periculos",
)

_ddl_ok = False


async def _ensure_schema(db: AsyncSession) -> None:
    """Cria a tabela de consultas do CHRO se não existir (idempotente)."""
    global _ddl_ok
    if _ddl_ok:
        return
    existe = (
        await db.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'rh_consultas'"
            )
        )
    ).scalar_one()
    if not existe:
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS rh_consultas (
                    id             BIGSERIAL PRIMARY KEY,
                    area           VARCHAR(20)  NOT NULL,
                    competencia    VARCHAR(7),
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
# PANORAMA — fotografia real de DP+RH (todas as queries validadas no banco)
# ─────────────────────────────────────────────────────────────────────────────
async def panorama(db: AsyncSession) -> dict[str, Any]:
    await _ensure_schema(db)

    # Headcount por status (employees.status é minúsculo: ativo/inativo/...)
    headcount = {
        r.status: r.qtd
        for r in (
            await db.execute(
                text("SELECT status, count(*) AS qtd FROM employees GROUP BY status")
            )
        ).fetchall()
    }
    ativos = int(headcount.get("ativo", 0))

    # Top 5 cargos entre os ativos
    cargos_top = [
        {"cargo": r.cargo, "quantidade": r.qtd}
        for r in (
            await db.execute(
                text(
                    "SELECT cargo, count(*) AS qtd FROM employees "
                    "WHERE status = 'ativo' AND cargo IS NOT NULL "
                    "GROUP BY cargo ORDER BY qtd DESC LIMIT 5"
                )
            )
        ).fetchall()
    ]

    # Folha — competência mais recente registrada em hr_payslips
    folha_row = (
        await db.execute(
            text(
                "SELECT reference_year, reference_month, count(*) AS holerites, "
                "round(COALESCE(sum(net_salary), 0)::numeric, 2) AS liquido, "
                "round(COALESCE(sum(fgts_value), 0)::numeric, 2) AS fgts, "
                "round(COALESCE(sum(inss_value), 0)::numeric, 2) AS inss "
                "FROM hr_payslips "
                "WHERE (reference_year, reference_month) = ("
                "  SELECT reference_year, reference_month FROM hr_payslips "
                "  ORDER BY reference_year DESC, reference_month DESC LIMIT 1) "
                "GROUP BY reference_year, reference_month"
            )
        )
    ).first()
    if folha_row:
        folha = {
            "competencia": f"{folha_row.reference_year:04d}-{folha_row.reference_month:02d}",
            "holerites": int(folha_row.holerites),
            "liquido_total": float(folha_row.liquido),
            "fgts_total": float(folha_row.fgts),
            "inss_total": float(folha_row.inss),
        }
    else:
        folha = {
            "competencia": None, "holerites": 0, "liquido_total": 0.0,
            "fgts_total": 0.0, "inss_total": 0.0,
            "aviso": "nenhuma folha registrada em hr_payslips",
        }

    # Ponto — batidas dos últimos 7 dias + pendências
    ponto_row = (
        await db.execute(
            text(
                "SELECT count(*) AS batidas, "
                "count(*) FILTER (WHERE status = 'pending') AS pendentes_revisao, "
                "count(DISTINCT employee_id) AS funcionarios_batendo "
                "FROM gp_clock_punches "
                "WHERE (punch_timestamp) >= now() - interval '7 days'"
            )
        )
    ).first()
    justificativas_pendentes = int(
        (
            await db.execute(
                text(
                    "SELECT count(*) FROM gp_justifications "
                    "WHERE lower(COALESCE(status, '')) IN ('pending', 'pendente')"
                )
            )
        ).scalar_one()
    )
    ponto = {
        "batidas_7d": int(ponto_row.batidas),
        "batidas_pendentes_revisao": int(ponto_row.pendentes_revisao),
        "funcionarios_batendo_7d": int(ponto_row.funcionarios_batendo),
        "justificativas_pendentes": justificativas_pendentes,
    }

    # Férias — pedidos aguardando aprovação + agendadas (hr_vacation_requests)
    ferias_row = (
        await db.execute(
            text(
                "SELECT count(*) FILTER (WHERE status = 'SUBMITTED') AS aguardando_aprovacao, "
                "count(*) FILTER (WHERE status = 'APPROVED') AS aprovadas, "
                "count(*) FILTER (WHERE start_date >= CURRENT_DATE "
                "  AND status NOT IN ('CANCELLED', 'REJECTED')) AS agendadas_futuras "
                "FROM hr_vacation_requests"
            )
        )
    ).first()
    ferias = {
        "aguardando_aprovacao": int(ferias_row.aguardando_aprovacao),
        "aprovadas": int(ferias_row.aprovadas),
        "agendadas_futuras": int(ferias_row.agendadas_futuras),
        "fonte": "hr_vacation_requests",
    }

    # SST — ASOs vencendo em 60 dias E vencidas (honestidade: vencida é pior)
    aso_row = (
        await db.execute(
            text(
                "SELECT count(*) FILTER (WHERE data_validade BETWEEN CURRENT_DATE "
                "  AND CURRENT_DATE + 60) AS vencendo_60d, "
                "count(*) FILTER (WHERE data_validade < CURRENT_DATE) AS vencidas, "
                "count(*) AS total FROM gp_asos"
            )
        )
    ).first()
    asos = {
        "vencendo_60d": int(aso_row.vencendo_60d),
        "vencidas": int(aso_row.vencidas),
        "total": int(aso_row.total),
    }

    # EPIs — entregas nos últimos 90 dias + última entrega registrada
    epi_row = (
        await db.execute(
            text(
                "SELECT count(*) FILTER (WHERE data_entrega >= CURRENT_DATE - 90) "
                "  AS entregas_90d, "
                "count(*) AS total, max(data_entrega) AS ultima_entrega "
                "FROM gp_epi_deliveries"
            )
        )
    ).first()
    epis = {
        "entregas_90d": int(epi_row.entregas_90d),
        "total": int(epi_row.total),
        "ultima_entrega": str(epi_row.ultima_entrega) if epi_row.ultima_entrega else None,
    }

    # Movimentação — rescisões recentes (termination_processes, 180 dias)
    resc_rows = (
        await db.execute(
            text(
                "SELECT status, count(*) AS qtd FROM termination_processes "
                "WHERE created_at >= now() - interval '180 days' GROUP BY status"
            )
        )
    ).fetchall()
    rescisoes = {
        "ultimos_180d": sum(int(r.qtd) for r in resc_rows),
        "por_status": {r.status: int(r.qtd) for r in resc_rows},
    }

    return {
        "headcount": {"ativos": ativos, "por_status": headcount},
        "cargos_top5": cargos_top,
        "folha": folha,
        "ponto": ponto,
        "ferias": ferias,
        "asos": asos,
        "epis": epis,
        "rescisoes": rescisoes,
        "fonte": (
            "employees + hr_payslips + gp_clock_punches + gp_justifications + "
            "hr_vacation_requests + gp_asos + gp_epi_deliveries + termination_processes"
        ),
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CHAT — pergunta ancorada no contexto real
# ─────────────────────────────────────────────────────────────────────────────
def _bloco_grupo() -> str:
    from modules.empresas.services.contexto_grupo import bloco_contexto_grupo

    return bloco_contexto_grupo()


_REGRAS_COMUNS = _bloco_grupo() + """
Você é o CONSULTOR DE PESSOAS (CHRO/DP) do GRUPO CONECTA MAIS \
(segurança patrimonial, Manaus-AM), especialista em Departamento Pessoal e Recursos Humanos. \
O EMPREGADOR dos CLT é a empresa indicada no cadastro de cada funcionário (a folha migra para \
a Conecta Mais Patrimonial na transição conduzida pela Portte).
BASE LEGAL: CLT + CCT SINDECOMPRESTS AM000613/2025. A empresa emprega AGENTES DE PORTARIA \
(NÃO é vigilância armada — nunca aplique regras de vigilante). O PISO da categoria em 2026 \
é R$ 1.670,00 e é a base salarial mínima — NUNCA o mínimo federal (R$ 1.621 serve só para \
referências como INSS). Escalas típicas 12x36; VT/VR conforme escala; ASOs (admissional, \
periódico, demissional) e EPIs são obrigações de SST.
REGRAS INEGOCIÁVEIS:
- Dado trabalhista/legal NUNCA se inventa: nem valor de verba, nem prazo, nem artigo de lei \
duvidoso, nem nome de funcionário. Use APENAS o contexto real fornecido.
- Se a informação não está no contexto, diga claramente "não está registrado no sistema".
- ASO vencida e EPI sem entrega registrada são riscos de SST — sempre aponte.
- Rescisão, justa causa, estabilidade, acidente e afastamento INSS exigem validação do \
jurídico/contabilidade antes de qualquer ato formal — recomende o escalonamento.
- Responda em Markdown curto: ## Resposta direta, ## Situação real (números do contexto), \
## Próximos passos (checklist acionável), ## Atenção (riscos/prazos)."""

_LENTES = {
    "folha": (
        "FOCO: folha de pagamento — competência mais recente registrada, holerites, líquido, "
        "FGTS e INSS reais; piso CCT R$ 1.670 como base; adicionais por pessoa conforme CCT; "
        "cruzamento com headcount ativo (holerites ≠ ativos merece explicação)."
    ),
    "ponto": (
        "FOCO: ponto eletrônico — batidas dos últimos 7 dias, batidas pendentes de revisão, "
        "justificativas pendentes, cobertura (quantos ativos estão batendo); riscos de escala "
        "12x36 e de fechamento de ponto para a folha."
    ),
    "beneficios_sst": (
        "FOCO: benefícios e SST — VT/VR conforme CCT e escala, ASOs (vencidas e vencendo em "
        "60 dias — vencida é irregularidade), entregas de EPI registradas (sem registro recente "
        "= risco de fiscalização/NR-6); nunca minimize pendência de SST."
    ),
    "movimentacao": (
        "FOCO: movimentação de pessoal — headcount por status, admissões, férias (pedidos "
        "aguardando aprovação, agendadas), rescisões em andamento; prazos legais de férias "
        "(período concessivo) e de rescisão sempre com validação jurídica."
    ),
}


def _detectar_escalonamento(pergunta: str, resposta: str) -> bool:
    alvo = f"{pergunta} {resposta}".lower()
    return any(g in alvo for g in _GATILHOS_ESCALONAR)


def _montar_contexto(pano: dict[str, Any]) -> str:
    hc = pano["headcount"]
    folha = pano["folha"]
    ponto = pano["ponto"]
    ferias = pano["ferias"]
    asos = pano["asos"]
    epis = pano["epis"]
    resc = pano["rescisoes"]

    linhas = [
        "=== PANORAMA REAL DE PESSOAS (DP+RH) — dados vivos do banco ===",
        f"HEADCOUNT: {hc['ativos']} ativos | por status: "
        + ", ".join(f"{k}={v}" for k, v in sorted(hc["por_status"].items())),
        "TOP CARGOS (ativos): "
        + ("; ".join(f"{c['cargo']}={c['quantidade']}" for c in pano["cargos_top5"]) or "sem registro"),
        "",
    ]
    if folha.get("competencia"):
        linhas.append(
            f"FOLHA (competência {folha['competencia']}): {folha['holerites']} holerites | "
            f"líquido R$ {folha['liquido_total']:.2f} | FGTS R$ {folha['fgts_total']:.2f} | "
            f"INSS R$ {folha['inss_total']:.2f}"
        )
    else:
        linhas.append("FOLHA: nenhuma competência registrada em hr_payslips.")
    linhas += [
        f"PONTO (últimos 7 dias): {ponto['batidas_7d']} batidas | "
        f"{ponto['funcionarios_batendo_7d']} funcionários batendo | "
        f"{ponto['batidas_pendentes_revisao']} batidas pendentes de revisão | "
        f"{ponto['justificativas_pendentes']} justificativas pendentes",
        f"FÉRIAS: {ferias['aguardando_aprovacao']} pedidos aguardando aprovação | "
        f"{ferias['aprovadas']} aprovadas | {ferias['agendadas_futuras']} agendadas futuras",
        f"ASOs: {asos['vencidas']} VENCIDAS (irregularidade) | {asos['vencendo_60d']} vencendo "
        f"em 60 dias | {asos['total']} no total",
        f"EPIs: {epis['entregas_90d']} entregas nos últimos 90 dias | última entrega registrada: "
        f"{epis['ultima_entrega'] or 'nenhuma'} | {epis['total']} entregas no histórico",
        f"RESCISÕES (últimos 180 dias): {resc['ultimos_180d']} processo(s)"
        + (
            " — " + ", ".join(f"{k}={v}" for k, v in sorted(resc["por_status"].items()))
            if resc["por_status"] else ""
        ),
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

    user_content = (pergunta or "").strip() or "Faça um diagnóstico da situação de pessoas (DP+RH) da empresa."
    if (anexo_texto or "").strip():
        user_content += (
            f"\n\n=== DOCUMENTO ANEXADO{f' ({anexo_nome})' if anexo_nome else ''} ===\n"
            f"{anexo_texto.strip()[:14000]}\n=== FIM DO DOCUMENTO ===\n\n"
            "Analise o documento acima à luz da pergunta e do panorama real de pessoas."
        )

    resposta_texto: str | None = None
    llm_meta: dict[str, Any] = {}
    try:
        from modules.ai.conversation.services import consultor_hub as _hub
        _extra = await _hub.contexto_compartilhado(db, 'rh', pergunta)
        _conversa = await _hub.conversa_recente(db, 'rh')
        if _extra:
            system_prompt = f"{system_prompt}\n\n{_extra}"
        if _conversa:
            system_prompt = f"{system_prompt}\n\n{_conversa}"
        from modules.ai.conversation.services.consultor_conhecimento_service import contexto_para_prompt
        system_prompt = system_prompt + contexto_para_prompt("chro", pergunta)
        resposta_texto, llm_meta = await _hub.gerar(
            messages=[{"role": "user", "content": user_content}],
            system_prompt=system_prompt, max_tokens=2500, temperature=0.2,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Consultor Pessoas (CHRO): LLM indisponível: %s", e)
        from modules.ai.conversation.services.llm_credit_alert import alertar_llm_indisponivel
        await alertar_llm_indisponivel("Consultor Pessoas (CHRO)", str(e))

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
                "INSERT INTO rh_consultas "
                "(area, competencia, pergunta, resposta, escalonar, disclaimer, contexto_usado, created_by) "
                "VALUES (:a, :comp, :p, :r, :e, :d, CAST(:ctx AS jsonb), :by) RETURNING id"
            ),
            {
                "a": area_n, "comp": pano["folha"].get("competencia"),
                "p": user_content[:8000], "r": resposta_texto, "e": escalonar,
                "d": DISCLAIMER,
                "ctx": _json.dumps({"panorama": pano, "llm": llm_meta}, default=str),
                "by": user_id,
            },
        )
    ).first()
    await db.commit()

    # aprendizado permanente (best-effort, nunca quebra o chat)
    try:
        from modules.ai.conversation.services import consultor_hub as _hub
        await _hub.aprender(db, 'rh', pergunta or '', resposta_texto)
    except Exception as e:  # noqa: BLE001
        logger.warning("Consultor Pessoas: aprender falhou: %s", e)

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
                "SELECT id, area, competencia, pergunta, resposta, escalonar, created_at "
                f"FROM rh_consultas {where} ORDER BY created_at DESC LIMIT :lim"
            ),
            params,
        )
    ).fetchall()
    return [
        {**dict(r._mapping), "created_at": str(r.created_at), "pergunta": r.pergunta[:300]}
        for r in rows
    ]
