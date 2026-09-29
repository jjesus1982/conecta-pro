"""Relatório do roster de kit por condomínio. READ-ONLY — não escreve nada.

    python3 roster_kit_agosto_por_condominio.py            # competência = mês anterior
    python3 roster_kit_agosto_por_condominio.py 08/2026    # competência explícita

⭐ 29/09/2026 — A REGRA NÃO MORA MAIS AQUI. Este arquivo era a fonte e virou só a VISTA: a lógica
está em `modules/people_management/ged/services/kit_roster_service.py`, que serve também a tela
«Conferir kits do mês» da Pyetra.

POR QUÊ: a regra mudou **três vezes em 28/09** — alocação → escala → posto da batida — cada vez
por uma correção do Jordan. Com duas cópias, a tela e este relatório teriam divergido na primeira
mudança, e o número que ele lê no terminal deixaria de descrever o que a tela dela faz.

O serviço documenta o que este arquivo não repete: por que `employee_alocacoes` não serve como
histórico (as datas são ficção), por que `shifts` perde gente em silêncio, e por que o «Conecta
Village» fica fora (é posto nosso, não de cliente).
"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402
from modules.people_management.ged.services.kit_roster_service import (  # noqa: E402
    FONTES_MEDIDAS,
    _bounds,
    condominios_conhecidos,
    resolucao_humana,
    roster,
    sem_condominio,
)


def _competencia_do_argv() -> date:
    """MM/AAAA ou MM.AAAA no argv; sem argumento, o mês ANTERIOR.

    O padrão é o mês anterior porque é o kit que se entrega AGORA — salário em arrears. Era o
    default que o Gedeon já usava (`_competencia_anterior`) e que as telas não ofereciam.
    """
    if len(sys.argv) > 1:
        mes, ano = (int(x) for x in sys.argv[1].replace(".", "/").split("/", 1))
        return date(ano, mes, 1)
    return (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)


def main() -> None:
    comp = _competencia_do_argv()
    with get_sync_db() as db:
        por_cond, nomes, _motivo = roster(db, comp)
        manual = resolucao_humana(db, comp)
        pendentes = sem_condominio(db, comp)
        conds = condominios_conhecidos(db, comp)
        ini, fim = _bounds(comp)
        med = db.execute(
            text(
                "SELECT count(*) AS total, "
                "  count(*) FILTER (WHERE lower(coalesce(device_type,'')) = ANY(:fontes)) AS medida "
                "  FROM gp_clock_punches WHERE punch_timestamp >= :i AND punch_timestamp < :f"
            ),
            {"i": ini, "f": fim, "fontes": list(FONTES_MEDIDAS)},
        ).mappings().first()

    total = len({e for v in por_cond.values() for e in v})
    print(f"KIT DE {comp:%m/%Y} · {len(por_cond)} condomínio(s) · {total} pessoa(s)\n")
    for cond in sorted(por_cond, key=lambda x: (-len(por_cond[x]), x)):
        print(f"  {cond:<36} {len(por_cond[cond]):>3}")

    print(f"\nResolvidos por humano (o dado não tinha posto): {len(manual)}")
    for eid, (cond, quem) in manual.items():
        print(f"  + {nomes.get(eid, eid)} → {cond}   [{quem}]")

    if pendentes:
        print(f"\n⚠️ SEM CONDOMÍNIO ({len(pendentes)}) — a tela «Definir condomínio de quem ficou sem» resolve:")
        for _eid, (nome, q) in sorted(pendentes.items(), key=lambda x: -x[1][1]):
            print(f"  ? {nome} — {q} batida(s) no mês, nenhuma gravou o posto")
    else:
        print("\nOK ninguém ficou sem condomínio.")

    print(f"\nCondomínios com batida nesta competência ({len(conds)}): {', '.join(conds) or '(nenhum)'}")
    pct = 100.0 * (med["medida"] or 0) / (med["total"] or 1)
    print(
        f"\n⚠️ {med['medida']} de {med['total']} batidas da competência são MEDIÇÃO ({pct:.0f}%). "
        "O resto é grade de escala (Tangerino/web) e o espelho corretamente não conta — a folha "
        "de ponto do kit mostra os dias medidos e rotula os outros «sem registro eletrônico», com "
        "o horário da escala ao lado como referência."
    )


if __name__ == "__main__":
    main()
