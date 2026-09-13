"""Mapa de Ponto (5 estados) e Grade real/contratual — a régua ÚNICA, reutilizável.

Frente 4 do plano DigiExpress (12/09/2026). Duas superfícies (a grade cliente×dia e o mapa de
hoje) e a triagem diária do Hermes têm de responder a MESMA pergunta — "quem deveria estar em
qual posto, e estava?" — com a mesma régua. A régua já existia em três pedaços:

  · quem NÃO é cobrado hoje ........ `coorte_ponto.SQL_NAO_AUSENTE_HOJE` (férias, afastado,
                                     reta final). Aqui ela vira `nao_ausente_em(<expr>)` para
                                     valer em QUALQUER dia do mês, sem cópia: é o mesmo texto
                                     com o "hoje" trocado pela expressão.
  · turno esperado e janela ........ `presence_controller` (`_SHIFT_ESPERADO`,
                                     `_janela_presenca`, `_primeira_batida_na_janela`,
                                     `TOLERANCIA_ATRASO`) — é o que `presenca_ao_vivo`, a
                                     ferramenta que o Hermes usa na triagem, já aplica.
  · distância ao posto .............. `punch_service._haversine`.

Os cinco estados, exatamente: ok · atendido_com_atraso · atendido_posto_incorreto ·
atendido_fora_de_escala · descoberto. "Posto incorreto" = a batida caiu dentro do geofence de
OUTRO posto. "Fora de escala" = bateu sem turno na escala do dia. Não há sexto estado: turno
cuja tolerância ainda não venceu devolve `None` e o chamador o conta, não o pinta.

Fuso: `gp_clock_punches.punch_timestamp` é `timestamp without time zone` guardando hora LOCAL
de Manaus (convenção do `punch_service`; medido em 12/09: batida 17:02 com `created_at`
21:02 UTC). Por isso aqui NÃO há conversão — `agora` é Manaus naive, como no quadro ao vivo.

A tolerância é lida do banco (`geofence_zones.entry_tolerance_minutes` do posto); sem valor lá
— e em 12/09 nenhum posto tinha — vale a do quadro ao vivo, que é a que a triagem enxerga.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from modules.operacional.presence.controllers.presence_controller import (
    _SHIFT_ESPERADO,
    FIM_JANELA_NOTURNO,
    TOLERANCIA_ATRASO,
    _janela_presenca,
    _janela_turno,
    _primeira_batida_na_janela,
)
from modules.people_management.ponto.coorte_ponto import SQL_NAO_AUSENTE_HOJE
from modules.people_management.ponto.services.punch_service import _haversine

_TZ = ZoneInfo("America/Manaus")

ESTADOS = ("ok", "atendido_com_atraso", "atendido_posto_incorreto", "atendido_fora_de_escala", "descoberto")

#: Quem entra na conta: ativo e não homologação. PJ com turno na escala é cobrado como todo
#: mundo — o posto precisa dele lá.
COORTE = "lower(coalesce(e.status,'')) = 'ativo' AND coalesce(e.is_homologacao,false) = false"

_HOJE_MANAUS = "(now() AT TIME ZONE 'America/Manaus')::date"


def nao_ausente_em(expr_data: str) -> str:
    """A régua de ausência da coorte, valendo para a data `expr_data` (expressão SQL).

    `SQL_NAO_AUSENTE_HOJE` só conhece o hoje de Manaus; a grade do mês precisa dela dia a dia.
    Trocar a expressão é reutilizar, não copiar — se a régua mudar lá, muda aqui.
    """
    if _HOJE_MANAUS not in SQL_NAO_AUSENTE_HOJE:
        raise RuntimeError("coorte_ponto.SQL_NAO_AUSENTE_HOJE mudou de forma — nao_ausente_em precisa acompanhar")
    return SQL_NAO_AUSENTE_HOJE.replace(_HOJE_MANAUS, f"({expr_data})")


_SQL_TURNOS = f"""
SELECT sh.id::text AS shift_id, sh.shift_date, sh.planned_start_time, sh.planned_end_time,
       sh.actual_start_time, sh.status AS shift_status,
       sh.post_id::text AS post_id, p.name AS posto, coalesce(c.name, '—') AS cliente,
       sh.employee_id::text AS employee_id, e.nome
  FROM shifts sh
  JOIN employees e ON e.id = sh.employee_id
  JOIN posts p ON p.id = sh.post_id
  LEFT JOIN clients c ON c.id = p.client_id
 WHERE sh.shift_date BETWEEN CAST(:de AS date) AND CAST(:ate AS date)
   AND {_SHIFT_ESPERADO} AND {COORTE} {{nao_ausente}}
 ORDER BY p.name, sh.shift_date, sh.planned_start_time, e.nome
