"""Oráculo — DGX T3: vagas do contrato, restrição por cliente, grid com ação, livro Visualizado/Finalizar,
copiar contrato, última visita por cliente, painel de alertas (24/09/2026).

Por que existe: cada superfície do T3 tem um jeito óbvio de mentir. Um posto "ligado ao contrato" de OUTRO
cliente; um quadro contratado × alocado que não bate com `allocations`; um custo por contrato que não é
Σ salário × contratado × (1 + encargos) da tabela de precificação; uma restrição que a tela mostra mas a
movimentação/cobertura ignora; um "Visualizado" que não muda estado; uma cópia de contrato com número
repetido ou sem os itens; um "última visita" que não é a última; um painel que soma menos alertas do
que a tabela tem.

O que afirma (recontado por SQL próprio, não pelo serviço):
  (a) RESTRIÇÃO: com restrição viva, `movimentacao_service.alocar` e `cobertura_service.registrar` recusam
      com 422 e a mensagem cita o cliente; nenhuma linha fica para trás; encerrada, `exigir_livre` passa e a
      recontagem de vivas é 0. A restrição só existe uma vez por (colaborador, cliente) — a segunda dá 409.
  (b) VAGAS: todo `posts.contract_id` preenchido aponta para contrato do MESMO cliente; posto que ficou sem
      contrato é exatamente aquele cujo cliente não tem UM contrato vivo; `_meta.vagas` da tela bate com
      `allocations` ativas e `required_headcount`; `com_encargos` por contrato == Σ salário × contratado ×
      (1 + Σ ENCARGO_KEYS de crm_pricing_params).
  (c) LIVRO: ocorrência fixture aberta → `livro-visualizado` deixa `em_analise` → `livro-finalizar` deixa
      `resolvida` com resolved_at e resolved_by; finalizar de novo é recusado (409).
  (d) COPIAR: a cópia nasce `draft`, com número novo e único, mesmo cliente e valores, e o mesmo número de
      itens ativos do original; a fixture é apagada ao fim.
  (e) VISITAS: para cada cliente da tela, `_meta.ultima` == greatest(max(crm_visit_reports.data_visita),
      max(visitas realizadas/check-in)) recontado aqui.
  (f) PAINEL: `_meta.total` == count(*) de proativo_alert_state com resolved_at IS NULL.
  (g) As telas T3 montam sem "FALHOU" e todas têm porta (`_op_grupos` / EXTRA_MENU do CRM).

Fixtures marcadas com 'FIXTURE DGX T3', apagadas no `finally`.
Estado medido no nascimento (staging, 24/09/2026): builder não existia (ImportError) → VERMELHO.
Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL ...: N`.
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

from sqlalchemy import text

FIX = "FIXTURE DGX T3"
falhas = 0


def ok(cond, msg):
    global falhas
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond:
        falhas += 1


async def main() -> int:
    from core.database import async_session_factory

    try:
        from modules.operacional.controllers.redesign_builders import _dgx_t3_operacional_comercial as t3
        from modules.operacional.controllers.redesign_builders import _frente_04, _op_grupos
        from modules.operacional.controllers.redesign_builders import crm as crm_builder
        from modules.operacional.services import cobertura_service as cs
        from modules.operacional.services import movimentacao_service as ms
        from modules.operacional.services import restricao_cliente as rc
        from modules.operacional.services import supervisao_service as ss
    except Exception as exc:  # noqa: BLE001
        ok(False, f"(a–g) builder/serviços do T3 não importam: {type(exc).__name__}: {exc}")
        print(f"TOTAL falhas T3 operacional/comercial: {falhas}")
        return 1

    async with async_session_factory() as db:
        uid = (await db.execute(text("SELECT id::text FROM users WHERE email = 'jjesus@conectamais.pro'"))).scalar()
        user = SimpleNamespace(id=uid, name="oráculo T3", email="jjesus@conectamais.pro")
        await t3._ensure(db)
        await db.commit()
        occ_id = novo_ctr = None
        try:
            # ── (a) restrição ──
            emp, cli, cond, post = (
                await db.execute(
                    text(
                        "SELECT e.id::text, c.id::text, cd.id::text, p.id::text FROM employees e, clients c "
                        "JOIN condominios cd ON cd.client_id = c.id AND cd.ativo JOIN posts p ON p.client_id = c.id AND p.is_active "
                        "WHERE e.status = 'ativo' AND coalesce(e.is_homologacao,false) = false "
                        "AND NOT EXISTS (SELECT 1 FROM employee_alocacoes a WHERE a.employee_id = e.id AND a.ativo AND a.condominio_id = cd.id) "
                        "ORDER BY e.nome, c.name LIMIT 1"
                    )
                )
            ).fetchone()
            r = await rc.incluir(db, employee_id=emp, client_id=cli, motivo=f"{FIX} pedido do síndico", user_id=uid)
            try:
                await rc.incluir(db, employee_id=emp, client_id=cli, motivo=f"{FIX} de novo", user_id=uid)
                ok(False, "(a) segunda restrição igual deveria dar 409")
            except rc.RestricaoErro as exc:
                await db.rollback()
                ok(exc.status == 409, f"(a) restrição repetida recusada com {exc.status}")
            antes = (await db.execute(text("SELECT count(*) FROM employee_alocacoes"))).scalar()
            try:
                await ms.alocar(
                    db,
                    employee_id=emp,
                    condominio_id=cond,
                    funcao="AGENTE DE PORTARIA",
                    data_inicio=ms.hoje_manaus(),
                    motivo="alocacao_de_vaga",
                    posto_id=post,
                    observacao=FIX,
                    user_id=uid,
                )
                ok(False, "(a) alocar com restrição deveria dar 422")
            except ms.MovimentacaoErro as exc:
                await db.rollback()
                ok(
                    exc.status == 422 and "restrição" in str(exc),
                    f"(a) alocar recusado com {exc.status}: {str(exc)[:110]}",
                )
            depois = (await db.execute(text("SELECT count(*) FROM employee_alocacoes"))).scalar()
            ok(antes == depois, f"(a) nenhuma alocação ficou para trás: {antes} → {depois}")
            outro = (
                await db.execute(
                    text(
                        "SELECT id::text FROM employees WHERE status='ativo' AND coalesce(is_homologacao,false)=false AND id <> CAST(:e AS uuid) ORDER BY nome LIMIT 1"
                    ),
                    {"e": emp},
                )
            ).scalar()
            try:
                await cs.registrar(
                    db,
                    coberto_id=outro,
                    cobertura_id=emp,
                    post_id=post,
                    inicio=cs.hoje_manaus(),
                    motivo="falta",
                    observacao=FIX,
                    user_id=uid,
                )
                ok(False, "(a) cobertura com restrição deveria dar 422")
            except cs.CoberturaErro as exc:
                await db.rollback()
                ok(
                    exc.status == 422 and "restrição" in str(exc),
                    f"(a) cobertura recusada com {exc.status}: {str(exc)[:110]}",
                )
            await rc.encerrar(db, restricao_id=r["id"], motivo=FIX, user_id=uid)
            vivas = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM op_restricoes_cliente WHERE ativo AND employee_id = CAST(:e AS uuid) AND client_id = CAST(:c AS uuid)"
                    ),
                    {"e": emp, "c": cli},
                )
            ).scalar()
            await rc.exigir_livre(db, emp, post_id=post)
            ok(vivas == 0, f"(a) encerrada: vivas recontadas = {vivas}; exigir_livre passa")

            # ── (b) vagas ──
            cruzado = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM posts p JOIN contracts ct ON ct.id = p.contract_id WHERE ct.client_id <> p.client_id"
                    )
                )
            ).scalar()
            ok(cruzado == 0, f"(b) postos ligados a contrato de OUTRO cliente: {cruzado}")
            sem_ctr_errado = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM posts p WHERE coalesce(p.is_active,true) AND p.contract_id IS NULL AND "
                        "(SELECT count(*) FROM contracts c WHERE c.client_id = p.client_id AND c.is_active AND c.status IN ('active','pending_signature')) = 1"
                    )
                )
            ).scalar()
            ok(
                sem_ctr_errado == 0,
                f"(b) postos sem contrato cujo cliente tem UM contrato vivo (deviam estar ligados): {sem_ctr_errado}",
            )
            out: dict = {}
            out.update(await _frente_04.telas(db))
            await t3.telas(db, out)
            vagas = (out.get("vagas-do-contrato") or {}).get("_meta", {}).get("vagas", [])
            dif = 0
            for v in vagas:
                r2 = (
                    await db.execute(
                        text(
                            "SELECT coalesce(required_headcount,0), (SELECT count(*) FROM allocations a WHERE a.post_id = p.id AND a.status='active' AND a.is_active) "
                            "FROM posts p WHERE p.id = CAST(:p AS uuid)"
                        ),
                        {"p": v["post_id"]},
                    )
                ).fetchone()
                dif += int(r2[0] != v["contratado"] or r2[1] != v["alocado"])
            ok(
                vagas and dif == 0,
                f"(b) {len(vagas)} vaga(s): contratado/alocado da tela == posts/allocations (divergentes: {dif})",
            )
            # O encargo que a tela DEVE usar é o da empresa que emprega, não a soma da
            # tabela global. Até 27/09/2026 esta linha lia `crm_pricing_params` — uma tabela
            # sem coluna de empresa, cujos sete encargos somam 0,6124 (Lucro Real, com os
            # 5,8% de terceiros). A empresa é Simples Anexo IV: 0,5544. A régua velha
            # aprovaria a tela justamente por ela estar errada do mesmo jeito.
            from modules.crm.services.pricing_cct import CNPJ_MAO_DE_OBRA  # noqa: PLC0415
            from modules.financial.services.encargos import (  # noqa: PLC0415
                encargo_pct_da_empresa,
            )

            _eid = (
                await db.execute(
                    text("SELECT id::text FROM empresas WHERE regexp_replace(coalesce(cnpj,''),'[^0-9]','','g') = :c"),
                    {"c": CNPJ_MAO_DE_OBRA},
                )
            ).scalar()
            enc = encargo_pct_da_empresa(_eid)
            rows = (out.get("contratos-custo-por-vaga") or {}).get("rows", [])
            dif = 0
            for row in rows:
                m = row.get("_meta") or {}
                if not m:
                    continue
                sal = (
                    await db.execute(
                        text(
                            "SELECT coalesce(sum(coalesce(salario_base,0) * coalesce(required_headcount,0)),0) FROM posts WHERE contract_id = CAST(:c AS uuid) AND coalesce(is_active,true)"
                        ),
                        {"c": m["contract_id"]},
                    )
                ).scalar()
                dif += int(abs(float(sal) * (1 + float(enc)) - m["com_encargos"]) > 0.01)
            # DECLARA a população. Hoje os 15 postos ativos têm `salario_base` ZERADO, então
            # a conta acima é 0 == 0 em todas as linhas: verde por vacuidade, não por acerto.
            # «0 divergentes» de uma base vazia não é prova de nada, e uma trava que não diz
            # isso ensina a confiar no verde errado.
            com_salario = (
                await db.execute(
                    text("SELECT count(*) FROM posts  WHERE coalesce(is_active,true) AND coalesce(salario_base,0) > 0")
                )
            ).scalar()
            ok(
                dif == 0,
                f"(b) custo com encargos por contrato == Σ salário×contratado×(1+{float(enc):.4f}) "
                f"em {len(rows)} contrato(s) (divergentes: {dif}) "
                + (
                    f"— ATENÇÃO: {com_salario} posto(s) com salário base preenchido; "
                    f"com zero, esta verificação compara 0 com 0"
                    if not com_salario
                    else f"· {com_salario} posto(s) com salário base"
                ),
            )

            # ── (c) livro ──
            occ = await ss.criar_ocorrencia(
                db, user_id=uid, post_id=post, titulo=f"{FIX} ocorrência", descricao=f"{FIX} descrição longa o bastante"
            )
            occ_id = str(occ["id"] if isinstance(occ, dict) else getattr(occ, "id", occ))
            st = (
                await db.execute(text("SELECT status FROM occurrences WHERE id = CAST(:i AS uuid)"), {"i": occ_id})
            ).scalar()
            ok(st == "aberta", f"(c) fixture nasce aberta: {st}")
            await t3.rd_livro_visualizado(current_user=user, occ_id=occ_id, payload={}, db=db)
            st = (
                await db.execute(text("SELECT status FROM occurrences WHERE id = CAST(:i AS uuid)"), {"i": occ_id})
            ).scalar()
            ok(st == "em_analise", f"(c) visualizado → {st}")
            await t3.rd_livro_finalizar(
                current_user=user, occ_id=occ_id, payload={"corrective_action": f"{FIX} orientado o posto"}, db=db
            )
            st, rat, rby = (
                await db.execute(
                    text(
                        "SELECT status, resolved_at IS NOT NULL, resolved_by_id::text FROM occurrences WHERE id = CAST(:i AS uuid)"
                    ),
                    {"i": occ_id},
                )
            ).fetchone()
            ok(
                st == "resolvida" and rat and rby == uid,
                f"(c) finalizado → {st}, resolved_at={rat}, por={'eu' if rby == uid else rby}",
            )
            try:
                await t3.rd_livro_finalizar(
                    current_user=user, occ_id=occ_id, payload={"corrective_action": f"{FIX} de novo"}, db=db
                )
                ok(False, "(c) finalizar de novo deveria dar 409")
            except Exception as exc:  # noqa: BLE001
                await db.rollback()
                ok(
                    getattr(exc, "status_code", 0) == 409,
                    f"(c) finalizar de novo recusado com {getattr(exc, 'status_code', '?')}",
                )

            # ── (d) copiar contrato ──
            src = (
                await db.execute(
                    text(
                        "SELECT ct.id::text, ct.contract_number, ct.client_id::text, ct.monthly_value, "
                        "(SELECT count(*) FROM contract_items i WHERE i.contract_id = ct.id AND coalesce(i.is_active,true)) FROM contracts ct "
                        "WHERE ct.is_active AND EXISTS (SELECT 1 FROM contract_items i WHERE i.contract_id = ct.id) ORDER BY 5 DESC LIMIT 1"
                    )
                )
            ).fetchone()
            r = await t3.rd_contrato_copiar(
                current_user=user, payload={"contract_id": src[0], "name": f"{FIX} cópia", "copiar_itens": "sim"}, db=db
            )
            novo_ctr = r["id"]
            c2 = (
                await db.execute(
                    text(
                        "SELECT status::text, client_id::text, monthly_value, contract_number, "
                        "(SELECT count(*) FROM contract_items i WHERE i.contract_id = ct.id AND coalesce(i.is_active,true)), "
                        "(SELECT count(*) FROM contracts x WHERE x.contract_number = ct.contract_number) FROM contracts ct WHERE ct.id = CAST(:i AS uuid)"
                    ),
                    {"i": novo_ctr},
                )
            ).fetchone()
            ok(
                c2[0] == "draft" and c2[1] == src[2] and float(c2[2]) == float(src[3]),
                f"(d) cópia {c2[3]}: draft, mesmo cliente e valor ({c2[2]})",
            )
            ok(
                c2[4] == src[4] and c2[5] == 1 and c2[3] != src[1],
                f"(d) itens copiados {c2[4]} == {src[4]} do original; número único ({c2[5]} ocorrência)",
            )

            # ── (e) última visita ──
            outc: dict = {}
            await t3.telas_crm(db, outc)
            rows = (outc.get("visitas-por-cliente") or {}).get("rows", [])
            dif = 0
            for row in rows:
                m = row.get("_meta") or {}
                if not m:
                    continue
                u = (
                    await db.execute(
                        text(
                            "SELECT greatest((SELECT max(data_visita::date) FROM crm_visit_reports WHERE cliente_id = CAST(:c AS uuid)), "
                            " (SELECT max(coalesce(((checkin_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/Manaus')::date, data_visita)) FROM visitas "
                            "   WHERE cliente_id = CAST(:c AS uuid) AND coalesce(ativo,true) AND (status::text = 'realizada' OR checkin_at IS NOT NULL)))"
                        ),
                        {"c": m["client_id"]},
                    )
                ).scalar()
                dif += int((u.isoformat() if u else None) != m["ultima"])
            ok(
                rows and dif == 0,
                f"(e) última visita da tela == max recontado em {len(rows)} cliente(s) (divergentes: {dif})",
            )

            # ── (f) painel ──
            tot = (
                await db.execute(text("SELECT count(*) FROM proativo_alert_state WHERE resolved_at IS NULL"))
            ).scalar()
            mt = (out.get("painel-alertas") or {}).get("_meta", {}).get("total")
            ok(mt == tot, f"(f) painel soma {mt} == {tot} alertas vivos na tabela")

            # ── (g) telas + porta ──
            ids_op = [
                "vagas-do-contrato",
                "vaga-nova",
                "contratos-custo-por-vaga",
                "restricoes-cliente",
                "restricao-nova",
                "painel-alertas",
                "grid-real-contratual",
                "mapa-de-ponto",
            ]
            falhou = [i for i in ids_op if "FALHOU" in str((out.get(i) or {}).get("title", "FALHOU"))]
            falhou += [
                i
                for i in ("contrato-copiar", "visitas-por-cliente")
                if "FALHOU" in str((outc.get(i) or {}).get("title", "FALHOU"))
            ]
            abas = {tid for _g, _t, _s, tabs in _op_grupos.GRUPOS for tid, _l in tabs}
            menu = {m["id"] for m in crm_builder.EXTRA_MENU}
            sem_porta = [i for i in ids_op if i not in abas] + [
                i for i in ("contrato-copiar", "visitas-por-cliente") if i not in menu
            ]
            ok(
                not falhou and not sem_porta,
                f"(g) telas sem FALHOU e com porta (falhou={falhou}, sem_porta={sem_porta})",
            )
            ok(
                sum(1 for r in (out.get("grid-real-contratual") or {}).get("rows", []) if r.get("actions")) > 0,
                "(g) o grid real/contratual tem ação por linha (Cobrir/Alocar)",
            )
        finally:
            await db.rollback()
            if occ_id:
                await db.execute(text("DELETE FROM occurrences WHERE id = CAST(:i AS uuid)"), {"i": occ_id})
            if novo_ctr:
                await db.execute(
                    text("DELETE FROM contract_items WHERE contract_id = CAST(:i AS uuid)"), {"i": novo_ctr}
                )
                await db.execute(text("DELETE FROM contracts WHERE id = CAST(:i AS uuid)"), {"i": novo_ctr})
            await db.execute(text("DELETE FROM op_restricoes_cliente WHERE motivo LIKE :f"), {"f": f"{FIX}%"})
            await db.execute(text("DELETE FROM employee_alocacoes WHERE observacao LIKE :f"), {"f": f"{FIX}%"})
            await db.execute(text("DELETE FROM substitutions WHERE notes LIKE :f"), {"f": f"%{FIX}%"})
            await db.commit()
            sobra = (
                await db.execute(
                    text(
                        "SELECT (SELECT count(*) FROM occurrences WHERE title LIKE :f) + (SELECT count(*) FROM contracts WHERE name LIKE :f) "
                        "+ (SELECT count(*) FROM op_restricoes_cliente WHERE motivo LIKE :f)"
                    ),
                    {"f": f"{FIX}%"},
                )
            ).scalar()
            ok(sobra == 0, f"fixtures apagadas ao fim: {sobra} sobrando")
    print(f"TOTAL falhas T3 operacional/comercial: {falhas}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
