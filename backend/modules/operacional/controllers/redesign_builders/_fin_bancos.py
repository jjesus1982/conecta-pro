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
