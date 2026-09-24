"""Oráculo — feriado trabalhado e HE 100%: o que a CCT manda pagar × o que a folha pagou (DGX X3).

24/09/2026. A W5 (§7) mediu: o motor de folha produz 8 dos 15 eventos do ponto, e entre os que
faltam estão `feriado_trabalhado` e `he100`. A rubrica `0011 Hora Extra 100%` existe em
`rubricas_folha` desde 03/2026 e **nunca foi emitida** por ninguém. Os feriados viraram dado com
ESCOPO na F7 (`cct_feriados`: nacional | estadual | municipal | cliente). Falta o cruzamento:
quem trabalhou em feriado, e o que recebeu por isso.

`folha_feriado_conferencia` é esse cruzamento — tabela PRÓPRIA, **paralelo cego**: nada nela muda
um centavo de holerite. Este oráculo é o que impede a tabela de virar ficção (e é a trava do dia
em que o motor passar a emitir a verba).

O que afirma:
  (a) `apurar` é idempotente — rodar 2× não duplica linha nenhuma;
  (b) a lista de quem trabalhou em feriado == a recontada por SQL PRÓPRIO deste arquivo, com a
      régua de escopo da F7 (nacional vale para todos; estadual/municipal só para o condomínio
      da mesma UF/cidade; CLIENTE só para aquele condomínio) e a régua do «um plantão é UM dia»
      (`shifts` como janela — a batida de 03:00 do 12x36 noturno é do plantão da véspera);
  (c) ninguém aparece por feriado de CLIENTE de outro condomínio (fixture 'FIXTURE DGX X3':
      feriado de cliente num condomínio, apagada ao fim mesmo em falha);
  (d) o valor pago lido em cada linha == o que o holerite daquela competência realmente tem
      (recontado aqui direto de `hr_payslips.earnings`);
  (e) **Σ|Δ| contra `hr_payslips` = R$ 0,00** — a apuração não tocou em nenhum holerite (a soma
      de proventos/descontos/líquido de TODOS os holerites das competências é idêntica antes e
      depois de apurar);
  (f) as linhas novas de `ponto_evento_rubrica` (`feriado_trabalhado` e `he100`) existem, têm
      `origem_regra` e nascem com «o motor usa? NÃO» (`EVENTOS[...]['produzido'] is False`);
  (g) fiação: `departamento_pessoal.build()` chama `_dgx_x3_feriado.telas` e as abas estão em
      `_dp_grupos` (tela sem porta não existe).

O que (b) e (d) produzem NÃO é uma estatística: é a lista nominal do passivo — nome, dia e valor.
Ela vai para o §1 do relatório.

Estado medido no nascimento (sandbox = cópia de produção, 24/09/2026): `folha_feriado_conferencia`
não existia e `feriado_conferencia` não importava → VERMELHO em tudo. 2 feriados em 07–09/2026
(05/09 estadual AM, 07/09 nacional), 57 turnos lançados neles, 126 batidas — e **zero** verba de
feriado ou de HE 100% em qualquer holerite de 2026.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL desvios: N`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from decimal import Decimal

FIX = "FIXTURE DGX X3"
TOL = Decimal("0.01")

#: As competências do §1 da frente. 07/2026 é backfill do espelho da Portte (verba copiada), mas
#: entra: o feriado trabalhado é um fato do PONTO, não do motor — e se lá houver passivo, é passivo.
COMPETENCIAS = ("2026-07", "2026-08", "2026-09")

#: Recontagem INDEPENDENTE de quem trabalhou em feriado. Não importa nada do serviço:
#:  · o dia do plantão sai da janela do turno (`shifts`, ±1h nas pontas; noturno cruza a
#:    meia-noite) e, sem turno que cubra a batida, do dia civil dela — a régua do horas_service
#:    escrita em SQL;
#:  · o feriado vale pelo ESCOPO da F7, comparado com a UF/cidade/id do condomínio da pessoa.
SQL_RECONTA = """
WITH emp AS (
  SELECT e.id::text AS employee_id, e.nome,
         (SELECT c.id FROM condominios c WHERE c.client_id = e.cliente_id ORDER BY c.ativo DESC LIMIT 1) AS cond_id
    FROM employees e),
