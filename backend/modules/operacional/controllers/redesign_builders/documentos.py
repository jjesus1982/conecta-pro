"""Documentos/GED (T1) — override do _build_documentos + telas kits e pastas (leitura real)."""
from sqlalchemy import text

from modules.operacional.controllers.redesign_data_controller import (
    IC, S, _helpers, _scalar, b, doc, t,
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
                ],
                # PILOTO DA FUNDAÇÃO (docs nível-tela) — prova os 3 modos de fonte do DocButtons:
                #  • blob  : documento GED real (FileResponse) → abre/baixa o arquivo direto.
                #  • json  : export conciliação ({content,filename}) → decodifica p/ Blob.
                #  • disabled: honesto (stub/sem-transmissão) → botão off + tooltip, nunca abre lixo.
                # Depois vira o EXEMPLO-ÂNCORA que os builders de cada território replicam.
                "docs": [
                    doc("Documento GED (exemplo)", "/api/v1/ged/documents/9c672ac5-7c71-4fa2-bf17-c90719c0b833/download", fmt="pdf", mode="blob"),
                    doc("Export conciliação (CSV)", "/api/v1/financial/bank-reconciliations/e9d72c71-eabd-4652-9de8-f1b9b2357b7e/export", fmt="csv", mode="json", gate="financeiro"),
                    doc("SPED (aguardando)", disabled=True, motivo="Aguardando emissão real — botão liga quando o arquivo existir"),
                ]}

    await safe("visao", _visao())
    # PILOTO (docs por-LINHA) — cada documento GED ganha Abrir/Baixar via download real (FileResponse).
    # Este é o padrão de row.docs que os builders replicam onde o clássico tem download por item.
    await safe("arquivos", tbl(
        "Arquivos", f"{n_ged} documentos", "Enviar documento",
        ["Documento", "Tipo", "Colaborador", "Assinado"], "2fr 1.4fr 1.6fr 0.9fr",
        "SELECT g.id, coalesce(g.document_name,'—'), coalesce(g.document_type::text,'—'), coalesce(e.nome,'—'), g.is_signed "
        "FROM ged_kit_documents g LEFT JOIN employees e ON e.id=g.employee_id ORDER BY g.created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[1], 600, "#0F1B3A"), t((r[2] or '—').replace('_', ' ')), t(r[3]), b("Assinado", "ok") if r[4] else b("Pendente", "warn")],
        docsfn=lambda r: [doc("Documento", f"/api/v1/ged/documents/{r[0]}/download", fmt="pdf", mode="blob")]))

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
