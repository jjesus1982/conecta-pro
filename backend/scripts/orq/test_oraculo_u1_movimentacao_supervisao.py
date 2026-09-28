"""Oráculo — Movimentação em dois passos + Supervisão planejada (paridade DGX, frente U1, 24/09/2026).

Por que existe: no DGX a movimentação nasce PENDENTE e alguém aprova — e é na aprovação que a
restrição do cliente barra («Colaborador tem restrição nesse cliente», visto pela T3). Aqui a F5
gravava `aprovado_por/em` mas quem registrava aprovava. E a supervisão (checklist F8, check-in do
gerente) não tinha denominador: 3 visitas no mês eram 3 de 3 ou 3 de 20? Os dois jeitos óbvios
de mentir: um pedido que já muda a alocação antes de aprovado (a folha por condomínio lê a tabela
por data), e um mapa que conta "planejadas" diferente do que a frequência manda.

O que afirma (recontado por SQL próprio, não pelo serviço):
  a. `pedir()` NÃO mexe em `employee_alocacoes`: a alocação ativa anterior continua ativa, sem
     `data_fim`; o pedido está `pendente` em `op_movimentacao_pedidos`; nº de linhas da fixture
     em `employee_alocacoes` não muda.
  b. `recusar()` deixa tudo como estava (pedido `recusada`, alocação intacta, nenhuma linha nova).
  c. `aprovar()` respeita a restrição por cliente (T3): com restrição viva → erro 422 e o pedido
     continua pendente; sem restrição → a anterior encerra em D−1 (`ativo=false`), a nova nasce
     ativa com `aprovado_por` = quem aprovou e `alocacao_origem_id` = anterior; o pedido vira
     `aprovada` com `alocacao_id` = a nova.
  d. Caminho direto do DP (`alocar()`) continua idêntico (a linha nasce ativa com `aprovado_por`) —
     `test_oraculo_movimentacao_com_motivo.py` segue verde (rodado à parte).
  e. Ocorrências geradas == recontadas por SQL pela frequência: plano diário de 7 dias → 7
     (`generate_series`); plano semanal seg/qua em 14 dias → count de isodow ∈ (1,3) no intervalo.
  f. Um checklist executado no posto (F8) marca EXATAMENTE 1 ocorrência como realizada, com
     `checklist_preenchido_id` apontando para a execução.
  g. `gerar_ocorrencias` duas vezes não duplica (UNIQUE plano × data): contagens iguais.
Fixtures marcadas 'FIXTURE DGX U1' (observacao / motivo / observacoes_gerais), apagadas no `finally`.

Estado medido no nascimento (staging, 24/09/2026): `op_movimentacao_pedidos`, `op_supervisao_*`
não existiam, `movimentacao_service.pedir` e `supervisao_planejada` não existiam → VERMELHO
(ImportError/AttributeError em a–g).

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL ...: N`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta

FIX = "FIXTURE DGX U1"
SQL_USER = "SELECT id::text FROM users WHERE email = 'jjesus@conectamais.pro'"
SQL_APROVADOR = "SELECT id::text FROM users WHERE email = 'pjesus@conectamais.pro'"  # quem aprova ≠ quem pede
SQL_CANDIDATO = """
SELECT e.id::text FROM employees e
WHERE e.status = 'ativo' AND coalesce(e.is_homologacao, false) = false
  AND NOT EXISTS (SELECT 1 FROM employee_alocacoes a WHERE a.employee_id = e.id AND a.ativo)
  AND NOT EXISTS (SELECT 1 FROM op_restricoes_cliente r WHERE r.employee_id = e.id AND r.ativo)
