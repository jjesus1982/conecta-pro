"""Documentos/GED (T1) — override do _build_documentos + telas kits e pastas (leitura real)."""
from sqlalchemy import text

from modules.operacional.controllers.redesign_data_controller import (
    IC, S, _ged_screen, _helpers, _scalar, b, t,
)

SLUG = "documentos"
EXTRA_MENU: list[dict] = []


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)
    n_ged = await _scalar(db, "SELECT count(*) FROM ged_kit_documents")
    n_signed = await _scalar(db, "SELECT count(*) FROM ged_kit_documents WHERE is_signed=true")

    async def _visao():
        ty = (await db.execute(text("SELECT document_type::text, count(*) FROM ged_kit_documents GROUP BY document_type ORDER BY count(*) DESC LIMIT 8"))).fetchall()
        return {"title": "Visão geral", "sub": "Documentos (GED) — dados reais", "cta": "Enviar documento", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": f"{n_ged:,}".replace(",", "."), "l": "Documentos", "icon": IC["cal"], "color": "#0F1B3A"},
                    {"v": f"{n_signed:,}".replace(",", "."), "l": "Assinados", "icon": IC["shield"], "color": "#16A34A"},
                    {"v": str(await _scalar(db, "SELECT count(DISTINCT employee_id) FROM ged_kit_documents") or 0), "l": "Colaboradores", "icon": IC["users"], "color": "#0F1B3A"},
                    {"v": str(await _scalar(db, "SELECT count(*) FROM ged_document_kits") or 0), "l": "Kits", "icon": IC["cal"], "color": "#0F1B3A"},
                ],
                "panels": [
                    {"title": "Documentos por tipo", "rows": [{"left": (s or "—").replace("_", " ").capitalize(), "right": str(c), **S["ok"]} for s, c in ty] or [{"left": "Sem documentos", "right": "0", **S["mut"]}]},
                    {"title": "Assinatura", "rows": [{"left": "Assinados", "right": str(n_signed), **S["ok"]}, {"left": "Pendentes", "right": str((n_ged or 0) - (n_signed or 0)), **S["warn"]}]},
                ]}

    await safe("visao", _visao())
    await safe("arquivos", _ged_screen(db, tbl))

    # Kits de documentos por competência — ged_document_kits (58). client_id é órfão
    # (não casa com clients/condominiums) → mostro os campos reais de completude.
    _kit_tone = {"completo": "ok", "aprovado": "ok", "enviado": "ok", "concluido": "ok", "em_montagem": "warn", "pendente": "warn", "montando": "warn"}
    await safe("kits", tbl(
        "Kits de documentos", f"{await _scalar(db, 'SELECT count(*) FROM ged_document_kits')} kits", "—",
        ["Competência", "Colaboradores", "Docs", "Assinados", "Completude", "Status"], "1fr 1fr 0.8fr 0.8fr 1fr 1.1fr",
        "SELECT to_char(reference_month,'MM/YYYY'), total_employees, total_documents, documents_signed, completion_percentage, coalesce(status::text,'—') "
        "FROM ged_document_kits ORDER BY reference_month DESC NULLS LAST, completion_percentage DESC LIMIT 200",
        lambda r: [t(r[0] or '—', 600, "#0F1B3A"), t(f"{int(r[1] or 0)}"), t(f"{int(r[2] or 0)}"), t(f"{int(r[3] or 0)}"),
                   t(f"{float(r[4] or 0):.0f}%", 600), b((r[5] or '—').replace('_', ' ').capitalize(), _kit_tone.get((r[5] or '').lower(), "info"))]))

    # Pastas (GED / Drive) — ged_folders (8)
    await safe("pastas", tbl(
        "Pastas", f"{await _scalar(db, 'SELECT count(*) FROM ged_folders')} pastas", "—",
        ["Pasta", "Código", "Tipo", "Nível", "Status"], "1.8fr 1.2fr 1.1fr 0.7fr 0.9fr",
        "SELECT coalesce(name,'—'), coalesce(code,'—'), coalesce(folder_type::text,'—'), level, coalesce(status::text,'—') "
        "FROM ged_folders ORDER BY coalesce(path,'') LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t((r[2] or '—').replace('_', ' ').capitalize()), t(f"{int(r[3] or 0)}"),
                   b((r[4] or '—').capitalize(), "ok" if (r[4] or '').lower() in ("ativa", "ativo", "active") else "mut")]))

    return out
