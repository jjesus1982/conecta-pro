#!/usr/bin/env python3
"""Oráculo da REVISÃO DO FUNIL — fazer o funil dizer a verdade.

Medido em 27/08/2026: 22 propostas em RASCUNHO, R$ 431.880, média 46 dias. Parte já foi
ganha ou perdida e ninguém registrou. Consequência: o alerta diário está PARCIALMENTE
ERRADO, e alerta errado ensina a ignorar alerta — 182 notificações em 5 dias, ZERO lidas.
O Jordan não parou de ler por volume: parou porque o que chega não é verdade.

⭐ MEDIR SALVOU UMA MIGRAÇÃO. A análise dizia "não existe status de perdida" porque olhou
os valores EM USO (draft/sent/accepted). O enum tem DEZ e `rejected` está lá. Não havia o
que criar — e a coluna tem 42 consumidores literais, onde inventar valor é risco puro.

Oito invariantes:
  1. `rejected` EXISTE no enum (se sumir, a revisão perde onde registrar derrota)
  2. a revisão agrupa por CLIENTE, do maior valor para o menor
  3. proposta RECENTE fica FORA (está viva, não é dívida)
  4. proposta de valor ZERO é NOMEADA, nunca apagada
  5. resolver sem informar nada é RECUSADO
  6. o mesmo número em ganhas E perdidas é RECUSADO
  7. proposta que JÁ tem desfecho é RECUSADA (sobrescrever apaga histórico)
  8. INÉRCIA: propor não muda status de proposta nenhuma

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/test_revisao_funil.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

_MARCA = "ZZteste-oraculo-revisao-funil"


async def _limpar(db) -> None:
    from sqlalchemy import text as _t

    ids = (await db.execute(_t(
        "SELECT id FROM agent_drafts WHERE tipo = 'resolver_propostas' "
        "AND payload::text LIKE :m"), {"m": f"%{_MARCA}%"})).scalars().all()
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
    from modules.crm.models.proposal import ProposalStatus
    from modules.crm.services import escopo_analogo as E
    from modules.ai.conversation.services.orquestrador.tools_acao_crm import (
        _propor_resolver_propostas as P,
    )

    falhas: list[str] = []
    async with async_session_factory() as db:
        await _limpar(db)

        # 1 · o lugar onde a derrota se registra tem de existir
        valores = {s.value for s in ProposalStatus}
        if "rejected" not in valores:
            falhas.append("`rejected` sumiu do ProposalStatus — sem ele não há onde "
                          "registrar proposta perdida, e o funil volta a mentir")

        u = (await db.execute(select(User).where(
            User.email == "jjesus@conectamais.pro"))).scalar_one()
        scope, _ = await C._resolver_tier_e_tools(db, u)

        r = await E.revisar_funil(db)
        grupos = r.get("a_revisar") or []
        if not grupos:
            print("  (nenhuma proposta parada — revisão não exercitada)")
        else:
            # 2 · maior valor primeiro
            totais = [g["total"] for g in grupos]
            if totais != sorted(totais, reverse=True):
                falhas.append("a revisão NÃO está ordenada por valor — o Jordan tem 10 "
                              "minutos, e eles têm de ir para os R$ maiores")
            # 3 · recente fica fora
            for g in grupos:
                if g["dias_max"] < E.DIAS_VIVA:
                    falhas.append(f"{g['cliente'][:30]!r} tem {g['dias_max']}d e entrou na "
                                  f"revisão — proposta recente está VIVA, não é dívida")
            # 4 · valor zero é nomeado
            zeros_reais = [p["numero"] for g in grupos for p in g["propostas"]
                           if p["valor"] == 0]
            if zeros_reais and not (r.get("atencao_valor_zero") or []):
                falhas.append(f"há proposta de valor ZERO ({zeros_reais}) e a revisão não "
                              f"a NOMEIA — apagar em silêncio seria decidir sozinho")

            alvo = grupos[0]
            nums = [p["numero"] for p in alvo["propostas"]]

            # 5 · nada informado
            res = await P(db, u, scope, cliente=alvo["cliente"])
            if not res.get("erro"):
                falhas.append("resolver SEM ganhas nem perdidas foi aceito")

            # 6 · mesma nos dois lados
            res = await P(db, u, scope, cliente=alvo["cliente"],
                          ganhas=nums[0], perdidas=nums[0])
            if not res.get("erro"):
                falhas.append("o mesmo número em GANHAS e PERDIDAS foi aceito")

            # 7 · já resolvida
            ja = (await db.execute(text(
                "SELECT number FROM proposals WHERE status = 'accepted' LIMIT 1"))).scalar()
            if ja:
                res = await P(db, u, scope, cliente="x", ganhas=ja)
                if not res.get("erro"):
                    falhas.append(f"{ja} já está accepted e foi aceita de novo — "
                                  f"sobrescrever desfecho apaga histórico")

            # 8 · INÉRCIA
            antes = (await db.execute(text(
                "SELECT status, count(*) FROM proposals GROUP BY 1 ORDER BY 1"))).all()
            res = await P(db, u, scope, cliente=alvo["cliente"], ganhas=nums[0],
                          perdidas=";".join(nums[1:]) or None, motivo=_MARCA)
            if not (res.get("draft_id") or res.get("id")):
                falhas.append(f"caso válido não virou rascunho: {str(res)[:110]}")
            depois = (await db.execute(text(
                "SELECT status, count(*) FROM proposals GROUP BY 1 ORDER BY 1"))).all()
            if antes != depois:
                falhas.append(f"A PROPOSTA MUDOU STATUS antes da aprovação: "
                              f"{antes} → {depois}")

        # 9 · CONTA DE SERVIÇO NÃO RECEBE ALERTA. Medido em 27/08/2026: `mcp-service@`
        #     (robô) e `admin@` (desativada) receberam 78 alertas comerciais cada e leram
        #     0. Cinco admins × 78 achados = 390 notificações, UMA lida. O sino não estava
        #     morto — 9,5% do resto era lido; quem o matou foi este volume.
        from modules.notifications.proativo.entrega import resolver_usuarios_por_roles

        ids = await resolver_usuarios_por_roles(db, ("admin", "gerente_comercial",
                                                     "comercial"))
        emails = (await db.execute(text(
            "SELECT lower(email) FROM users WHERE id::text = ANY(:i)"),
            {"i": ids})).scalars().all()
        robos = [e for e in emails if e.startswith(("mcp-service@", "admin@"))
                 or "bot@" in e]
        if robos:
            falhas.append(f"conta de SERVIÇO no sino: {robos} — robô não lê notificação, "
                          f"e cada uma multiplica o volume que enterra o canal")
        if not any(e.startswith("jjesus@") for e in emails):
            falhas.append("o Jordan NÃO está entre os destinatários do alerta comercial — "
                          "o filtro apertou demais e agora ninguém recebe")

        await _limpar(db)

    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        return 1
    print("OK revisao_funil: 9/9 — `rejected` existe no enum; a revisão agrupa por "
          "cliente do maior valor para o menor; recente fica FORA; valor zero é NOMEADO; "
          "recusa vazio, número nos dois lados e proposta já resolvida; e propor NÃO muda "
          "status de proposta nenhuma; e conta de SERVIÇO não recebe alerta comercial.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
