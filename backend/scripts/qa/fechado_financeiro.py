#!/usr/bin/env python3
"""Critério de aceite EXECUTÁVEL do Financeiro (fechamento de 06/09/2026, etapa 2 do plano).

Sai 0 só quando as 6 condições passam. Enquanto sair vermelho, o módulo não fechou.
Mesma forma dos outros fechado_*: cada condição imprime ✅/❌ com o número que a sustenta,
e o exit code decide. Entra no gate semanal de checar_regressao (conta ✅, acusa quando cai).

As 6, e por que cada uma existe:
  1. extrato    oráculo do extrato verde — o Inter ficou 14 dias sem sincronizar com o beat
                "succeeded" (constraint inexistente engolida); a divergência era R$ 5.260,83
  2. inter vivo bank_transactions do Inter tem linha de até 2 dias atrás — "verde ontem"
                não vale se o sync morrer calado de novo
  3. recebíveis oráculo dos recebíveis verde (o oráculo agrupava por cliente+valor e acusava
                dois meses iguais como "dobrado"; corrigido para agrupar por título)
  4. contábil   balanço e fechamento contábil verdes — a quarentena de tabelas derrubou a
                seção contábil inteira por causa de fin_cost_centers, e só o oráculo viu
  5. baixa      o beat auto_baixa NÃO falhou nos últimos 7 dias (task_falha no sino) e há
                consumidor na fila. Primeira versão exigia "rascunho de baixa em 7 dias" e
                reprovava por decisão de negócio: o beat propor_baixa_pendentes está atrás
                de CONECTA_PROPOR_BAIXA=0 de propósito (celery_app.py) — os 36 rascunhos
                são todos de 13/08, quando o flag esteve ligado. Gate não mede decisão
  6. telas      o builder do redesign entrega as telas-chave com KPI (g-visao, g-pagar,
                g-receber, balanco-patrimonial, g-bancos)

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/fechado_financeiro.py
"""
from __future__ import annotations

import asyncio
import subprocess
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/scripts/orq")

INTER = "20663dc9-805c-4721-bc1f-62a041cee3c1"
FALHAS: list[str] = []


def ok(cond: bool, nome: str, detalhe: str = "") -> None:
    print(f"  {'✅' if cond else '❌'} {nome}" + (f" — {detalhe}" if detalhe else ""))
    if not cond:
        FALHAS.append(nome)


def _oraculo(nome: str) -> tuple[bool, str]:
    r = subprocess.run([sys.executable, f"/app/scripts/orq/{nome}.py"], capture_output=True, text=True, timeout=600)
    ultima = (r.stdout.strip().splitlines() or [""])[-1][:90]
    return r.returncode == 0, ultima


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    import main_production  # noqa: F401 — antes de medir qualquer registro

    print("== fechado_financeiro ==")
    v, d = _oraculo("test_oraculo_extrato"); ok(v, "1. extrato: oráculo verde", d)
    async with async_session_factory() as db:
        dias = (await db.execute(text(
            "SELECT current_date - max(transaction_date)::date FROM bank_transactions WHERE bank_account_id::text = :c"),
            {"c": INTER})).scalar()
        ok(dias is not None and dias <= 2, "2. Inter vivo: última linha há ≤2 dias", f"{dias} dia(s)")
    v, d = _oraculo("test_oraculo_recebiveis"); ok(v, "3. recebíveis: oráculo verde", d)
    v1, d1 = _oraculo("test_oraculo_balanco"); v2, d2 = _oraculo("test_oraculo_contabil_fecha")
    ok(v1 and v2, "4. contábil: balanço + fechamento verdes", d2 if not v2 else d1)
    async with async_session_factory() as db:
        falhas = (await db.execute(text(
            "SELECT count(*) FROM communication_notifications WHERE extra_data->>'origem' = 'task_falha' "
            "AND extra_data->>'tarefa' LIKE 'financial.auto_baixa%' AND created_at > now() - interval '7 days'"))).scalar()
        from celery_app import app as celery
        filas = set()
        try:
            for w, qs in (celery.control.inspect(timeout=5).active_queues() or {}).items():
                filas |= {q["name"] for q in qs}
        except Exception:  # noqa: BLE001 — sem broker, fica vazio e reprova
            pass
        fila = (celery.conf.beat_schedule.get("financeiro-auto-baixa-pagaveis") or {}).get("options", {}).get("queue")
        ok((falhas or 0) == 0 and fila in filas, "5. baixa: beat sem falha em 7 dias e com consumidor",
           f"{falhas} falha(s); fila {fila} {'ouvida' if fila in filas else 'SEM consumidor'}")
        from _fixtures import tela
        from modules.operacional.controllers.redesign_builders.financeiro import build
        out = await build(db)
        faltam = [s for s in ("g-visao", "g-pagar", "g-receber", "balanco-patrimonial", "g-bancos")
                  if not (isinstance(tela(out, s), dict) and (tela(out, s).get("kpis") or tela(out, s).get("panels") or tela(out, s).get("tabs")))]
        ok(not faltam, "6. telas-chave do redesign com conteúdo", f"{len(out)} telas; faltam {faltam}" if faltam else f"{len(out)} telas")
    print(f"\n{'FECHADO' if not FALHAS else 'NÃO FECHOU'}: {6 - len(FALHAS)}/6" + (f" — {', '.join(FALHAS)}" if FALHAS else ""))
    return 0 if not FALHAS else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
