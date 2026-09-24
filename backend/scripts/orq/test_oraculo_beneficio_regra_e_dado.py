"""Oráculo — Tipo de Benefício CARREGA a regra, e a regra na tabela reproduz o motor (DGX F3, 24/09/2026).

Por que existe: no DGX o tipo de benefício é DADO — tipo de desconto (7), coeficiente, evento de
débito, integração com o ponto (8), limite de faltas, remover férias/afastados. Aqui a regra do
VT/VR vivia em constantes (`calculo_service.DESC_VT_PCT`, `VT_DIA`) e em código do motor da
frente 03 (`beneficio_ponto`: férias e afastados sempre removidos, sem limite de faltas). A F3
move a regra para `beneficio_tipos` e o motor passa a LÊ-LA — em PARALELO CEGO. O risco é o de
sempre num caminho de dinheiro: a regra na tabela ser DIFERENTE da que o código aplicava e
ninguém notar, ou alguém "corrigir" o seed e mudar o pedido de VT de 50 pessoas.

O que afirma (recontado por SQL próprio, não pelo serviço):
  (a) `beneficio_tipos` existe; todo tipo ativo tem `tipo_desconto` num dos 7 valores e
      `origem_regra` preenchida; o seed de VT/VR bate com a constante do código
      (coeficiente == DESC_VT_PCT×100 / DESC_VR_PCT×100) e a rubrica de débito existe em
      `rubricas_folha`. Um tipo ativo por primitivo VT e por VR (o motor precisa de UMA regra).
  (b) todo `employee_benefits` ATIVO de VT/VR (type em VT/vale_transporte/VR/vale_refeicao) aponta
      para um `beneficio_tipos` ativo do mesmo primitivo.
  (c) o motor com a regra da tabela reproduz, linha a linha e SEM GRAVAR, o que
      `folha_beneficio_conferencia` guarda para cada competência já calculada: mesmo estado,
      previsão, quantidade, unitário e total → Σ|Δ total| = 0. Linha guardada que o motor não
      produz mais (pessoa saiu da coorte) é impressa, não julgada.
  (d) nenhuma `beneficio_linhas` com tarifa inventada: `valor` não nulo exige `origem_regra`.

Estado medido no nascimento (staging, 24/09/2026): tabela não existe → VERMELHO em (a)/(b)/(d);
(c) não roda sem `gravar=False` no motor. Baseline gravada com o motor ANTERIOR: 08/2026 (108 linhas,
R$ 20.922,00) e 09/2026 (102 linhas, R$ 22.228,00).

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL desvios: N`.
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

TIPOS_DESCONTO = {
    "fixo",
    "nenhum",
    "percentual_valor_sobre_falta",
    "percentual_sobre_salario",
    "percentual_sobre_valor",
    "unidade",
    "valor_por_dia",
}

SQL_TIPOS = """
SELECT id, nome, tipo_primitivo, tipo_desconto, coeficiente_desconto, rubrica_debito, origem_regra,
       (SELECT count(*) FROM rubricas_folha r WHERE r.codigo = t.rubrica_debito)
FROM beneficio_tipos t WHERE ativo ORDER BY id
"""
SQL_EB_SEM_TIPO = """
SELECT e.nome, b.type, b.beneficio_tipo_id FROM employee_benefits b JOIN employees e ON e.id = b.employee_id
LEFT JOIN beneficio_tipos t ON t.id = b.beneficio_tipo_id AND t.ativo
WHERE lower(b.status) = 'active' AND lower(b.type) IN ('vt','vale_transporte','vr','vale_refeicao')
  AND (t.id IS NULL OR t.tipo_primitivo <> CASE WHEN lower(b.type) IN ('vt','vale_transporte') THEN 'VT' ELSE 'VR' END)
