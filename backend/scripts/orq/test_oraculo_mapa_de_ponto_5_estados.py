"""Oráculo — todo item do MAPA DE PONTO de hoje tem um dos CINCO estados, e o estado se
reproduz a partir das FONTES (12/09/2026, frente 4 do plano DigiExpress).

Os cinco, decididos e não reabertos: `ok` · `atendido_com_atraso` · `atendido_posto_incorreto`
· `atendido_fora_de_escala` · `descoberto`. "Posto incorreto" = bateu dentro do geofence de
OUTRO posto. "Fora de escala" = bateu sem turno na escala do dia.

Por que existe: o pré-mortem previu que "os cinco estados vão virar dois" — posto incorreto e
fora de escala exigem comparar a batida com a escala do dia e com o geofence, e as duas fontes
estão sujas (a escala esteve 1h errada desde julho; o Francisco Ramon sai fora_local em 100% das
batidas). Este oráculo NÃO conserta fonte: afirma que a tela diz o que a fonte diz.

O que afirma, recomputando cada item com SQL próprio (não com o módulo que a tela usa):
  1. Todo item listado tem estado em ESTADOS — nenhum sexto estado, nenhum None.
  2. Turno esperado: a primeira batida válida na janela de presença (a mesma de
     `presenca_ao_vivo`: [início−2h, fim]; noturno até D+1 07:00) decide — sem batida e
     tolerância vencida → descoberto; batida em geofence de outro posto → posto incorreto;
     batida depois de início+tolerância → atraso; senão ok. Check-in manual (`actual_start_time`)
     vale como presença, como no quadro ao vivo.
  3. `atendido_fora_de_escala` só para quem NÃO tem turno esperado hoje em posto nenhum e
     bateu hoje.
  4. Turno que ainda não venceu a tolerância NÃO está na lista (não existe "aguardando" entre
     os cinco; ele entra no contador `nao_vencidos`).
  5. A tolerância é a do banco (`geofence_zones.entry_tolerance_minutes` do posto) e, sem
     valor lá, a do quadro ao vivo (`TOLERANCIA_ATRASO`) — a mesma que a triagem vê.

Estado medido no nascimento (12/09/2026, staging): tela inexistente. `posto_descoberto` era
só um TIPO DE ALERTA (`alert_service`), não um estado de grade.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import asyncio
import math
import sys
from datetime import date, datetime, time, timedelta

ESTADOS = ("ok", "atendido_com_atraso", "atendido_posto_incorreto", "atendido_fora_de_escala", "descoberto")

#: ⭐ 29/09/2026 — ESTE ORÁCULO OBSERVAVA A COISA ERRADA, e reprovou uma tela boa.
#:
#: A verdade do horário não é `shifts` cru: quando há linha em `ponto_horario_vigencia` na data,
#: ela é o horário que vale — escrita à mão, com AUTOR e MOTIVO, porque o cadastro estava errado.
#: A CELIANE tem cadastro 08:00 e entra 09:00. Medindo pelo cru, este oráculo dizia «as fontes
#: dizem atendido_com_atraso» sobre uma pessoa que chega pontual, e acusava o mapa de divergir.
#:
#: ⚠️ Não é copiar a query do código: é expressar a REGRA do domínio de forma independente. A
#: régua mudou porque estava errada — não para o teste passar.
_SQL_TURNO = """
SELECT sh.shift_date,
       coalesce((SELECT hv.entrada FROM ponto_horario_vigencia hv
                  WHERE hv.employee_id = sh.employee_id
                    AND hv.vigencia_inicio <= sh.shift_date
                    AND (hv.vigencia_fim IS NULL OR hv.vigencia_fim >= sh.shift_date)
                  ORDER BY hv.vigencia_inicio DESC LIMIT 1),
                sh.planned_start_time) AS planned_start_time,
       coalesce((SELECT hv.saida FROM ponto_horario_vigencia hv
                  WHERE hv.employee_id = sh.employee_id
                    AND hv.vigencia_inicio <= sh.shift_date
                    AND (hv.vigencia_fim IS NULL OR hv.vigencia_fim >= sh.shift_date)
                  ORDER BY hv.vigencia_inicio DESC LIMIT 1),
                sh.planned_end_time) AS planned_end_time,
       sh.actual_start_time, sh.status,
       sh.post_id::text AS post_id, sh.employee_id::text AS employee_id
  FROM shifts sh WHERE sh.id::text = :sid
