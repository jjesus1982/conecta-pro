"""Documentos/GED (T1) — override do _build_documentos + telas kits e pastas (leitura real)."""
from sqlalchemy import text

from modules.operacional.controllers.redesign_data_controller import (
    IC, S, _helpers, _scalar, b, doc, t,
)

SLUG = "documentos"
_ICO_D = "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6"

EXTRA_MENU: list[dict] = [
    {"id": "gedeon-perguntar", "label": "Consultor GEDEON", "icon": _ICO_D},
    {"id": "gedeon-intercorrencia", "label": "Registrar intercorrência", "icon": _ICO_D},
    {"id": "sophia-indexar", "label": "Indexar acervo (SOPHIA)", "icon": _ICO_D},
    {"id": "kits-montar", "label": "Montar kits do mês", "icon": _ICO_D},
]


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
                # PILOTO DA FUNDAÇÃO (docs nível-tela) — prova os 3 modos do DocButtons com ROTAS
                # VERIFICADAS (curl 200): blob (ZIP do kit mais recente, nativo GED) · json (export
                # conciliação {content,filename} via export_format=csv) · disabled (honesto, botão off).
                # Vira o EXEMPLO-ÂNCORA que os builders de cada território replicam.
                "docs": [
                    doc("Kit mais recente (ZIP)", "/api/v1/ged/kits/31c7bed9-ae21-4a48-9b36-ae64576d44a8/download-zip", fmt="zip", mode="blob"),
                    doc("Export conciliação (CSV)", "/api/v1/financial/bank-reconciliations/e9d72c71-eabd-4652-9de8-f1b9b2357b7e/export?export_format=csv", fmt="csv", mode="json", gate="financeiro"),
                    doc("SPED (aguardando)", disabled=True, motivo="Aguardando emissão real — botão liga quando o arquivo existir"),
                ]}

    await safe("visao", _visao())
    # Arquivos (ged_kit_documents) — SEM download por-doc: a rota /ged/documents/{id}/download
    # serve ged_documents (tabela VAZIA), não ged_kit_documents. Download real = ZIP do kit (abaixo).
    # Gap registrado na MATRIZ: falta rota servindo ged_kit_documents.file_path por-doc (759 têm arquivo).
    await safe("arquivos", tbl(
        "Arquivos", f"{n_ged} documentos", "Enviar documento",
        ["Documento", "Tipo", "Colaborador", "Assinado"], "2fr 1.4fr 1.6fr 0.9fr",
        "SELECT coalesce(g.document_name,'—'), coalesce(g.document_type::text,'—'), coalesce(e.nome,'—'), g.is_signed "
        "FROM ged_kit_documents g LEFT JOIN employees e ON e.id=g.employee_id ORDER BY g.created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')), t(r[2]), b("Assinado", "ok") if r[3] else b("Pendente", "warn")]))

    # Kits de documentos por competência — ged_document_kits (58). PILOTO row.docs: cada kit ganha
    # "Baixar ZIP" via /ged/kits/{id}/download-zip (rota nativa verificada, 200 application/zip).
    _kit_tone = {"completo": "ok", "aprovado": "ok", "enviado": "ok", "concluido": "ok", "em_montagem": "warn", "pendente": "warn", "montando": "warn"}
    await safe("kits", tbl(
        "Kits de documentos", f"{await _scalar(db, 'SELECT count(*) FROM ged_document_kits')} kits", "—",
        ["Competência", "Colaboradores", "Docs", "Assinados", "Completude", "Status"], "1fr 1fr 0.8fr 0.8fr 1fr 1.1fr",
        "SELECT id, to_char(reference_month,'MM/YYYY'), total_employees, total_documents, documents_signed, completion_percentage, coalesce(status::text,'—') "
        "FROM ged_document_kits ORDER BY reference_month DESC NULLS LAST, completion_percentage DESC LIMIT 200",
        lambda r: [t(r[1] or '—', 600, "#0F1B3A"), t(f"{int(r[2] or 0)}"), t(f"{int(r[3] or 0)}"), t(f"{int(r[4] or 0)}"),
                   t(f"{float(r[5] or 0):.0f}%", 600), b((r[6] or '—').replace('_', ' ').capitalize(), _kit_tone.get((r[6] or '').lower(), "info"))],
        docsfn=lambda r: [doc("Kit ZIP", f"/api/v1/ged/kits/{r[0]}/download-zip", fmt="zip", mode="blob")]))

    # Pastas (GED / Drive) — ged_folders (8)
    await safe("pastas", tbl(
        "Pastas", f"{await _scalar(db, 'SELECT count(*) FROM ged_folders')} pastas", "—",
        ["Pasta", "Código", "Tipo", "Nível", "Status"], "1.8fr 1.2fr 1.1fr 0.7fr 0.9fr",
        "SELECT coalesce(name,'—'), coalesce(code,'—'), coalesce(folder_type::text,'—'), level, coalesce(status::text,'—') "
        "FROM ged_folders ORDER BY coalesce(path,'') LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t((r[2] or '—').replace('_', ' ').capitalize()), t(f"{int(r[3] or 0)}"),
                   b((r[4] or '—').capitalize(), "ok" if (r[4] or '').lower() in ("ativa", "ativo", "active") else "mut")]))

    # ── FIOS SOLTOS DE GED/GEDEON (2026-08-10) ────────────────────────────────────────
    # DE FORA: sophia/perguntar, sophia/reindexar, hermes/classificar, kit-real/gerar-todos,
    # kits/generate-all-pdfs e config/schedule usam QUERY PARAM, e o form manda JSON no
    # CORPO — ligar assim entrega botao que sempre falha. Precisam de acao /redesign/action
    # que traduza corpo->query, ou de suporte a query no renderizador.
    # kits/{kit_id}/* e intercorrencias/{id} levam id no CAMINHO -> acao por linha.
    out["gedeon-perguntar"] = {
        "title": "Consultor GEDEON",
        "sub": "Pergunta ancorada nos kits reais do GED. É consulta — não altera documento.",
        "cta": "Perguntar", "type": "form",
        "submit": {"endpoint": "/api/v1/gedeon/consultor/perguntar",
                   "okMsg": "Consulta respondida", "showResult": True},
        "fields": [
            {"key": "area", "label": "Área*", "type": "text", "span": "span 1",
             "ph": "Ex.: folha, documentos, kit"},
            {"key": "condominio", "label": "Condomínio", "type": "text", "span": "span 1"},
            {"key": "competencia", "label": "Competência", "type": "text", "span": "span 1",
             "ph": "AAAA-MM"},
            {"key": "pergunta", "label": "Pergunta*", "type": "textarea", "span": "span 2",
             "ph": "Ex.: quais documentos faltam no kit deste mês?"},
        ],
    }
    out["gedeon-intercorrencia"] = {
        "title": "Registrar intercorrência do mês",
        "sub": "Contratação, demissão, falta — o que aconteceu no condomínio e afeta o kit "
               "(e, se marcar, a folha).",
        "cta": "Registrar", "type": "form",
        "submit": {"endpoint": "/api/v1/gedeon/consultor/intercorrencias",
                   "okMsg": "Intercorrência registrada"},
        "fields": [
            {"key": "condominio", "label": "Condomínio*", "type": "text", "span": "span 1"},
            {"key": "tipo", "label": "Tipo*", "type": "select", "span": "span 1", "ph": "Selecione",
             "options": [{"value": "contratacao", "label": "Contratação"},
                         {"value": "demissao", "label": "Demissão"},
                         {"value": "falta", "label": "Falta"},
                         {"value": "afastamento", "label": "Afastamento"},
                         {"value": "outro", "label": "Outro"}]},
            {"key": "funcionario", "label": "Colaborador", "type": "text", "span": "span 1"},
            {"key": "data_evento", "label": "Data do evento", "type": "date", "span": "span 1"},
            {"key": "competencia", "label": "Competência", "type": "text", "span": "span 1",
             "ph": "AAAA-MM"},
            {"key": "impacto_folha", "label": "Impacta a folha?", "type": "select", "span": "span 1",
             "ph": "Não", "options": [{"value": "false", "label": "Não"},
                                      {"value": "true", "label": "Sim"}]},
            {"key": "descricao", "label": "O que aconteceu*", "type": "textarea", "span": "span 2"},
        ],
    }
    out["sophia-indexar"] = {
        "title": "Indexar acervo (SOPHIA)",
        "sub": "Varre e indexa o acervo completo de documentos. Pesado — rode fora do horário "
               "de pico.",
        "cta": "Indexar", "type": "form",
        "submit": {"endpoint": "/api/v1/gedeon/sophia/indexar", "okMsg": "Indexação disparada",
                   "confirm": "A indexação varre TODO o acervo e consome bastante máquina. Confirma?"},
        "fields": [],
    }
    out["kits-montar"] = {
        "title": "Montar kits do mês",
        "sub": "Cria o kit dos clientes ativos que ainda não têm kit no mês corrente. "
               "Não sobrescreve kit existente.",
        "cta": "Montar", "type": "form",
        "submit": {"endpoint": "/api/v1/ged/kits/montar", "okMsg": "Kits montados"},
        "fields": [],
    }

    return out
