"""F2 — Bancos & Conciliação: contas bancárias reais, conciliação bancária de EXTRATO
(bank_reconciliations + matching status das bank_transactions) — corrige a lacuna em que a
tela 'conciliacao' só mostrava folha×Inter. Rotas verificadas: /financial/bank-accounts 200,
/financial/bank-reconciliations?bank_account_id 200; pending-reconciliation=500 (bug backend,
NÃO fiado); import OFX é POST JSON de transações parseadas (UI de upload = iteração futura)."""
from sqlalchemy import text

from modules.operacional.controllers.redesign_data_controller import (
    S, _fmtdate, _helpers, _scalar, b, brl, t,
)


async def build_bancos(db, out: dict) -> None:
    _, _safe, tbl = _helpers(db)

    # ── Contas bancárias (bank_accounts: Inter + Cora, saldos reais) ─────────────────────
    try:
        out["contas-bancarias"] = await tbl(
            "Contas bancárias",
            f"{await _scalar(db, 'SELECT count(*) FROM bank_accounts')} contas cadastradas",
            "—", ["Banco", "Conta", "Saldo atual", "Disponível", "Status"], "1.6fr 1fr 1.1fr 1.1fr 0.8fr",
            "SELECT coalesce(bank_name, name, '—'), coalesce(account_number,'—') || coalesce('-'||account_digit,''), "
            "current_balance, available_balance, coalesce(status::text,'—') FROM bank_accounts ORDER BY bank_name LIMIT 50",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(brl(r[2]) if r[2] is not None else '—', 600),
                       t(brl(r[3]) if r[3] is not None else '—'),
                       b((r[4] or '—').capitalize(), "ok" if (r[4] or '').lower() in ('active', 'ativa', 'ativo') else "mut")])
    except Exception:  # noqa: BLE001
        pass

    # ── Conciliação bancária de EXTRATO (a REAL — bank_reconciliations + matching) ───────
    _rtone = {"completed": "ok", "concluida": "ok", "in_progress": "warn", "em_andamento": "warn", "draft": "mut"}
    try:
        scr = await tbl(
            "Conciliação bancária (extrato)",
            f"{await _scalar(db, 'SELECT count(*) FROM bank_reconciliations')} conciliações — extrato × sistema",
            "—", ["Período", "Banco", "Itens conciliados", "Pendentes", "Diferença", "Status"],
            "1.1fr 1.2fr 1fr 0.9fr 1fr 0.9fr",
            "SELECT to_char(r.period_start,'DD/MM') || '–' || to_char(r.period_end,'DD/MM/YY'), "
            "coalesce(a.bank_name,'—'), coalesce(r.items_reconciled,0), coalesce(r.items_pending,0), "
            "r.difference, coalesce(r.status::text,'—') "
            "FROM bank_reconciliations r LEFT JOIN bank_accounts a ON a.id=r.bank_account_id "
            "ORDER BY r.period_start DESC LIMIT 100",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(str(r[2])), b(str(r[3]), "warn" if r[3] else "mut"),
                       t(brl(r[4]) if r[4] is not None else '—'),
                       b((r[5] or '—').replace('_', ' ').capitalize(), _rtone.get((r[5] or '').lower(), "info"))])
        # Matching das transações (o coração da conciliação): status real das 5.136 transações.
        stt = (await db.execute(text(
            "SELECT coalesce(reconciliation_status::text,'sem status'), count(*) "
            "FROM bank_transactions GROUP BY 1 ORDER BY 2 DESC"))).fetchall()
        _tone = {"conciliado": S["ok"], "justificado": S["info"], "pendente": S["warn"]}
        scr["panelGrid"] = "1fr 1fr"
        scr["panels"] = [
            {"title": "Transações por status de conciliação", "rows": [
                {"left": (s or '—').capitalize(), "right": f"{c:,}".replace(",", "."),
                 **_tone.get((s or '').lower(), S["mut"])} for s, c in stt]},
            {"title": "Importação de extrato", "rows": [
                {"left": "Sincronização Inter/Cora", "right": "Automática (conector)", **S["ok"]},
                {"left": "Upload manual OFX", "right": "Backend pronto (via API) — UI próxima", **S["info"]},
            ]},
        ]
        out["conciliacao-bancaria"] = scr
    except Exception:  # noqa: BLE001
        pass

    # ── Rodar conciliação automática (matching extrato×contas) — bookkeeping, não move dinheiro ──
    out["conciliar-auto"] = {
        "title": "Rodar conciliação automática",
        "sub": "Casa o extrato bancário com contas a pagar/receber (valor ±R$0,01 ou ±2% + data ±3/7 dias). "
               "NÃO move dinheiro — só marca o status de conciliação. Sem match → fica para justificar.",
        "cta": "Rodar conciliação agora", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/conciliar-auto", "gated": False,
                   "confirm": "Rodar o matching automático de todas as transações pendentes agora?",
                   "okMsg": "Conciliação executada."},
        "fields": [],
    }

    # ── Conciliação CONSOLIDADA por mês: líquido faturado (NFS-e) × recebido no banco
    # (Inter+Cora). Modelo mensal (robusto ao lag de pagamento). O que cai no banco é o
    # LÍQUIDO (bruto − ISS − retenções), por isso comparamos com valor_liquido, não bruto. ──
    try:
        emit = {r[0]: float(r[1] or 0) for r in (await db.execute(text(
            "SELECT to_char(data_emissao,'YYYY-MM'), sum(valor_liquido) FROM nfse_emitidas_nacional "
            "WHERE coalesce(valor_liquido,0)>0 GROUP BY 1"))).fetchall()}
        recv = {r[0]: float(r[1] or 0) for r in (await db.execute(text(
            "SELECT to_char(bt.transaction_date,'YYYY-MM'), sum(abs(bt.amount)) FROM bank_transactions bt "
            "JOIN bank_accounts ba ON ba.id=bt.bank_account_id WHERE ba.bank_code IN ('077','403') "
            "AND bt.transaction_type IN ('credit','credito') GROUP BY 1"))).fetchall()}
        meses = sorted(set(emit) | set(recv), reverse=True)[:8]
        rows, acc_e, acc_r = [], 0.0, 0.0
        for m in meses:
            e = emit.get(m, 0.0); rc = recv.get(m, 0.0); acc_e += e; acc_r += rc
            saldo = rc - e
            rows.append({"cells": [
                t(m, 600, "#0F1B3A"), t(brl(e), 600), t(brl(rc), 600), t(brl(saldo)),
                b("recebido ≥ faturado" if saldo >= -0.5 else "conferir", "ok" if saldo >= -0.5 else "warn")]})
        scr = {
            "title": "Conciliação consolidada por mês", "type": "table", "cta": "—",
            "sub": (f"Líquido faturado (NFS-e, após ISS+retenções) × recebido no banco (Inter+Cora), por mês. "
                    f"Acumulado: faturado {brl(acc_e)} · recebido {brl(acc_r)} · saldo {brl(acc_r - acc_e)}. "
                    "Recebido ≥ faturado = sem inadimplência (a sobra é o lag: pagamento cai no mês seguinte)."),
            "grid": "0.9fr 1.3fr 1.4fr 1.2fr 1.3fr",
            "cols": ["Mês", "Líquido faturado", "Recebido (Inter+Cora)", "Saldo", "Status"],
            "rows": rows or [{"cells": [t("Sem dados"), t("—"), t("—"), t("—"), b("—", "mut")]}],
            "panelGrid": "1fr",
            "panels": [{"title": "Leitura", "rows": [
                {"left": "Recebido inclui TODOS os créditos (clientes + transferências/outros)", "right": "atenção", **S["warn"]},
                {"left": "Casamento fino nota↔crédito é pelo LÍQUIDO (ex.: IDEAL FLORES 55.355,64 = crédito Inter)", "right": "ok", **S["ok"]},
                {"left": "Notas sem crédito no mês = pagas no mês seguinte, Cora ou Itaú", "right": "lag", **S["info"]},
            ]}],
        }
        out["conciliacao-consolidada"] = scr
    except Exception:  # noqa: BLE001
        pass

    # ── Conciliação POR LÍQUIDO (NFS-e valor_liquido ↔ crédito Inter/Cora) — relatório read-only.
    # Casa pelo que REALMENTE cai na conta (líquido, e líquido−INSS quando retido). Baixa = ação gated. ─
    try:
        from modules.financial.services.conciliacao_liquido_service import casar_notas_banco
        rep = await casar_notas_banco(db, "2026-01-01", "2026-12-31", persistir=False)
        scr = {
            "title": "Conciliação por líquido (NFS-e × banco)", "type": "table", "cta": "—", "searchHint": "Buscar cliente…",
            "sub": (f"{rep['n_casados']} nota(s) casada(s) pelo LÍQUIDO ({rep['pct_casado']}% do faturado) · "
                    f"{rep['n_sugestoes']} sugestão(ões) a revisar · {rep['n_sem']} sem crédito (Cora/Itaú/recente). "
                    f"Líquido conciliado R$ {rep['liquido_casado']:,.2f} de R$ {rep['liquido_total']:,.2f}. "
                    "Baixa é ação gated (aba 'Aplicar conciliação')."),
            "grid": "2fr 1.1fr 1.1fr 1fr 0.9fr",
            "cols": ["Cliente", "Líquido (nota)", "Crédito (banco)", "Data crédito", "Match"],
            "rows": [{"cells": [
                t((m["cliente"] or "—")[:34], 600, "#0F1B3A"), t(brl(m["liquido"]), 600),
                t(brl(m["credito_valor"]), 600), t(str(m["credito_data"])),
                b("exato" + (" (−INSS)" if m["inss"] > 0 else ""), "ok")]} for m in rep["casados"]],
            "panelGrid": "1fr 1fr",
            "panels": [
                {"title": f"Sugestões a revisar ({rep['n_sugestoes']}) — identidade bate, valor aproximado",
                 "rows": [{"left": f"{(s['cliente'] or '—')[:26]} · líq {brl(s['liquido'])}",
                           "right": f"{brl(s['credito_valor'])} (dif {brl(s['diff'])})", **S["warn"]}
                          for s in rep["sugestoes"][:8]] or [{"left": "Nenhuma sugestão pendente", "right": "—", **S["ok"]}]},
                {"title": f"Sem crédito no banco ({rep['n_sem']}) — pago via Cora/Itaú ou recente",
                 "rows": [{"left": f"{(n['cliente'] or '—')[:26]} · emit {n['emissao']}",
                           "right": brl(n["liquido"]), **S["info"]} for n in rep["notas_sem"][:8]]
                         or [{"left": "Todas as notas casaram", "right": "—", **S["ok"]}]},
            ],
        }
        out["conciliacao-por-liquido"] = scr
    except Exception:  # noqa: BLE001
        pass

    # Ação gated: aplicar a conciliação por líquido (marca os créditos exatos como conciliados)
    out["aplicar-conciliacao-liquido"] = {
        "title": "Aplicar conciliação por líquido",
        "sub": "Marca como CONCILIADOS os créditos do banco que casaram EXATO com o líquido das NFS-e "
               "(só os exatos; sugestões ficam de fora). Bookkeeping — NÃO move dinheiro nem altera contas a receber.",
        "cta": "Aplicar conciliação", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/conciliar-liquido", "gated": False,
                   "confirm": "Marcar como conciliados os créditos que casaram exato com o líquido das notas?",
                   "okMsg": "Conciliação por líquido aplicada."},
        "fields": [
            {"key": "inicio", "label": "Início (AAAA-MM-DD)", "type": "date", "span": "span 1", "ph": "2026-01-01"},
            {"key": "fim", "label": "Fim (AAAA-MM-DD)", "type": "date", "span": "span 1", "ph": "2026-12-31"},
        ],
    }