dias AS (
  SELECT p.employee_id::text AS employee_id,
         CASE
           WHEN s.shift_date IS NOT NULL THEN s.shift_date
           -- sem turno que cubra a batida: ela é a continuação do plantão da VÉSPERA quando há
           -- batida do mesmo empregado no dia civil anterior a menos de 13h (o teto de um turno,
           -- `horas_service.MAX_TURNO_H`). É assim que a saída 06:10 do noturno que entrou
           -- 17:53 da véspera fica no dia da ENTRADA — a régua do «um plantão é UM dia».
           WHEN EXISTS (SELECT 1 FROM gp_clock_punches pa
                         WHERE pa.employee_id = p.employee_id
                           AND pa.punch_timestamp < p.punch_timestamp
                           AND pa.punch_timestamp::date = p.punch_timestamp::date - 1
                           AND p.punch_timestamp - pa.punch_timestamp <= interval '13 hours')
             THEN p.punch_timestamp::date - 1
           ELSE p.punch_timestamp::date
         END AS dia
    FROM gp_clock_punches p
    LEFT JOIN LATERAL (
      SELECT sh.shift_date FROM shifts sh
       WHERE sh.employee_id = p.employee_id
         AND lower(coalesce(sh.status,'')) <> 'cancelled' AND NOT coalesce(sh.is_off_day,false)
         AND sh.shift_date BETWEEN CAST(:de AS date) - 1 AND CAST(:ate AS date) + 1
         AND p.punch_timestamp BETWEEN (sh.shift_date + sh.planned_start_time - interval '1 hour')
             AND (sh.shift_date + sh.planned_end_time - interval '1 hour'
                  + CASE WHEN sh.planned_end_time < sh.planned_start_time THEN interval '25 hours'
                         ELSE interval '2 hours' END)
       ORDER BY sh.shift_date DESC, sh.planned_start_time DESC LIMIT 1) s ON true
   WHERE p.punch_timestamp >= CAST(:de AS date) - 1 AND p.punch_timestamp < CAST(:ate AS date) + 2)
SELECT DISTINCT d.employee_id, d.dia, f.nome
  FROM dias d
  JOIN emp ON emp.employee_id = d.employee_id
  LEFT JOIN condominios co ON co.id = emp.cond_id
  JOIN cct_feriados f ON f.data_feriado = d.dia AND coalesce(f.is_active, true)
   AND (coalesce(f.escopo,'nacional') = 'nacional'
     OR (f.escopo = 'estadual'  AND (f.uf IS NULL OR co.estado IS NULL OR upper(f.uf) = upper(co.estado)))
     OR (f.escopo = 'municipal' AND (f.municipio IS NULL OR co.cidade IS NULL OR lower(f.municipio) = lower(co.cidade)))
     OR (f.escopo = 'cliente'   AND f.condominio_id IS NOT NULL AND f.condominio_id = emp.cond_id))
 WHERE d.dia BETWEEN CAST(:de AS date) AND CAST(:ate AS date)
"""

#: (e) — a fotografia do dinheiro. Se esta soma mudar, a frente deixou de ser paralelo cego.
SQL_FOTO_FOLHA = """
SELECT coalesce(sum(total_earnings),0), coalesce(sum(total_deductions),0), coalesce(sum(net_salary),0), count(*)
  FROM hr_payslips
 WHERE (reference_year, reference_month) IN ((2026,7),(2026,8),(2026,9))
"""

#: (d) — o que o holerite tem, por pessoa e competência, nos códigos que pagariam feriado/HE 100%.
SQL_PAGO = """
SELECT p.employee_id::text, x->>'codigo', round(sum((x->>'valor')::numeric), 2)
  FROM hr_payslips p, jsonb_array_elements(coalesce(p.earnings,'[]'::jsonb)) x
 WHERE p.reference_year = :a AND p.reference_month = :m AND coalesce(p.status,'') <> 'cancelled'
   AND x->>'codigo' = ANY(CAST(:cods AS text[]))
 GROUP BY 1, 2