"""
SQL_LINHAS_SEM_ORIGEM = (
    "SELECT operadora, nome, valor FROM beneficio_linhas WHERE valor IS NOT NULL AND coalesce(origem_regra,'') = ''"
)
SQL_COMPS = "SELECT DISTINCT competencia FROM folha_beneficio_conferencia WHERE estado <> 'so_portal' ORDER BY 1"
SQL_GUARDADO = """
SELECT employee_id::text, beneficio, estado, previsao, quantidade, unitario, total
FROM folha_beneficio_conferencia WHERE competencia = CAST(:c AS date) AND estado <> 'so_portal'
"""


async def main() -> int:  # noqa: C901, PLR0912, PLR0915
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []
    async with async_session_factory() as db:
        if (await db.execute(text("SELECT to_regclass('beneficio_tipos')"))).scalar() is None:
            print("FALHOU: tabela beneficio_tipos não existe — a regra ainda mora no código")
            print("TOTAL desvios: 1")
            return 1

        # (a) regra completa e igual ao código
        from modules.people_management.folha.services.calculo_service import DESC_VR_PCT, DESC_VT_PCT

        tipos = (await db.execute(text(SQL_TIPOS))).fetchall()
        por_prim: dict[str, list] = {}
        for _id, nome, prim, tdesc, coef, rub, origem, rub_ok in tipos:
            por_prim.setdefault(prim, []).append(nome)
            if tdesc not in TIPOS_DESCONTO:
                falhas.append(f"(a) {nome}: tipo_desconto {tdesc!r} fora dos 7 do DGX")
            if not (origem or "").strip():
                falhas.append(f"(a) {nome}: sem origem_regra — regra sem fonte é regra inventada")
            if rub and not rub_ok:
                falhas.append(f"(a) {nome}: rubrica_debito {rub} não existe em rubricas_folha")
            esperado = {"VT": DESC_VT_PCT, "VR": DESC_VR_PCT}.get(prim)
            if esperado is not None:
                if tdesc != "percentual_sobre_salario" or coef is None or Decimal(coef) != esperado * 100:
                    falhas.append(
                        f"(a) {nome}: regra {tdesc}/{coef} ≠ código percentual_sobre_salario/{esperado * 100}"
                    )
                if rub != {"VT": "1010", "VR": "1011"}[prim]:
                    falhas.append(f"(a) {nome}: rubrica_debito {rub} ≠ a que calculo_service lança")
        for prim in ("VT", "VR"):
            if len(por_prim.get(prim, [])) != 1:
                falhas.append(
                    f"(a) {prim}: {len(por_prim.get(prim, []))} tipo(s) ativo(s) — o motor precisa de exatamente 1"
                )

        # (b) benefício individual aponta para o tipo
        for nome, typ, tid in (await db.execute(text(SQL_EB_SEM_TIPO))).fetchall():
            falhas.append(
                f"(b) {nome} · {typ}: beneficio_tipo_id={tid} não aponta para um tipo ativo do mesmo primitivo"
            )

        # (d) tarifa sem fonte
        for op, nome, valor in (await db.execute(text(SQL_LINHAS_SEM_ORIGEM))).fetchall():
            falhas.append(f"(d) linha {op}/{nome}: valor {valor} sem origem_regra")

        # (c) motor com regra da tabela == conferência guardada (sem gravar)
        from modules.people_management.folha.services import beneficio_ponto as bp

        comps = [r[0] for r in (await db.execute(text(SQL_COMPS))).fetchall()]
        soma_delta = Decimal("0")
        comparadas = orfas = 0
        for comp in comps:
            guardado = {(r[0], r[1]): r for r in (await db.execute(text(SQL_GUARDADO), {"c": comp})).fetchall()}
            try:
                res = await bp.calcular_competencia(db, comp.year, comp.month, gravar=False)
            except TypeError as e:
                falhas.append(f"(c) motor não sabe calcular sem gravar: {e}")
                break
            calc = {(ln["e"], ln["b"]): ln for ln in res["linhas_calc"]}
            for k, ln in calc.items():
                g = guardado.get(k)
                if g is None:
                    falhas.append(f"(c) {comp:%m/%Y} {k[1]} {k[0][:8]}: motor produz linha que a conferência não tem")
                    continue
                comparadas += 1
                d = (Decimal(ln["total"]) if ln["total"] is not None else Decimal(0)) - (
                    Decimal(g[6]) if g[6] is not None else Decimal(0)
                )
                soma_delta += abs(d)
                dif = [
                    c
                    for c, a, b_ in (
                        ("previsao", ln["prev"], g[3]),
                        ("qtd", ln["qtd"], g[4]),
                        ("unit", ln["unit"], g[5]),
                        ("total", ln["total"], g[6]),
                    )
                    if (a is None) != (b_ is None) or (a is not None and Decimal(str(a)) != Decimal(str(b_)))
                ]
                if ln["estado"] != g[2]:
                    dif.insert(0, "estado")
                if dif:
                    falhas.append(
                        f"(c) {comp:%m/%Y} {k[1]} {k[0][:8]}: difere em {dif} — motor {ln['estado']}/{ln['prev']}/{ln['qtd']}/{ln['total']} × guardado {g[2]}/{g[3]}/{g[4]}/{g[6]}"
                    )
            orfas += len(set(guardado) - set(calc))
        await db.rollback()

    print(f"tipos ativos: {len(tipos)} · por primitivo: { {k: len(v) for k, v in sorted(por_prim.items())} }")
    print(
        f"competências comparadas: {len(comps)} · linhas comparadas: {comparadas} · guardadas sem par (fora da coorte): {orfas} · Σ|Δ total|: R$ {soma_delta}"
    )
    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL desvios: {len(falhas)}")
    if falhas:
        raise AssertionError(
            f"{len(falhas)} desvio(s) — a regra do benefício não está na tabela ou não reproduz o motor"
        )
    print(
        "OK benefício regra e dado: tipo carrega a regra, individual aponta para o tipo, motor pela tabela reproduz a conferência, linha sem tarifa inventada"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
