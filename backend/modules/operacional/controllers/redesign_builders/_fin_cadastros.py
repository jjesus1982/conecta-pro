"""F7 — Compras & Estoque REAIS (corrige substitutos: 'compras' mostrava itens de NF-e e
'estoque' saldo derivado de NF-e). Fontes certas: purchase_requisitions/purchase_orders
(hoje 0 — vazio honesto, igual ao clássico) e fin_stock_items/fin_warehouses/
fin_stock_movements. As telas antigas ficam como abas renomeadas honestamente."""
from modules.operacional.controllers.redesign_data_controller import (
    S, _fmtdate, _helpers, _scalar, b, brl, t,
)


async def build_cadastros(db, out: dict) -> None:
    _, _safe, tbl = _helpers(db)

    # ── Compras (fluxo REAL: requisições + ordens — hoje vazio, dado honesto) ────────────
    try:
        n_req = await _scalar(db, "SELECT count(*) FROM purchase_requisitions") or 0
        n_ord = await _scalar(db, "SELECT count(*) FROM purchase_orders") or 0
        scr = await tbl(
            "Compras — requisições e ordens",
            f"{n_req} requisição(ões) · {n_ord} ordem(ns) de compra — fluxo real (purchase_*)",
            "—", ["Número", "Descrição", "Valor", "Data", "Status"], "1fr 2fr 1fr 1fr 0.9fr",
            "SELECT coalesce(number, id::text), coalesce(description, justification, '—'), "
            "estimated_total, requisition_date, coalesce(status::text,'—') FROM purchase_requisitions "
            "ORDER BY requisition_date DESC NULLS LAST LIMIT 100",
            lambda r: [t((r[0] or '—')[:14], 600, "#0F1B3A"), t((r[1] or '—')[:46]),
                       t(brl(r[2]) if r[2] is not None else '—'), t(_fmtdate(r[3])),
                       b((r[4] or '—').capitalize(), "info")])
        if not scr.get("rows"):
            scr["sub"] = "Nenhuma requisição/ordem registrada — fluxo de compras aguardando uso (dado real)"
        scr["panelGrid"] = "1fr"
        scr["panels"] = [{"title": "Fluxo de compras", "rows": [
            {"left": "Requisições", "right": str(n_req), **(S["info"] if n_req else S["mut"])},
            {"left": "Ordens de compra", "right": str(n_ord), **(S["info"] if n_ord else S["mut"])},
            {"left": "Itens de NF-e (entradas)", "right": "aba 'Compras (NF-e)'", **S["info"]},
        ]}]
        out["compras-reais"] = scr
    except Exception:  # noqa: BLE001
        pass

    # ── Estoque (fonte REAL: fin_stock_items + fin_warehouses + movimentos) ──────────────
    try:
        n_mov = await _scalar(db, "SELECT count(*) FROM fin_stock_movements") or 0
        scr = await tbl(
            "Estoque — itens e armazéns",
            f"{await _scalar(db, 'SELECT count(*) FROM fin_stock_items')} item(ns) · "
            f"{await _scalar(db, 'SELECT count(*) FROM fin_warehouses')} armazém(ns) · {n_mov} movimento(s)",
            "—", ["Produto", "Qtd em mãos", "Disponível", "Custo", "Status"], "2fr 0.9fr 0.9fr 1fr 0.9fr",
            "SELECT coalesce(p.nome, s.batch_number, s.location_code, s.id::text), s.quantity_on_hand, "
            "s.quantity_available, p.preco_custo, coalesce(s.status::text,'—') "
            "FROM fin_stock_items s LEFT JOIN fin_products p ON p.id=s.product_id ORDER BY 1 LIMIT 100",
            lambda r: [t((r[0] or '—')[:44], 600, "#0F1B3A"), t(str(r[1] if r[1] is not None else '—')),
                       t(str(r[2] if r[2] is not None else '—')),
                       t(brl(r[3]) if r[3] is not None else '—'), b((r[4] or '—').capitalize(), "info")])
        if not scr.get("rows"):
            scr["sub"] = "Sem itens no controle formal de estoque — dado real (saldo por NF-e na aba 'Estoque (NF-e)')"
        out["estoque-real"] = scr
    except Exception:  # noqa: BLE001
        pass

    # ── Fornecedores por categoria (suppliers + gasto via payable_accounts) — isolado da folha.
    # suppliers = fornecedores de NF-e/compras, nunca folha (domínio T2). Read-only. ─────────
    try:
        from sqlalchemy import text as _text
        cats = (await db.execute(_text(
            "SELECT coalesce(s.category,'sem categoria'), count(DISTINCT s.id), coalesce(sum(pa.net_value),0) "
            "FROM suppliers s LEFT JOIN payable_accounts pa ON pa.supplier_id=s.id "
            "GROUP BY 1 ORDER BY 3 DESC"))).fetchall()
        n_forn = int((await db.execute(_text("SELECT count(*) FROM suppliers"))).scalar() or 0)
        gasto_tot = sum(float(c[2] or 0) for c in cats)
        tops = (await db.execute(_text(
            "SELECT coalesce(s.name, s.trade_name, '—'), coalesce(s.category,'—'), coalesce(sum(pa.net_value),0) "
            "FROM suppliers s LEFT JOIN payable_accounts pa ON pa.supplier_id=s.id "
            "GROUP BY s.id, s.name, s.trade_name, s.category HAVING coalesce(sum(pa.net_value),0) > 0 "
            "ORDER BY 3 DESC LIMIT 10"))).fetchall()
        scr = {
            "title": "Fornecedores por categoria", "type": "table", "cta": "—", "searchHint": "Buscar categoria…",
            "sub": (f"{n_forn} fornecedores · gasto total R$ {gasto_tot:,.2f} (via contas a pagar). "
                    "Categorização automática por CNPJ/nome (fornecedor_categoria_service). Isolado da folha."),
            "grid": "1.8fr 1fr 1.3fr",
            "cols": ["Categoria", "Fornecedores", "Gasto (contas a pagar)"],
            "rows": [{"cells": [
                t((str(c[0]) or "—").replace("_", " ").capitalize(), 600, "#0F1B3A"),
                t(str(int(c[1]))), t(brl(float(c[2] or 0)), 600)]} for c in cats]
                or [{"cells": [t("Sem fornecedores"), t("0"), t("—")]}],
            "panelGrid": "1fr",
            "panels": [{"title": "Maiores fornecedores (por gasto)", "rows": [
                {"left": f"{(str(r[0]) or '—')[:34]} · {(str(r[1]) or '—').replace('_',' ')}", "right": brl(float(r[2] or 0)), **S["info"]}
                for r in tops] or [{"left": "Sem gasto registrado", "right": "—", **S["mut"]}]}],
        }
        out["fornecedores-categoria"] = scr
    except Exception:  # noqa: BLE001
        pass
