"""HUB dos Consultores IA (CFO, Jurídico, GED) — requisitos Jordan 2026-07-07.

1. MELHOR MODELO SEMPRE: cadeia gpt-5 → gpt-4.1 → gpt-4o → Claude.
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

# Cadeia de modelos: MELHOR primeiro (gpt-5 = cérebro escolhido pelo Jordan). Probe real
# 2026-07-25: `gpt-5-chat-latest` foi DEPRECIADO (404) — removido. `gpt-5` exige
# `max_completion_tokens` + temperature default (1); a adaptação está no OpenAIProvider
# (llm_provider._completion_params). gpt-4.1/gpt-4o ficam como fallback (contrato antigo).
MODEL_CHAIN = ["gpt-5", "gpt-4.1", "gpt-4o"]
# DECISÃO Jordan (2026-07-21): cérebro de raciocínio = OpenAI (MODEL_CHAIN acima); Anthropic
# NÃO é usada (conta sem crédito). CLAUDE_MODEL é só o modelo do fallback de emergência em gerar().
CLAUDE_MODEL = os.getenv("CONSULTOR_CLAUDE_MODEL", "claude-sonnet-4-6")

# Tabelas de consultas de cada consultor (p/ conversa cruzada entre os chats)
TABELAS_CONSULTAS = {
    "cfo": ("financial_cfo_consultas", "CFO (Financeiro)"),
    "juridico": ("juridico_consultas", "Consultor Jurídico"),
    "ged": ("gedeon_consultas", "Consultor GED"),
    "comercial": ("comercial_consultas", "CMO (Comercial)"),
    "operacional": ("operacional_consultas", "COO (Operacional)"),
    "rh": ("rh_consultas", "CHRO (Pessoas/DP)"),
    "fiscal": ("fiscal_consultas", "Consultor Fiscal"),
    "ceo": ("ceo_consultas", "CEO (Executivo)"),
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
                )
                """
            )
        )
        # asyncpg nao aceita multiplos comandos num prepared statement — indice a parte
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_consultor_memorias_origem "
                "ON consultor_memorias (origem, ativo)"
            )
        )
        await db.commit()
    # Fase 5.5 Task 1 — colunas de curadoria (aditivo/idempotente; espelha a
    # migration fase55_consultor_memorias_curadoria para instâncias onde o
    # DDL fallback acima criou a tabela sem elas, ou pra bancadas sem alembic).
    for ddl in (
        "ALTER TABLE consultor_memorias ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'pendente_revisao'",
        "ALTER TABLE consultor_memorias ADD COLUMN IF NOT EXISTS confidence real",
        "ALTER TABLE consultor_memorias ADD COLUMN IF NOT EXISTS autor text",
        "ALTER TABLE consultor_memorias ADD COLUMN IF NOT EXISTS curator_veredito jsonb",
        "ALTER TABLE consultor_memorias ADD COLUMN IF NOT EXISTS expira_em timestamptz",
    ):
        await db.execute(text(ddl))
    await db.commit()
    _ddl_ok = True


