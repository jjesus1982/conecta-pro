"""Campo (T1) — delega ao _build_campo e CORRIGE o 'checkin': o clássico mostra registros
de check-in/check-out de campo (gp_clock_punches), não visitas. Fidelidade da FONTE de dados."""
from modules.operacional.controllers.redesign_data_controller import _build_campo, _helpers, b, t

SLUG = "campo"
EXTRA_MENU: list[dict] = []


async def build(db) -> dict:
    out = await _build_campo(db)
    _, _safe, tbl = _helpers(db)
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
    return out
