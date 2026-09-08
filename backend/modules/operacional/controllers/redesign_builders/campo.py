"""Campo (T1) — delega ao _build_campo e CORRIGE o 'checkin': o clássico mostra registros
de check-in/check-out de campo (gp_clock_punches), não visitas. Fidelidade da FONTE de dados."""
import logging
from sqlalchemy import text as _sqltext
from modules.operacional.controllers.redesign_data_controller import _build_campo, _helpers, _scalar, b, doc, t

SLUG = "campo"
logger = logging.getLogger(__name__)

EXTRA_MENU: list[dict] = [
    {"id": "visitas", "label": "Visitas de campo", "icon": "M3 3v18h18"},
    {"id": "visita-nova", "label": "Agendar visita", "icon": "M3 3v18h18"},
]


async def build(db) -> dict:
    out = await _build_campo(db)
    _, _safe, tbl = _helpers(db)

    # Relatório de visita (por-visita) = ⛔ NÃO ligar: a rota /campo/visitas/{id}/pdf está SEM
    # autenticação (risco). Chip disabled honesto na visão até o backend corrigir (CurrentActiveUser).
    try:
        if "visao" in out and isinstance(out["visao"], dict):
            out["visao"].setdefault("docs", [])
            out["visao"]["docs"].append(
                doc("Relatório de visita (indisponível)", disabled=True,
                    motivo="Rota /campo/visitas/{id}/pdf sem autenticação — aguardando correção do backend"))
    except Exception:  # noqa: BLE001
        pass
    # 'checkin' estava ligado a visitas (fonte errada). O clássico mostra check-in/out de campo
    # = gp_clock_punches (batidas). FIDELIDADE TZ: o container roda em America/Manaus e o import
    # Tangerino grava via datetime.fromtimestamp(ts/1000) SEM tz → punch_timestamp é naïve em
    # horário LOCAL de Manaus (já convertido). O clássico exibe o raw. NÃO subtrair 4h de novo
    # (o -4h antigo mostrava 02:07 onde o real é 06:07 — turno 18:00→06:07 12x36). Exibe raw.
    try:
        out["checkin"] = await tbl(
            "Check-in / Check-out", "Registros de presença em campo (horário de Manaus)", "—",
            ["Colaborador", "Tipo", "Horário", "Facial", "Geofence"], "1.8fr 0.9fr 1fr 0.8fr 0.9fr",
            "SELECT coalesce(e.nome,'—'), coalesce(p.punch_type::text,'—'), "
            "to_char(p.punch_timestamp,'DD/MM HH24:MI'), p.facial_match, p.dentro_geofence "
            "FROM gp_clock_punches p LEFT JOIN employees e ON e.id=p.employee_id "
            "ORDER BY p.punch_timestamp DESC LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), b((r[1] or '—').capitalize(), "ok" if r[1] == "entrada" else "info"),
                       t(r[2] or '—'), b("OK", "ok") if r[3] else t("—"),
                       (b("Dentro", "ok") if r[4] else b("Fora", "warn")) if r[4] is not None else t("—")])
    except Exception:  # noqa: BLE001
        pass
    await _ligar_campo_20260908(db, out, tbl)
    return out


