"""Redesign builder — Licitações.

Estende `_build_licitacoes` (base: visao, oportunidades, editais, propostas,
certidoes, contratos) e liga disputas·documentos·resultados lendo as tabelas
reais de licitação (bidding_*), hoje vazias = 0 linhas honestas. A tela `ia`
não tem tabela de origem no clássico → deixada como está (sem fabricar dado).
"""

from modules.operacional.controllers.redesign_data_controller import (
    _build_licitacoes,
    _helpers,
    b,
    brl,
    doc,
    t,
)

SLUG = "licitacoes"
_ICO_L = "M3 3v18h18M7 16l4-4 3 3 5-6"

EXTRA_MENU: list[dict] = [
    {"id": "sync-pncp", "label": "Sincronizar PNCP", "icon": _ICO_L},
    {"id": "sync-precos", "label": "Sincronizar preços", "icon": _ICO_L},
    {"id": "contratos-publicos", "label": "Contratos públicos", "icon": _ICO_L},
    {"id": "medicoes", "label": "Medicoes", "icon": _ICO_L},
]
_ND = "#0F1B3A"


def _d(v, fmt="%d/%m/%Y"):
    try:
        return v.strftime(fmt) if v else "—"
    except Exception:
        return "—"


def _bs(v):
    s = (v or "").lower()
    if s in ("ganho", "homologado", "vencido_ganho", "adjudicado", "ativo", "publicado", "won"):
        return b(v or "—", "ok")
    if s in ("aberto", "em_disputa", "disputa", "aguardando", "participando", "em_analise", "publicada"):
        return b(v or "—", "warn")
    if s in ("perdido", "cancelado", "deserto", "fracassado", "revogado", "impugnado"):
        return b(v or "—", "bad")
    return b(v or "—", "info")


# Status/modalidade — espelha statusLabel do clássico (licitacoes/page.tsx)
_BID_ST = {"draft": ("Rascunho", "mut"), "analyzing": ("Em Análise", "info"),
           "decided_go": ("Participar", "info"), "proposal_ready": ("Proposta Pronta", "warn"),
           "in_dispute": ("Em Disputa", "warn"), "won": ("GANHA", "ok"), "lost": ("Perdida", "bad")}
_MODAL = {"pregao_eletronico": "Pregão Eletrônico", "pregao_presencial": "Pregão Presencial",
          "concorrencia": "Concorrência", "tomada_precos": "Tomada de Preços",
          "convite": "Convite", "dispensa": "Dispensa", "inexigibilidade": "Inexigibilidade"}


def _bid_status(v):
    lbl, tone = _BID_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


def _modal(v):
    return _MODAL.get((v or "").lower(), (v or "—").replace("_", " ").capitalize())


_PROP_ST = {"draft": ("Rascunho", "mut"), "sent": ("Enviada", "warn"), "accepted": ("Aceita", "ok"),
            "rejected": ("Recusada", "bad"), "expired": ("Expirada", "bad")}
_CONTR_ST = {"draft": ("Rascunho", "mut"), "active": ("Ativo", "ok"), "suspended": ("Suspenso", "warn"),
             "cancelled": ("Cancelado", "bad"), "expired": ("Expirado", "bad"), "finished": ("Encerrado", "mut")}


def _prop_status(v):
    lbl, tone = _PROP_ST.get((v or "").lower(), ((v or "—").capitalize(), "info"))
    return b(lbl, tone)


def _contr_status(v):
    lbl, tone = _CONTR_ST.get((v or "").lower(), ((v or "—").capitalize(), "info"))
    return b(lbl, tone)


