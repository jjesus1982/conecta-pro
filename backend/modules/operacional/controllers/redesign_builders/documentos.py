"""Documentos/GED (T1) — override do _build_documentos + telas kits e pastas (leitura real)."""
from datetime import date

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
    {"id": "kits-pdfs-mes", "label": "Gerar PDFs dos kits do mês", "icon": _ICO_D},
    {"id": "kit-real-mes", "label": "Gerar kits reais do mês", "icon": _ICO_D},
    {"id": "sophia-reindexar", "label": "Re-indexar acervo (SOPHIA v2)", "icon": _ICO_D},
    {"id": "ingestao-historica", "label": "Ingestão histórica do Drive", "icon": _ICO_D},
    {"id": "sophia-perguntar", "label": "Perguntar ao acervo (SOPHIA)", "icon": _ICO_D},
    {"id": "gedeon-perguntar-arquivo", "label": "Consultor GEDEON — com anexo", "icon": _ICO_D},
    {"id": "hermes-classificar", "label": "Classificar documento (Hermes)", "icon": _ICO_D},
    {"id": "ged-agendamento", "label": "Agendamento de envio do GED", "icon": _ICO_D},
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

    # ── Rotas de QUERY PARAM ligadas SEM tela de campo (2026-08-10) ──────────────────
    # O renderizador manda JSON no CORPO e estas rotas leem QUERY. Mas o endpoint do form
    # aceita query fixa (padrao ja usado no financeiro: "...sync-recebidos?dias=30"), e
    # endpoint sem parametro de corpo IGNORA o corpo. Entao query derivavel = botao que
    # funciona, sem uma linha de frontend e sem rota nova.
    #
    # E nao e so conveniencia: os defaults destas rotas estao CONGELADOS em marco/2026
    # (mes=3, ano=2026, reference_month="2026-03-01"). Um botao seco geraria documento da
    # competencia errada em silencio. Embutir o mes corrente CORRIGE isso.
    _hoje = date.today()
    _comp = f"{_hoje.year:04d}-{_hoje.month:02d}"
    out["kits-pdfs-mes"] = {
        "title": f"Gerar PDFs dos kits — {_hoje.month:02d}/{_hoje.year}",
        "sub": "Gera os PDFs de todos os kits da competência corrente. A competência é a de "
               "hoje, não a do sistema (o padrão da rota está preso em março/2026).",
        "cta": "Gerar PDFs", "type": "form",
        "submit": {"endpoint": f"/api/v1/ged/kits/generate-all-pdfs?reference_month={_comp}-01",
                   "okMsg": "Geração dos PDFs disparada",
                   "confirm": f"Gera os PDFs de TODOS os kits de {_hoje.month:02d}/{_hoje.year}. Confirma?"},
        "fields": [],
    }
    out["kit-real-mes"] = {
        "title": f"Gerar kits reais — {_hoje.month:02d}/{_hoje.year}",
        "sub": "Monta os kits reais (com documento de verdade) da competência corrente.",
        "cta": "Gerar kits", "type": "form",
        "submit": {"endpoint": f"/api/v1/ged/kit-real/gerar-todos?mes={_hoje.month}&ano={_hoje.year}",
                   "okMsg": "Geração dos kits reais disparada",
                   "confirm": f"Gera os kits reais de TODOS os clientes em {_hoje.month:02d}/{_hoje.year}. Confirma?"},
        "fields": [],
    }
    out["sophia-reindexar"] = {
        "title": "Re-indexar acervo (SOPHIA v2)",
        "sub": "Refaz os embeddings do acervo na versão 2. Mais pesado que indexar — use "
               "quando a busca estiver devolvendo resultado ruim.",
        "cta": "Re-indexar", "type": "form",
        "submit": {"endpoint": "/api/v1/gedeon/sophia/reindexar", "okMsg": "Re-indexação disparada",
                   "confirm": "Re-indexar refaz o acervo INTEIRO e consome bastante máquina. Confirma?"},
        "fields": [],
    }
    out["ingestao-historica"] = {
        "title": "Ingestão histórica do Drive",
        "sub": "Processa os ZIPs históricos da pasta do Drive e alimenta a SOPHIA. "
               "Idempotente por arquivo já processado.",
        "cta": "Processar", "type": "form",
        "submit": {"endpoint": "/api/v1/people-management/ged/documents/ingestao/historica",
                   "okMsg": "Ingestão histórica disparada",
                   "confirm": "Processa TODOS os ZIPs históricos da pasta. Demorado. Confirma?"},
        "fields": [],
    }

    # ── Rotas de QUERY PARAM com entrada do usuário (submit.query) ──────────────────
    # O renderizador ganhou `submit.query`: os campos viram query string em vez de ficarem
    # só no corpo. Opt-in — sem a flag nada muda nos ~200 forms existentes.
    out["sophia-perguntar"] = {
        "title": "Perguntar ao acervo (SOPHIA)",
        "sub": "Busca em linguagem natural sobre TODO o acervo indexado. Se vier vazio, "
               "provavelmente falta indexar — use 'Indexar acervo' antes.",
        "cta": "Perguntar", "type": "form",
        "submit": {"endpoint": "/api/v1/gedeon/sophia/perguntar", "query": True,
                   "okMsg": "Consulta respondida", "showResult": True},
        "fields": [
            {"key": "pergunta", "label": "Pergunta*", "type": "textarea", "span": "span 2",
             "ph": "Ex.: em que mês entregamos o último atestado do condomínio X?"},
            {"key": "cliente_id", "label": "Cliente (id)", "type": "text", "span": "span 1"},
            {"key": "funcionario_id", "label": "Colaborador (id)", "type": "text", "span": "span 1"},
            {"key": "modulo", "label": "Módulo", "type": "text", "span": "span 1",
             "ph": "Ex.: folha, sst, fiscal"},
            {"key": "competencia", "label": "Competência", "type": "text", "span": "span 1",
             "ph": "AAAA-MM"},
        ],
    }
    out["gedeon-perguntar-arquivo"] = {
        "title": "Consultor GEDEON — analisando um anexo",
        "sub": "Anexe PDF, DOCX, TXT ou CSV e pergunte sobre ele. O arquivo NÃO é guardado "
               "no acervo — é lido para responder.",
        "cta": "Analisar", "type": "form",
        # multipart + query: o ARQUIVO vai no corpo, os demais campos na URL. Foi para isto
        # que o submit.query passou a valer também no caminho multipart.
        "submit": {"endpoint": "/api/v1/gedeon/consultor/perguntar-arquivo",
                   "multipart": True, "query": True,
                   "okMsg": "Análise concluída", "showResult": True},
        "fields": [
            {"key": "arquivo", "label": "Arquivo*", "type": "file", "span": "span 2"},
            {"key": "area", "label": "Área*", "type": "text", "span": "span 1",
             "ph": "Ex.: folha, documentos"},
            {"key": "condominio", "label": "Condomínio", "type": "text", "span": "span 1"},
            {"key": "competencia", "label": "Competência", "type": "text", "span": "span 1",
             "ph": "AAAA-MM"},
            {"key": "pergunta", "label": "Pergunta*", "type": "textarea", "span": "span 2"},
        ],
    }
    out["hermes-classificar"] = {
        "title": "Classificar documento (Hermes)",
        "sub": "Diz em que categoria do GED um documento se encaixa, a partir do nome e de "
               "um trecho do conteúdo. Só classifica — não move nem grava nada.",
        "cta": "Classificar", "type": "form",
        "submit": {"endpoint": "/api/v1/gedeon/hermes/classificar", "query": True,
                   "okMsg": "Documento classificado", "showResult": True},
        "fields": [
            {"key": "nome_arquivo", "label": "Nome do arquivo*", "type": "text", "span": "span 2",
             "ph": "Ex.: DARF_08_2026.pdf"},
            {"key": "conteudo_preview", "label": "Trecho do conteúdo", "type": "textarea",
             "span": "span 2", "ph": "Cole as primeiras linhas — ajuda quando o nome é genérico"},
        ],
    }
    out["ged-agendamento"] = {
        "title": "Agendamento de envio do GED",
        "sub": "Quando e por onde o kit vai para o cliente. Campos em branco não são "
               "alterados — o backend só aceita as chaves conhecidas.",
        "cta": "Salvar agendamento", "type": "form",
        "submit": {"endpoint": "/api/v1/ged/config/schedule", "method": "PUT",
                   "okMsg": "Agendamento salvo", "showResult": True},
        "fields": [
            {"key": "ativo", "label": "Agendamento ativo?", "type": "select", "span": "span 1",
             "ph": "Selecione", "options": [{"value": "true", "label": "Sim"},
                                            {"value": "false", "label": "Não"}]},
            {"key": "envio_automatico", "label": "Envio automático?", "type": "select",
             "span": "span 1", "ph": "Selecione",
             "options": [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]},
            {"key": "dia_envio", "label": "Dia do mês", "type": "number", "span": "span 1",
             "ph": "Ex.: 5"},
            {"key": "hora_envio", "label": "Hora", "type": "text", "span": "span 1",
             "ph": "HH:MM"},
            {"key": "canal_envio", "label": "Canal", "type": "select", "span": "span 1",
             "ph": "Selecione", "options": [{"value": "email", "label": "E-mail"},
                                            {"value": "whatsapp", "label": "WhatsApp"},
                                            {"value": "portal", "label": "Portal do cliente"}]},
            {"key": "destinatarios", "label": "Destinatários", "type": "text", "span": "span 1",
             "ph": "e-mails separados por vírgula"},
            {"key": "incluir_kits", "label": "Incluir kits?", "type": "select", "span": "span 1",
             "ph": "Selecione", "options": [{"value": "true", "label": "Sim"},
                                            {"value": "false", "label": "Não"}]},
            {"key": "incluir_certidoes", "label": "Incluir certidões?", "type": "select",
             "span": "span 1", "ph": "Selecione",
             "options": [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]},
        ],
    }

    return out