"""

#: Turno lançado para quem a régua NÃO cobra no dia — não vira "descoberto", mas o supervisor
#: precisa saber que aquele turno está sem gente cobrada (é buraco de escala, não falta).
_SQL_TURNOS_EXCLUIDOS = f"""
SELECT sh.id::text AS shift_id, sh.shift_date, sh.planned_start_time, p.name AS posto,
       sh.employee_id::text AS employee_id, e.nome
  FROM shifts sh JOIN employees e ON e.id = sh.employee_id JOIN posts p ON p.id = sh.post_id
 WHERE sh.shift_date BETWEEN CAST(:de AS date) AND CAST(:ate AS date)
   AND {_SHIFT_ESPERADO} AND NOT ({COORTE} {{nao_ausente}})
"""

#: Mesma validade e mesma cauda D+1 07:00 de `presence_controller._batidas_por_funcionario`;
#: traz a mais o que o geofence precisa (posição, posto que o app validou).
_SQL_BATIDAS = """
SELECT cp.employee_id::text AS employee_id, cp.punch_timestamp, cp.posto_id, cp.posto_nome,
       cp.dentro_geofence, cp.distancia_posto_metros, cp.latitude, cp.longitude, cp.device_type
  FROM gp_clock_punches cp
 WHERE cp.punch_timestamp >= :ini AND cp.punch_timestamp < :fim
   AND coalesce(cp.status, '') <> 'facial_reprovado'
   AND cp.employee_id NOT IN (SELECT id FROM employees WHERE coalesce(is_homologacao, false) = true)
 ORDER BY cp.employee_id, cp.punch_timestamp
"""

_SQL_POSTOS_GEO = """
SELECT id::text AS post_id, name, latitude, longitude, geofence_raio_metros
  FROM posts WHERE is_active AND latitude IS NOT NULL AND longitude IS NOT NULL
"""

_SQL_TOLERANCIA = """
SELECT DISTINCT ON (post_id) post_id::text, entry_tolerance_minutes
  FROM geofence_zones
 WHERE post_id IS NOT NULL AND coalesce(is_active, true) AND entry_tolerance_minutes IS NOT NULL
 ORDER BY post_id, coalesce(is_primary, false) DESC
"""

#: Quem bateu no dia SEM turno esperado em posto nenhum (o "extra" do quadro ao vivo), dentro
#: da coorte — batida de afastado/férias é achado do oráculo `afastado_nao_bate`, não deste mapa.
_SQL_SEM_TURNO = f"""
SELECT e.id::text AS employee_id, e.nome, coalesce(e.posto_atual_nome, '—') AS posto_cadastro
  FROM employees e
 WHERE e.id::text = ANY(:ids) AND {COORTE} {{nao_ausente}}
   AND NOT EXISTS (SELECT 1 FROM shifts sh WHERE sh.employee_id = e.id
                     AND sh.shift_date = CAST(:dia AS date) AND {_SHIFT_ESPERADO})
