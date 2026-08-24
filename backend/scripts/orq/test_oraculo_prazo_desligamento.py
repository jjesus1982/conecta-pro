#!/usr/bin/env python3
"""Nenhum prazo de desligamento ≤7 dias fica invisível para os vigias do DP.

O defeito real (13/08/2026): KEYSON DA SILVA PINTO, último dia de trabalho 14/08 — no dia
seguinte. Três leituras do mesmo fato e a única que avisa o RH lia o campo vazio:

    dp_aviso_previo_vencendo  → notice_start_date + notice_period_days  → NÃO o via
    coorte_ponto.py           → last_working_day                        → via
    tela "Aviso prévio" do DP → employees.status IN ('aviso_previo',…)  → 0 para sempre

`notice_start_date` estava preenchido em 1 de 3 processos; `last_working_day` em 3 de 3. A
regra lia só o campo esparso. Um prazo trabalhista de uma pessoa real ia vencer em silêncio.

Este oráculo NÃO procura o Keyson — ele some do banco quando o processo fechar, e um
oráculo que só sabe um nome morre com ele. Ele afirma a regra:

    (A) tudo que a VERDADE (escrita aqui, independente da regra) diz ser prazo ≤7 dias e
        ainda em curso, a regra `dp_aviso_previo_vencendo` tem que devolver;
    (B) suspensório contra a volta do defeito EXATO: um processo sintético com
        `notice_start_date` NULO e `last_working_day` daqui a 3 dias é enxergado.
        Sintético nasce e morre dentro de uma transação com ROLLBACK — nunca é commitado,
        porque este banco é produção.

(B) é o que mantém o oráculo com dentes quando a produção estiver limpa: sem ele, um banco
sem desligamento em curso deixa (A) verde sem provar nada.

Receita:
  docker exec -e PYTHONPATH=/app conecta-pro-backend \\
    python3 /app/scripts/orq/test_oraculo_prazo_desligamento.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402
from modules.notifications.proativo.regras import _detectar_aviso_previo  # noqa: E402

JANELA_DIAS = 7

# A VERDADE, escrita aqui e de propósito diferente da query da regra: pega o prazo por
# QUALQUER data disponível no processo, sem preferir uma leitura à outra. Copiar a query da
# regra provaria só que sei copiar — foi assim que o QA do fiscal aprovou 31 obrigações
# onde havia 5.
#
# `least()` do Postgres já ignora NULL: com as duas datas vazias devolve NULL, e `NULL <= x`
# é falso — o processo sem prazo nenhum sai da conta, que é o certo (não dá para cobrar um
# prazo que ninguém registrou; esse buraco quem conta é `sem_registro`, dentro da regra).
SQL_VERDADE = text(
    "SELECT id, nome, prazo FROM ("
    "  SELECT t.id::text AS id, e.nome AS nome, "
    "         least((t.notice_start_date "
    "                + (coalesce(t.notice_period_days,0) || ' days')::interval)::date, "
    "               t.last_working_day) AS prazo "
    "  FROM termination_processes t JOIN employees e ON e.id = t.employee_id "
    "  WHERE lower(coalesce(t.status::text,'')) NOT IN ('completed','cancelled')"
    ") v WHERE prazo <= current_date + CAST(:janela AS integer) "
    "ORDER BY prazo"
)


async def _ids_vistos_pela_regra(db) -> set[str]:
    """IDs de processo que a regra proativa efetivamente devolve.

    O correlation_id é `dp_aviso_previo:<id do processo>:<data fim>` — pego o pedaço do
    meio em vez de reexecutar a query da regra, para o oráculo depender do que ela ENTREGA
    e não de como ela pergunta.
    """
    return {a.correlation_id.split(":")[1] for a in await _detectar_aviso_previo(db)}



#: MARCA no `reason`. Esta é a pior tabela dos sete: uma rescisão órfã é um documento com
#: efeito legal, e o oráculo limpava pelo `id` que o INSERT retorna — se a execução morre por
#: sinal, o id se perde com ela e a linha fica INDISTINGUÍVEL de um desligamento real. Sem
#: marca não há como achá-la depois; é o caso extremo do "não dá para limpar o que não dá
#: para identificar".
_MARCA = "ZZORQ-PRAZO-DESLIGAMENTO — registro de teste, pode excluir"
_MARCAS_ANTIGAS: tuple[str, ...] = ()  # nunca houve marca aqui; nada antigo a varrer


async def _limpar_orfaos_de_entrada(db) -> int:
    """Apaga a rescisão sintética que sobrou de execução sem saída. Por MARCA, nunca por id."""
    n = 0
    for marca in (_MARCA, *_MARCAS_ANTIGAS):
        r = await db.execute(text(
            "DELETE FROM termination_processes WHERE strpos(coalesce(reason, ''), :m) > 0"),
            {"m": marca.split(" —")[0]})
        n += r.rowcount or 0
    if n:
        await db.commit()
    return n

async def main() -> int:
    falhas: list[str] = []

    async with async_session_factory() as db:
        # ENTRADA, antes de qualquer leitura: a rescisão órfã de uma execução morta entraria
        # na "produção real" que este próprio oráculo mede logo abaixo — resíduo virando
        # verdade de referência é o pior jeito de errar.
        _orf = await _limpar_orfaos_de_entrada(db)
        if _orf:
            print(f"entrada: {_orf} rescisão(ões) órfã(s) de teste removida(s)")

        # ── (A) contra a produção real ───────────────────────────────────────
        verdade = (await db.execute(SQL_VERDADE, {"janela": JANELA_DIAS})).mappings().all()
        vistos = await _ids_vistos_pela_regra(db)
        cegos = [r for r in verdade if r["id"] not in vistos]

        print(f"(A) prazos ≤{JANELA_DIAS}d em curso: {len(verdade)} · "
              f"vistos pela regra: {len(verdade) - len(cegos)}")
        for r in verdade:
            marca = "  " if r["id"] in vistos else "✗ "
            print(f"    {marca}{r['nome']} — prazo {r['prazo']}")
        if cegos:
            falhas.append(
                f"{len(cegos)} desligamento(s) com prazo ≤{JANELA_DIAS}d que NENHUMA regra "
                f"enxerga: {', '.join(r['nome'] for r in cegos)}"
            )

        # ── (B) suspensório: o defeito exato, em transação descartada ────────
        # Sem `last_working_day` como fallback, a regra devolve o sintético de fora e o
        # oráculo fica vermelho. É o defeito do Keyson reproduzido sob demanda.
        alvo = (await db.execute(text(
            "SELECT id::text FROM employees WHERE lower(coalesce(status,''))='ativo' LIMIT 1"
        ))).scalar()
        sid = None
        if not alvo:
            falhas.append("(B) NÃO VERIFICADO: nenhum employee ativo para o caso sintético")
        else:
            try:
                sid = (await db.execute(text(
                    "INSERT INTO termination_processes "
                    "  (employee_id, type, status, last_working_day, reason) "
                    "VALUES (CAST(:e AS uuid), 'involuntary', 'initiated', "
                    "        current_date + 3, :marca) "
                    "RETURNING id::text"
                ), {"e": alvo, "marca": _MARCA})).scalar()
                await db.flush()
                if sid in await _ids_vistos_pela_regra(db):
                    print("(B) caso sintético (notice_start_date NULO, último dia +3d): visto")
                else:
                    falhas.append(
                        "(B) a regra NÃO vê processo sem `notice_start_date` — o fallback "
                        "para `last_working_day` caiu; é o defeito do Keyson de volta"
                    )
            finally:
                # nunca commitado: o sintético não existe fora desta transação
                await db.rollback()

        # conferência do rollback pelo ID exato — contar por data pegaria processo legítimo
        if sid and (await db.execute(text(
            "SELECT count(*) FROM termination_processes WHERE id = CAST(:i AS uuid)"
        ), {"i": sid})).scalar():
            falhas.append(f"(B) VAZOU: o processo sintético {sid} ficou no banco")

    if falhas:
        for f in falhas:
            print(f"FALHA: {f}")
        print("TEST oraculo_prazo_desligamento FAIL")
        return 1
    print("TEST oraculo_prazo_desligamento PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
