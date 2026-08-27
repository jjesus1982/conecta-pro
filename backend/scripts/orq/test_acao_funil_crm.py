#!/usr/bin/env python3
"""Oráculo das ações de FUNIL — mover estágio de deal.

46 deals estavam parados em `proposal` há 24 dias (R$ 596.881) porque o Bartolo lia o
funil e não o movia: só sabia `marcar_deal_perdido`.

⭐ O que este oráculo protege: mover para `closed_won` é FECHAR VENDA — vira MRR e
contrato. Isso não pode acontecer por uma frase no chat. As demais etapas são
movimentação de funil e cabem em propor→aprovar.

Quatro invariantes:
  1. deal inexistente é RECUSADO
  2. estágio inválido é RECUSADO (o LLM inventa nome de estágio)
  3. `closed_won` é RECUSADO nesta ação (fechar tem porta própria, com decisão do dono)
  4. INÉRCIA: o caso válido vira rascunho e o `stage` do deal NÃO muda

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/test_acao_funil_crm.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

_MARCA = "ZZteste-oraculo-funil"


async def _limpar(db) -> None:
    from sqlalchemy import text as _t

    ids = (await db.execute(_t(
        "SELECT id FROM agent_drafts WHERE payload::text LIKE :m"),
        {"m": f"%{_MARCA}%"})).scalars().all()
    if ids:
        await db.execute(_t(
            "DELETE FROM communication_notifications WHERE reference_id::text = ANY(:i)"),
            {"i": [str(x) for x in ids]})
        await db.execute(_t("DELETE FROM agent_drafts WHERE id = ANY(:i)"), {"i": ids})
    await db.commit()


async def main() -> int:
    from sqlalchemy import select, text

    from core.database import async_session_factory
    from core.models.user import User
    import modules.ai.conversation.controllers.consultor_escopado_controller as C
    from modules.ai.conversation.controllers.agente_aprovacao_controller import grau_de
    from modules.ai.conversation.services.orquestrador.agir_dispatcher import _ACOES
    from modules.ai.conversation.services.orquestrador.tools_acao_crm import (
        _propor_mover_estagio_deal as P,
    )

    falhas: list[str] = []
    async with async_session_factory() as db:
        await _limpar(db)

        if "mover_estagio_deal" not in _ACOES.get("crm", {}):
            print("FALHOU: `mover_estagio_deal` não está registrada em agir_crm")
            return 1
        if grau_de("mover_estagio_deal")[0] not in ("🟡", "🔴"):
            falhas.append("grau 🔵 — mover deal muda previsão de receita")

        u = (await db.execute(select(User).where(
            User.email == "jjesus@conectamais.pro"))).scalar_one()
        scope, _ = await C._resolver_tier_e_tools(db, u)

        deal = (await db.execute(text(
            "SELECT title, stage::text FROM opportunities "
            "WHERE stage::text NOT IN ('closed_won', 'closed_lost') LIMIT 1"))).first()
        if not deal:
            print("FALHOU (pré-condição): nenhum deal aberto na base")
            return 1
        titulo, estagio_antes = deal[0], deal[1]

        r = await P(db, u, scope, deal="ZZ_NAO_EXISTE", estagio="negotiation")
        if not r.get("erro"):
            falhas.append("deal inexistente foi aceito")

        r = await P(db, u, scope, deal=titulo, estagio="estagio_inventado")
        if not r.get("erro"):
            falhas.append("estágio inválido foi aceito")

        r = await P(db, u, scope, deal=titulo, estagio="closed_won")
        if not r.get("erro"):
            falhas.append("closed_won foi aceito — FECHAR VENDA não passa por aqui")

        # ⚠️ O estágio ALVO tem de ser diferente do atual: a ação recusa "mover para onde
        # já está", e a 1ª versão deste oráculo sorteava um deal que já estava em
        # `negotiation` — reprovava o código por defeito do teste.
        destino = "qualification" if estagio_antes == "negotiation" else "negotiation"
        r = await P(db, u, scope, deal=titulo, estagio=destino, motivo=_MARCA)
        if not (r.get("draft_id") or r.get("id")):
            falhas.append(f"caso válido não virou rascunho: {str(r)[:110]}")
        depois = (await db.execute(text(
            "SELECT stage::text FROM opportunities WHERE title = :t"),
            {"t": titulo})).scalar()
        if depois != estagio_antes:
            falhas.append(f"A PROPOSTA MOVEU o deal: {estagio_antes!r} → {depois!r}")

        # ── FOLLOW-UP EM LOTE: a ação de maior alcance do plano ──────────────────────
        from modules.ai.conversation.services.orquestrador.tools_acao_crm import (
            _propor_followup_em_lote as LOTE,
        )

        r = await LOTE(db, u, scope)
        if not r.get("erro"):
            falhas.append("follow-up em lote SEM MENSAGEM foi aceito — sairia texto "
                          "vazio para dezenas de clientes")

        n0 = (await db.execute(text("SELECT count(*) FROM crm_followups"))).scalar()
        r = await LOTE(db, u, scope, mensagem=f"{_MARCA} toque de teste")
        if not (r.get("draft_id") or r.get("id")):
            falhas.append(f"lote válido não virou rascunho: {str(r)[:110]}")
        else:
            d = (await db.execute(text(
                "SELECT resumo FROM agent_drafts WHERE tipo = 'followup_em_lote' "
                "ORDER BY created_at DESC LIMIT 1"))).scalar() or ""
            if not any(ch.isdigit() for ch in d):
                falhas.append("o resumo do lote não diz QUANTOS clientes serão tocados — "
                              "quem aprova não sabe o alcance")
        n1 = (await db.execute(text("SELECT count(*) FROM crm_followups"))).scalar()
        if n0 != n1:
            falhas.append(f"PROPOR JÁ DISPAROU o lote: crm_followups {n0} → {n1}")

        await _limpar(db)

    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        return 1
    print("OK acao_funil_crm: 7/7 — recusa deal inexistente, estágio inválido e "
          "closed_won; recusa lote sem mensagem; o resumo do lote diz QUANTOS clientes "
          "serão tocados; e nem mover nem disparar acontece antes da aprovação.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
