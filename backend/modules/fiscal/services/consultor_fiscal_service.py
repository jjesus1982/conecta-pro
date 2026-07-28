"""Consultor Fiscal IA — motor do chat ancorado nos dados fiscais reais do ERP.

Espelha o padrão CFO IA / Consultor Jurídico / Consultor GED (chat + anexo + histórico
+ contexto REAL), aplicado ao domínio FISCAL: notas fiscais (NFS-e nacional emitidas e
tomadas, NF-e de entrada, histórico municipal Manaus 2019-2025), apuração de tributos,
certidões (CNDs) e obrigações acessórias com seus prazos.

Doutrina: a IA assiste; o gestor e o contador decidem. NUNCA inventa dado — todo número
vem do banco. Documento fiscal JAMAIS é dito "autorizado" sem transmissão real: as notas
em nfse_emitidas_nacional/nfse_tomadas_nacional vêm da Distribuição ADN (Portal Nacional),
onde só entram documentos efetivamente autorizados pelo fisco.
Provider LLM: via consultor_hub (melhor modelo + fallback).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

AREAS_VALIDAS = {"notas", "apuracao", "certidoes", "obrigacoes"}

DISCLAIMER = (
    "Consultor Fiscal IA — as informações vêm dos dados reais do ERP (NFS-e da "
    "Distribuição Nacional, NF-e de entrada da SEFAZ, histórico municipal de Manaus, "
    "certidões e obrigações registradas). Confira guias e declarações oficiais com a "
    "contabilidade antes de recolher ou transmitir; a decisão final é do gestor."
)

MSG_INDISPONIVEL = (
    "Consultor Fiscal indisponível — configurar. O provedor de LLM não está acessível "
    "no momento. Os dados do painel abaixo continuam reais; a análise por IA volta "
    "assim que a integração for ajustada."
)

_GATILHOS_ESCALONAR = (
    "multa", "autua", "malha", "débito", "debito", "parcelament", "liminar",
    "sonega", "execução fiscal", "execucao fiscal", "retenç", "retenc",
    "fraude", "crime", "prazo vencid", "não recolh", "nao recolh", "atras",
    "notifica", "intima",
)

_ddl_ok = False


async def _ensure_schema(db: AsyncSession) -> None:
    """Cria a tabela do consultor se não existir (idempotente, DDL só se faltar)."""
    global _ddl_ok
    if _ddl_ok:
        return
    existe = (
        await db.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'fiscal_consultas'"
            )
        )
    ).scalar_one()
    if not existe:
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fiscal_consultas (
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
# PANORAMA — fotografia fiscal real (notas, tributos, certidões, obrigações)
# ─────────────────────────────────────────────────────────────────────────────
async def panorama(db: AsyncSession, ano: int | None = None) -> dict[str, Any]:
    await _ensure_schema(db)
    hoje = date.today()
    ano_ref = int(ano or hoje.year)
    mes_atual = hoje.strftime("%Y-%m")

    # NFS-e emitidas (Portal Nacional / ADN — só notas AUTORIZADAS entram na distribuição)
    emitidas = [
        {
            "mes": r.mes, "qtd": int(r.qtd),
            "receita": float(r.receita), "iss": float(r.iss),
        }
        for r in (
            await db.execute(
                text(
                    "SELECT competencia AS mes, count(*) qtd, "
                    "round(COALESCE(sum(valor_servicos),0)::numeric,2) receita, "
                    "round(COALESCE(sum(iss_valor),0)::numeric,2) iss "
                    "FROM nfse_emitidas_nacional WHERE competencia LIKE :pref "
                    "AND COALESCE(cancelada, FALSE) = FALSE "
                    "GROUP BY 1 ORDER BY 1"
                ),
                {"pref": f"{ano_ref}-%"},
            )
        ).fetchall()
    ]

    # NFS-e tomadas (serviços que a empresa CONTRATOU — custo mensal)
    tomadas = [
        {"mes": r.mes, "qtd": int(r.qtd), "valor": float(r.valor)}
        for r in (
            await db.execute(
                text(
                    "SELECT competencia AS mes, count(*) qtd, "
                    "round(COALESCE(sum(valor_servicos),0)::numeric,2) valor "
                    "FROM nfse_tomadas_nacional WHERE competencia LIKE :pref "
                    "GROUP BY 1 ORDER BY 1"
                ),
                {"pref": f"{ano_ref}-%"},
            )
        ).fetchall()
    ]

    # NF-e de entrada (mercadorias contra o CNPJ — Distribuição DFe SEFAZ)
    nfe_entradas = [
        {"mes": r.mes, "qtd": int(r.qtd), "valor": float(r.valor)}
        for r in (
            await db.execute(
                text(
                    "SELECT to_char(data_emissao,'YYYY-MM') AS mes, count(*) qtd, "
                    "round(COALESCE(sum(valor_total),0)::numeric,2) valor "
                    "FROM nfe_entradas WHERE extract(year FROM data_emissao) = :ano "
                    "GROUP BY 1 ORDER BY 1"
                ),
                {"ano": ano_ref},
            )
        ).fetchall()
    ]

    # Histórico municipal Manaus 2019-2025 (receita por ano — regime anterior ao Portal Nacional)
    historico = [
        {
            "ano": int(r.ano), "qtd": int(r.qtd),
            "receita": float(r.receita), "iss": float(r.iss),
        }
        for r in (
            await db.execute(
                text(
                    "SELECT extract(year FROM competencia)::int AS ano, count(*) qtd, "
                    "round(COALESCE(sum(valor_servicos),0)::numeric,2) receita, "
                    "round(COALESCE(sum(iss_valor),0)::numeric,2) iss "
                    "FROM nfse_manaus_historico WHERE competencia IS NOT NULL "
                    "GROUP BY 1 ORDER BY 1"
                )
            )
        ).fetchall()
    ]

    # Certidões (CNDs) — status por validade real
    cert_rows = (
        await db.execute(
            text(
                "SELECT name, document_type, issuing_body, issue_date, expiry_date, "
                "CASE WHEN expiry_date IS NULL THEN 'sem_validade' "
                "     WHEN expiry_date < CURRENT_DATE THEN 'vencida' "
                "     WHEN expiry_date <= CURRENT_DATE + 30 THEN 'vencendo' "
                "     ELSE 'valida' END AS situacao "
                "FROM ged_certidoes ORDER BY expiry_date NULLS LAST"
            )
        )
    ).fetchall()
    cert_itens = [
        {
            "nome": r.name, "tipo": r.document_type, "orgao": r.issuing_body,
            "emissao": str(r.issue_date) if r.issue_date else None,
            "validade": str(r.expiry_date) if r.expiry_date else None,
            "situacao": r.situacao,
        }
        for r in cert_rows
    ]
    certidoes = {
        "total": len(cert_itens),
        "validas": sum(1 for c in cert_itens if c["situacao"] == "valida"),
        "vencendo_30d": sum(1 for c in cert_itens if c["situacao"] == "vencendo"),
        "vencidas": sum(1 for c in cert_itens if c["situacao"] == "vencida"),
        "itens": cert_itens,
    }

    # Obrigações acessórias/tributárias (fiscal_obligations) — best-effort
    obrigacoes: dict[str, Any] = {"disponivel": False, "pendentes": 0, "vencidas": 0, "itens": []}
    try:
        ob_rows = (
            await db.execute(
                text(
                    "SELECT tipo, nome, status, data_vencimento, valor_devido, "
                    "(data_vencimento < CURRENT_DATE) AS vencida "
                    "FROM fiscal_obligations WHERE active AND status <> 'cumprida' "
                    "ORDER BY data_vencimento LIMIT 30"
                )
            )
        ).fetchall()
        itens = [
            {
                "tipo": r.tipo, "nome": r.nome, "status": r.status,
                "vencimento": str(r.data_vencimento),
                "valor_devido": float(r.valor_devido or 0),
                "vencida": bool(r.vencida),
            }
            for r in ob_rows
        ]
        obrigacoes = {
            "disponivel": True,
            "pendentes": len(itens),
            "vencidas": sum(1 for i in itens if i["vencida"]),
            "itens": itens,
        }
    except Exception as e:  # noqa: BLE001 — tabela pode não existir em outro ambiente
        logger.warning("Consultor Fiscal: fiscal_obligations indisponível: %s", e)

    def _mes(lista: list[dict], chave_mes: str) -> dict:
        return next((x for x in lista if x["mes"] == chave_mes), {})

    em_mes = _mes(emitidas, mes_atual)
    to_mes = _mes(tomadas, mes_atual)
    nfe_mes = _mes(nfe_entradas, mes_atual)
    resumo_mes = {
        "mes": mes_atual,
        "nfse_emitidas_qtd": int(em_mes.get("qtd", 0)),
        "nfse_emitidas_receita": float(em_mes.get("receita", 0.0)),
        "nfse_emitidas_iss": float(em_mes.get("iss", 0.0)),
        "tomadas_qtd": int(to_mes.get("qtd", 0)),
        "tomadas_valor": float(to_mes.get("valor", 0.0)),
        "nfe_entrada_qtd": int(nfe_mes.get("qtd", 0)),
        "nfe_entrada_valor": float(nfe_mes.get("valor", 0.0)),
    }

    # Multi-CNPJ: receita/ISS por empresa (o consultor é do GRUPO — precisa distinguir
    # Lucro Real (Eletrônica) × Simples (Patrimonial), não só o total somado do grupo).
    receita_por_empresa = [
        {"empresa": r.slug, "qtd": int(r.qtd), "receita": float(r.receita), "iss": float(r.iss)}
        for r in (
            await db.execute(
                text(
                    "SELECT e.slug, count(*) qtd, "
                    "round(COALESCE(sum(n.valor_servicos),0)::numeric,2) receita, "
                    "round(COALESCE(sum(n.iss_valor),0)::numeric,2) iss "
                    "FROM nfse_emitidas_nacional n JOIN empresas e ON e.id = n.empresa_id "
                    "WHERE n.competencia LIKE :pref AND COALESCE(n.cancelada, FALSE) = FALSE "
                    "GROUP BY e.slug ORDER BY e.slug"
                ),
                {"pref": f"{ano_ref}-%"},
            )
        ).fetchall()
    ]

    return {
        "ano": ano_ref,
        "mes_atual": mes_atual,
        "resumo_mes_atual": resumo_mes,
        "emitidas_por_mes": emitidas,
        "tomadas_por_mes": tomadas,
        "nfe_entradas_por_mes": nfe_entradas,
        "receita_ano": round(sum(x["receita"] for x in emitidas), 2),
        "iss_ano": round(sum(x["iss"] for x in emitidas), 2),
        "receita_por_empresa": receita_por_empresa,
        "historico_manaus": historico,
        "certidoes": certidoes,
        "obrigacoes": obrigacoes,
        "fonte": (
            "nfse_emitidas_nacional + nfse_tomadas_nacional (Distribuição ADN — só notas "
            "AUTORIZADAS entram) + nfe_entradas (Distribuição DFe SEFAZ) + "
            "nfse_manaus_historico (municipal 2019-2025) + ged_certidoes + fiscal_obligations"
        ),
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CHAT — pergunta ancorada no contexto fiscal real
# ─────────────────────────────────────────────────────────────────────────────
def _bloco_grupo() -> str:
    from modules.empresas.services.contexto_grupo import bloco_contexto_grupo

    return bloco_contexto_grupo()


_REGRAS_COMUNS = _bloco_grupo() + """
Você é o CONSULTOR FISCAL do GRUPO CONECTA MAIS (Manaus-AM) — as DUAS empresas acima. \
Sempre indique a qual CNPJ cada análise se refere.
CONTEXTO TRIBUTÁRIO (o regime, a IM e o CNPJ de CADA empresa vêm do bloco do GRUPO acima \
— use-os, NÃO presuma; assim, quando a estrutura mudar (ex.: retorno ao Simples em 2027), \
esta resposta continua correta sem reescrever nada aqui):
- ISS Manaus: alíquota de 5% sobre serviços.
- NFS-e: emitidas pelo PORTAL NACIONAL desde 2026 (padrão ADN); de 2019 a 2025 a emissão \
era municipal (Manaus) — esse histórico está importado em tabela própria.
REGRAS INEGOCIÁVEIS:
- NUNCA invente número, nota, guia, certidão ou prazo. Use APENAS o contexto real fornecido.
- Se a informação não está no contexto, diga claramente "não está registrado no sistema".
- JAMAIS afirme que um documento fiscal foi "autorizado" ou "transmitido" sem que isso \
conste do contexto real — as notas listadas vêm da Distribuição Nacional (só autorizadas \
entram); o que não está lá não existe para o sistema.
- Cálculo de tributo é ESTIMATIVA de apoio: o recolhimento oficial é sempre validado com \
a contabilidade (Portte) antes de pagar ou transmitir.
- Obrigações VENCIDAS e certidões VENCIDAS são risco imediato — sempre aponte com destaque.
- Responda em Markdown curto: ## Resposta direta, ## Situação real (números do contexto), \
## Próximos passos (checklist acionável), ## Atenção (riscos/prazos)."""

