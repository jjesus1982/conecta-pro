"""HUB dos Consultores IA (CFO, Jurídico, GED) — requisitos Jordan 2026-07-07.

1. MELHOR MODELO SEMPRE: cadeia gpt-5-chat-latest → gpt-5 → gpt-4.1 → gpt-4o → Claude.
   Override por env CONSULTOR_LLM_MODEL (tentado primeiro).
2. MEMÓRIA PERMANENTE + APRENDIZADO: cada resposta boa passa por um extrator barato
   (gpt-4o-mini) que destila 0-2 fatos duráveis → tabela consultor_memorias. As
   memórias de TODOS os consultores entram no prompt de CADA um.
3. CHATS CONVERSAM ENTRE SI: além das memórias compartilhadas, cada consultor vê as
   últimas consultas dos OUTROS (pergunta + resumo da resposta) — o CFO sabe o que o
   Jurídico respondeu e vice-versa.

Doutrina: memória registra FATOS (correções do gestor, decisões, particularidades do
negócio) — nunca substitui o dado vivo do banco, que continua vindo dos panoramas.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Cadeia de modelos: melhor primeiro (gpt-5 disponível na chave, provado 2026-07-07)
MODEL_CHAIN = ["gpt-5-chat-latest", "gpt-5", "gpt-4.1", "gpt-4o"]

# Tabelas de consultas de cada consultor (p/ conversa cruzada)
TABELAS_CONSULTAS = {
    "cfo": ("financial_cfo_consultas", "CFO (Financeiro)"),
    "juridico": ("juridico_consultas", "Consultor Jurídico"),
    "ged": ("gedeon_consultas", "Consultor GED"),
}

_ddl_ok = False


async def _ensure_schema(db: AsyncSession) -> None:
    global _ddl_ok
    if _ddl_ok:
        return
    existe = (
        await db.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_name='consultor_memorias'")
        )
    ).scalar_one()
    if not existe:
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS consultor_memorias (
                    id         BIGSERIAL PRIMARY KEY,
                    origem     VARCHAR(20)  NOT NULL,
                    conteudo   TEXT         NOT NULL,
                    fonte      TEXT,
                    ativo      BOOLEAN      NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
                );
                CREATE INDEX IF NOT EXISTS ix_consultor_memorias_origem
                    ON consultor_memorias (origem, ativo);
                """
            )
        )
        await db.commit()
    _ddl_ok = True


# ─────────────────────────────────────────────────────────────────────────────
# GERAÇÃO — melhor modelo sempre, com cadeia de fallback
# ─────────────────────────────────────────────────────────────────────────────
async def gerar(
    *, messages: list[dict], system_prompt: str, max_tokens: int = 2500, temperature: float = 0.2,
) -> tuple[str, dict[str, Any]]:
    """Gera com o melhor modelo disponível. Levanta RuntimeError se TODOS falharem."""
    from modules.ai.conversation.services.llm_provider import ClaudeProvider, OpenAIProvider

    chain = list(MODEL_CHAIN)
    override = os.getenv("CONSULTOR_LLM_MODEL", "").strip()
    if override and override not in chain:
        chain.insert(0, override)

    erros: list[str] = []
    for model in chain:
        try:
            p = OpenAIProvider(model=model)
            if not p.api_key:
                raise RuntimeError("OPENAI_API_KEY ausente")
            r = await p.generate(
                messages=messages, system_prompt=system_prompt,
                max_tokens=max_tokens, temperature=temperature,
            )
            texto = (r.content or "").strip()
            if texto:
                return texto, {"model": getattr(r, "model", model)}
            erros.append(f"{model}: resposta vazia")
        except Exception as e:  # noqa: BLE001
            erros.append(f"{model}: {str(e)[:120]}")
    # Fallback final: Claude (se houver chave/crédito)
    try:
        p = ClaudeProvider()
        if p.api_key:
            r = await p.generate(
                messages=messages, system_prompt=system_prompt,
                max_tokens=max_tokens, temperature=temperature,
            )
            texto = (r.content or "").strip()
            if texto:
                return texto, {"model": getattr(r, "model", "claude")}
    except Exception as e:  # noqa: BLE001
        erros.append(f"claude: {str(e)[:120]}")
    raise RuntimeError("; ".join(erros[-3:]))


