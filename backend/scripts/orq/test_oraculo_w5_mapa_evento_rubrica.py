"""Oráculo — o mapa evento→rubrica EXPLICA o que o motor de folha emitiu (DGX W5, 24/09/2026).

Por que existe: a F1 trouxe a rubrica como dado (40 atributos do DGX) e a F7 trouxe a configuração
de ponto em cascata. O ELO entre as duas continuava em código: quando o ponto produz uma ocorrência
(falta, HE 50%, adicional noturno, hora noturna reduzida, intrajornada, DSR), quem decide em qual
rubrica isso vira — e com que fórmula — é `calculo_service.py`. No DGX isso é uma linha de cadastro
(«Configurações de Ponto» → mapa evento→rubrica + tipo de cálculo). Enquanto for código, mudar a
CCT é mexer em Python.

`ponto_evento_rubrica` é esse cadastro. Este oráculo é o que impede o cadastro de virar ficção:
a verdade continua sendo o holerite.

O que afirma (competências: as duas últimas de `source_system='conecta'` — 09/2026 e 08/2026):
  (a) toda verba de PONTO do holerite (os códigos que o mapa reivindica) tem linha no mapa e o
      código que o mapa RESOLVE para aquele evento e aquela pessoa == o código que o motor emitiu;
  (b) o VALOR recomposto pela fórmula do mapa (a quantidade vem da `referencia` do próprio
      holerite; valor_hora/salário/ronda vêm do cadastro do empregado) bate com o valor gravado,
      tolerância R$ 0,01 por linha e **Σ|Δ| = R$ 0,00** no total;
  (c) nenhum evento que o motor PRODUZ está sem linha no mapa (a lista de eventos produzidos é
      levantada do próprio holerite, não de uma constante);
  (d) toda linha do mapa tem `origem_regra` — arquivo e linha do motor, ou cláusula/lei;
  (e) a cascata resolve: uma linha de COLABORADOR vence a de EMPRESA (fixture 'FIXTURE DGX W5',
      apagada ao fim mesmo em falha);
  (f) fiação: `departamento_pessoal.build()` chama `_dgx_w5_mapa_evento_rubrica.telas` e as abas
      estão em `_dp_grupos` (tela sem porta não existe).

Onde (b) não bate, a lista nominal que sai aqui É a dívida entre o cadastro e o motor — vai para
o §7 do relatório. Zero por falta de dado ≠ zero por ausência de divergência: (c) conta a
população antes.

Estado medido no nascimento (sandbox = cópia de produção, 24/09/2026): `ponto_evento_rubrica` não
existia e `mapa_evento_rubrica` não importava → VERMELHO em tudo. 153 verbas de ponto em 08+09/2026
sem uma linha de cadastro que as explicasse.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL desvios: N`.
"""

from __future__ import annotations

import asyncio
import calendar
import inspect
import re
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

FIX = "FIXTURE DGX W5"
TOL = Decimal("0.01")

#: As duas últimas competências do motor próprio. 09/2026 e 08/2026 estão em `draft` (o último
#: `published` é 07/2026, e 07 é 100% backfill do espelho da Portte — verba copiada, não calculada
#: por evento; ver §5 do relatório). "Publicado" aqui = emitido pelo nosso motor.
SQL_COMPETENCIAS = """
SELECT DISTINCT reference_year, reference_month FROM hr_payslips
WHERE source_system = 'conecta' AND payslip_code NOT LIKE '13O-%'
  AND make_date(reference_year, reference_month, 1) <= date_trunc('month', now() AT TIME ZONE 'America/Manaus')
ORDER BY 1 DESC, 2 DESC LIMIT 2
"""

