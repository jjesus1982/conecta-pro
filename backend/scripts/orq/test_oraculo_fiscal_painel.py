"""Oráculo do painel FISCAL: os 4 KPIs batem com o banco, e batem pelo motivo certo.

Existia UM oráculo fiscal (`test_u2_fiscal`, só o dispatcher de leitura) para 22 telas — a
cobertura mais fina do sistema, no módulo de maior risco legal. Em 11/08/2026, dois dos
quatro KPIs do painel estavam errados e ninguém tinha como saber:

  • "Obrigações em aberto: 31" — o filtro excluía `('pago','paga','concluido','concluida')`,
    quatro grafias de "feito", e o vocabulário real da tabela é 'cumprida'/'pendente'. Toda
    obrigação CUMPRIDA contava como pendente: 31 anunciadas, 5 de verdade.
  • "Faturamento (12m)" — a janela ancorava na última nota do histórico (parado em
    29/12/2025) e somava só o arquivo, ignorando as 99 notas de 2026.

O QA de 09/08 conferiu que os números da tela batiam com as queries do builder e aprovou.
Batiam mesmo: a query é que estava errada. Por isso este oráculo não compara tela × query —
compara tela × VERDADE do banco, escrita de forma independente aqui.

Roda:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_fiscal_painel.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _fixtures import tela  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402
from modules.operacional.controllers.redesign_builders.fiscal import build  # noqa: E402


def _kpi(scr: dict, prefixo: str):
    """KPI pelo começo do rótulo — o texto varia (ex.: 'Certidões (3 vencidas)')."""
    for k in scr.get("kpis", []):
        if (k.get("l") or "").startswith(prefixo):
            return k
    return None


def _brl_para_float(v: str) -> float:
    """'R$ 3.140.234,54' -> 3140234.54"""
    return float(v.replace("R$", "").replace(".", "").replace(",", ".").strip())


async def main() -> None:
    async with async_session_factory() as db:
        painel = tela(await build(db), "painel")
        assert painel, "painel do fiscal não resolve"
        assert painel.get("type") == "dash", f"painel deixou de ser dash: {painel.get('type')}"

        async def um(q: str):
            return (await db.execute(text(q))).scalar()

        # ── 1. NFS-e emitidas (fonte autoritativa: a nacional, não o histórico) ──
        n_emit = await um("SELECT count(*) FROM nfse_emitidas_nacional")
        k = _kpi(painel, "NFS-e Emitidas")
        assert k and k["v"] == str(n_emit), f"NFS-e: tela {k and k['v']} != banco {n_emit}"
        print(f"OK NFS-e emitidas: {n_emit}")

        # ── 2. Certidões: vencida tem que APARECER, não sumir na contagem total ──
        n_cnd = await um("SELECT count(*) FROM ged_certidoes")
        venc = await um("SELECT count(*) FROM ged_certidoes WHERE expiry_date < CURRENT_DATE")
        k = _kpi(painel, "Certidões")
        assert k, "KPI de certidões sumiu do painel"
        if venc:
            assert str(venc) in (k["l"] or ""), \
                f"{venc} certidão(ões) vencida(s) e o rótulo não diz: {k['l']!r}"
            assert k["v"] == f"{n_cnd - venc}/{n_cnd}", f"contagem de certidões: {k['v']}"
            assert k.get("color") == "#C2410C", "certidão vencida tem que pintar de alerta"
        else:
            assert k["v"] == str(n_cnd), f"certidões: tela {k['v']} != banco {n_cnd}"
        print(f"OK certidões: {n_cnd} total, {venc} vencida(s) — {k['v']!r} / {k['l']!r}")

        # ── 3. Obrigações em aberto: só as PENDENTES ──
        pend = await um("SELECT count(*) FROM fiscal_obligations "
                        "WHERE lower(coalesce(status::text,'')) = 'pendente'")
        k = _kpi(painel, "Obrigações em aberto")
        assert k and k["v"] == str(pend), \
            (f"obrigações: tela {k and k['v']} != pendentes reais {pend}. "
             f"Se voltou a inflar, o filtro do builder perdeu alguma grafia de 'feito'.")
        # Suspenders: o total não pode virar o número da tela de novo (foi o defeito original).
        total = await um("SELECT count(*) FROM fiscal_obligations")
        if total != pend:
            assert k["v"] != str(total), "o KPI voltou a contar TODAS as obrigações como abertas"
        print(f"OK obrigações em aberto: {pend} (de {total} no total)")

        # ── 4. Faturamento 12m: janela a partir de HOJE, nas duas tabelas ──
        real = float(await um(
            "SELECT coalesce((SELECT sum(valor_servicos) FROM nfse_manaus_historico "
            "            WHERE data_emissao >= CURRENT_DATE - interval '12 months'), 0) "
            "     + coalesce((SELECT sum(valor_servicos) FROM nfse_emitidas_nacional "
            "            WHERE data_emissao >= CURRENT_DATE - interval '12 months'), 0)"))
        k = _kpi(painel, "Faturamento")
        assert k, "KPI de faturamento sumiu"
        exibido = _brl_para_float(k["v"])
        assert abs(exibido - real) < 0.01, f"faturamento 12m: tela {exibido} != banco {real}"
        # Suspenders: a âncora não pode voltar a ser a última nota do arquivo. Se voltar, o
        # valor congela no passado — o defeito não aparece hoje, aparece daqui a meses.
        ancorado = float(await um(
            "SELECT coalesce(sum(valor_servicos),0) FROM nfse_manaus_historico "
            "WHERE data_emissao >= (SELECT max(data_emissao) FROM nfse_manaus_historico) "
            "      - interval '12 months'"))
        if abs(ancorado - real) > 0.01:
            assert abs(exibido - ancorado) > 0.01, \
                "faturamento voltou a ancorar na última nota do histórico (congela no passado)"
        print(f"OK faturamento 12m: R$ {real:,.2f} (janela a partir de hoje, 2 tabelas)")

    print("TEST oraculo_fiscal_painel PASS")


if __name__ == "__main__":
    asyncio.run(main())