# ─────────────────────────────────────────────────────────────────────────────
# GERAÇÃO — melhor modelo sempre, com cadeia de fallback
# ─────────────────────────────────────────────────────────────────────────────
async def gerar(
    *, messages: list[dict], system_prompt: str, max_tokens: int = 2500, temperature: float = 0.2,
    origem: str | None = None, direct: bool = False, model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Gera com o melhor modelo disponível. Levanta RuntimeError se TODOS falharem.

    Fase 5.2a.2 — PONTE Hermes: quando `HERMES_BRIDGE_ENABLED=true` E `origem=="executivo"`
    (o orquestrador cross-domínio) E `direct is False`, roteia pro Hermes local primeiro.
    Os 8 consultores existentes (origem cfo/juridico/rh/etc., ou sem origem) NUNCA entram
    aqui — caminho intocado. `direct=True` é o guard de re-entrância: quando o próprio
    Hermes chama um tool `consultor_*` (que cai neste `gerar()` de novo), o call-site passa
    direct=True pra NUNCA re-rotear pro Hermes (evita loop infinito). Qualquer falha do
    Hermes (indisponível, timeout, formato inesperado) degrada silenciosamente pro caminho
    atual (MODEL_CHAIN) — nunca quebra o consultor.

    Fase 5.3 fast-follow — `model`: quando fornecido, a cadeia vira `[model]` (pula o
    MODEL_CHAIN e o override por env), preservando TODO o resto (fallback pro Claude em
    erro, tuple de retorno, a ponte Hermes). Serve ao redator utilitário, que precisa de
    um modelo rápido que RESPEITE temperature (gpt-4.1), não do gpt-5 reasoning (que roda
    temp=1 e derruba o groundedness). `model=None` (default) = comportamento atual.
    """
    if (
        os.getenv("HERMES_BRIDGE_ENABLED", "false").lower() == "true"
        and origem == "executivo" and not direct
    ):
        try:
            from modules.ai.conversation.services import hermes_client
            from modules.ai.conversation.services.garantia import observability, routing

            if await hermes_client.hermes_disponivel():
                # Fase 5.2a.3 — roteamento por custo (piso por tamanho + domínio
                # dinheiro/legal/C-level força a pesada) no lugar do "gpt-5" fixo,
                # e um span Sentry (gen_ai.hermes) em volta da chamada.
                modelo = routing.modelo_por_tier(origem, messages)
                with observability.llm_span("hermes", origem=origem, modelo=modelo):
                    return await hermes_client.perguntar_hermes(messages, system_prompt, model=modelo)
        except Exception:  # noqa: BLE001 — degradação graciosa → cai no caminho atual
            pass

    from modules.ai.conversation.services.llm_provider import ClaudeProvider, OpenAIProvider

    # DECISÃO Jordan (2026-07-21): o cérebro de RACIOCÍNIO usa OpenAI, NÃO Anthropic (a conta
    # Anthropic está sem crédito e não vamos usá-la). OpenAI é PRIMÁRIO; Claude fica só como
    # fallback de emergência (não dispara sem crédito). A SOBERANIA real não vem de trocar de
    # fornecedor externo (ambos são externos) — vem do modelo LOCAL de embeddings (Fase 2) e,
    # no futuro, do raciocínio local (Fase 5, exige GPU).
    if model:
        # Modelo explícito (ex.: redator utilitário → gpt-4.1): usa SÓ ele, ignora
        # MODEL_CHAIN e o override por env. Fallback pro Claude em erro continua valendo.
        chain = [model]
    else:
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
    # Fallback: Claude (com o modelo bom quando houver crédito).
    try:
        p = ClaudeProvider(model=CLAUDE_MODEL)
        if p.api_key:
            r = await p.generate(
                messages=messages, system_prompt=system_prompt,
                max_tokens=max_tokens, temperature=temperature,
            )
            texto = (r.content or "").strip()
            if texto:
                return texto, {"model": getattr(r, "model", CLAUDE_MODEL)}
    except Exception as e:  # noqa: BLE001
        erros.append(f"claude: {str(e)[:120]}")
    raise RuntimeError("; ".join(erros[-3:]))


# ─────────────────────────────────────────────────────────────────────────────
# MEMÓRIA COMPARTILHADA + CONVERSA CRUZADA
# ─────────────────────────────────────────────────────────────────────────────
async def contexto_compartilhado(
    db: AsyncSession, origem_atual: str, pergunta: str | None = None, *, max_memorias: int = 30
) -> str:
    """Bloco de prompt: memórias permanentes + consultas cruzadas + alertas do sino +
    (se a pergunta cita um cliente) o RETRATO CRUZADO desse cliente (Fase 2, grafo)."""
    await _ensure_schema(db)
    partes: list[str] = []

    rows = (
        await db.execute(
            text(
                "SELECT origem, conteudo FROM consultor_memorias "
                "WHERE status = 'ativo' AND (expira_em IS NULL OR expira_em > now()) "
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
            # asyncpg: query falha envenena a transação — rollback obrigatório
            await db.rollback()
            continue
    if cruzadas:
        partes.append("")
        partes.append("=== O QUE OS OUTROS CONSULTORES RESPONDERAM RECENTEMENTE (contexto cruzado) ===")
        partes.extend(cruzadas)

    # Fase 1 (ponte consultor→sino): o consultor passa a SABER dos alertas ativos que a
    # Fase 0 materializou (RiskMonitor, aging, documentos, SST). Antes não lia nenhum.
    try:
        alertas = (
            await db.execute(
                text(
                    "SELECT category, subject FROM notification_queue "
                    "WHERE coalesce(opened,false)=false AND correlation_id IS NOT NULL "
                    "AND (category LIKE 'risco_%' OR category LIKE 'financeiro_%' "
                    "OR category LIKE 'documento_%' OR category LIKE 'contrato_%' OR category = 'sst') "
                    "ORDER BY created_at DESC LIMIT 20"
                )
            )
        ).fetchall()
        if alertas:
            partes.append("")
            partes.append("=== ALERTAS ATIVOS DO SISTEMA (o sino — o que está acontecendo AGORA) ===")
            for a in alertas:
                partes.append(f"- [{a.category}] {a.subject}")
    except Exception:  # noqa: BLE001
        await db.rollback()

    # Fase 2 (grafo): se a pergunta menciona um cliente, injeta o RETRATO CRUZADO dele.
    # LGPD (auditoria 2026-07-21): SÓ no Consultor CEO (cross-módulo, já restrito à diretoria
    # jjesus+pjesus). Nos outros consultores o retrato cruzado (RH+financeiro+NF-e de um cliente)
    # quebraria finalidade (ex.: CMO veria roster de RH). Escopo por domínio virá com o plumbing
    # de current_user (Fase 1.D). Até lá, cross-entidade fica no consultor autorizado a ver tudo.
    if pergunta and origem_atual == "ceo":
        try:
            cli = await resolver_cliente(db, pergunta)
            if cli:
                ent = await contexto_entidade(db, cli["client_key"])
                if ent:
                    partes.append("")
                    partes.append(ent)
        except Exception:  # noqa: BLE001
            await db.rollback()

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
        await db.rollback()
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


# ─────────────────────────────────────────────────────────────────────────────
# FASE 4 — FEEDBACK HUMANO + PLACAR DE APRENDIZADO ("certificar que aprendem")
# ─────────────────────────────────────────────────────────────────────────────
async def registrar_feedback(
    db: AsyncSession, origem: str, consulta_id: int, util: bool, correcao: str | None = None
) -> dict:
    """Grava 👍/👎 (+ correção) numa consulta. A correção do gestor vira MEMÓRIA PERMANENTE
    (o consultor passa a respeitá-la) — é o aprendizado com feedback. Best-effort."""
    tabela, _ = TABELAS_CONSULTAS.get(origem, (None, None))
    if not tabela:
        return {"ok": False, "erro": "origem desconhecida"}
    try:
        await _ensure_schema(db)
        await db.execute(
            text(  # noqa: S608 — tabela de whitelist interna
                f"UPDATE {tabela} SET util=:u, correcao=:c, feedback_em=now() WHERE id=:id"
            ),
            {"u": util, "c": (correcao or None), "id": consulta_id},
        )
        # 👎 com correção → o gestor está ENSINANDO: grava como memória durável (fonte confiável).
        if correcao and correcao.strip():
            await db.execute(
                text(
                    "INSERT INTO consultor_memorias (origem, conteudo, fonte, ativo, created_at) "
                    "VALUES (:o, :c, 'feedback_gestor', true, now())"
                ),
                {"o": origem, "c": f"CORREÇÃO DO GESTOR: {correcao.strip()[:400]}"},
            )
        await db.commit()
        return {"ok": True, "virou_memoria": bool(correcao and correcao.strip())}
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        return {"ok": False, "erro": str(e)[:120]}


async def placar_aprendizado(db: AsyncSession) -> dict:
    """O PLACAR: prova que os consultores aprendem — taxa de 👍, feedback dado, memórias,
    correções que viraram conhecimento. Números, não promessa."""
    await _ensure_schema(db)
    por_origem = []
    tot = com_fb = uteis = 0
    for origem, (tabela, rotulo) in TABELAS_CONSULTAS.items():
        try:
            r = (
                await db.execute(
                    text(  # noqa: S608
                        f"SELECT count(*) t, count(*) FILTER (WHERE feedback_em IS NOT NULL) fb, "
                        f"count(*) FILTER (WHERE util) ok FROM {tabela}"
                    )
                )
            ).fetchone()
            t_, fb_, ok_ = int(r.t or 0), int(r.fb or 0), int(r.ok or 0)
            tot += t_; com_fb += fb_; uteis += ok_
            por_origem.append({"consultor": rotulo, "consultas": t_, "com_feedback": fb_, "uteis": ok_})
        except Exception:  # noqa: BLE001
            await db.rollback()
            continue
    mem = int((await db.execute(text("SELECT count(*) FROM consultor_memorias WHERE ativo"))).scalar() or 0)
    corr = int(
        (await db.execute(text("SELECT count(*) FROM consultor_memorias WHERE ativo AND fonte='feedback_gestor'"))).scalar()
        or 0
    )
    taxa = round(uteis / com_fb * 100) if com_fb else None
    return {
        "consultas_totais": tot,
        "com_feedback": com_fb,
        "taxa_util_pct": taxa,
        "memorias_ativas": mem,
        "correcoes_do_gestor": corr,
        "por_consultor": por_origem,
    }


# ─────────────────────────────────────────────────────────────────────────────
# FASE 2 — GRAFO POR ENTIDADE ("tudo se cruza"): navega dos IDs já resolvidos
# (views entity_client + entity_client_override) pelos domínios que LIGAM de fato.
# Honesto: aging→cliente e processo→cliente ficam quebrados na ORIGEM (recebível
# sem documento; processo sem link) — não fabricamos; mostramos o que conecta.
# ─────────────────────────────────────────────────────────────────────────────
async def resolver_cliente(db: AsyncSession, termo: str) -> dict | None:
    """Resolve um cliente a partir de um trecho (nome ou CNPJ) → client_key canônico."""
    if not termo or len(termo.strip()) < 3:
        return None
    try:
        # LGPD (auditoria 2026-07-21): casa SÓ por CNPJ no texto OU pelo NOME COMPLETO do cliente
        # (prefixo de condomínio removido) contido na pergunta. REMOVIDA a cláusula reversa
        # `name ILIKE '%termo%'`, que casava cliente errado em termo curto. E se >1 cliente casar
        # (ambiguidade real, ex. 'FLORES' → IDEAL FLORES vs MIRANTE DAS FLORES), NÃO resolve.
        rows = (
            await db.execute(
                text(
                    "SELECT id, name, document_number FROM clients "
                    "WHERE ativo IS NOT false AND ("
                    "  (length(regexp_replace(coalesce(document_number,''),'[^0-9]','','g'))=14 "
                    "   AND regexp_replace(:t,'[^0-9]','','g') LIKE '%' || regexp_replace(document_number,'[^0-9]','','g') || '%') "
                    "  OR (length(regexp_replace(name,'^(CONDOMINIO|COND|EDIFICIO|EDIF|RESIDENCIAL|RES|CONJUNTO)\\s+','','i'))>6 "
                    "      AND :t ILIKE '%' || regexp_replace(name,'^(CONDOMINIO|COND|EDIFICIO|EDIF|RESIDENCIAL|RES|CONJUNTO)\\s+','','i') || '%')) "
                    "ORDER BY length(name) DESC LIMIT 2"
                ),
                {"t": termo.strip()},
            )
        ).fetchall()
        if len(rows) != 1:  # 0 = ninguém; >1 = ambíguo → não injeta dado do cliente errado
            return None
        r = rows[0]
        return {"client_key": str(r.id), "name": r.name, "cnpj": r.document_number}
    except Exception:  # noqa: BLE001
        await db.rollback()
        return None


async def contexto_entidade(db: AsyncSession, client_key: str) -> str:
    """Bloco de prompt: retrato CRUZADO de um cliente (condomínios, equipe alocada,
    NF-e emitidas, alertas ancorados) pelos links que funcionam. Vazio-real = honesto."""
    partes: list[str] = []

    async def _q(sql, **kw):
        try:
            return (await db.execute(text(sql), {"ck": client_key, **kw})).fetchall()
        except Exception:  # noqa: BLE001
            await db.rollback()
            return []

    cab = await _q("SELECT name, document_number, coalesce(mrr,0) mrr, status::text st FROM clients WHERE id=CAST(:ck AS uuid)")
    if not cab:
        return ""
    c = cab[0]
    partes.append(f"=== RETRATO CRUZADO DO CLIENTE: {c.name} (CNPJ {c.document_number}) — MRR R$ {float(c.mrr):.2f} · {c.st} ===")

    conds = await _q("SELECT nome FROM condominios WHERE client_id=CAST(:ck AS uuid) LIMIT 20")
    if conds:
        partes.append("Condomínios/postos: " + ", ".join(x.nome for x in conds if x.nome))

    equipe = await _q(
        "SELECT e.nome, coalesce(e.cargo,'—') cargo FROM employee_alocacoes a "
        "JOIN condominios cd ON cd.id=a.condominio_id JOIN employees e ON e.id=a.employee_id "
        "WHERE cd.client_id=CAST(:ck AS uuid) AND coalesce(a.ativo,true) LIMIT 30"
    )
    if equipe:
        partes.append(f"Equipe alocada ({len(equipe)}): " + ", ".join(f"{x.nome} ({x.cargo})" for x in equipe[:12]))

    nfs = await _q(
        "SELECT count(*) q, coalesce(sum(n.valor_servicos),0) v FROM nfses n "
        "JOIN entity_client_override o ON o.satellite_type='nfse' AND o.satellite_id=n.id::text "
        "WHERE o.client_key=CAST(:ck AS uuid)"
    )
    if nfs and int(nfs[0].q or 0) > 0:
        partes.append(f"NF-e emitidas a este cliente: {int(nfs[0].q)} (R$ {float(nfs[0].v):.2f})")

    al = await _q(
        "SELECT category, subject FROM notification_queue WHERE source_entity_id=CAST(:ck AS uuid) "
        "AND coalesce(opened,false)=false ORDER BY created_at DESC LIMIT 10"
    )
    if al:
        partes.append("Alertas ativos deste cliente: " + "; ".join(f"[{x.category}] {x.subject}" for x in al))

    return "\n".join(partes)
