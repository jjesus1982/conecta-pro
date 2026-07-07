"""Consultor Jurídico IA — Conecta Mais (segurança patrimonial / agentes de portaria).

Consultor especializado em 3 áreas: trabalhista, cível e tributária. Responde dúvidas
do dia a dia FUNDAMENTADO (cita fonte legal), com disclaimer e sinalização de
escalonamento em casos de alto risco.

Princípio: a IA ASSISTE, o humano/escritório CERTIFICA. NUNCA inventa lei ou
jurisprudência — cita a fonte ou diz explicitamente "consultar escritório".

Reusa o LLM já configurado do projeto (ClaudeProvider). Se a chave/cliente faltar em
runtime, responde honestamente que a IA jurídica está indisponível — não fabrica.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constantes
# --------------------------------------------------------------------------- #

AREAS_VALIDAS = ("trabalhista", "civel", "tributaria")

DISCLAIMER_PADRAO = (
    "Apoio jurídico por IA — não substitui parecer formal do advogado. "
    "Em caso de alto risco, consulte o escritório."
)

MSG_INDISPONIVEL = (
    "IA jurídica indisponível — configurar. O provedor de LLM não está "
    "acessível no momento. Encaminhe a dúvida ao escritório enquanto a integração é ajustada."
)

# Contexto REAL da empresa para fundamentar as respostas (embutido no system prompt).
_CONTEXTO_EMPRESA = """CONTEXTO DA EMPRESA (use para fundamentar, é a verdade dos fatos):
- Atividade: SEGURANÇA PATRIMONIAL — a categoria é de AGENTES DE PORTARIA (NÃO é vigilância
  armada / vigilante regido pela Lei 7.102/83). Não confundir portaria com vigilância.
- Convenção Coletiva de referência: CCT SINDECOMPRESTS AM000613/2025 — é a FONTE DA VERDADE
  para pisos, adicionais e benefícios da categoria. PISO da categoria em 2026 = R$ 1.670,00
  (a base salarial é o PISO da CCT, jamais o mínimo federal). Adicionais são calculados
  por-pessoa/por-cargo conforme a CCT.
- Salário mínimo federal 2026 = R$ 1.621,00 (usado apenas como referência p/ INSS, não como base).
- Encargos: INSS e IRRF conforme tabelas vigentes de 2026.

ESTRUTURA SOCIETÁRIA / TRIBUTÁRIA (fatos):
- CNPJ1 (Jordan Santos de Jesus Ltda) 35.710.481/0001-03 — Manaus/AM — atualmente em LUCRO REAL
  (desde 01/01/2026). Estratégia: migrar contratos humanizados para o CNPJ2 e voltar ao SIMPLES.
- CNPJ2 (Conecta Mais Patrimonial) — em abertura — SIMPLES NACIONAL, CNAE 8111-7/00
  (serviços combinados p/ apoio a edifícios). Serviços humanizados vão para o CNPJ2.
- Retenções relevantes na tomada/prestação de serviços de mão de obra: ISS, INSS (retenção de
  11% na cessão de mão de obra — art. 31 Lei 8.212/91 quando aplicável), CSLL/PIS/COFINS/IRRF
  (retenções federais). Há discussão/liminares sobre PIS/COFINS.
- Carteira: ~10 contratos ativos, faturamento mensal na ordem de R$ 270 mil.
"""


# --------------------------------------------------------------------------- #
# System prompts por área
# --------------------------------------------------------------------------- #

_REGRAS_COMUNS = f"""Você é o Consultor Jurídico IA do Conecta PRO, ERP da Conecta Mais.
Sua função é APOIAR o dia a dia jurídico da empresa — a IA assiste, o advogado/escritório
certifica. Responda em português do Brasil, de forma objetiva e prática.

REGRAS INEGOCIÁVEIS:
1. FUNDAMENTE toda orientação citando a fonte legal específica (artigo da CLT, cláusula da
   CCT SINDECOMPRESTS AM000613/2025, artigo do CDC/Código Civil, ou dispositivo tributário).
