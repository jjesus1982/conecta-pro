#!/usr/bin/env python3
"""Holerite de competência que ainda não aconteceu — e holerite sem origem declarada.

Origem (13/09/2026): 94 holerites de NOVEMBRO e DEZEMBRO/2026 criados de uma vez em
03/08/2026, todos rascunho, R$ 66.274,80 somados. Ninguém os abriu, ninguém os baixou,
nenhum pagamento ligado — mas eles entravam na tela DP → Folha: Conecta × Portte, que é
justamente onde o Jordan confere a nossa folha contra a do escritório. A tela abria em
dezembro (a competência mais recente que existia) e comparava o nada com o nada.

Duas famílias, uma pergunta cada:

  1. **Competência futura.** Holerite do mês que ainda não terminou é rascunho legítimo:
     é assim que a folha fecha. Holerite de mês que nem começou não tem origem possível —
     não há ponto, não há escala, não há dia trabalhado para calcular.

  2. **Sem `source_system`.** A tela compara 'conecta' com 'portte'. Linha sem origem não
     entra em lado nenhum da comparação: existe, soma no banco e some do confronto.
     Havia 12 assim em 08/2026, R$ 17.397,33.

    docker exec -e PYTHONPATH=/app conecta-pro-backend \
        python3 /app/scripts/qa/checar_holerite_de_mes_futuro.py

Linha canônica: `TOTAL: <n> holerite(s) impossível(eis)`. Exit 1 quando há achado.
"""
from __future__ import annotations

import asyncio
from pathlib import Path


async def main() -> int:
    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415

    if not Path("/app/scripts").is_dir():
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    async with async_session_factory() as db:
        # Competência POSTERIOR ao mês corrente. O mês corrente fica de fora de propósito:
        # é nele que a folha é montada antes de fechar.
        futuros = (
            await db.execute(
                text(
                    "SELECT h.reference_period, coalesce(h.source_system,'(sem origem)'), "
                    "       count(*), round(sum(coalesce(h.net_salary,0))::numeric,2), "
                    "       min(h.created_at)::date "
                    "FROM hr_payslips h "
                    "WHERE NOT EXISTS (SELECT 1 FROM employees e WHERE e.id = h.employee_id "
                    "                  AND coalesce(e.is_homologacao, false) = true) "
                    "  AND (h.reference_year * 100 + h.reference_month) > "
                    "      (date_part('year', CURRENT_DATE) * 100 + date_part('month', CURRENT_DATE)) "
                    "GROUP BY 1, 2 ORDER BY 1"
                )
            )
        ).all()

        sem_origem = (
            await db.execute(
                text(
                    "SELECT h.reference_period, count(*), round(sum(coalesce(h.net_salary,0))::numeric,2) "
                    "FROM hr_payslips h "
                    "WHERE coalesce(nullif(trim(h.source_system),''), '') = '' "
                    "  AND NOT EXISTS (SELECT 1 FROM employees e WHERE e.id = h.employee_id "
                    "                  AND coalesce(e.is_homologacao, false) = true) "
                    "GROUP BY 1 ORDER BY 1"
                )
            )
        ).all()

    total = 0
    for periodo, origem, n, liq, criado in futuros:
        total += n
        print(f"   {periodo}  {n:3} holerite(s)  R$ {liq}  origem '{origem}'  criados em {criado}")
        print("      competência que ainda não começou: não há ponto nem escala que os explique")
    for periodo, n, liq in sem_origem:
        total += n
        print(f"   {periodo}  {n:3} holerite(s)  R$ {liq}  SEM source_system")
        print("      não entra em nenhum lado da tela Conecta × Portte — some do confronto")

    print(f"\nTOTAL: {total} holerite(s) impossível(eis)")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
