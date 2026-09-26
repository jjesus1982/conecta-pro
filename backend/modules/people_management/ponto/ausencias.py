"""Dashboard de ausências — por mês, por condomínio, com a MESMA régua do mapa de ponto.

DGX F7 (24/09/2026). A DGX tem `/frontend/DashboardAusencias` (início, término, colaboradores,
eventos, contratos). Aqui: turnos planejados, trabalhados, faltas (turno sem batida), atrasos,
justificativas, afastados (`sst_afastamentos`) e férias (`hr_vacation_requests`), por cliente,
mais "faltas por período" por colaborador.

Não há SQL de contagem próprio para turno/falta/atraso: os turnos vêm de `mapa_de_ponto._carregar`
e cada estado de `mapa_de_ponto.classificar` — é o que a frente 04 chamou de régua única. O oráculo
`test_oraculo_ponto_configuravel.py` (e) reconta o bruto por SQL próprio e confere.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text

from modules.people_management.ponto import mapa_de_ponto as regua

_SQL_LANCADOS = """
SELECT count(*) FROM shifts sh
 WHERE sh.shift_date BETWEEN CAST(:de AS date) AND CAST(:ate AS date) AND sh.employee_id IS NOT NULL
   AND sh.is_off_day = FALSE AND sh.status <> 'cancelled' AND sh.is_active = TRUE
"""
_SQL_JUSTIFICADAS = """
SELECT coalesce(c.name, '—') AS cliente, count(*) AS n
  FROM gp_justifications j
  JOIN employees e ON e.id::text = j.employee_id
  LEFT JOIN clients c ON c.id = e.cliente_id
 -- ⚠️ 25/09/2026: era `j.created_at`, que é quando a justificativa foi DIGITADA, não quando o
 -- fato ocorreu. Justificativa lançada hoje para uma falta da semana passada caía no mês errado,
 -- e por isso "justificadas" nunca fechava com "faltas". `data_fato` é o dia a que ela se refere;
 -- `created_at` fica como degrau para as linhas antigas que não têm a data.
 WHERE coalesce(j.data_fato, j.created_at::date) >= CAST(:de AS date)
   AND coalesce(j.data_fato, j.created_at::date) <= CAST(:ate AS date)
 GROUP BY 1
"""
_SQL_AFASTADOS = """
SELECT coalesce(c.name, '—') AS cliente, count(DISTINCT a.employee_id) AS n
  FROM sst_afastamentos a
  JOIN employees e ON e.id = a.employee_id
  LEFT JOIN clients c ON c.id = e.cliente_id
 WHERE a.data_inicio <= CAST(:ate AS date)
   AND coalesce(a.data_retorno, a.data_fim_prevista, CAST(:ate AS date)) >= CAST(:de AS date)
 GROUP BY 1
"""
_SQL_FERIAS = """
SELECT coalesce(c.name, '—') AS cliente, count(DISTINCT v.employee_id) AS n
  FROM hr_vacation_requests v
  JOIN employees e ON e.id = v.employee_id
  LEFT JOIN clients c ON c.id = e.cliente_id
 WHERE upper(coalesce(v.status, '')) = 'APPROVED'
   AND v.start_date <= CAST(:ate AS date) AND v.end_date >= CAST(:de AS date)
 GROUP BY 1
"""

_VAZIO = {
    "planejados": 0,
    "trabalhados": 0,
    "faltas": 0,
    "atrasos": 0,
    "posto_incorreto": 0,
    "pendentes": 0,
    "justificadas": 0,
    "afastados": 0,
    "ferias": 0,
}


async def ausencias_do_mes(db, ano: int, mes: int, agora=None) -> dict:
    agora = agora or regua.agora_manaus()
    de = date(ano, mes, 1)
    ate = date(ano + (mes == 12), mes % 12 + 1, 1) - timedelta(days=1)
    turnos, batidas, _geo, tol, regras = await regua._carregar(db, de, ate)

    por_cliente: dict[str, dict] = {}
    por_pessoa: dict[str, dict] = {}
    for t in turnos:
        c = por_cliente.setdefault(t["cliente"], dict(_VAZIO))
        c["planejados"] += 1
        if t["shift_date"] > agora.date():
            c["pendentes"] += 1
            continue
        estado, _b = regua.classificar(t, batidas.get(t["employee_id"], []), regua._tolerancia(tol, t, regras), agora)
        if estado is None:
            c["pendentes"] += 1
            continue
        p = por_pessoa.setdefault(
            t["employee_id"], {"nome": t["nome"], "cliente": t["cliente"], "turnos": 0, "faltas": 0, "atrasos": 0}
        )
        p["turnos"] += 1
        if estado == "descoberto":
            c["faltas"] += 1
            p["faltas"] += 1
        else:
            c["trabalhados"] += 1
            if estado == "atendido_com_atraso":
                c["atrasos"] += 1
                p["atrasos"] += 1
            elif estado == "atendido_posto_incorreto":
                c["posto_incorreto"] += 1

    params = {"de": de, "ate": ate}
    for chave, sql in (("justificadas", _SQL_JUSTIFICADAS), ("afastados", _SQL_AFASTADOS), ("ferias", _SQL_FERIAS)):
        for r in (await db.execute(text(sql), params)).all():
            por_cliente.setdefault(r[0], dict(_VAZIO))[chave] = int(r[1])
    lancados = int((await db.execute(text(_SQL_LANCADOS), params)).scalar() or 0)
    return {
        "ano": ano,
        "mes": mes,
        "de": de.isoformat(),
        "ate": ate.isoformat(),
        "hoje": agora.date().isoformat(),
        "lancados": lancados,
        "planejados": len(turnos),
        "por_cliente": dict(sorted(por_cliente.items())),
        "por_pessoa": sorted(por_pessoa.values(), key=lambda p: (-p["faltas"], -p["atrasos"], p["nome"])),
    }
