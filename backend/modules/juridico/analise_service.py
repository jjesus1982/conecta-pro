"""Análise de Contrato com IA (módulo Jurídico do Conecta PRO).

Revisão CLÁUSULA-A-CLÁUSULA do texto de um contrato contra um PLAYBOOK padrão da empresa
(posições desejadas por tipo de cláusula). Para cada cláusula relevante, retorna avaliação,
nível de risco (baixo/médio/alto) e sugestão de redação/negociação. Calcula um score_risco
(0-100) e conta as cláusulas críticas.

Empresa: segurança patrimonial / agentes de portaria (CCT SINDECOMPRESTS). O playbook reflete
as posições contratuais desejadas na prestação de serviços a condomínios e empresas.

Padrão inspirado no claude-for-legal (Apache-2.0), implementado nativo.
Princípio: a IA fundamenta, o humano certifica; NUNCA inventa lei. Se o LLM faltar em runtime
→ resposta honesta "IA indisponível", sem fabricar análise.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── PLAYBOOK padrão da empresa: posição desejada por tipo de cláusula ─────────
PLAYBOOK: dict[str, str] = {
    "objeto": (
        "Objeto deve descrever com precisão os serviços de portaria/segurança patrimonial "
        "(postos, turnos, escala 12x36), sem ampliar o escopo para vigilância armada ou "
        "atividades estranhas à categoria."
    ),
    "prazo": (
        "Prazo determinado (usualmente 12 meses) com renovação por acordo expresso ou "
        "automática mediante aviso prévio. Evitar prazo indeterminado sem cláusula de saída."
    ),
    "reajuste": (
        "Reajuste anual OBRIGATÓRIO vinculado à CCT do SINDECOMPRESTS e/ou índice oficial "
        "(IPCA/IGP-M), repassando os aumentos de piso e encargos. Repactuação por alteração "
        "de convenção coletiva deve ser prevista."
    ),
    "rescisao": (
        "Rescisão com aviso prévio mínimo de 30 dias por qualquer parte; rescisão imotivada "
        "não pode gerar multa desproporcional contra a contratada. Prever rescisão por "
        "inadimplemento com notificação."
    ),
    "multa": (
        "Multa limitada e proporcional (usualmente até 10% do valor remanescente ou 1-2 "
        "mensalidades). Rejeitar multas unilaterais, cumulativas ou excessivas contra a contratada."
    ),
    "foro": (
        "Foro da comarca de Manaus/AM (sede da contratada) ou eleição equilibrada. "
        "Rejeitar foro distante que dificulte a defesa."
    ),
    "responsabilidade": (
        "Responsabilidade da contratada limitada à culpa comprovada e ao valor do contrato; "
        "afastar responsabilidade objetiva por furto/roubo (portaria NÃO é vigilância armada) "
        "e por caso fortuito/força maior."
    ),
    "lgpd": (
        "Cláusula de proteção de dados (LGPD, Lei 13.709/2018): tratamento restrito à "
        "finalidade, confidencialidade, segurança, e responsabilidades definidas entre "
        "controlador e operador. Deve existir e estar adequada."
    ),
}

_DISCLAIMER = (
    "Análise assistida por IA, de caráter opinativo. NÃO substitui a revisão de advogado "
    "habilitado (OAB). A IA não inventa lei; referências devem ser conferidas na fonte oficial. "
    "A certificação final é do responsável jurídico."
)


def _system_prompt() -> str:
    playbook_txt = "\n".join(f"- {tipo.upper()}: {pos}" for tipo, pos in PLAYBOOK.items())
    return (
        "Você é um advogado revisor de contratos de uma empresa brasileira de SEGURANÇA "
        "PATRIMONIAL / AGENTES DE PORTARIA (não vigilância armada; base na CCT SINDECOMPRESTS). "
        "Faça a revisão CLÁUSULA-A-CLÁUSULA do contrato fornecido, comparando cada cláusula "
        "relevante com o PLAYBOOK de posições desejadas da empresa.\n\n"
        f"PLAYBOOK (posição desejada por tipo de cláusula):\n{playbook_txt}\n\n"
        "REGRAS INVIOLÁVEIS:\n"
        "1. NUNCA invente leis, artigos ou jurisprudência. Se citar norma, só o faça com certeza; "
        "caso contrário, descreva o risco sem citar norma específica.\n"
        "2. A IA fundamenta, o humano certifica. Sinalize risco alto onde a cláusula desviar do "
        "playbook em desfavor da empresa, for abusiva, ambígua ou ausente.\n"
        "3. Cubra ao menos os tipos do playbook (objeto, prazo, reajuste, rescisão, multa, foro, "
        "responsabilidade, lgpd). Se uma cláusula esperada estiver AUSENTE no contrato, registre-a "
        "como cláusula com risco (avaliação = 'ausente') e sugestão de inclusão.\n\n"
        "FORMATO DE SAÍDA — responda EXCLUSIVAMENTE com JSON válido (sem markdown, sem texto fora "
        "do JSON) no schema:\n"
        "{\n"
        '  "clausulas": [\n'
        '    {"clausula": "nome/tipo da cláusula", "avaliacao": "análise objetiva do texto vs playbook",\n'
        '     "risco": "baixo|medio|alto", "sugestao": "sugestão de redação ou negociação"}\n'
        "  ],\n"
        '  "resumo": "parecer geral curto sobre o contrato"\n'
        "}"
    )


_MODEL_OPENAI = "gpt-5"  # análise pesada
_MODEL_ANTHROPIC = "claude-sonnet-4-6"  # fallback opcional (só se ANTHROPIC_API_KEY definida)


async def _chamar_llm(system_prompt: str, user_content: str, max_tokens: int = 8192) -> dict[str, Any] | None:
    """Cascata OpenAI → Anthropic. Retorna None se nenhum provedor disponível (sem fabricar)."""
    try:
        from core.llm_cascade import aroute_ex

        # tier PESADA: risco jurídico → melhor modelo direto (não escala p/ baixo)
        result = await aroute_ex(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            tier="pesada",
            max_tokens=max_tokens,
            temperature=0.2,
            json_mode=True,
        )
        if result is None:
            logger.warning("Análise contrato: nenhum provedor LLM disponível — IA indisponível")
            return None
        content, provider, model, _tier = result
        logger.info("Análise contrato: resposta via %s (%s)", provider, model)
        return {"content": content, "model": model}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Análise contrato: falha ao chamar LLM: {e}")
        return None


def _parse_json_llm(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        s = s.removeprefix("json").strip()
    try:
        return json.loads(s)
    except Exception:  # noqa: BLE001
        ini = s.find("{")
        fim = s.rfind("}")
        if ini != -1 and fim != -1 and fim > ini:
            try:
                return json.loads(s[ini : fim + 1])
            except Exception:  # noqa: BLE001
                return None
    return None


_PESO_RISCO = {"alto": 100, "medio": 55, "baixo": 15}


def _normalizar_risco(v: Any) -> str:
    r = str(v or "").strip().lower()
    if r in ("alto", "high", "critico", "crítico"):
        return "alto"
    if r in ("medio", "médio", "medium", "moderado"):
        return "medio"
    return "baixo"


def _calcular_score(clausulas: list[dict]) -> tuple[int, int]:
    """Score de risco (0-100, média ponderada dos pesos) + contagem de cláusulas críticas (alto)."""
    if not clausulas:
        return 0, 0
    pesos = [_PESO_RISCO[_normalizar_risco(c.get("risco"))] for c in clausulas]
    score = round(sum(pesos) / len(pesos))
    criticas = sum(1 for c in clausulas if _normalizar_risco(c.get("risco")) == "alto")
    return int(score), int(criticas)


async def _ensure_table(db: AsyncSession) -> None:
    """Cria a tabela juridico_analises se ainda não existir (idempotente, sem migration)."""
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS juridico_analises (
                id                  SERIAL PRIMARY KEY,
                tipo                VARCHAR(40)  NOT NULL DEFAULT 'contrato',
                nome                TEXT         NOT NULL,
                conteudo            TEXT,
                resultado           JSONB,
                score_risco         INTEGER      NOT NULL DEFAULT 0,
                clausulas_criticas  INTEGER      NOT NULL DEFAULT 0,
                created_by          VARCHAR(64),
                created_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
            )
            """
        )
    )