async def build(db) -> dict:
    out = await _build_licitacoes(db)
    _o2, _s2, tbl = _helpers(db)

    async def safe(key, coro):
        try:
            out[key] = await coro
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass

    # 1) Disputas — bidding_tenders em que participamos
    await safe("disputas", tbl(
        "Disputas", "Licitações em disputa", "—",
        ["Número", "Órgão", "Modalidade", "Abertura", "Status"],
        "1fr 1.8fr 1.1fr 1fr 0.9fr",
        "SELECT coalesce(numero,'—'), coalesce(orgao_nome,'—'), coalesce(modalidade::text,'—'), "
        "data_abertura, coalesce(status::text,'—') FROM bidding_tenders WHERE coalesce(participando,false) "
        "ORDER BY data_abertura DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t(_modal(r[2])), t(_d(r[3])), _bid_status(r[4])]))

    # 2) Documentos — bidding_tender_documents. arquivo_url NULL em 100% (8/8) e o
    #    document_controller só expõe metadados (sem FileResponse) → sem arquivo servível.
    await safe("documentos", tbl(
        "Documentos", "Documentos de licitação", "—",
        ["Documento", "Tipo", "Obrigatório", "Criado"],
        "2fr 1.2fr 1fr 1fr",
        "SELECT coalesce(nome,'—'), coalesce(tipo::text,'—'), coalesce(obrigatorio,false), created_at "
        "FROM bidding_tender_documents ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t((r[1] or "—").replace("_", " ")),
                   (b("Sim", "warn") if r[2] else b("Não", "mut")), t(_d(r[3]))]))
    if "documentos" in out:
        out["documentos"]["docs"] = [doc(
            "Arquivo do documento (indisponível)", disabled=True,
            motivo="bidding_tender_documents.arquivo_url vazio e sem rota de download — falta upload/servir o arquivo")]

    # 3) Resultados — bidding_tenders homologadas/com resultado
    await safe("resultados", tbl(
        "Resultados", "Resultados de licitações", "—",
        ["Número", "Órgão", "Objeto", "Valor homologado", "Status"],
        "1fr 1.5fr 2fr 1.2fr 0.9fr",
        "SELECT coalesce(numero,'—'), coalesce(orgao_nome,'—'), coalesce(objeto_resumido, objeto, '—'), "
        "coalesce(valor_homologado,0), coalesce(status::text,'—') FROM bidding_tenders "
        "WHERE (status IN ('won','lost') OR data_resultado IS NOT NULL OR coalesce(valor_homologado,0)>0) "
        "ORDER BY coalesce(data_resultado, data_abertura) DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t((r[2] or "—")[:80]), t(brl(r[3]), 600), _bid_status(r[4])]))

    # Editais — SOBRESCREVE a base (Modalidade+Status crus) → PT
    await safe("editais", tbl(
        "Editais", "Editais monitorados", "—",
        ["Nº / Objeto", "Órgão", "Modalidade", "Valor estimado", "Status", "Participa"],
        "2fr 1.6fr 1.1fr 1fr 0.9fr 0.8fr",
        "SELECT coalesce(objeto_resumido, objeto, numero, '—'), coalesce(orgao_nome,'—'), "
        "coalesce(modalidade,'—'), valor_estimado, coalesce(status,'—'), coalesce(participando,false) "
        "FROM bidding_tenders ORDER BY data_abertura DESC NULLS LAST LIMIT 200",
        lambda r: [t((r[0] or "—")[:70], 600, _ND), t(r[1]), t(_modal(r[2])), t(brl(r[3] or 0)),
                   _bid_status(r[4]), (b("Sim", "ok") if r[5] else b("Não", "mut"))]))

    # Propostas — SOBRESCREVE a base (Status cru) → PT. Documento POR-LINHA: PDF real da
    # proposta via /api/v1/crm/proposals/{id}/pdf (curl 200 application/pdf ~371KB, mesma
    # tabela `proposals`). id na 1ª coluna do SELECT.
    await safe("propostas", tbl(
        "Propostas", "Propostas comerciais", "—",
        ["Número", "Cliente", "Título", "Valor", "Status"], "1fr 1.6fr 1.6fr 1fr 0.9fr",
        "SELECT id, coalesce(number,'—'), coalesce(client_name,'—'), coalesce(title,'—'), "
        "coalesce(total,subtotal,0), status::text FROM proposals ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[1], 600, _ND), t(r[2]), t(r[3]), t(brl(r[4]), 600), _prop_status(r[5])],
        docsfn=lambda r: [doc("Proposta (PDF)", f"/api/v1/crm/proposals/{r[0]}/pdf", fmt="pdf")]))

    # Contratos — SOBRESCREVE a base do CRM (este builder é mapeado no slug `crm`, e vence).
    # 23/08: o botão apontava para /pdf, que é o MOLDE de 3 páginas, e não para /pdf-modelo,
    # que renderiza o instrumento real do modelo cadastrado. Quem clicasse recebia o
    # documento errado — resumo em vez de contrato. Agora o botão do instrumento só aparece
    # em quem TEM modelo; sem modelo, o molde continua sendo oferecido, mas dizendo o que é.
    # A coluna Assinatura lê sig_signature_requests: é o banco dizendo quem firmou, nunca
    # uma inferência a partir do status do contrato.
    await safe("contratos", tbl(
        "Contratos", "Contratos de prestação — baixe o instrumento e acompanhe a assinatura", "—",
        ["Contrato", "Cliente", "Serviço", "Mensal", "Status", "Assinatura"],
        "1.1fr 1.5fr 1fr 0.9fr 0.8fr 1.1fr",
        "SELECT ct.id, coalesce(ct.contract_number,'—'), coalesce(cl.name, ct.name, '—'), "
        "coalesce(ct.monthly_value,0), ct.status::text, "
        "coalesce(ct.tipo_servico::text,'—'), ct.template_id::text, "
        "(SELECT count(*) FROM sig_signature_requests s WHERE s.reference_code = ct.contract_number), "
        "(SELECT count(*) FROM sig_signature_requests s WHERE s.reference_code = ct.contract_number AND s.signed_at IS NOT NULL) "
        "FROM contracts ct LEFT JOIN clients cl ON cl.id=ct.client_id ORDER BY ct.start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[1], 600, _ND), t((r[2] or '—')[:32]), t((r[5] or '—').replace('_', ' ')),
                   t(brl(r[3]), 600), _contr_status(r[4]),
                   (b("Não aberta", "mut") if not r[7]
                    else b(f"{r[8]}/{r[7]} assinada(s)", "ok" if r[8] and r[8] == r[7] else "warn"))],
        docsfn=lambda r: ([doc("Contrato completo (PDF)",
                               f"/api/v1/crm/contracts/{r[1]}/pdf-modelo", fmt="pdf")] if r[6]
                          else [doc("Resumo do contrato (sem modelo vinculado)",
                                    f"/api/v1/crm/contracts/{r[0]}/pdf", fmt="pdf")])))

    # Certidões — bidding_certificates.arquivo_url NULL em 100% (8/8) e o certificate_controller
    # não serve arquivo → sinal honesto de indisponibilidade (sem botão que abre lixo).
    if "certidoes" in out and isinstance(out.get("certidoes"), dict):
        out["certidoes"]["docs"] = [doc(
            "Certidão (arquivo indisponível)", disabled=True,
            motivo="bidding_certificates.arquivo_url vazio e sem rota de download — CND só como metadado")]

    # ── FIOS SOLTOS DE LICITACOES (2026-08-10) — os 2 gatilhos manuais de sync ─────────
    # As 4 rotas /bidding/erp/* (converter, crm, medicao, fatura) ficaram DE FORA: levam
    # {contract_id}/{medicao_id} no CAMINHO, e o endpoint do form e fixo. Lugar certo delas
    # e acao por LINHA na tabela de contratos publicos — nao tela pedindo UUID colado.
    out["sync-pncp"] = {
        "title": "Sincronizar com o PNCP",
        "sub": "Puxa editais e contratos do Portal Nacional de Contratações Públicas. "
               "Só LÊ do portal — não envia nada, não assina nada.",
        "cta": "Sincronizar agora", "type": "form",
        "submit": {"endpoint": "/api/v1/bidding/sync/pncp/trigger",
                   "okMsg": "Sincronização com o PNCP disparada"},
        "fields": [],
    }
    out["sync-precos"] = {
        "title": "Sincronizar preços referenciais",
        "sub": "Atualiza a tabela de preços de referência usada para montar proposta.",
        "cta": "Sincronizar agora", "type": "form",
        "submit": {"endpoint": "/api/v1/bidding/sync/precos/trigger",
                   "okMsg": "Sincronização de preços disparada"},
        "fields": [],
    }

    # ── Oportunidades → funil do CRM (07/09/2026) ─────────────────────────────────
    # Sobrescreve a aba base: mesma consulta + coluna "CRM" (lead já criado?) + ação que chama
    # /bidding/erp/lead/{id} (idempotente). Lead é intenção; cliente é contrato assinado.
    await safe("oportunidades", tbl(
        "Oportunidades", "Licitações captadas · cada uma pode virar lead no funil do CRM", "Atualizar",
        ["Objeto", "Órgão", "UF", "Valor estimado", "Encerra", "Status", "CRM"], "2fr 1.5fr 0.5fr 1fr 0.9fr 0.8fr 0.7fr",
        "SELECT o.id, o.objeto, coalesce(o.orgao_nome,'—'), coalesce(o.uf,'—'), o.valor_estimado, o.data_encerramento, "
        "coalesce(o.status,'—'), (SELECT count(*) FROM leads l WHERE l.custom_fields->>'bidding_opportunity_id' = o.id::text AND l.is_active) "
        "FROM bidding_opportunities o ORDER BY o.data_encerramento DESC NULLS LAST LIMIT 200",
        lambda r: [t((r[1] or '—')[:80], 600, _ND), t((r[2] or '—')[:40]), t(r[3]),
                   t(brl(r[4]) if r[4] is not None else '—'), t(_d(r[5])), b((r[6] or '—').capitalize(), "info"),
                   b("no funil" if (r[7] or 0) else "—", "ok" if (r[7] or 0) else "mut")],
        actionsfn=lambda r: [
            {"title": f"Levar ao funil do CRM: {(r[2] or '')[:40]}",
             "sub": "Cria um lead (fonte: licitação) para este órgão/objeto. Já existe? Não duplica.",
             "endpoint": f"/api/v1/bidding/erp/lead/{r[0]}",
             "method": "POST", "btnLabel": "Virar lead", "submitLabel": "Criar lead no CRM",
             "btnStyle": "outline", "okMsg": "Lead criado no CRM. Recarregue.", "fields": []},
        ]))

    # ── Contratos publicos e medicoes (2026-08-10) ─────────────────────────────────
    # As 4 rotas /bidding/erp/* levam {contract_id} ou {medicao_id} no CAMINHO. Aqui elas
    # cabem: o id vem da LINHA. Como tela solta, exigiriam colar UUID a mao.
    await safe("contratos-publicos", tbl(
        "Contratos públicos", "Contratos ganhos em licitacao", "—",
        ["Contrato", "Orgao", "Objeto", "Valor", "Executado"],
        "1fr 1.6fr 1.8fr 1fr 1fr",
        "SELECT id, coalesce(numero_contrato,'—'), coalesce(orgao_nome,'—'), "
        "coalesce(objeto_resumido, objeto, '—'), coalesce(valor_contrato,0), "
        "coalesce(valor_executado,0) "
        "FROM bidding_public_contracts ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[1], 600, _ND), t((r[2] or '—')[:40]), t((r[3] or '—')[:60]),
                   t(brl(r[4]), 600), t(brl(r[5]))],
        actionsfn=lambda r: [
            {"title": f"Converter {r[1]} em operacao",
             "sub": "Cria as entidades operacionais do contrato público no ERP.",
             "endpoint": f"/api/v1/bidding/erp/converter/{r[0]}",
             "method": "POST", "btnLabel": "Converter", "submitLabel": "Converter em operacao",
             "btnStyle": "primary", "okMsg": "Contrato convertido. Recarregue.", "fields": []},
            {"title": f"Vincular {r[1]} ao CRM",
             "sub": "Liga o contrato público ao modulo comercial.",
             "endpoint": f"/api/v1/bidding/erp/crm/{r[0]}",
             "method": "POST", "btnLabel": "Vincular CRM", "submitLabel": "Vincular ao CRM",
             "btnStyle": "outline", "okMsg": "Contrato vinculado ao CRM. Recarregue.", "fields": []},
            {"title": f"Gerar medição de {r[1]}",
             "sub": "Medição do período — e ela que vira fatura depois de aprovada.",
             "endpoint": f"/api/v1/bidding/erp/medicao/{r[0]}",
             "method": "POST", "btnLabel": "Medicao", "submitLabel": "Gerar medição",
             "btnStyle": "outline", "okMsg": "Medição gerada. Recarregue.",
             "fields": [
                 {"key": "competencia", "label": "Competencia*", "type": "text", "value": "",
                  "span": "span 2"},
                 {"key": "periodo_inicio", "label": "Inicio do período*", "type": "date",
                  "value": "", "span": "span 1"},
                 {"key": "periodo_fim", "label": "Fim do período*", "type": "date",
                  "value": "", "span": "span 1"},
             ]},
        ]))
    await safe("medicoes", tbl(
        "Medicoes", "Medições dos contratos públicos", "—",
        ["Medicao", "Competencia", "Periodo", "Bruto", "Liquido"],
        "1fr 1fr 1.4fr 1fr 1fr",
        "SELECT id, coalesce(numero_medicao::text,'—'), coalesce(competencia,'—'), "
        "periodo_inicio, periodo_fim, coalesce(valor_bruto,0), coalesce(valor_liquido,0) "
        "FROM bidding_measurements ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[1], 600, _ND), t(r[2]),
                   t(f"{r[3]} a {r[4]}" if r[3] and r[4] else "—"),
                   t(brl(r[5]), 600), t(brl(r[6]), 600)],
        actionsfn=lambda r: [
            {"title": f"Gerar fatura da medição {r[1]}",
             "sub": "Cria a conta a RECEBER a partir da medição aprovada. Não cobra o órgão "
                    "sozinho — so lança o recebivel.",
             "endpoint": f"/api/v1/bidding/erp/fatura/{r[0]}",
             "method": "POST", "btnLabel": "Faturar", "submitLabel": "Gerar fatura",
             "btnStyle": "primary", "okMsg": "Fatura gerada. Recarregue.", "fields": []},
        ]))

    return out