"""
_SQL_BATIDAS = """
SELECT punch_timestamp, latitude, longitude, dentro_geofence, posto_id
  FROM gp_clock_punches
 WHERE employee_id::text = :eid AND punch_timestamp >= :ini AND punch_timestamp <= :fim
   AND coalesce(status,'') <> 'facial_reprovado'
 ORDER BY punch_timestamp
"""
_SQL_POSTOS_GEO = """
SELECT id::text, latitude, longitude, geofence_raio_metros FROM posts
 WHERE is_active AND latitude IS NOT NULL AND longitude IS NOT NULL
"""
_SQL_TOLERANCIA = """
SELECT entry_tolerance_minutes FROM geofence_zones
 WHERE post_id::text = :pid AND coalesce(is_active, true) AND entry_tolerance_minutes IS NOT NULL
 ORDER BY coalesce(is_primary,false) DESC LIMIT 1
"""
_SQL_TEM_TURNO_HOJE = """
SELECT 1 FROM shifts sh WHERE sh.employee_id::text = :eid AND sh.shift_date = CAST(:dia AS date)
   AND sh.is_off_day = FALSE AND sh.status <> 'cancelled' AND sh.is_active = TRUE LIMIT 1
"""
_SQL_BATEU_HOJE = """
SELECT min(punch_timestamp) FROM gp_clock_punches
 WHERE employee_id::text = :eid AND punch_timestamp >= :ini AND punch_timestamp < :fim
   AND coalesce(status,'') <> 'facial_reprovado'
"""


_SQL_ULTIMO_DIA_COM_BATIDA = """
SELECT max(punch_timestamp::date) FROM gp_clock_punches
 WHERE punch_timestamp::date < CAST(:dia AS date) AND coalesce(status,'') <> 'facial_reprovado'
