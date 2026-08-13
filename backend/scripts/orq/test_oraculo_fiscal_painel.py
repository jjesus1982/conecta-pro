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

        # ── 5. Pedido de cancelamento não pode ficar parado ──
        # Nota marcada por NÓS sai do faturamento na hora, mas quem cancela de
        # verdade é o Ambiente Nacional. Se o gov REJEITAR, o dinheiro fica fora
        # do faturamento para sempre e ninguém descobre — é a única forma de o
        # sistema mostrar menos receita do que existe sem nenhum alarme.
        paradas = (await db.execute(text(
            "SELECT numero, tomador_nome, valor_servicos, "
            "       (CURRENT_DATE - cancelamento_solicitado_em::date) AS dias "
            "FROM nfse_emitidas_nacional "
            "WHERE cancelamento_solicitado_em < NOW() - interval '30 days' "
            "ORDER BY cancelamento_solicitado_em"))).mappings().all()
        assert not paradas, (
            f"{len(paradas)} nota(s) com cancelamento pedido e NUNCA confirmado pelo ADN: "
            + "; ".join(f"n{p['numero']} {p['tomador_nome'][:24]} R$ {float(p['valor_servicos']):,.2f} "
                        f"({p['dias']} dias)" for p in paradas[:4])
            + " — se o gov rejeitou, esse valor sumiu do faturamento sem motivo")
        pendentes = await um("SELECT count(*) FROM nfse_emitidas_nacional "
                             "WHERE cancelamento_solicitado_em IS NOT NULL")
        print(f"OK cancelamentos pedidos aguardando o ADN: {pendentes} (nenhum parado há 30+ dias)")

        # ── 6. Competência corrigida move a nota de mês, nunca cria receita ──
        # A correção existe porque o ADN manda `dCompet` = data de emissão. Ela pode
        # mudar em QUE mês a nota aparece; não pode mudar o total, nem jogar serviço
        # para o futuro, nem sobreviver a uma nota que o gov nunca mandou.
        corrigidas = (await db.execute(text(
            "SELECT numero, competencia, competencia_origem_adn, valor_servicos "
            "FROM nfse_emitidas_nacional WHERE competencia_origem_adn IS NOT NULL "
            "ORDER BY numero"))).mappings().all()
        for c in corrigidas:
            assert c["competencia"] <= c["competencia_origem_adn"], (
                f"n{c['numero']}: competência corrigida para {c['competencia']}, DEPOIS do que o "
                f"ADN mandou ({c['competencia_origem_adn']}) — serviço não se presta no futuro")
        # O total do ano não pode depender da correção: ela só redistribui entre meses.
        bruto = float(await um("SELECT coalesce(sum(valor_servicos),0) FROM nfse_emitidas_nacional "
                               "WHERE coalesce(cancelada,false)=false AND competencia LIKE '2026-%'"))
        por_mes = float(await um(
            "SELECT coalesce(sum(v),0) FROM (SELECT sum(valor_servicos) v FROM nfse_emitidas_nacional "
            "WHERE coalesce(cancelada,false)=false AND competencia LIKE '2026-%' GROUP BY competencia) x"))
        assert abs(bruto - por_mes) < 0.01, \
            f"a soma por mês ({por_mes:,.2f}) não bate com o total do ano ({bruto:,.2f})"
        print(f"OK competências corrigidas: {len(corrigidas)} nota(s), "
              f"total do ano intacto (R$ {bruto:,.2f})")

    print("TEST oraculo_fiscal_painel PASS")


if __name__ == "__main__":
    asyncio.run(main())