"""


def _brl(v) -> str:
    return f"R$ {Decimal(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def main() -> int:  # noqa: C901, PLR0912, PLR0915
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []

    # (g) fiação — tela sem porta não existe
    try:
        import inspect

        from modules.operacional.controllers.redesign_builders import _dp_grupos as g
        from modules.operacional.controllers.redesign_builders import departamento_pessoal as dp

        src = inspect.getsource(dp)
        if "_dgx_x3_feriado" not in src:
            falhas.append("(g) departamento_pessoal.py não chama a frente X3")
        abas = {a for _i, _l, _s, tabs in g.GRUPOS for a, _n in tabs}
        for tid in ("feriado-trabalhado", "feriado-apurar"):
            if tid not in abas:
                falhas.append(f"(g) aba '{tid}' não está em _dp_grupos.GRUPOS")
    except Exception as exc:  # noqa: BLE001
        falhas.append(f"(g) fiação não verificável: {exc}")

    try:
        from modules.people_management.folha.services.feriado_conferencia import (
            CODIGOS_PAGAM_FERIADO,
            apurar,
            linhas,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FALHOU: feriado_conferencia não importa: {type(exc).__name__}: {exc}")
        print("TOTAL desvios: 1")
        return 1

    total_linhas = 0
    passivo = Decimal("0")
    por_tipo: dict[str, int] = {}
    fix_id = None

    async with async_session_factory() as db:
        foto_antes = (await db.execute(text(SQL_FOTO_FOLHA))).first()

        # (f) as linhas novas do mapa (W5) — declaração, não caminho do motor.
        # `_ensure` primeiro: a semente das duas linhas nasce com a tabela desta frente.
        try:
            from modules.people_management.folha.services.feriado_conferencia import _ensure
            from modules.people_management.folha.services.mapa_evento_rubrica import EVENTOS

            await _ensure(db)

            mapa = {
                r[0]: (r[1], r[2])
                for r in (
                    await db.execute(
                        text(
                            "SELECT evento, rubrica_codigo, coalesce(origem_regra,'') FROM ponto_evento_rubrica "
                            "WHERE ativo AND evento = ANY(ARRAY['feriado_trabalhado','he100'])"
                        )
                    )
                ).all()
            }
            for ev in ("feriado_trabalhado", "he100"):
                if ev not in mapa:
                    falhas.append(f"(f) '{ev}' não tem linha ativa em ponto_evento_rubrica")
                elif len(mapa[ev][1].strip()) < 20:
                    falhas.append(f"(f) '{ev}' sem origem_regra que cite a regra ({mapa[ev][1]!r})")
                if EVENTOS.get(ev, {}).get("produzido"):
                    falhas.append(f"(f) '{ev}' está marcado como produzido pelo motor — o motor NÃO o emite")
            if "he100" in mapa and mapa["he100"][0] != "0011":
                falhas.append(f"(f) he100 deveria apontar para 0011, aponta para {mapa['he100'][0]}")
        except Exception as exc:  # noqa: BLE001
            falhas.append(f"(f) mapa evento→rubrica não verificável: {exc}")

        # (c) fixture: feriado de CLIENTE num condomínio — ninguém de fora pode aparecer por ele.
        #
        # Medido em 24/09/2026: `condominios.client_id` casa com `employees.cliente_id` em 1 de 63
        # ativos (e esse um não bate ponto). A cascata da F7/W5 resolve o condomínio por essa
        # junção, então sem fixture o teste nasceria CEGO — verde por não achar ninguém. A fixture
        # cria o condomínio que falta para UMA pessoa real e o feriado de cliente dela.
        alvo = (
            await db.execute(
                text(
                    "SELECT e.id::text, e.nome, e.cliente_id::text, p.punch_timestamp::date "
                    "  FROM employees e JOIN gp_clock_punches p ON p.employee_id = e.id "
                    # `clients` de verdade: 47 dos 63 ativos carregam um `cliente_id` ÓRFÃO
                    # (nenhuma linha em `clients`), e `condominios.client_id` tem FK — §7.
                    "  JOIN clients cl ON cl.id = e.cliente_id "
                    " WHERE p.punch_timestamp >= DATE '2026-08-05' AND p.punch_timestamp < DATE '2026-08-25' "
                    " GROUP BY 1,2,3,4 ORDER BY count(*) DESC LIMIT 1"
                )
            )
        ).first()
        conv = (await db.execute(text("SELECT id FROM cct_convencoes ORDER BY is_vigente DESC LIMIT 1"))).scalar()
        cond_fix = None
        dia_fix = alvo[3] if alvo else date(2026, 8, 14)
        if alvo and conv:
            cond_fix = (
                await db.execute(
                    text(
                        "INSERT INTO condominios (id, nome, client_id, ativo) "
                        "VALUES (gen_random_uuid(), :n, CAST(:cli AS uuid), true) RETURNING id::text"
                    ),
                    {"n": f"{FIX} — condomínio de teste", "cli": alvo[2]},
                )
            ).scalar()
            fix_id = (
                await db.execute(
                    text(
                        "INSERT INTO cct_feriados (id, convencao_id, data_feriado, nome, tipo, ano, is_active,"
                        " escopo, condominio_id, recorrente, observacao) "
                        "VALUES (gen_random_uuid(), :conv, :d, :n, 'municipal', 2026, true, 'cliente',"
                        " CAST(:c AS uuid), false, :obs) RETURNING id::text"
                    ),
                    {"conv": conv, "d": dia_fix, "n": f"{FIX} — feriado de cliente", "c": cond_fix, "obs": FIX},
                )
            ).scalar()
            await db.commit()

        try:
            for comp in COMPETENCIAS:
                ano, mes = int(comp[:4]), int(comp[5:7])

                # (a) idempotência — apurar 2×
                r1 = await apurar(db, comp)
                n1 = (
                    await db.execute(
                        text("SELECT count(*) FROM folha_feriado_conferencia WHERE competencia = :c"), {"c": comp}
                    )
                ).scalar()
                await apurar(db, comp)
                n2 = (
                    await db.execute(
                        text("SELECT count(*) FROM folha_feriado_conferencia WHERE competencia = :c"), {"c": comp}
                    )
                ).scalar()
                if n1 != n2:
                    falhas.append(f"(a) {comp}: apurar 2× duplicou — {n1} → {n2} linha(s)")
                if int(r1.get("linhas", -1)) != int(n1 or 0):
                    falhas.append(f"(a) {comp}: apurar disse {r1.get('linhas')} e a tabela tem {n1}")

                ls = await linhas(db, comp)
                total_linhas += len(ls)
                for ln in ls:
                    if str(ln["condominio"] or "").startswith(FIX):
                        continue  # linha da fixture de (c): não é passivo de verdade
                    por_tipo[ln["tipo"]] = por_tipo.get(ln["tipo"], 0) + 1
                    passivo += Decimal(str(ln["diferenca"]))

                # (b) a lista de feriado trabalhado == a recontada por SQL próprio
                de = date(ano, mes, 1)
                ate = date.fromordinal(date(ano + (mes == 12), (mes % 12) + 1, 1).toordinal() - 1)
                recont = {
                    (str(e), d) for e, d, _n in (await db.execute(text(SQL_RECONTA), {"de": de, "ate": ate})).all()
                }
                servico = {(ln["employee_id"], ln["data"]) for ln in ls if ln["tipo"] == "feriado_trabalhado"}
                for k in sorted(servico - recont):
                    falhas.append(f"(b) {comp}: {k[0]} em {k[1]:%d/%m} está na tabela e o SQL próprio não acha")
                for k in sorted(recont - servico):
                    falhas.append(f"(b) {comp}: {k[0]} trabalhou em feriado {k[1]:%d/%m} e a tabela não tem")

                # (c) o feriado de cliente da fixture só pode alcançar gente daquele condomínio
                if fix_id and comp == "2026-08":
                    do_dia = [ln for ln in ls if ln["data"] == dia_fix and ln["tipo"] == "feriado_trabalhado"]
                    if not any(ln["employee_id"] == alvo[0] for ln in do_dia):
                        falhas.append(
                            f"(c) {alvo[1]} é do condomínio do feriado de cliente, trabalhou em "
                            f"{dia_fix:%d/%m} e NÃO apareceu — a régua de escopo não alcança o cliente"
                        )
                    for ln in do_dia:
                        if not str(ln["condominio"] or "").startswith(FIX):
                            falhas.append(
                                f"(c) {ln['nome']} ({ln['condominio']}) apareceu por feriado de CLIENTE de outro "
                                f"condomínio em {dia_fix:%d/%m}"
                            )

                # (d) o valor pago lido == o do holerite (SQL próprio)
                pago_hol: dict[tuple[str, str], Decimal] = {
                    (str(e), c): Decimal(str(v))
                    for e, c, v in (
                        await db.execute(text(SQL_PAGO), {"a": ano, "m": mes, "cods": list(CODIGOS_PAGAM_FERIADO)})
                    ).all()
                }
                for ln in ls:
                    for cod, val in (ln.get("verbas") or {}).items():
                        esperado = pago_hol.get((ln["employee_id"], cod), Decimal("0"))
                        if abs(Decimal(str(val)) - esperado) > TOL:
                            falhas.append(
                                f"(d) {comp} {ln['nome']}: a linha diz {cod}={_brl(val)} e o holerite tem "
                                f"{_brl(esperado)}"
                            )

            # (e) Σ|Δ| contra hr_payslips = R$ 0,00
            foto_depois = (await db.execute(text(SQL_FOTO_FOLHA))).first()
            delta = sum(
                abs(Decimal(str(a or 0)) - Decimal(str(b or 0))) for a, b in zip(foto_antes, foto_depois, strict=True)
            )
            if delta != 0:
                falhas.append(f"(e) a apuração MEXEU nos holerites: Σ|Δ| = {_brl(delta)} (era paralelo cego)")
        finally:
            if fix_id:
                await db.execute(text("DELETE FROM cct_feriados WHERE id::text = :i"), {"i": fix_id})
                await db.execute(text("DELETE FROM folha_feriado_conferencia WHERE data = :d"), {"d": dia_fix})
                if cond_fix:
                    await db.execute(text("DELETE FROM condominios WHERE id::text = :i"), {"i": cond_fix})
                await db.commit()
                n_fix = (
                    await db.execute(
                        text(
                            "SELECT (SELECT count(*) FROM cct_feriados WHERE coalesce(observacao,'') LIKE :f) "
                            "     + (SELECT count(*) FROM condominios WHERE nome LIKE :f) "
                            "     + (SELECT count(*) FROM folha_feriado_conferencia WHERE condominio LIKE :f)"
                        ),
                        {"f": f"{FIX}%"},
                    )
                ).scalar()
                if n_fix:
                    falhas.append(f"(e) {n_fix} fixture(s) '{FIX}' não foram apagadas")

    print(
        f"{', '.join(COMPETENCIAS)} · {total_linhas} linha(s) de conferência · "
        + " · ".join(f"{k}={v}" for k, v in sorted(por_tipo.items()))
        + f" · passivo Σ = {_brl(passivo)} · Σ|Δ| nos holerites = R$ 0,00"
    )
    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL desvios: {len(falhas)}")
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) na conferência de feriado/HE 100%")
    print(
        "OK feriado/HE 100%: a lista de quem trabalhou em feriado == a recontada por SQL próprio com a régua de "
        "escopo, feriado de cliente não vaza para outro condomínio, o pago lido == o do holerite, "
        "Σ|Δ| nos holerites = R$ 0,00 e as linhas novas do mapa dizem «o motor NÃO usa»"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
