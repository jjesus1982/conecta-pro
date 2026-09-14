#!/usr/bin/env python3
"""Gente ativa que não bate ponto pelo Conecta PRO — desde 13/09 isso é gente SEM ponto.

Origem: em 13/09/2026 o Jordan desligou o pull de batidas do Sólides/Tangerino
(`solides-sync-punches` no beat), porque as batidas já vinham pelo app. Naquele dia 44
das 51 pessoas com movimento em setembro já batiam pelo Conecta PRO — e **7 não**:

    nunca usaram o app: ALAN VIEIRA, THIAGO MAQUINE, KELLY PATRICIA, EIDY CULIER
    usavam e pararam:   EULER FELIPE (17/08), JONILSON MARTINS (21/08), GEILSON (11/08)

Até então essas 7 apareciam no espelho porque o Tangerino as trazia. Com o pull
desligado, elas não somem da folha: somem do PONTO. Ninguém percebe — o espelho fica
vazio e vazio parece "mês limpo".

Duas perguntas diferentes, e o caçador separa porque a ação é diferente:
  • quem NUNCA usou o app precisa de instalação (e dois deles nem telefone têm);
  • quem USAVA e PAROU é sintoma — o app quebrou para aquela pessoa, ou ela voltou ao
    relógio por hábito. Essa segunda família é a que costuma indicar defeito.

    docker exec -e PYTHONPATH=/app conecta-pro-backend \
        python3 /app/scripts/qa/checar_pessoa_fora_do_app_de_ponto.py

Linha canônica: `TOTAL: <n> pessoa(s) sem ponto pelo Conecta PRO`. Exit 1 se houver.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from modules.people_management.ponto.coorte_ponto import SQL_NAO_AUSENTE_HOJE

#: O que conta como batida MEDIDA pelo Conecta PRO. 'tangerino' e 'web' ficam de fora de
#: propósito — a mesma separação que o painel de ponto ao vivo já usa.
FONTES_CONECTA = ("mobile", "contingencia", "facial", "biometria", "app")


async def main() -> int:
    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415

    if not Path("/app/scripts").is_dir():
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    lista = "(" + ",".join(f"'{f}'" for f in FONTES_CONECTA) + ")"
    async with async_session_factory() as db:
        linhas = (
            await db.execute(
                text(
                    "SELECT e.nome, coalesce(e.cargo,'—'), coalesce(c.nome,'(sem posto)'), "
                    "       coalesce(nullif(trim(e.telefone),''), '(sem telefone)'), "
                    "       (SELECT max(g.punch_timestamp)::date FROM gp_clock_punches g "
                    f"        WHERE g.employee_id = e.id AND g.device_type IN {lista}) AS ultima_no_app, "
                    "       (SELECT max(g.punch_timestamp)::date FROM gp_clock_punches g "
                    "        WHERE g.employee_id = e.id) AS ultima_qualquer "
                    "FROM employees e "
                    "LEFT JOIN employee_alocacoes a ON a.employee_id = e.id AND a.ativo = true "
                    "LEFT JOIN condominios c ON c.id = a.condominio_id "
                    "WHERE e.status = 'ativo' "
                    "  AND coalesce(e.is_homologacao, false) = false "
                    "  AND coalesce(e.tipo_contrato, 'clt') <> 'pj' "
                    # Férias, afastamento e reta final de desligamento: a MESMA regra do
                    # painel e do lembrete, por data e nunca por marcação manual. Sem ela o
                    # caçador cobraria ponto de quem não deve ponto — o Geilson está
                    # afastado e aparecia aqui como "parou de usar o app".
                    + SQL_NAO_AUSENTE_HOJE +
                    # Só quem teve movimento no mês: admitido ontem ainda não devia ponto.
                    "  AND EXISTS (SELECT 1 FROM gp_clock_punches g WHERE g.employee_id = e.id "
                    "              AND g.punch_timestamp >= date_trunc('month', CURRENT_DATE)) "
                    "  AND NOT EXISTS (SELECT 1 FROM gp_clock_punches g WHERE g.employee_id = e.id "
                    f"                 AND g.device_type IN {lista} "
                    "                 AND g.punch_timestamp >= date_trunc('month', CURRENT_DATE)) "
                    "ORDER BY e.nome"
                )
            )
        ).all()

    nunca, pararam = [], []
    for nome, cargo, posto, fone, no_app, qualquer in linhas:
        (pararam if no_app else nunca).append((nome, cargo, posto, fone, no_app, qualquer))

    if nunca:
        print("   NUNCA usaram o app — precisa instalar:")
        for nome, cargo, posto, fone, _, qualquer in nunca:
            print(f"      {nome} — {cargo} · {posto} · {fone}")
            print(f"         última batida (qualquer fonte): {qualquer or 'nenhuma'}")
    if pararam:
        print("\n   USAVAM e PARARAM — isto costuma ser defeito, não hábito:")
        for nome, cargo, posto, fone, no_app, qualquer in pararam:
            print(f"      {nome} — {cargo} · {posto} · {fone}")
            print(f"         última no app: {no_app} · última em qualquer fonte: {qualquer}")

    print(f"\nTOTAL: {len(linhas)} pessoa(s) sem ponto pelo Conecta PRO")
    return 1 if linhas else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
