"""Consultor Operacional (COO IA) — chat ancorado nos dados reais da operação.

Espelha o padrão CFO IA / Consultor Jurídico / Consultor GED (chat + anexo +
histórico + contexto REAL), aplicado ao domínio OPERACIONAL: cobertura de postos,
alocações vigentes, escalas 12x36, diaristas e ocorrências de campo.

Doutrina: a IA assiste; o gestor decide. NUNCA inventa dado — todo número vem do
banco via SQL direto (text()). Vazio real = "aguardando dado", nunca mascarar.
Geração via HUB dos consultores (melhor modelo + memória compartilhada).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

AREAS_VALIDAS = {"postos", "alocacoes", "diaristas", "ocorrencias"}

DISCLAIMER = (
    "Consultor Operacional IA — as informações vêm dos dados reais do ERP "
    "(postos, alocações, diaristas, ocorrências). Confirme em campo antes de "
    "mudanças de escala; a decisão final é do gestor operacional."
)

MSG_INDISPONIVEL = (
    "Consultor Operacional indisponível — configurar. O provedor de LLM não está "
    "acessível no momento. Os dados do painel abaixo continuam reais; a análise "
    "por IA volta assim que a integração for ajustada."
)

_GATILHOS_ESCALONAR = (
    "posto descoberto", "sem cobertura", "abandono", "acidente", "arma",
    "invas", "furto", "roubo", "agress", "emergênc", "emergenc",
    "demiss", "rescis", "justa causa", "afastamento", "inss",
)

_ddl_ok = False


async def _ensure_schema(db: AsyncSession) -> None:
    """Cria a tabela de consultas se não existir (idempotente, DDL só se faltar)."""
    global _ddl_ok
    if _ddl_ok:
        return
    existe = (
        await db.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'operacional_consultas'"
            )
        )
    ).scalar_one()
    if not existe:
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS operacional_consultas (
                    id             BIGSERIAL PRIMARY KEY,
                    area           VARCHAR(20)  NOT NULL,
                    posto          VARCHAR(200),
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
# PANORAMA — fotografia real da operação (SQL direto, colunas validadas no banco)
# ─────────────────────────────────────────────────────────────────────────────
async def panorama(db: AsyncSession) -> dict[str, Any]:
    await _ensure_schema(db)

    # Postos (posts.status é varchar 'active'/'inactive'; is_active boolean)
    postos = (
        await db.execute(
            text(
                "SELECT count(*) AS total, "
                "count(*) FILTER (WHERE COALESCE(is_active, true) "
                "  AND status::text ILIKE 'ACTIVE%') AS ativos "
                "FROM posts"
            )
        )
    ).first()

    # Alocações ativas (allocations.status varchar: active/on_hold/terminated)
    alocacoes_ativas = (
        await db.execute(
            text("SELECT count(*) FROM allocations WHERE status::text ILIKE 'ACTIVE%'")
        )
    ).scalar_one()

    # Funcionários (employees.status: ativo/afastado_inss/demitido/inativo/suspenso)
    func = (
        await db.execute(
            text(
                "SELECT count(*) FILTER (WHERE status = 'ativo') AS ativos, "
                "count(*) FILTER (WHERE status = 'afastado_inss') AS afastados "
                "FROM employees"
            )
        )
    ).first()

    # Diaristas (diarists.ativo boolean + status varchar 'ativo'/'inativo')
    diaristas = (
        await db.execute(
            text(
                "SELECT count(*) AS total, "
                "count(*) FILTER (WHERE COALESCE(ativo, true) AND status = 'ativo') AS ativos "
                "FROM diarists"
            )
        )
    ).first()

    # Vínculos de diaristas ATIVOS (diarist_assignments.status é ENUM nativo → ::text)
    vinculos_diaristas = (
        await db.execute(
            text("SELECT count(*) FROM diarist_assignments WHERE status::text = 'ATIVO'")
        )
    ).scalar_one()

    # Ocorrências de campo (tabela occurrences existe; hoje pode estar vazia — dado honesto)
    ocorrencias = (
        await db.execute(
            text(
                "SELECT count(*) AS total, "
                "count(*) FILTER (WHERE resolved_at IS NULL AND COALESCE(is_active, true)) AS abertas "
                "FROM occurrences"
            )
        )
    ).first()

    # Escalas vigentes hoje. scales NÃO tem start_date/end_date populados (ficam NULL) —
    # a vigência é por MÊS/ANO. Usar CURRENT_DATE BETWEEN start/end dava sempre 0.
    escalas = (
        await db.execute(
            text(
                "SELECT count(*) AS total, "
                "count(*) FILTER (WHERE COALESCE(is_active, true) "
                "  AND month = EXTRACT(MONTH FROM CURRENT_DATE)::int "
                "  AND year = EXTRACT(YEAR FROM CURRENT_DATE)::int) AS vigentes, "
                "count(*) FILTER (WHERE status::text ILIKE 'DRAFT%') AS rascunhos "
                "FROM scales"
            )
        )
    ).first()

    # Postos × alocados (1 query) — cobertura real por posto
    postos_alocados = [
        {
            "posto": r.posto,
            "status": r.status,
            "efetivo_requerido": r.efetivo_requerido,
            "alocados": r.alocados,
            "coberto": bool(r.alocados and r.alocados > 0),
        }
        for r in (
            await db.execute(
                text(
                    "SELECT p.name AS posto, p.status::text AS status, "
                    "p.required_headcount AS efetivo_requerido, "
                    "count(a.id) FILTER (WHERE a.status::text ILIKE 'ACTIVE%') AS alocados "
                    "FROM posts p "
                    "LEFT JOIN allocations a ON a.post_id = p.id "
                    "WHERE COALESCE(p.is_active, true) AND p.status::text ILIKE 'ACTIVE%' "
                    "GROUP BY p.id, p.name, p.status, p.required_headcount "
                    "ORDER BY alocados DESC, p.name"
                )
            )
        ).fetchall()
    ]

    postos_cobertos = sum(1 for p in postos_alocados if p["coberto"])
    postos_descobertos = [p["posto"] for p in postos_alocados if not p["coberto"]]
    cobertura_pct = (
        round(100.0 * postos_cobertos / len(postos_alocados), 1) if postos_alocados else None
    )

    return {
        "postos": {"total": postos.total, "ativos": postos.ativos},
        "alocacoes_ativas": alocacoes_ativas,
        "funcionarios": {"ativos": func.ativos, "afastados_inss": func.afastados},
        "diaristas": {"total": diaristas.total, "ativos": diaristas.ativos},
        "vinculos_diaristas_ativos": vinculos_diaristas,
        "ocorrencias": {"total": ocorrencias.total, "abertas": ocorrencias.abertas},
        "escalas": {
            "total": escalas.total,
            "vigentes_hoje": escalas.vigentes,
            "rascunhos": escalas.rascunhos,
        },
        "cobertura": {
            "postos_ativos": len(postos_alocados),
            "postos_cobertos": postos_cobertos,
            "postos_descobertos": postos_descobertos,
            "percentual": cobertura_pct,
        },
        "postos_alocados": postos_alocados,
        "fonte": (
            "posts + allocations + employees + diarists + diarist_assignments + "
            "occurrences + scales (SQL direto, contagens reais)"
        ),
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CHAT — pergunta ancorada no contexto real
# ─────────────────────────────────────────────────────────────────────────────
_REGRAS_COMUNS = """Você é o COO (diretor de operações) da Conecta Mais, empresa de \
segurança patrimonial e portaria em Manaus-AM. Sua especialidade: cobertura de postos \
em condomínios, alocação de agentes de portaria, escalas 12x36, gestão de diaristas \
(faxina/jardinagem/apoio, pagas por diária) e ocorrências de campo.
REGRAS INEGOCIÁVEIS:
- NUNCA invente número, posto, funcionário, diarista ou ocorrência. Use APENAS o contexto real fornecido.
- Se a informação não está no contexto, diga claramente "não está registrado no sistema".
- Posto ativo SEM alocação ativa = posto descoberto — é o risco operacional número 1, sempre aponte.
- Zero ocorrências registradas NÃO significa zero problemas — significa que nada foi registrado; alerte quando for o caso.
- Escala em rascunho não cobre ninguém — só escala vigente conta.
- Responda em Markdown curto: ## Resposta direta, ## Situação real (números do contexto), \
## Próximos passos (checklist acionável), ## Atenção (riscos operacionais).
- Somos AGENTES DE PORTARIA (CCT SINDECOMPRESTS), não vigilância armada — não recomende porte de arma."""

_LENTES = {
    "postos": "FOCO: postos — quais estão ativos, cobertos e descobertos; efetivo requerido vs alocado por posto; onde o risco de descobertura é maior.",
    "alocacoes": "FOCO: alocações e escalas — quem está alocado onde, alocações ativas vs funcionários ativos, escalas 12x36 vigentes vs rascunho, folgas e trocas.",
    "diaristas": "FOCO: diaristas — cadastro ativo, vínculos ativos, disponibilidade para cobrir demanda avulsa; lembre que diária é paga no dia 15 e o cadastro exige CPF + PIX.",
    "ocorrencias": "FOCO: ocorrências de campo — o que está registrado, abertas vs resolvidas; se não há NENHUM registro, orientar a registrar (o campo sem registro é ponto cego).",
}


def _detectar_escalonamento(pergunta: str, resposta: str) -> bool:
    alvo = f"{pergunta} {resposta}".lower()
    return any(g in alvo for g in _GATILHOS_ESCALONAR)


async def consultar(
    db: AsyncSession, *, area: str, pergunta: str,
    posto: str | None = None, user_id: str | None = None,
    anexo_texto: str | None = None, anexo_nome: str | None = None,
) -> dict[str, Any]:
    await _ensure_schema(db)
    area_n = (area or "").strip().lower()
    if area_n not in AREAS_VALIDAS:
        raise ValueError(f"Área inválida '{area}'. Válidas: {', '.join(sorted(AREAS_VALIDAS))}")

    pano = await panorama(db)

    contexto = [
        "=== PANORAMA REAL DA OPERAÇÃO (agora) ===",
        f"Postos: {pano['postos']['ativos']} ativos de {pano['postos']['total']} cadastrados",
        f"Alocações ativas: {pano['alocacoes_ativas']}",
        f"Funcionários: {pano['funcionarios']['ativos']} ativos | {pano['funcionarios']['afastados_inss']} afastados (INSS)",
        f"Diaristas: {pano['diaristas']['ativos']} ativos de {pano['diaristas']['total']} cadastrados | vínculos ativos: {pano['vinculos_diaristas_ativos']}",
        f"Ocorrências de campo: {pano['ocorrencias']['total']} registradas ({pano['ocorrencias']['abertas']} abertas)"
        + (" — ATENÇÃO: nenhum registro, campo sem visibilidade" if pano['ocorrencias']['total'] == 0 else ""),
        f"Escalas: {pano['escalas']['vigentes_hoje']} vigentes hoje | {pano['escalas']['rascunhos']} em rascunho | {pano['escalas']['total']} no total",
        f"Cobertura: {pano['cobertura']['postos_cobertos']}/{pano['cobertura']['postos_ativos']} postos ativos com alocação"
        + (f" ({pano['cobertura']['percentual']}%)" if pano['cobertura']['percentual'] is not None else ""),
        "",
        "POR POSTO ATIVO (efetivo requerido | alocados ativos | coberto?):",
    ]
    for p in pano["postos_alocados"]:
        contexto.append(
            f"- {p['posto']}: requerido={p['efetivo_requerido']} | alocados={p['alocados']}"
            f" | {'COBERTO' if p['coberto'] else 'DESCOBERTO'}"
        )
    if pano["cobertura"]["postos_descobertos"]:
        contexto.append("")
        contexto.append(
            "POSTOS DESCOBERTOS (risco): " + ", ".join(pano["cobertura"]["postos_descobertos"])
        )

    system_prompt = f"{_REGRAS_COMUNS}\n\n{_LENTES[area_n]}\n\n{chr(10).join(contexto)}"

    user_content = (pergunta or "").strip() or "Faça um diagnóstico da cobertura operacional agora."
    if posto:
        user_content = f"[Posto em foco: {posto}] {user_content}"
    if (anexo_texto or "").strip():
        user_content += (
            f"\n\n=== DOCUMENTO ANEXADO{f' ({anexo_nome})' if anexo_nome else ''} ===\n"
            f"{anexo_texto.strip()[:14000]}\n=== FIM DO DOCUMENTO ===\n\n"
            "Analise o documento acima à luz da pergunta e do panorama real da operação."
        )

    resposta_texto: str | None = None
    llm_meta: dict[str, Any] = {}
    try:
        from modules.ai.conversation.services import consultor_hub as _hub

        _extra = await _hub.contexto_compartilhado(db, "operacional")
        _conversa = await _hub.conversa_recente(db, "operacional")
        if _extra:
            system_prompt = f"{system_prompt}\n\n{_extra}"
        if _conversa:
            system_prompt = f"{system_prompt}\n\n{_conversa}"
        resposta_texto, llm_meta = await _hub.gerar(
            messages=[{"role": "user", "content": user_content}],
            system_prompt=system_prompt, max_tokens=2500, temperature=0.2,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Consultor Operacional: LLM indisponível: %s", e)
        from modules.ai.conversation.services.llm_credit_alert import alertar_llm_indisponivel

        await alertar_llm_indisponivel("Consultor Operacional (COO)", str(e))

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
                "INSERT INTO operacional_consultas "
                "(area, posto, pergunta, resposta, escalonar, disclaimer, contexto_usado, created_by) "
                "VALUES (:a, :po, :p, :r, :e, :d, CAST(:ctx AS jsonb), :by) RETURNING id"
            ),
            {
                "a": area_n, "po": posto, "p": user_content[:8000], "r": resposta_texto,
                "e": escalonar, "d": DISCLAIMER,
                "ctx": _json.dumps({"panorama": pano, "llm": llm_meta}, default=str),
                "by": user_id,
            },
        )
    ).first()
    await db.commit()

    # aprendizado permanente (best-effort, nunca quebra o chat)
    try:
        from modules.ai.conversation.services import consultor_hub as _hub

        await _hub.aprender(db, "operacional", pergunta or "", resposta_texto)
    except Exception as e:  # noqa: BLE001
        logger.warning("Consultor Operacional: aprender falhou: %s", e)

    return {
        "resposta": resposta_texto, "escalonar": escalonar, "disclaimer": DISCLAIMER,
        "id": row.id if row else None, "indisponivel": False, "panorama": pano,
    }


async def listar_consultas(db: AsyncSession, *, area: str | None = None, limit: int = 50) -> list[dict]:
    await _ensure_schema(db)
    where, params = "", {"lim": limit}
    if area:
        where = "WHERE area = :a"
        params["a"] = area.strip().lower()
    rows = (
        await db.execute(
            text(
                "SELECT id, area, posto, pergunta, resposta, escalonar, created_at "
                f"FROM operacional_consultas {where} ORDER BY created_at DESC LIMIT :lim"
            ),
            params,
        )
    ).fetchall()
    return [
        {**dict(r._mapping), "created_at": str(r.created_at), "pergunta": r.pergunta[:300]}
        for r in rows
    ]
