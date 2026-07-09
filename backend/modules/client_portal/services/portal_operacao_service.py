"""Portal do Cliente — Raio-X da Operação.

Dá ao condomínio total transparência sobre as PESSOAS e a OPERAÇÃO da Conecta Mais
alocadas nele: equipe, assiduidade (ponto), atestados (ASO), turnover, ranking
(derivado do ponto), escalas e advertências.

Escopo: ged_clients.id → (CNPJ) clients.id → condominios.nome → posts (match por nome,
com fallback) → allocations(active) → employees. O conjunto de employee_ids alimenta
ponto (gp_clock_punches), ASO (gp_asos) e turnover (employees).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# fallback p/ condomínios cujo nome não casa direto com o nome do posto
ALIAS_POSTO = {
    "PARQUE RESIDENCIAL GELAIN": "gelain",
    "VILLA DOS PASSAROS": "passaro",
    "VILLA PASSAROS": "passaro",
    "PARISE": "parise",
    "GREEN HILLS": "green",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9 ]", " ", s).strip()


async def _resolver(db: AsyncSession, client_id: str) -> dict:
    """Resolve o condomínio do cliente do portal → posts + employee_ids + nome."""
    row = (
        await db.execute(
            text(
                """SELECT g.name AS ged_nome, g.cnpj,
                          c.id AS cliente_id, cond.id AS cond_id, cond.nome AS cond_nome
                   FROM ged_clients g
                   LEFT JOIN clients c ON regexp_replace(c.document_number,'[^0-9]','','g')
                                        = regexp_replace(COALESCE(g.cnpj,''),'[^0-9]','','g')
                                        AND g.cnpj IS NOT NULL
                   LEFT JOIN condominios cond ON cond.client_id = c.id
                   WHERE g.id = :cid"""
            ),
            {"cid": client_id},
        )
    ).mappings().first()
    if not row:
        return {"cond_nome": None, "cliente_id": None, "post_ids": [], "employee_ids": []}

    cond_nome = row["cond_nome"] or row["ged_nome"]
    cliente_id = row["cliente_id"]
    # tokens significativos do nome do condomínio (>3 chars, sem genéricos)
    GENERICOS = {"CONDOMINIO", "RESIDENCIAL", "VILLAGE", "VILLA", "EDIFICIO", "DA", "DE", "DO", "DOS", "DAS", "CIDADE"}
    toks = [t for t in _norm(cond_nome).split() if len(t) > 3 and t not in GENERICOS]
    alias = ALIAS_POSTO.get(_norm(cond_nome))

    # busca posts por client_id (raro) OU por token no nome do posto OU alias
    posts = (await db.execute(text("SELECT id, name, code FROM posts"))).mappings().all()
    post_ids = []
    for p in posts:
        pn = _norm(p["name"])
        if cliente_id and str(p.get("client_id") or "") == str(cliente_id):
            post_ids.append(str(p["id"]))
        elif alias and alias.upper() in pn:
            post_ids.append(str(p["id"]))
        elif any(t in pn for t in toks):
            post_ids.append(str(p["id"]))
    post_ids = list(dict.fromkeys(post_ids))

    employee_ids: list[str] = []
    if post_ids:
        rows = (
            await db.execute(
                text(
                    "SELECT DISTINCT a.employee_id FROM allocations a "
                    "WHERE a.post_id = ANY(:pids) AND a.status='active'"
                ),
                {"pids": post_ids},
            )
        ).fetchall()
        employee_ids = [str(r[0]) for r in rows]
    return {"cond_nome": cond_nome, "cliente_id": str(cliente_id) if cliente_id else None,
            "post_ids": post_ids, "employee_ids": employee_ids}


async def equipe(db: AsyncSession, client_id: str) -> dict:
    """Equipe da Conecta Mais alocada no condomínio (ficha resumida)."""
    ctx = await _resolver(db, client_id)
    if not ctx["post_ids"]:
        return {"condominio": ctx["cond_nome"], "total": 0, "equipe": []}
    rows = (
        await db.execute(
            text(
                """SELECT DISTINCT e.id, e.nome, e.cargo, a.role, e.data_admissao, e.status
                   FROM allocations a JOIN employees e ON e.id = a.employee_id
                   WHERE a.post_id = ANY(:pids) AND a.status='active'
                   ORDER BY e.cargo, e.nome"""
            ),
            {"pids": ctx["post_ids"]},
        )
    ).mappings().all()
    hoje = date.today()
    equipe = []
    for r in rows:
        adm = r["data_admissao"]
        meses = ((hoje.year - adm.year) * 12 + hoje.month - adm.month) if adm else None
        equipe.append(
            {
                "id": str(r["id"]),
                "nome": r["nome"],
                "funcao": r["role"] or r["cargo"],
                "cargo": r["cargo"],
                "admissao": str(adm) if adm else None,
                "tempo_casa_meses": meses,
                "status": r["status"],
            }
        )
    return {"condominio": ctx["cond_nome"], "total": len(equipe), "equipe": equipe}


async def assiduidade(db: AsyncSession, client_id: str, competencia: str | None = None) -> dict:
    """Assiduidade do mês: dias presentes, % no local (geofence), pontos batidos."""
    ctx = await _resolver(db, client_id)
    if not ctx["employee_ids"]:
        return {"condominio": ctx["cond_nome"], "mes": competencia, "funcionarios": [], "resumo": {}}
    if competencia:
        ini = date(int(competencia.split("-")[0]), int(competencia.split("-")[1]), 1)
    else:
        ini = date.today().replace(day=1)
    rows = (
        await db.execute(
            text(
                """SELECT e.nome,
                          COUNT(DISTINCT gc.punch_timestamp::date) AS dias,
                          COUNT(*) AS batidas,
                          COUNT(*) FILTER (WHERE gc.dentro_geofence)::float / NULLIF(COUNT(*),0) AS pct_local,
                          COUNT(*) FILTER (WHERE gc.facial_match)::float / NULLIF(COUNT(*),0)   AS pct_facial
                   FROM gp_clock_punches gc JOIN employees e ON e.id = gc.employee_id
                   WHERE gc.employee_id::text = ANY(:eids) AND gc.punch_timestamp >= :ini
                   GROUP BY e.nome ORDER BY dias DESC"""
            ),
            {"eids": ctx["employee_ids"], "ini": ini},
        )
    ).mappings().all()
    func = [
        {
            "nome": r["nome"],
            "dias_presentes": r["dias"],
            "batidas": r["batidas"],
            "pct_no_local": round((r["pct_local"] or 0) * 100),
            "pct_facial_ok": round((r["pct_facial"] or 0) * 100),
        }
        for r in rows
    ]
    total_dias = sum(f["dias_presentes"] for f in func)
    return {
        "condominio": ctx["cond_nome"],
        "mes": competencia or ini.strftime("%Y-%m"),
        "funcionarios": func,
        "resumo": {
            "funcionarios_com_ponto": len(func),
            "dias_presenca_total": total_dias,
            "pct_no_local_medio": round(sum(f["pct_no_local"] for f in func) / len(func)) if func else 0,
        },
    }


async def ranking(db: AsyncSession, client_id: str) -> dict:
    """Ranking dos funcionários derivado do ponto (assiduidade + presença no local + facial)."""
    a = await assiduidade(db, client_id)
    pessoas = a["funcionarios"]
    for p in pessoas:
        # score: dias (peso 3) + % no local (peso 1) + % facial (peso 1), normalizado simples
        p["score"] = round(p["dias_presentes"] * 3 + p["pct_no_local"] * 0.5 + p["pct_facial_ok"] * 0.5)
    pessoas = sorted(pessoas, key=lambda x: x["score"], reverse=True)
    for i, p in enumerate(pessoas):
        p["posicao"] = i + 1
    return {"condominio": a["condominio"], "ranking": pessoas, "criterio": "Assiduidade + presença no local + reconhecimento facial"}


async def atestados(db: AsyncSession, client_id: str) -> dict:
    """ASOs (saúde ocupacional) da equipe — validade e aptidão."""
    ctx = await _resolver(db, client_id)
    if not ctx["employee_ids"]:
        return {"condominio": ctx["cond_nome"], "asos": [], "resumo": {}}
    rows = (
        await db.execute(
            text(
                """SELECT e.nome, a.tipo, a.status, a.data_realizacao, a.data_validade, a.apto
                   FROM gp_asos a JOIN employees e ON e.id = a.employee_id
                   WHERE a.employee_id::text = ANY(:eids) ORDER BY a.data_validade NULLS LAST"""
            ),
            {"eids": ctx["employee_ids"]},
        )
    ).mappings().all()
    hoje = date.today()
    asos = []
    vencidos = 0
    for r in rows:
        venc = r["data_validade"]
        vencido = bool(venc and venc < hoje)
        vencidos += 1 if vencido else 0
        asos.append(
            {
                "funcionario": r["nome"],
                "tipo": r["tipo"],
                "status": r["status"],
                "realizado": str(r["data_realizacao"]) if r["data_realizacao"] else None,
                "validade": str(venc) if venc else None,
                "apto": r["apto"],
                "vencido": vencido,
            }
        )
    return {"condominio": ctx["cond_nome"], "asos": asos, "resumo": {"total": len(asos), "vencidos": vencidos}}


async def turnover(db: AsyncSession, client_id: str, meses: int = 12) -> dict:
    """Rotatividade: admissões/demissões da equipe no período + headcount atual."""
    ctx = await _resolver(db, client_id)
    if not ctx["post_ids"]:
        return {"condominio": ctx["cond_nome"], "resumo": {}, "movimentacoes": []}
    r = (
        await db.execute(
            text(
                """SELECT
                     COUNT(*) FILTER (WHERE e.status='ativo') AS ativos,
                     COUNT(*) FILTER (WHERE e.data_admissao >= (CURRENT_DATE - make_interval(months => :m))) AS admissoes,
                     COUNT(*) FILTER (WHERE e.data_demissao >= (CURRENT_DATE - make_interval(months => :m))) AS demissoes
                   FROM (SELECT DISTINCT a.employee_id FROM allocations a WHERE a.post_id = ANY(:pids)) al
                   JOIN employees e ON e.id = al.employee_id"""
            ),
            {"pids": ctx["post_ids"], "m": meses},
        )
    ).mappings().first()
    mov = (
        await db.execute(
            text(
                """SELECT e.nome, e.cargo, e.data_admissao, e.data_demissao, e.status
                   FROM (SELECT DISTINCT a.employee_id FROM allocations a WHERE a.post_id = ANY(:pids)) al
                   JOIN employees e ON e.id = al.employee_id
                   WHERE e.data_demissao IS NOT NULL OR e.data_admissao >= (CURRENT_DATE - make_interval(months => :m))
                   ORDER BY COALESCE(e.data_demissao, e.data_admissao) DESC"""
            ),
            {"pids": ctx["post_ids"], "m": meses},
        )
    ).mappings().all()
    ativos = r["ativos"] or 0
    adm, dem = r["admissoes"] or 0, r["demissoes"] or 0
    taxa = round(((adm + dem) / 2) / ativos * 100, 1) if ativos else 0.0
    return {
        "condominio": ctx["cond_nome"],
        "resumo": {"ativos": ativos, "admissoes": adm, "demissoes": dem, "taxa_turnover_pct": taxa, "periodo_meses": meses},
        "movimentacoes": [
            {
                "nome": m["nome"],
                "cargo": m["cargo"],
                "admissao": str(m["data_admissao"]) if m["data_admissao"] else None,
                "demissao": str(m["data_demissao"]) if m["data_demissao"] else None,
                "status": m["status"],
            }
            for m in mov
        ],
    }


async def advertencias(db: AsyncSession, client_id: str) -> dict:
    """Medidas disciplinares aplicadas pela Conecta Mais (transparência). Vazio até o DP registrar."""
    ctx = await _resolver(db, client_id)
    out = []
    if ctx["cliente_id"]:
        rows = (
            await db.execute(
                text(
                    """SELECT employee_name, action_type, reason_category, incident_date, status
                       FROM disciplinary_actions
                       WHERE (client_id = :cid OR post_id = ANY(:pids)) AND COALESCE(is_active,true)=true
                       ORDER BY incident_date DESC"""
                ),
                {"cid": ctx["cliente_id"], "pids": ctx["post_ids"] or [""]},
            )
        ).mappings().all()
        out = [
            {
                "funcionario": r["employee_name"],
                "tipo": r["action_type"],
                "motivo": r["reason_category"],
                "data": str(r["incident_date"]) if r["incident_date"] else None,
                "status": r["status"],
            }
            for r in rows
        ]
    return {"condominio": ctx["cond_nome"], "advertencias": out, "total": len(out)}


async def escalas(db: AsyncSession, client_id: str, competencia: str | None = None) -> dict:
    """Escala/turnos publicados do posto (quando existirem) + horário padrão como fallback."""
    ctx = await _resolver(db, client_id)
    if not ctx["post_ids"]:
        return {"condominio": ctx["cond_nome"], "tem_escala": False, "turnos": [], "padrao": None}
    turnos = (
        await db.execute(
            text(
                """SELECT sh.shift_date, sh.planned_start_time, sh.planned_end_time, sh.status,
                          sh.is_night_shift, e.nome AS funcionario
                   FROM scales s JOIN shifts sh ON sh.scale_id = s.id
                   LEFT JOIN employees e ON e.id = sh.employee_id
                   WHERE s.post_id = ANY(:pids)
                   ORDER BY sh.shift_date LIMIT 200"""
            ),
            {"pids": ctx["post_ids"]},
        )
    ).mappings().all()
    padrao = (
        await db.execute(
            text("SELECT name, shift_type, shift_start_time, shift_end_time FROM posts WHERE id = ANY(:pids)"),
            {"pids": ctx["post_ids"]},
        )
    ).mappings().all()
    return {
        "condominio": ctx["cond_nome"],
        "tem_escala": len(turnos) > 0,
        "turnos": [
            {
                "data": str(t["shift_date"]),
                "inicio": str(t["planned_start_time"]) if t["planned_start_time"] else None,
                "fim": str(t["planned_end_time"]) if t["planned_end_time"] else None,
                "noturno": t["is_night_shift"],
                "status": t["status"],
                "funcionario": t["funcionario"],
            }
            for t in turnos
        ],
        "padrao": [
            {"posto": p["name"], "turno": p["shift_type"], "inicio": str(p["shift_start_time"]) if p["shift_start_time"] else None,
             "fim": str(p["shift_end_time"]) if p["shift_end_time"] else None}
            for p in padrao
        ],
    }


async def resumo(db: AsyncSession, client_id: str) -> dict:
    """Visão consolidada (cards do topo do Raio-X)."""
    eq = await equipe(db, client_id)
    asos = await atestados(db, client_id)
    tov = await turnover(db, client_id)
    assi = await assiduidade(db, client_id)
    return {
        "condominio": eq["condominio"],
        "equipe_total": eq["total"],
        "asos_vencidos": asos["resumo"].get("vencidos", 0),
        "turnover_pct": tov["resumo"].get("taxa_turnover_pct", 0),
        "assiduidade_local_pct": assi["resumo"].get("pct_no_local_medio", 0),
        "admissoes_12m": tov["resumo"].get("admissoes", 0),
        "demissoes_12m": tov["resumo"].get("demissoes", 0),
    }


async def ocorrencias(db: AsyncSession, client_id: str) -> dict:
    """Ocorrências NÃO-SENSÍVEIS do condomínio (allowlist dupla; sem pessoa/texto livre).

    Segurança (auditoria 2026-07-08): expõe SOMENTE incidentes/manutenção/elogios de
    natureza operacional dos postos do próprio cliente. NUNCA disciplinar/conduta/
    assiduidade, NUNCA employee/inspetor/descrição/testemunhas/anexos/notas.
    """
    ctx = await _resolver(db, client_id)
    if not ctx.get("post_ids"):
        return {"condominio": ctx.get("cond_nome"), "total": 0, "ocorrencias": []}

    rows = (
        await db.execute(
            text(
                """
                SELECT o.code, lower(trim(o.occurrence_type)) AS tipo,
                       lower(trim(o.severity)) AS severidade,
                       lower(trim(o.status)) AS status,
                       o.occurred_at, o.resolved_at, p.name AS posto
                FROM occurrences o
                JOIN posts p ON p.id = o.post_id
                WHERE o.post_id = ANY(CAST(:pids AS uuid[]))
                  AND COALESCE(o.is_active, true) = true
                  AND lower(trim(o.category)) IN ('operacional', 'seguranca_trabalho', 'outros')
                  AND lower(trim(o.occurrence_type)) IN ('incidente', 'manutencao', 'outros', 'elogio')
                ORDER BY o.occurred_at DESC
                LIMIT 100
                """
            ),
            {"pids": ctx["post_ids"]},
        )
    ).mappings().all()

    rotulos = {
        "incidente": "Incidente",
        "manutencao": "Manutenção",
        "elogio": "Elogio",
        "outros": "Registro operacional",
    }
    itens = [
        {
            "code": r["code"],
            "tipo": rotulos.get(r["tipo"], "Registro operacional"),
            "severidade": r["severidade"],
            "status": r["status"],
            "posto": r["posto"],
            "data": r["occurred_at"].isoformat() if r["occurred_at"] else None,
            "resolvida_em": r["resolved_at"].isoformat() if r["resolved_at"] else None,
        }
        for r in rows
    ]
    return {"condominio": ctx.get("cond_nome"), "total": len(itens), "ocorrencias": itens}
