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
