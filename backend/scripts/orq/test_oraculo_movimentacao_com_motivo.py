"""Oráculo — Movimentação com motivo tipado (paridade DGX, frente F5, 24/09/2026).

Por que existe: no DGX a Movimentação é a unidade operacional — alocar ou remover alguém de uma
VAGA, com motivo tipado (7), data, origem/destino, quem pediu. Aqui `employee_alocacoes` (73
linhas) tinha só employee × condomínio × função × datas: sem motivo, sem quem pediu, sem
histórico legível e sem NENHUM caminho do app que escrevesse nela (`checar_alocacao_de_quem_saiu`
documenta isso). Alocar por cima de outra alocação era impossível pela tela e, por SQL, deixava
duas ativas ao mesmo tempo — e é a alocação ativa que o kit do GEDEON, o Hermes, a categorização
do Inter e o "Sem alocação" do DP leem.

O que afirma (recontado por SQL próprio, não pelo serviço):
  a. Toda alocação ATIVA tem `tipo` e `motivo` preenchidos (as 73 antigas ganham
     alocar/alocacao_de_vaga + observação "retroativo"; nada mais nelas muda).
  b. Nenhum colaborador tem duas alocações ativas no mesmo condomínio + função.
  c. Alocar por cima de uma ativa ENCERRA a anterior no dia anterior (`data_fim = data_inicio − 1`,
     `ativo=false`) e liga `alocacao_origem_id`; alocar igual de novo é recusado (409).
     Fixture no sandbox ('FIXTURE DGX F5' na observação), apagada ao fim.
  d. Cobertura de férias/afastamento sem `coberto_employee_id` é recusada (422); com coberto que
     NÃO está de férias na data também.
  e. O mapa de ponto de HOJE (régua da frente 04, `mapa_de_ponto.mapa_do_dia`) e esta tabela
     contam a MESMA gente: toda pessoa com turno hoje tem alocação ativa no condomínio do posto.

Estado medido no nascimento (staging, 24/09/2026): colunas não existiam (UndefinedColumn em a),
serviço não existia (ImportError em c/d) → VERMELHO. (b) já era verde (0 duplicadas) e (e)
media 27 = 27 (turnos de hoje na coorte do ponto).

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL ...: N`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta

FIX = "FIXTURE DGX F5"

SQL_ATIVAS_SEM_TIPO = "SELECT count(*) FROM employee_alocacoes WHERE ativo AND (tipo IS NULL OR motivo IS NULL)"
SQL_DUPLICADAS = """
SELECT count(*) FROM (
  SELECT employee_id, condominio_id, funcao FROM employee_alocacoes
  WHERE ativo AND (data_fim IS NULL OR data_fim >= (now() AT TIME ZONE 'America/Manaus')::date)
  GROUP BY 1, 2, 3 HAVING count(*) > 1) d
"""
SQL_CANDIDATO = """
SELECT e.id::text FROM employees e
WHERE e.status = 'ativo' AND coalesce(e.is_homologacao, false) = false
  AND NOT EXISTS (SELECT 1 FROM employee_alocacoes a WHERE a.employee_id = e.id AND a.ativo)
ORDER BY e.nome LIMIT 1
"""
SQL_CONDS = "SELECT id::text FROM condominios WHERE ativo ORDER BY nome LIMIT 2"
SQL_FIX = "SELECT id::text, data_inicio, data_fim, ativo, alocacao_origem_id::text FROM employee_alocacoes WHERE observacao LIKE :f ORDER BY data_inicio"
SQL_APAGA_FIX = "DELETE FROM employee_alocacoes WHERE observacao LIKE :f"
# (e) recontagem: pessoa com turno hoje → alocação ativa no condomínio do posto (posts.client_id = condominios.client_id)
SQL_ALOCADO_NO_POSTO = """
SELECT count(*) FROM employee_alocacoes a
JOIN condominios c ON c.id = a.condominio_id
JOIN posts p ON p.client_id = c.client_id AND p.id = CAST(:post AS uuid)
WHERE a.employee_id = CAST(:emp AS uuid) AND a.ativo
  AND a.data_inicio <= :hoje AND (a.data_fim IS NULL OR a.data_fim >= :hoje)
