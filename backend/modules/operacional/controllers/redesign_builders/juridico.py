"""Jurídico (T1) — override do _build_juridico com telas novas (leitura real).
Ação legal (parecer/transmitir) fica GATED. Ver auditoria/parity/DIVISAO_3T.md."""
from sqlalchemy import text

from modules.operacional.controllers.redesign_data_controller import (
    IC, S, _ICF, _fmtdate, _helpers, _scalar, b, brl, t,
)

SLUG = "juridico"
EXTRA_MENU: list[dict] = []  # det-comunicacoes já vem do EXTRA_MENU do monólito


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)
    n_proc = await _scalar(db, "SELECT count(*) FROM juridico_processos")

    async def _visao():
        st = (await db.execute(text("SELECT status::text, count(*) FROM juridico_processos GROUP BY status ORDER BY count(*) DESC"))).fetchall()
        tp = (await db.execute(text("SELECT tipo::text, count(*) FROM juridico_processos GROUP BY tipo ORDER BY count(*) DESC LIMIT 6"))).fetchall()
        n_conh = await _scalar(db, "SELECT count(*) FROM juridico_conhecimento")
        n_ctr = await _scalar(db, "SELECT count(*) FROM client_contracts")
        return {"title": "Visão geral", "sub": "Jurídico — dados reais", "cta": "Novo processo", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": str(n_proc), "l": "Processos", "icon": _ICF["chart"], "color": "#0F1B3A"},
                    {"v": str(await _scalar(db, "SELECT count(*) FROM juridico_processos WHERE escalonar=true") or 0), "l": "Escalonados", "icon": IC["alert"], "color": "#C2410C"},
                    {"v": str(n_conh), "l": "Base de conhecimento", "icon": IC["cal"], "color": "#0F1B3A"},
                    {"v": str(n_ctr), "l": "Contratos", "icon": _ICF["hand"], "color": "#0F1B3A"},
                ],
                "panels": [
                    {"title": "Processos por status", "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["info"]} for s, c in st] or [{"left": "Sem processos", "right": "0", **S["mut"]}]},
                    {"title": "Processos por tipo", "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["warn"]} for s, c in tp] or [{"left": "—", "right": "0", **S["mut"]}]},
                ]}

    await safe("visao", _visao())
    await safe("processos", tbl("Processos", f"{n_proc} processos", "Novo processo",
        ["Número", "Tipo", "Reclamante", "Status"], "1.4fr 1.2fr 1.8fr 0.9fr",
        "SELECT coalesce(numero,'—'), coalesce(tipo::text,'—'), coalesce(reclamante,'—'), status::text FROM juridico_processos ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')), t(r[2]), b(r[3] or "—", "info")]))

    # DET — Comunicações (Domicílio Eletrônico Trabalhista). Serve tanto o EXTRA_MENU
    # 'det-comunicacoes' quanto o item de menu json 'processos-det' (mesma fonte real).
    _det_tone = {"nova": "warn", "aberta": "warn", "pendente": "warn", "respondida": "ok", "encerrada": "ok", "ciente": "ok", "arquivada": "mut"}

    def _det_screen():
        return tbl(
            "DET — Comunicações", f"{n_det} comunicações", "—",
            ["Título", "Tipo", "Órgão", "Número", "Prazo", "Status"], "1.9fr 1fr 1.3fr 0.9fr 0.9fr 0.9fr",
            "SELECT coalesce(titulo,'—'), coalesce(tipo,'—'), coalesce(orgao,'—'), coalesce(numero,'—'), coalesce(prazo,'—'), coalesce(status,'—') "
            "FROM juridico_det_comunicacoes ORDER BY created_at DESC NULLS LAST LIMIT 200",
            lambda r: [t((r[0] or '—')[:52], 600, "#0F1B3A"), t(r[1]), t((r[2] or '—')[:30]), t(r[3]), t(r[4]),
                       b((r[5] or '—').capitalize(), _det_tone.get((r[5] or '').lower(), "info"))])
    n_det = await _scalar(db, "SELECT count(*) FROM juridico_det_comunicacoes")
    await safe("det-comunicacoes", _det_screen())
    await safe("processos-det", _det_screen())

    # Contratos (jurídico) — client_contracts
    await safe("contratos", tbl(
        "Contratos", f"{await _scalar(db, 'SELECT count(*) FROM client_contracts')} contratos", "—",
        ["Contrato", "Serviço", "Início", "Fim", "Mensal", "Status"], "1.1fr 1.3fr 0.9fr 0.9fr 1fr 0.9fr",
        "SELECT coalesce(contract_number,'—'), coalesce(service_type::text,'—'), start_date, end_date, monthly_value, coalesce(status::text,'—') "
        "FROM client_contracts ORDER BY start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')), t(_fmtdate(r[2])), t(_fmtdate(r[3])),
                   t(brl(r[4]) if r[4] is not None else '—', 600),
                   b((r[5] or '—').capitalize(), "ok" if (r[5] or '').lower() in ("active", "ativo", "vigente") else "mut")]))

    # Base de conhecimento jurídico — juridico_conhecimento
    await safe("conhecimento", tbl(
        "Base de conhecimento", f"{await _scalar(db, 'SELECT count(*) FROM juridico_conhecimento')} itens", "—",
        ["Título", "Tipo", "Área", "Desfecho"], "2fr 1fr 1.1fr 1.4fr",
        "SELECT coalesce(titulo,'—'), coalesce(tipo::text,'—'), coalesce(area,'—'), coalesce(desfecho,'—') "
        "FROM juridico_conhecimento WHERE coalesce(ativo,true)=true ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t((r[0] or '—')[:60], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')), t(r[2]), t((r[3] or '—')[:50])]))

    # 'escritorio' (juridico_escritorio_consultas) NÃO wirado: só contém linha de teste
    # (__probe_frontend__) → fica honesto "aguardando dado" até haver consulta real.

    # Análises (contratos/documentos) — juridico_analises (resultado é JSON → extrai resumo)
    def _risk_b(v):
        try:
            n = float(v)
        except (TypeError, ValueError):
            return b(str(v or "—"), "info")
        return b(f"risco {n:.0f}", "bad" if n >= 67 else "warn" if n >= 34 else "ok")
    await safe("analise", tbl(
        "Análises", f"{await _scalar(db, 'SELECT count(*) FROM juridico_analises')} análises", "—",
        ["Nome", "Tipo", "Parecer", "Risco"], "1.5fr 1fr 2fr 0.9fr",
        "SELECT coalesce(nome,'—'), coalesce(tipo::text,'—'), coalesce(resultado->>'resumo', resultado::text, '—'), score_risco "
        "FROM juridico_analises ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t((r[0] or '—')[:48], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')), t((r[2] or '—')[:75]), _risk_b(r[3])]))

    # Riscos jurídicos — Exposição trabalhista por funcionário. FIDELIDADE: reusa o MESMO
    # serviço do clássico (riscos_service.riscos_trabalhista) → os números batem. Sync → thread.
    try:
        import asyncio

        from core.database.session import SyncSessionLocal
        from modules.juridico import riscos_service

        def _sync_riscos():
            sdb = SyncSessionLocal()
            try:
                return riscos_service.riscos_trabalhista(sdb)
            finally:
                sdb.close()

        rk = await asyncio.to_thread(_sync_riscos)
        det = rk.get("detalhado", []) or []
        _VLBL0 = {"fgts_multa_40": "FGTS+multa 40%", "aviso_previo": "Aviso prévio",
                  "ferias_prop_mais_terco": "Férias+1/3", "decimo_terceiro_prop": "13º",
                  "diferenca_piso_retroativa": "Dif. piso"}
        _por_tipo = " · ".join(f"{_VLBL0.get(k, k)} {brl(v)}"
                               for k, v in sorted((rk.get("por_tipo") or {}).items(), key=lambda x: -(x[1] or 0))
                               if v)

        _VLBL = {  # rótulos do clássico (fidelidade — o clássico vence)
            "fgts_multa_40": "FGTS + multa 40%", "aviso_previo": "Aviso prévio",
            "ferias_prop_mais_terco": "Férias prop. + 1/3", "decimo_terceiro_prop": "13º proporcional",
            "diferenca_piso_retroativa": "Diferença de piso", "horas_extras_noturno": "Horas extras/noturno",
            "adicionais_risco": "Adicionais de risco",
        }

        def _verbas_tags(v: dict) -> str:
            xs = [_VLBL.get(k, k.replace('_', ' ')) for k, vv in (v or {}).items()
                  if isinstance((vv or {}).get('valor'), (int, float)) and (vv or {}).get('valor')]
            return " · ".join(xs)

        out["riscos"] = {
            "title": "Riscos Jurídicos — Exposição trabalhista",
            "sub": (f"Exposição estimada total {brl(rk.get('total_exposicao_estimada', 0))} · "
                    f"{rk.get('funcionarios_com_risco', 0)} de {rk.get('funcionarios_analisados', 0)} "
                    f"colaboradores com risco (estimativa, não provisão)"
                    + (f" · Por tipo de verba: {_por_tipo}" if _por_tipo else "")),
            "cta": "—", "type": "table", "searchHint": "Buscar colaborador…",
            "grid": "1.8fr 1.3fr 0.8fr 1fr 1.9fr",
            "cols": ["Colaborador", "Cargo", "Meses casa", "Exposição estimada", "Verbas"],
            "rows": [{"cells": [
                t(d.get("nome") or "—", 600, "#0F1B3A"),
                t(d.get("cargo") or "—"),
                t(str(d.get("meses_de_casa")) if d.get("meses_de_casa") is not None else "—"),
                t(brl(d.get("exposicao_estimada") or 0), 600, "#0F1B3A"),
                t(_verbas_tags(d.get("verbas")) or "—"),
            ]} for d in det[:300]],
        }
        # Seção Tributário (mesmo serviço do clássico) → painéis abaixo da tabela (tela composta)
        try:
            def _sync_trib():
                sdb = SyncSessionLocal()
                try:
                    return riscos_service.riscos_tributario(sdb)
                finally:
                    sdb.close()

            tb = await asyncio.to_thread(_sync_trib)
            enq = tb.get("enquadramento", {}) or {}
            _nt = {"alto": "bad", "atenção": "warn", "atencao": "warn", "medio": "warn", "baixo": "ok"}
            out["riscos"]["panelGrid"] = "1fr 1fr"
            out["riscos"]["panels"] = [
                {"title": "Tributário — Enquadramento (Simples × Lucro Real)", "rows": [
                    {"left": "Faturamento anualizado", "right": brl(enq.get("faturamento_anualizado", 0)), **S["info"]},
                    {"left": "Teto do Simples (anual)", "right": brl(enq.get("teto_simples_anual", 0)), **S["info"]},
                    {"left": "Ocupação do teto", "right": f"{enq.get('ocupacao_teto_pct', '—')}%", **S["warn"]},
                    {"left": "Pode optar pelo Simples?", "right": "Sim" if enq.get("pode_simples") else "Não",
                     **(S["ok"] if enq.get("pode_simples") else S["bad"])},
                ]},
                {"title": "Riscos tributários identificados", "rows": [
                    {"left": (r.get("tema") or "—")[:64], "right": (r.get("nivel") or "—").capitalize(),
                     **S[_nt.get((r.get("nivel") or "").lower(), "info")]}
                    for r in (tb.get("riscos") or [])
                ] or [{"left": "Nenhum risco tributário", "right": "OK", **S["ok"]}]},
            ]
        except Exception:  # noqa: BLE001 — tributário não derruba a tabela trabalhista
            pass
    except Exception:  # noqa: BLE001 — riscos não derruba o resto do módulo
        pass

    return out