# ─────────────────────────────────────────────────────────────────────────────
# MEMÓRIA COMPARTILHADA + CONVERSA CRUZADA
# ─────────────────────────────────────────────────────────────────────────────
async def contexto_compartilhado(db: AsyncSession, origem_atual: str, *, max_memorias: int = 30) -> str:
    """Bloco de prompt: memórias permanentes (todas as origens) + últimas consultas dos OUTROS consultores."""
    await _ensure_schema(db)
    partes: list[str] = []

    rows = (
        await db.execute(
            text(
                "SELECT origem, conteudo FROM consultor_memorias WHERE ativo "
                "ORDER BY created_at DESC LIMIT :lim"
            ),
            {"lim": max_memorias},
        )
    ).fetchall()
    if rows:
        partes.append("=== MEMÓRIAS PERMANENTES (aprendidas com o gestor — respeite-as) ===")
        for r in rows:
            partes.append(f"- [{r.origem}] {r.conteudo}")

    cruzadas: list[str] = []
    for chave, (tabela, rotulo) in TABELAS_CONSULTAS.items():
        if chave == origem_atual:
            continue
        try:
            qs = (
                await db.execute(
                    text(
                        f"SELECT pergunta, resposta FROM {tabela} "  # noqa: S608 — tabela de whitelist interna
                        "ORDER BY created_at DESC LIMIT 3"
                    )
                )
            ).fetchall()
            for q in qs:
                cruzadas.append(f"- [{rotulo}] P: {q.pergunta[:120]} | R: {q.resposta[:200]}")
        except Exception:  # noqa: BLE001 — tabela pode não existir ainda
            continue
    if cruzadas:
        partes.append("")
        partes.append("=== O QUE OS OUTROS CONSULTORES RESPONDERAM RECENTEMENTE (contexto cruzado) ===")
        partes.extend(cruzadas)

    return "\n".join(partes)


async def conversa_recente(db: AsyncSession, origem: str, *, limit: int = 6) -> str:
    """Continuidade: últimas trocas do PRÓPRIO consultor (memória de conversa)."""
    tabela, _ = TABELAS_CONSULTAS.get(origem, (None, None))
    if not tabela:
        return ""
    try:
        rows = (
            await db.execute(
                text(
                    f"SELECT pergunta, resposta FROM {tabela} "  # noqa: S608
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
        linhas.append(f"Gestor: {r.pergunta[:150]}")
        linhas.append(f"Você: {r.resposta[:250]}")
    return "\n".join(linhas)


async def aprender(db: AsyncSession, origem: str, pergunta: str, resposta: str) -> None:
    """Extrai 0-2 fatos duráveis da troca (gpt-4o-mini, barato) e grava como memória.

    Nunca propaga exceção — aprendizado é best-effort e não pode quebrar o chat.
    """
    try:
        await _ensure_schema(db)
        from modules.ai.conversation.services.llm_provider import OpenAIProvider

        p = OpenAIProvider(model="gpt-4o-mini")
        if not p.api_key:
            return
        r = await p.generate(
            messages=[{
                "role": "user",
                "content": (
                    "Da troca abaixo, extraia no MÁXIMO 2 fatos DURÁVEIS que valham memória "
                    "permanente para consultores de um ERP (correções do gestor, decisões de "
                    "negócio, preferências, particularidades da empresa). IGNORE números que "
                    "mudam todo mês (saldos, MRR do mês). Responda um fato por linha, curto. "
                    "Se não houver nada durável, responda exatamente: NENHUM\n\n"
                    f"PERGUNTA: {pergunta[:800]}\n\nRESPOSTA: {resposta[:1500]}"
                ),
            }],
            system_prompt="Você destila memórias duráveis. Seja rigoroso: na dúvida, NENHUM.",
            max_tokens=150, temperature=0.0,
        )
        texto = (r.content or "").strip()
        if not texto or texto.upper().startswith("NENHUM"):
            return
        for linha in [x.strip("-• ").strip() for x in texto.splitlines() if x.strip()][:2]:
            if len(linha) < 12 or linha.upper().startswith("NENHUM"):
                continue
            # dedup exato simples
            ja = (
                await db.execute(
                    text("SELECT 1 FROM consultor_memorias WHERE ativo AND conteudo = :c LIMIT 1"),
                    {"c": linha},
                )
            ).first()
            if ja:
                continue
            await db.execute(
                text(
                    "INSERT INTO consultor_memorias (origem, conteudo, fonte) "
                    "VALUES (:o, :c, :f)"
                ),
                {"o": origem, "c": linha, "f": f"P: {pergunta[:180]}"},
            )
        await db.commit()
        logger.info("Consultor %s aprendeu memória(s) nova(s)", origem)
    except Exception as e:  # noqa: BLE001
        logger.warning("aprender(%s): %s", origem, e)