_LENTES = {
    "notas": "FOCO: notas fiscais — NFS-e emitidas (receita/ISS por mês), serviços tomados, NF-e de entrada e o histórico municipal 2019-2025. Compare meses, aponte quedas/anomalias de emissão e o que ainda não foi emitido no mês corrente.",
    "apuracao": "FOCO: apuração de tributos CONFORME O REGIME DE CADA EMPRESA (ver bloco do GRUPO — Lucro Real e Simples convivem) — ISS Manaus (5%), e no Lucro Real também PIS/COFINS, IRPJ/CSLL, INSS patronal e retenções; no Simples, o DAS (Anexo III) engloba a maior parte. Use receita e ISS reais do contexto; deixe claro o que é estimativa e o que depende da contabilidade (Portte).",
    "certidoes": "FOCO: certidões (CNDs) — o que está válido, vencendo em 30 dias e VENCIDO. Certidão vencida trava licitação e contrato público; priorize a renovação e diga qual órgão emite cada uma.",
    "obrigacoes": "FOCO: obrigações acessórias e tributárias — eSocial, DCTFWeb, EFD-Reinf, FGTS, ISS, DARFs. Cruze status pendente/vencido com as datas reais; monte a fila de regularização por urgência e valor.",
}


def _detectar_escalonamento(pergunta: str, resposta: str) -> bool:
    alvo = f"{pergunta} {resposta}".lower()
    return any(g in alvo for g in _GATILHOS_ESCALONAR)