2. NUNCA invente lei, número de artigo, súmula ou jurisprudência. Se não tiver certeza da
   fonte, diga explicitamente "consultar o escritório para confirmar a fundamentação" —
   é preferível admitir a dúvida a fabricar uma citação.
3. Sempre distinga o que é regra clara do que é interpretação/tese sujeita a debate.
4. Sinalize ALTO RISCO (e a necessidade de escalar ao escritório) quando a dúvida envolver:
   processo judicial em curso ou iminente, tese jurídica nova/controversa, rescisão/demissão,
   valores elevados, autuação fiscal, ou qualquer decisão com efeito irreversível.
5. Ao final da resposta, liste as FONTES efetivamente citadas.

FORMATO DA RESPOSTA (use Markdown, seja organizado e escaneável):
## Resposta direta
Uma resposta objetiva em 1–3 frases (o "sim/não/depende" e o essencial).
## Fundamentação
O porquê, citando a fonte legal específica (artigo/cláusula) em **negrito**.
## Na prática
Passo a passo do que fazer, em lista numerada ou com marcadores (-).
## Atenção
Riscos, prazos, exceções e ressalvas relevantes (se houver).
## Fontes
Lista das fontes legais efetivamente citadas.
Regras de formatação: use `##` para os títulos das seções, **negrito** para artigos/valores/prazos,
listas com `-` ou numeradas. Seja conciso — evite parágrafos longos. Omita uma seção se não se aplicar.

{_CONTEXTO_EMPRESA}
"""

_PROMPTS_AREA = {
    "trabalhista": (
        _REGRAS_COMUNS
        + """
ÁREA: DIREITO DO TRABALHO.
Base normativa: CLT (Decreto-Lei 5.452/43), CCT SINDECOMPRESTS AM000613/2025 (piso,
adicionais, benefícios da categoria de agentes de portaria), NRs aplicáveis, jurisprudência
do TST quando pertinente. Lembre que a base salarial é o PISO da CCT (R$ 1.670 em 2026).
Trate temas como jornada 12x36, adicional noturno, horas extras, intervalos, banco de horas,
férias, verbas rescisórias, admissão/demissão e enquadramento sindical da categoria.
"""
    ),
    "civel": (
        _REGRAS_COMUNS
        + """
ÁREA: DIREITO CÍVEL / CONTRATUAL / CONSUMIDOR.
Base normativa: Código Civil (Lei 10.406/02), CDC (Lei 8.078/90) quando houver relação de
consumo, e legislação correlata. Trate contratos de prestação de serviços de portaria/
segurança patrimonial, responsabilidade civil, cláusulas de reajuste, rescisão contratual,
multas, cobrança, inadimplência e relação com condomínios/empresas contratantes.
"""
    ),
    "tributaria": (
        _REGRAS_COMUNS
        + """
ÁREA: DIREITO TRIBUTÁRIO.
Base normativa: CTN (Lei 5.172/66), legislação do SIMPLES NACIONAL (LC 123/06), regras do
Lucro Real, ISS (LC 116/03 e legislação de Manaus/AM), retenções federais (IRRF, PIS, COFINS,
CSLL) e retenção previdenciária de 11% na cessão de mão de obra (art. 31 Lei 8.212/91).
Considere a estrutura societária (CNPJ1 em Lucro Real migrando p/ Simples; CNPJ2 no Simples)
e as discussões/liminares sobre PIS/COFINS. Enquadramento de regime e planejamento com efeito
relevante são ALTO RISCO — recomende validação com o contador (Domínio/TOTVS) e escritório.
"""
    ),
}


# --------------------------------------------------------------------------- #
# Tabela (criação idempotente — sem migration)
# --------------------------------------------------------------------------- #

_DDL_CONSULTAS = """
CREATE TABLE IF NOT EXISTS juridico_consultas (
    id           BIGSERIAL PRIMARY KEY,
    area         VARCHAR(20)  NOT NULL,
    pergunta     TEXT         NOT NULL,
    resposta     TEXT         NOT NULL,
    fontes       JSONB        NOT NULL DEFAULT '[]'::jsonb,
    escalonar    BOOLEAN      NOT NULL DEFAULT FALSE,
    disclaimer   TEXT         NOT NULL,
    contexto_usado JSONB      NOT NULL DEFAULT '{}'::jsonb,
    created_by   VARCHAR(64),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);