ORDER BY e.nome LIMIT 1
"""
SQL_CONDS = (
    "SELECT id::text, client_id::text FROM condominios WHERE ativo AND client_id IS NOT NULL ORDER BY nome LIMIT 2"
)
SQL_POSTOS = "SELECT id::text FROM posts WHERE is_active ORDER BY name LIMIT 2"
SQL_FIX_ALOC = (
    "SELECT id::text, ativo, data_fim, aprovado_por::text, alocacao_origem_id::text FROM employee_alocacoes "
    "WHERE observacao LIKE :f ORDER BY data_inicio"
)
SQL_PEDIDO = "SELECT status, alocacao_id::text FROM op_movimentacao_pedidos WHERE id = CAST(:i AS uuid)"
SQL_N_OCORR = "SELECT count(*) FROM op_supervisao_ocorrencias WHERE plano_id = CAST(:p AS uuid)"
SQL_DIARIO_ESPERADO = "SELECT count(*) FROM generate_series(CAST(:a AS date), CAST(:b AS date), '1 day') d"
SQL_SEMANAL_ESPERADO = "SELECT count(*) FROM generate_series(CAST(:a AS date), CAST(:b AS date), '1 day') d WHERE extract(isodow FROM d) IN (1, 3)"
SQL_REALIZADAS = (
    "SELECT count(*), max(checklist_preenchido_id::text) FROM op_supervisao_ocorrencias o "
    "JOIN op_supervisao_planos p ON p.id = o.plano_id WHERE p.observacao LIKE :f AND o.status = 'realizada'"
)
LIMPA = [
    "DELETE FROM op_supervisao_planos WHERE observacao LIKE :f",  # ocorrências caem por CASCADE
    "DELETE FROM checklist_respostas WHERE checklist_preenchido_id IN (SELECT id FROM checklist_preenchido WHERE observacoes_gerais LIKE :f)",
    "DELETE FROM checklist_preenchido WHERE observacoes_gerais LIKE :f",
    "DELETE FROM op_movimentacao_pedidos WHERE observacao LIKE :f",
    "DELETE FROM employee_alocacoes WHERE observacao LIKE :f",
    "DELETE FROM op_restricoes_cliente WHERE motivo LIKE :f",
]


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []

    def ok(cond: bool, msg: str) -> None:
        print(("  ✓ " if cond else "  ✗ ") + msg)
        if not cond:
            falhas.append(msg)

    try:
        from modules.operacional.services import movimentacao_service as ms
        from modules.operacional.services import restricao_cliente as rc
        from modules.operacional.services import supervisao_planejada as sp
        from modules.operacional.services import supervisao_service as ss

        ms.pedir, ms.aprovar, ms.recusar  # noqa: B018 — AttributeError no código de ontem
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ (a–g) serviços da U1 não importam: {type(exc).__name__}: {exc}")
        print("TOTAL falhas U1 movimentação/supervisão: 1")
        return 1

    async def limpar(db) -> None:
        await db.rollback()
        for sql in LIMPA:
            try:
                await db.execute(text(sql), {"f": FIX + "%"})
            except Exception:  # noqa: BLE001 — tabela pode não existir no código de ontem
                await db.rollback()
        await db.commit()

    async with async_session_factory() as db:
        await ms._ensure(db)
        await sp._ensure(db)
        await limpar(db)
        user = (await db.execute(text(SQL_USER))).scalar()
        # 28/09/2026: a fixture pedia e aprovava com o MESMO usuário — e `aprovar` passou a recusar
        # isso (403, «quem pediu não aprova o próprio pedido»). Quem decide tem de ser outra pessoa
        # do DP, que é justamente o que a regra afirma; a fixture só estava espelhando o furo antigo.
        aprovador = (await db.execute(text(SQL_APROVADOR))).scalar()
        emp = (await db.execute(text(SQL_CANDIDATO))).scalar()
        conds = (await db.execute(text(SQL_CONDS))).fetchall()
        postos = [r[0] for r in (await db.execute(text(SQL_POSTOS))).fetchall()]
        hoje = ms.hoje_manaus()
        if not (user and aprovador and emp and len(conds) == 2 and len(postos) == 2):
            ok(False, "fixture impossível: falta usuário, aprovador, colaborador livre, 2 condomínios ou 2 postos")
            print(f"TOTAL falhas U1 movimentação/supervisão: {len(falhas)}")
            return 1
        try:
            # ── a. pedir não mexe na alocação ──
            base = await ms.alocar(
                db,
                employee_id=emp,
                condominio_id=conds[0][0],
                funcao="AGENTE DE PORTARIA",
                data_inicio=hoje - timedelta(days=3),
                motivo="alocacao_de_vaga",
                solicitado_por="dp",
                observacao=FIX + " base",
                user_id=user,
            )
            ped = await ms.pedir(
                db,
                employee_id=emp,
                condominio_id=conds[1][0],
                funcao="AGENTE DE PORTARIA",
                data_inicio=hoje,
                motivo="a_pedido_do_cliente",
                solicitado_por="cliente",
                solicitante_nome="síndico",
                observacao=FIX + " pedido",
                user_id=user,
            )
            rows = (await db.execute(text(SQL_FIX_ALOC), {"f": FIX + "%"})).fetchall()
            st = (await db.execute(text(SQL_PEDIDO), {"i": ped["id"]})).fetchone()
            ok(
                len(rows) == 1 and rows[0][1] is True and rows[0][2] is None,
                f"(a) pedido não mexeu na alocação: {len(rows)} linha(s), ativo={rows and rows[0][1]}, data_fim={rows and rows[0][2]}",
            )
            ok(st is not None and st[0] == "pendente", f"(a) pedido gravado como pendente: {st and st[0]}")
            ok(
                rows and rows[0][3] == user,
                f"(d) caminho direto do DP: linha nasce com aprovado_por = quem alocou ({rows[0][3] == user})",
            )

            # ── b. recusar deixa tudo como estava ──
            await ms.recusar(db, pedido_id=ped["id"], motivo="teste de recusa", user_id=user)
            rows = (await db.execute(text(SQL_FIX_ALOC), {"f": FIX + "%"})).fetchall()
            st = (await db.execute(text(SQL_PEDIDO), {"i": ped["id"]})).fetchone()
            ok(
                st[0] == "recusada" and len(rows) == 1 and rows[0][1] is True and rows[0][2] is None,
                f"(b) recusar: pedido={st[0]}, alocações={len(rows)}, anterior ativa={rows[0][1]}",
            )
            try:
                await ms.aprovar(db, pedido_id=ped["id"], user_id=aprovador)
                ok(False, "(b) aprovar pedido recusado foi ACEITO")
            except ms.MovimentacaoErro as exc:
                ok(exc.status == 409, f"(b) aprovar pedido recusado recusado com {exc.status}: {exc}")
            await db.rollback()

            # ── c. aprovar respeita restrição; sem restrição encerra a anterior em D−1 ──
            ped2 = await ms.pedir(
                db,
                employee_id=emp,
                condominio_id=conds[1][0],
                funcao="AGENTE DE PORTARIA",
                data_inicio=hoje,
                motivo="a_pedido_do_cliente",
                solicitado_por="cliente",
                observacao=FIX + " pedido 2",
                user_id=user,
            )
            restr = await rc.incluir(
                db, employee_id=emp, client_id=conds[1][1], motivo=FIX + " síndico pediu", user_id=user
            )
            try:
                await ms.aprovar(db, pedido_id=ped2["id"], user_id=aprovador)
                ok(False, "(c) aprovar com restrição viva foi ACEITO")
            except ms.MovimentacaoErro as exc:
                ok(exc.status == 422, f"(c) aprovar com restrição recusado com {exc.status}: {str(exc)[:90]}")
            await db.rollback()
            st = (await db.execute(text(SQL_PEDIDO), {"i": ped2["id"]})).fetchone()
            rows = (await db.execute(text(SQL_FIX_ALOC), {"f": FIX + "%"})).fetchall()
            ok(
                st[0] == "pendente" and len(rows) == 1 and rows[0][1] is True,
                f"(c) depois da recusa por restrição: pedido={st[0]}, alocações={len(rows)}, anterior ativa={rows[0][1]}",
            )
            await rc.encerrar(db, restricao_id=restr["id"], motivo="fim da fixture", user_id=user)
            apr = await ms.aprovar(db, pedido_id=ped2["id"], user_id=aprovador)
            rows = (await db.execute(text(SQL_FIX_ALOC), {"f": FIX + "%"})).fetchall()
            por_id = {r[0]: r for r in rows}
            ant, nova = por_id.get(base["id"]), por_id.get(apr["id"])
            st = (await db.execute(text(SQL_PEDIDO), {"i": ped2["id"]})).fetchone()
            ok(
                ant is not None and ant[1] is False and ant[2] == hoje - timedelta(days=1),
                f"(c) anterior encerrada em D−1: ativo={ant and ant[1]} data_fim={ant and ant[2]} (esperado {hoje - timedelta(days=1)})",
            )
            ok(
                nova is not None and nova[1] is True and nova[3] == aprovador and nova[4] == base["id"],
                f"(c) nova ativa, aprovado_por = aprovador (não quem pediu), origem = anterior: "
                f"{nova and (nova[1], nova[3] == aprovador, nova[4] == base['id'])}",
            )
            ok(st[0] == "aprovada" and st[1] == apr["id"], f"(c) pedido aprovada com alocacao_id = nova: {st}")

            # ── e. ocorrências == recontagem SQL pela frequência ──
            ini, fim7 = hoje, hoje + timedelta(days=6)
            p_dia = await sp.criar_plano(
                db,
                supervisor_employee_id=emp,
                frequencia="diaria",
                posto_id=postos[0],
                vigencia_inicio=ini,
                vigencia_fim=fim7,
                observacao=FIX + " diario",
                user_id=user,
            )
            fim14 = hoje + timedelta(days=13)
            p_sem = await sp.criar_plano(
                db,
                supervisor_employee_id=emp,
                frequencia="semanal",
                posto_id=postos[1],
                dias_semana=[1, 3],
                vigencia_inicio=ini,
                vigencia_fim=fim14,
                observacao=FIX + " semanal",
                user_id=user,
            )
            for i in range(14):
                await sp.gerar_ocorrencias(db, ini + timedelta(days=i))
            n_dia = (await db.execute(text(SQL_N_OCORR), {"p": p_dia["id"]})).scalar()
            e_dia = (await db.execute(text(SQL_DIARIO_ESPERADO), {"a": ini, "b": fim7})).scalar()
            n_sem = (await db.execute(text(SQL_N_OCORR), {"p": p_sem["id"]})).scalar()
            e_sem = (await db.execute(text(SQL_SEMANAL_ESPERADO), {"a": ini, "b": fim14})).scalar()
            ok(n_dia == e_dia == 7, f"(e) plano diário 7 dias: geradas {n_dia} == generate_series {e_dia} == 7")
            ok(
                n_sem == e_sem and n_sem > 0,
                f"(e) plano semanal seg/qua 14 dias: geradas {n_sem} == isodow∈(1,3) {e_sem}",
            )

            # ── g. gerar de novo não duplica ──
            for i in range(14):
                await sp.gerar_ocorrencias(db, ini + timedelta(days=i))
            n_dia2 = (await db.execute(text(SQL_N_OCORR), {"p": p_dia["id"]})).scalar()
            n_sem2 = (await db.execute(text(SQL_N_OCORR), {"p": p_sem["id"]})).scalar()
            ok(n_dia2 == n_dia and n_sem2 == n_sem, f"(g) gerar duas vezes: {n_dia}→{n_dia2}, {n_sem}→{n_sem2}")

            # ── f. checklist no posto marca exatamente 1 realizada ──
            tpl = (
                await db.execute(text("SELECT id::text FROM checklist_templates WHERE codigo = 'CHK-SUP-001'"))
            ).scalar()
            itens = [r for r in (await db.execute(text(ss.SQL_ITENS))).fetchall() if r[1] == tpl]
            resp = {
                f"r_{it[0]}": (
                    "sim" if ss.tipo_item(it[4]) == "sim_nao" else "10" if ss.tipo_item(it[4]) == "nota" else "ok"
                )
                for it in itens
            }
            ex = await ss.executar(
                db,
                template_id=tpl,
                post_id=postos[0],
                respostas=resp,
                observacoes=FIX + " checklist",
                user_id=user,
                user_nome="oráculo U1",
            )
            n_real, chk = (await db.execute(text(SQL_REALIZADAS), {"f": FIX + "%"})).fetchone()
            ok(
                n_real == 1 and chk == ex["id"],
                f"(f) checklist no posto → realizadas na fixture = {n_real} (esperado 1), ligada à execução: {chk == ex['id']}",
            )
            hoje_rows = (
                await db.execute(
                    text(
                        "SELECT status FROM op_supervisao_ocorrencias WHERE plano_id = CAST(:p AS uuid) AND data = :d"
                    ),
                    {"p": p_dia["id"], "d": hoje},
                )
            ).fetchall()
            ok(hoje_rows == [("realizada",)], f"(f) ocorrência de hoje do plano diário: {hoje_rows}")
        except ms.MovimentacaoErro as exc:
            ok(False, f"serviço recusou a fixture: {exc.status} {exc}")
        except sp.SupervisaoPlanejadaErro as exc:
            ok(False, f"supervisão recusou a fixture: {exc.status} {exc}")
        finally:
            await limpar(db)
            sobras = 0
            for sql in (
                "SELECT count(*) FROM employee_alocacoes WHERE observacao LIKE :f",
                "SELECT count(*) FROM op_movimentacao_pedidos WHERE observacao LIKE :f",
                "SELECT count(*) FROM op_supervisao_planos WHERE observacao LIKE :f",
                "SELECT count(*) FROM op_restricoes_cliente WHERE motivo LIKE :f",
                "SELECT count(*) FROM checklist_preenchido WHERE observacoes_gerais LIKE :f",
            ):
                sobras += (await db.execute(text(sql), {"f": FIX + "%"})).scalar() or 0
            ok(sobras == 0, f"fixtures apagadas ao fim: {sobras} sobrando")

    print(f"TOTAL falhas U1 movimentação/supervisão: {len(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