#: Uma linha por verba do holerite, com o que a fórmula precisa: base salarial efetiva (piso da CCT
#: vence o cadastrado, como o motor faz), escala (divisor), ronda do funcionário e a `referencia`
#: (onde o motor gravou a QUANTIDADE — horas, plantões ou dias).
SQL_VERBAS = """
SELECT p.employee_id::text, coalesce(e.nome,'?') AS nome, coalesce(e.escala_padrao,'12x36') AS escala,
       GREATEST(coalesce(e.salario_base,0), coalesce((
         SELECT c.piso_salarial FROM cct_cargos c
          WHERE c.is_active AND lower(c.cargo_nome) = lower(coalesce(a.cct_nome, e.cargo))
          ORDER BY c.updated_at DESC NULLS LAST LIMIT 1), 0)) AS base,
       coalesce(e.adicional_ronda_percentual,0) AS ronda, e.cargo, e.cliente_id::text AS cliente_id,
       x->>'codigo' AS codigo, x->>'tipo' AS tipo, x->>'referencia' AS referencia, (x->>'valor')::numeric AS valor
  FROM hr_payslips p
  JOIN employees e ON e.id = p.employee_id
  LEFT JOIN LATERAL (SELECT CAST(:alias AS jsonb) ->> upper(regexp_replace(translate(e.cargo,
         'ÁÀÂÃÉÊÍÓÔÕÚÜÇáàâãéêíóôõúüç','AAAAEEIOOOUUCaaaaeeioouuc'), '\\s+', ' ', 'g')) AS cct_nome) a ON true
  CROSS JOIN LATERAL jsonb_array_elements(p.earnings || p.deductions) x
 WHERE p.source_system = 'conecta' AND p.reference_year = :a AND p.reference_month = :m
   AND x->>'codigo' = ANY(CAST(:cods AS text[]))
 ORDER BY nome, codigo
"""

#: O mapa, lido por SQL PRÓPRIO (o resolvedor do serviço não é consultado em (a)/(b)).
SQL_MAPA = """
SELECT id, evento, rubrica_codigo, escopo, escopo_id, formula, base, percentual, ativo, origem_regra
  FROM ponto_evento_rubrica
 WHERE ativo AND (vigencia_inicio IS NULL OR vigencia_inicio <= :ref)
   AND (vigencia_fim IS NULL OR vigencia_fim >= :ref)
 ORDER BY created_at, id
"""


def _r(v) -> Decimal:
    """O arredondamento do motor (`calculo_service._d`): 2 casas, meio para cima."""
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _fator_dsr(escala: str, mes: int, ano: int) -> Decimal:
    """Recontado aqui (não importado do motor): 1/6 no 12x36, domingos/dias úteis no comercial."""
    if escala == "12x36":
        return Decimal(1) / Decimal(6)
    uteis = domingos = 0
    for dia in range(1, calendar.monthrange(ano, mes)[1] + 1):
        if calendar.weekday(ano, mes, dia) == 6:
            domingos += 1
        else:
            uteis += 1
    return Decimal(domingos) / Decimal(uteis) if uteis else Decimal(0)


_NUM = re.compile(r"^\s*([0-9]+(?:[.,][0-9]+)?)")
_VIRG = re.compile(r"(?<=[0-9]),(?=[0-9])")
#: literal numérico da fórmula → Decimal (misturar float com Decimal estoura em Python)
_LIT = re.compile(r"(?<![\w.'])([0-9]+(?:\.[0-9]+)?)")


def qtd_da_referencia(ref: str) -> Decimal | None:
    """A QUANTIDADE que o motor gravou no holerite: «91.00h noturnas (escala)» → 91,00;
    «4 dia(s) sem justificativa» → 4. Sem número (reflexo do DSR) → None."""
    m = _NUM.match(ref or "")
    return Decimal(m.group(1).replace(",", ".")) if m else None


def avaliar(formula: str, vars_: dict) -> Decimal:
    """Avalia a fórmula do CADASTRO, escrita como se lê: «arred(salario_base ÷ 30) × dias».

    `×`→`*`, `÷`→`/`, vírgula decimal→ponto, `arred(x)` = o arredondamento do motor. Só os nomes
    de `vars_` existem no escopo — nada de builtins."""
    expr = _VIRG.sub(".", (formula or "").replace("×", "*").replace("÷", "/").replace("−", "-"))
    expr = _LIT.sub(r"D('\1')", expr)
    amb = {k: (v if isinstance(v, Decimal) else Decimal(str(v))) for k, v in vars_.items()}
    amb["arred"], amb["D"] = _r, Decimal
    # Expressão aritmética do CADASTRO, avaliada só aqui (nunca num caminho de requisição), sem
    # builtins e só com os nomes de `vars_`. `ast.literal_eval` não serve: é aritmética com
    # variáveis, não um literal.
    return _r(eval(expr, {"__builtins__": {}}, amb))  # noqa: S307  # nosec B307


