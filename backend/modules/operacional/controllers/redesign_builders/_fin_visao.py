"""F4 — Visão Geral: Projeção de fluxo (30/60/90d, 3 cenários), Insights IA (riscos/
oportunidades) e DRE inline — REUSANDO as funções EXATAS dos endpoints (mesmos números
do clássico garantidos): get_cashflow_forecast, CashFlowAIService, get_dre."""
from datetime import date as _date

from modules.operacional.controllers.redesign_data_controller import S, _helpers, b, brl, t


def _tone_status(s):
    s = (s or "").lower()
    return S["bad"] if s in ("critico", "crítico", "negativo") else S["warn"] if s in ("atencao", "atenção", "alerta") else S["ok"]


async def build_visao(db, out: dict) -> None:
    _, _safe, _tbl = _helpers(db)
    _user = {"id": "redesign", "email": "redesign@conectapro"}

    # ── Projeção de fluxo (30/60/90d) — REUSO EXATO do endpoint /cashflow/forecast ──────
    try:
        from modules.financial.controllers.financial_dashboard_controller import get_cashflow_forecast
        fc = await get_cashflow_forecast(condominio_id=None, current_user=_user, db=db)
        hist = fc.get("historico_base", {}) or {}
        cen = fc.get("cenarios", {}) or {}

        def _rows_cenario(nome):
            c = cen.get(nome, {}) or {}
            proj = c.get("projecao_90d") or c.get("projecao_60d") or c.get("projecao_30d") or []
            return [{"left": f"{p.get('mes','—')} · saldo projetado", "right": brl(p.get("saldo_projetado")),
                     **_tone_status(p.get("status"))} for p in proj[:3]] or [
                {"left": "Sem projeção", "right": "—", **S["mut"]}]

        out["projecao"] = {
            "title": "Projeção de fluxo de caixa", "type": "dash",
            "sub": f"Cenários 30/60/90 dias — base: {hist.get('periodo', 'histórico real')} (espelho do endpoint; nada é fabricado)",
            "cta": "—", "panelGrid": "1fr 1fr 1fr",
            "kpis": [
                {"v": brl(fc.get("saldo_atual")), "l": "Saldo atual (conta principal)", "icon": "M3 21h18M4 10h16M5 10 12 4l7 6M6 10v11M18 10v11M10 10v11M14 10v11", "color": "#0F1B3A", "to": "consolidacao-grupo"},
                {"v": brl(fc.get("mrr_base")), "l": "Base recorrente (MRR)", "icon": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6", "color": "#16A34A", "to": "contas-receber"},
                {"v": brl(hist.get("media_entradas_mensal")), "l": "Média entradas/mês (90d)", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3", "color": "#0F1B3A", "to": "contas-receber"},
                {"v": brl(hist.get("media_saidas_mensal")), "l": "Média saídas/mês (90d)", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3", "color": "#C2410C", "to": "contas-pagar"},
            ],
            "panels": [
                {"title": "Cenário pessimista", "rows": _rows_cenario("pessimista")},
                {"title": "Cenário realista", "rows": _rows_cenario("realista")},
                {"title": "Cenário otimista", "rows": _rows_cenario("otimista")},
            ],
        }
    except Exception:  # noqa: BLE001 — projeção não derruba o módulo
        pass

    # ── Insights/Alertas IA — Motor A (ai_controller) sobre dado REAL ────────────────────
    # O motor do CashFlowAIService é escopado por CONDOMÍNIO (legado) e exige um forecast
    # pronto → não serve p/ a empresa (voltava sempre vazio: os métodos reais são privados
    # _identify_risks/_identify_opportunities). O Motor A calcula direto de ReceivableAccount/
    # PayableAccount reais (inadimplência, vencimentos 7d), sem condominio_id.
    try:
        from modules.financial.controllers.ai_controller import (
            _build_alerts, _build_insights, _calculate_default_metrics,
        )
        _m = await _calculate_default_metrics(db, None)
        _alerts = _build_alerts(_m)
        _insights = _build_insights(_m)
        _lvl = {"vermelho": "bad", "laranja": "warn", "amarelo": "warn"}

        def _alert_rows(items):
            return ([{"left": (getattr(a, "title", "") or "—")[:60],
                      "right": (getattr(a, "level", "") or "—").capitalize(),
                      **S[_lvl.get(getattr(a, "level", ""), "warn")]} for a in items[:8]] if items else
                    [{"left": "Sem alertas — inadimplência e liquidez sob controle", "right": "ok", **S["ok"]}])

        def _insight_rows(items):
            return ([{"left": (getattr(i, "title", "") or "—")[:60],
                      "right": (getattr(i, "type", "") or "—").capitalize(),
                      **(S["ok"] if getattr(i, "type", "") == "oportunidade" else S["info"])}
                     for i in items[:8]] if items else
                    [{"left": "Sem insights no momento", "right": "—", **S["mut"]}])

        if isinstance(out.get("projecao"), dict):
            out["projecao"]["panels"].extend([
                {"title": f"Alertas IA · inadimplência {_m['default_rate']:.1f}%", "rows": _alert_rows(_alerts)},
                {"title": "Insights IA", "rows": _insight_rows(_insights)},
            ])
            out["projecao"]["panelGrid"] = "1fr 1fr 1fr"
    except Exception:  # noqa: BLE001
        pass

    # ── DRE inline (ano corrente) — REUSO EXATO do get_dre (mesmo do PDF/clássico) ──────
    try:
        from modules.financial.controllers.relatorios_controller import get_dre
        ano = _date.today().year
        dre = await get_dre(ano=ano, mes_inicio=1, mes_fim=12, comparativo=False, condominio_id=None, db=db)
        grupos = dre.get("grupos", []) or []
        _neg = ("deducoes", "custo_servicos", "despesas_operacionais", "despesas_administrativas", "despesas_financeiras", "impostos")
        out["dre-inline"] = {
            "title": f"DRE — exercício {ano}", "type": "dash", "cta": "—",
            "sub": f"Regime {dre.get('regime','—')} · fonte {dre.get('fonte','dados reais')} · margem líquida {dre.get('margem_liquida_pct','—')}%",
            "panelGrid": "1fr",
            "kpis": [
                {"v": f"{dre.get('margem_bruta_pct','—')}%", "l": "Margem bruta", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3", "color": "#0F1B3A"},
                {"v": f"{dre.get('margem_operacional_pct','—')}%", "l": "Margem operacional", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3", "color": "#0F1B3A"},
                {"v": f"{dre.get('margem_liquida_pct','—')}%", "l": "Margem líquida", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3", "color": "#16A34A"},
            ],
            "panels": [{"title": "Demonstrativo (acumulado do ano)", "rows": [
                {"left": g.get("nome") or g.get("grupo") or "—", "right": brl(g.get("valor")),
                 **(S["bad"] if (g.get("grupo") in _neg) else S["ok"] if "receita" in (g.get("grupo") or "") or "lucro" in (g.get("grupo") or "") else S["info"])}
                for g in grupos]}],
            "chartGrid": "1fr",
            "charts": [{"type": "bar", "horizontal": True, "title": "DRE — grupos (R$)", "data": [
                {"name": (g.get("nome") or "—")[:24], "value": round(float(g.get("valor") or 0), 2)} for g in grupos]}],
        }
    except Exception:  # noqa: BLE001
        pass

    # ── Indicadores financeiros (DSO/DPO/ciclo de caixa) — de contas a receber/pagar (NÃO folha).
    # Isolado do módulo de folha (T2): lê receivable_accounts/payable_accounts, domínio financeiro. ─
    try:
        from sqlalchemy import text as _text
        dias = max(1, (_date.today() - _date(2026, 1, 1)).days)
        rr = (await db.execute(_text(
            "SELECT coalesce(sum(net_value),0), "
            "coalesce(sum(net_value) FILTER (WHERE status NOT IN ('paga','cancelada','recebida')),0), "
            "coalesce(avg((data_recebimento - due_date)) FILTER (WHERE data_recebimento IS NOT NULL AND due_date IS NOT NULL),0) "
            "FROM receivable_accounts"))).fetchone()
        pp = (await db.execute(_text(
            "SELECT coalesce(sum(net_value),0), "
            "coalesce(sum(net_value) FILTER (WHERE status NOT IN ('pago','paga','cancelada')),0) "
            "FROM payable_accounts"))).fetchone()
        recb_tot = float(rr[0] or 0); ar_ab = float(rr[1] or 0); atraso = float(rr[2] or 0)
        pag_tot = float(pp[0] or 0); ap_ab = float(pp[1] or 0)
        dso = round(ar_ab / (recb_tot / dias), 1) if recb_tot > 0 else 0.0
        dpo = round(ap_ab / (pag_tot / dias), 1) if pag_tot > 0 else 0.0
        ciclo = round(dso - dpo, 1)
        cob = round(ar_ab / ap_ab, 2) if ap_ab > 0 else None
        out["indicadores"] = {
            "title": "Indicadores financeiros (DSO / DPO / ciclo)", "type": "dash", "cta": "—",
            "sub": (f"Prazos médios de contas a receber × pagar (não inclui folha). Período jan–hoje ({dias}d). "
                    f"Atraso médio de recebimento: {atraso:.1f} dia(s) — recebido em dia = sem inadimplência."),
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": f"{dso:.0f}d", "l": "DSO — prazo médio recebimento", "icon": "M12 8v4l3 3M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20", "color": "#16A34A", "to": "contas-receber"},
                {"v": f"{dpo:.0f}d", "l": "DPO — prazo médio pagamento", "icon": "M12 8v4l3 3M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20", "color": "#C2410C", "to": "contas-pagar"},
                {"v": f"{ciclo:.0f}d", "l": "Ciclo de caixa (DSO−DPO)", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3", "color": "#0F1B3A"},
                {"v": (f"{cob:.2f}x" if cob is not None else "—"), "l": "Cobertura (AR aberto / AP aberto)", "icon": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6", "color": "#0F1B3A"},
            ],
            "panels": [
                {"title": "Contas a receber", "rows": [
                    {"left": "Total emitido", "right": brl(recb_tot), **S["info"]},
                    {"left": "Em aberto (a receber)", "right": brl(ar_ab), **(S["warn"] if ar_ab > 0 else S["ok"])},
                    {"left": "Atraso médio de recebimento", "right": f"{atraso:.1f}d", **(S["ok"] if atraso <= 0 else S["warn"])},
                ]},
                {"title": "Contas a pagar", "rows": [
                    {"left": "Total", "right": brl(pag_tot), **S["info"]},
                    {"left": "Em aberto (a pagar)", "right": brl(ap_ab), **S["warn"]},
                    {"left": "Leitura", "right": ("Ciclo negativo = recebe antes de pagar (bom)" if ciclo < 0 else "Ciclo positivo"), **(S["ok"] if ciclo < 0 else S["info"])},
                ]},
            ],
        }
    except Exception:  # noqa: BLE001
        pass

    # ── A4: Cockpit executivo — uma landing só com os KPIs-chave + gráficos + o que precisa de
    # atenção. Agrega dado REAL de bancos/NFS-e/recebíveis; drill-down em cada KPI. ──────────────
    try:
        from sqlalchemy import text as _text
        _saldo = float((await db.execute(_text(
            "SELECT coalesce(sum(coalesce(current_balance,0)),0) FROM bank_accounts "
            "WHERE COALESCE(ativo,true)=true AND COALESCE(status,'ativa')='ativa'"))).scalar() or 0)
        _cnpj = (await db.execute(_text(
            "SELECT bank_name, coalesce(current_balance,0) FROM bank_accounts "
            "WHERE bank_code IN ('077','403') ORDER BY current_balance DESC"))).fetchall()
        _fatm = (await db.execute(_text(
            "SELECT competencia, coalesce(sum(valor_servicos),0) FROM nfse_emitidas_nacional "
            "WHERE coalesce(cancelada,false)=false AND competencia IS NOT NULL GROUP BY 1 ORDER BY 1 DESC LIMIT 6"))).fetchall()
        _fatm = list(reversed(_fatm))
        _fat_ult = float(_fatm[-1][1] or 0) if _fatm else 0.0
        _venc = (await db.execute(_text(
            "SELECT count(*), coalesce(sum(net_value),0) FROM receivable_accounts "
            "WHERE due_date < current_date AND coalesce(status::text,'') NOT ILIKE '%pag%' "
            "AND coalesce(status::text,'') NOT ILIKE '%cancel%'"))).fetchone()
        _n_venc, _v_venc = int(_venc[0] or 0), float(_venc[1] or 0)
        _pag7 = float((await db.execute(_text(
            "SELECT coalesce(sum(net_value),0) FROM payable_accounts WHERE due_date BETWEEN current_date AND current_date+7 "
            "AND coalesce(status::text,'') NOT ILIKE '%pag%'"))).scalar() or 0)
        out["cockpit"] = {
            "title": "Cockpit executivo", "type": "dash", "cta": "—",
            "sub": "Visão de comando do financeiro — saldo, faturamento, recebíveis e o que precisa de atenção. Dado real, clicável.",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": brl(_saldo), "l": "Saldo consolidado (2 bancos)", "icon": "M3 21h18M4 10h16M5 10 12 4l7 6M6 10v11M18 10v11", "color": "#16277D", "to": "consolidacao-grupo"},
                {"v": brl(_fat_ult), "l": f"Faturamento {_fatm[-1][0] if _fatm else '—'}", "icon": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6", "color": "#16A34A", "to": "tendencias"},
                {"v": brl(_v_venc), "l": f"Recebíveis vencidos ({_n_venc})", "icon": "M12 8v4l3 3M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20", "color": "#C2410C" if _v_venc > 0 else "#16A34A", "to": "contas-receber"},
                {"v": brl(_pag7), "l": "A pagar (próx. 7 dias)", "icon": "M2 6h20M2 18h20M6 6v12M18 6v12", "color": "#0F1B3A", "to": "contas-pagar"},
            ],
            "chartGrid": "1fr 1fr",
            "charts": [
                {"type": "line", "title": "Faturamento mês a mês (R$)", "data": [
                    {"name": r[0], "value": round(float(r[1] or 0), 2)} for r in _fatm]},
                {"type": "donut", "title": "Caixa por CNPJ (R$)", "data": [
                    {"name": (str(r[0]) or "—"), "value": round(float(r[1] or 0), 2)} for r in _cnpj] or [{"name": "—", "value": 0}]},
            ],
            "panels": [
                {"title": "Precisa de atenção", "rows": [
                    {"left": "Recebíveis vencidos", "right": (brl(_v_venc) + f" ({_n_venc})") if _v_venc > 0 else "nada vencido ✓", **(S["bad"] if _v_venc > 0 else S["ok"])},
                    {"left": "A pagar em 7 dias", "right": brl(_pag7), **(S["warn"] if _pag7 >= 10000 else S["info"])},
                    {"left": "Saldo cobre os 7 dias?", "right": ("Sim ✓" if _saldo >= _pag7 else "Atenção — saldo < a pagar"), **(S["ok"] if _saldo >= _pag7 else S["bad"])},
                ]},
                {"title": "Atalhos", "rows": [
                    {"left": "Ver Balanço / DRE / DAS", "right": "g-fiscal", **S["info"]},
                    {"left": "Consultar o CFO (IA)", "right": "cfo", **S["info"]},
                    {"left": "Bancos & conciliação", "right": "g-bancos", **S["info"]},
                ]},
            ],
        }
    except Exception:  # noqa: BLE001
        pass

    # ── A2: Tendências temporais (série mês a mês) — faturamento bruto/líquido dos últimos 12 meses.
    # Reusa a query mensal real de nfse_emitidas_nacional; renderer de LINHA/ÁREA já existe (RdChart). ─
    try:
        from sqlalchemy import text as _text
        _fat = (await db.execute(_text(
            "SELECT competencia, coalesce(sum(valor_servicos),0), coalesce(sum(valor_liquido),0) "
            "FROM nfse_emitidas_nacional WHERE coalesce(cancelada,false)=false AND competencia IS NOT NULL "
            "GROUP BY 1 ORDER BY 1 DESC LIMIT 12"))).fetchall()
        _fat = list(reversed(_fat))
        if _fat:
            _ult = float(_fat[-1][1] or 0)
            _media = sum(float(r[1] or 0) for r in _fat) / len(_fat)
            out["tendencias"] = {
                "title": "Tendências — faturamento mês a mês", "type": "dash", "cta": "—",
                "sub": f"Evolução do faturamento NFS-e (bruto e líquido), últimos {len(_fat)} meses. Dado real.",
                "chartGrid": "1fr 1fr",
                "kpis": [
                    {"v": brl(_ult), "l": f"Faturamento {_fat[-1][0]}", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3", "color": "#16A34A", "to": "contas-receber"},
                    {"v": brl(_media), "l": f"Média mensal ({len(_fat)}m)", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3", "color": "#0F1B3A"},
                ],
                "charts": [
                    {"type": "line", "title": "Faturamento bruto por mês (R$)", "data": [
                        {"name": r[0], "value": round(float(r[1] or 0), 2)} for r in _fat]},
                    {"type": "area", "title": "Faturamento líquido por mês (R$)", "data": [
                        {"name": r[0], "value": round(float(r[2] or 0), 2)} for r in _fat]},
                ],
                "panelGrid": "1fr",
                "panels": [{"title": "Faturamento por competência", "rows": [
                    {"left": r[0], "right": brl(float(r[1] or 0)), **S["info"]} for r in _fat]}],
            }
    except Exception:  # noqa: BLE001
        pass
