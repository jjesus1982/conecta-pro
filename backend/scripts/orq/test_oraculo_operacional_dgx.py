"""Oráculo — Operacional DGX F8: coberturas, livro do posto, checklist, chamados, avisos (24/09/2026).

Por que existe: a frente F8 traz cinco superfícies novas para o Operacional e cada uma tem um jeito
óbvio de mentir. "Folga trabalhada" marcada por gosto e não pela escala; um livro que mostra menos
do que o posto registrou; um checklist reprovado que abre DUAS ocorrências (ou nenhuma); um chamado
"resolvido" antes de atendido; um aviso "para o posto" contado como se fosse para a empresa inteira.

O que afirma (recontado por SQL próprio, não pelo serviço):
  (a) COBERTURA: cada dia gravado em `substitutions` tem `folga_trabalhada` == o que `shifts` do
      cobertura diz naquele dia (linha is_off_day, ou nenhum turno no dia e escala na quinzena),
      IGNORANDO o turno espelho que a própria cobertura criou; o turno espelho existe no posto; quem
      já tem turno no dia é recusado (409); cobertura de FÉRIAS sem férias aprovadas é recusada
      (422) e não deixa NENHUMA linha para trás (a F5 valida antes de gravar).
  (b) LIVRO: a lista do dia (posto × dia, hora de Manaus) tem o mesmo número de linhas que a união
      ocorrências + passagens + check-ins do gerente + instruções recontada aqui; e a ocorrência
      recém-registrada está nela.
  (c) CHECKLIST: execução com 1 item obrigatório reprovado gera EXATAMENTE 1 ocorrência (delta da
      tabela = 1, ligada em `ocorrencia_id`); execução toda conforme gera 0; o % conforme gravado
      bate com o recontado em `checklist_respostas`.
  (d) CHAMADO: resolvido tem atendido_em ≤ resolvido_em; `sla_cumprido` devolvido == recomputado
      (resolvido_em ≤ aberto_em + sla_min); prioridade urgente = 60 min; um chamado aberto há 2 h
      com SLA de 1 h aparece na tela como "SLA VENCIDO".
  (e) AVISO com público = posto: destinatários no painel == ativos com `posto_atual_id` = posto
      (régua do serviço de comunicados), e MENOR que o total de ativos.
  (f) As 13 telas montam sem "FALHOU".

Fixtures marcadas com 'FIXTURE DGX F8' (notes/descrição/título/observações), apagadas no `finally`;
o turno real do coberto tem notes/needs_substitution restaurados. O aviso da fixture nasce AGENDADO
(início amanhã) para não disparar notificação a ninguém.

Estado medido no nascimento (staging, 24/09/2026): serviços não existiam (ImportError), colunas
não existiam → VERMELHO em (a)–(f). `substitutions` 0 linhas, `checklist_*` 0, `op_chamados`
inexistente, `occurrences` 5.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL ...: N`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta

FIX = "FIXTURE DGX F8"

SQL_USER = "SELECT id::text FROM users WHERE email = 'jjesus@conectamais.pro'"
# coberto: alguém com turno agendado no dia D; cobertura: ativo, sem turno em D nem noturno em D-1,
# com escala na quinzena em volta (→ folga trabalhada esperada = true)
SQL_COBERTO = """
SELECT s.employee_id::text, s.post_id::text, s.id::text, s.notes, s.needs_substitution, s.status
FROM shifts s JOIN employees e ON e.id = s.employee_id
WHERE s.shift_date = :d AND s.is_active AND NOT s.is_off_day AND s.status = 'scheduled'
  AND e.status = 'ativo' AND coalesce(e.is_homologacao, false) = false
ORDER BY e.nome LIMIT 1
"""
SQL_COBERTURA = """
SELECT e.id::text, e.nome FROM employees e
WHERE e.status = 'ativo' AND coalesce(e.is_homologacao, false) = false AND e.id <> CAST(:c AS uuid)
  AND NOT EXISTS (SELECT 1 FROM shifts s WHERE s.employee_id = e.id AND s.is_active AND NOT s.is_off_day
                   AND s.status IN ('scheduled','in_progress','completed')
                   AND (s.shift_date = :d OR (s.shift_date = CAST(:d AS date) - 1 AND s.planned_end_time <= s.planned_start_time)))
  AND EXISTS (SELECT 1 FROM shifts s WHERE s.employee_id = e.id AND s.is_active AND NOT s.is_off_day AND s.status <> 'cancelled'
               AND s.shift_date BETWEEN CAST(:d AS date) - 15 AND CAST(:d AS date) + 15)