"""


def _dist_m(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def _posto_do_geofence(b, postos) -> str | None:
    if b["dentro_geofence"] is True and b["posto_id"]:
        return str(b["posto_id"])
    if b["latitude"] is None or b["longitude"] is None:
        return None
    dentro = [(_dist_m(b["latitude"], b["longitude"], p[1], p[2]), p[0]) for p in postos
              if _dist_m(b["latitude"], b["longitude"], p[1], p[2]) <= (p[3] or 150)]
    return min(dentro)[1] if dentro else None


def _janela(dia: date, ini: time, fim: time) -> tuple[datetime, datetime, datetime]:
    dt_ini = datetime.combine(dia, ini)
    dt_fim = datetime.combine(dia, fim)
    if dt_fim <= dt_ini:
        dt_fim += timedelta(days=1)
    fim_pres = datetime.combine(dia + timedelta(days=1), time(7, 0)) if ini >= time(15, 0) else dt_fim
    return dt_ini, dt_ini - timedelta(hours=2), fim_pres


async def _reproduzir(db, item, postos, tol_padrao, agora):
    """Estado que as FONTES dizem para este item, e o limite de tolerância usado.

    SQL próprio de propósito: o oráculo não chama `mapa_de_ponto.classificar` — afirmar uma
    função com ela mesma é o oráculo que nasce verde medindo a coisa errada.
    """
    from sqlalchemy import text

    sh = (await db.execute(text(_SQL_TURNO), {"sid": item["shift_id"]})).mappings().first()
    if not sh:
        return "_sem_shift", None
    dt_ini, j_ini, j_fim = _janela(sh["shift_date"], sh["planned_start_time"], sh["planned_end_time"])
    tol = (await db.execute(text(_SQL_TOLERANCIA), {"pid": sh["post_id"]})).scalar()
    limite = dt_ini + timedelta(minutes=int(tol) if tol is not None else tol_padrao)
    bats = (await db.execute(text(_SQL_BATIDAS),
                             {"eid": sh["employee_id"], "ini": j_ini, "fim": j_fim})).mappings().all()
    b = bats[0] if bats else None
    if b is None and sh["actual_start_time"] is not None:
        return ("atendido_com_atraso" if sh["actual_start_time"] > limite else "ok"), limite
    if b is None:
        return ("descoberto" if (agora >= limite or sh["status"] == "missed") else None), limite
    pg = _posto_do_geofence(b, postos)
    if pg and pg != sh["post_id"]:
        return "atendido_posto_incorreto", limite
    return ("atendido_com_atraso" if b["punch_timestamp"] > limite else "ok"), limite


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db
    from modules.operacional.presence.controllers.presence_controller import TOLERANCIA_ATRASO

    gen = get_db()
    db = await gen.__anext__()
    try:
        from modules.operacional.controllers.redesign_data_controller import BUILDERS

        telas = await BUILDERS["operacional"](db)
        mapa = telas["mapa-de-ponto"]
        meta = mapa["_meta"]
    except Exception as exc:  # noqa: BLE001 — a tela não existir É o vermelho
        print(f"FALHOU: mapa-de-ponto não existe no builder do operacional: {type(exc).__name__}: {exc}")
        raise AssertionError("o mapa de ponto com os 5 estados não existe") from exc

    falhas: list[str] = []
    agora = datetime.fromisoformat(meta["agora"])
    dia = date.fromisoformat(meta["dia"])
    postos = (await db.execute(text(_SQL_POSTOS_GEO))).all()
    tol_padrao = int(TOLERANCIA_ATRASO.total_seconds() // 60)

    # 1) nenhum estado fora dos cinco nas LINHAS da tela (o que o supervisor vê). A linha
    #    única de "nenhum turno" não tem badge e é legítima — só quando NÃO há nada a listar.
    rotulos = {e.replace("_", " ") for e in ESTADOS}
    listados = [i for i in meta["itens"] if i.get("estado") is not None] + meta.get("fora_de_escala", [])
    if listados:
        for row in mapa.get("rows", []):
            badge = next((c for c in row["cells"] if c.get("isBadge")), None)
            if not badge or badge["v"] not in rotulos:
                falhas.append(f"linha da tela sem um dos 5 estados: {badge and badge['v']!r}")
    elif len(mapa.get("rows", [])) != 1:
        falhas.append(f"sem itens a listar e a tela tem {len(mapa.get('rows', []))} linha(s)")

    # 2) turnos esperados: reproduzir o estado a partir de shifts × gp_clock_punches × posts
    for i in [x for x in listados if x.get("shift_id")]:
        if i["estado"] not in ESTADOS:
            falhas.append(f"{i['nome']}: estado '{i['estado']}' não é um dos cinco")
            continue
        esperado, limite = await _reproduzir(db, i, postos, tol_padrao, agora)
        if esperado == "_sem_shift":
            falhas.append(f"{i['nome']}: shift {i['shift_id'][:8]} não existe em `shifts`")
        elif esperado is None:
            falhas.append(f"{i['nome']} ({i['posto']} {i['turno']}): a tolerância ainda não venceu às "
                          f"{agora:%H:%M} e a tela já lista '{i['estado']}'")
        elif esperado != i["estado"]:
            falhas.append(f"{i['nome']} ({i['posto']} {i['turno']}): tela diz '{i['estado']}', as fontes dizem "
                          f"'{esperado}' (limite {limite:%H:%M})")

    # 3) fora de escala: sem turno hoje em posto nenhum, e bateu hoje
    ini_dia, fim_dia = datetime.combine(dia, time.min), datetime.combine(dia + timedelta(days=1), time(7, 0))
    for i in meta.get("fora_de_escala", []):
        if i.get("estado") != "atendido_fora_de_escala":
            falhas.append(f"{i['nome']}: item de fora de escala com estado '{i.get('estado')}'")
        if (await db.execute(text(_SQL_TEM_TURNO_HOJE), {"eid": i["employee_id"], "dia": dia})).first():
            falhas.append(f"{i['nome']} está como 'fora de escala' mas TEM turno hoje em `shifts`")
        if (await db.execute(text(_SQL_BATEU_HOJE), {"eid": i["employee_id"], "ini": ini_dia, "fim": fim_dia})).scalar() is None:
            falhas.append(f"{i['nome']} está como 'fora de escala' e não tem batida hoje")

    # 4) quem ainda não venceu não está listado (contador existe e bate)
    nao_vencidos = [i for i in meta["itens"] if i.get("estado") is None]
    if meta.get("nao_vencidos") != len(nao_vencidos):
        falhas.append(f"contador nao_vencidos={meta.get('nao_vencidos')} e há {len(nao_vencidos)} turno(s) sem estado")

    contagem = {e: sum(1 for i in listados if i["estado"] == e) for e in ESTADOS}

    # 5) UM DIA FECHADO, sempre. Rodando de madrugada, o dia de hoje ainda não venceu nenhum
    #    turno e os quatro passos acima passariam sobre uma lista VAZIA — verde por ausência de
    #    medição é a doença que esta casa já pagou. Então o oráculo também reproduz o dia
    #    anterior, já fechado, e confere cada estado contra as fontes.
    from modules.people_management.ponto import mapa_de_ponto as regua

    # O dia fechado é o último com BATIDA, não simplesmente ontem: num ambiente cujo acervo
    # parou há dois dias, "ontem" só produz descoberto e os outros quatro estados nunca são
    # exercitados — o oráculo passaria sem nunca ter comparado uma batida com a escala.
    fechado = (await db.execute(text(_SQL_ULTIMO_DIA_COM_BATIDA), {"dia": dia})).scalar() or (dia - timedelta(days=1))
    depois = datetime.combine(fechado + timedelta(days=1), time(12, 0))
    m_ontem = await regua.mapa_do_dia(db, dia=fechado, agora=depois)
    itens_ontem = [i for i in m_ontem["itens"] if i.get("estado")]
    for i in itens_ontem:
        esperado, _lim = await _reproduzir(db, i, postos, tol_padrao, depois)
        if esperado != i["estado"]:
            falhas.append(f"[{fechado:%d/%m}] {i['nome']} ({i['posto']} {i['turno']}): a régua diz "
                          f"'{i['estado']}', as fontes dizem '{esperado}'")
    if not itens_ontem and not listados:
        falhas.append(f"nada medido: nem hoje ({dia:%d/%m}) nem o dia fechado ({fechado:%d/%m}) têm "
                      f"turno com estado — o oráculo não afirmou nada")
    cont_ontem = {e: sum(1 for i in itens_ontem if i["estado"] == e) for e in ESTADOS}
    cont_ontem["atendido_fora_de_escala"] = len(m_ontem.get("fora_de_escala", []))

    print(f"mapa {dia:%d/%m} às {agora:%H:%M} · " + " · ".join(f"{k}={v}" for k, v in contagem.items())
          + f" · ainda não venceram={len(nao_vencidos)}")
    print(f"dia fechado {fechado:%d/%m} · " + " · ".join(f"{k}={v}" for k, v in cont_ontem.items()))
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) entre o mapa de ponto e as fontes")
    print("OK mapa de ponto: só os cinco estados, e cada um se reproduz de shifts × batidas × geofence")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
