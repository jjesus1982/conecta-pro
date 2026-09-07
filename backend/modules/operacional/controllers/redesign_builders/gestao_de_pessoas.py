"""
redesign_builders/gestao_de_pessoas.py — T4.
Sobrescreve _build_gp: reusa a base e ADICIONA GED (kits/envios/assinaturas),
banco de horas, RH (staff/treinamentos/cargos), saúde ocupacional e consultor IA.
Só leitura. Nunca fabricar — vazio real = "aguardando dado".
"""
from modules.operacional.controllers.redesign_data_controller import (  # noqa: F401
    _build_gp as _base,
    _fmtdate,
    _helpers,
    _scalar,
    b,
    brl,
    doc,
    initials,
    t,
)

SLUG = "gestao-de-pessoas"
EXTRA_MENU: list[dict] = [
    {"id": "consultor-gestao", "label": "Consultor de gestão",
     "icon": "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20M12 8v4M12 16h.01"},
    {"id": "consultor-gestao-arquivo", "label": "Consultor de gestão — com anexo", "icon": "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20M12 8v4M12 16h.01"},
    {"id": "carreira-planos", "label": "Planos de carreira", "icon": "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"},
    {"id": "treinamento-inscricoes", "label": "Inscrições em treinamento", "icon": "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"},
]

# GED · Envios — ação em PT + ator legível (nome real, ou rótulo do tipo quando é UUID cru no log)
_GED_ACTION = {"viewed": "Visualizado", "downloaded": "Baixado", "sent": "Enviado",
               "uploaded": "Enviado", "signed": "Assinado", "created": "Criado"}
_GED_ACTOR = {"client": "Cliente", "internal": "Interno", "employee": "Colaborador"}


def _is_uuid(s):
    s = (s or "").strip()
    return len(s) == 36 and s.count("-") == 4 and " " not in s


