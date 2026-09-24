"""Oráculo Y3 — o ciclo da justificativa fecha, e a batida que falta tem nome (24/09/2026).

## Por que existe

A X2 mediu duas coisas e nenhuma delas fechava:

  1. **13 justificativas na base, 13 pendentes, 0 aprovadas**, a mais antiga desde 21/07/2026 —
     e o motor de folha **nunca** consulta `gp_justifications`: aprovar hoje não devolve o
     dinheiro de ninguém.
  2. **64 % do «atraso» de 09/2026 é batida de ENTRADA faltando**, não atraso.

A Y3 fecha o ciclo (fila + deferir/indeferir com efeito PROPOSTO) e dá nome à batida que falta.
São dois riscos, e este oráculo é a trava dos dois:

  · que «aprovar» passe a MEXER na folha — a devolução é proposta, não pagamento;
  · que a pendência de batida acuse dia errado, e alguém desconte (ou abone) em cima dela.

## O que afirma

(a) **Aprovar marca o dia como abonado e NÃO muda holerite** — fixture de justificativa para
    quem tem holerite na competência: depois de `revisar(..., 'aprovar', ...)` o dia aparece em
    `ponto_folha_conferencia` (tipo `falta_justificada`, dentro de `detalhe`), e Σ|Δ| = R$ 0,00
    em `total_earnings`, `total_deductions` e `net_salary` dos holerites da competência.
(b) **Recusar exige motivo** — `revisar(..., 'rejeitar', motivo='')` levanta `ValueError`; com
    motivo, a justificativa fica `rejeitada` e o motivo fica gravado em `review_notes`.
(c) **Dia com batida faltando não conta como atraso nem como falta automática** — recontado por
    **SQL PRÓPRIO** (turno esperado, janela de presença, `punch_type`), não pelo serviço:
      · para todo dia com ENTRADA faltando (e escala conferindo), se ele aparece no `detalhe` da
        conferência de atraso, tem de estar marcado `entrada_ausente` — ou seja, fora do dinheiro;
        o sentido inverso é CONTADO e não travado (a X2 descarta pelo TEMPO e pega também o
        registro tardio, que não é batida faltando);
      · todo dia da lista tem ao menos UMA batida — e o espelho só conta falta em dia **sem
        nenhuma** batida (`espelho_service` L660-673), logo nenhum deles vira falta automática.
(d) **O caçador acha a fixture e não acha quem está completo** — dois turnos de fixture no mesmo
    colaborador: um com só a entrada (tem de aparecer) e um com entrada E saída (não pode).
(e) **A fila mostra exatamente as pendentes** — `fila(db)` recontada por SQL próprio: mesmo
    conjunto de `justification_id`, e os dias parados batem com `hoje − created_at`.
(f) **Fiação** — o build do DP chama a frente e as duas abas estão em `_dp_grupos`.

Toda fixture é marcada `'FIXTURE DGX Y3'` e apagada no `finally`, mesmo em falha.

## Estado medido no nascimento (sandbox, 24/09/2026)

    justificativas: 13 na base, 13 `pendente`, 0 `aprovada`, 0 `rejeitada`;
                    a mais antiga parada há 65 dias (21/07, atestado médico)
    batida faltando (60 dias, 26/07→24/09): 121 dia(s)-pessoa em 34 pessoa(s)
                    — falta ENTRADA em 12, falta SAÍDA em 105, faltam AS DUAS em 4
                    + 79 dias FORA da conta: a batida existe, só que fora do turno previsto
                      (escala lançada invertida — MAURICIO 17, PAULO LAMEGO 14, EDIWILSON 14)
    registro tardio (contado, não trava): 15 dias que a X2 descarta e esta régua não lista
    prazo de revisão: 5 dias (`ponto.justificativa_prazo_dias`, semeado por esta frente)

## Como roda

    WT=$(git rev-parse --show-toplevel)
    ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
           | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
    docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
      --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,mode=1777 \
      -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
      -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
      conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_y3_justificativa_batida.py
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

MARCA = "FIXTURE DGX Y3"
DESVIOS: list[str] = []


def falhou(msg: str) -> None:
    DESVIOS.append(msg)
    print(f"FALHOU: {msg}")


def _r(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


SQL_SOMA_HOLERITES = """
SELECT coalesce(sum(total_earnings),0), coalesce(sum(total_deductions),0), coalesce(sum(net_salary),0), count(*)
  FROM hr_payslips
 WHERE source_system = 'conecta' AND payslip_code NOT LIKE '13O-%'
   AND reference_year = :a AND reference_month = :m