async def analisar_contrato(
    db: AsyncSession,
    nome: str,
    conteudo: str,
    user_id: str | None,
) -> dict[str, Any]:
    """Revisa o contrato cláusula-a-cláusula vs playbook e persiste em juridico_analises.

    Se a IA estiver indisponível, registra o pedido honestamente sem fabricar análise.
    """
    await _ensure_table(db)

    if not conteudo or not conteudo.strip():
        raise ValueError("Conteúdo do contrato vazio.")

    llm = await _chamar_llm(_system_prompt(), f"CONTRATO A REVISAR:\n\n{conteudo.strip()}")

    if llm is None:
        row = await db.execute(
            text(
                """
                INSERT INTO juridico_analises
                    (tipo, nome, conteudo, resultado, score_risco, clausulas_criticas, created_by)
                VALUES
                    ('contrato', :nome, :conteudo, NULL, 0, 0, :created_by)
                RETURNING id, created_at
                """
            ),
            {"nome": nome, "conteudo": conteudo, "created_by": str(user_id) if user_id else None},
        )
        rec = row.mappings().first()
        return {
            "id": rec["id"],
            "tipo": "contrato",
            "nome": nome,
            "ia_disponivel": False,
            "clausulas": [],
            "score_risco": 0,
            "clausulas_criticas": 0,
            "mensagem": (
                "IA indisponível no momento. O pedido foi registrado, mas nenhuma análise foi "
                "gerada — encaminhe ao responsável jurídico."
            ),
            "disclaimer": _DISCLAIMER,
            "created_at": rec["created_at"].isoformat() if rec.get("created_at") else None,
        }

    parsed = _parse_json_llm(llm["content"])
    if not parsed or not isinstance(parsed.get("clausulas"), list):
        clausulas: list[dict] = []
        resumo = "Resposta da IA fora do formato esperado — requer revisão humana."
    else:
        clausulas = []
        for c in parsed["clausulas"]:
            if not isinstance(c, dict):
                continue
            clausulas.append(
                {
                    "clausula": str(c.get("clausula", "")).strip() or "—",
                    "avaliacao": str(c.get("avaliacao", "")).strip(),
                    "risco": _normalizar_risco(c.get("risco")),
                    "sugestao": str(c.get("sugestao", "")).strip(),
                }
            )
        resumo = str(parsed.get("resumo", "")).strip()

    score, criticas = _calcular_score(clausulas)
    resultado = {"clausulas": clausulas, "resumo": resumo, "modelo_ia": llm["model"]}

    row = await db.execute(
        text(
            """
            INSERT INTO juridico_analises
                (tipo, nome, conteudo, resultado, score_risco, clausulas_criticas, created_by)
            VALUES
                ('contrato', :nome, :conteudo, CAST(:resultado AS JSONB), :score, :criticas, :created_by)
            RETURNING id, created_at
            """
        ),
        {
            "nome": nome,
            "conteudo": conteudo,
            "resultado": json.dumps(resultado, ensure_ascii=False),
            "score": score,
            "criticas": criticas,
            "created_by": str(user_id) if user_id else None,
        },
    )
    rec = row.mappings().first()

    return {
        "id": rec["id"],
        "tipo": "contrato",
        "nome": nome,
        "ia_disponivel": True,
        "clausulas": clausulas,
        "resumo": resumo,
        "score_risco": score,
        "clausulas_criticas": criticas,
        "modelo_ia": llm["model"],
        "disclaimer": _DISCLAIMER,
        "created_by": str(user_id) if user_id else None,
        "created_at": rec["created_at"].isoformat() if rec.get("created_at") else None,
    }


async def listar_analises(db: AsyncSession, limit: int = 50) -> list[dict[str, Any]]:
    """Lista as análises mais recentes (metadados + score, sem o texto completo do contrato)."""
    await _ensure_table(db)
    rows = await db.execute(
        text(
            """
            SELECT id, tipo, nome, score_risco, clausulas_criticas, created_by, created_at
            FROM juridico_analises
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"limit": int(limit)},
    )
    out = []
    for r in rows.mappings().all():
        out.append(
            {
                "id": r["id"],
                "tipo": r["tipo"],
                "nome": r["nome"],
                "score_risco": r["score_risco"],
                "clausulas_criticas": r["clausulas_criticas"],
                "created_by": r["created_by"],
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            }
        )
    return out
