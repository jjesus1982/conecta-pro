"""Saúde ocupacional (T1) — delega ao _build_saude do monólito e ESTENDE com
estabilidade (garantia de emprego) e alertas (ASOs vencidos). Leitura real; ação
legal (transmitir eSocial) segue GATED."""
import logging

from sqlalchemy import text

from modules.operacional.controllers.redesign_data_controller import (
    S, _build_saude, _fmtdate, _helpers, _scalar, b, brl, doc, t,
)

logger = logging.getLogger(__name__)

SLUG = "saude-ocupacional"
EXTRA_MENU: list[dict] = [
    {"id": "ltcat", "label": "LTCAT", "icon": "M3 3v18h18"},
    {"id": "ltcat-atualizar", "label": "LTCAT — atualizar", "icon": "M3 3v18h18"},
    {"id": "fichas-epi", "label": "Fichas de EPI",
     "icon": "M9 12l2 2 4-4M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z"},
    {"id": "cipa-reuniao", "label": "Registrar reunião da CIPA", "icon": "M12 2l7 4v6c0 5-3 8-7 10-4-2-7-5-7-10V6z"},
]


async def build(db) -> dict:
    out = await _build_saude(db)  # base: visao, exames, epi, riscos, esocial, cat, afastamentos
    _, _safe, tbl = _helpers(db)

    # Estabilidade / garantia de emprego (CCT + Lei 8.213) — sst_afastamentos c/ gera_estabilidade
    try:
        n_est = await _scalar(db, "SELECT count(*) FROM sst_afastamentos WHERE gera_estabilidade=true")
        out["estabilidade"] = await tbl(
            "Estabilidade (garantia de emprego)", f"{n_est} colaborador(es) com estabilidade", "—",
            ["Colaborador", "Motivo", "Estável até", "Status"], "1.8fr 1.3fr 1fr 0.9fr",
            "SELECT coalesce(e.nome,'—'), coalesce(a.tipo::text,'—'), a.estabilidade_ate, coalesce(a.status::text,'—') "
            "FROM sst_afastamentos a LEFT JOIN employees e ON e.id::text=a.employee_id::text "
            "WHERE a.gera_estabilidade=true ORDER BY a.estabilidade_ate DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')), t(_fmtdate(r[2])),
                       b((r[3] or '—').replace('_', ' ').capitalize(), "ok")])
    except Exception:  # noqa: BLE001 — uma tela falha não derruba as demais
        pass

    # Alertas SST — ASOs vencidos (renovação de exame) — gp_asos
    try:
        n_venc = await _scalar(db, "SELECT count(*) FROM gp_asos WHERE data_validade < now()")
        out["alertas"] = await tbl(
            "Alertas SST — ASOs vencidos", f"{n_venc} ASOs vencidos (renovar exame)", "—",
            ["Colaborador", "Tipo", "Venceu em", "Status"], "1.8fr 1.2fr 1fr 0.9fr",
            "SELECT coalesce(e.nome,'—'), coalesce(a.tipo::text,'—'), a.data_validade, coalesce(a.status::text,'—') "
            "FROM gp_asos a LEFT JOIN employees e ON e.id=a.employee_id "
            "WHERE a.data_validade < now() ORDER BY a.data_validade DESC LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')), t(_fmtdate(r[2])), b("Vencido", "bad")])
    except Exception:  # noqa: BLE001
        pass

    # Exames: painel de regularização PCMSO (composite) — FIDELIDADE: lógica EXATA do clássico
    # (último ASO por colaborador ATIVO), _get_pcmso_stats do sst_service → números batem (25).
    try:
        validos = await _scalar(
            db, "SELECT count(DISTINCT employee_id) FROM gp_asos WHERE status='realizado' "
                "AND (data_validade IS NULL OR data_validade >= current_date)")
        vencidos = await _scalar(
            db, "WITH ultimo_aso AS (SELECT DISTINCT ON (a.employee_id) a.employee_id, a.data_validade "
                "FROM gp_asos a WHERE a.data_validade IS NOT NULL ORDER BY a.employee_id, a.data_validade DESC) "
                "SELECT count(*) FROM ultimo_aso u JOIN employees e ON e.id=u.employee_id AND e.status='ativo' "
                "WHERE u.data_validade < current_date")
        ativos = await _scalar(db, "SELECT count(*) FROM employees WHERE status='ativo'")
        # Lista dos colaboradores com ASO vencido (bate os 25 do clássico): último ASO por
        # colaborador ativo, expirado → nome/cargo/dias vencido.
        desc = (await db.execute(text(
            "WITH ultimo AS (SELECT DISTINCT ON (a.employee_id) a.employee_id, a.data_validade "
            "FROM gp_asos a WHERE a.data_validade IS NOT NULL ORDER BY a.employee_id, a.data_validade DESC) "
            "SELECT e.nome, coalesce(e.cargo,'—'), (CURRENT_DATE - u.data_validade) AS dias "
            "FROM ultimo u JOIN employees e ON e.id=u.employee_id AND e.status='ativo' "
            "WHERE u.data_validade < CURRENT_DATE ORDER BY u.data_validade ASC LIMIT 40"))).fetchall()
        if "exames" in out and isinstance(out["exames"], dict):
            out["exames"]["panelGrid"] = "1fr 1.4fr"
            out["exames"]["panels"] = [
                {"title": "Regularização PCMSO (por colaborador ativo)", "rows": [
                    {"left": "ASOs válidos", "right": str(validos or 0), **S["ok"]},
                    {"left": "Colaboradores com ASO vencido", "right": str(vencidos or 0), **S["bad"]},
                    {"left": "Pendentes (sem ASO válido)", "right": str(max(0, (ativos or 0) - (validos or 0))), **S["warn"]},
                ]},
                {"title": f"Colaboradores a regularizar ({len(desc)})", "rows": [
                    {"left": f"{d[0]} · {d[1]}", "right": f"{int(d[2])} dias", **S["warn"]} for d in desc
                ] or [{"left": "Todos regularizados", "right": "OK", **S["ok"]}]},
            ]
    except Exception:  # noqa: BLE001
        pass

    # Afastamentos: indicadores (composite). FIDELIDADE ao clássico (afastamentos/page.tsx:213):
    # taxaAfastamento = ATIVOS / TOTAL_REGISTROS (não / headcount). O SSTService dava 4/50=8%,
    # mas o clássico exibe 4/8=50.0%. Replicar a fórmula da tela. Custo = ajuda-medicamento (R$900).
    try:
        from modules.people_management.sst.services.sst_service import SSTService
        dash = await SSTService(db).get_dashboard()
        tot_afast = await _scalar(db, "SELECT count(*) FROM sst_afastamentos") or 0
        ativ_afast = await _scalar(db, "SELECT count(*) FROM sst_afastamentos WHERE lower(status::text)='ativo'") or 0
        taxa_afast = round((ativ_afast / tot_afast * 100) if tot_afast else 0, 1)
        if "afastamentos" in out and isinstance(out["afastamentos"], dict):
            out["afastamentos"].setdefault("panelGrid", "1fr")
            out["afastamentos"]["panels"] = [{"title": "Indicadores de afastamento", "rows": [
                {"left": "Afastados ativos", "right": str(ativ_afast), **S["warn"]},
                {"left": "Taxa de afastamento", "right": f"{taxa_afast}%", **S["info"]},
                {"left": "Ajuda-medicamento ativa", "right": str(dash.get("ajuda_medicamento_ativa", 0)), **S["info"]},
                {"left": "Custo mensal (ajuda-medicamento)", "right": brl(dash.get("custo_afastamentos_mes", 0)), **S["bad"]},
            ]}]
    except Exception:  # noqa: BLE001
        pass

    # CAT: indicadores de acidente (composite) — mesma fórmula do clássico (calcular_taxa_acidente)
    try:
        tot_cats = await _scalar(db, "SELECT count(*) FROM gp_cats")
        tot_colab = await _scalar(db, "SELECT count(*) FROM employees WHERE status='ativo'")
        taxa = round((tot_cats / tot_colab * 100) if tot_colab else 0, 2)
        if "cat" in out and isinstance(out["cat"], dict):
            out["cat"].setdefault("panelGrid", "1fr")
            out["cat"]["panels"] = [{"title": "Indicadores de acidentes", "rows": [
                {"left": "Total de CATs", "right": str(tot_cats or 0), **S["info"]},
                {"left": "Total de colaboradores", "right": str(tot_colab or 0), **S["info"]},
                {"left": "Taxa de acidente", "right": f"{taxa}%", **S["warn"]},
            ]}]
    except Exception:  # noqa: BLE001
        pass

    # DOCUMENTOS SST — rotas curl-provadas (200 application/pdf):
    # NR-1 compliance (nível-tela, sem id) na visão; Ficha EPI + PPP por-linha na tela nova.
    try:
        if "visao" in out and isinstance(out["visao"], dict):
            out["visao"].setdefault("docs", [])
            out["visao"]["docs"].append(
                doc("NR-1 Compliance (PDF)", "/api/v1/people-management/sst/nr1/compliance/pdf",
                    fmt="pdf", gate="sst"))
    except Exception:  # noqa: BLE001
        pass

    try:
        n_epi = await _scalar(db, "SELECT count(*) FROM sst_fichas_epi") or 0
        out["fichas-epi"] = await tbl(
            "Fichas de EPI", f"{n_epi} ficha(s)", "—",
            ["Colaborador", "Status", "Emitida"], "2fr 1.3fr 1fr",
            "SELECT id, employee_id, coalesce(employee_nome,'—'), coalesce(status::text,'—'), created_at "
            "FROM sst_fichas_epi ORDER BY created_at DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[2], 600, "#0F1B3A"),
                       b((r[3] or '—').replace('_', ' ').capitalize(),
                         "ok" if 'assinad' in (r[3] or '').lower() else "warn"),
                       t(_fmtdate(r[4]))],
            docsfn=lambda r: [
                doc("Ficha EPI (PDF)", f"/api/v1/people-management/sst/epi/fichas/{r[0]}/pdf", fmt="pdf"),
                doc("PPP (PDF)", f"/api/v1/people-management/sst/ppp/{r[1]}/pdf", fmt="pdf"),
            ])
    except Exception:  # noqa: BLE001
        pass

    # CIPA (2026-08-10): o backend registrava a reuniao e nao havia tela. O endpoint recebe
    # um dict livre; as chaves lidas sao data_reuniao (obrigatoria), tipo e pauta.
    # LIGAR (revisão 08/09/2026): vencimentos dos próximos 30 dias e membros da CIPA — existiam só por API
    try:
        out["asos-vencendo"] = await tbl(
            "ASOs vencendo em 30 dias", "Renovar antes de vencer — sem ASO válido o colaborador não trabalha (NR-7)", "—",
            ["Colaborador", "Tipo", "Vence em", "Dias"], "2fr 1fr 1fr 0.7fr",
            "SELECT coalesce(e.nome,'—'), coalesce(a.tipo::text,'—'), a.data_validade, "
            "(a.data_validade - (now() AT TIME ZONE 'America/Manaus')::date) AS dias "
            "FROM gp_asos a JOIN employees e ON e.id=a.employee_id "
            "WHERE e.status='ativo' AND a.data_validade BETWEEN (now() AT TIME ZONE 'America/Manaus')::date "
            "AND (now() AT TIME ZONE 'America/Manaus')::date + 30 ORDER BY a.data_validade LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or "—").replace("_", " ").capitalize()),
                       t(r[2].strftime("%d/%m/%Y") if r[2] else "—"), b(str(r[3]), "warn" if (r[3] or 0) <= 10 else "info")])
        out["cipa-membros"] = await tbl(
            "CIPA — membros", "Composição vigente (eleitos e indicados) com posse e fim de mandato", "—",
            ["Membro", "Função", "Representação", "Posse", "Fim do mandato", "Status"], "1.8fr 1fr 1fr 0.9fr 0.9fr 0.8fr",
            "SELECT coalesce(employee_nome,'—'), coalesce(funcao,'—'), coalesce(representacao,'—'), data_posse, data_fim_mandato, "
            "coalesce(status,'—') FROM sst_cipa_membros ORDER BY data_posse DESC NULLS LAST LIMIT 100",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(r[2]), t(r[3].strftime("%d/%m/%Y") if r[3] else "—"),
                       t(r[4].strftime("%d/%m/%Y") if r[4] else "—"), b((r[5] or "—").capitalize(), "ok" if (r[5] or "").lower() == "ativo" else "mut")])
    except Exception as _exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("saude: asos-vencendo/cipa-membros não montadas: %s", _exc)
    out["cipa-reuniao"] = {
        "title": "Registrar reunião da CIPA",
        "sub": "Ata mínima da reunião: data, tipo e pauta. Ordinária é a do calendário; "
               "extraordinária é a convocada fora dele.",
        "cta": "Registrar", "type": "form",
        "submit": {"endpoint": "/api/v1/people-management/sst/cipa/reunioes",
                   "okMsg": "Reunião da CIPA registrada"},
        "fields": [
            {"key": "data_reuniao", "label": "Data da reunião*", "type": "date", "span": "span 1"},
            {"key": "tipo", "label": "Tipo", "type": "select", "span": "span 1", "ph": "Ordinária",
             "options": [{"value": "ordinaria", "label": "Ordinária"},
                         {"value": "extraordinaria", "label": "Extraordinária"}]},
            {"key": "pauta", "label": "Pauta", "type": "textarea", "span": "span 2",
             "ph": "O que foi tratado"},
        ],
    }

    await _ligar_lote3_20260908(db, out)
    return out


