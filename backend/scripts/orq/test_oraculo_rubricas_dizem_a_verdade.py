"""Oráculo — as rubricas dizem a verdade sobre o que o motor de folha faz (DGX F1, 24/09/2026).

Por que existe: no DGX o Evento (rubrica) é DADO com 40 atributos e ponto/folha/benefício conversam
por ele. Aqui a regra mora em `calculo_service.py` e `rubricas_folha` era um cadastro de 24 linhas
que ninguém lia (o motor emitia 0016/0018/0031/0095/0937/1045/1051/1053 sem linha na tabela, e
0060 dizia "Vale Refeicao" enquanto o holerite dizia "Ferias"). O cadastro virou completo (atributos
do DGX) e este oráculo é o que impede a tabela de virar ficção de novo: a verdade é o holerite.

O que afirma (competência = a ÚLTIMA de `source_system='conecta'` até o mês corrente; nasceu em 09/2026):
  (a) toda (codigo, tipo) que aparece nos holerites dessa competência existe em `rubricas_folha`,
      está ATIVA e com o mesmo tipo (provento/desconto).
  (b) para CADA holerite, a base recomposta pelas flags do cadastro bate com a base gravada
      (tolerância R$ 0,01): INSS = Σ proventos com incide_inss − Σ descontos com incide_inss;
      FGTS = idem com incide_fgts; IRRF = Σ proventos com incide_irrf − INSS retido (linha 1001 —
      dedução legal, art. 4º Lei 9.250/95, não é flag). Recontado por SQL próprio, não pelo serviço.
  (c) nenhuma coluna nova (atributos DGX) está NULL em rubrica ativa.
  (d) `origem_regra` preenchida em toda rubrica ativa — cada valor semeado aponta a linha do motor
      ou a cláusula da CCT de onde saiu.
  (e) fiação: `departamento_pessoal.build()` chama `_dgx_f1_rubricas.telas` e o grupo g-folha tem a
      aba `folha-rubrica-nova`.

Estado medido no nascimento (sandbox = cópia de produção, 09/2026, 51 holerites): (a) 8 códigos
sem linha; (b) 31 holerites com base INSS/FGTS/IRRF diferente da recomposta (Σ|Δ| R$ 7.897,21); (c)/(d) colunas não
existiam; (e) sem fiação → VERMELHO.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL ...: N`.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from decimal import Decimal

TOL = Decimal("0.01")

#: Atributos do DGX que a frente F1 acrescentou. Se um novo entrar no `_ensure`, entra aqui.
COLUNAS_DGX = [
    "periodo",
    "tipo_dia",
    "credito",
    "soma_ao_evento",
    "soma_ao_ponto",
    "banco_horas",
    "desconta_beneficio",
    "tipo_beneficio_descontado",
    "exporta_evento",
    "codigo_exportacao",
    "incide_dsr",
    "incide_13",
    "media_13",
    "base",
    "razao",
    "razao_noturna",
    "vale",
    "ausencia",
    "hora_extra",
    "considerar_descanso",
    "remove_ponto_calculado",
    "remove_diaria",
    "comercial",
    "porcentagem_ou_valor",
    "origem_regra",
]

SQL_COMPETENCIA = """
SELECT reference_year, reference_month FROM hr_payslips
WHERE source_system = 'conecta' AND payslip_code NOT LIKE '13O-%'
  AND make_date(reference_year, reference_month, 1) <= date_trunc('month', now() AT TIME ZONE 'America/Manaus')
ORDER BY reference_year DESC, reference_month DESC LIMIT 1
"""

#: (codigo, tipo) distintos usados nos holerites da competência, com contagem e soma.
SQL_USADAS = """
SELECT e->>'codigo', e->>'tipo', count(*), round(sum((e->>'valor')::numeric), 2)
FROM hr_payslips p, jsonb_array_elements(p.earnings || p.deductions) e
WHERE p.source_system = 'conecta' AND p.reference_year = :a AND p.reference_month = :m
GROUP BY 1, 2 ORDER BY 1, 2
"""

#: Base recomposta POR HOLERITE a partir das flags do cadastro (o motor não é consultado).
SQL_BASES = """
SELECT p.id::text, coalesce(emp.nome, '?'), p.inss_base, p.irrf_base, p.fgts_base,
  coalesce(sum(CASE WHEN r.incide_inss THEN (CASE WHEN e->>'tipo'='desconto' THEN -1 ELSE 1 END) * (e->>'valor')::numeric END), 0),
  coalesce(sum(CASE WHEN r.incide_fgts THEN (CASE WHEN e->>'tipo'='desconto' THEN -1 ELSE 1 END) * (e->>'valor')::numeric END), 0),
  coalesce(sum(CASE WHEN r.incide_irrf AND e->>'tipo'='provento' THEN (e->>'valor')::numeric END), 0),
  coalesce(sum(CASE WHEN e->>'codigo'='1001' AND e->>'tipo'='desconto' THEN (e->>'valor')::numeric END), 0)