def _ged_actor(name, tipo):
    if not name or _is_uuid(name):
        return _GED_ACTOR.get((tipo or "").lower(), "—")
    return name


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)
    out.update(await _base(db))

    # ---- GED · Kits (ged_document_kits) ----
    await safe("ged-kits", tbl(
        "GED · Kits", f"{await _scalar(db, 'SELECT count(*) FROM ged_document_kits')} kits documentais",
        "—", ["Condomínio", "Competência", "Status", "Colaboradores", "Documentos", "Conclusão"],
        "1.8fr 1fr 1fr 1fr 1fr 1fr",
        "SELECT coalesce(gc.name, k.client_id::text), k.reference_month, coalesce(k.status,'—'), "
        "k.total_employees, k.total_documents, k.completion_percentage, CAST(k.id AS TEXT) "
        "FROM ged_document_kits k LEFT JOIN ged_clients gc ON gc.id = k.client_id "
        "ORDER BY k.reference_month DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, "#0F1B3A"), t(_fmtdate(r[1], '%m/%Y'), 600, "#0F1B3A"),
                   b({"em_montagem": "Em montagem", "enviado": "Enviado", "completo": "Completo"}.get(
                       (r[2] or "").lower(), (r[2] or "—").replace("_", " ").capitalize()),
                     "ok" if (r[2] or "").lower() in ("aprovado", "approved", "enviado", "sent", "completo") else "warn"),
                   t(str(r[3]) if r[3] is not None else '—'), t(str(r[4]) if r[4] is not None else '—'),
                   t(f"{float(r[5]):.0f}%" if r[5] is not None else '—', 600)],
        docsfn=lambda r: [doc("Kit (ZIP)", f"/api/v1/ged/kits/{r[6]}/download-zip", fmt="zip", mode="blob")],
        # Ações por LINHA: as 3 rotas de kit levam {kit_id} no CAMINHO, então o lugar delas é
        # aqui — o id vem da linha. Como tela solta, exigiriam colar UUID à mão.
        actionsfn=lambda r: [
            {"title": f"Gerar os PDFs do kit de {r[0]}",
             "sub": "Refaz os PDFs de todos os documentos DESTE kit.",
             "endpoint": f"/api/v1/ged/kits/{r[6]}/generate-pdfs",
             "method": "POST", "btnLabel": "Gerar PDFs", "submitLabel": "Gerar agora",
             "btnStyle": "outline", "okMsg": "Geração dos PDFs disparada. Recarregue a tela.",
             "fields": []},
            {"title": f"Anexar as NFS-e ao kit de {r[0]}",
             "sub": "Busca as NFS-e reais do cliente na competência e junta ao kit, gerando "
                    "os PDFs. Não emite nota — só anexa o que já existe.",
             "endpoint": f"/api/v1/ged/kits/{r[6]}/add-nfse",
             "method": "POST", "btnLabel": "Anexar NFS-e", "submitLabel": "Anexar agora",
             "btnStyle": "outline", "okMsg": "NFS-e anexadas ao kit. Recarregue a tela.",
             "fields": []},
            {"title": f"Enviar o kit de {r[0]} por e-mail",
             "sub": "Manda o kit ao cliente com o link do Drive. Efeito EXTERNO: o cliente "
                    "recebe agora.",
             "endpoint": f"/api/v1/people-management/ged/kits/{r[6]}/send-email",
             "method": "POST", "btnLabel": "Enviar", "submitLabel": "Enviar ao cliente agora",
             "btnStyle": "primary", "okMsg": "Kit enviado ao cliente. Recarregue a tela.",
             "fields": []},
        ]))

    # ---- GED · Envios (ged_kit_access_logs — eventos de entrega/acesso) ----
    await safe("ged-envios", tbl(
        "GED · Envios", f"{await _scalar(db, 'SELECT count(*) FROM ged_kit_access_logs')} eventos de acesso/entrega",
        "—", ["Ação", "Ator", "Tipo", "Data"], "1.2fr 1.6fr 1fr 1.2fr",
        "SELECT action, actor_name, actor_type, created_at "
        "FROM ged_kit_access_logs ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [b(_GED_ACTION.get((r[0] or '').lower(), (r[0] or '—').replace('_', ' ').capitalize()), "info"),
                   t(_ged_actor(r[1], r[2]), 600, "#0F1B3A"),
                   t(_GED_ACTOR.get((r[2] or '').lower(), (r[2] or '—').capitalize())), t(_fmtdate(r[3]))]))

    # ---- GED · Assinaturas (ged_kit_documents — status de assinatura) ----
    await safe("ged-assinaturas", tbl(
        "GED · Assinaturas", f"{await _scalar(db, 'SELECT count(*) FROM ged_kit_documents WHERE is_signed=true')} documentos assinados de {await _scalar(db, 'SELECT count(*) FROM ged_kit_documents')}",
        "—", ["Documento", "Tipo", "Assinado", "Data assinatura"], "2fr 1.2fr 0.9fr 1.2fr",
        "SELECT coalesce(document_name,'—'), coalesce(document_type,'—'), is_signed, signed_at "
        "FROM ged_kit_documents ORDER BY is_signed DESC, signed_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ').capitalize()),
                   b("Assinado", "ok") if r[2] else b("Pendente", "warn"), t(_fmtdate(r[3]))]))

    # ---- Ponto · Banco de horas (time_bank — honesto se vazio) ----
    await safe("ponto-banco", tbl(
        "Ponto · Banco de horas", f"{await _scalar(db, 'SELECT count(*) FROM time_bank')} lançamentos (aguardando dado se vazio)",
        "—", ["Tipo", "Horas", "Saldo", "Referência", "Status"], "1fr 0.8fr 0.8fr 1fr 0.9fr",
        "SELECT coalesce(entry_type,'—'), hours, balance_after, reference_date, coalesce(status,'—') "
        "FROM time_bank ORDER BY reference_date DESC NULLS LAST LIMIT 200",
        lambda r: [t((r[0] or '—').capitalize(), 600, "#0F1B3A"), t(f"{float(r[1]):+.1f}h" if r[1] is not None else '—'),
                   t(f"{float(r[2]):.1f}h" if r[2] is not None else '—', 600), t(_fmtdate(r[3])), b((r[4] or '—').capitalize(), "info")]))

    # ---- RH · Quadro de colaboradores (employees) ----
    await safe("rh", tbl(
        # Mesma régua do DP: ativo = status 'ativo' (CLT). `is_active=true` somava PJ, suspenso e
        # candidato e dizia 65 onde o DP diz 53 — duas verdades para o mesmo número (07/09/2026).
        "RH", (f"{await _scalar(db, 'SELECT count(*) FROM employees WHERE status=%s' % chr(39) + 'ativo' + chr(39))} colaboradores CLT ativos · "
               f"{await _scalar(db, 'SELECT count(*) FROM employees WHERE status=%s' % chr(39) + 'pj_ativo' + chr(39))} PJ ativos"),
        "—", ["Colaborador", "Cargo", "Departamento", "Status"], "2fr 1.5fr 1.3fr 0.9fr",
        "SELECT nome, coalesce(cargo,'—'), coalesce(departamento,'—'), coalesce(status,'—') "
        "FROM employees WHERE status IN ('ativo','pj_ativo') ORDER BY status, nome LIMIT 300",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]), t(r[2]),
                   b((r[3] or '—').capitalize(), "ok" if (r[3] or '').lower() in ("ativo", "active") else "mut")]))

    # ---- RH · Treinamentos (sst_treinamentos — honesto se vazio) ----
    await safe("rh-treinamentos", tbl(
        "RH · Treinamentos", f"{await _scalar(db, 'SELECT count(*) FROM sst_treinamentos')} treinamentos (aguardando dado se vazio)",
        "—", ["Norma", "Descrição", "Realização", "Vencimento"], "1fr 2fr 1fr 1fr",
        "SELECT coalesce(norma,'—'), coalesce(descricao,'—'), data_realizacao, vencimento "
        "FROM sst_treinamentos ORDER BY data_realizacao DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(_fmtdate(r[2])), t(_fmtdate(r[3]))]))

    # ---- RH · Cargos (cct_cargos — tabela CCT de cargos) ----
    await safe("rh-cargos", tbl(
        "RH · Cargos", f"{await _scalar(db, 'SELECT count(*) FROM cct_cargos WHERE is_active=true')} cargos (base CCT)",
        "—", ["Cargo", "Piso", "Jornada", "Noturno", "Periculosidade"], "2fr 1fr 1fr 1fr 1fr",
        "SELECT cargo_nome, piso_salarial, jornada_semanal_horas, adicional_noturno_percentual, adicional_periculosidade_percentual "
        "FROM cct_cargos WHERE is_active=true ORDER BY piso_salarial DESC NULLS LAST LIMIT 100",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(brl(r[1]), 600), t(f"{r[2]}h" if r[2] is not None else '—'),
                   t(f"{float(r[3]):.0f}%" if r[3] else '—'), t(f"{float(r[4]):.0f}%" if r[4] else '—')]))

    # ---- Saúde ocupacional (gp_asos — ASOs) ----
    await safe("saude", tbl(
        "Saúde ocupacional", f"{await _scalar(db, 'SELECT count(*) FROM gp_asos')} ASOs",
        "—", ["Tipo", "Status", "Realização", "Validade", "Clínica"], "1fr 1fr 1fr 1fr 1.4fr",
        "SELECT coalesce(tipo,'—'), coalesce(status,'—'), data_realizacao, data_validade, coalesce(clinica,'—') "
        "FROM gp_asos ORDER BY data_realizacao DESC NULLS LAST LIMIT 300",
        lambda r: [b((r[0] or '—').capitalize(), "info"),
                   b((r[1] or '—').capitalize(), "ok" if (r[1] or '').lower() in ("concluido", "concluído", "realizado", "apto") else "warn"),
                   t(_fmtdate(r[2])), t(_fmtdate(r[3])), t(r[4], 600, "#0F1B3A")]))

    # ---- Consultor de Pessoas IA (rh_consultas — histórico READ) ----
    await safe("consultor", tbl(
        "Consultor de Pessoas IA", f"{await _scalar(db, 'SELECT count(*) FROM rh_consultas')} consultas (histórico)",
        "—", ["Área", "Competência", "Pergunta", "Autor", "Data"], "1fr 1fr 2fr 1fr 1fr",
        "SELECT coalesce(area,'—'), coalesce(competencia,'—'), left(coalesce(pergunta,'—'),80), coalesce(created_by,'—'), created_at "
        "FROM rh_consultas ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [b((r[0] or '—').upper() if len(r[0] or '') <= 3 else (r[0] or '—').replace('_', ' ').capitalize(), "info"),
                   t(r[1]), t(r[2], 600, "#0F1B3A"),
                   t("Sistema" if _is_uuid(r[3]) else (r[3] or "—")), t(_fmtdate(r[4]))]))

    # Ponto — SOBRESCREVE a base (que aplica AT TIME ZONE 'America/Manaus' sobre timestamp já-local
    # = +4h errado, e status cru 'pending'). punch_timestamp é Manaus-local naive → formato RAW.
    _PUNCH_ST = {"pending": ("Pendente", "warn"), "approved": ("Aprovado", "ok"),
                 "processed": ("Processado", "ok"), "rejected": ("Rejeitado", "bad"),
                 "pending_contingencia": ("Contingência", "warn")}
    _PUNCH_TP = {"entrada": "Entrada", "saida": "Saída", "saída": "Saída",
                 "intervalo": "Intervalo", "retorno": "Retorno"}
    await safe("ponto", tbl(
        "Ponto eletrônico", "Últimas batidas", "—",
        ["Colaborador", "Data/hora", "Tipo", "Status"], "1.8fr 1.1fr 1fr 1fr",
        "SELECT coalesce(e.nome,'—'), to_char(p.punch_timestamp,'DD/MM HH24:MI'), "
        "coalesce(p.punch_type::text,'—'), coalesce(p.status::text,'—') "
        "FROM gp_clock_punches p LEFT JOIN employees e ON e.id=p.employee_id "
        "ORDER BY p.punch_timestamp DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, "#0F1B3A", initials(r[0] or "")), t(r[1]),
                   t(_PUNCH_TP.get((r[2] or "").lower(), (r[2] or "—").capitalize())),
                   b(*_PUNCH_ST.get((r[3] or "").lower(), ((r[3] or "—").capitalize(), "info")))]))

    # Ponto-espelho (Portaria 671) — SOBRESCREVE p/ formatar Atraso (min) como inteiro (base exibia '0.0')
    await safe("ponto-espelho", tbl(
        "Fechamento de ponto (Portaria 671)", f"{await _scalar(db, 'SELECT count(*) FROM gp_monthly_closings')} fechamentos", "Fechar mês",
        ["Colaborador", "Competência", "Dias", "Horas trab.", "HE 50%", "Faltas", "Atraso (min)", "Status"],
        "1.8fr 1fr 0.6fr 1fr 0.8fr 0.7fr 0.9fr 0.9fr",
        "SELECT coalesce(e.nome, m.employee_id, '—'), m.month, m.year, coalesce(m.total_dias_trabalhados,0), "
        "coalesce(m.total_horas_trabalhadas,0), coalesce(m.total_horas_extras_50,0), coalesce(m.total_faltas,0), "
        "coalesce(m.total_atrasos_minutos,0), coalesce(m.fechado,false) "
        "FROM gp_monthly_closings m LEFT JOIN employees e ON e.id::text=m.employee_id::text "
        "ORDER BY m.year DESC NULLS LAST, m.month DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(f"{r[1]:02d}/{r[2]}" if r[1] else "—"), t(str(int(r[3] or 0))),
                   t(f"{float(r[4]):.0f}h" if r[4] is not None else "—"), t(f"{float(r[5]):.0f}h" if r[5] else "—"),
                   b(str(int(r[6] or 0)), "bad" if (r[6] or 0) > 0 else "ok"), t(str(int(r[7] or 0))),
                   b("Fechado", "ok") if r[8] else b("Aberto", "warn")]))

    # Fio solto (2026-08-10): o consultor de gestão existia no backend sem tela.
    out["consultor-gestao"] = {
        "title": "Consultor de gestão de pessoas",
        "sub": "Pergunta ancorada no quadro real de pessoas. É consulta — não altera nada.",
        "cta": "Perguntar", "type": "form",
        "submit": {"endpoint": "/api/v1/gestao/consultor/perguntar",
                   "okMsg": "Consulta respondida", "showResult": True},
        "fields": [
            {"key": "area", "label": "Área*", "type": "text", "span": "span 2",
             "ph": "Ex.: banco de horas, treinamentos, cargos"},
            {"key": "pergunta", "label": "Pergunta*", "type": "textarea", "span": "span 2"},
        ],
    }

    out["consultor-gestao-arquivo"] = {
        "title": "Consultor de gestão — com anexo",
        "sub": "Anexe o documento e pergunte sobre ele. O arquivo é lido para responder, não fica guardado.",
        "cta": "Analisar", "type": "form",
        "submit": {"endpoint": "/api/v1/gestao/consultor/perguntar-arquivo",
                   "multipart": True, "query": True,
                   "okMsg": "Análise concluída", "showResult": True},
        "fields": [
            {"key": "arquivo", "label": "Arquivo*", "type": "file", "span": "span 2"},
            {"key": "area", "label": "Área", "type": "text", "span": "span 2", "ph": "Ex.: banco de horas, treinamentos"},
            {"key": "pergunta", "label": "Pergunta*", "type": "textarea", "span": "span 2"},
        ],
    }

    # Carreira e treinamento (2026-08-10): concluir milestone, atualizar milestones e emitir
    # certificado levam {id} no CAMINHO -> acao por LINHA das listagens abaixo.
    await safe("carreira-planos", tbl(
        "Planos de carreira", "Trilha de cada colaborador", "—",
        ["Colaborador", "Cargo atual", "Cargo alvo", "Prazo", "Status"],
        "1.6fr 1.3fr 1.3fr 0.8fr 0.9fr",
        "SELECT p.id, coalesce(e.nome,'—'), coalesce(p.current_position,'—'), "
        "coalesce(p.target_position,'—'), p.estimated_timeline_months, coalesce(p.status::text,'—') "
        "FROM career_plans p LEFT JOIN employees e ON e.id = p.employee_id "
        "ORDER BY p.created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[1], 600, "#0F1B3A", initials(r[1] or "")), t(r[2]), t(r[3]),
                   t(f"{int(r[4])} meses" if r[4] else "—"),
                   b((r[5] or '—').capitalize(), "ok" if (r[5] or '').lower() in ("active", "ativo", "completed") else "warn")],
        actionsfn=lambda r: [
            {"title": f"Concluir uma etapa do plano de {r[1]}",
             "sub": "Informe o número da etapa (a 1ª é 0). Marca como concluída na trilha.",
             "endpoint": f"/api/v1/people-management/human-resources/career/plans/{r[0]}/milestones/0/complete",
             "method": "POST", "btnLabel": "Concluir 1ª etapa", "submitLabel": "Concluir etapa",
             "btnStyle": "primary", "okMsg": "Etapa concluída. Recarregue a tela.", "fields": []},
        ]))
    await safe("treinamento-inscricoes", tbl(
        "Inscrições em treinamento", "Quem está inscrito e quem já pode receber certificado", "—",
        ["Colaborador", "Status", "Inscrição", "Presença", "Nota"],
        "1.8fr 1fr 1fr 1fr 0.7fr",
        "SELECT i.id, coalesce(e.nome,'—'), coalesce(i.status::text,'—'), i.enrolled_at, "
        "i.attended_at, i.score "
        "FROM training_enrollments i LEFT JOIN employees e ON e.id = i.employee_id "
        "ORDER BY i.enrolled_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[1], 600, "#0F1B3A", initials(r[1] or "")),
                   b((r[2] or '—').capitalize(), "ok" if (r[2] or '').lower() in ("completed", "concluido", "attended") else "warn"),
                   t(_fmtdate(r[3])), t(_fmtdate(r[4])),
                   t(f"{float(r[5]):.0f}" if r[5] is not None else "—")],
        actionsfn=lambda r: [
            {"title": f"Emitir certificado — {r[1]}",
             "sub": "Só faz sentido para quem concluiu o treinamento.",
             "endpoint": f"/api/v1/people-management/human-resources/training/enrollments/{r[0]}/certificate",
             "method": "POST", "btnLabel": "Certificado", "submitLabel": "Emitir certificado",
             "btnStyle": "primary", "okMsg": "Certificado emitido. Recarregue a tela.", "fields": []},
        ] if r[4] or (r[2] or '').lower() in ("completed", "concluido", "attended") else None))

    return out