async def consultar(
    db: AsyncSession, *, area: str, pergunta: str,
    ano: int | None = None, user_id: str | None = None,
    anexo_texto: str | None = None, anexo_nome: str | None = None,
) -> dict[str, Any]:
    await _ensure_schema(db)
    area_n = (area or "").strip().lower()
    if area_n not in AREAS_VALIDAS:
        raise ValueError(f"Área inválida '{area}'. Válidas: {', '.join(sorted(AREAS_VALIDAS))}")

    pano = await panorama(db, ano)

    contexto = [
        f"=== PANORAMA FISCAL REAL — ano {pano['ano']} (gerado em {pano['gerado_em']}) ===",
        f"Receita NFS-e no ano: R$ {pano['receita_ano']:.2f} | ISS destacado no ano: R$ {pano['iss_ano']:.2f}",
        "",
        "NFS-e EMITIDAS por mês (Portal Nacional — só notas autorizadas; mês | qtd | receita | ISS):",
    ]
    for m in pano["emitidas_por_mes"]:
        contexto.append(f"- {m['mes']}: {m['qtd']} notas | R$ {m['receita']:.2f} | ISS R$ {m['iss']:.2f}")
    rm = pano["resumo_mes_atual"]
    if rm["nfse_emitidas_qtd"] == 0:
        contexto.append(
            f"- {rm['mes']} (mês corrente): NENHUMA NFS-e emitida constou na distribuição até agora "
            "— aguardando emissão/distribuição (não é necessariamente atraso, confira o faturamento do mês)."
        )

    contexto.append("")
    contexto.append("SERVIÇOS TOMADOS por mês (NFS-e contra o CNPJ; mês | qtd | valor):")
    for m in pano["tomadas_por_mes"]:
        contexto.append(f"- {m['mes']}: {m['qtd']} notas | R$ {m['valor']:.2f}")

    contexto.append("")
    contexto.append("NF-e DE ENTRADA por mês (mercadorias — Distribuição DFe SEFAZ; mês | qtd | valor):")
    for m in pano["nfe_entradas_por_mes"]:
        contexto.append(f"- {m['mes']}: {m['qtd']} notas | R$ {m['valor']:.2f}")

    contexto.append("")
    contexto.append("HISTÓRICO MUNICIPAL MANAUS (receita por ano, 2019-2025 — regime anterior):")
    for h in pano["historico_manaus"]:
        contexto.append(f"- {h['ano']}: {h['qtd']} notas | R$ {h['receita']:.2f} | ISS R$ {h['iss']:.2f}")

    c = pano["certidoes"]
    contexto.append("")
    contexto.append(
        f"CERTIDÕES: {c['total']} registradas — {c['validas']} válidas, "
        f"{c['vencendo_30d']} vencendo em 30 dias, {c['vencidas']} VENCIDAS:"
    )
    for i in c["itens"]:
        contexto.append(f"- [{i['situacao'].upper()}] {i['nome']} | validade: {i['validade'] or 'sem validade registrada'}")

    o = pano["obrigacoes"]
    contexto.append("")
    if o["disponivel"]:
        contexto.append(
            f"OBRIGAÇÕES NÃO CUMPRIDAS: {o['pendentes']} pendentes ({o['vencidas']} já VENCIDAS):"
        )
        for i in o["itens"]:
            contexto.append(
                f"- [{'VENCIDA' if i['vencida'] else i['status'].upper()}] {i['nome']} ({i['tipo']}) "
                f"| vencimento {i['vencimento']} | valor devido R$ {i['valor_devido']:.2f}"
            )
        if not o["itens"]:
            contexto.append("- nenhuma obrigação pendente registrada no sistema.")
    else:
        contexto.append("OBRIGAÇÕES: cadastro indisponível no momento (não invente prazos).")

    system_prompt = f"{_REGRAS_COMUNS}\n\n{_LENTES[area_n]}\n\n{chr(10).join(contexto)}"

    user_content = (pergunta or "").strip() or "Faça um diagnóstico da situação fiscal atual da empresa."
    if (anexo_texto or "").strip():
        user_content += (
            f"\n\n=== DOCUMENTO ANEXADO{f' ({anexo_nome})' if anexo_nome else ''} ===\n"
            f"{anexo_texto.strip()[:14000]}\n=== FIM DO DOCUMENTO ===\n\n"
            "Analise o documento acima à luz da pergunta e do panorama fiscal real."
        )

    resposta_texto: str | None = None
    llm_meta: dict[str, Any] = {}
    try:
        from modules.ai.conversation.services import consultor_hub as _hub
        _extra = await _hub.contexto_compartilhado(db, 'fiscal', pergunta)
        _conversa = await _hub.conversa_recente(db, 'fiscal')
        if _extra:
            system_prompt = f"{system_prompt}\n\n{_extra}"
        if _conversa:
            system_prompt = f"{system_prompt}\n\n{_conversa}"
        from modules.ai.conversation.services.consultor_conhecimento_service import contexto_para_prompt
        system_prompt = system_prompt + contexto_para_prompt("fiscal", pergunta)
        resposta_texto, llm_meta = await _hub.gerar(
            messages=[{"role": "user", "content": user_content}],
            system_prompt=system_prompt, max_tokens=2500, temperature=0.2,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Consultor Fiscal: LLM indisponível: %s", e)
        from modules.ai.conversation.services.llm_credit_alert import alertar_llm_indisponivel
        await alertar_llm_indisponivel("Consultor Fiscal", str(e))

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
                "INSERT INTO fiscal_consultas "
                "(area, competencia, pergunta, resposta, escalonar, disclaimer, contexto_usado, created_by) "
                "VALUES (:a, :comp, :p, :r, :e, :d, CAST(:ctx AS jsonb), :by) RETURNING id"
            ),
            {
                "a": area_n, "comp": pano["mes_atual"],
                "p": user_content[:8000], "r": resposta_texto, "e": escalonar,
                "d": DISCLAIMER,
                "ctx": _json.dumps(
                    {"resumo_mes_atual": pano["resumo_mes_atual"],
                     "certidoes": {k: v for k, v in pano["certidoes"].items() if k != "itens"},
                     "obrigacoes": {k: v for k, v in pano["obrigacoes"].items() if k != "itens"},
                     "llm": llm_meta},
                    default=str,
                ),
                "by": user_id,
            },
        )
    ).first()
    await db.commit()

    # aprendizado permanente (best-effort, nunca quebra o chat)
    from modules.ai.conversation.services import consultor_hub as _hub2
    await _hub2.aprender(db, 'fiscal', pergunta or '', resposta_texto, panorama=pano)

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
                f"FROM fiscal_consultas {where} ORDER BY created_at DESC LIMIT :lim"
            ),
            params,
        )
    ).fetchall()
    return [
        {**dict(r._mapping), "created_at": str(r.created_at), "pergunta": r.pergunta[:300]}
        for r in rows
    ]
