"""Y4 — efeito medido: quantas pessoas o feriado de CLIENTE passa a alcançar.

Não é oráculo (não entra na régua): é a medição antes/depois do §4 do relatório. Cria um feriado
de CLIENTE 'FIXTURE DGX Y4' num condomínio com gente, roda a apuração da X3 (paralelo cego —
tabela própria, não toca em `hr_payslips`), conta quem ele alcança, e apaga tudo no `finally`.

O «antes» é medido com a régua ANTIGA (condomínio = NULL para todos, que era o que a cascata por
`employees.cliente_id` devolvia) na mesma consulta de escopo da F7.
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

FIX = "FIXTURE DGX Y4"
COMP = "2026-09"


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.people_management.folha.services import feriado_conferencia as fc

    foto = "SELECT coalesce(sum(total_earnings),0), coalesce(sum(net_salary),0), count(*) FROM hr_payslips"
    fid = None
    async with async_session_factory() as db:
        antes_folha = tuple((await db.execute(text(foto))).first())

        # um dia útil de 09/2026 com bastante gente batendo, que ainda NÃO é feriado
        dia, quantos = (
            await db.execute(
                text(
                    "SELECT p.punch_timestamp::date AS d, count(DISTINCT p.employee_id) n FROM gp_clock_punches p"
                    " WHERE p.punch_timestamp >= DATE '2026-09-01' AND p.punch_timestamp < DATE '2026-10-01'"
                    "   AND p.punch_timestamp::date NOT IN (SELECT data_feriado FROM cct_feriados)"
                    " GROUP BY 1 ORDER BY n DESC, d LIMIT 1"
                )
            )
        ).first()

        # o condomínio com mais gente na apuração da competência
        cond_id, cond_nome, pop = (
            await db.execute(
                text(
                    "SELECT cd.id::text, f.condominio, count(DISTINCT f.employee_id) n"
                    "  FROM folha_feriado_conferencia f JOIN condominios cd ON cd.nome = f.condominio"
                    " WHERE f.competencia = :c AND f.condominio <> :tr GROUP BY 1,2 ORDER BY n DESC LIMIT 1"
                ),
                {"c": COMP, "tr": "—"},
            )
        ).first()

        print(
            f"dia escolhido: {dia:%d/%m/%Y} ({quantos} pessoa(s) bateram) · condomínio: {cond_nome} ({pop} na apuração)"
        )

        # ANTES — a cascata MORTA, recontada: quantas das pessoas da apuração tinham condomínio por
        # `condominios.client_id = employees.cliente_id`. Sem condomínio, o ramo `escopo='cliente'`
        # da régua da F7 (`f.condominio_id = :cond`) nunca é verdadeiro — alcance 0 por construção.
        antes, pop_total = (
            await db.execute(
                text(
                    "SELECT count(co.id), count(*) FROM employees e"
                    "  LEFT JOIN LATERAL (SELECT c.id FROM condominios c"
                    "                      WHERE c.client_id = e.cliente_id ORDER BY c.ativo DESC LIMIT 1) co ON true"
                    " WHERE EXISTS (SELECT 1 FROM gp_clock_punches p WHERE p.employee_id = e.id"
                    "                 AND p.punch_timestamp >= DATE '2026-08-31'"
                    "                 AND p.punch_timestamp < DATE '2026-10-02')"
                )
            )
        ).first()
        agora = (
            await db.execute(
                text(
                    "SELECT count(DISTINCT employee_id) FROM folha_feriado_conferencia"
                    " WHERE competencia = :c AND condominio <> :tr"
                ),
                {"c": COMP, "tr": "—"},
            )
        ).scalar()
        print(
            f"ANTES (cascata por employees.cliente_id): {antes}/{pop_total} com condomínio → "
            f"feriado de CLIENTE alcança 0 pessoa(s), por construção"
        )
        print(f"DEPOIS (resolvedor pela alocação vigente): {agora} pessoa(s) da apuração com condomínio")

        try:
            conv = (await db.execute(text("SELECT id::text FROM cct_convencoes LIMIT 1"))).scalar()
            fid = (
                await db.execute(
                    text(
                        "INSERT INTO cct_feriados (id, convencao_id, data_feriado, nome, tipo, ano, is_active,"
                        " escopo, condominio_id, recorrente, observacao)"
                        " VALUES (gen_random_uuid(), :conv, :d, :n, 'municipal', 2026, true, 'cliente',"
                        " CAST(:c AS uuid), false, :obs) RETURNING id::text"
                    ),
                    {"conv": conv, "d": dia, "n": f"{FIX} — aniversário do condomínio", "c": cond_id, "obs": FIX},
                )
            ).scalar()
            await db.commit()

            await fc.apurar(db, COMP)
            alcance = [
                r[0]
                for r in (
                    await db.execute(
                        text(
                            "SELECT nome FROM folha_feriado_conferencia WHERE competencia = :c AND data = :d"
                            "   AND tipo = 'feriado_trabalhado' ORDER BY nome"
                        ),
                        {"c": COMP, "d": dia},
                    )
                ).all()
            ]
            vazou = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM folha_feriado_conferencia WHERE competencia = :c AND data = :d"
                        "   AND coalesce(condominio,'') <> :k"
                    ),
                    {"c": COMP, "d": dia, "k": str(cond_nome)},
                )
            ).scalar()
            print(f"DEPOIS (condomínio resolvido pela alocação): alcance = {len(alcance)} pessoa(s)")
            print("  " + " · ".join(alcance) if alcance else "  (ninguém)")
            print(f"vazou para outro condomínio: {vazou} (tem que ser 0)")
        finally:
            if fid:
                await db.execute(text("DELETE FROM cct_feriados WHERE id = CAST(:i AS uuid)"), {"i": fid})
                await db.commit()
                await fc.apurar(db, COMP)
            sobra = (
                await db.execute(text("SELECT count(*) FROM cct_feriados WHERE nome LIKE :m"), {"m": f"%{FIX}%"})
            ).scalar()
            print(f"fixture '{FIX}' restante: {sobra} (tem que ser 0)")

        depois_folha = tuple((await db.execute(text(foto))).first())
        delta = sum(
            abs(Decimal(str(a)) - Decimal(str(b))) for a, b in zip(antes_folha[:2], depois_folha[:2], strict=True)
        )
        print(f"Σ|Δ| em hr_payslips = R$ {delta} (holerites: {antes_folha[2]} → {depois_folha[2]})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
