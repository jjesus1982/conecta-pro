#!/usr/bin/env python3
"""Pedido de férias nasce em UMA tabela só: `hr_vacation_requests`.

TRÊS TABELAS GUARDAM PEDIDO DE FÉRIAS, e medi as três em 13/08/2026:

    hr_vacation_requests         19 linhas · última 16/07 · APROVA/REJEITA/CANCELA
    employee_vacation_requests   15 linhas · última 01/04 · 14 presas em SUBMITTED
    vacation_requests            10 linhas · última 01/04 ·  9 presas em 'pendente'

(o briefing dizia `vacation_requests` = 0; são 10.)

`hr_vacation_requests` é a AUTORITATIVA: é a maior, a mais recente, a única com ciclo
completo (4 APPROVED, 1 CANCELLED) e é onde a tela do DP aprova.

E É AQUI QUE MORA O DEFEITO QUE ESTE ORÁCULO VIGIA. A tela do DP **cria** o pedido em
`employee_vacation_requests` (`/redesign/action/vacation-request` →
`hr/employee_portal/services/vacation_service`) e **aprova** em `hr_vacation_requests`
(`/redesign/action/ferias-aprovar` → `people_management/hr/vacation_controller`). O pedido
que a tela cria nunca pode ser aprovado pela tela. Não é hipótese: são 14 pedidos parados
em SUBMITTED desde 01/04 de um lado, enquanto o outro seguiu até julho.

CORTE DE DÍVIDA, e é deliberado. Os 25 pedidos antigos fora da autoritativa NÃO reprovam:
eles já existem, e um vermelho que ninguém consegue calar é um vermelho que todo mundo
aprende a ignorar. O oráculo reprova por pedido NOVO — nascido depois do corte — fora da
autoritativa. É o mesmo princípio da linha de base do `checar_regressao`: dívida velha não
vira ruído, defeito novo acusa.

Receita:
  docker exec -e PYTHONPATH=/app conecta-pro-backend \\
    python3 /app/scripts/orq/test_oraculo_ferias_autoritativa.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402

AUTORITATIVA = "hr_vacation_requests"

#: Dia em que a autoritativa foi declarada. Não é fotografia de dado: é a fronteira entre
#: "dívida que já existia" e "defeito novo", declarada uma vez e nunca reajustada. Mover
#: esta data para frente para calar um vermelho é apagar o achado, não resolvê-lo.
CORTE = date(2026, 8, 13)

#: As outras duas, com o motivo de cada uma continuar de pé.
CONCORRENTES = {
    "employee_vacation_requests": (
        "hr/employee_portal — o controller dela NÃO está montado (0 rotas em /api/v1/hr/), "
        "mas a ação da tela do DP ainda escreve nela pelo service"
    ),
    "vacation_requests": (
        "operacional/vacations — módulo curado à mão pelo Jordan, read-only para agentes; "
        "divergência aqui vira relatório, não correção"
    ),
}


async def conferir(db) -> list[str]:
    """As falhas, na sessão que quem chama abrir — vazia quer dizer verde.

    Recebe a sessão para que a prova do vermelho (inserir um pedido fora da autoritativa e
    descartar a transação) exercite ESTE código, e não uma cópia dele.
    """
    falhas: list[str] = []

    total_aut = (await db.execute(text(
        f"SELECT count(*) FROM {AUTORITATIVA}"  # noqa: S608 — nome fixo, não vem de fora
    ))).scalar()
    print(f"autoritativa {AUTORITATIVA}: {total_aut} pedido(s)")

    for tabela, motivo in CONCORRENTES.items():
        velhos = (await db.execute(text(
            f"SELECT count(*) FROM {tabela} WHERE created_at::date < :corte"  # noqa: S608
        ), {"corte": CORTE})).scalar()
        novos = (await db.execute(text(
            f"SELECT count(*) FROM {tabela} WHERE created_at::date >= :corte"  # noqa: S608
        ), {"corte": CORTE})).scalar()

        print(f"  {tabela}: {velhos} anterior(es) ao corte · {novos} novo(s)")
        print(f"      {motivo}")
        if novos:
            falhas.append(
                f"{novos} pedido(s) de férias nasceram em `{tabela}` depois de "
                f"{CORTE.isoformat()} — a autoritativa é `{AUTORITATIVA}`"
            )

    # Suspensório: o sintoma que denunciou o defeito foi pedido que entra e não sai.
    # Se voltar a crescer, é a tela criando onde não consegue aprovar.
    presos = (await db.execute(text(
        "SELECT count(*) FROM employee_vacation_requests "
        "WHERE upper(coalesce(status,'')) = 'SUBMITTED'"
    ))).scalar()
    print(f"  pedidos presos em SUBMITTED na employee_vacation_requests: {presos}")
    print("      (a tela do DP CRIA aqui e APROVA na autoritativa — quem entra não sai)")

    return falhas


async def main() -> int:
    async with async_session_factory() as db:
        falhas = await conferir(db)

    if falhas:
        for f in falhas:
            print(f"FALHA: {f}")
        print("TEST oraculo_ferias_autoritativa FAIL")
        return 1
    print(f"\nDÍVIDA DECLARADA, não reprovada: os pedidos anteriores a "
          f"{CORTE.isoformat()} seguem fora da autoritativa. Enquanto "
          f"`/redesign/action/vacation-request` gravar em `employee_vacation_requests`, "
          f"o próximo pedido feito pela tela reprova este oráculo — que é exatamente o "
          f"aviso que ele existe para dar.")
    print("TEST oraculo_ferias_autoritativa PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
