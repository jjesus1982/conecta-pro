#!/usr/bin/env python3
"""Sincroniza `employees.recebe_intrajornada` com o que o CONTRACHEQUE pagou.

A REGRA, dita pelo Jordan em 14/08/2026:

    recebe o adicional de intrajornada no contracheque  →  NÃO faz a pausa  →  2 batidas
    NÃO recebe o adicional                              →  almoça uma hora  →  4 batidas

Quem decide não é o cadastro nem o posto: é a FOLHA. O adicional de intrajornada é dinheiro
pago, registrado em `folha_verba_espelho` sob os códigos **0030** (Intrajornada Diurno) e
**0031** (Intrajornada Noturna). Se a empresa pagou, a pessoa não faz a pausa — e o ponto
dela tem 2 batidas, não 4.

POR QUE ISTO EXISTE. Até 13/08/2026 o número de batidas vinha de
`posts.tem_intervalo_almoco`, um flag de POSTO. O intervalo é de PESSOA: no mesmo Ideal
Flores há quem almoce e quem receba o adicional. Com os NOVE postos em `false`, o app
fechava o dia na 2ª batida e 36 pessoas de 12x36 não conseguiram registrar a volta do
almoço — com print e áudio de quem sofreu.

DIVERGÊNCIA MEDIDA em 14/08: 5 pessoas em que a folha PAGOU o adicional e o cadastro dizia
que não recebia. O sistema esperava 4 batidas delas quando deveria esperar 2.

⚠️ NÃO INVENTA NADA. Só marca `recebe_intrajornada = true` para quem tem verba 0030/0031 na
folha, e `false` para quem não tem. Sem verba não há adicional; sem adicional, a pessoa
almoça. A folha é a fonte, e o script não tem opinião própria.

Ensaio é o padrão. Aplicar: --aplicar. Acima do teto de 10: --forcar.

    docker exec -e PYTHONPATH=/app conecta-pro-backend \\
      python3 /app/scripts/sincronizar_intrajornada.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/scripts/qa")

from _mutacao import Mutacao  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402

#: Os códigos do adicional na folha. Se aparecer um terceiro, ele entra AQUI — e não numa
#: condição espalhada por aí. `LIKE '%INTRA%'` não serve: pegaria rubrica de rescisão.
VERBAS_INTRAJORNADA = ("0030", "0031")

SQL_DIVERGENTES = text(
    "WITH folha AS ("
    "  SELECT DISTINCT employee_id FROM folha_verba_espelho "
    "  WHERE codigo = ANY(:codigos)) "
    "SELECT e.id::text AS id, e.nome AS nome, e.cargo AS cargo, "
    "       (f.employee_id IS NOT NULL) AS folha_pagou, "
    "       coalesce(e.recebe_intrajornada, false) AS cadastro "
    "FROM employees e LEFT JOIN folha f ON f.employee_id = e.id "
    "WHERE lower(coalesce(e.status,'')) = 'ativo' "
    "  AND upper(coalesce(e.nome,'')) NOT LIKE '%TESTE%' "
    "  AND upper(coalesce(e.nome,'')) NOT LIKE '%HOMOLOGA%' "
    "  AND (f.employee_id IS NOT NULL) IS DISTINCT FROM coalesce(e.recebe_intrajornada, false) "
    "ORDER BY e.nome"
)


async def main() -> int:
    m = Mutacao("sincronizar recebe_intrajornada com a folha", teto=10)

    async with async_session_factory() as db:
        linhas = (await db.execute(
            SQL_DIVERGENTES, {"codigos": list(VERBAS_INTRAJORNADA)}
        )).mappings().all()

        alvos = [
            (r["id"][:8],
             f"{r['nome']} ({r['cargo']}) — folha "
             f"{'PAGOU' if r['folha_pagou'] else 'não pagou'} · cadastro dizia "
             f"{'recebe' if r['cadastro'] else 'não recebe'} → passa a "
             f"{'2 batidas' if r['folha_pagou'] else '4 batidas'}")
            for r in linhas
        ]
        print(f"\n══ intrajornada: cadastro × contracheque — {len(linhas)} divergência(s) ══")

        if not m.confirmar(alvos):
            return 0

        n = (await db.execute(text(
            "UPDATE employees e SET recebe_intrajornada = EXISTS ("
            "  SELECT 1 FROM folha_verba_espelho f "
            "  WHERE f.employee_id = e.id AND f.codigo = ANY(:codigos)), updated_at = now() "
            "WHERE lower(coalesce(e.status,'')) = 'ativo' "
            "  AND upper(coalesce(e.nome,'')) NOT LIKE '%TESTE%' "
            "  AND upper(coalesce(e.nome,'')) NOT LIKE '%HOMOLOGA%' "
            "  AND EXISTS (SELECT 1 FROM folha_verba_espelho f2 "
            "              WHERE f2.employee_id = e.id AND f2.codigo = ANY(:codigos)) "
            "      IS DISTINCT FROM coalesce(e.recebe_intrajornada, false)"
        ), {"codigos": list(VERBAS_INTRAJORNADA)})).rowcount
        await db.commit()
        m.feito(n)

        conf = (await db.execute(text(
            "SELECT count(*) FILTER (WHERE coalesce(recebe_intrajornada,false)) AS de_2, "
            "       count(*) FILTER (WHERE NOT coalesce(recebe_intrajornada,false)) AS de_4, "
            "       count(*) AS total FROM employees "
            "WHERE lower(coalesce(status,'')) = 'ativo' "
            "  AND upper(coalesce(nome,'')) NOT LIKE '%TESTE%' "
            "  AND upper(coalesce(nome,'')) NOT LIKE '%HOMOLOGA%'"
        ))).first()
        print(f"  DEPOIS: {conf[0]} pessoa(s) com 2 batidas (recebem o adicional) · "
              f"{conf[1]} com 4 · {conf[2]} no total")
        restam = (await db.execute(
            SQL_DIVERGENTES, {"codigos": list(VERBAS_INTRAJORNADA)}
        )).rowcount
        print(f"  divergências restantes: {restam}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
