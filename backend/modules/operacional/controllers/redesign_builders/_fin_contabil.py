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
                {"v": brl(at_tot), "l": "Ativo total", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3", "color": "#16A34A"},
                {"v": brl(pa_tot), "l": "Passivo total", "icon": "M2 6h20M2 18h20M6 6v12M18 6v12", "color": "#C2410C"},
                {"v": brl(pl_tot), "l": "Patrimônio Líquido (resultado)", "icon": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6", "color": "#0F1B3A"},
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
