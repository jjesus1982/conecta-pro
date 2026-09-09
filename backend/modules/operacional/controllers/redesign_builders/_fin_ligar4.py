"""Lote 4 LIGAR (08/09/2026) — telas do financeiro para rotas que só existiam por API. Chamado por financeiro.build antes de montar_grupos."""

async def build_ligar4(db, out: dict) -> None:
    """LIGAR lote 4 (08/09/2026): rotas que existiam sem tela (vereditos B e C). Blocos independentes (try/except + rollback).
    Regra da casa: a página nunca chama Drive/robô/governo — leituras do Drive viram formulários GET que o usuário dispara."""
    import logging as _lg
    from datetime import date as _dt
    from sqlalchemy import text as _T
    from modules.operacional.controllers.redesign_data_controller import _helpers, t, b, brl
    from modules.operacional.controllers.redesign_builders._ligar_generico import chamar, painel_de_dict, selecionar, tabela_de_lista
    _log = _lg.getLogger(__name__)
    _, _safe, tbl = _helpers(db)
    _SN = [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]
    hoje = _dt.today()

    def _fd(v, fmt="%d/%m/%Y"):
        try:
            return v.strftime(fmt) if v else "—"
        except Exception:  # noqa: BLE001
            return str(v or "—")

    async def _n(sql):
        try:
            return (await db.execute(_T(sql))).scalar() or 0
        except Exception:  # noqa: BLE001
            await db.rollback(); return 0

    def _consulta(key, titulo, sub, endpoint, fields, method="GET"):
        """Form de CONSULTA: dispara o GET com query e mostra o resultado (a página não chama nada ao abrir)."""
        out[key] = {"title": titulo, "sub": sub, "cta": "Consultar", "type": "form",
                    "submit": {"endpoint": endpoint, "method": method, "query": True, "okMsg": "Consulta feita — veja o resultado.", "showResult": True},
                    "fields": fields}

    try:  # GET /financeiro/inter/payments/audit — por SQL
        out["pagamentos-auditoria"] = await tbl(
            "Pagamentos Inter — trilha de auditoria", f"{await _n('SELECT count(*) FROM inter_payment_audit')} eventos · quem mudou o status de cada pagamento, quando e de onde · fonte: inter_payment_audit", "—",
            ["Quando", "Usuário", "Destinatário", "Valor", "De → para", "Motivo", "IP"], "1fr 1.2fr 1.6fr 0.9fr 1.1fr 1.4fr 0.8fr",
            "SELECT a.created_at, coalesce(u.email,'—'), coalesce(p.destinatario->>'nome', p.destinatario->>'name', p.destinatario->>'chave', p.destinatario::text, '—'), p.valor, coalesce(a.status_from,'—') || ' → ' || coalesce(a.status_to,'—'), coalesce(a.motivo,''), coalesce(a.ip_address,'—') "
            "FROM inter_payment_audit a LEFT JOIN users u ON u.id=a.user_id LEFT JOIN inter_payments p ON p.id=a.payment_id ORDER BY a.created_at DESC LIMIT 200",
            lambda r: [t(_fd(r[0], "%d/%m/%Y %H:%M")), t(r[1][:30]), t(r[2][:40], 600, "#0F1B3A"), t(brl(r[3]) if r[3] is not None else "—", 600), b(r[4], "info"), t(r[5][:50] or "—"), t(r[6])])
    except Exception as exc:  # noqa: BLE001
        await db.rollback(); _log.warning("pagamentos-auditoria: %s", exc)
    try:  # GET /financial/payables/installments/pending — por SQL
        n_parc = await _n("SELECT count(*) FROM payable_installments WHERE status IN ('pendente','parcial','pending')")
        out["parcelas-pendentes"] = await tbl(
            "Parcelas pendentes", f"{n_parc} parcela(s) em aberto · fonte: payable_installments × payable_accounts", "—",
            ["Conta", "Parcela", "Vencimento", "Valor", "Pago", "Status"], "2.2fr 0.7fr 0.9fr 0.9fr 0.9fr 0.8fr",
            "SELECT coalesce(a.description, i.description, '—'), i.installment_number || '/' || coalesce(i.total_installments, a.total_installments, i.installment_number), i.due_date, i.current_value, coalesce(i.paid_amount,0), coalesce(i.status,'—') "
            "FROM payable_installments i LEFT JOIN payable_accounts a ON a.id=i.payable_account_id WHERE i.status IN ('pendente','parcial','pending') AND coalesce(i.ativo,true) ORDER BY i.due_date LIMIT 200",
            lambda r: [t(r[0][:60], 600, "#0F1B3A"), t(str(r[1])), b(_fd(r[2]), "bad" if r[2] and r[2] < hoje else "info"), t(brl(r[3]) if r[3] is not None else "—", 600), t(brl(r[4])), b(r[5].capitalize(), "warn")])
    except Exception as exc:  # noqa: BLE001
        await db.rollback(); _log.warning("parcelas-pendentes: %s", exc)
    out["pagaveis-recorrentes-gerar"] = {  # POST /financial/payables/process-recurring
        "title": "Gerar contas recorrentes do mês", "sub": f"Cria as contas a pagar do mês a partir das {await _n('SELECT count(*) FROM payable_accounts WHERE is_recurring=true')} contas marcadas como recorrentes. Só cria registros — não paga.",
        "cta": "Gerar", "type": "form", "submit": {"endpoint": "/api/v1/financial/payables/process-recurring", "query": True, "okMsg": "Contas geradas — veja o resultado.", "showResult": True},
        "fields": [{"key": "reference_date", "label": "Data de referência (opcional)", "type": "date", "span": "span 1"}]}
    meses = [(hoje.year, hoje.month), ((hoje.year if hoje.month > 1 else hoje.year - 1), (hoje.month - 1 or 12)), ((hoje.year if hoje.month < 12 else hoje.year + 1), (hoje.month % 12 + 1))]
    out["folha-pj-programar"] = {  # POST /financial/pagamentos-pj/programar/{ano}/{mes}
        "title": "Folha PJ — programar o mês", "sub": "Monta os itens da folha PJ do mês (salário + VA/VT por dias úteis) em financial_pagamentos_pj. É o passo ANTES de 'Pagar folha PJ' — sem ele o pagamento diz 'nenhum item elegível'. Não paga nada.",
        "cta": "—", "type": "table", "searchHint": "", "grid": "1fr 1.4fr", "cols": ["Competência", "Itens já programados"],
        "rows": []}
    for ano, mes in meses:
        n = await _n(f"SELECT count(*) FROM financial_pagamentos_pj WHERE competencia='{mes:02d}/{ano}' OR competencia='{ano}-{mes:02d}'")
        out["folha-pj-programar"]["rows"].append({"cells": [t(f"{mes:02d}/{ano}", 600, "#0F1B3A"), t(str(n))],
                                                  "actions": [{"title": f"Programar folha PJ {mes:02d}/{ano}", "endpoint": f"/api/v1/financial/pagamentos-pj/programar/{ano}/{mes}", "method": "POST",
                                                               "btnLabel": "Programar", "btnStyle": "primary", "submitLabel": "Programar", "okMsg": "Folha PJ programada. Recarregue.", "fields": []}]})
    conds = []
    try:
        conds = [{"value": str(i), "label": n} for i, n in (await db.execute(_T("SELECT id, name FROM condominiums WHERE coalesce(is_active,true) ORDER BY name LIMIT 300"))).fetchall()]
    except Exception:  # noqa: BLE001
        await db.rollback()
    _consulta("fluxo-resumo", "Fluxo de caixa — resumo do período", "Entradas, saídas e saldo previsto × realizado nos últimos N dias (cashflow_entries, espelho do extrato).",
              "/api/v1/financial/cashflow/summary", [{"key": "period_days", "label": "Período (dias, 7–365)", "type": "number", "span": "span 1", "value": 30}, selecionar("condominio_id", "Condomínio (opcional)", conds, "span 1")])
    _consulta("fluxo-tendencia", "Fluxo de caixa — tendência mensal", "Entradas e saídas mês a mês nos últimos N meses.",
              "/api/v1/financial/cashflow/trends", [{"key": "months", "label": "Meses (3–24)", "type": "number", "span": "span 1", "value": 12}, selecionar("condominio_id", "Condomínio (opcional)", conds, "span 1")])
    _consulta("fluxo-categorias", "Fluxo de caixa — saídas por categoria", "Composição das saídas de um condomínio no período (a rota exige o condomínio).",
              "/api/v1/financial/cashflow/category-breakdown", [selecionar("condominio_id", "Condomínio*", conds, "span 2"), {"key": "start_date", "label": "De", "type": "date", "span": "span 1"}, {"key": "end_date", "label": "Até", "type": "date", "span": "span 1"}])
    _consulta("fluxo-fornecedores", "Fluxo de caixa — saídas por fornecedor", "Maiores fornecedores de um condomínio no período.",
              "/api/v1/financial/cashflow/supplier-breakdown", [selecionar("condominio_id", "Condomínio*", conds, "span 2"), {"key": "start_date", "label": "De", "type": "date", "span": "span 1"}, {"key": "end_date", "label": "Até", "type": "date", "span": "span 1"}, {"key": "limit", "label": "Top N (1–50)", "type": "number", "span": "span 1", "value": 10}])
    _consulta("dre-consolidado", "DRE consolidado por empresa (grupo)", "Receita, custo e resultado por CNPJ a partir dos lançamentos contábeis (accounting_entries). Período AAAA-MM; vazio = tudo.",
              "/api/v1/financial/accounting/dre-consolidado", [{"key": "periodo", "label": "Período (AAAA-MM)", "type": "text", "span": "span 1", "value": hoje.strftime("%Y-%m")}])
    try:  # GET /financial/inventory/real/movimentos + /resumo
        out["estoque-movimentos"] = await tbl(
            "Estoque — movimentos", f"{await _n('SELECT count(*) FROM nfe_estoque_movimentos')} movimento(s) · saídas registradas contra as compras por NF-e · fonte: nfe_estoque_movimentos", "—",
            ["Data", "Item", "Tipo", "Qtde", "Valor", "Serviço/OS", "Motivo"], "0.8fr 2fr 0.7fr 0.6fr 0.9fr 1fr 1.4fr",
            "SELECT data_mov, coalesce(descricao, item_code, '—'), coalesce(tipo,'—'), quantidade, valor_total, coalesce(servico_ref,'—'), coalesce(motivo,'') FROM nfe_estoque_movimentos ORDER BY data_mov DESC NULLS LAST, created_at DESC LIMIT 200",
            lambda r: [t(_fd(r[0])), t(r[1][:50], 600, "#0F1B3A"), b(r[2].capitalize(), "warn" if r[2] in ("saida", "saída") else "ok"), t(str(r[3] or 0)), t(brl(r[4]) if r[4] is not None else "—"), t(r[5]), t(r[6][:50] or "—")])
        from modules.financial.controllers import inventory_controller as Inv
        res = await chamar(Inv.estoque_real_resumo, db)
        out["estoque-resumo"] = painel_de_dict("Estoque — resumo", "Itens, valor em estoque, saídas do mês e itens zerados — mesma conta da rota /inventory/real/resumo.", res)
    except Exception as exc:  # noqa: BLE001
        await db.rollback(); _log.warning("estoque lote4: %s", exc)

