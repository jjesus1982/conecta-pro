"""Painel do Ponto — LINK PÚBLICO (token) pro Jordan acompanhar o rollout no celular.

Sem login: `/painel-ponto?token=…`. Mostra ao vivo quem cadastrou (primeiro acesso),
quem tem rosto, quem bateu hoje e quem falta. Só dados operacionais (nome/posto/status) —
nada sensível (sem CPF/salário). Token fixo (env PAINEL_PONTO_TOKEN) — só quem tem o link vê.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database.session import get_sync_db_dependency
from modules.people_management.ponto.coorte_ponto import (
    APRENDIZADO_DESDE,
    HORAS_ENTRE_TURNOS,
    SQL_NAO_AUSENTE_HOJE,
    SQL_PADRAO_BATIDAS,
    SQL_ULTIMO_TURNO,
    TOLERANCIA_ENTRADA_MIN,
    folga_hoje,
    horario_entrada,
    montar_aprendizado,
)

router = APIRouter(prefix="/painel-ponto", tags=["Painel Ponto (público, token)"])

_TOKEN = os.environ.get("PAINEL_PONTO_TOKEN", "ponto-live-2026-a7f3k9d2")
# Só batidas pelo CONECTA PRO (rollout). Sólides/Tangerino continuam sendo puxados
# (ponto oficial na transição), mas NÃO entram neste acompanhamento.
_CONECTA = "coalesce(device_type,'') NOT IN ('tangerino','web')"
_COHORT = (
    "e.status='ativo' AND coalesce(e.is_homologacao,false)=false "
    "AND (e.tipo_contrato='clt' OR e.tipo_contrato IS NULL) AND (e.tipo_contrato IS DISTINCT FROM 'pj')"
    # Quem está de férias ou afastado não deve ponto — cobrar essa gente polui o painel
    # e o fechamento. Regra por data, compartilhada com o lembrete (uma fonte só).
    + SQL_NAO_AUSENTE_HOJE
)


@router.get("")
def painel(
    token: str = Query(...),
    db: Session = Depends(get_sync_db_dependency),
) -> dict[str, Any]:
    """Painel ao vivo (público por token). Fatos no banco, nunca estimado."""
    if token != _TOKEN:
        raise HTTPException(status_code=403, detail="Link inválido.")

    hoje = "(now() AT TIME ZONE 'America/Manaus')::date"
    rows = (
        db.execute(
            text(
                f"SELECT e.nome, e.posto_atual_nome AS posto, "
                f"  (e.face_descriptor IS NOT NULL) AS com_rosto, "
                # Ativado = consegue usar o ponto novo. Rosto cadastrado pelo DP (enroll oficial)
                # não passa pelo primeiro acesso e não preenche primeiro_acesso_em — a pessoa
                # está pronta e o painel a chamava de pendente. Graciene, contada como pendente,
                # já tinha batido ponto pelo Conecta PRO.
                f"  (e.primeiro_acesso_em IS NOT NULL OR e.face_descriptor IS NOT NULL) AS ativado, "
                f"  to_char(e.primeiro_acesso_em, 'DD/MM HH24:MI') AS ativado_em, "
                f"  coalesce(b.n, 0) AS num_batidas, b.ultima AS ultima_batida, "
                f"  coalesce(e.cargo,'') AS cargo, coalesce(e.turno_padrao,'') AS turno, "
                f"  coalesce(e.escala_padrao,'') AS escala, "
                f"  ({hoje} - ult.ultimo_turno) AS dias_desde_turno "
                f"FROM employees e "
                f"LEFT JOIN ( "
                f"  SELECT employee_id, count(*) AS n, to_char(max(punch_timestamp), 'HH24:MI') AS ultima "
                f"  FROM gp_clock_punches WHERE punch_timestamp::date = {hoje} AND {_CONECTA} GROUP BY employee_id "
                f") b ON b.employee_id = e.id "
                f"{SQL_ULTIMO_TURNO} "
                f"WHERE {_COHORT} ORDER BY e.nome"
            )
        )
        .mappings()
        .all()
    )

    funcionarios = []
    agora_hhmm, dia_semana, iso_week = db.execute(text(
        "SELECT to_char(now() AT TIME ZONE 'America/Manaus','HH24:MI'), "
        "       extract(dow from (now() AT TIME ZONE 'America/Manaus'))::int, "
        "       extract(week from (now() AT TIME ZONE 'America/Manaus'))::int"
    )).first()

    n_ativados = n_rosto = n_bateu = 0
    for r in rows:
        bateu = int(r["num_batidas"]) > 0
        n_ativados += 1 if r["ativado"] else 0
        n_rosto += 1 if r["com_rosto"] else 0
        n_bateu += 1 if bateu else 0
        funcionarios.append(
            {
                "nome": r["nome"],
                "posto": r["posto"],
                "ativado": bool(r["ativado"]),
                "ativado_em": r["ativado_em"],
                "com_rosto": bool(r["com_rosto"]),
                "bateu_hoje": bateu,
                "num_batidas": int(r["num_batidas"]),
                "ultima_batida": r["ultima_batida"],
                "cargo": r["cargo"],
                "turno": r["turno"],
                "escala": r["escala"],
                "dias_desde_turno": r["dias_desde_turno"],
            }
        )

    # ── ATRASO — só afirmável para quem tem horário conhecido ────────────────
    # `horario_entrada` devolve None quando o posto não tem aquele turno parametrizado, e
    # None NÃO vira atraso: a pessoa entra em `sem_horario`. Concluir atraso sem saber a
    # hora foi o que me fez apontar quatro pessoas erradas em 14/08.
    hh, mm = [int(x) for x in (agora_hhmm or "00:00").split(":")[:2]]
    agora_min = hh * 60 + mm
    atrasados, sem_horario, de_folga = [], [], []
    for f in funcionarios:
        if f["bateu_hoje"]:
            continue
        # 12x36 que começou turno ONTEM está de folga hoje. Sem isto o painel chamou de
        # atrasadas 11 das 15 pessoas em 14/08 às 09:26 — gente que não tinha que estar lá.
        if folga_hoje(f.get("escala") or "", f.get("dias_desde_turno")):
            de_folga.append(f["nome"])
            continue
        # `iso_week` decide o revezamento de fim de semana do Michelangelo. Omitir o
        # argumento o deixava em 0, e (0 - 33) % 2 = 1 INVERTIA a escala: no sábado o painel
        # cobraria o artífice que está de folga e daria o escalado como ausente.
        ent = horario_entrada(f["nome"], f.get("posto") or "", f.get("cargo") or "",
                              f.get("turno") or "", dia_semana, iso_week)
        f["entrada_prevista"] = ent
        if not ent:
            sem_horario.append(f["nome"])
            continue
        eh, em_ = [int(x) for x in ent.split(":")]
        limite = eh * 60 + em_ + TOLERANCIA_ENTRADA_MIN
        # turno noturno cruza a meia-noite: às 07:00 ninguém está atrasado para as 18:00
        if agora_min > limite and (eh <= 13 or agora_min >= eh * 60):
            f["atraso_min"] = agora_min - (eh * 60 + em_)
            atrasados.append(f)

    b = (
        db.execute(
            text(
                f"SELECT count(*) AS total, count(DISTINCT employee_id) AS pessoas, "
                f"  count(*) FILTER (WHERE status='pending_contingencia') AS validar "
                f"FROM gp_clock_punches WHERE punch_timestamp::date = {hoje} AND {_CONECTA} "
                f"  AND employee_id IN (SELECT id FROM employees e WHERE {_COHORT})"
            )
        )
        .mappings()
        .first()
    )

    feed = (
        db.execute(
            text(
                f"SELECT e.nome, p.punch_type, p.device_type, p.status, to_char(p.punch_timestamp,'HH24:MI') AS hora "
                f"FROM gp_clock_punches p JOIN employees e ON e.id=p.employee_id "
                f"WHERE p.punch_timestamp::date = {hoje} AND coalesce(p.device_type,'') NOT IN ('tangerino','web') "
                f"  AND p.employee_id IN (SELECT id FROM employees e2 WHERE "
                + _COHORT.replace("e.", "e2.")
                + ") ORDER BY p.punch_timestamp DESC LIMIT 20"
            )
        )
        .mappings()
        .all()
    )

    # Padrão aprendido: a MESMA regra que o monitor do DP usa — mora em
    # `ponto/coorte_ponto.py`, junto da coorte, porque três superfícies precisam da mesma
    # resposta e três cópias viram três verdades.
    padrao = db.execute(
        text(SQL_PADRAO_BATIDAS.format(coorte=_COHORT)),
        {"desde": APRENDIZADO_DESDE, "horas_turno": HORAS_ENTRE_TURNOS},
    ).mappings().all()
    aprendizado = montar_aprendizado(padrao)

    agora = db.execute(text("SELECT to_char(now() AT TIME ZONE 'America/Manaus', 'HH24:MI:SS')")).scalar()
    total = len(funcionarios)
    return {
        "resumo": {
            "total": total,
            "ativados": n_ativados,
            "com_rosto": n_rosto,
            "pendentes": total - n_ativados,
            "bateram_hoje": n_bateu,
            "atrasados": len(atrasados),
            "sem_horario_parametrizado": len(sem_horario),
            "de_folga": len(de_folga),
            "batidas_hoje": int(b["total"]),
            "contingencias_validar": int(b["validar"]),
        },
        "funcionarios": funcionarios,
        "feed": [dict(x) for x in feed],
        "atrasados": [
            {"nome": a["nome"], "posto": a["posto"], "entrada_prevista": a["entrada_prevista"],
             "atraso_min": a["atraso_min"]}
            for a in sorted(atrasados, key=lambda x: -x["atraso_min"])
        ],
        "sem_horario_parametrizado": sem_horario,
        "de_folga": de_folga,
        "aprendizado": aprendizado,
        "alertas": aprendizado["alertas"],
        "atualizado_em": agora,
    }