"""


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []

    def ok(cond: bool, msg: str) -> None:
        print(("  ✓ " if cond else "  ✗ ") + msg)
        if not cond:
            falhas.append(msg)

    async with async_session_factory() as db:
        # a. tipo e motivo em toda ativa
        try:
            n = (await db.execute(text(SQL_ATIVAS_SEM_TIPO))).scalar()
            ok(n == 0, f"(a) alocações ativas sem tipo/motivo: {n}")
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            ok(False, f"(a) coluna tipo/motivo não existe: {type(exc).__name__}")

        # b. sem duplicada ativa
        n = (await db.execute(text(SQL_DUPLICADAS))).scalar()
        ok(n == 0, f"(b) colaboradores com 2 alocações ativas no mesmo condomínio+função: {n}")

        # c/d. serviço
        try:
            from modules.operacional.services import movimentacao_service as ms
        except Exception as exc:  # noqa: BLE001
            ms = None
            ok(False, f"(c/d) serviço movimentacao_service não importa: {type(exc).__name__}: {exc}")

        if ms is not None:
            await db.execute(text(SQL_APAGA_FIX), {"f": FIX + "%"})
            await db.commit()
            emp = (await db.execute(text(SQL_CANDIDATO))).scalar()
            conds = [r[0] for r in (await db.execute(text(SQL_CONDS))).fetchall()]
            hoje = ms.hoje_manaus()
            if not emp or len(conds) < 2:
                ok(False, "(c) sem colaborador ativo sem alocação ou sem 2 condomínios para a fixture")
            else:
                try:
                    r1 = await ms.alocar(
                        db,
                        employee_id=emp,
                        condominio_id=conds[0],
                        funcao="AGENTE DE PORTARIA",
                        data_inicio=hoje - timedelta(days=3),
                        motivo="alocacao_de_vaga",
                        solicitado_por="dp",
                        observacao=FIX + " 1",
                    )
                    r2 = await ms.alocar(
                        db,
                        employee_id=emp,
                        condominio_id=conds[1],
                        funcao="AGENTE DE PORTARIA",
                        data_inicio=hoje,
                        motivo="a_pedido_do_cliente",
                        solicitado_por="cliente",
                        solicitante_nome="síndico",
                        observacao=FIX + " 2",
                    )
                    await db.commit()
                    rows = (await db.execute(text(SQL_FIX), {"f": FIX + "%"})).fetchall()
                    por_id = {r[0]: r for r in rows}
                    a1, a2 = por_id.get(str(r1["id"])), por_id.get(str(r2["id"]))
                    ok(
                        a1 is not None and a1[3] is False and a1[2] == hoje - timedelta(days=1),
                        f"(c) anterior encerrada no dia anterior: ativo={a1 and a1[3]} data_fim={a1 and a1[2]} (esperado {hoje - timedelta(days=1)})",
                    )
                    ok(
                        a2 is not None and a2[3] is True and a2[4] == str(r1["id"]),
                        f"(c) nova ativa e ligada à origem: ativo={a2 and a2[3]} origem={a2 and a2[4]}",
                    )
                    try:
                        await ms.alocar(
                            db,
                            employee_id=emp,
                            condominio_id=conds[1],
                            funcao="AGENTE DE PORTARIA",
                            data_inicio=hoje,
                            motivo="alocacao_de_vaga",
                            solicitado_por="dp",
                            observacao=FIX + " dup",
                        )
                        ok(False, "(c) alocação igual repetida foi ACEITA")
                    except ms.MovimentacaoErro as exc:
                        ok(exc.status == 409, f"(c) alocação igual repetida recusada com {exc.status}: {exc}")
                    n = (await db.execute(text(SQL_DUPLICADAS))).scalar()
                    ok(n == 0, f"(c) recontagem de duplicadas com a fixture no banco: {n}")
                except ms.MovimentacaoErro as exc:
                    ok(False, f"(c) serviço recusou a fixture: {exc.status} {exc}")
                finally:
                    await db.rollback()
                    await db.execute(text(SQL_APAGA_FIX), {"f": FIX + "%"})
                    await db.commit()

                # d. cobertura de férias exige coberto que esteja de férias
                for motivo in ("cobertura_de_ferias", "cobertura_de_afastamento"):
                    try:
                        await ms.alocar(
                            db,
                            employee_id=emp,
                            condominio_id=conds[0],
                            funcao="AGENTE DE PORTARIA",
                            data_inicio=hoje,
                            motivo=motivo,
                            solicitado_por="dp",
                            observacao=FIX + " d",
                        )
                        ok(False, f"(d) {motivo} sem coberto foi ACEITA")
                    except ms.MovimentacaoErro as exc:
                        ok(exc.status == 422, f"(d) {motivo} sem coberto recusada com {exc.status}: {exc}")
                    await db.rollback()
                try:
                    await ms.alocar(
                        db,
                        employee_id=emp,
                        condominio_id=conds[0],
                        funcao="AGENTE DE PORTARIA",
                        data_inicio=hoje,
                        motivo="cobertura_de_ferias",
                        solicitado_por="dp",
                        coberto_employee_id=emp,
                        observacao=FIX + " d2",
                    )
                    ok(False, "(d) cobertura com coberto que NÃO está de férias foi ACEITA")
                except ms.MovimentacaoErro as exc:
                    ok(exc.status == 422, f"(d) coberto sem férias na data recusado com {exc.status}: {exc}")
                await db.rollback()
                await db.execute(text(SQL_APAGA_FIX), {"f": FIX + "%"})
                await db.commit()
                n = (
                    await db.execute(
                        text("SELECT count(*) FROM employee_alocacoes WHERE observacao LIKE :f"), {"f": FIX + "%"}
                    )
                ).scalar()
                ok(n == 0, f"(c/d) fixture apagada ao fim: {n} sobrando")

        # e. mapa de hoje (frente 04) × alocação ativa
        from modules.people_management.ponto import mapa_de_ponto as regua

        m = await regua.mapa_do_dia(db)
        hoje = date.fromisoformat(m["dia"][:10])
        pares = {(i["employee_id"], i["post_id"]) for i in m["itens"] if i.get("estado")}
        com = 0
        for emp_id, post_id in pares:
            com += (
                1
                if (
                    await db.execute(text(SQL_ALOCADO_NO_POSTO), {"emp": emp_id, "post": post_id, "hoje": hoje})
                ).scalar()
                else 0
            )
        ok(com == len(pares), f"(e) turnos de hoje {len(pares)} × com alocação ativa no condomínio do posto {com}")

    print(f"TOTAL falhas movimentação com motivo: {len(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
