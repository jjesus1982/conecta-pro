"""F3 — Pagar: aging com KPIs (espelho do endpoint /payables/aging: sum(net_value),
status NOT IN ('pago','cancelado')), fila de aprovação (LEITURA — aprovar segue ação
humana gated fora desta tela) e AUDIT LOG dos pagamentos Inter (trilha real da tabela:
prepared_by/approved_by/otp/executed_at). Nenhum pagamento é disparado por estas telas."""
from sqlalchemy import text

from modules.operacional.controllers.redesign_data_controller import (
    S, _fmtdate, _helpers, _scalar, b, brl, t,
)


async def build_pagar(db, out: dict) -> None:
    _, _safe, tbl = _helpers(db)

    # ── Aging na tela (espelho EXATO do endpoint /financial/payables/aging) ─────────────
    try:
        faixas = (await db.execute(text(
            "SELECT CASE WHEN due_date >= CURRENT_DATE THEN '1. A vencer' "
            "WHEN due_date >= CURRENT_DATE-30 THEN '2. Vencidas até 30d' "
            "WHEN due_date >= CURRENT_DATE-60 THEN '3. Vencidas 31-60d' "
            "WHEN due_date >= CURRENT_DATE-90 THEN '4. Vencidas 61-90d' "
            "ELSE '5. Acima de 90d' END AS faixa, count(*), coalesce(sum(net_value),0) "
            "FROM payable_accounts WHERE status::text NOT IN ('pago','cancelado') "
            "GROUP BY 1 ORDER BY 1"))).fetchall()
        if isinstance(out.get("contas-pagar"), dict):
            out["contas-pagar"]["panelGrid"] = "1fr"
            out["contas-pagar"]["panels"] = [{"title": "Aging — contas em aberto", "rows": [
                {"left": f[3:], "right": f"{n} · {brl(v)}",
                 **(S["ok"] if f.startswith('1.') else S["warn"] if f.startswith('2.') else S["bad"])}
                for f, n, v in faixas] or [{"left": "Sem contas em aberto", "right": "0", **S["ok"]}]}]
    except Exception:  # noqa: BLE001
        pass

    # ── Fila de aprovação (LEITURA) — inter_payments preparados + payables requires_approval.
    # Aprovar/agendar = ação humana no fluxo gated (OTP); esta tela SÓ mostra a fila. ──
    try:
        n_prep = await _scalar(db, "SELECT count(*) FROM inter_payments WHERE lower(status)='preparado'")
        n_req = await _scalar(db, "SELECT count(*) FROM payable_accounts WHERE requires_approval=true AND coalesce(approval_status::text,'') NOT IN ('approved','aprovado')")
        scr = await tbl(
            "Fila de aprovação (D7)",
            f"{(n_prep or 0)} pagamento(s) Inter preparado(s) · {(n_req or 0)} conta(s) exigindo aprovação — aprovar é ação humana gated (fora desta tela)",
            "—", ["Origem", "Descrição", "Valor", "Preparado em", "Status"], "1fr 1.8fr 1fr 1fr 0.9fr",
            "SELECT 'Inter', coalesce(destinatario->>'nome_recebedor', destinatario->>'chave', left(destinatario->>'codigo_barras',22), payment_type), "
            "valor, created_at, coalesce(status,'—') FROM inter_payments WHERE lower(status)='preparado' "
            "UNION ALL "
            "SELECT 'Contas a pagar', coalesce(description,'—'), net_value, created_at, coalesce(approval_status::text,'aguardando') "
            "FROM payable_accounts WHERE requires_approval=true AND coalesce(approval_status::text,'') NOT IN ('approved','aprovado') "
            "ORDER BY 4 DESC LIMIT 100",
            lambda r: [b(r[0], "info"), t((r[1] or '—')[:44], 600, "#0F1B3A"),
                       t(brl(r[2]) if r[2] is not None else '—', 600), t(_fmtdate(r[3])),
                       b((r[4] or '—').capitalize(), "warn")])
        if not scr.get("rows"):
            scr["sub"] = "Nenhum pagamento aguardando aprovação — fila vazia (dado real)"
        out["fila-aprovacao"] = scr
    except Exception:  # noqa: BLE001
        pass

    # ── AUDIT LOG dos pagamentos Inter — trilha REAL da tabela (quem preparou/aprovou,
    # OTP usado, quando executou/confirmou/cancelou). Era só do clássico; agora exposta. ──
    _atone = {"confirmado": "ok", "executado": "ok", "preparado": "warn", "cancelado": "mut", "erro": "bad"}
    try:
        out["audit-log"] = await tbl(
            "Audit log de pagamentos (Inter)",
            f"{await _scalar(db, 'SELECT count(*) FROM inter_payments')} pagamentos — trilha completa de auditoria",
            "—", ["Destinatário", "Valor", "Preparado por", "Aprovado por", "OTP", "Executado", "Status"],
            "1.6fr 0.9fr 1.1fr 1.1fr 0.6fr 1fr 0.9fr",
            "SELECT coalesce(p.destinatario->>'nome_recebedor', p.destinatario->>'chave', left(p.destinatario->>'codigo_barras',18), p.payment_type), "
            "p.valor, coalesce(u1.email, left(p.prepared_by::text,8), '—'), coalesce(u2.email, left(p.approved_by::text,8), '—'), "
            "(p.approval_otp_used IS NOT NULL AND p.approval_otp_used<>''), "
            "coalesce(p.executed_at, p.confirmed_at, p.cancelled_at), coalesce(p.status,'—') "
            "FROM inter_payments p LEFT JOIN users u1 ON u1.id=p.prepared_by LEFT JOIN users u2 ON u2.id=p.approved_by "
            "ORDER BY p.created_at DESC LIMIT 200",
            lambda r: [t((r[0] or '—')[:34], 600, "#0F1B3A"), t(brl(r[1]) if r[1] is not None else '—', 600),
                       t((r[2] or '—')[:18]), t((r[3] or '—')[:18]),
                       b("✓", "ok") if r[4] else t("—"), t(_fmtdate(r[5], "%d/%m %H:%M") if r[5] else '—'),
                       b((r[6] or '—').capitalize(), _atone.get((r[6] or '').lower(), "info"))])
    except Exception:  # noqa: BLE001
        pass
