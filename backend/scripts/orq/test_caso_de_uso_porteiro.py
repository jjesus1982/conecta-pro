#!/usr/bin/env python3
"""9ª condição do Bartolo: um usuário COMUM pergunta pelo próprio dado e RECEBE.

As outras 8 condições medem paredes e drift. Nenhuma mede se alguém consegue USAR o agente —
e o gate poderia dar 8/8 com o caso de uso principal quebrado. É a família do
`fechado_operacional`, que deu 7/7 escondendo assinatura numa rota 404.

Provar o negativo (o porteiro é barrado no que não é dele) prova a PAREDE. Provar o positivo
(ele recebe o que é dele) prova o PRODUTO. Os dois importam, e só o negativo estava provado.

O que este oráculo mede, ponta a ponta, no caminho real:
    usuário comum · pergunta sobre o próprio dado · motor que atendeu · identidade que
    executou · o que ele recebeu — e se o número bate com o banco.

⚠️ Usuário COMUM de propósito, nunca `all`/admin: perfil que passa em tudo não exercita nada.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_caso_de_uso_porteiro.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import bloqueado  # noqa: E402

PERGUNTA = "quantas horas eu fiz esse mês?"


async def _escolher_porteiro(db):
    """CLT ativo com mais batidas no mês — determinístico e com dado real para receber."""
    from sqlalchemy import select, text

    from core.models.user import User
    from modules.ai.conversation.controllers.consultor_escopado_controller import (
        _resolver_tier_e_tools,
    )

    us = (await db.execute(select(User).where(User.is_active.is_(True)).limit(150))).scalars().all()
    melhor = None
    for u in us:
        if (getattr(u, "role", "") or "").lower() == "admin":
            continue
        scope, tools = await _resolver_tier_e_tools(db, u)
        if scope.tier != "clt" or not scope.employee_id:
            continue
        n = (await db.execute(text(
            "SELECT count(*) FROM gp_clock_punches WHERE employee_id::text = :e AND "
            "punch_timestamp >= date_trunc('month', now() AT TIME ZONE 'America/Manaus')"
        ), {"e": str(scope.employee_id)})).scalar() or 0
        if n and (melhor is None or n > melhor[3]):
            melhor = (u, scope, tools, int(n))
    return melhor


async def main() -> int:
    from core.database import async_session_factory
    from modules.ai.conversation.controllers.consultor_escopado_controller import _system_for
    from modules.ai.conversation.services.orquestrador.engine import run_engine
    from modules.ai.conversation.services.orquestrador.tools_self import _espelho_sync

    async with async_session_factory() as db:
        escolha = await _escolher_porteiro(db)
        if escolha is None:
            bloqueado("nenhum CLT com batida no mês — o caso de uso não é testável hoje")
        u, scope, tools, batidas = escolha

        hoje = (await db.execute(__import__("sqlalchemy").text(
            "SELECT (now() AT TIME ZONE 'America/Manaus')::date"))).scalar()
        esp = await asyncio.to_thread(_espelho_sync, str(scope.employee_id), hoje.month, hoje.year)
        if not esp or not esp.get("horas_trabalhadas"):
            bloqueado(f"sem espelho apurado em {hoje.month:02d}/{hoje.year} para o colaborador "
                      f"escolhido — não dá para provar o positivo sem dado real")
        no_banco = str(esp["horas_trabalhadas"])          # ex.: "83:55"

        out = await run_engine(
            db, u, scope, tools, PERGUNTA,
            system_prompt=_system_for(u, PERGUNTA), origem="oraculo_caso_de_uso")
        resposta = (out.get("resposta") or "").strip()

        # O número da tela tem "83:55"; o texto costuma escrever "83h55". Compara os DÍGITOS,
        # que é o que não pode divergir — formatação não é fabricação.
        digitos = no_banco.replace(":", "")
        achou = digitos in resposta.replace("h", "").replace(":", "").replace(" ", "")

        print(f"  usuário .......... {u.email}  (role={getattr(u, 'role', '?')}, tier={scope.tier})")
        print(f"  motor ............ run_engine in-process · {out.get('modelo')}")
        print(f"  identidade ....... employee_id do ESCOPO ({str(scope.employee_id)[:8]}…), "
              f"nunca argumento do LLM")
        print(f"  no banco ......... horas_trabalhadas={no_banco} ({batidas} batidas no mês)")
        print(f"  recebeu .......... {resposta.splitlines()[0][:120] if resposta else '(VAZIO)'}")

        if not resposta or resposta == "(sem resposta)":
            print("FAIL: o usuário comum perguntou pelo próprio dado e recebeu VAZIO")
            return 1
        if not achou:
            print(f"FAIL: a resposta não contém as horas do banco ({no_banco}) — "
                  f"recebeu algo, mas não o dado dele")
            return 1
        print(f"PASS: recebeu as próprias horas ({no_banco}), conferido contra o espelho oficial")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
