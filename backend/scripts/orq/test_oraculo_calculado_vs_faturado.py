"""Oráculo — todo contrato ativo tem custo CALCULADO e valor FATURADO lado a lado, e a divergência
é publicada para o dono, nunca corrigida (12/09/2026).

Frente 7 do plano de paridade DigiExpress/DGX: a ficha deles mostra "Total Calculado vs Total
Faturado". O pré-mortem previu dois modos de falha: (i) quando a coluna aparecer, alguém vai
"ajustar o cálculo" para a divergência sumir; (ii) recalcular com reserva técnica vai virar
preço de contrato vigente — reajuste unilateral. Por isso este oráculo afirma o RELATÓRIO e
afirma a AUSÊNCIA de gatilho.

Três afirmações:

  1. Para CADA contrato ativo existe uma linha no relatório com `custo_calculado` (número, ou
     `motivo_sem_calculo` dizendo por quê — vazio real é "sem dado", nunca 0) e `faturado`
     (número com `fonte_faturado` = nfse|contrato, ou `motivo_sem_faturado`). Onde há os dois
     números, há `divergencia_reais` e `divergencia_pct`, e a conta bate.
  2. A tela do redesign (builder do crm, frente 07) publica essa mesma lista: tela
     `calculado-vs-faturado` com uma linha por contrato ativo.
  3. Rodar o relatório e a tela NÃO muda contrato nenhum: `monthly_value`/`updated_at` de todos
     os contratos são idênticos antes e depois.

Estado medido no nascimento (12/09/2026, staging): 15 contratos ativos, R$ 291.300,06/mês, e
nenhum lugar do sistema que compare custo calculado com faturado — VERMELHO por ImportError.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db

    falhas: list[str] = []
    gen = get_db()
    db = await gen.__anext__()

    ativos = (await db.execute(text(
        "SELECT contract_number FROM contracts WHERE status='active' ORDER BY 1"))).scalars().all()
    foto_antes = (await db.execute(text(
        "SELECT contract_number, monthly_value::text, updated_at::text FROM contracts ORDER BY 1"))).all()

    try:
        from modules.crm.services import precificacao_contrato as prec
    except ImportError as e:
        print(f"contratos ativos: {len(ativos)} · relatório: inexistente")
        print("FALHOU:", f"serviço calculado×faturado não existe: {e}")
        raise AssertionError("1 desvio(s): não há calculado × faturado")

    comp = date.today().strftime("%Y-%m")
    linhas = await prec.relatorio_calculado_vs_faturado(db, comp)
    por_ctr = {r.get("contract_number"): r for r in linhas}

    # 1) uma linha honesta por contrato ativo
    for n in ativos:
        r = por_ctr.get(n)
        if not r:
            falhas.append(f"{n}: ativo e fora do relatório")
            continue
        calc, fat = r.get("preco_calculado"), r.get("faturado")
        if not isinstance(calc, (int, float)) and not r.get("motivo_sem_calculo"):
            falhas.append(f"{n}: sem preco_calculado e sem motivo_sem_calculo")
        if isinstance(calc, (int, float)) and calc == 0:
            falhas.append(f"{n}: preco_calculado = 0 — zero não é 'sem dado'")
        if not isinstance(fat, (int, float)) and not r.get("motivo_sem_faturado"):
            falhas.append(f"{n}: sem faturado e sem motivo_sem_faturado")
        if isinstance(fat, (int, float)) and r.get("fonte_faturado") not in ("nfse", "contrato"):
            falhas.append(f"{n}: faturado sem fonte declarada ({r.get('fonte_faturado')!r})")
        if isinstance(calc, (int, float)) and isinstance(fat, (int, float)):
            esperado = round(fat - calc, 2)
            if r.get("divergencia_reais") != esperado:
                falhas.append(f"{n}: divergencia_reais={r.get('divergencia_reais')} ≠ faturado−calculado={esperado}")
            if calc and r.get("divergencia_pct") != round((fat - calc) / calc * 100, 2):
                falhas.append(f"{n}: divergencia_pct não bate")

    # 2) a tela publica a mesma lista
    try:
        from modules.operacional.controllers.redesign_builders._frente_07 import telas
        scr = (await telas(db)).get("calculado-vs-faturado")
        if not scr:
            falhas.append("tela 'calculado-vs-faturado' ausente no builder da frente 07")
        else:
            n_rows = len(scr.get("rows") or [])
            if n_rows != len(ativos):
                falhas.append(f"tela publica {n_rows} linhas, contratos ativos: {len(ativos)}")
            cols = " ".join(scr.get("cols") or []).lower()
            if "diverg" not in cols:
                falhas.append(f"tela sem coluna de divergência: {scr.get('cols')}")
    except ImportError as e:
        falhas.append(f"builder da frente 07 não existe: {e}")

    # 3) relatório não é gatilho
    foto_depois = (await db.execute(text(
        "SELECT contract_number, monthly_value::text, updated_at::text FROM contracts ORDER BY 1"))).all()
    if foto_antes != foto_depois:
        falhas.append("algum contrato MUDOU ao rodar o relatório — a divergência virou gatilho")

    com_diverg = sorted((r for r in linhas if isinstance(r.get("divergencia_reais"), (int, float))),
                        key=lambda r: r["divergencia_reais"])
    print(f"contratos ativos: {len(ativos)} · no relatório: {len(linhas)} · com os dois números: {len(com_diverg)}"
          + (f" · maior divergência: {com_diverg[0]['contract_number']} R$ {com_diverg[0]['divergencia_reais']:,.2f}"
             if com_diverg else ""))
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) em calculado × faturado")
    print("OK calculado × faturado: cada contrato ativo tem os dois números (ou o motivo), a tela publica "
          "a divergência e nenhum contrato mudou")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