ORDER BY e.nome LIMIT 1
"""
SQL_DIA_COM_TURNO = """
SELECT s.shift_date FROM shifts s WHERE s.employee_id = CAST(:e AS uuid) AND s.is_active AND NOT s.is_off_day
  AND s.status = 'scheduled' AND s.shift_date > :d ORDER BY s.shift_date LIMIT 1
"""
# (a) folga recontada: ignora o turno espelho (shift_cobertura_id) que a cobertura criou
SQL_FOLGA_RECONTADA = """
SELECT su.id::text, su.folga_trabalhada, su.shift_cobertura_id::text,
  (EXISTS (SELECT 1 FROM shifts s WHERE s.employee_id = su.substitute_employee_id AND s.shift_date = su.substitution_date
            AND s.is_active AND s.is_off_day)
   OR (NOT EXISTS (SELECT 1 FROM shifts s WHERE s.employee_id = su.substitute_employee_id AND s.shift_date = su.substitution_date
                    AND s.is_active AND NOT s.is_off_day AND s.status <> 'cancelled' AND s.id <> su.shift_cobertura_id)
       AND EXISTS (SELECT 1 FROM shifts s WHERE s.employee_id = su.substitute_employee_id AND s.is_active AND NOT s.is_off_day
                    AND s.status <> 'cancelled' AND s.id <> su.shift_cobertura_id
                    AND s.shift_date BETWEEN su.substitution_date - 15 AND su.substitution_date + 15))) AS folga_sql,
  (SELECT count(*) FROM shifts s WHERE s.id = su.shift_cobertura_id AND s.employee_id = su.substitute_employee_id
     AND s.post_id = su.post_id AND s.shift_date = su.substitution_date AND s.is_active) AS espelho
