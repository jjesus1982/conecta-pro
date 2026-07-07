"""Consultor GED/GEDEON — motor do chat ancorado nos dados reais dos kits.

Espelha o padrão CFO IA / Consultor Jurídico (chat + anexo + histórico + contexto REAL),
aplicado ao domínio GED: montagem de kits por condomínio, checklist, cronograma e as
INTERCORRÊNCIAS do mês (contratações, demissões, faltas, atrasos, suspensões...) que
precisam estar registradas ANTES do fechamento do kit para a folha sair perfeita.

Doutrina: a IA assiste; o gestor decide. NUNCA inventa dado — todo número vem do banco.
Provider LLM: OpenAI primário (decisão Jordan 2026-07-07), Claude fallback.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

AREAS_VALIDAS = {"montagem", "checklist", "intercorrencias", "folha"}

DISCLAIMER = (
    "Consultor GED IA — as informações vêm dos dados reais do ERP (kits, alocações, "
    "intercorrências registradas). Confira documentos oficiais antes do fechamento; "
    "a decisão final é do gestor."
)

MSG_INDISPONIVEL = (
    "Consultor GED indisponível — configurar. O provedor de LLM não está acessível no "
    "momento. Os dados do painel abaixo continuam reais; a análise por IA volta assim "
    "que a integração for ajustada."
)

TIPOS_INTERCORRENCIA = {
    "contratacao", "demissao", "falta", "atraso", "suspensao", "afastamento",
    "ferias", "advertencia", "acidente", "hora_extra", "troca_posto", "outro",
}

_GATILHOS_ESCALONAR = (
    "demiss", "rescis", "justa causa", "afastamento", "inss", "acidente",
    "esocial", "prazo vencid", "multa", "fgts atras", "não recolh", "nao recolh",
)

_ddl_ok = False


async def _ensure_schema(db: AsyncSession) -> None:
    """Cria as tabelas do consultor se não existirem (idempotente, DDL só se faltar)."""
    global _ddl_ok
    if _ddl_ok:
        return
    falta = (
        await db.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name IN ('gedeon_consultas','gedeon_intercorrencias')"
            )
        )
    ).scalar_one()
    if falta < 2:
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS gedeon_consultas (
                    id             BIGSERIAL PRIMARY KEY,
                    area           VARCHAR(20)  NOT NULL,
                    condominio     VARCHAR(200),
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
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS gedeon_intercorrencias (
                    id            BIGSERIAL PRIMARY KEY,
                    condominio    VARCHAR(200) NOT NULL,
                    competencia   VARCHAR(7)   NOT NULL,
                    tipo          VARCHAR(30)  NOT NULL,
                    funcionario   VARCHAR(200),
                    data_evento   DATE,
                    descricao     TEXT         NOT NULL,
                    impacto_folha BOOLEAN      NOT NULL DEFAULT TRUE,
                    status        VARCHAR(15)  NOT NULL DEFAULT 'aberta',
                    tratada_em    TIMESTAMPTZ,
                    created_by    VARCHAR(64),
                    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
                );
                CREATE INDEX IF NOT EXISTS ix_gedeon_interc_cond_comp
                    ON gedeon_intercorrencias (condominio, competencia);
                """
            )
        )
        await db.commit()
    _ddl_ok = True


def _competencia_padrao() -> str:
    """Competência do kit em fechamento = mês anterior (YYYY-MM)."""
    hoje = date.today()
    ano, mes = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)
    return f"{ano:04d}-{mes:02d}"


def _competencias_equivalentes(comp: str) -> list[str]:
    """Aceita YYYY-MM e MM.YYYY (o histórico legado tem os dois formatos)."""
    ano, mes = comp.split("-")
    return [comp, f"{mes}.{ano}"]


