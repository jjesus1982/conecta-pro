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