"""


def agora_manaus() -> datetime:
    return datetime.now(_TZ).replace(tzinfo=None)


def posto_do_geofence(batida: dict, postos_geo: list[dict]) -> tuple[str | None, float | None]:
    """(post_id, distância) do posto em cujo geofence a batida caiu; (None, menor distância)
    quando não caiu em nenhum. Se o app já validou `dentro_geofence`, vale o posto que ele
    validou — o app olhou o posto da alocação, e este é o dado gravado no momento."""
    if batida.get("dentro_geofence") is True and batida.get("posto_id"):
        return str(batida["posto_id"]), batida.get("distancia_posto_metros")
    lat, lon = batida.get("latitude"), batida.get("longitude")
    if lat is None or lon is None:
        return None, None
    dentro, menor = [], None
    for p in postos_geo:
        d = _haversine(lat, lon, p["latitude"], p["longitude"])
        menor = d if menor is None or d < menor else menor
        if d <= (p["geofence_raio_metros"] or 150):
            dentro.append((d, p["post_id"]))
    return (min(dentro)[1], min(dentro)[0]) if dentro else (None, menor)


def classificar(turno: dict, batidas: list[dict], tolerancia_min: int, agora: datetime) -> tuple[str | None, dict | None]:
    """Estado de UM turno esperado a partir das batidas da pessoa (já com `posto_geofence`).

    Devolve (estado, batida_que_decidiu). Estado None = a tolerância ainda não venceu e não
    há batida: não é um dos cinco, e quem chama conta em vez de pintar.
    Pura: nada de banco aqui — é o que os oráculos reproduzem.
    """
    dia, ini, fim = turno["shift_date"], turno["planned_start_time"], turno["planned_end_time"]
    dt_ini, _ = _janela_turno(dia, ini, fim)
    limite = dt_ini + timedelta(minutes=tolerancia_min)
    j_ini, j_fim = _janela_presenca(dia, ini, fim)
    b = _primeira_batida_na_janela(batidas, j_ini, j_fim)
    if b is None:
        manual = turno.get("actual_start_time")
        if manual is not None:  # check-in manual vale como presença, como no quadro ao vivo
            return ("atendido_com_atraso" if manual > limite else "ok"), {"punch_timestamp": manual, "fonte": "manual"}
        if agora >= limite or turno.get("shift_status") == "missed":
            return "descoberto", None
        return None, None
    pg = b.get("posto_geofence")
    if pg and pg != turno["post_id"]:
        return "atendido_posto_incorreto", b
    return ("atendido_com_atraso" if b["punch_timestamp"] > limite else "ok"), b


async def _carregar(db, de: date, ate: date) -> tuple[list[dict], dict[str, list[dict]], list[dict], dict[str, int]]:
    from sqlalchemy import text

    turnos = (await db.execute(text(_SQL_TURNOS.format(nao_ausente=nao_ausente_em("sh.shift_date"))),
                               {"de": de, "ate": ate})).mappings().all()
    postos_geo = [dict(r) for r in (await db.execute(text(_SQL_POSTOS_GEO))).mappings().all()]
    tol = {r[0]: int(r[1]) for r in (await db.execute(text(_SQL_TOLERANCIA))).all()}
    bats = (await db.execute(text(_SQL_BATIDAS), {
        "ini": datetime.combine(de, time.min),
        "fim": datetime.combine(ate + timedelta(days=1), FIM_JANELA_NOTURNO)})).mappings().all()
    batidas: dict[str, list[dict]] = {}
    for r in bats:
        b = dict(r)
        b["posto_geofence"], b["dist_geofence"] = posto_do_geofence(b, postos_geo)
        batidas.setdefault(b["employee_id"], []).append(b)
    return [dict(t) for t in turnos], batidas, postos_geo, tol


def _tolerancia(tol: dict[str, int], post_id: str) -> int:
    return tol.get(post_id, int(TOLERANCIA_ATRASO.total_seconds() // 60))


def _item(t: dict, estado: str | None, b: dict | None, tol_min: int) -> dict:
    return {
        "shift_id": t["shift_id"], "employee_id": t["employee_id"], "nome": t["nome"],
        "post_id": t["post_id"], "posto": t["posto"], "cliente": t["cliente"],
        "dia": t["shift_date"].isoformat(),
        "turno": f"{t['planned_start_time']:%H:%M}–{t['planned_end_time']:%H:%M}",
        "estado": estado, "tolerancia_min": tol_min,
        "batida_em": b["punch_timestamp"].isoformat(timespec="seconds") if b else None,
        "fonte": (b or {}).get("fonte") or ((b or {}).get("device_type")),
        "posto_geofence": (b or {}).get("posto_geofence"),
        "dist_m": round(b["dist_geofence"]) if b and b.get("dist_geofence") is not None else None,
        "dentro_geofence": (b or {}).get("dentro_geofence"),
    }


async def mapa_do_dia(db, dia: date | None = None, agora: datetime | None = None) -> dict:
    """Um item por turno esperado do dia (estado ou None) + quem bateu fora de escala."""
    from sqlalchemy import text

    agora = agora or agora_manaus()
    dia = dia or agora.date()
    turnos, batidas, _geo, tol = await _carregar(db, dia, dia)
    itens = []
    for t in turnos:
        tm = _tolerancia(tol, t["post_id"])
        estado, b = classificar(t, batidas.get(t["employee_id"], []), tm, agora)
        itens.append(_item(t, estado, b, tm))

    fora: list[dict] = []
    ids = list(batidas)
    if ids:
        sem_turno = (await db.execute(text(_SQL_SEM_TURNO.format(nao_ausente=nao_ausente_em("CAST(:dia AS date)"))),
                                      {"ids": ids, "dia": dia})).mappings().all()
        for r in sem_turno:
            b = batidas[r["employee_id"]][0]
            fora.append({
                "shift_id": None, "employee_id": r["employee_id"], "nome": r["nome"],
                "post_id": b.get("posto_geofence") or (str(b["posto_id"]) if b.get("posto_id") else None),
                "posto": b.get("posto_nome") or r["posto_cadastro"], "cliente": "—", "dia": dia.isoformat(),
                "turno": "sem turno", "estado": "atendido_fora_de_escala",
                "batida_em": b["punch_timestamp"].isoformat(timespec="seconds"), "fonte": b.get("device_type"),
                "posto_geofence": b.get("posto_geofence"),
                "dist_m": round(b["dist_geofence"]) if b.get("dist_geofence") is not None else None,
                "dentro_geofence": b.get("dentro_geofence"),
            })

    excluidos = (await db.execute(text(_SQL_TURNOS_EXCLUIDOS.format(nao_ausente=nao_ausente_em("sh.shift_date"))),
                                   {"de": dia, "ate": dia})).mappings().all()
    return {
        "dia": dia.isoformat(), "agora": agora.isoformat(timespec="seconds"),
        "itens": itens, "fora_de_escala": fora,
        "nao_vencidos": sum(1 for i in itens if i["estado"] is None),
        "excluidos": [{"nome": r["nome"], "posto": r["posto"], "turno": f"{r['planned_start_time']:%H:%M}"} for r in excluidos],
        "tolerancia_padrao_min": int(TOLERANCIA_ATRASO.total_seconds() // 60),
        "tolerancia_do_banco": tol,
    }


async def grade_do_mes(db, ano: int, mes: int, agora: datetime | None = None) -> dict:
    """Por posto, por dia do mês: contratual (turnos esperados) e real (atendidos).

    Dia futuro tem contratual e real=None. Hoje conta só o que já venceu a tolerância — um
    turno noturno às 09:00 não é buraco, é o resto do dia.
    """
    agora = agora or agora_manaus()
    de = date(ano, mes, 1)
    ate = (date(ano + (mes == 12), mes % 12 + 1, 1) - timedelta(days=1))
    turnos, batidas, _geo, tol = await _carregar(db, de, ate)
    postos: dict[str, dict] = {}
    for t in turnos:
        p = postos.setdefault(t["post_id"], {"post_id": t["post_id"], "posto": t["posto"], "cliente": t["cliente"], "dias": {}})
        d = t["shift_date"].isoformat()
        cel = p["dias"].setdefault(d, {"contratual": 0, "real": 0, "descoberto": 0, "pendente": 0})
        cel["contratual"] += 1
        if t["shift_date"] > agora.date():
            cel["pendente"] += 1
            continue
        estado, _b = classificar(t, batidas.get(t["employee_id"], []), _tolerancia(tol, t["post_id"]), agora)
        if estado is None:
            cel["pendente"] += 1
        elif estado == "descoberto":
            cel["descoberto"] += 1
        else:
            cel["real"] += 1
    return {"ano": ano, "mes": mes, "de": de.isoformat(), "ate": ate.isoformat(), "hoje": agora.date().isoformat(),
            "postos": sorted(postos.values(), key=lambda p: (p["cliente"], p["posto"]))}