FROM substitutions su WHERE su.notes LIKE :f
"""
# (b) união do dia recontada
SQL_LIVRO_DIA = """
SELECT count(*) FROM (
  SELECT 1 FROM occurrences o WHERE o.is_active AND o.post_id = CAST(:p AS uuid)
    AND ((o.occurred_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/Manaus')::date = :d
  UNION ALL
  SELECT 1 FROM operacional_passagens_turno pt WHERE coalesce(pt.is_active, true) AND pt.post_id = CAST(:p AS uuid)
    AND (pt.criada_em AT TIME ZONE 'America/Manaus')::date = :d
  UNION ALL
  SELECT 1 FROM visitas v WHERE v.tipo = 'acompanhamento' AND v.origem = 'interna' AND coalesce(v.ativo, true)
    AND v.checkin_at IS NOT NULL AND ((v.checkin_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/Manaus')::date = :d
    AND CAST(:p AS uuid) = (SELECT p2.id FROM posts p2 WHERE p2.client_id = v.cliente_id AND p2.is_active ORDER BY p2.name LIMIT 1)
  UNION ALL
  SELECT 1 FROM operacional_post_orders po WHERE po.post_id = CAST(:p AS uuid)
    AND (po.updated_at AT TIME ZONE 'America/Manaus')::date = :d
) x
"""
SQL_PCT_RECONTADO = """
SELECT round(100.0 * count(*) FILTER (WHERE is_conforme) / nullif(count(*) FILTER (WHERE is_conforme IS NOT NULL), 0), 1)
FROM checklist_respostas WHERE checklist_preenchido_id = CAST(:c AS uuid)
"""
SQL_CHAMADO = """
SELECT aberto_em, atendido_em, resolvido_em, sla_min, status,
       (resolvido_em <= aberto_em + sla_min * interval '1 minute') AS sla_sql
FROM op_chamados WHERE id = CAST(:i AS uuid)
"""
SQL_DEST_POSTO = (
    "SELECT count(*) FROM employees WHERE status = 'ativo' AND coalesce(is_homologacao, false) = false "
    "AND posto_atual_id = CAST(:p AS uuid)"
)
SQL_ATIVOS = "SELECT count(*) FROM employees WHERE status = 'ativo' AND coalesce(is_homologacao, false) = false"
SQL_POSTO_COM_GENTE = """
SELECT p.id::text FROM posts p JOIN employees e ON e.posto_atual_id = p.id AND e.status = 'ativo'
  AND coalesce(e.is_homologacao, false) = false
WHERE p.is_active GROUP BY p.id ORDER BY count(*) DESC LIMIT 1
"""

TELAS = [
    "coberturas",
    "cobertura-nova",
    "livro-ocorrencias",
    "livro-ocorrencia-nova",
    "livro-ocorrencias-pdf",
    "checklist-modelos",
    "checklist-modelo-novo",
    "checklist-executar",
    "checklist-execucoes",
    "chamados",
    "chamado-novo",
    "avisos-painel",
    "aviso-novo",
]


async def _limpar(db, restaurar: list) -> None:
    from sqlalchemy import text

    await db.rollback()
    for sql, p in [
        (
            "DELETE FROM shifts WHERE id IN (SELECT shift_cobertura_id FROM substitutions WHERE notes LIKE :f)",
            {"f": f"%{FIX}%"},
        ),
        ("DELETE FROM substitutions WHERE notes LIKE :f", {"f": f"%{FIX}%"}),
        ("DELETE FROM employee_alocacoes WHERE observacao LIKE :f", {"f": f"%{FIX}%"}),
        (
            "DELETE FROM checklist_respostas WHERE checklist_preenchido_id IN (SELECT id FROM checklist_preenchido WHERE observacoes_gerais LIKE :f)",
            {"f": f"{FIX}%"},
        ),
        (
            "DELETE FROM occurrences WHERE id IN (SELECT ocorrencia_id FROM checklist_preenchido WHERE observacoes_gerais LIKE :f)",
            {"f": f"{FIX}%"},
        ),
        ("DELETE FROM checklist_preenchido WHERE observacoes_gerais LIKE :f", {"f": f"{FIX}%"}),
        (
            "DELETE FROM occurrence_comments WHERE occurrence_id IN (SELECT id FROM occurrences WHERE title LIKE :f)",
            {"f": f"{FIX}%"},
        ),
        ("DELETE FROM occurrences WHERE title LIKE :f", {"f": f"{FIX}%"}),
        ("DELETE FROM op_chamados WHERE descricao LIKE :f", {"f": f"{FIX}%"}),
        (
            "DELETE FROM communication_announcement_reads WHERE announcement_id IN (SELECT id FROM communication_announcements WHERE titulo LIKE :f)",
            {"f": f"{FIX}%"},
        ),
        ("DELETE FROM communication_announcements WHERE titulo LIKE :f", {"f": f"{FIX}%"}),
    ]:
        try:
            await db.execute(text(sql), p)
            await db.commit()
        except Exception:  # noqa: BLE001 — tabela/coluna pode não existir na rodada vermelha
            await db.rollback()
    for sid, notes, needs, status in restaurar:
        await db.execute(
            text("UPDATE shifts SET notes = :n, needs_substitution = :ns, status = :st WHERE id = CAST(:i AS uuid)"),
            {"n": notes, "ns": needs, "st": status, "i": sid},
        )
    await db.commit()


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []
    restaurar: list = []

    def ok(cond: bool, msg: str) -> None:
        print(("  ✓ " if cond else "  ✗ ") + msg)
        if not cond:
            falhas.append(msg)

    async with async_session_factory() as db:
        try:
            try:
                from modules.operacional.controllers.redesign_builders import _dgx_f8_operacional as f8
                from modules.operacional.services import cobertura_service as cs
                from modules.operacional.services import supervisao_service as ss
            except Exception as exc:  # noqa: BLE001
                ok(False, f"(a–f) serviços/builder da F8 não importam: {type(exc).__name__}: {exc}")
                raise SystemExit(1) from exc

            await _limpar(db, [])
            await ss._ensure(db)  # o que o 1º GET da tela faz: DDL + semente
            uid = (await db.execute(text(SQL_USER))).scalar()
            hoje = cs.hoje_manaus()
            agora = cs.agora_manaus()

            # ── (a) cobertura em folga ──
            d = hoje + timedelta(days=3)
            cob = None
            for _ in range(10):  # acha um dia com coberto E cobertura disponíveis
                cob = (await db.execute(text(SQL_COBERTO), {"d": d})).fetchone()
                sub = (await db.execute(text(SQL_COBERTURA), {"c": cob[0], "d": d})).fetchone() if cob else None
                if cob and sub:
                    break
                d += timedelta(days=1)
            if not (cob and sub):
                ok(False, "(a) sem par coberto/cobertura disponível nos próximos dias para a fixture")
            else:
                restaurar.append((cob[2], cob[3], cob[4], cob[5]))
                r = await cs.registrar(
                    db,
                    coberto_id=cob[0],
                    cobertura_id=sub[0],
                    post_id=cob[1],
                    inicio=d,
                    fim=None,
                    motivo="folga",
                    observacao=FIX,
                    user_id=uid,
                    user_nome="oráculo",
                )
                rows = (await db.execute(text(SQL_FOLGA_RECONTADA), {"f": f"%{FIX}%"})).fetchall()
                ok(len(rows) == 1 and r["dias"] == 1, f"(a) 1 dia de cobertura gravado em substitutions: {len(rows)}")
                for row in rows:
                    ok(
                        row[1] == row[3],
                        f"(a) folga_trabalhada gravada={row[1]} == recontada em shifts={row[3]} (sem o espelho)",
                    )
                    ok(row[4] == 1, f"(a) turno espelho do cobertura no posto no dia: {row[4]}")
                ok(
                    rows and rows[0][3] is True,
                    "(a) fixture escolhida estava de folga (escala na quinzena, sem turno no dia)",
                )
                d2 = (await db.execute(text(SQL_DIA_COM_TURNO), {"e": sub[0], "d": d + timedelta(days=1)})).scalar()
                if d2:
                    try:
                        await cs.registrar(
                            db,
                            coberto_id=cob[0],
                            cobertura_id=sub[0],
                            post_id=cob[1],
                            inicio=d2,
                            motivo="falta",
                            observacao=FIX,
                            user_id=uid,
                        )
                        ok(False, "(a) cobertura em dia com turno próprio deveria ser recusada")
                    except cs.CoberturaErro as exc:
                        await db.rollback()
                        ok(exc.status == 409, f"(a) dia com turno próprio recusado com 409: {exc}")
                n_antes = (await db.execute(text("SELECT count(*) FROM substitutions"))).scalar()
                try:
                    await cs.registrar(
                        db,
                        coberto_id=cob[0],
                        cobertura_id=sub[0],
                        post_id=cob[1],
                        inicio=d + timedelta(days=5),
                        motivo="ferias",
                        observacao=FIX,
                        user_id=uid,
                    )
                    ok(False, "(a) cobertura de férias sem férias aprovadas deveria ser recusada")
                except cs.CoberturaErro as exc:
                    await db.rollback()
                    ok(exc.status == 422, f"(a) férias sem férias aprovadas recusada com 422: {exc}")
                n_depois = (await db.execute(text("SELECT count(*) FROM substitutions"))).scalar()
                ok(n_antes == n_depois, f"(a) recusa da F5 não deixou linha para trás: {n_antes} → {n_depois}")

            # ── (b) livro do dia == união recontada ──
            posto = (
                cob[1]
                if cob
                else (
                    await db.execute(text("SELECT id::text FROM posts WHERE is_active ORDER BY name LIMIT 1"))
                ).scalar()
            )
            occ = await ss.criar_ocorrencia(
                db,
                user_id=uid,
                post_id=posto,
                titulo=f"{FIX} livro",
                descricao=f"{FIX} — registro de teste no livro do posto",
                tipo="incidente",
                gravidade="leve",
                quando=agora,
            )
            linhas = await f8._linhas_do_dia(db, posto, hoje)
            n_sql = (await db.execute(text(SQL_LIVRO_DIA), {"p": posto, "d": hoje})).scalar()
            ok(len(linhas) == n_sql, f"(b) livro do dia: tela {len(linhas)} == união recontada {n_sql}")
            ok(
                any((ln.get("ref") == occ.code) for ln in linhas),
                f"(b) ocorrência recém-registrada {occ.code} está no livro",
            )
            ok(
                all(linhas[i]["quando"] <= linhas[i + 1]["quando"] for i in range(len(linhas) - 1)),
                "(b) livro em ordem cronológica",
            )

            # ── (c) checklist: obrigatório reprovado → 1 ocorrência, e só 1 ──
            tid = (
                await db.execute(
                    text("SELECT id::text FROM checklist_templates WHERE codigo = :c"), {"c": ss.SEED_CODIGO}
                )
            ).scalar()
            itens = [i for i in (await db.execute(text(ss.SQL_ITENS))).fetchall() if i[1] == tid]
            ok(len(itens) == 10, f"(c) modelo semente '{ss.SEED_CODIGO}' com 10 itens: {len(itens)}")
            resp = {}
            reprovado = None
            for it in itens:
                if ss.tipo_item(it[4]) == "nota":
                    resp[f"r_{it[0]}"] = "9"
                elif it[5] and reprovado is None:
                    resp[f"r_{it[0]}"] = "nao"
                    reprovado = it[3]
                else:
                    resp[f"r_{it[0]}"] = "sim"
            n_occ0 = (await db.execute(text("SELECT count(*) FROM occurrences"))).scalar()
            r1 = await ss.executar(
                db,
                template_id=tid,
                post_id=posto,
                respostas=resp,
                observacoes=f"{FIX} reprovado",
                user_id=uid,
                user_nome="oráculo",
            )
            n_occ1 = (await db.execute(text("SELECT count(*) FROM occurrences"))).scalar()
            ok(
                r1["ocorrencia_id"] is not None and n_occ1 - n_occ0 == 1,
                f"(c) 1 obrigatório reprovado → delta de ocorrências = {n_occ1 - n_occ0} (esperado 1)",
            )
            ligada = (
                (
                    await db.execute(
                        text(
                            "SELECT count(*) FROM occurrences WHERE id = CAST(:i AS uuid) AND post_id = CAST(:p AS uuid)"
                        ),
                        {"i": r1["ocorrencia_id"], "p": posto},
                    )
                ).scalar()
                if r1["ocorrencia_id"]
                else 0
            )
            ok(ligada == 1, f"(c) ocorrência ligada em checklist_preenchido.ocorrencia_id e no posto certo: {ligada}")
            pct_sql = (await db.execute(text(SQL_PCT_RECONTADO), {"c": r1["id"]})).scalar()
            ok(
                float(pct_sql or 0) == float(r1["percentual"]),
                f"(c) % conforme gravado {r1['percentual']} == recontado {pct_sql}",
            )
            resp_ok = {k: ("sim" if v == "nao" else v) for k, v in resp.items()}
            r2 = await ss.executar(
                db,
                template_id=tid,
                post_id=posto,
                respostas=resp_ok,
                observacoes=f"{FIX} conforme",
                user_id=uid,
                user_nome="oráculo",
            )
            n_occ2 = (await db.execute(text("SELECT count(*) FROM occurrences"))).scalar()
            ok(
                r2["ocorrencia_id"] is None and n_occ2 == n_occ1 and r2["percentual"] == 100.0,
                f"(c) tudo conforme → 0 ocorrência, {r2['percentual']}%",
            )

            # ── (d) chamado ──
            c1 = await ss.abrir_chamado(
                db,
                descricao=f"{FIX} portão travado",
                post_id=posto,
                aberto_por="cliente",
                solicitante_nome="síndico",
                canal="whatsapp",
                categoria="equipamento",
                prioridade="urgente",
                user_id=uid,
            )
            ok(c1["sla_min"] == 60, f"(d) urgente → SLA 60 min: {c1['sla_min']}")
            await ss.assumir_chamado(db, chamado_id=c1["id"], employee_id=None, user_id=uid)
            rr = await ss.resolver_chamado(db, chamado_id=c1["id"], resolucao="técnico destravou o portão")
            row = (await db.execute(text(SQL_CHAMADO), {"i": c1["id"]})).fetchone()
            ok(row[1] is not None and row[1] <= row[2], f"(d) atendido_em {row[1]} ≤ resolvido_em {row[2]}")
            ok(
                bool(row[5]) == rr["sla_cumprido"],
                f"(d) sla_cumprido devolvido {rr['sla_cumprido']} == recomputado {row[5]}",
            )
            c2 = await ss.abrir_chamado(
                db, descricao=f"{FIX} luz da guarita apagada", post_id=posto, prioridade="urgente", user_id=uid
            )
            await db.execute(
                text("UPDATE op_chamados SET aberto_em = :a WHERE id = CAST(:i AS uuid)"),
                {"a": agora - timedelta(hours=2), "i": c2["id"]},
            )
            await db.commit()
            out: dict = {}
            await f8.telas(db, out)
            linha = next((r for r in out["chamados"]["rows"] if r["cells"][0].get("v") == f"#{c2['numero']}"), None)
            ok(
                linha is not None and linha["cells"][8].get("v") == "SLA VENCIDO",
                f"(d) chamado aberto há 2 h com SLA 1 h pintado como SLA VENCIDO: {linha and linha['cells'][8].get('v')}",
            )

            # ── (e) aviso com público posto ──
            from sqlalchemy import select

            from core.models.user import User

            user = (await db.execute(select(User).where(User.email == "jjesus@conectamais.pro"))).scalar_one()
            p_gente = (await db.execute(text(SQL_POSTO_COM_GENTE))).scalar()
            av = await ss.criar_aviso(
                db,
                current_user=user,
                titulo=f"{FIX} aviso do posto",
                conteudo="Aviso de teste do oráculo — só para o posto.",
                publico="posto",
                post_id=p_gente,
                inicio=hoje + timedelta(days=1),
            )
            ok(not av["publicado"], "(e) fixture nasce agendada (início amanhã) — ninguém é notificado")
            painel = next((r for r in await ss.avisos(db) if r[0] == av["id"]), None)
            n_posto = (await db.execute(text(SQL_DEST_POSTO), {"p": p_gente})).scalar()
            n_ativos = (await db.execute(text(SQL_ATIVOS))).scalar()
            ok(
                painel is not None and painel[11] == n_posto,
                f"(e) destinatários no painel {painel and painel[11]} == ativos do posto {n_posto}",
            )
            ok(n_posto < n_ativos, f"(e) público do posto ({n_posto}) é menor que a empresa ({n_ativos})")

            # ── (f) telas ──
            faltam = [t for t in TELAS if t not in out]
            falhou = [t for t in TELAS if t in out and "FALHOU" in str(out[t].get("title", ""))]
            ok(
                not faltam and not falhou,
                f"(f) {len(TELAS)} telas montadas sem FALHOU (faltam={faltam}, falhou={falhou})",
            )
        finally:
            await _limpar(db, restaurar)
            sobras = 0
            for sql in (
                "SELECT count(*) FROM substitutions WHERE notes LIKE '%FIXTURE DGX F8%'",
                "SELECT count(*) FROM occurrences WHERE title LIKE 'FIXTURE DGX F8%'",
                "SELECT count(*) FROM op_chamados WHERE descricao LIKE 'FIXTURE DGX F8%'",
                "SELECT count(*) FROM communication_announcements WHERE titulo LIKE 'FIXTURE DGX F8%'",
            ):
                try:
                    sobras += (await db.execute(text(sql))).scalar() or 0
                except Exception:  # noqa: BLE001
                    await db.rollback()
            print(f"  {'✓' if sobras == 0 else '✗'} fixtures apagadas ao fim: {sobras} sobrando")
            if sobras:
                falhas.append("fixtures sobrando")

    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL falhas operacional DGX F8: {len(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except SystemExit as e:
        print("TOTAL falhas operacional DGX F8: 1" if e.code else "")
        sys.exit(e.code)