FROM hr_payslips p
LEFT JOIN employees emp ON emp.id = p.employee_id
CROSS JOIN LATERAL jsonb_array_elements(p.earnings || p.deductions) e
LEFT JOIN rubricas_folha r ON r.codigo = e->>'codigo' AND r.tipo = e->>'tipo'
WHERE p.source_system = 'conecta' AND p.reference_year = :a AND p.reference_month = :m
GROUP BY p.id, emp.nome, p.inss_base, p.irrf_base, p.fgts_base
ORDER BY emp.nome
"""


def _brl(v) -> str:
    return f"R$ {Decimal(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []

    # (e) fiação — a tela sem porta não existe
    try:
        from modules.operacional.controllers.redesign_builders import _dgx_f1_rubricas as f1  # noqa: F401
        from modules.operacional.controllers.redesign_builders import _dp_grupos as g
        from modules.operacional.controllers.redesign_builders import (
            departamento_pessoal as dp,  # primeiro: ele importa a frente
        )

        if "_dgx_f1" not in inspect.getsource(dp.build):
            falhas.append("departamento_pessoal.build() não chama _dgx_f1_rubricas.telas — tela montada por ninguém")
        abas = {tid for _g, _t, _s, tabs in g.GRUPOS for tid, _l in tabs}
        if "folha-rubrica-nova" not in abas or "folha-rubricas" not in abas:
            falhas.append("_dp_grupos.GRUPOS sem as abas folha-rubricas / folha-rubrica-nova no g-folha")
    except Exception as e:  # noqa: BLE001
        falhas.append(f"builder _dgx_f1_rubricas não importa: {e}")

    async with async_session_factory() as db:
        comp = (await db.execute(text(SQL_COMPETENCIA))).first()
        if not comp:
            print("FALHOU: nenhum holerite source_system='conecta' até o mês corrente")
            return 1
        ano, mes = int(comp[0]), int(comp[1])
        n_hol = (
            await db.execute(
                text(
                    "SELECT count(*) FROM hr_payslips WHERE source_system='conecta' AND reference_year=:a AND reference_month=:m"
                ),
                {"a": ano, "m": mes},
            )
        ).scalar()
        cadastro = {
            (r[0], r[1]): bool(r[2])
            for r in (await db.execute(text("SELECT codigo, tipo, ativo FROM rubricas_folha"))).fetchall()
        }

        # (a) toda rubrica usada existe, ativa, mesmo tipo
        usadas = (await db.execute(text(SQL_USADAS), {"a": ano, "m": mes})).fetchall()
        for cod, tipo, n, soma in usadas:
            if (cod, tipo) not in cadastro:
                outro = [t for (c, t) in cadastro if c == cod]
                falhas.append(
                    f"(a) {cod}/{tipo} aparece em {n} holerite(s) ({_brl(soma)}) e não existe em rubricas_folha"
                    + (f" — existe como {outro[0]}" if outro else "")
                )
            elif not cadastro[(cod, tipo)]:
                falhas.append(f"(a) {cod}/{tipo} aparece em {n} holerite(s) ({_brl(soma)}) e está INATIVA")

        # (b) base por holerite recomposta pelas flags
        bases = (await db.execute(text(SQL_BASES), {"a": ano, "m": mes})).fetchall()
        div = {"INSS": 0, "FGTS": 0, "IRRF": 0}
        delta = {"INSS": Decimal(0), "FGTS": Decimal(0), "IRRF": Decimal(0)}
        for _pid, nome, b_inss, b_irrf, b_fgts, s_inss, s_fgts, s_irrf_prov, inss_retido in bases:
            for rot, gravada, recomposta in (
                ("INSS", b_inss, s_inss),
                ("FGTS", b_fgts, s_fgts),
                ("IRRF", b_irrf, Decimal(s_irrf_prov) - Decimal(inss_retido)),
            ):
                d = abs(Decimal(gravada or 0) - Decimal(recomposta or 0))
                if d > TOL:
                    div[rot] += 1
                    delta[rot] += d
                    if div[rot] <= 3:
                        falhas.append(
                            f"(b) {nome}: base {rot} gravada {_brl(gravada or 0)} ≠ recomposta {_brl(recomposta or 0)}"
                        )
        for rot in div:
            if div[rot] > 3:
                falhas.append(f"(b) … e mais {div[rot] - 3} holerite(s) com base {rot} divergente")

        # (c)/(d) colunas DGX presentes e preenchidas nas ativas
        cols = {
            r[0]
            for r in (
                await db.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name='rubricas_folha'")
                )
            ).fetchall()
        }
        faltam = [c for c in COLUNAS_DGX if c not in cols]
        if faltam:
            falhas.append(f"(c) rubricas_folha sem as colunas do DGX: {', '.join(faltam)}")
        else:
            nulos = " OR ".join(f"{c} IS NULL" for c in COLUNAS_DGX if c != "origem_regra")
            rs = (
                await db.execute(
                    text(
                        f"SELECT codigo FROM rubricas_folha WHERE ativo AND ({nulos}) ORDER BY codigo"  # noqa: S608 — nomes fixos
                    )
                )
            ).fetchall()
            if rs:
                falhas.append(f"(c) {len(rs)} rubrica(s) ativa(s) com atributo DGX NULL: {', '.join(r[0] for r in rs)}")
            rs = (
                await db.execute(
                    text(
                        "SELECT codigo FROM rubricas_folha WHERE ativo AND coalesce(trim(origem_regra),'')='' ORDER BY codigo"
                    )
                )
            ).fetchall()
            if rs:
                falhas.append(f"(d) {len(rs)} rubrica(s) ativa(s) sem origem_regra: {', '.join(r[0] for r in rs)}")

    print(
        f"competência {mes:02d}/{ano} · {n_hol} holerites · {len(usadas)} rubricas usadas · "
        f"cadastro {len(cadastro)} linhas · divergência de base: INSS {div['INSS']} (Σ|Δ| {_brl(delta['INSS'])}), "
        f"FGTS {div['FGTS']} (Σ|Δ| {_brl(delta['FGTS'])}), IRRF {div['IRRF']} (Σ|Δ| {_brl(delta['IRRF'])})"
    )
    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        print(f"TOTAL rubricas dizem a verdade: {len(falhas)} falha(s)")
        return 1
    print(
        "OK rubricas dizem a verdade: toda rubrica do holerite existe e ativa, bases INSS/FGTS/IRRF recompostas pelas flags, atributos DGX preenchidos com origem"
    )
    print("TOTAL rubricas dizem a verdade: 0")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