def _brl(v) -> str:
    return f"R$ {Decimal(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def main() -> int:  # noqa: C901, PLR0912, PLR0915
    import json

    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []

    # (f) fiação — tela sem porta não existe
    try:
        from modules.operacional.controllers.redesign_builders import _dp_grupos as g
        from modules.operacional.controllers.redesign_builders import departamento_pessoal as dp

        if "_dgx_w5" not in inspect.getsource(dp.build):
            falhas.append("departamento_pessoal.build() não chama _dgx_w5_mapa_evento_rubrica.telas")
        abas = {tid for _g, _t, _s, tabs in g.GRUPOS for tid, _l in tabs}
        for tid in ("ponto-evento-rubrica", "ponto-evento-rubrica-nova"):
            if tid not in abas:
                falhas.append(f"aba {tid} não está em _dp_grupos.GRUPOS — tela sem porta")
    except Exception as e:  # noqa: BLE001
        falhas.append(f"fiação do builder: {type(e).__name__}: {e}")

    try:
        from modules.people_management.folha.services.mapa_evento_rubrica import (
            CARGO_CCT_ALIAS,
            EVENTOS,
            _ensure,
            mapa_evento_rubrica,
        )
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: mapa_evento_rubrica não importa: {type(e).__name__}: {e}")
        print("TOTAL desvios: 1")
        return 1

    async with async_session_factory() as db:
        await _ensure(db)
        regras = [dict(r) for r in (await db.execute(text(SQL_MAPA), {"ref": date.today()})).mappings().all()] or []
        # (d) origem obrigatória
        for r in regras:
            if not (r["origem_regra"] or "").strip():
                falhas.append(f"(d) linha {r['id']} ({r['evento']}→{r['rubrica_codigo']}) sem origem_regra")

        #: códigos que o mapa reivindica — é isso que vamos exigir que ele explique no holerite
        por_codigo: dict[str, list[dict]] = {}
        for r in regras:
            por_codigo.setdefault(r["rubrica_codigo"], []).append(r)
        cods = sorted(por_codigo)
        #: eventos que o motor produz (levantado do holerite, não de constante)
        produzidos = {e for e, meta in EVENTOS.items() if meta.get("produzido")}
        sem_linha = produzidos - {r["evento"] for r in regras}
        for e in sorted(sem_linha):
            falhas.append(f"(c) evento '{e}' é produzido pelo motor e não tem linha no mapa")

        comps = (await db.execute(text(SQL_COMPETENCIAS))).fetchall()
        if not comps:
            falhas.append("nenhuma competência do motor próprio em hr_payslips — não há o que explicar")
        alias = json.dumps(CARGO_CCT_ALIAS)

        total_linhas = 0
        soma_delta = Decimal("0")
        divergentes: list[str] = []
        por_evento: dict[str, int] = {}
        for ano, mes in comps:
            if not cods:
                break
            rows = (
                (await db.execute(text(SQL_VERBAS), {"a": ano, "m": mes, "cods": cods, "alias": alias}))
                .mappings()
                .all()
            )
            valor_he: dict[str, Decimal] = {
                r["employee_id"]: Decimal(str(r["valor"])) for r in rows if r["codigo"] == "0040"
            }
            for r in rows:
                total_linhas += 1
                escala = r["escala"] or "12x36"
                divisor = 180 if escala == "12x36" else 220
                base = Decimal(str(r["base"] or 0))
                qtd = qtd_da_referencia(r["referencia"]) or Decimal(0)
                ambiente = {
                    "horas": qtd,
                    "dias": qtd,
                    "plantoes": qtd,
                    "valor_hora": _r(base / divisor),
                    "salario_base": base,
                    "salario_minimo": Decimal("1518.00"),
                    "piso_cct": base,
                    "ronda": Decimal(str(r["ronda"] or 0)) / 100,
                    "valor_he": valor_he.get(r["employee_id"], Decimal(0)),
                    "fator_dsr": _fator_dsr(escala, mes, ano),
                }
                # (a) o mapa resolve o MESMO código que o motor emitiu, para ESTA pessoa
                candidatas = por_codigo.get(r["codigo"], [])
                if not candidatas:
                    falhas.append(f"(a) {r['codigo']} no holerite de {r['nome']} ({mes:02d}/{ano}) sem linha no mapa")
                    continue
                evento = candidatas[0]["evento"]
                por_evento[evento] = por_evento.get(evento, 0) + 1
                resolvida = await mapa_evento_rubrica(db, evento, employee_id=r["employee_id"])
                if not resolvida:
                    falhas.append(f"(a) cascata não resolve '{evento}' para {r['nome']} — o motor emitiu {r['codigo']}")
                    continue
                if resolvida["rubrica_codigo"] != r["codigo"]:
                    falhas.append(
                        f"(a) {r['nome']} {mes:02d}/{ano}: motor emitiu {r['codigo']} e o mapa resolve "
                        f"{resolvida['rubrica_codigo']} para '{evento}'"
                    )
                    continue
                # (b) o VALOR recomposto pela fórmula do mapa
                try:
                    recomposto = avaliar(resolvida["formula"], ambiente)
                except Exception as e:  # noqa: BLE001
                    falhas.append(f"(b) fórmula de '{evento}' não avalia ({resolvida['formula']!r}): {e}")
                    continue
                delta = abs(recomposto - Decimal(str(r["valor"])))
                soma_delta += delta
                if delta > TOL:
                    divergentes.append(
                        f"(b) {r['nome']} {mes:02d}/{ano} {r['codigo']} ({evento}) ref={r['referencia']!r}: "
                        f"holerite {_brl(r['valor'])} × mapa {_brl(recomposto)} — Δ {_brl(delta)}"
                    )
        falhas.extend(divergentes[:40])
        if len(divergentes) > 40:
            falhas.append(f"(b) … e mais {len(divergentes) - 40} linha(s) divergentes")
        if soma_delta > TOL:
            falhas.append(f"(b) Σ|Δ| = {_brl(soma_delta)} — esperado R$ 0,00")

        # (e) a cascata: colaborador vence empresa
        emp_id = (
            await db.execute(text("SELECT id::text FROM employees WHERE status='ativo' ORDER BY nome LIMIT 1"))
        ).scalar()
        alvo = next((r for r in regras if r["escopo"] == "empresa"), None)
        if emp_id and alvo:
            try:
                await db.execute(
                    text(
                        "INSERT INTO ponto_evento_rubrica (evento, rubrica_codigo, escopo, escopo_id, formula, base, "
                        "percentual, origem_regra, criado_por) VALUES (:ev, 'ZZ99', 'colaborador', :e, "
                        "'horas × valor_hora × 1,5', 'valor_hora', 1.5, :o, 'oraculo-w5')"
                    ),
                    {"ev": alvo["evento"], "e": emp_id, "o": f"{FIX} — cascata"},
                )
                await db.commit()
                venceu = await mapa_evento_rubrica(db, alvo["evento"], employee_id=emp_id)
                outro = await mapa_evento_rubrica(db, alvo["evento"], employee_id=None)
                if not venceu or venceu["rubrica_codigo"] != "ZZ99":
                    falhas.append(
                        f"(e) cascata: linha de colaborador não venceu a de empresa em '{alvo['evento']}' "
                        f"(resolveu {venceu and venceu['rubrica_codigo']})"
                    )
                if not outro or outro["rubrica_codigo"] != alvo["rubrica_codigo"]:
                    falhas.append("(e) cascata: sem colaborador deveria resolver a linha de empresa")
            finally:
                await db.execute(text("DELETE FROM ponto_evento_rubrica WHERE origem_regra LIKE :f"), {"f": f"{FIX}%"})
                await db.commit()
        else:
            falhas.append("(e) sem empregado ativo ou sem linha de empresa — cascata não pôde ser provada")

        n_fix = (
            await db.execute(
                text("SELECT count(*) FROM ponto_evento_rubrica WHERE origem_regra LIKE :f"), {"f": f"{FIX}%"}
            )
        ).scalar()
        if n_fix:
            falhas.append(f"(e) {n_fix} fixture(s) '{FIX}' não foram apagadas")

    comp_txt = " e ".join(f"{m:02d}/{a}" for a, m in comps) if comps else "—"
    print(
        f"{comp_txt} · mapa com {len(regras)} linha(s) · {len(produzidos)} evento(s) produzidos pelo motor · "
        f"{total_linhas} verba(s) de ponto no holerite · divergentes: {len(divergentes)} · Σ|Δ| = {_brl(soma_delta)}"
    )
    if por_evento:
        print("por evento: " + " · ".join(f"{e}={n}" for e, n in sorted(por_evento.items())))
    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL desvios: {len(falhas)}")
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) no mapa evento→rubrica")
    print(
        "OK mapa evento→rubrica: todo evento produzido tem linha, o código resolvido == o emitido, "
        "o valor recomposto pela fórmula == o do holerite (Σ|Δ| = R$ 0,00), cascata resolve, origem em todas"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