async def _ligar_campo_20260908(db, out: dict, tbl) -> None:
    """LIGAR 08/09/2026: visitas de campo (agendar, confirmar, check-in/out, resultado, cancelar, reagendar, PDF)."""
    from modules.operacional.controllers.redesign_builders._ligar_generico import badge_status, selecionar
    from modules.operacional.controllers.redesign_data_controller import _fmtdate
    _RES = [{"value": v, "label": l} for v, l in (("sucesso", "Sucesso"), ("parcial", "Parcial"), ("sem_sucesso", "Sem sucesso"), ("cliente_ausente", "Cliente ausente"), ("endereco_nao_encontrado", "Endereço não encontrado"))]
    def _acts(r):
        vid, st = r[7], (r[3] or "").lower()
        base = f"/api/v1/campo/visitas/{vid}"
        acts = []
        if not r[8]:
            acts.append({"title": f"Confirmar visita {r[0]}", "endpoint": f"{base}/confirmar", "method": "POST", "btnLabel": "Confirmar", "submitLabel": "Confirmar", "btnStyle": "outline", "okMsg": "Confirmada. Recarregue.", "fields": [{"key": "confirmado_por", "label": "Confirmado por", "type": "text", "span": "span 2", "value": ""}]})
        if st in ("agendada", "confirmada", "em_deslocamento") and not r[9]:
            acts.append({"title": f"Check-in — {r[0]}", "endpoint": f"{base}/checkin", "method": "POST", "btnLabel": "Check-in", "submitLabel": "Registrar chegada", "btnStyle": "primary", "okMsg": "Check-in registrado. Recarregue.", "fields": []})
        if r[9] and not r[10]:
            acts.append({"title": f"Check-out — {r[0]}", "endpoint": f"{base}/checkout", "method": "POST", "btnLabel": "Check-out", "submitLabel": "Registrar saída", "btnStyle": "primary", "okMsg": "Check-out registrado. Recarregue.", "fields": []})
        if st not in ("cancelada", "concluida"):
            acts.append({"title": f"Resultado — {r[0]}", "endpoint": f"{base}/resultado", "method": "POST", "btnLabel": "Resultado", "submitLabel": "Registrar", "btnStyle": "outline", "okMsg": "Resultado registrado. Recarregue.",
                         "fields": [selecionar("resultado", "Resultado*", _RES), {"key": "descricao_atendimento", "label": "O que foi feito", "type": "textarea", "span": "span 2", "value": ""}, {"key": "proximos_passos", "label": "Próximos passos", "type": "textarea", "span": "span 2", "value": ""}]})
            acts.append({"title": f"Reagendar — {r[0]}", "endpoint": f"{base}/reagendar", "method": "POST", "btnLabel": "Reagendar", "submitLabel": "Reagendar", "btnStyle": "outline", "okMsg": "Reagendada. Recarregue.",
                         "fields": [{"key": "nova_data", "label": "Nova data*", "type": "date", "span": "span 1", "value": ""}, {"key": "novo_horario", "label": "Novo horário*", "type": "text", "span": "span 1", "value": "09:00"}, {"key": "motivo", "label": "Motivo", "type": "text", "span": "span 2", "value": ""}]})
            acts.append({"title": f"Cancelar — {r[0]}", "endpoint": f"{base}/cancelar", "method": "POST", "btnLabel": "Cancelar", "submitLabel": "Cancelar visita", "btnStyle": "outline", "confirm": "Cancelar a visita?", "okMsg": "Cancelada. Recarregue.",
                         "fields": [{"key": "motivo", "label": "Motivo", "type": "text", "span": "span 2", "value": ""}]})
        return acts
    try:
        out["visitas"] = await tbl(
            "Visitas de campo", f"{await _scalar(db, 'SELECT count(*) FROM visitas WHERE coalesce(is_active,true)')} visitas — técnica, comercial, vistoria; check-in/out com GPS", "Agendar visita",
            ["Nº", "Tipo", "Cliente / prospect", "Status", "Data", "Horário", "Responsável"], "0.8fr 0.9fr 1.8fr 0.9fr 0.9fr 0.7fr 1.2fr",
            "SELECT coalesce(v.numero,'—'), coalesce(v.tipo,'—'), coalesce(cl.name, v.prospect_nome, v.prospect_empresa, '—'), coalesce(v.status,'—'), v.data_visita, "
            "v.horario_inicio, coalesce(v.responsavel_nome, e.nome, '—'), v.id::text, coalesce(v.confirmada,false), v.checkin_at, v.checkout_at "
            "FROM visitas v LEFT JOIN clients cl ON cl.id=v.cliente_id LEFT JOIN employees e ON e.id=v.responsavel_id "
            "WHERE coalesce(v.is_active,true) ORDER BY v.data_visita DESC NULLS LAST, v.horario_inicio DESC LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').capitalize()), t((r[2] or '—')[:40]), badge_status(r[3]), t(_fmtdate(r[4])), t(str(r[5])[:5] if r[5] else '—'), t((r[6] or '—')[:28])],
            docsfn=lambda r: [doc("Relatório (PDF)", f"/api/v1/campo/visitas/{r[7]}/pdf", fmt="pdf")],
            actionsfn=_acts)
        out["visitas"]["ctaTo"] = "visita-nova"
    except Exception as exc:  # noqa: BLE001
        logger.warning("visitas: %s", exc)
    emp, cli = [], []
    try:
        emp = [{"value": str(i), "label": n} for i, n in (await db.execute(_sqltext("SELECT id, nome FROM employees WHERE status='ativo' ORDER BY nome LIMIT 300"))).fetchall()]
        cli = [{"value": str(i), "label": n} for i, n in (await db.execute(_sqltext("SELECT id, name FROM clients WHERE coalesce(ativo,true) ORDER BY name LIMIT 300"))).fetchall()]
    except Exception:  # noqa: BLE001
        await db.rollback()
    out["visita-nova"] = {
        "title": "Agendar visita", "sub": "Visita técnica, comercial ou vistoria. Cliente da base ou prospect (preencha o nome).",
        "cta": "Agendar", "type": "form", "submit": {"endpoint": "/api/v1/campo/visitas/", "okMsg": "Visita agendada"},
        "fields": [selecionar("tipo", "Tipo*", [{"value": v, "label": l} for v, l in (("tecnica", "Técnica"), ("comercial", "Comercial"), ("vistoria", "Vistoria"), ("prospeccao", "Prospecção"), ("orcamento", "Orçamento"))], "span 1"),
                   selecionar("origem", "Origem", [{"value": v, "label": l} for v, l in (("cliente", "Cliente"), ("lead", "Lead"), ("indicacao", "Indicação"), ("prospeccao_ativa", "Prospecção ativa"), ("campanha_marketing", "Campanha"))], "span 1"),
                   selecionar("responsavel_id", "Responsável*", emp), selecionar("responsavel_tipo", "Papel do responsável", [{"value": v, "label": v.capitalize()} for v in ("tecnico", "vendedor", "supervisor", "consultor")], "span 1"),
                   selecionar("cliente_id", "Cliente", cli, "span 1"), {"key": "prospect_nome", "label": "Prospect (se não for cliente)", "type": "text", "span": "span 1"},
                   {"key": "prospect_telefone", "label": "Telefone do prospect", "type": "text", "span": "span 1"},
                   {"key": "data_visita", "label": "Data*", "type": "date", "span": "span 1"}, {"key": "horario_inicio", "label": "Horário*", "type": "text", "span": "span 1", "ph": "09:00"},
                   {"key": "endereco", "label": "Endereço", "type": "text", "span": "span 2"}, {"key": "bairro", "label": "Bairro", "type": "text", "span": "span 1"}, {"key": "cidade", "label": "Cidade", "type": "text", "span": "span 1", "ph": "Manaus"},
                   {"key": "objetivo", "label": "Objetivo", "type": "textarea", "span": "span 2"}]}