"""


async def _garantir_tabela(db: AsyncSession) -> None:
    """Cria a tabela juridico_consultas se ainda não existir (idempotente)."""
    await db.execute(text(_DDL_CONSULTAS))


# --------------------------------------------------------------------------- #
# Enriquecimento de contexto com dados reais do banco
# --------------------------------------------------------------------------- #

async def _contexto_dados_reais(db: AsyncSession) -> dict[str, Any]:
    """Consulta contagens reais do banco para enriquecer o contexto (best-effort)."""
    ctx: dict[str, Any] = {}
    try:
        row = await db.execute(
            text("SELECT COUNT(*) FROM employees WHERE status = 'ativo'")
        )
        ctx["funcionarios_ativos"] = int(row.scalar() or 0)
    except Exception as e:  # pragma: no cover - tabela pode variar
        logger.debug("Falha ao contar employees: %s", e)
    try:
        row = await db.execute(
            text("SELECT COUNT(*) FROM contracts WHERE lower(status) = 'active'")
        )
        ctx["contratos_ativos"] = int(row.scalar() or 0)
    except Exception as e:  # pragma: no cover
        logger.debug("Falha ao contar contracts: %s", e)
    return ctx


def _formatar_contexto_real(ctx: dict[str, Any]) -> str:
    if not ctx:
        return ""
    partes = []
    if "funcionarios_ativos" in ctx:
        partes.append(f"funcionários ativos: {ctx['funcionarios_ativos']}")
    if "contratos_ativos" in ctx:
        partes.append(f"contratos ativos: {ctx['contratos_ativos']}")
    if not partes:
        return ""
    return "\nDADOS REAIS DO BANCO AGORA (" + "; ".join(partes) + ")."


# --------------------------------------------------------------------------- #
# Heurística de escalonamento (defensiva, além do sinal do LLM)
# --------------------------------------------------------------------------- #

_GATILHOS_RISCO = (
    "processo", "ação judicial", "acao judicial", "reclamatória", "reclamatoria",
    "demissão", "demissao", "rescisão", "rescisao", "justa causa", "autuação",
    "autuacao", "auto de infração", "auto de infracao", "liminar", "penhora",
    "execução", "execucao", "tese", "inconstitucional", "danos morais",
)


def _detectar_risco_pergunta(pergunta: str) -> bool:
    p = (pergunta or "").lower()
    return any(g in p for g in _GATILHOS_RISCO)


# --------------------------------------------------------------------------- #
# Parsing da resposta do LLM
# --------------------------------------------------------------------------- #

def _extrair_fontes(texto: str) -> list[str]:
    """Extrai referências legais citadas (heurística leve sobre o texto da resposta)."""
    import re

    fontes: list[str] = []
    padroes = [
        r"art(?:igo)?\.?\s*\d+[\-ºo]?(?:\s*(?:da|do)\s*[A-ZÀ-Úa-zà-ú]{2,20})?",
        r"CLT",
        r"CDC",
        r"C[óo]digo Civil",
        r"CTN",
        r"LC\s*\d+/\d+",
        r"Lei\s*n?º?\.?\s*[\d\.]+/\d+",
        r"S[úu]mula\s*\d+",
        r"CCT\s*[A-Z0-9/]+",
        r"NR-?\s*\d+",
    ]
    for pad in padroes:
        for m in re.finditer(pad, texto, flags=re.IGNORECASE):
            f = m.group(0).strip()
            if f and f not in fontes:
                fontes.append(f)
    return fontes[:20]


# --------------------------------------------------------------------------- #
# API pública do serviço
# --------------------------------------------------------------------------- #

async def consultar(
    db: AsyncSession,
    area: str,
    pergunta: str,
    user_id: str | None,
    anexo_texto: str | None = None,
    anexo_nome: str | None = None,
) -> dict[str, Any]:
    """Responde uma dúvida jurídica fundamentada na área indicada e persiste a consulta.

    anexo_texto: texto extraído de um arquivo anexado (PDF/DOCX/TXT) para a IA analisar.
    Retorna: {resposta, fontes, escalonar, disclaimer, id}
    """
    area_norm = (area or "").strip().lower()
    if area_norm not in AREAS_VALIDAS:
        raise ValueError(
            f"Área inválida '{area}'. Áreas válidas: {', '.join(AREAS_VALIDAS)}."
        )
    if not (pergunta or "").strip() and not (anexo_texto or "").strip():
        raise ValueError("A pergunta não pode ser vazia.")

    await _garantir_tabela(db)

    contexto_real = await _contexto_dados_reais(db)
    system_prompt = _PROMPTS_AREA[area_norm] + _formatar_contexto_real(contexto_real)
    # Base de conhecimento/playbook da própria empresa (RAG-lite)
    try:
        from modules.juridico import conhecimento_service as _CS
        _kb = await _CS.contexto_para_prompt(db, area_norm, f"{pergunta} {anexo_texto or ''}")
        if _kb:
            system_prompt += _kb
    except Exception:  # noqa: BLE001
        pass

    contexto_usado = {
        "area": area_norm,
        "dados_reais": contexto_real,
        "cct": "SINDECOMPRESTS AM000613/2025",
    }

    # Chamada ao LLM já configurado no projeto. Se indisponível, responde honesto.
    resposta_texto: str | None = None
    llm_ok = False
    llm_meta: dict[str, Any] = {}
    try:
        import os as _os

        from modules.ai.conversation.services import consultor_hub as _hub
        _extra = await _hub.contexto_compartilhado(db, 'juridico')
        _conversa = await _hub.conversa_recente(db, 'juridico')
        if _extra:
            system_prompt = f"{system_prompt}\n\n{_extra}"
        if _conversa:
            system_prompt = f"{system_prompt}\n\n{_conversa}"
        from modules.ai.conversation.services.llm_provider import ClaudeProvider, OpenAIProvider

        # OpenAI é o provider PRIMÁRIO dos consultores (decisão Jordan 2026-07-07:
        # mais barato que Anthropic). Claude fica como fallback se a chave faltar.
        pass  # geração via hub (melhor modelo + fallback)

        user_content = pergunta.strip()
        if (anexo_texto or "").strip():
            user_content = (
                f"{user_content}\n\n=== DOCUMENTO ANEXADO PELO USUÁRIO"
                f"{f' ({anexo_nome})' if anexo_nome else ''} ===\n"
                f"{anexo_texto.strip()[:14000]}\n=== FIM DO DOCUMENTO ===\n\n"
                "Analise o documento acima à luz da pergunta e responda de forma fundamentada."
            )
        resposta_texto, llm_meta = await _hub.gerar(
            messages=[{"role": "user", "content": user_content}],
            system_prompt=system_prompt, max_tokens=2500, temperature=0.2,
        )
    except Exception as e:
        logger.warning("Consultor jurídico: LLM indisponível (%s)", e)
        from modules.ai.conversation.services.llm_credit_alert import alertar_llm_indisponivel
        await alertar_llm_indisponivel("Consultor Jurídico", str(e))
        llm_ok = False

    if not llm_ok:
        # Honesto: não fabrica resposta.
        resultado = {
            "resposta": MSG_INDISPONIVEL,
            "fontes": [],
            "escalonar": True,
            "disclaimer": DISCLAIMER_PADRAO,
            "id": None,
            "indisponivel": True,
        }
        contexto_usado["llm_indisponivel"] = True
        try:
            row = await db.execute(
                text(
                    """
                    INSERT INTO juridico_consultas
                        (area, pergunta, resposta, fontes, escalonar, disclaimer,
                         contexto_usado, created_by)
                    VALUES
                        (:area, :pergunta, :resposta, CAST(:fontes AS jsonb), :escalonar,
                         :disclaimer, CAST(:contexto AS jsonb), :created_by)
                    RETURNING id
                    """
                ),
                {
                    "area": area_norm,
                    "pergunta": pergunta.strip(),
                    "resposta": MSG_INDISPONIVEL,
                    "fontes": json.dumps([]),
                    "escalonar": True,
                    "disclaimer": DISCLAIMER_PADRAO,
                    "contexto": json.dumps(contexto_usado, default=str, ensure_ascii=False),
                    "created_by": str(user_id) if user_id else None,
                },
            )
            resultado["id"] = int(row.scalar())
        except Exception as e:  # pragma: no cover
            logger.error("Falha ao persistir consulta indisponível: %s", e)
        return resultado

    # Determina escalonamento: sinal textual do LLM OU heurística de risco na pergunta.
    resp_lower = resposta_texto.lower()
    escalonar_llm = any(
        s in resp_lower
        for s in ("escalar", "escalonar", "consultar o escritório", "consultar escritório",
                  "consultar o escritorio", "alto risco", "procure um advogado")
    )
    escalonar = bool(escalonar_llm or _detectar_risco_pergunta(pergunta))

    fontes = _extrair_fontes(resposta_texto)
    contexto_usado["llm"] = llm_meta
    contexto_usado["escalonar_por_pergunta"] = _detectar_risco_pergunta(pergunta)

    consulta_id: int | None = None
    try:
        row = await db.execute(
            text(
                """
                INSERT INTO juridico_consultas
                    (area, pergunta, resposta, fontes, escalonar, disclaimer,
                     contexto_usado, created_by)
                VALUES
                    (:area, :pergunta, :resposta, CAST(:fontes AS jsonb), :escalonar,
                     :disclaimer, CAST(:contexto AS jsonb), :created_by)
                RETURNING id
                """
            ),
            {
                "area": area_norm,
                "pergunta": pergunta.strip(),
                "resposta": resposta_texto,
                "fontes": json.dumps(fontes, ensure_ascii=False),
                "escalonar": escalonar,
                "disclaimer": DISCLAIMER_PADRAO,
                "contexto": json.dumps(contexto_usado, default=str, ensure_ascii=False),
                "created_by": str(user_id) if user_id else None,
            },
        )
        consulta_id = int(row.scalar())
    except Exception as e:  # pragma: no cover
        logger.error("Falha ao persistir consulta jurídica: %s", e)

    # aprendizado permanente do hub (best-effort, nunca quebra o chat)
    await _hub.aprender(db, "juridico", pergunta or "", resposta_texto)

    return {
        "resposta": resposta_texto,
        "fontes": fontes,
        "escalonar": escalonar,
        "disclaimer": DISCLAIMER_PADRAO,
        "id": consulta_id,
    }


async def listar_consultas(
    db: AsyncSession,
    area: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Histórico de consultas, opcionalmente filtrado por área."""
    await _garantir_tabela(db)

    limit = max(1, min(int(limit or 50), 200))
    params: dict[str, Any] = {"lim": limit}
    filtro = ""
    if area:
        area_norm = area.strip().lower()
        if area_norm not in AREAS_VALIDAS:
            raise ValueError(
                f"Área inválida '{area}'. Áreas válidas: {', '.join(AREAS_VALIDAS)}."
            )
        filtro = "WHERE area = :area"
        params["area"] = area_norm

    rows = (
        await db.execute(
            text(
                f"""
                SELECT id, area, pergunta, resposta, fontes, escalonar, disclaimer,
                       contexto_usado, created_by, created_at
                FROM juridico_consultas
                {filtro}
                ORDER BY created_at DESC, id DESC
                LIMIT :lim
                """
            ),
            params,
        )
    ).mappings().all()

    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": int(r["id"]),
                "area": r["area"],
                "pergunta": r["pergunta"],
                "resposta": r["resposta"],
                "fontes": r["fontes"] or [],
                "escalonar": bool(r["escalonar"]),
                "disclaimer": r["disclaimer"],
                "contexto_usado": r["contexto_usado"] or {},
                "created_by": r["created_by"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
        )
    return out