# ─────────────────────────────────────────────────────────────────────────────
# PANORAMA — fotografia real dos kits/intercorrências por condomínio
# ─────────────────────────────────────────────────────────────────────────────
async def panorama(db: AsyncSession, competencia: str | None = None) -> dict[str, Any]:
    await _ensure_schema(db)
    comp = (competencia or _competencia_padrao()).strip()[:7]
    comps = _competencias_equivalentes(comp)

    # Condomínios do padrão GEDEON (config ativa → nome do cliente)
    condominios = [
        dict(r._mapping)
        for r in (
            await db.execute(
                text(
                    "SELECT DISTINCT c.id AS client_id, c.name AS condominio "
                    "FROM gedeon_kit_config g JOIN clients c ON c.id = g.client_id "
                    "WHERE COALESCE(g.ativo, true) ORDER BY 2"
                )
            )
        ).fetchall()
    ]

    # Última montagem da competência por cliente
    montagens = {
        str(r.client_id): dict(r._mapping)
        for r in (
            await db.execute(
                text(
                    "SELECT DISTINCT ON (client_id) client_id, competencia, tipo_kit, "
                    "score_final, docs_total, docs_auto, created_at "
                    "FROM gedeon_kit_history WHERE competencia = ANY(:comps) "
                    "ORDER BY client_id, created_at DESC"
                ),
                {"comps": comps},
            )
        ).fetchall()
    }

    # Intercorrências da competência por condomínio
    interc = {
        r.condominio: {"abertas": r.abertas, "total": r.total}
        for r in (
            await db.execute(
                text(
                    "SELECT condominio, count(*) total, "
                    "count(*) FILTER (WHERE status='aberta') abertas "
                    "FROM gedeon_intercorrencias WHERE competencia = :comp GROUP BY 1"
                ),
                {"comp": comp},
            )
        ).fetchall()
    }

    # Funcionários alocados por posto cujo nome casa com o condomínio (melhor esforço,
    # fonte marcada — o elo formal posto↔cliente ainda não existe no schema)
    aloc = {
        r.condominio: r.funcionarios
        for r in (
            await db.execute(
                text(
                    "SELECT c.name AS condominio, count(DISTINCT a.employee_id) AS funcionarios "
                    "FROM clients c JOIN gedeon_kit_config g ON g.client_id = c.id "
                    "LEFT JOIN posts p ON p.name ILIKE '%' || split_part(c.name, ' ', 1) || '%' "
                    "   OR c.name ILIKE '%' || p.name || '%' "
                    "LEFT JOIN allocations a ON a.post_id = p.id AND a.status::text ILIKE 'ACTIVE%' "
                    "GROUP BY 1"
                )
            )
        ).fetchall()
    }

    itens = []
    for c in condominios:
        nome = c["condominio"]
        m = montagens.get(str(c["client_id"])) or {}
        i = interc.get(nome) or {"abertas": 0, "total": 0}
        itens.append(
            {
                "condominio": nome,
                "kit": {
                    "montado": bool(m),
                    "score": m.get("score_final"),
                    "docs_total": m.get("docs_total"),
                    "montado_em": str(m.get("created_at") or "") or None,
                },
                "intercorrencias_abertas": i["abertas"],
                "intercorrencias_total": i["total"],
                "funcionarios_alocados": aloc.get(nome, 0),
                "pronto_para_fechar": bool(m) and i["abertas"] == 0,
            }
        )

    # Folha da competência (contexto p/ fechamento perfeito)
    ano, mes = comp.split("-")
    folha = (
        await db.execute(
            text(
                "SELECT count(*) holerites, round(COALESCE(sum(net_salary),0)::numeric,2) liquido "
                "FROM hr_payslips WHERE reference_year = :a AND reference_month = :m"
            ),
            {"a": int(ano), "m": int(mes)},
        )
    ).first()

    return {
        "competencia": comp,
        "condominios": itens,
        "total_condominios": len(itens),
        "kits_montados": sum(1 for x in itens if x["kit"]["montado"]),
        "intercorrencias_abertas": sum(x["intercorrencias_abertas"] for x in itens),
        "folha_competencia": {"holerites": folha.holerites, "liquido": float(folha.liquido)},
        "fonte": "gedeon_kit_history + gedeon_intercorrencias + allocations (elo por nome, melhor esforço) + hr_payslips",
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# INTERCORRÊNCIAS — registro do dia a dia antes do fechamento
# ─────────────────────────────────────────────────────────────────────────────
async def registrar_intercorrencia(
    db: AsyncSession, *, condominio: str, tipo: str, descricao: str,
    competencia: str | None = None, funcionario: str | None = None,
    data_evento: date | None = None, impacto_folha: bool = True,
    created_by: str | None = None,
) -> dict[str, Any]:
    await _ensure_schema(db)
    tipo_n = (tipo or "").strip().lower()
    if tipo_n not in TIPOS_INTERCORRENCIA:
        raise ValueError(f"Tipo inválido '{tipo}'. Válidos: {', '.join(sorted(TIPOS_INTERCORRENCIA))}")
    if not (descricao or "").strip():
        raise ValueError("Descrição é obrigatória")
    comp = (competencia or _competencia_padrao()).strip()[:7]
    row = (
        await db.execute(
            text(
                "INSERT INTO gedeon_intercorrencias "
                "(condominio, competencia, tipo, funcionario, data_evento, descricao, impacto_folha, created_by) "
                "VALUES (:c, :comp, :t, :f, :d, :desc, :imp, :by) "
                "RETURNING id, condominio, competencia, tipo, funcionario, data_evento, "
                "descricao, impacto_folha, status, created_at"
            ),
            {
                "c": condominio.strip(), "comp": comp, "t": tipo_n,
                "f": (funcionario or "").strip() or None, "d": data_evento,
                "desc": descricao.strip(), "imp": impacto_folha, "by": created_by,
            },
        )
    ).first()
    await db.commit()
    return {k: (str(v) if isinstance(v, (datetime, date)) else v) for k, v in row._mapping.items()}


async def listar_intercorrencias(
    db: AsyncSession, *, condominio: str | None = None,
    competencia: str | None = None, status: str | None = None, limit: int = 200,
) -> list[dict[str, Any]]:
    await _ensure_schema(db)
    where, params = ["1=1"], {"lim": limit}
    if condominio:
        where.append("condominio ILIKE :c"); params["c"] = f"%{condominio.strip()}%"
    if competencia:
        where.append("competencia = :comp"); params["comp"] = competencia.strip()[:7]
    if status:
        where.append("status = :st"); params["st"] = status.strip().lower()
    rows = (
        await db.execute(
            text(
                "SELECT id, condominio, competencia, tipo, funcionario, data_evento, descricao, "
                "impacto_folha, status, tratada_em, created_by, created_at "
                f"FROM gedeon_intercorrencias WHERE {' AND '.join(where)} "
                "ORDER BY created_at DESC LIMIT :lim"
            ),
            params,
        )
    ).fetchall()
    return [
        {k: (str(v) if isinstance(v, (datetime, date)) else v) for k, v in r._mapping.items()}
        for r in rows
    ]


async def tratar_intercorrencia(db: AsyncSession, intercorrencia_id: int) -> dict[str, Any]:
    await _ensure_schema(db)
    row = (
        await db.execute(
            text(
                "UPDATE gedeon_intercorrencias SET status='tratada', tratada_em=now() "
                "WHERE id=:i RETURNING id, status, tratada_em"
            ),
            {"i": intercorrencia_id},
        )
    ).first()
    if not row:
        raise ValueError(f"Intercorrência {intercorrencia_id} não encontrada")
    await db.commit()
    return {"id": row.id, "status": row.status, "tratada_em": str(row.tratada_em)}


async def excluir_intercorrencia(db: AsyncSession, intercorrencia_id: int) -> None:
    await _ensure_schema(db)
    r = await db.execute(text("DELETE FROM gedeon_intercorrencias WHERE id=:i"), {"i": intercorrencia_id})
    if r.rowcount == 0:
        raise ValueError(f"Intercorrência {intercorrencia_id} não encontrada")
    await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# CHAT — pergunta ancorada no contexto real
# ─────────────────────────────────────────────────────────────────────────────
_REGRAS_COMUNS = """Você é o CONSULTOR GED da Conecta Mais (segurança patrimonial, Manaus-AM), \
especialista em fechamento documental mensal (kits por condomínio) e departamento pessoal.
O kit mensal por condomínio reúne: folha/contracheques, guias (FGTS/INSS/ISS), comprovantes \
bancários, VT/VR, CNDs, NFS-e e documentos de movimentação de pessoal.
REGRAS INEGOCIÁVEIS:
- NUNCA invente número, documento, funcionário ou prazo. Use APENAS o contexto real fornecido.
- Se a informação não está no contexto, diga claramente "não está registrado no sistema".
- Intercorrências ABERTAS bloqueiam um fechamento perfeito — sempre aponte as pendências.
- Responda em Markdown curto: ## Resposta direta, ## Situação real (números do contexto), \
## Próximos passos (checklist acionável), ## Atenção (riscos/prazos).
- Fechamento de folha: contratações/demissões/faltas/atrasos/suspensões precisam estar \
registradas ANTES de fechar o kit — é o propósito deste consultor."""

_LENTES = {
    "montagem": "FOCO: montagem do kit por condomínio — o que já foi montado na competência, score, documentos, o que falta disparar, e se há intercorrências abertas que devem entrar antes.",
    "checklist": "FOCO: checklist de fechamento — para cada condomínio citado, liste o que está pronto e o que falta (kit montado? intercorrências abertas? funcionários alocados batem?).",
    "intercorrencias": "FOCO: intercorrências do mês — o que está registrado, o que está aberto vs tratado, impacto na folha, e o que tipicamente falta registrar (contratação, demissão, falta, atraso, suspensão, afastamento, férias).",
    "folha": "FOCO: fechamento de folha perfeito — cruze intercorrências abertas com a folha da competência; aponte riscos (demissão sem rescisão no kit, afastamento sem ASO, falta sem desconto).",
}


def _detectar_escalonamento(pergunta: str, resposta: str) -> bool:
    alvo = f"{pergunta} {resposta}".lower()
    return any(g in alvo for g in _GATILHOS_ESCALONAR)


async def consultar(
    db: AsyncSession, *, area: str, pergunta: str,
    condominio: str | None = None, competencia: str | None = None,
    user_id: str | None = None, anexo_texto: str | None = None, anexo_nome: str | None = None,
) -> dict[str, Any]:
    await _ensure_schema(db)
    area_n = (area or "").strip().lower()
    if area_n not in AREAS_VALIDAS:
        raise ValueError(f"Área inválida '{area}'. Válidas: {', '.join(sorted(AREAS_VALIDAS))}")

    pano = await panorama(db, competencia)
    intercs = await listar_intercorrencias(
        db, condominio=condominio, competencia=pano["competencia"], limit=60
    )

    contexto = [
        f"=== PANORAMA REAL DOS KITS — competência {pano['competencia']} ===",
        f"Condomínios no padrão GEDEON: {pano['total_condominios']} | kits montados: {pano['kits_montados']} | intercorrências abertas: {pano['intercorrencias_abertas']}",
        f"Folha da competência: {pano['folha_competencia']['holerites']} holerites, líquido R$ {pano['folha_competencia']['liquido']:.2f}",
        "",
        "POR CONDOMÍNIO (kit montado? | score | docs | intercorrências abertas | funcionários alocados | pronto p/ fechar):",
    ]
    for c in pano["condominios"]:
        k = c["kit"]
        score_txt = f" score={k['score']} docs={k['docs_total']}" if k["montado"] else ""
        contexto.append(
            f"- {c['condominio']}: kit={'SIM' if k['montado'] else 'NÃO'}{score_txt}"
            f" | interc.abertas={c['intercorrencias_abertas']}"
            f" | funcionários≈{c['funcionarios_alocados']}"
            f" | pronto={'SIM' if c['pronto_para_fechar'] else 'NÃO'}"
        )
    if intercs:
        contexto.append("")
        contexto.append(f"INTERCORRÊNCIAS REGISTRADAS ({'filtro: ' + condominio if condominio else 'todas'}):")
        for i in intercs[:40]:
            contexto.append(
                f"- [{i['status'].upper()}] {i['condominio']} | {i['tipo']}"
                f"{' | ' + i['funcionario'] if i.get('funcionario') else ''}"
                f"{' | ' + str(i['data_evento']) if i.get('data_evento') else ''} — {i['descricao'][:140]}"
            )
    else:
        contexto.append("")
        contexto.append("INTERCORRÊNCIAS REGISTRADAS: nenhuma na competência (atenção: mês sem NENHUM registro é improvável — provavelmente falta registrar).")

    system_prompt = f"{_REGRAS_COMUNS}\n\n{_LENTES[area_n]}\n\n{chr(10).join(contexto)}"

    user_content = (pergunta or "").strip() or "Faça um diagnóstico do fechamento dos kits desta competência."
    if (anexo_texto or "").strip():
        user_content += (
            f"\n\n=== DOCUMENTO ANEXADO{f' ({anexo_nome})' if anexo_nome else ''} ===\n"
            f"{anexo_texto.strip()[:14000]}\n=== FIM DO DOCUMENTO ===\n\n"
            "Analise o documento acima à luz da pergunta e do panorama real dos kits."
        )

    resposta_texto: str | None = None
    llm_meta: dict[str, Any] = {}
    try:
        from modules.ai.conversation.services.llm_provider import ClaudeProvider, OpenAIProvider

        provider = OpenAIProvider(model=os.getenv("CONSULTOR_LLM_MODEL", "gpt-4o"))
        if not provider.api_key:
            provider = ClaudeProvider()
        if not provider.api_key:
            raise RuntimeError("OPENAI_API_KEY/ANTHROPIC_API_KEY ausentes")
        llm_resp = await provider.generate(
            messages=[{"role": "user", "content": user_content}],
            system_prompt=system_prompt, max_tokens=2500, temperature=0.2,
        )
        resposta_texto = (llm_resp.content or "").strip()
        llm_meta = {"model": getattr(llm_resp, "model", None)}
    except Exception as e:  # noqa: BLE001
        logger.warning("Consultor GED: LLM indisponível: %s", e)
        from modules.ai.conversation.services.llm_credit_alert import alertar_llm_indisponivel
        await alertar_llm_indisponivel("Consultor GED (GEDEON)", str(e))

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
                "INSERT INTO gedeon_consultas "
                "(area, condominio, competencia, pergunta, resposta, escalonar, disclaimer, contexto_usado, created_by) "
                "VALUES (:a, :c, :comp, :p, :r, :e, :d, CAST(:ctx AS jsonb), :by) RETURNING id"
            ),
            {
                "a": area_n, "c": condominio, "comp": pano["competencia"],
                "p": user_content[:8000], "r": resposta_texto, "e": escalonar,
                "d": DISCLAIMER,
                "ctx": _json.dumps({"panorama": pano, "llm": llm_meta}, default=str),
                "by": user_id,
            },
        )
    ).first()
    await db.commit()

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
                "SELECT id, area, condominio, competencia, pergunta, resposta, escalonar, created_at "
                f"FROM gedeon_consultas {where} ORDER BY created_at DESC LIMIT :lim"
            ),
            params,
        )
    ).fetchall()
    return [
        {**dict(r._mapping), "created_at": str(r.created_at), "pergunta": r.pergunta[:300]}
        for r in rows
    ]
