"""Oráculo do balanço: Ativo = Passivo + PL, e a apuração não fica pela metade.

Em 13/08/2026 o razão tinha **zero lançamentos no grupo 3.x**. Receita e despesa
acumulavam desde 2022 sem nunca serem encerradas: o patrimônio existia escondido
dentro das contas de resultado, onde ninguém o lê como patrimônio, e 2027 somaria
em cima de 2026.

O que este oráculo trava:
  (a) o balanço FECHA — Ativo = Passivo + PL + resultado ainda aberto;
  (b) a conta de passagem `3.3.1.01` volta a ZERO. Ela recebe receita e despesa
      no encerramento e se esvazia na mesma operação; saldo sobrando significa
      apuração pela metade — e o balanço fecharia mentindo, porque o valor está
      pendurado no PL sem ter saído do resultado;
  (c) competência FECHADA não fica com saldo de resultado em aberto;
  (d) nenhum lançamento em conta 3.x DESATIVADA. `3.1.1 Portaria`, `3.1.2
      Vigilância`, `3.1.3 Limpeza` e `3.2.1 ISS 5%` estavam dentro do PL — linha
      de serviço e alíquota de imposto no lugar de patrimônio. Foram desativadas
      (não apagadas: outro razão as referencia por FK), e voltar a usá-las é
      regressão.

Roda:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_balanco.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

TOLERANCIA = 0.01


async def _saldo(db, prefixo: str) -> float:
    """Saldo DEVEDOR do grupo (débitos − créditos)."""
    return float(
        (
            await db.execute(
                text(
                    f"SELECT coalesce(sum(CASE WHEN conta_debito LIKE '{prefixo}%' THEN valor ELSE 0 END), 0) "
                    f"     - coalesce(sum(CASE WHEN conta_credito LIKE '{prefixo}%' THEN valor ELSE 0 END), 0) "
                    f"FROM accounting_entries"
                )
            )
        ).scalar()
        or 0
    )


async def main() -> None:
    falhas: list[str] = []
    async with async_session_factory() as db:
        # ── (a) o balanço fecha ──────────────────────────────────────────────
        ativo = await _saldo(db, "1")
        passivo = -await _saldo(db, "2")
        pl = -await _saldo(db, "3")
        resultado = -await _saldo(db, "4") - await _saldo(db, "5")
        dif = round(ativo - (passivo + pl + resultado), 2)
        if abs(dif) > TOLERANCIA:
            falhas.append(
                f"balanço NÃO fecha por R$ {dif:,.2f} — ativo R$ {ativo:,.2f} contra "
                f"passivo R$ {passivo:,.2f} + PL R$ {pl:,.2f} + resultado R$ {resultado:,.2f}"
            )
        else:
            print(
                f"OK balanço fecha: ativo R$ {ativo:,.2f} = passivo R$ {passivo:,.2f} "
                f"+ PL R$ {pl:,.2f} + resultado em curso R$ {resultado:,.2f}"
            )

        # ── (b) a conta de passagem está vazia ───────────────────────────────
        passagem = round(await _saldo(db, "3.3.1.01"), 2)
        if abs(passagem) > TOLERANCIA:
            falhas.append(
                f"conta de apuração 3.3.1.01 com saldo de R$ {passagem:,.2f} — a apuração "
                f"ficou pela metade e o balanço fecha mentindo"
            )
        else:
            print("OK conta de apuração vazia: a apuração não ficou pela metade")

        # ── (c) competência fechada sem resultado em aberto ──────────────────
        hoje = date.today()
        # O saldo tem que somar OS DOIS LADOS: o encerramento CREDITA 5.x e DEBITA
        # 4.x, então uma fórmula que só olha `conta_debito LIKE '5%'` enxerga a
        # despesa original e ignora a baixa — e acusa competência já encerrada.
        # (Foi o que aconteceu na primeira versão: 42 falsos positivos.)
        abertas = (
            (
                await db.execute(
                    text("""
            WITH mov AS (
                SELECT periodo_competencia AS comp, conta_debito AS conta, valor AS v
                  FROM accounting_entries WHERE periodo_competencia IS NOT NULL
                UNION ALL
                SELECT periodo_competencia, conta_credito, -valor
                  FROM accounting_entries WHERE periodo_competencia IS NOT NULL
            )
            SELECT comp, round(sum(v), 2) AS saldo
            FROM mov
            WHERE comp < :mes AND (conta LIKE '4%' OR conta LIKE '5%')
            GROUP BY 1 HAVING abs(sum(v)) > 0.01 ORDER BY 1
        """),
                    {"mes": f"{hoje:%Y-%m}"},
                )
            )
            .mappings()
            .all()
        )
        if abertas:
            falhas.append(
                f"{len(abertas)} competência(s) FECHADA(s) com resultado em aberto: "
                f"{', '.join(a['comp'] for a in abertas[:6])} — rode a apuração"
            )
        else:
            print("OK toda competência fechada foi encerrada contra o PL")

        # ── (d2) a apuração FECHA RESÍDUO de lançamento retroativo ───────────
        # 18/09/2026: 2026-08 foi apurada em 07/09 e DEPOIS chegaram uma folha manual de
        # R$ 132.524,09 e notas tomadas até 17/09. Sobraram R$ 21.175,06 abertos, o balanço
        # acusando todo dia, e a apuração se RECUSANDO a rodar: o `documento_ref` dizia que
        # ela já tinha rodado, e o saldo era calculado ignorando os próprios lançamentos de
        # apuração — então rodar de novo fecharia o mês inteiro em dobro.
        #
        # Consertado na raiz: o saldo passa a incluir a apuração (vira o RESÍDUO de verdade) e
        # a idempotência vem de «não sobrou nada», que é fato, não de «já rodei», que é
        # lembrança. Esta trava afirma as DUAS metades — senão a próxima pessoa "conserta" uma
        # e reabre a outra.
        from modules.financial.services.apuracao_resultado import apurar  # noqa: PLC0415

        fechada = f"{hoje.year}-{hoje.month - 1:02d}" if hoje.month > 1 else f"{hoje.year - 1}-12"
        seca = apurar(fechada, preview=True)
        if seca.get("ok") and int(seca.get("contas_encerradas") or 0) != 0:
            falhas.append(
                f"a apuração de {fechada} quer encerrar {seca['contas_encerradas']} conta(s) de "
                f"novo (R$ {seca.get('resultado')}) — ou ficou resíduo aberto, ou ela voltou a "
                f"calcular o saldo ignorando os próprios lançamentos e fecharia em DOBRO"
            )
        else:
            print(f"OK a apuração de {fechada} não tem o que encerrar — idempotente pelo FATO")

        # ── (e) o DRE concorda com a apuração ────────────────────────────────
        # Dois caminhos independentes para o mesmo número: o DRE agrega 4.x/5.x
        # por competência; a apuração encerra essas contas contra o PL. Se
        # divergirem, um dos dois está lendo o plano de contas errado — foi
        # exatamente o que aconteceu até 13/08, quando o DRE tratava `4.1.1` como
        # "pessoal" (plano antigo) e mostrava a RECEITA de julho como CUSTO.
        for comp in ("2026-06", "2026-07"):
            dre = float(
                (
                    await db.execute(
                        text("""
                WITH mov AS (
                    SELECT conta_debito AS conta, valor AS v FROM accounting_entries
                     WHERE status='confirmado' AND coalesce(tipo_lancamento,'') <> 'apuracao'
                       AND periodo_competencia = :c
                    UNION ALL
                    SELECT conta_credito, -valor FROM accounting_entries
                     WHERE status='confirmado' AND coalesce(tipo_lancamento,'') <> 'apuracao'
                       AND periodo_competencia = :c
                )
                SELECT -coalesce(sum(v), 0) FROM mov
                WHERE conta LIKE '4%' OR conta LIKE '5%'
            """),
                        {"c": comp},
                    )
                ).scalar()
                or 0
            )
            apu = float(
                (
                    await db.execute(
                        text("""
                SELECT coalesce(sum(CASE WHEN conta_credito = '3.2.1.01' THEN valor
                                         ELSE -valor END), 0)
                FROM accounting_entries
                WHERE tipo_lancamento = 'apuracao' AND periodo_competencia = :c
                  AND (conta_debito = '3.2.1.01' OR conta_credito = '3.2.1.01')
            """),
                        {"c": comp},
                    )
                ).scalar()
                or 0
            )
            if abs(round(dre - apu, 2)) > TOLERANCIA:
                falhas.append(
                    f"{comp}: o DRE diz R$ {dre:,.2f} e a apuração levou R$ {apu:,.2f} ao PL "
                    f"— diferença de R$ {dre - apu:,.2f}; um dos dois lê o plano errado"
                )
            else:
                print(f"OK {comp}: DRE R$ {dre:,.2f} = resultado levado ao PL")

        # ── (d) conta desativada do PL não volta a ser usada ─────────────────
        mortas = (
            (
                await db.execute(
                    text("""
            SELECT c.code, count(*) AS n
            FROM fin_accounting_accounts c
            JOIN accounting_entries a
              ON a.conta_debito = c.code OR a.conta_credito = c.code
            WHERE c.code LIKE '3%' AND c.status <> 'ACTIVE'
            GROUP BY 1
        """)
                )
            )
            .mappings()
            .all()
        )
        if mortas:
            falhas.append(
                "lançamento em conta de PL DESATIVADA: "
                + ", ".join(f"{m['code']} ({m['n']})" for m in mortas)
                + " — linha de serviço/alíquota não é patrimônio"
            )
        else:
            print("OK nenhuma conta desativada do PL voltou a ser usada")

    # ── (f) o beat VARRE resíduo, não só o mês anterior ──────────────────
    # A task de apuração roda dia 5 e fecha a competência ANTERIOR. Só isso deixa um buraco
    # permanente: competência já apurada que recebe lançamento DEPOIS nunca mais é
    # revisitada, porque no mês seguinte a task olha outro mês. Foi assim que 42
    # competências ficaram abertas desde 2022, e aconteceu de novo em 2026-08 — apurada em
    # 07/09 e reaberta pelas NFS-e de agosto que o ADN só publicou em setembro
    # (R$ 15.139,00, fechados à mão em 25/09).
    #
    # As checagens acima medem o ESTADO, e o estado só fica vermelho meses depois de alguém
    # tirar a varredura. Esta mede o CÓDIGO — por AST, não por grep: a palavra aparece em
    # comentário, a CHAMADA não.
    import ast as _ast  # noqa: PLC0415
    import pathlib as _pathlib  # noqa: PLC0415

    _tasks = _pathlib.Path("/app/modules/financial/tasks.py")
    if not _tasks.exists():
        falhas.append("(f) modules/financial/tasks.py não existe — o beat não foi medido")
    else:
        _arv = _ast.parse(_tasks.read_text())
        _fn = next(
            (n for n in _ast.walk(_arv)
             if isinstance(n, _ast.FunctionDef) and n.name == "apurar_competencia_task"),
            None,
        )
        if _fn is None:
            falhas.append("(f) `apurar_competencia_task` sumiu de tasks.py")
        else:
            _chamadas = {
                c.func.id for c in _ast.walk(_fn)
                if isinstance(c, _ast.Call) and isinstance(c.func, _ast.Name)
            }
            if "_competencias_com_resultado_aberto" not in _chamadas:
                falhas.append(
                    "(f) a task de apuração NÃO varre competência anterior com resultado "
                    "aberto — lançamento retroativo volta a ficar órfão para sempre"
                )
            else:
                print("OK o beat varre resíduo de competência já apurada, não só o mês anterior")

    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        raise AssertionError(f"{len(falhas)} invariante(s) do balanço quebrada(s)")
    # ── a apuração é IDEMPOTENTE pelas REFERÊNCIAS, não só pelo fato ────────────────
    # Rodar a apuração duas vezes não pode criar dois lançamentos iguais. Em 26/09/2026
    # criou: o número da rodada era contado só nas referências `...-RESULTADO%`, e quando
    # uma rodada fechava contas que SE ANULAM (resultado zero, nenhuma linha de RESULTADO
    # postada) o número ficava gasto pelas contas e livre para o resultado. A chamada
    # seguinte reusava o número, o `WHERE NOT EXISTS` pulava a conta e o RESULTADO entrava
    # SOZINHO — transferência para o PL sem a contrapartida que a originou, duas vezes,
    # R$ 5.456,14 parados em `3.3.1.01`.
    dup = (await db.execute(text("""
        SELECT count(*) FROM (
            SELECT periodo_competencia, conta_debito, conta_credito, valor
              FROM accounting_entries
             WHERE documento_ref LIKE 'APURACAO-%-RESULTADO%'
             GROUP BY 1, 2, 3, 4 HAVING count(*) > 1) x
    """))).scalar() or 0
    if dup:
        falhas.append(
            f"{dup} transferência(s) de resultado ao PL em DUPLICIDADE — a apuração "
            "rodou duas vezes e o contador de rodada deixou passar"
        )
    else:
        print("OK apuração idempotente: nenhuma transferência de resultado repetida")

    print("TEST oraculo_balanco PASS")


if __name__ == "__main__":
    asyncio.run(main())