async def _ligar_lote3_20260908(db, out: dict) -> None:
    """LIGAR lote 3 (08/09/2026): rotas que existiam sem tela. Cada bloco é independente (try/except + rollback)."""
    import logging as _lg
    from sqlalchemy import text as _T
    from modules.operacional.controllers.redesign_data_controller import _helpers, t, b, brl
    from modules.operacional.controllers.redesign_builders._ligar_generico import chamar, painel_de_dict, selecionar, tabela_de_lista
    _log = _lg.getLogger(__name__)
    _, _safe, tbl = _helpers(db)
    _SN = [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]

    def _fd(v, fmt="%d/%m/%Y"):
        try:
            return v.strftime(fmt) if v else "—"
        except Exception:  # noqa: BLE001
            return str(v or "—")

    async def _n(sql):
        try:
            return (await db.execute(_T(sql))).scalar() or 0
        except Exception:  # noqa: BLE001
            await db.rollback(); return 0

    try:  # GET /people-management/sst/ltcat/status + PUT /people-management/sst/ltcat
        row = (await db.execute(_T("SELECT status, responsavel_tecnico, registro_conselho, validade_inicio, validade_fim, observacoes, updated_at FROM sst_ltcat ORDER BY updated_at DESC NULLS LAST LIMIT 1"))).first()
        dias = (row[4] - __import__("datetime").date.today()).days if row and row[4] else None
        painel = {"status": (row[0] if row else "sem registro"), "responsavel_tecnico": row[1] if row else None, "registro_conselho": row[2] if row else None,
                  "validade_inicio": _fd(row[3]) if row else None, "validade_fim": _fd(row[4]) if row else None,
                  "dias_para_vencer": dias, "observacoes": row[5] if row else None, "atualizado_em": _fd(row[6], "%d/%m/%Y %H:%M") if row else None}
        out["ltcat"] = painel_de_dict("LTCAT — laudo técnico das condições ambientais", "Situação do laudo (NR-15/16, base do eSocial S-2240) · fonte: sst_ltcat", painel, kpis_de=["status", "validade_fim", "dias_para_vencer", "responsavel_tecnico"])
        _ST = [{"value": v, "label": v.replace("_", " ").capitalize()} for v in ("pendente_elaboracao", "em_elaboracao", "vigente", "vencido")]
        out["ltcat-atualizar"] = {
            "title": "LTCAT — atualizar", "sub": "Responsável técnico, registro no conselho, validade e status. Campos em branco não são alterados.",
            "cta": "Salvar", "type": "form", "submit": {"endpoint": "/api/v1/people-management/sst/ltcat", "method": "PUT", "okMsg": "LTCAT atualizado. Recarregue.", "showResult": True},
            "fields": [selecionar("status", "Status", _ST, "span 1"),
                       {"key": "responsavel_tecnico", "label": "Responsável técnico", "type": "text", "span": "span 1", "value": (row[1] if row else "") or ""},
                       {"key": "registro_conselho", "label": "Registro no conselho (CREA/CRM)", "type": "text", "span": "span 1", "value": (row[2] if row else "") or ""},
                       {"key": "validade_inicio", "label": "Validade — início", "type": "date", "span": "span 1"},
                       {"key": "validade_fim", "label": "Validade — fim", "type": "date", "span": "span 1"},
                       {"key": "observacoes", "label": "Observações", "type": "textarea", "span": "span 2", "value": (row[5] if row else "") or ""}]}
    except Exception as exc:  # noqa: BLE001
        await db.rollback(); _log.warning("ltcat: %s", exc)
