"""Oráculo — gente de HOMOLOGAÇÃO não recebe mensagem de verdade (11/09/2026).

Origem: os 12 funcionários de teste (criados em 01/08, `is_homologacao = true`) têm telefone
sequencial de fachada — 92 99999-0001 a 0012. Esses números EXISTEM e são de gente real. Em
10/09 às 13:00 o dono do 92 99999-0003 recebeu

    "Olá, Rafael! Aqui é a Conecta Mais. Você tem 12 documento(s) ... para assinar"

e respondeu "Vc se enganou de numero". Oito mensagens já tinham saído assim, e havia 136
pedidos de assinatura pendentes desses 12 contra 3 de gente real — a rodada seguinte avisaria
doze estranhos, cada um com o nome de um funcionário e a lista de documentos dele.

A REGRA afirmada aqui não é "o filtro existe no arquivo X": é que **a audiência calculada por
cada disparador não contém ninguém de homologação**. Vale para quem chegar depois — um
disparador novo que esqueça o filtro cai aqui, mesmo sem ninguém lembrar desta história.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import asyncio
import sys


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db
    from modules.operacional.lembrete_ponto import SQL_PENDENTES as SQL_PONTO
    from modules.signatures.services.aviso_assinatura_service import _SQL_PENDENTES as SQL_ASSINATURA
    from modules.signatures.services.aviso_assinatura_service import _TITULO_LEMBRETE

    falhas: list[str] = []
    gen = get_db()
    db = await gen.__anext__()

    homologacao = {r[0] for r in (await db.execute(text(
        "SELECT id::text FROM employees WHERE coalesce(is_homologacao, false)"))).fetchall()}
    if not homologacao:
        print("nenhum funcionário de homologação no banco — nada a vigiar (isto não é falha)")
        return 0

    # 1) aviso de assinatura (e-mail + WhatsApp). Janela de reenvio neutralizada de propósito:
    #    quem manda em quem recebe é o FILTRO, não o fato de já ter sido avisado ontem.
    alvo = (await db.execute(SQL_ASSINATURA,
                             {"titulo_lembrete": _TITULO_LEMBRETE, "janela": 0})).mappings().all()
    for r in alvo:
        if r["eid"] in homologacao:
            falhas.append(f"aviso de assinatura alcançaria {r['nome']} (homologação) "
                          f"em {r['fone'] or r['email']}")

    # 2) lembrete de ponto por WhatsApp, nas três etapas
    for etapa in (-15, 0, 10):
        for r in (await db.execute(text(SQL_PONTO), {"etapa": etapa})).mappings().all():
            if r["employee_id"] in homologacao:
                falhas.append(f"lembrete de ponto (etapa {etapa}) alcançaria {r['nome']} "
                              f"(homologação) em {r['telefone']}")

    print(f"funcionários de homologação: {len(homologacao)} · audiência do aviso de assinatura agora: {len(alvo)}")
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} disparo(s) de mensagem real para gente de teste")
    print("OK: nenhum disparador alcança a coorte de homologação")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
