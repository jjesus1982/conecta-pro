#!/usr/bin/env python3
"""Oráculo do que SAI DA EMPRESA — proposta por WhatsApp e cadastro de número.

10 propostas estavam sem resposta há 64 dias, todas enviadas por e-mail. WhatsApp é onde
o cliente responde.

⭐ O que este oráculo protege: envio é IRREVERSÍVEL e EXTERNO. Depois que a mensagem sai,
não há desfazer. Por isso o rascunho tem de NOMEAR O DESTINATÁRIO no resumo — quem aprova
precisa ver para quem vai antes de clicar — e a proposta precisa EXISTIR de verdade.

Cinco invariantes:
  1. proposta inexistente é RECUSADA
  2. cliente sem WhatsApp cadastrado é RECUSADO (não inventa número)
  3. o resumo do rascunho NOMEIA o destinatário
  4. INÉRCIA: propor NÃO envia (nada em crm_followups muda)
  5. número inválido no cadastro é RECUSADO

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/test_acao_envio_cliente.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

_MARCA = "ZZteste-oraculo-envio"


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
    from modules.ai.conversation.services.orquestrador.agir_dispatcher import _ACOES
    from modules.ai.conversation.services.orquestrador.tools_acao_crm import (
        _propor_cadastrar_whatsapp as CAD,
        _propor_enviar_proposta_whatsapp as ENV,
    )

    falhas: list[str] = []
    async with async_session_factory() as db:
        await _limpar(db)

        for nome in ("enviar_proposta_whatsapp", "cadastrar_whatsapp"):
            if nome not in _ACOES.get("crm", {}):
                falhas.append(f"{nome} não está registrada em agir_crm")
        if falhas:
            for f in falhas:
                print(f"FALHOU: {f}")
            return 1

        u = (await db.execute(select(User).where(
            User.email == "jjesus@conectamais.pro"))).scalar_one()
        scope, _ = await C._resolver_tier_e_tools(db, u)

        # 1 · proposta inexistente
        r = await ENV(db, u, scope, proposta="PROP-ZZ-NAO-EXISTE")
        if not r.get("erro"):
            falhas.append("proposta inexistente foi aceita para envio")

        # 4 · inércia: contar follow-ups antes e depois
        n0 = (await db.execute(text("SELECT count(*) FROM crm_followups"))).scalar()

        prop = (await db.execute(text(
            "SELECT number FROM proposals ORDER BY created_at DESC LIMIT 1"))).scalar()
        if prop:
            r = await ENV(db, u, scope, proposta=prop)
            # 2 e 3: ou recusa por falta de número, ou nomeia o destinatário
            if r.get("erro"):
                if "whatsapp" not in str(r["erro"]).lower():
                    falhas.append(f"recusa sem explicar a falta de WhatsApp: {r['erro'][:80]}")
            else:
                d = (await db.execute(text(
                    "SELECT resumo, payload->>'numero' AS numero FROM agent_drafts "
                    "WHERE tipo = 'enviar_proposta_whatsapp' "
                    "ORDER BY created_at DESC LIMIT 1"))).mappings().first() or {}
                # ⚠️ "tem algum dígito" NÃO serve como prova: o valor em R$ já tem
                # dígitos, e a 1ª versão deste teste passava com o resumo sem telefone
                # nenhum. O invariante é o NÚMERO DE DESTINO aparecer no texto que quem
                # aprova lê.
                numero = str(d.get("numero") or "")
                if not numero.strip():
                    falhas.append("rascunho criado SEM número de destino no payload")
                elif numero not in str(d.get("resumo") or ""):
                    falhas.append(f"o resumo NÃO mostra o número de destino {numero!r} — "
                                  f"quem aprova não vê para quem vai")

        n1 = (await db.execute(text("SELECT count(*) FROM crm_followups"))).scalar()
        if n0 != n1:
            falhas.append(f"PROPOR JÁ ENVIOU: crm_followups {n0} → {n1}")

        # 5 · número inválido
        cli = (await db.execute(text("SELECT name FROM clients LIMIT 1"))).scalar()
        r = await CAD(db, u, scope, cliente=cli, numero="123")
        if not r.get("erro"):
            falhas.append("número inválido foi aceito no cadastro de WhatsApp")

        await _limpar(db)

    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        return 1
    print("OK acao_envio_cliente: 5/5 — recusa proposta inexistente e número inválido; "
          "o rascunho NOMEIA o destinatário; e propor NÃO envia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