"""

#: (e) a fila, recontada sem passar pelo serviço.
SQL_PENDENTES = """
SELECT justification_id,
       (CAST((now() AT TIME ZONE 'America/Manaus') AS date) - created_at::date) AS dias
  FROM gp_justifications
 WHERE lower(coalesce(status,'')) IN ('pendente','pending','em_analise')
"""

#: (c) a batida faltando, recontada em SQL. Mesma régua que a tela usa, escrita de novo aqui:
#: turno esperado da coorte, janela de presença [início−2h, fim] (noturno até D+1 07:00), e a
#: cauda de 2 h depois do fim planejado para a SAÍDA — que vem DEPOIS do fim do turno.
#: Não conhece `escala_divergente` de propósito: aqui a pergunta é «existe batida no turno?».
SQL_BATIDA_FALTANDO = """
WITH turnos AS (
  SELECT sh.id::text AS sid, sh.shift_date AS d, sh.planned_start_time AS ini,
         sh.planned_end_time AS fim, sh.actual_start_time AS ast,
         sh.employee_id::text AS eid, e.nome
    FROM shifts sh JOIN employees e ON e.id = sh.employee_id JOIN posts p ON p.id = sh.post_id
   WHERE sh.shift_date BETWEEN CAST(:de AS date) AND CAST(:ate AS date)
     AND {esperado} AND {coorte} {nao_ausente}),
t AS (
  SELECT *, (d + ini) AS dt_ini,
         CASE WHEN (d + fim) <= (d + ini) THEN (d + interval '1 day' + fim) ELSE (d + fim) END AS dt_fim
    FROM turnos),
w AS (
  SELECT *, dt_ini - interval '2 hours' AS j_ini,
         CASE WHEN ini >= time '15:00' THEN (d + interval '1 day' + time '07:00') ELSE dt_fim END AS j_fim
    FROM t),
x AS (
  SELECT *, GREATEST(j_fim, dt_fim + interval '2 hours') AS f_saida FROM w
   WHERE dt_fim + interval '2 hours' <= CAST(:agora AS timestamp)),
marcado AS (
  SELECT x.*,
    EXISTS (SELECT 1 FROM gp_clock_punches cp WHERE cp.employee_id::text = x.eid
             AND lower(coalesce(cp.punch_type,'')) = 'entrada'
             AND cp.punch_timestamp BETWEEN x.j_ini AND x.j_fim
             AND coalesce(cp.status,'') <> 'facial_reprovado') AS tem_entrada,
    EXISTS (SELECT 1 FROM gp_clock_punches cp WHERE cp.employee_id::text = x.eid
             AND lower(coalesce(cp.punch_type,'')) = 'saida'
             AND cp.punch_timestamp BETWEEN x.j_ini AND x.f_saida
             AND coalesce(cp.status,'') <> 'facial_reprovado') AS tem_saida,
    (SELECT count(*) FROM gp_clock_punches cp WHERE cp.employee_id::text = x.eid
      AND cp.punch_timestamp BETWEEN x.j_ini AND x.f_saida
      AND coalesce(cp.status,'') <> 'facial_reprovado') AS n_batidas
    FROM x)
SELECT eid, nome, d::text AS dia, tem_entrada, tem_saida, n_batidas
  FROM marcado
 WHERE (n_batidas > 0 OR ast IS NOT NULL) AND NOT (tem_entrada AND tem_saida)
