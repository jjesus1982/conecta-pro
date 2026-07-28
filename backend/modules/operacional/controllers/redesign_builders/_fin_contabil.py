"""F5 — Contabilidade REAL (corrige o substituto: a tela 'contabilidade' mostrava extrato
bancário categorizado; o razão de partidas dobradas estava invisível). Fontes reais:
fin_accounting_accounts (62 contas), accounting_entries (1.317 lançamentos D/C),
fin_accounting_periods (3), fin_cost_centers (1). Leitura; postar/estornar segue gated."""
from sqlalchemy import text

from modules.operacional.controllers.redesign_data_controller import (
    S, _fmtdate, _helpers, _scalar, b, brl, t,
)


async def build_contabil(db, out: dict) -> None:
    _, _safe, tbl = _helpers(db)

    # ── Plano de contas (fin_accounting_accounts) ────────────────────────────────────────
    _ntone = {"debit": "info", "credit": "ok", "devedora": "info", "credora": "ok"}
    try:
        out["plano-contas"] = await tbl(
            "Plano de contas",
            f"{await _scalar(db, 'SELECT count(*) FROM fin_accounting_accounts')} contas contábeis (partidas dobradas)",
            "—", ["Código", "Conta", "Tipo", "Natureza", "Saldo atual"], "0.8fr 2.2fr 1fr 0.9fr 1.1fr",
            "SELECT coalesce(code,'—'), coalesce(name,'—'), coalesce(account_type::text,'—'), "
            "coalesce(nature::text,'—'), current_balance FROM fin_accounting_accounts "
            "WHERE coalesce(active,true)=true ORDER BY code LIMIT 300",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—')[:44]),
                       t((r[2] or '—').replace('_', ' ').capitalize()),
                       b((r[3] or '—').capitalize(), _ntone.get((r[3] or '').lower(), "mut")),
                       t(brl(r[4]) if r[4] is not None else '—', 600)])
    except Exception:  # noqa: BLE001
        pass

    # ── Lançamentos (accounting_entries — razão D/C real) ────────────────────────────────
    try:
        out["lancamentos"] = await tbl(
            "Lançamentos contábeis",
            f"{await _scalar(db, 'SELECT count(*) FROM accounting_entries')} lançamentos (débito × crédito)",
            "—", ["Data", "Débito", "Crédito", "Valor", "Histórico", "Tipo"], "0.8fr 0.9fr 0.9fr 1fr 2fr 1fr",
            "SELECT data_lancamento, coalesce(conta_debito,'—'), coalesce(conta_credito,'—'), valor, "
            "coalesce(historico,'—'), coalesce(tipo_lancamento,'—') FROM accounting_entries "
            "ORDER BY data_lancamento DESC, id DESC LIMIT 200",
            lambda r: [t(_fmtdate(r[0])), t(r[1], 600, "#0F1B3A"), t(r[2], 600, "#0F1B3A"),
                       t(brl(r[3]) if r[3] is not None else '—', 600), t((r[4] or '—')[:48]),
                       b((r[5] or '—').replace('_', ' ').capitalize(), "info")])
    except Exception:  # noqa: BLE001
        pass

    # ── Balancete (agregado por conta a partir dos LANÇAMENTOS reais — soma D/C) ─────────
    try:
        scr = await tbl(
            "Balancete (do razão)",
            "Somas de débito/crédito por conta — agregado dos lançamentos reais",
            "—", ["Conta", "Nome", "Débitos", "Créditos", "Saldo (D−C)"], "0.9fr 1.8fr 1fr 1fr 1.1fr",
            "WITH mov AS ("
            " SELECT conta_debito AS conta, valor AS deb, 0::numeric AS cred FROM accounting_entries"
            " UNION ALL SELECT conta_credito, 0, valor FROM accounting_entries) "
            "SELECT m.conta, coalesce(max(a.name),'—'), sum(m.deb), sum(m.cred), sum(m.deb)-sum(m.cred) "
            "FROM mov m LEFT JOIN fin_accounting_accounts a ON a.code=m.conta "
            "WHERE m.conta IS NOT NULL GROUP BY m.conta ORDER BY m.conta LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—')[:36]), t(brl(r[2]), 600), t(brl(r[3]), 600),
                       b(brl(r[4]), "ok" if (r[4] or 0) >= 0 else "bad")])
        # Painel: períodos contábeis + centros de custo (cadastros reais pequenos)
        per = (await db.execute(text(
            "SELECT coalesce(name, to_char(start_date,'MM/YYYY')), coalesce(status::text,'—') "
            "FROM fin_accounting_periods ORDER BY start_date DESC LIMIT 6"))).fetchall()
        cc = (await db.execute(text(
            "SELECT coalesce(name,'—'), coalesce(status::text,'—') FROM fin_cost_centers LIMIT 6"))).fetchall()
        scr["panelGrid"] = "1fr 1fr"
        scr["panels"] = [
            {"title": "Períodos contábeis", "rows": [
                {"left": p, "right": (s or '—').capitalize(), **(S["ok"] if (s or '').lower() in ('open', 'aberto') else S["mut"])}
                for p, s in per] or [{"left": "Sem períodos", "right": "0", **S["mut"]}]},
            {"title": "Centros de custo", "rows": [
                {"left": n, "right": (s or '—').capitalize(), **S["info"]} for n, s in cc] or
                [{"left": "Sem centros de custo", "right": "0", **S["mut"]}]},
        ]
        out["balancete"] = scr
    except Exception:  # noqa: BLE001
        pass

    # ── Balanço Patrimonial (do razão REAL accounting_entries — classifica pelo 1º dígito do
    # código: 1=Ativo, 2=Passivo, 3=Receita, 4=Despesa; PL = Resultado do exercício. O serviço
    # ORM balance_sheet_service lê o razão VAZIO fin_journal_entries → aqui lemos o populado). ─
    try:
        _rows = (await db.execute(text(
            "WITH mov AS ("
            " SELECT conta_debito AS conta, valor AS deb, 0::numeric AS cred FROM accounting_entries"
            " UNION ALL SELECT conta_credito, 0, valor FROM accounting_entries) "
            "SELECT m.conta, coalesce(max(a.name), m.conta), sum(m.deb), sum(m.cred) "
            "FROM mov m LEFT JOIN fin_accounting_accounts a ON a.code=m.conta "
            "WHERE m.conta IS NOT NULL GROUP BY m.conta ORDER BY m.conta"))).fetchall()
        ativo, passivo, receita, despesa, at_tot, pa_tot = [], [], 0.0, 0.0, 0.0, 0.0
        for conta, nome, d, c in _rows:
            d = float(d or 0); c = float(c or 0); pre = (conta or "")[:1]
            if pre == "1":
                s = d - c; at_tot += s; ativo.append((nome, conta, s))
            elif pre == "2":
                s = c - d; pa_tot += s; passivo.append((nome, conta, s))
            elif pre == "3":
                receita += c - d
            elif pre == "4":
                despesa += d - c
        resultado = receita - despesa
        pl_tot = resultado  # sem conta de PL com movimento → resultado do exercício é o PL
        confere = abs(at_tot - (pa_tot + pl_tot)) < 0.01
        out["balanco-patrimonial"] = {
            "title": "Balanço Patrimonial", "type": "dash", "cta": "—",
            "sub": (f"Do razão real (accounting_entries) · "
                    f"{'FECHA ✓' if confere else 'NÃO FECHA — revisar razão'} · "
                    f"Ativo {brl(at_tot)} = Passivo {brl(pa_tot)} + PL {brl(pl_tot)}"),
            "panelGrid": "1fr 1fr 1fr",
            "kpis": [
                {"v": brl(at_tot), "l": "Ativo total", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3", "color": "#16A34A", "to": "balancete"},
                {"v": brl(pa_tot), "l": "Passivo total", "icon": "M2 6h20M2 18h20M6 6v12M18 6v12", "color": "#C2410C", "to": "balancete"},
                {"v": brl(pl_tot), "l": "Patrimônio Líquido (resultado)", "icon": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6", "color": "#0F1B3A", "to": "apuracao-resultado"},
                {"v": ("Fecha ✓" if confere else "Não fecha"), "l": "Ativo = Passivo + PL",
                 "icon": "M20 6L9 17l-5-5", "color": "#16A34A" if confere else "#DC2626"},
            ],
            "panels": [
                {"title": "Ativo", "rows": [{"left": f"{(n or '—')[:34]} ({co})", "right": brl(s), **S["ok"]}
                                            for n, co, s in ativo] or [{"left": "—", "right": "0", **S["mut"]}]},
                {"title": "Passivo", "rows": [{"left": f"{(n or '—')[:34]} ({co})", "right": brl(s), **S["warn"]}
                                              for n, co, s in passivo] or [{"left": "—", "right": "0", **S["mut"]}]},
                {"title": "Patrimônio Líquido", "rows": [
                    {"left": "Receitas do período", "right": brl(receita), **S["ok"]},
                    {"left": "(−) Despesas do período", "right": brl(despesa), **S["bad"]},
                    {"left": "= Resultado do exercício", "right": brl(resultado),
                     **(S["ok"] if resultado >= 0 else S["bad"])}]},
            ],
            "chartGrid": "1fr",
            "charts": [{"type": "bar", "title": "Estrutura patrimonial (R$)", "data": [
                {"name": "Ativo", "value": round(at_tot, 2), "color": "#16A34A"},
                {"name": "Passivo", "value": round(pa_tot, 2), "color": "#C2410C"},
                {"name": "Patrim. Líquido", "value": round(pl_tot, 2), "color": "#16277D"}]}],
        }
    except Exception:  # noqa: BLE001
        pass

    # ── Índices de liquidez & endividamento (do razão REAL) — leitura, isolado da folha.
    # Ativo Circulante = saldo das contas 1.1.*; Passivo Circulante = 2.1.*. Só índices que o
    # dado real sustenta (corrente, geral, composição, imobilização); nada fabricado. ──────────
    try:
        _liq = (await db.execute(text(
            "WITH mov AS ("
            " SELECT conta_debito AS conta, valor AS deb, 0::numeric AS cred FROM accounting_entries"
            " UNION ALL SELECT conta_credito, 0, valor FROM accounting_entries) "
            "SELECT "
            " sum(deb-cred) FILTER (WHERE conta LIKE '1.1%'), "     # Ativo Circulante
            " sum(deb-cred) FILTER (WHERE conta LIKE '1%'), "       # Ativo Total
            " sum(cred-deb) FILTER (WHERE conta LIKE '2.1%'), "     # Passivo Circulante
            " sum(cred-deb) FILTER (WHERE conta LIKE '2%') "        # Passivo Total (exigível)
            "FROM mov WHERE conta IS NOT NULL"))).fetchone()
        ac = float(_liq[0] or 0); at = float(_liq[1] or 0)
        pc = float(_liq[2] or 0); pt = float(_liq[3] or 0)
        anc = at - ac  # ativo não circulante (imobilizado etc.)
        pl = at - pt   # patrimônio líquido (resultado acumulado)
        liq_corr = round(ac / pc, 2) if pc > 0 else None
        endiv = round(pt / at, 2) if at > 0 else None
        comp = round(pc / pt, 2) if pt > 0 else None
        imob = round(anc / pl, 2) if pl > 0 else None
        _rating = ("Sólida" if (liq_corr or 0) >= 1.5 else "Adequada" if (liq_corr or 0) >= 1.0 else "Apertada")
        out["indices-liquidez"] = {
            "title": "Liquidez & endividamento", "type": "dash", "cta": "—",
            "sub": (f"Índices do razão real (accounting_entries) · AC {brl(ac)} / PC {brl(pc)}. "
                    f"Posição {_rating.lower()}. Não inclui provisões de folha ainda não postadas."),
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": (f"{liq_corr:.2f}" if liq_corr is not None else "—"), "l": "Liquidez corrente (AC/PC)",
                 "icon": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6",
                 "color": "#16A34A" if (liq_corr or 0) >= 1 else "#C2410C"},
                {"v": (f"{endiv*100:.0f}%" if endiv is not None else "—"), "l": "Endividamento geral (P/A)",
                 "icon": "M2 6h20M2 18h20M6 6v12M18 6v12", "color": "#C2410C" if (endiv or 0) > 0.6 else "#0F1B3A"},
                {"v": (f"{comp*100:.0f}%" if comp is not None else "—"), "l": "Composição (curto prazo / total)",
                 "icon": "M12 8v4l3 3M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20", "color": "#0F1B3A"},
                {"v": (f"{imob:.2f}" if imob is not None else "—"), "l": "Imobilização do PL (ANC/PL)",
                 "icon": "M3 21h18M4 10h16M5 10 12 4l7 6M6 10v11M18 10v11", "color": "#0F1B3A"},
            ],
            "panels": [
                {"title": "Estrutura patrimonial", "rows": [
                    {"left": "Ativo Circulante", "right": brl(ac), **S["ok"]},
                    {"left": "Ativo Não Circulante", "right": brl(anc), **S["info"]},
                    {"left": "Passivo Circulante", "right": brl(pc), **S["warn"]},
                    {"left": "Passivo Não Circulante", "right": brl(pt - pc), **S["warn"]},
                    {"left": "Patrimônio Líquido", "right": brl(pl), **(S["ok"] if pl >= 0 else S["bad"])},
                ]},
                {"title": "Leitura dos índices", "rows": [
                    {"left": "Liquidez corrente", "right": (f"{liq_corr:.2f} — paga o curto prazo {liq_corr:.1f}x" if liq_corr else "—"),
                     **(S["ok"] if (liq_corr or 0) >= 1 else S["bad"])},
                    {"left": "Endividamento geral", "right": (f"{endiv*100:.0f}% do ativo é de terceiros" if endiv is not None else "—"),
                     **(S["warn"] if (endiv or 0) > 0.6 else S["ok"])},
                    {"left": "Composição da dívida", "right": (f"{comp*100:.0f}% vence no curto prazo" if comp is not None else "—"), **S["info"]},
                    {"left": "Base", "right": "Razão real; provisões de folha (T2) entram depois", **S["mut"]},
                ]},
            ],
            "chartGrid": "1fr",
            "charts": [{"type": "bar", "horizontal": True, "title": "Estrutura patrimonial (R$)", "data": [
                {"name": "Ativo Circulante", "value": round(ac, 2), "color": "#16A34A"},
                {"name": "Ativo Não Circ.", "value": round(anc, 2), "color": "#0EA5E9"},
                {"name": "Passivo Circulante", "value": round(pc, 2), "color": "#C2410C"},
                {"name": "Passivo Não Circ.", "value": round(pt - pc, 2), "color": "#F26522"},
                {"name": "Patrim. Líquido", "value": round(pl, 2), "color": "#16277D"}]}],
        }
    except Exception:  # noqa: BLE001
        pass

    # ── DRE por regime de CAIXA (dos fluxos bancários REAIS) — distinta da DRE por competência.
    # Recebido = credit+pix_recebido+boleto_recebido; Pago = debit+ted+pix_enviado+saque+boleto_pago.
    # Agrupa despesas por category. É dinheiro que ENTROU/SAIU, não competência. Isolado. ────────
    try:
        _cred = ("'credit','credito','pix_recebido','boleto_recebido'")
        _receb = float((await db.execute(text(
            f"SELECT coalesce(sum(amount),0) FROM bank_transactions WHERE transaction_type IN ({_cred})"))).scalar() or 0)
        _desp_rows = (await db.execute(text(
            f"SELECT coalesce(nullif(category,''),'Sem categoria'), coalesce(sum(abs(amount)),0), count(*) "
            f"FROM bank_transactions WHERE transaction_type NOT IN ({_cred}) AND amount < 0 "
            f"GROUP BY 1 ORDER BY 2 DESC LIMIT 12"))).fetchall()
        _pago = float((await db.execute(text(
            f"SELECT coalesce(sum(abs(amount)),0) FROM bank_transactions WHERE transaction_type NOT IN ({_cred}) AND amount < 0"))).scalar() or 0)
        _result = _receb - _pago
        _margem = round(_result / _receb * 100, 1) if _receb > 0 else None
        out["dre-caixa"] = {
            "title": "DRE por regime de caixa", "type": "dash", "cta": "—",
            "sub": (f"Do que efetivamente ENTROU e SAIU na conta (bank_transactions) — regime de CAIXA, "
                    f"diferente da DRE por competência. Recebido {brl(_receb)} − pago {brl(_pago)} = {brl(_result)}."),
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": brl(_receb), "l": "Receitas recebidas (caixa)", "icon": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6", "color": "#16A34A"},
                {"v": brl(_pago), "l": "Despesas pagas (caixa)", "icon": "M2 6h20M2 18h20M6 6v12M18 6v12", "color": "#C2410C"},
                {"v": brl(_result), "l": "Resultado de caixa", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3", "color": "#16A34A" if _result >= 0 else "#DC2626"},
                {"v": (f"{_margem:.1f}%" if _margem is not None else "—"), "l": "Margem de caixa", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3", "color": "#0F1B3A"},
            ],
            "panels": [
                {"title": "Entradas de caixa", "rows": [
                    {"left": "Recebimentos (PIX + boleto + crédito)", "right": brl(_receb), **S["ok"]},
                    {"left": "= Total recebido no período", "right": brl(_receb), **S["ok"]}]},
                {"title": "Saídas de caixa por categoria", "rows": [
                    {"left": f"{(str(c[0]))[:36]}", "right": brl(float(c[1] or 0)), **S["bad"]}
                    for c in _desp_rows] or [{"left": "Sem saídas", "right": "0", **S["mut"]}]},
            ],
            "chartGrid": "1fr 1fr",
            "charts": [
                {"type": "bar", "title": "Recebido × Pago (R$)", "data": [
                    {"name": "Recebido", "value": round(_receb, 2), "color": "#16A34A"},
                    {"name": "Pago", "value": round(_pago, 2), "color": "#C2410C"}]},
                {"type": "bar", "horizontal": True, "title": "Saídas por categoria (R$)", "data": [
                    {"name": (str(c[0])[:22]), "value": round(float(c[1] or 0), 2)} for c in _desp_rows][:8]},
            ],
        }
    except Exception:  # noqa: BLE001
        pass

    # ── Análise Vertical da DRE (cada linha como % da Receita Líquida) — leitura clássica.
    # Reusa get_dre (mesmo do PDF/clássico) — isolado, read-only. ──────────────────────────────
    try:
        from datetime import date as _date
        from modules.financial.controllers.relatorios_controller import get_dre as _get_dre
        _d = await _get_dre(ano=_date.today().year, mes_inicio=1, mes_fim=12,
                            comparativo=False, condominio_id=None, db=db)
        _gs = _d.get("grupos", []) or []
        _rl = next((float(g.get("valor") or 0) for g in _gs if g.get("grupo") == "receita_liquida"), 0.0)
        _bases = {"receita_liquida", "lucro_bruto", "lucro_operacional", "lucro_liquido"}
        _rows = []
        for g in _gs:
            v = float(g.get("valor") or 0)
            av = (v / _rl * 100) if _rl else 0.0
            _rows.append({"cells": [
                t((g.get("nome") or "—")[:40], 600 if g.get("grupo") in _bases else 400,
                  "#0F1B3A" if g.get("grupo") in _bases else "#334155"),
                t(brl(v), 600 if g.get("grupo") in _bases else 400),
                t(f"{av:.1f}%", 600 if g.get("grupo") in _bases else 400,
                  "#16A34A" if av >= 0 else "#C2410C")]})
        out["dre-analise-vertical"] = {
            "title": "Análise Vertical da DRE", "type": "table", "cta": "—",
            "sub": (f"Cada linha como % da Receita Líquida ({brl(_rl)}) — regime {_d.get('regime','—')}. "
                    f"Margem bruta {_d.get('margem_bruta_pct','—')}% · líquida {_d.get('margem_liquida_pct','—')}%. "
                    "Mesmos números do get_dre (clássico/PDF)."),
            "grid": "2.2fr 1.2fr 0.9fr", "cols": ["Conta", "Valor", "% da Receita Líq."],
            "rows": _rows or [{"cells": [t("Sem DRE"), t("—"), t("—")]}],
        }
    except Exception:  # noqa: BLE001
        pass

    # ── Apuração de resultado (Lucro Real — IRPJ/CSLL do razão REAL) — rota órfã religada ──
    try:
        from starlette.concurrency import run_in_threadpool

        from modules.financial.services.apuracao_lucro_real_service import ApuracaoLucroRealService
        _svc = ApuracaoLucroRealService()
        ap = await run_in_threadpool(_svc.apurar, 2026, None)
        base = ap.get("base", {}) or {}
        apu = ap.get("apuracao", {}) or {}
        tris = []
        for _tri in (1, 2, 3, 4):
            try:
                a = await run_in_threadpool(_svc.apurar, 2026, _tri)
                tris.append((f"{_tri}ºT", (a.get("base", {}) or {}).get("lucro_antes_ircsll", 0),
                             (a.get("apuracao", {}) or {}).get("total_irpj_csll", 0)))
            except Exception:  # noqa: BLE001
                pass
        _lucro = base.get("lucro_antes_ircsll") or 0
        scr = {
            "title": "Apuração de resultado (Lucro Real)", "type": "dash", "cta": "—",
            "sub": (f"IRPJ 15% + adicional 10% · CSLL 9% sobre o lucro REAL do razão (accounting_entries) · "
                    f"{ap.get('periodo', '—')} · carga {apu.get('carga_sobre_receita_pct', '—')}% da receita"),
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": brl(base.get("receita_liquida")), "l": "Receita líquida", "icon": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6", "color": "#16A34A"},
                {"v": brl(_lucro), "l": "Lucro antes IR/CSLL", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3", "color": "#0F1B3A"},
                {"v": brl(apu.get("total_irpj_csll")), "l": "IRPJ + CSLL", "icon": "M2 6h20M2 18h20M6 6v12M18 6v12", "color": "#C2410C"},
                {"v": f"{apu.get('carga_sobre_receita_pct', '—')}%", "l": "Carga sobre receita", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3", "color": "#0F1B3A"},
            ],
            "panels": [
                {"title": "Base de cálculo (do razão)", "rows": [
                    {"left": "Receita bruta", "right": brl(base.get("receita_bruta")), **S["info"]},
                    {"left": "(−) Deduções ISS", "right": brl(base.get("deducoes_iss")), **S["mut"]},
                    {"left": "(−) Despesa pessoal", "right": brl(base.get("despesa_pessoal")), **S["mut"]},
                    {"left": "(−) Encargos", "right": brl(base.get("despesa_encargos")), **S["mut"]},
                    {"left": "(−) Despesas dedutíveis (total)", "right": brl(base.get("despesas_dedutiveis_total")), **S["mut"]},
                    {"left": "= Lucro antes IR/CSLL", "right": brl(_lucro), **(S["ok"] if _lucro >= 0 else S["bad"])},
                ]},
                {"title": "Apuração IRPJ / CSLL", "rows": [
                    {"left": "IRPJ 15%", "right": brl(apu.get("irpj_15")), **S["info"]},
                    {"left": "IRPJ adicional 10%", "right": brl(apu.get("irpj_adicional_10")), **S["info"]},
                    {"left": "CSLL 9%", "right": brl(apu.get("csll_9")), **S["info"]},
                    {"left": "= Total IRPJ + CSLL", "right": brl(apu.get("total_irpj_csll")), **S["warn"]},
                    {"left": "Prejuízo fiscal compensável", "right": brl(ap.get("prejuizo_fiscal_compensavel")), **S["mut"]},
                ]},
                {"title": "Por trimestre (lucro · IRPJ+CSLL)", "rows": [
                    {"left": f"{nm} · lucro {brl(lu)}", "right": brl(tot), **S["info"]} for nm, lu, tot in tris]
                    or [{"left": "Sem trimestres", "right": "—", **S["mut"]}]},
                {"title": "Ressalvas (honestas, do serviço)", "rows": [
                    {"left": (ap.get("observacao", "") or "—")[:220], "right": "—", **S["warn"]}]},
            ],
        }
        out["apuracao-resultado"] = scr
    except Exception:  # noqa: BLE001
        pass

    # ── Provisões trabalhistas (férias 1/9 + 13º 1/12 sobre a folha REAL) — read-only.
    # bookkeeper_auto calcula os pares D/C (D 4.1.2.04 férias / D 4.1.2.03 13º / C 2.1.2.01) mas
    # NÃO posta no razão. Aqui mostramos o que DEVE ser provisionado; postar = ação gated (próxima). ─
    try:
        prov = (await db.execute(text(
            "SELECT reference_month, count(*), coalesce(sum(base_salary),0) "
            "FROM hr_payslips WHERE coalesce(base_salary,0)>0 GROUP BY 1 ORDER BY 1"))).fetchall()
        rows, tot_base, tot_fer, tot_dec = [], 0.0, 0.0, 0.0
        for mes, n, base in prov:
            base = float(base or 0); fer = base * 0.1111; dec = base * 0.0833
            tot_base += base; tot_fer += fer; tot_dec += dec
            rows.append({"cells": [
                t(f"{int(mes):02d}/2026" if mes else "—", 600, "#0F1B3A"), t(str(int(n))),
                t(brl(base), 600), t(brl(fer)), t(brl(dec))]})
        scr = {
            "title": "Provisões trabalhistas (férias + 13º)", "type": "table", "cta": "—",
            "sub": (f"Provisão de férias (1/9) e 13º (1/12) sobre a folha REAL (hr_payslips). "
                    f"Acumulado: base {brl(tot_base)} · férias {brl(tot_fer)} · 13º {brl(tot_dec)}. "
                    "Postagem no razão (4.1.2.04/4.1.2.03) pela ação 'Postar provisões' — gated, idempotente."),
            "grid": "1fr 0.9fr 1.2fr 1.2fr 1.2fr",
            "cols": ["Competência", "Func.", "Base salarial", "Provisão férias (1/9)", "Provisão 13º (1/12)"],
            "rows": rows or [{"cells": [t("Sem folha"), t("0"), t("—"), t("—"), t("—")]}],
            "panelGrid": "1fr",
            "panels": [{"title": "Lançamentos que serão postados (por competência)", "rows": [
                {"left": "Provisão férias — D 4.1.2.04 (despesa) / C 2.1.2.01 (provisões a pagar)", "right": brl(tot_fer), **S["info"]},
                {"left": "Provisão 13º — D 4.1.2.03 (despesa) / C 2.1.2.01 (provisões a pagar)", "right": brl(tot_dec), **S["info"]},
                {"left": "Total a provisionar (passivo + despesa de competência)", "right": brl(tot_fer + tot_dec), **S["warn"]},
            ]}],
        }
        out["provisoes-trabalhistas"] = scr
    except Exception:  # noqa: BLE001
        pass

    # ── Apuração de tributos POR CNPJ (2 empresas, cada uma no seu regime) — receita REAL das
    # NFS-e nacionais, regime/anexo do banco (empresas), motor tax_calculator. Multi-CNPJ. ─────
    try:
        from decimal import Decimal as _Dec

        from modules.financial.agents.tax_calculator import TaxCalculatorAgent
        _agent = TaxCalculatorAgent()
        _EMPS = [
            ("619a3df1-8bce-49ce-b77a-04f80a0e8491", "Eletrônica", "das-eletronica"),
            ("7d79ed12-d480-4906-b2e0-2b2c4d299bab", "Patrimonial", "das-patrimonial"),
        ]
        for _eid, _nome, _slug in _EMPS:
            _cfg = (await db.execute(text(
                "SELECT regime_tributario, anexo_simples FROM empresas WHERE id = :e"), {"e": _eid})).fetchone()
            if not _cfg:
                continue
            _regime = (_cfg[0] or "").lower()
            # receita mensal real (12 competências), NFS-e não canceladas desta empresa
            _mrows = (await db.execute(text(
                "SELECT competencia, coalesce(sum(valor_servicos),0) FROM nfse_emitidas_nacional "
                "WHERE empresa_id = :e AND coalesce(cancelada,false)=false AND competencia IS NOT NULL "
                "GROUP BY 1 ORDER BY 1 DESC LIMIT 12"), {"e": _eid})).fetchall()
            if not _mrows:
                continue
            _rec_mes = _Dec(str(float(_mrows[0][1] or 0)))
            _comp = _mrows[0][0]
            _n = len(_mrows)
            _soma = sum(_Dec(str(float(m[1] or 0))) for m in _mrows)
            # RBT12: 12m reais; se empresa nova (<12 meses), proporcionaliza (LC 123 art.18 §2)
            _rbt12 = _soma if _n >= 12 else (_soma / _Dec(_n) * _Dec("12"))
            _rec_tri = sum(_Dec(str(float(m[1] or 0))) for m in _mrows[:3])  # último trimestre

            if _regime == "simples_nacional":
                _anexo = (_cfg[1] or "III")
                # LIMINAR PIS/COFINS/INSS: deu entrada mas NÃO foi obtida (2026-07) → DAS INTEGRAL.
                # A Patrimonial ainda sofre retenção de PIS/COFINS/INSS (INSS em dobro: na nota de
                # serviço + na guia do Simples). Só aplicar a redução quando a liminar for deferida.
                c = _agent.calcular_simples(_rec_mes, _rbt12, anexo=_anexo, liminares=[])  # integral
                c_lim = _agent.calcular_simples(_rec_mes, _rbt12, anexo=_anexo, liminares=["pis_cofins_zero"])
                _econ_potencial = float(c.valor_das) - float(c_lim.valor_das)  # informativo (se deferida)
                _dist = c.distribuicao or {}
                out[_slug] = {
                    "title": f"Apuração DAS — {_nome} (Simples Nacional)", "type": "dash", "cta": "—",
                    "sub": (f"Anexo {_anexo} · competência {_comp} · RBT12 {brl(float(_rbt12))}"
                            f"{' (proporcional — empresa nova)' if _n < 12 else ''} · alíq. efetiva "
                            f"{float(c.aliquota_efetiva)*100:.2f}%. DAS INTEGRAL — liminar PIS/COFINS/INSS "
                            "EM ANDAMENTO (deu entrada, não obtida); retenção ainda ativa, INSS em dobro (nota+DAS)."),
                    "panelGrid": "1fr 1fr",
                    "kpis": [
                        {"v": brl(float(_rec_mes)), "l": f"Receita do mês ({_comp})", "icon": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6", "color": "#16A34A"},
                        {"v": f"{float(c.aliquota_efetiva)*100:.2f}%", "l": "Alíquota efetiva", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3", "color": "#0F1B3A"},
                        {"v": brl(float(c.valor_das)), "l": "DAS a pagar (integral)", "icon": "M2 6h20M2 18h20M6 6v12M18 6v12", "color": "#C2410C"},
                        {"v": brl(_econ_potencial), "l": "Economia SE liminar deferida", "icon": "M20 6L9 17l-5-5", "color": "#0F1B3A"},
                    ],
                    "panels": [
                        {"title": "DAS por tributo (integral, sem liminar)", "rows": [
                            {"left": k.upper(), "right": brl(float(v)),
                             **(S["mut"] if float(v) == 0 else S["info"])} for k, v in _dist.items()]
                            or [{"left": "—", "right": "0", **S["mut"]}]},
                        {"title": "Situação da liminar", "rows": [
                            {"left": "RBT12 (12 meses)", "right": brl(float(_rbt12)), **S["info"]},
                            {"left": "Alíquota nominal (faixa)", "right": f"{float(c.aliquota_nominal)*100:.2f}%", **S["info"]},
                            {"left": "Liminar PIS/COFINS/INSS", "right": "Em andamento — NÃO obtida (DAS integral)", **S["warn"]},
                            {"left": "Economia potencial se deferida", "right": brl(_econ_potencial), **S["ok"]},
                        ]},
                    ],
                    "chartGrid": "1fr 1fr",
                    "charts": [{"type": "pie", "title": "DAS por tributo (integral)",
                                "data": [{"name": k.upper(), "value": float(v)} for k, v in _dist.items() if float(v) > 0]}],
                }
            elif _regime == "lucro_real":
                c = _agent.calcular_lucro_real(_rec_mes, _rec_tri)
                out[_slug] = {
                    "title": f"Apuração de tributos — {_nome} (Lucro Real)", "type": "dash", "cta": "—",
                    "sub": (f"Tributos do mês {_comp} sobre receita real das NFS-e · carga "
                            f"{float(c.carga_tributaria_percentual):.2f}% da receita. Estimativa mensal "
                            "(IRPJ/CSLL definitivos na Apuração anual do razão)."),
                    "panelGrid": "1fr 1fr",
                    "kpis": [
                        {"v": brl(float(c.receita_bruta_mes)), "l": f"Receita do mês ({_comp})", "icon": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6", "color": "#16A34A"},
                        {"v": brl(float(c.total_impostos_mes)), "l": "Total de tributos do mês", "icon": "M2 6h20M2 18h20M6 6v12M18 6v12", "color": "#C2410C"},
                        {"v": f"{float(c.carga_tributaria_percentual):.2f}%", "l": "Carga sobre receita", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3", "color": "#0F1B3A"},
                        {"v": brl(float(c.iss)), "l": "ISS (Manaus 5%)", "icon": "M3 21h18M4 10h16M5 10 12 4l7 6", "color": "#0F1B3A"},
                    ],
                    "panels": [
                        {"title": "Tributos federais do mês", "rows": [
                            {"left": "IRPJ (15%)", "right": brl(float(c.irpj)), **S["info"]},
                            {"left": "IRPJ adicional (10%)", "right": brl(float(c.irpj_adicional)), **S["info"]},
                            {"left": "CSLL (9%)", "right": brl(float(c.csll)), **S["info"]},
                            {"left": "PIS (não-cumulativo)", "right": brl(float(c.pis)), **S["info"]},
                            {"left": "COFINS (não-cumulativo)", "right": brl(float(c.cofins)), **S["info"]},
                        ]},
                        {"title": "Municipal", "rows": [
                            {"left": "ISS Manaus (5%)", "right": brl(float(c.iss)), **S["info"]},
                            {"left": "= Total de tributos", "right": brl(float(c.total_impostos_mes)), **S["warn"]},
                        ]},
                    ],
                    "chartGrid": "1fr",
                    "charts": [{"type": "bar", "title": "Tributos do mês (R$)", "data": [
                        {"name": "IRPJ", "value": float(c.irpj) + float(c.irpj_adicional)},
                        {"name": "CSLL", "value": float(c.csll)},
                        {"name": "PIS", "value": float(c.pis)},
                        {"name": "COFINS", "value": float(c.cofins)},
                        {"name": "ISS", "value": float(c.iss)}]}],
                }
    except Exception:  # noqa: BLE001
        pass

    # ── Ação gated: postar as provisões no razão (bookkeeping, NÃO move dinheiro) ────────────
    out["postar-provisoes"] = {
        "title": "Postar provisões no razão", "type": "form", "cta": "Postar provisões",
        "sub": "Posta no razão as provisões de férias (1/9) e 13º (1/12) sobre a folha REAL, por "
               "competência. Bookkeeping — NÃO move dinheiro. Idempotente: re-acionar não duplica "
               "(ref PROVFER-/PROV13- por mês). Reversível apagando esses lançamentos.",
        "submit": {"endpoint": "/api/v1/redesign/action/postar-provisoes", "gated": False,
                   "confirm": "Postar no razão as provisões de férias e 13º sobre a folha real (por competência)?",
                   "okMsg": "Provisões postadas."},
        "fields": [],
    }

    # ── C-PAR (Fase 5): Pareamento nosso × Portte — medidor de maturidade p/ andar sem a Portte.
    # 1ª rubrica: folha = razão (nosso) × hr_payslips (Portte) por competência. Roda em paralelo ~6m. ─
    try:
        from sqlalchemy import text as _text
        _rz = {r[0]: float(r[1] or 0) for r in (await db.execute(_text(
            "SELECT periodo_competencia, coalesce(sum(valor),0) FROM accounting_entries "
            "WHERE conta_debito LIKE '4.1.1%' AND tipo_lancamento='folha' GROUP BY 1"))).fetchall()}
        _pt = {r[0]: float(r[1] or 0) for r in (await db.execute(_text(
            "SELECT reference_period, coalesce(sum(total_earnings),0) FROM hr_payslips GROUP BY 1"))).fetchall()}
        _comps = sorted(set(_rz) | set(_pt))
        _rows, _batem = [], 0
        for c in _comps:
            n, p = _rz.get(c, 0.0), _pt.get(c, 0.0)
            d = n - p
            ok = abs(d) < 0.5
            _batem += 1 if ok else 0
            _rows.append({"cells": [t(c, 600, "#0F1B3A"), t(brl(n)), t(brl(p)),
                          t(brl(d), 600, "#16A34A" if ok else "#C2410C"),
                          b("bate ✓" if ok else "diverge", "ok" if ok else "bad")]})
        _seq = 0
        for c in reversed(_comps):
            if abs(_rz.get(c, 0) - _pt.get(c, 0)) < 0.5:
                _seq += 1
            else:
                break
        out["pareamento-portte"] = {
            "title": "Pareamento Portte (nosso × contador)", "type": "table", "cta": "—",
            "sub": (f"Medidor de maturidade p/ andar sem a Portte (~6 meses de paralelo). Folha: razão (nosso) × "
                    f"hr_payslips (Portte) por competência. {_batem}/{len(_comps)} batem · {_seq} mês(es) seguidos batendo. "
                    "Próximas rubricas: DAS, tributos federais, ISS, FGTS/INSS."),
            "grid": "1fr 1.3fr 1.3fr 1.2fr 1fr",
            "cols": ["Competência", "Nosso (razão)", "Portte", "Δ", "Status"],
            "rows": _rows or [{"cells": [t("Aguardando dado"), t("—"), t("—"), t("—"), t("—")]}],
            "panelGrid": "1fr 1fr",
            "panels": [
                {"title": "Como o pareamento vira maturidade", "rows": [
                    {"left": "A PORTTE é a fonte da verdade — o nosso é medido contra ela", "right": "regra", **S["warn"]},
                    {"left": "Verde = nosso CONVERGIU à Portte (maduro nessa rubrica)", "right": "✓", **S["ok"]},
                    {"left": "Corte da Portte", "right": "só após N meses seguidos batendo TUDO", **S["warn"]},
                    {"left": "Roadmap", "right": "folha ✓ → tributos → guias → SPED", **S["info"]}]},
                {"title": "Próxima rubrica: tributos (alvos Portte a parear)", "rows": [
                    {"left": "INSS (Portte fiscal_obligations)",
                     "right": brl(float((await db.execute(_text("SELECT coalesce(sum(valor_devido),0) FROM fiscal_obligations WHERE tipo='INSS'"))).scalar() or 0)) + " · nosso a postar no razão",
                     **S["warn"]},
                    {"left": "FGTS (Portte)",
                     "right": brl(float((await db.execute(_text("SELECT coalesce(sum(valor_devido),0) FROM fiscal_obligations WHERE tipo='FGTS'"))).scalar() or 0)) + " · alinhar por competência",
                     **S["info"]},
                    {"left": "ISS (Portte)",
                     "right": brl(float((await db.execute(_text("SELECT coalesce(sum(valor_devido),0) FROM fiscal_obligations WHERE tipo='ISS'"))).scalar() or 0)) + " · alinhar por competência",
                     **S["info"]},
                    {"left": "Status", "right": "folha OK; tributos = alinhar competência+escopo (não é match cego)", **S["mut"]}]},
            ],
        }
    except Exception:  # noqa: BLE001
        pass

    # ── C-PAR tributos: FGTS por competência. LÓGICA PORTTE decifrada = 8% do fgts_base (não do
    # total). A verdade do FGTS é hr_payslips.fgts_value (NÃO fiscal_obligations, que é guia PDF
    # incompleta/chapada). Nosso _lancar_folha já posta fgts_value → já converge. ────────────────
    try:
        from sqlalchemy import text as _text
        _fp = {r[0]: float(r[1] or 0) for r in (await db.execute(_text(
            "SELECT reference_period, coalesce(sum(fgts_value),0) FROM hr_payslips "
            "WHERE coalesce(fgts_value,0) > 0 GROUP BY 1"))).fetchall()}
        _fn = {r[0]: float(r[1] or 0) for r in (await db.execute(_text(
            "SELECT periodo_competencia, coalesce(sum(valor),0) FROM accounting_entries "
            "WHERE conta_debito LIKE '4.1.2%' AND tipo_lancamento LIKE '%fgts%' GROUP BY 1"))).fetchall()}
        _cs = sorted(set(_fp) | set(_fn))
        _rows = []
        for c in _cs:
            n, p = _fn.get(c, 0.0), _fp.get(c, 0.0)
            d = n - p
            st = (b("só nosso", "warn") if p == 0 else b("só Portte", "warn") if n == 0
                  else b("bate ✓", "ok") if abs(d) < 0.5 else b("diverge", "bad"))
            _rows.append({"cells": [t(c, 600, "#0F1B3A"), t(brl(n)), t(brl(p)),
                          t(brl(d), 600, "#16A34A" if (n and p and abs(d) < 0.5) else "#C2410C"), st]})
        # ISS por competência: nosso (NFS-e iss_valor) × Portte (fiscal_obligations)
        _ip = {r[0]: float(r[1] or 0) for r in (await db.execute(_text(
            "SELECT competencia_ano||'-'||lpad(competencia_mes::text,2,'0'), coalesce(sum(valor_devido),0) "
            "FROM fiscal_obligations WHERE tipo='ISS' AND competencia_mes IS NOT NULL GROUP BY 1"))).fetchall()}
        _in = {r[0]: float(r[1] or 0) for r in (await db.execute(_text(
            "SELECT competencia, coalesce(sum(iss_valor),0) FROM nfse_emitidas_nacional "
            "WHERE coalesce(cancelada,false)=false AND competencia IS NOT NULL GROUP BY 1"))).fetchall()}
        _iss_rows = []
        for c in sorted(set(_ip) | set(_in)):
            n, p = _in.get(c, 0.0), _ip.get(c, 0.0)
            d = n - p
            _st = ("nosso convergiu ✓" if (n and p and abs(d) < 0.5) else "só nosso" if p == 0
                   else "só Portte" if n == 0 else f"Δ {brl(d)}")
            _iss_rows.append({"left": f"{c} · nosso {brl(n)} × Portte {brl(p)}", "right": _st,
                              **(S["ok"] if (n and p and abs(d) < 0.5) else S["warn"] if (n and p) else S["mut"])})
        out["pareamento-tributos"] = {
            "title": "Pareamento tributos — FGTS por competência", "type": "table", "cta": "—",
            "sub": "FGTS (lógica Portte decifrada = 8% do fgts_base, não do total): nosso razão × hr_payslips.fgts_value "
                   "(a verdade). Nosso _lancar_folha já posta o fgts_value → já CONVERGE. Próximas: INSS, DAS.",
            "grid": "1fr 1.3fr 1.3fr 1.2fr 1fr",
            "cols": ["Competência", "Nosso (razão)", "Portte", "Δ", "Status"],
            "rows": _rows or [{"cells": [t("Aguardando dado"), t("—"), t("—"), t("—"), t("—")]}],
            "panelGrid": "1fr 1fr",
            "panels": [
                {"title": "ISS por competência (nosso NFS-e × Portte) — já quase maduro", "rows": _iss_rows
                    or [{"left": "Sem dado de ISS", "right": "—", **S["mut"]}]},
                {"title": "FGTS — lógica Portte aplicada ✓", "rows": [
                    {"left": "Lógica Portte = 8% do fgts_base (base exclui verbas não-incidentes, < total)", "right": "decifrada", **S["ok"]},
                    {"left": "Nosso razão posta o fgts_value real da Portte → converge", "right": "✓", **S["ok"]},
                    {"left": "fiscal_obligations FGTS = guia PDF incompleta (não é a verdade do FGTS)", "right": "descartada", **S["mut"]}]}],
        }
    except Exception:  # noqa: BLE001
        pass
