"""Consultor Executivo (CEO IA) — visão cross-módulo da Conecta Mais.

Espelha o padrão CFO IA / Consultor Jurídico / Consultor GED (chat + anexo + histórico
+ contexto REAL), elevado ao nível executivo: uma única fotografia que cruza comercial,
pessoas, financeiro, fiscal, jurídico e GED para apoiar as decisões do Jordan.

Doutrina: a IA aconselha; o CEO decide. NUNCA inventa dado — todo número vem do banco.
Um domínio indisponível NÃO derruba o panorama: o bloco vem marcado 'indisponivel'.
Hub-wired: memórias compartilhadas + conversa cruzada via consultor_hub (origem 'ceo').
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

AREAS_VALIDAS = {"visao_geral", "riscos", "crescimento", "prioridades"}

DISCLAIMER = (
    "Consultor Executivo IA — as informações vêm dos dados reais do ERP (KPIs, contratos, "
    "folha, NFS-e, funil comercial, contas e processos). Números são apoio à decisão; "
    "a decisão final é do CEO, com validação da contabilidade/jurídico quando couber."
)

MSG_INDISPONIVEL = (
    "Consultor Executivo indisponível — o provedor de LLM não está acessível no momento. "
    "Os dados do painel abaixo continuam reais; a análise por IA volta assim que a "
    "integração for restabelecida."
)

_GATILHOS_ESCALONAR = (
    "demiss", "rescis", "justa causa", "processo", "liminar", "multa", "autua",
    "inadimpl", "runway", "caixa negativ", "dívida", "divida", "fgts atras",
    "não recolh", "nao recolh", "encerrar contrato", "cancelamento de contrato",
    "simples nacional", "lucro real", "migra",
)

_ddl_ok = False


async def _ensure_schema(db: AsyncSession) -> None:
    """Cria a tabela de consultas do CEO se não existir (idempotente)."""
    global _ddl_ok
    if _ddl_ok:
        return
    existe = (
        await db.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'ceo_consultas'"
            )
        )
    ).scalar_one()
    if not existe:
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS ceo_consultas (
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
# PANORAMA — fotografia CROSS-MÓDULO (cada bloco isolado; um domínio fora do ar
# não derruba a fotografia inteira — o bloco vem como 'indisponivel')
# ─────────────────────────────────────────────────────────────────────────────
async def panorama(db: AsyncSession) -> dict[str, Any]:
    await _ensure_schema(db)
    pano: dict[str, Any] = {}

    # 1) KPIs executivos — todos os 10 (executive_kpis)
    try:
        rows = (
            await db.execute(
                text(
                    "SELECT code, name, current_value, previous_value, unit, trend, status "
                    "FROM executive_kpis WHERE COALESCE(ativo, true) "
                    "ORDER BY display_order NULLS LAST, code"
                )
            )
        ).fetchall()
        pano["kpis"] = [
            {
                "code": r.code,
                "nome": r.name,
                "valor": float(r.current_value) if r.current_value is not None else None,
                "anterior": float(r.previous_value) if r.previous_value is not None else None,
                "unidade": r.unit,
                "tendencia": r.trend,
                "status": r.status,
            }
            for r in rows
        ]
    except Exception as e:  # noqa: BLE001
        logger.warning("panorama CEO: kpis indisponivel: %s", e)
        pano["kpis"] = "indisponivel"

    # 2) Contratos / MRR (client_contracts)
    try:
        r = (
            await db.execute(
                text(
                    "SELECT count(*) contratos, round(COALESCE(sum(monthly_value),0)::numeric,2) mrr "
                    "FROM client_contracts WHERE status = 'active' AND COALESCE(ativo, true)"
                )
            )
        ).first()
        pano["contratos"] = {"ativos": int(r.contratos), "mrr": float(r.mrr)}
    except Exception as e:  # noqa: BLE001
        logger.warning("panorama CEO: contratos indisponivel: %s", e)
        pano["contratos"] = "indisponivel"

    # 3) Pessoas — funcionários ativos (employees)
    try:
        n = (
            # status='ativo' e o criterio canonico (t2 2026-07-07: is_active e flag podre — 47 errado vs 50 real)
            await db.execute(text("SELECT count(*) FROM employees WHERE status = 'ativo'"))
        ).scalar_one()
        pano["funcionarios_ativos"] = int(n)
    except Exception as e:  # noqa: BLE001
        logger.warning("panorama CEO: employees indisponivel: %s", e)
        pano["funcionarios_ativos"] = "indisponivel"

    # 4) Folha — última competência fechada (hr_payslips)
    try:
        r = (
            await db.execute(
                text(
                    "SELECT reference_year, reference_month, count(*) holerites, "
                    "round(COALESCE(sum(net_salary),0)::numeric,2) liquido "
                    "FROM hr_payslips "
                    "GROUP BY reference_year, reference_month "
                    "ORDER BY reference_year DESC, reference_month DESC LIMIT 1"
                )
            )
        ).first()
        pano["folha_ultima"] = (
            {
                "competencia": f"{r.reference_year:04d}-{r.reference_month:02d}",
                "holerites": int(r.holerites),
                "liquido": float(r.liquido),
            }
            if r
            else None
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("panorama CEO: folha indisponivel: %s", e)
        pano["folha_ultima"] = "indisponivel"

    # 5) Fiscal — NFS-e do mês corrente (nfse_emitidas_nacional; competencia = 'YYYY-MM')
    try:
        comp = date.today().strftime("%Y-%m")
        r = (
            await db.execute(
                text(
                    "SELECT count(*) qtd, round(COALESCE(sum(valor_servicos),0)::numeric,2) valor "
                    "FROM nfse_emitidas_nacional WHERE competencia = :comp"
                ),
                {"comp": comp},
            )
        ).first()
        pano["nfse_mes_corrente"] = {
            "competencia": comp,
            "qtd": int(r.qtd),
            "valor_servicos": float(r.valor),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("panorama CEO: nfse indisponivel: %s", e)
        pano["nfse_mes_corrente"] = "indisponivel"

    # 6) Comercial — leads e oportunidades ABERTOS (leads + opportunities)
    try:
        rl = (
            await db.execute(
                text(
                    "SELECT count(*) FROM leads WHERE is_active "
                    "AND lower(COALESCE(status,'')) NOT IN "
                    "('won','lost','converted','disqualified','arquivado')"
                )
            )
        ).scalar_one()
        ro = (
            await db.execute(
                text(
                    "SELECT count(*) qtd, round(COALESCE(sum(value),0)::numeric,2) valor "
                    "FROM opportunities WHERE is_active AND stage NOT ILIKE 'closed%'"
                )
            )
        ).first()
        pano["comercial"] = {
            "leads_abertos": int(rl),
            "oportunidades_abertas": int(ro.qtd),
            "pipeline_valor": float(ro.valor),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("panorama CEO: comercial indisponivel: %s", e)
        pano["comercial"] = "indisponivel"

    # 7) Financeiro — vencidos (receivable_accounts / payable_accounts; status PT-BR)
    try:
        rr = (
            await db.execute(
                text(
                    "SELECT count(*) qtd, "
                    "round(COALESCE(sum(COALESCE(remaining_value, net_value)),0)::numeric,2) valor "
                    "FROM receivable_accounts "
                    "WHERE lower(status) IN ('pendente','parcial','vencida','vencido') "
                    "AND due_date < CURRENT_DATE AND COALESCE(ativo, true)"
                )
            )
        ).first()
        rp = (
            await db.execute(
                text(
                    "SELECT count(*) qtd, "
                    "round(COALESCE(sum(COALESCE(remaining_value, net_value)),0)::numeric,2) valor "
                    "FROM payable_accounts "
                    "WHERE lower(status) IN ('pendente','parcial','vencida','vencido','aprovada') "
                    "AND due_date < CURRENT_DATE AND COALESCE(ativo, true)"
                )
            )
        ).first()
        pano["vencidos"] = {
            "receber": {"qtd": int(rr.qtd), "valor": float(rr.valor)},
            "pagar": {"qtd": int(rp.qtd), "valor": float(rp.valor)},
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("panorama CEO: vencidos indisponivel: %s", e)
        pano["vencidos"] = "indisponivel"

    # 8) Jurídico — processos em aberto (juridico_processos)
    try:
        rows = (
            await db.execute(
                text(
                    "SELECT numero, tipo, reclamante, status FROM juridico_processos "
                    "WHERE lower(COALESCE(status,'')) NOT IN ('encerrado','arquivado','concluido') "
                    "ORDER BY created_at DESC LIMIT 10"
                )
            )
        ).fetchall()
        pano["juridico"] = {
            "processos_abertos": len(rows),
            "processos": [
                {"numero": r.numero, "tipo": r.tipo, "reclamante": r.reclamante, "status": r.status}
                for r in rows
            ],
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("panorama CEO: juridico indisponivel: %s", e)
        pano["juridico"] = "indisponivel"

    # 9) GED — intercorrências abertas (gedeon_intercorrencias; tabela é criada
    #    lazy pelo Consultor GED — se ainda não existe, o dado honesto é zero registro)
    try:
        existe = (
            await db.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_name = 'gedeon_intercorrencias'"
                )
            )
        ).scalar_one()
        if existe:
            r = (
                await db.execute(
                    text(
                        "SELECT count(*) total, count(*) FILTER (WHERE status='aberta') abertas "
                        "FROM gedeon_intercorrencias"
                    )
                )
            ).first()
            pano["ged_intercorrencias"] = {"abertas": int(r.abertas), "total": int(r.total)}
        else:
            pano["ged_intercorrencias"] = {"abertas": 0, "total": 0, "obs": "sem registros ainda"}
    except Exception as e:  # noqa: BLE001
        logger.warning("panorama CEO: ged indisponivel: %s", e)
        pano["ged_intercorrencias"] = "indisponivel"

    pano["fonte"] = (
        "executive_kpis + client_contracts + employees + hr_payslips + "
        "nfse_emitidas_nacional + leads/opportunities + receivable/payable_accounts + "
        "juridico_processos + gedeon_intercorrencias (SQL read-only, sem inferência)"
    )
    pano["gerado_em"] = datetime.now().isoformat(timespec="seconds")
    return pano


# ─────────────────────────────────────────────────────────────────────────────
# CHAT — pergunta ancorada na fotografia cross-módulo
# ─────────────────────────────────────────────────────────────────────────────
def _bloco_grupo() -> str:
    from modules.empresas.services.contexto_grupo import bloco_contexto_grupo

    return bloco_contexto_grupo()


_REGRAS_COMUNS = _bloco_grupo() + """
Você é o CONSELHEIRO EXECUTIVO do Jordan, CEO do GRUPO CONECTA MAIS \
(estrutura societária REAL acima — a segmentação é PERMANENTE e a migração dos \
contratos humanizados p/ a Patrimonial JÁ ESTÁ EM CURSO, com aditivos).
REGRAS INEGOCIÁVEIS:
- NUNCA invente número, cliente, funcionário, processo ou prazo. Use APENAS o contexto real fornecido.
- Se um bloco vier marcado 'indisponivel', diga que aquele domínio está fora do ar — não estime.
- Se a informação não está no contexto, diga claramente "não está registrado no sistema".
- Pense como conselheiro de CEO: conecte os módulos (um vencido a receber é caixa, mas também \
relacionamento com cliente; um processo trabalhista é jurídico, mas também gestão de pessoas).
- Responda em Markdown curto: ## Resposta direta, ## Leitura executiva (números do contexto), \
## Recomendações (priorizadas, acionáveis), ## Atenção (riscos/prazos).
- Decisões tributárias, trabalhistas e judiciais exigem validação da contabilidade/jurídico — sinalize."""

_LENTES = {
    "visao_geral": "FOCO: visão geral do negócio — leia a fotografia inteira (KPIs, MRR, folha, funil, vencidos, jurídico) e dê ao CEO o estado da empresa em linguagem direta.",
    "riscos": "FOCO: riscos — vencidos (a receber e a pagar), processos jurídicos abertos, concentração de receita, custo de folha sobre faturamento, pendências GED. Ordene por severidade e aponte o dono de cada risco.",
    "crescimento": "FOCO: crescimento — pipeline comercial (leads e oportunidades abertas), ticket médio, MRR por contrato, espaço para cross-sell e a transição societária (novos contratos no CNPJ certo).",
    "prioridades": "FOCO: prioridades da semana — das informações reais, extraia as 3 a 5 ações de maior impacto para o CEO agora, com critério explícito de por que cada uma vem antes.",
}


def _detectar_escalonamento(pergunta: str, resposta: str) -> bool:
    alvo = f"{pergunta} {resposta}".lower()
    return any(g in alvo for g in _GATILHOS_ESCALONAR)


def _fmt_brl(v: Any) -> str:
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "—"


def _montar_contexto(pano: dict[str, Any]) -> str:
    """Serializa a fotografia cross-módulo em texto de prompt (só fatos do banco)."""
    linhas = ["=== FOTOGRAFIA REAL DA EMPRESA (cross-módulo, agora) ==="]

    kpis = pano.get("kpis")
    if isinstance(kpis, list):
        linhas.append("KPIs EXECUTIVOS:")
        for k in kpis:
            val = k["valor"]
            valor_txt = "sem valor" if val is None else f"{val:,.2f} {k.get('unidade') or ''}".strip()
            extra = f" (anterior {k['anterior']:,.2f})" if k.get("anterior") is not None else ""
            linhas.append(f"- {k['code']} · {k['nome']}: {valor_txt}{extra} | tendência: {k.get('tendencia') or 'n/d'}")
    else:
        linhas.append("KPIs EXECUTIVOS: indisponível")

    c = pano.get("contratos")
    linhas.append(
        f"CONTRATOS: {c['ativos']} ativos | MRR {_fmt_brl(c['mrr'])}"
        if isinstance(c, dict) else "CONTRATOS: indisponível"
    )

    f = pano.get("funcionarios_ativos")
    linhas.append(
        f"PESSOAS: {f} funcionários ativos" if isinstance(f, int) else "PESSOAS: indisponível"
    )

    fo = pano.get("folha_ultima")
    if isinstance(fo, dict):
        linhas.append(
            f"FOLHA (última competência {fo['competencia']}): {fo['holerites']} holerites, "
            f"líquido {_fmt_brl(fo['liquido'])}"
        )
    else:
        linhas.append("FOLHA: " + ("sem competência fechada" if fo is None else "indisponível"))

    n = pano.get("nfse_mes_corrente")
    if isinstance(n, dict):
        linhas.append(
            f"FISCAL (NFS-e {n['competencia']}): {n['qtd']} notas, serviços {_fmt_brl(n['valor_servicos'])}"
            + (" — mês ainda sem emissão" if n["qtd"] == 0 else "")
        )
    else:
        linhas.append("FISCAL (NFS-e mês corrente): indisponível")

    co = pano.get("comercial")
    if isinstance(co, dict):
        linhas.append(
            f"COMERCIAL: {co['leads_abertos']} leads abertos | "
            f"{co['oportunidades_abertas']} oportunidades abertas somando {_fmt_brl(co['pipeline_valor'])}"
        )
    else:
        linhas.append("COMERCIAL: indisponível")

    v = pano.get("vencidos")
    if isinstance(v, dict):
        linhas.append(
            f"VENCIDOS: a receber {v['receber']['qtd']} títulos ({_fmt_brl(v['receber']['valor'])}) | "
            f"a pagar {v['pagar']['qtd']} títulos ({_fmt_brl(v['pagar']['valor'])})"
        )
    else:
        linhas.append("VENCIDOS: indisponível")

    j = pano.get("juridico")
    if isinstance(j, dict):
        linhas.append(f"JURÍDICO: {j['processos_abertos']} processo(s) em aberto")
        for p in j.get("processos", [])[:5]:
            linhas.append(
                f"- processo {p.get('numero') or 's/nº'} | {p.get('tipo') or 'tipo n/d'} | "
                f"reclamante {p.get('reclamante') or 'n/d'} | status {p.get('status') or 'n/d'}"
            )
    else:
        linhas.append("JURÍDICO: indisponível")

    g = pano.get("ged_intercorrencias")
    if isinstance(g, dict):
        linhas.append(
            f"GED: {g['abertas']} intercorrência(s) aberta(s) de {g['total']} registradas"
            + (f" ({g['obs']})" if g.get("obs") else "")
        )
    else:
        linhas.append("GED: indisponível")

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

    user_content = (pergunta or "").strip() or "Faça uma leitura executiva da empresa agora."
    if (anexo_texto or "").strip():
        user_content += (
            f"\n\n=== DOCUMENTO ANEXADO{f' ({anexo_nome})' if anexo_nome else ''} ===\n"
            f"{anexo_texto.strip()[:14000]}\n=== FIM DO DOCUMENTO ===\n\n"
            "Analise o documento acima à luz da pergunta e da fotografia real da empresa."
        )

    resposta_texto: str | None = None
    llm_meta: dict[str, Any] = {}
    try:
        from modules.ai.conversation.services import consultor_hub as _hub

        _extra = await _hub.contexto_compartilhado(db, "ceo", pergunta)
        _conversa = await _hub.conversa_recente(db, "ceo")
        if not _conversa:
            _conversa = await _conversa_recente_local(db)
        if _extra:
            system_prompt = f"{system_prompt}\n\n{_extra}"
        if _conversa:
            system_prompt = f"{system_prompt}\n\n{_conversa}"

        from modules.ai.conversation.services.consultor_conhecimento_service import contexto_para_prompt
        system_prompt = system_prompt + contexto_para_prompt("ceo", pergunta)

        resposta_texto, llm_meta = await _hub.gerar(
            messages=[{"role": "user", "content": user_content}],
            system_prompt=system_prompt, max_tokens=2500, temperature=0.2,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Consultor Executivo (CEO): LLM indisponível: %s", e)
        from modules.ai.conversation.services.llm_credit_alert import alertar_llm_indisponivel

        await alertar_llm_indisponivel("Consultor Executivo (CEO)", str(e))

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
                "INSERT INTO ceo_consultas "
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
    from modules.ai.conversation.services import consultor_hub as _hub2

    await _hub2.aprender(db, "ceo", pergunta or "", resposta_texto)

    return {
        "resposta": resposta_texto, "escalonar": escalonar, "disclaimer": DISCLAIMER,
        "id": row.id if row else None, "indisponivel": False, "panorama": pano,
    }


async def _conversa_recente_local(db: AsyncSession, *, limit: int = 6) -> str:
    """Continuidade do próprio CEO a partir de ceo_consultas (o hub ainda não
    conhece a origem 'ceo' em TABELAS_CONSULTAS — fallback local, mesmo formato)."""
    try:
        rows = (
            await db.execute(
                text(
                    "SELECT pergunta, resposta FROM ceo_consultas "
                    "ORDER BY created_at DESC LIMIT :lim"
                ),
                {"lim": limit},
            )
        ).fetchall()
    except Exception:  # noqa: BLE001
        return ""
    if not rows:
        return ""
    linhas = ["=== CONVERSA RECENTE (continuidade — não repita o que já foi dito) ==="]
    for r in reversed(rows):
        linhas.append(f"CEO: {r.pergunta[:150]}")
        linhas.append(f"Você: {r.resposta[:250]}")
    return "\n".join(linhas)


async def listar_consultas(
    db: AsyncSession, *, area: str | None = None, limit: int = 50
) -> list[dict]:
    await _ensure_schema(db)
    where, params = "", {"lim": limit}
    if area:
        where = "WHERE area = :a"
        params["a"] = area.strip().lower()
    rows = (
        await db.execute(
            text(
                "SELECT id, area, pergunta, resposta, escalonar, created_at "
                f"FROM ceo_consultas {where} ORDER BY created_at DESC LIMIT :lim"
            ),
            params,
        )
    ).fetchall()
    return [
        {**dict(r._mapping), "created_at": str(r.created_at), "pergunta": r.pergunta[:300]}
        for r in rows
    ]