"""


async def _limpar(db) -> None:
    await db.execute(text("DELETE FROM gp_clock_punches WHERE punch_id LIKE :m"), {"m": "y3fix-%"})
    await db.execute(text("DELETE FROM shifts WHERE notes LIKE :m"), {"m": f"%{MARCA}%"})
    await db.execute(text("DELETE FROM gp_justifications WHERE reason LIKE :m"), {"m": f"%{MARCA}%"})
    await db.commit()


async def main() -> int:
    from modules.people_management.folha.services import atraso_falta_conferencia as afc
    from modules.people_management.ponto import mapa_de_ponto as mp
    from modules.people_management.ponto.services import justificativa_batida as jb

    hoje = date.today()
    comp_ano, comp_mes = hoje.year, hoje.month
    resumo_linhas: list[str] = []

    async with async_session_factory() as db:
        await jb._ensure(db)
        await _limpar(db)

        # ── (e) a fila é exatamente o conjunto das pendentes ──────────────────────────────
        esperado = {(r[0], int(r[1] or 0)) for r in (await db.execute(text(SQL_PENDENTES))).all()}
        visto = {(r["justification_id"], int(r["dias_parada"] or 0)) for r in await jb.fila(db)}
        if visto != esperado:
            falhou(
                f"fila: {len(visto)} linha(s) × {len(esperado)} pendente(s) por SQL — "
                f"só no serviço {sorted(x[0] for x in visto - esperado)[:3]}, "
                f"só no SQL {sorted(x[0] for x in esperado - visto)[:3]}"
            )
        resumo_linhas.append(f"fila: {len(esperado)} justificativa(s) pendente(s) — recontadas por SQL")

        # ── (c) a batida faltando, recontada por SQL ──────────────────────────────────────
        de, ate = hoje - timedelta(days=jb.JANELA_DIAS_PADRAO), hoje
        agora = mp.agora_manaus()
        sql = SQL_BATIDA_FALTANDO.format(
            esperado="sh.employee_id IS NOT NULL AND sh.is_off_day = FALSE AND sh.status <> 'cancelled' AND sh.is_active = TRUE",
            coorte=mp.COORTE,
            nao_ausente=mp.nao_ausente_em("sh.shift_date"),
        )
        por_sql = {
            (r["eid"], r["dia"]): dict(r)
            for r in (await db.execute(text(sql), {"de": de, "ate": ate, "agora": agora})).mappings().all()
        }
        servico = await jb.batidas_faltando(db, de, ate, agora=agora)
        por_srv = {(x["employee_id"], x["dia"]): x for x in servico}
        so_srv = set(por_srv) - set(por_sql)
        so_sql = set(por_sql) - set(por_srv)
        if so_srv:
            falhou(f"batida faltando: {len(so_srv)} dia(s) que o serviço vê e o SQL não — ex.: {sorted(so_srv)[:2]}")
        if so_sql:
            falhou(f"batida faltando: {len(so_sql)} dia(s) que o SQL vê e o serviço não — ex.: {sorted(so_sql)[:2]}")
        for k, v in por_srv.items():
            s = por_sql.get(k)
            if s and (bool(s["tem_entrada"]) != v["tem_entrada"] or bool(s["tem_saida"]) != v["tem_saida"]):
                falhou(
                    f"batida faltando {k[1]} {v['nome']}: SQL entrada={s['tem_entrada']}/saída={s['tem_saida']} "
                    f"× serviço entrada={v['tem_entrada']}/saída={v['tem_saida']}"
                )

        # nenhum deles vira falta automática: todos têm ao menos UMA batida
        sem_batida = [k for k, s in por_sql.items() if int(s["n_batidas"] or 0) == 0]
        # (o único caso permitido é o check-in manual do supervisor, que o serviço marca)
        sem_batida = [k for k in sem_batida if not por_srv.get(k, {}).get("checkin_manual")]
        if sem_batida:
            falhou(
                f"{len(sem_batida)} dia(s) na lista de batida faltando NÃO têm batida nenhuma — "
                f"isso é falta/descoberto, não batida faltando: {sorted(sem_batida)[:2]}"
            )

        # Cruzamento com a conferência da X2, nos dois sentidos. São duas réguas INDEPENDENTES
        # para a mesma pergunta: a da X2 é por TEMPO (o «atraso» alcança 50 % da jornada), a
        # desta frente é por `punch_type` (existe batida de entrada?). Elas têm de concordar.
        comps = {k[1][:7] for k in por_srv}
        registro_tardio: list[tuple[str, str, int]] = []
        for comp in sorted(comps):
            linhas = (
                await db.execute(
                    text(
                        "SELECT employee_id, detalhe FROM ponto_folha_conferencia "
                        "WHERE competencia = :c AND tipo = 'atraso'"
                    ),
                    {"c": comp},
                )
            ).all()
            if not linhas:
                continue  # competência ainda não apurada — a X2 tem a própria trava para isso
            for eid, detalhe in linhas:
                for d in detalhe or []:
                    v = por_srv.get((eid, d["dia"]))
                    # (1) dia SEM batida de entrada, com a escala certa, não pode virar dinheiro
                    if v and not v["tem_entrada"] and not v["escala_divergente"] and not d.get("entrada_ausente"):
                        falhou(
                            f"{d['dia']} {eid}: entrada faltando e a conferência de atraso conta "
                            f"{d['minutos']} min como DINHEIRO (entrada_ausente=false)"
                        )
                    # (2) o outro sentido é CONTADO, não travado: a X2 descarta pelo TEMPO
                    #     («o atraso alcança 50 % da jornada»), e isso pega também o dia em que a
                    #     batida de entrada EXISTE mas foi registrada tarde demais — JEOVANE,
                    #     20/09: turno 06:00–18:00, batida `entrada` às 17:25. Não é batida
                    #     faltando, e por isso não entra nesta tela; também não é atraso de
                    #     verdade, e por isso a X2 tira do dinheiro. As duas estão certas, e o
                    #     número existe para o dono ver o tamanho do registro tardio.
                    if d.get("entrada_ausente") and (v is None or v["tem_entrada"]):
                        registro_tardio.append((d["dia"], eid, int(d["minutos"])))
        genuinos = {k: v for k, v in por_srv.items() if not v["escala_divergente"]}
        n_ent = sum(1 for v in genuinos.values() if not v["tem_entrada"])
        resumo_linhas.append(
            f"batida faltando ({de} → {ate}): {len(genuinos)} dia(s)-pessoa (+{len(por_srv) - len(genuinos)} com a "
            f"escala lançada divergente) · falta entrada em {n_ent} · nenhum vira falta automática (todos têm "
            f"batida) · nenhum minuto de entrada ausente virou dinheiro"
        )
        if registro_tardio:
            resumo_linhas.append(
                f"registro tardio (CONTADO, não trava): {len(registro_tardio)} dia(s) que a conferência da X2 "
                f"descarta pelo tempo e esta tela não lista — a batida de entrada existe, só que lançada horas "
                f"depois; ex.: {registro_tardio[0][0]} com {registro_tardio[0][2]} min"
            )

        # ── fixtures ──────────────────────────────────────────────────────────────────────
        antes = (await db.execute(text(SQL_SOMA_HOLERITES), {"a": comp_ano, "m": comp_mes})).first()
        try:
            # (d) dois turnos de fixture: um incompleto (tem de aparecer), um completo (não).
            # Um colaborador da coorte com DOIS dias livres na janela (sem turno e sem batida por
            # perto), para a fixture não esbarrar em dado real. Procura entre todos, não só no
            # primeiro: quem trabalha todo dia não tem dia livre.
            base = (
                await db.execute(
                    text(
                        "SELECT sh.employee_id::text, min(sh.scale_id::text), min(sh.post_id::text), min(e.nome), "
                        "       (SELECT array_agg(g::date ORDER BY g DESC) FROM ("
                        "          SELECT g FROM generate_series(CAST(:de AS date), CAST(:ate AS date) "
                        "                 - interval '2 days', interval '1 day') g "
                        "           WHERE NOT EXISTS (SELECT 1 FROM shifts s WHERE s.employee_id = sh.employee_id "
                        "                               AND s.shift_date = g::date) "
                        "             AND NOT EXISTS (SELECT 1 FROM gp_clock_punches cp "
                        "                               WHERE cp.employee_id = sh.employee_id "
                        "                                 AND cp.punch_timestamp::date BETWEEN g::date - 1 AND g::date + 1) "
                        "           ORDER BY g DESC LIMIT 2) x) AS livres "
                        "FROM shifts sh JOIN employees e ON e.id = sh.employee_id "
                        "WHERE sh.shift_date BETWEEN CAST(:de AS date) AND CAST(:ate AS date) "
                        f"AND sh.is_active AND sh.is_off_day = false AND {mp.COORTE} "
                        "GROUP BY sh.employee_id HAVING count(*) > 0 "
                        "ORDER BY 1 LIMIT 40"
                    ),
                    {"de": de, "ate": ate},
                )
            ).all()
            base = next((b for b in base if b[4] and len(b[4]) >= 2), None)
            if not base:
                falhou("nenhum colaborador com 2 dias livres na janela para montar a fixture (d)")
            else:
                eid, sid, pid, nome, livres = base
                d_incompleto, d_completo = livres[0], livres[1]
                for d_, completo in ((d_incompleto, False), (d_completo, True)):
                    await db.execute(
                        text(
                            "INSERT INTO shifts (id, scale_id, post_id, employee_id, status, shift_date, "
                            " planned_start_time, planned_end_time, planned_hours, notes) VALUES "
                            " (gen_random_uuid(), CAST(:s AS uuid), CAST(:p AS uuid), CAST(:e AS uuid), "
                            "  'scheduled', :d, time '07:00', time '16:00', 8, :n)"
                        ),
                        {
                            "s": sid,
                            "p": pid,
                            "e": eid,
                            "d": d_,
                            "n": f"{MARCA} ({'completo' if completo else 'sem saída'})",
                        },
                    )
                    await db.execute(
                        text(
                            "INSERT INTO gp_clock_punches (punch_id, employee_id, punch_type, punch_timestamp, status) "
                            "VALUES (:pid, CAST(:e AS uuid), 'entrada', :ts, 'aprovado')"
                        ),
                        {"pid": f"y3fix-e-{d_}", "e": eid, "ts": datetime.combine(d_, time(7, 2))},
                    )
                    if completo:
                        await db.execute(
                            text(
                                "INSERT INTO gp_clock_punches (punch_id, employee_id, punch_type, punch_timestamp, status) "
                                "VALUES (:pid, CAST(:e AS uuid), 'saida', :ts, 'aprovado')"
                            ),
                            {"pid": f"y3fix-s-{d_}", "e": eid, "ts": datetime.combine(d_, time(16, 3))},
                        )
                await db.commit()

                achados = {(x["employee_id"], x["dia"]) for x in await jb.batidas_faltando(db, de, ate, agora=agora)}
                if (eid, d_incompleto.isoformat()) not in achados:
                    falhou(f"caçador: o turno de fixture SEM saída ({nome}, {d_incompleto}) não foi achado")
                if (eid, d_completo.isoformat()) in achados:
                    falhou(f"caçador: o turno de fixture COMPLETO ({nome}, {d_completo}) foi acusado à toa")

            # (a)/(b) o ciclo da justificativa
            alvo = (
                await db.execute(
                    text(
                        "SELECT p.employee_id::text, coalesce(e.nome,'?') FROM hr_payslips p "
                        "JOIN employees e ON e.id = p.employee_id "
                        "WHERE p.source_system = 'conecta' AND p.payslip_code NOT LIKE '13O-%' "
                        "AND p.reference_year = :a AND p.reference_month = :m ORDER BY 2 LIMIT 1"
                    ),
                    {"a": comp_ano, "m": comp_mes},
                )
            ).first()
            if not alvo:
                falhou(f"nenhum holerite próprio em {comp_mes:02d}/{comp_ano} — as fixtures (a)/(b) não puderam rodar")
            else:
                eid_j, nome_j = alvo
                dia_j = date(comp_ano, comp_mes, min(15, hoje.day))
                jids = []
                for _ in range(2):
                    jid = str(uuid.uuid4())
                    jids.append(jid)
                    await db.execute(
                        text(
                            "INSERT INTO gp_justifications (justification_id, employee_id, justification_type, "
                            " reason, category, status, created_at) VALUES (:j, :e, 'falta', :r, 'saude', "
                            " 'pendente', :c)"
                        ),
                        {
                            "j": jid,
                            "e": eid_j,
                            "r": f"{MARCA} — atestado do dia {dia_j}",
                            "c": datetime.combine(dia_j, time(8, 0)),
                        },
                    )
                await db.commit()

                # (b) recusar sem motivo é recusado
                try:
                    await jb.revisar(db, jids[1], "rejeitar", eid_j, "")
                    falhou("recusar SEM motivo foi aceito — indeferir sem dizer por quê não é resposta")
                except ValueError:
                    pass
                await jb.revisar(db, jids[1], "rejeitar", eid_j, "Atestado ilegível; reenviar.")
                st = (
                    await db.execute(
                        text(
                            "SELECT lower(status), coalesce(review_notes,'') FROM gp_justifications "
                            "WHERE justification_id = :j"
                        ),
                        {"j": jids[1]},
                    )
                ).first()
                if not st or st[0] != "rejeitada" or "ilegível" not in st[1]:
                    falhou(
                        f"recusar com motivo não gravou: status={st[0] if st else None!r} notes={st[1] if st else None!r}"
                    )

                # (a) aprovar marca o dia como abonado na conferência da X2
                r = await jb.revisar(db, jids[0], "aprovar", eid_j, "Atestado conferido.")
                if not r["efeito"]["abonado"]:
                    falhou("aprovar não reapurou a conferência — o dia não foi marcado como abonado")
                linha = (
                    await db.execute(
                        text(
                            "SELECT detalhe, sentido, divergente, valor_estimado FROM ponto_folha_conferencia "
                            "WHERE competencia = :c AND tipo = 'falta_justificada' AND employee_id = :e"
                        ),
                        {"c": f"{comp_ano:04d}-{comp_mes:02d}", "e": eid_j},
                    )
                ).first()
                if not linha:
                    falhou(f"{nome_j}: justificativa APROVADA e nenhuma linha de abono na conferência")
                elif not any(d.get("dia") == dia_j.isoformat() for d in (linha[0] or [])):
                    falhou(f"{nome_j}: a conferência não marcou o dia {dia_j} como abonado — detalhe={linha[0]}")
                elif linha[2] and linha[1] != "passivo":
                    falhou(f"{nome_j}: divergente com sentido={linha[1]!r} — devia ser 'passivo'")
                else:
                    resumo_linhas.append(
                        f"aprovar {nome_j} ({dia_j:%d/%m}): dia abonado na conferência, sentido={linha[1]}, "
                        f"passivo estimado {_r(linha[3])} — e nenhum holerite tocado"
                    )
        finally:
            await _limpar(db)
            resto = (
                await db.execute(
                    text("SELECT count(*) FROM gp_justifications WHERE reason LIKE :m"), {"m": f"%{MARCA}%"}
                )
            ).scalar()
            resto += (
                await db.execute(text("SELECT count(*) FROM shifts WHERE notes LIKE :m"), {"m": f"%{MARCA}%"})
            ).scalar()
            if resto:
                falhou(f"fixture não foi apagada: {resto} linha(s) '{MARCA}'")
            await afc.apurar(db, f"{comp_ano:04d}-{comp_mes:02d}")  # volta a conferência ao estado medido

        # (a) paralelo cego — os holerites não se mexeram
        depois = (await db.execute(text(SQL_SOMA_HOLERITES), {"a": comp_ano, "m": comp_mes})).first()
        deltas = [abs(_r(antes[i]) - _r(depois[i])) for i in range(3)]
        if sum(deltas) or antes[3] != depois[3]:
            falhou(
                f"a folha MUDOU: Σ|Δ| earnings {deltas[0]} · deductions {deltas[1]} · net {deltas[2]} · "
                f"{antes[3]} → {depois[3]} holerite(s)"
            )
        else:
            resumo_linhas.append(f"paralelo cego {comp_mes:02d}/{comp_ano}: Σ|Δ| = R$ 0,00 em {depois[3]} holerite(s)")

        # ── (f) fiação ────────────────────────────────────────────────────────────────────
        raiz = Path(__file__).resolve().parents[1].parent / "modules/operacional/controllers/redesign_builders"
        dp = (raiz / "departamento_pessoal.py").read_text(encoding="utf-8")
        if "_dgx_y3_justificativa_batida" not in dp:
            falhou("departamento_pessoal.py não chama a frente Y3 — tela sem porta")
        grupos = (raiz / "_dp_grupos.py").read_text(encoding="utf-8")
        for tela in ("justificativas-fila", "batida-faltando"):
            if f'"{tela}"' not in grupos:
                falhou(f"a aba '{tela}' não está em _dp_grupos.py — tela sem porta")
        cacador = Path(__file__).resolve().parents[1] / "qa/checar_batida_faltando.py"
        if "TOTAL dias com batida faltando" not in cacador.read_text(encoding="utf-8"):
            falhou("o caçador perdeu a linha canônica 'TOTAL dias com batida faltando: N'")

    for ln in resumo_linhas:
        print(ln)
    print(f"TOTAL desvios: {len(DESVIOS)}")
    if not DESVIOS:
        print(
            "OK ciclo da justificativa e batida faltando: aprovar marca o dia como abonado e Σ|Δ| = R$ 0,00 nos "
            "holerites, recusar exige motivo, dia com batida faltando não conta como atraso nem como falta "
            "automática (recontado por SQL), o caçador acha a fixture e poupa quem está completo, a fila é o "
            "conjunto das pendentes"
        )
    return 1 if DESVIOS else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
