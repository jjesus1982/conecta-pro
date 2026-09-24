"""Oráculo — Suprimentos: a cadeia solicitação → pedido → NF fecha as contas, estoque entra uma vez,
status de estoque bate com a régua, rádio/rastreador tem posse única e o kit da função entrega N itens
(DGX F9, 24/09/2026).

Por que existe: compras e estoque são a parte do DGX que nunca teve porta aqui — `purchase_*` (0 linhas,
sem controller), `goods_receipts` (0), `nfe_compras_estoque` (147, só o sync escreve). A falha típica
não é conta errada, é dobra: uma NF conferida duas vezes soma duas vezes; um rádio entregue a dois.

O que afirma (recontado por SQL próprio, não pelo serviço):
  1. Pedido criado de uma solicitação copia os itens: Σ quantidade da solicitação == Σ do pedido, e cada
     item do pedido aponta o item de origem.
  2. Receber um pedido registra UM movimento de entrada por item (ref = nº do pedido); receber de novo é
     recusado e não repete. Conferir uma NF-e registra UM movimento por item (ref = chave) sem somar o
     saldo que o sync SEFAZ já somou; conferir de novo é recusado. Índice único é o que garante.
  3. Os 6 status do DGX (`status_estoque`) == um CASE em SQL escrito aqui, para TODO material ativo, e
     para casos fixos (zerado, sem mínimo, abaixo, próximo, regular, acima).
  4. Rádio/celular/rastreador é aceito pelo CHECK de tipo; posse é única — a segunda entrega do mesmo
     equipamento é recusada (índice parcial `ux_equip_aloc_aberta`) e não há equipamento com 2 posses.
  5. Kit da função com N itens → N solicitações de entrega POR pessoa com CPF na função (frente 10).

Estado medido no nascimento (sandbox, 24/09): não existia `sst_uniforme_kits`, nem mínimo/máximo em
`nfe_compras_estoque`, nem índice de entrada única; CHECK de tipo só aceitava armamento|colete → VERMELHO
por ausência do mecanismo. Fixtures marcadas 'FIXTURE DGX F9' e apagadas ao fim.

Roda no container (PYTHONPATH=/app), contra o sandbox. Sai 0 = verde; 1 = vermelho.
"""

from __future__ import annotations

import asyncio
import sys

FIX = "FIXTURE DGX F9"
CNPJ_FIX = "99999999000191"
CHAVE_FIX = "FIXF9" + "0" * 39
XML_FIX = (
    '<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe Id="NFe' + CHAVE_FIX + '">'
    '<det nItem="1"><prod><cProd>FIXF9-A</cProd><xProd>FIXTURE DGX F9 A</xProd><qCom>4</qCom><vUnCom>10.00</vUnCom></prod></det>'
    '<det nItem="2"><prod><cProd>FIXF9-B</cProd><xProd>FIXTURE DGX F9 B</xProd><qCom>6</qCom><vUnCom>10.00</vUnCom></prod></det>'
    "</infNFe></NFe></nfeProc>"
)
SQL_STATUS = """
SELECT item_code, qty_on_hand, minimo, maximo,
  CASE WHEN coalesce(qty_on_hand,0) <= 0 THEN 'Zerado'
       WHEN minimo IS NULL THEN 'Mínimo não informado'
       WHEN qty_on_hand < minimo THEN 'Abaixo do mínimo'
       WHEN maximo IS NOT NULL AND qty_on_hand > maximo THEN 'Acima do máximo'
       WHEN qty_on_hand <= minimo * (1 + :margem) THEN 'Próximo do mínimo'
       ELSE 'Regular' END
FROM nfe_compras_estoque WHERE ativo
"""


async def _limpar(db) -> None:
    from sqlalchemy import text

    for sql in (
        f"DELETE FROM sst_uniforme_entregas WHERE created_by = '{FIX}'",
        f"DELETE FROM sst_uniforme_kits WHERE funcao = '{FIX}' OR created_by = '{FIX}' OR grade_id IN (SELECT id FROM sst_uniforme_grade WHERE item LIKE '{FIX}%')",
        f"DELETE FROM sst_uniforme_grade WHERE item LIKE '{FIX}%'",
        "DELETE FROM equipamentos_controlados_alocacoes WHERE equipamento_id IN (SELECT id FROM equipamentos_controlados WHERE numero_serie LIKE 'FIXTURE-DGX-F9%')",
        "DELETE FROM equipamentos_controlados WHERE numero_serie LIKE 'FIXTURE-DGX-F9%'",
        f"DELETE FROM goods_receipts WHERE order_id IN (SELECT id FROM purchase_orders WHERE supplier_id IN (SELECT id FROM suppliers WHERE cpf_cnpj = '{CNPJ_FIX}'))",
        f"DELETE FROM purchase_orders WHERE supplier_id IN (SELECT id FROM suppliers WHERE cpf_cnpj = '{CNPJ_FIX}')",
        f"DELETE FROM purchase_requisitions WHERE title = '{FIX}'",
        f"DELETE FROM nfe_estoque_movimentos WHERE item_code LIKE 'FIXF9-%' OR ref_chave LIKE 'FIXF9%' OR created_by = '{FIX}'",
        f"DELETE FROM nfe_entradas WHERE chave_acesso = '{CHAVE_FIX}'",
        "DELETE FROM nfe_compras_estoque WHERE item_code LIKE 'FIXF9-%'",
        f"DELETE FROM suppliers WHERE cpf_cnpj = '{CNPJ_FIX}'",
        f"DELETE FROM accounting_entries WHERE historico LIKE 'Baixa estoque: {FIX}%'",  # COGS de saída de fixture (smoke)
    ):
        await db.execute(text(sql))
    await db.commit()


async def main() -> int:  # noqa: C901, PLR0912, PLR0915
    from fastapi import HTTPException
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []
    try:
        from modules.operacional.controllers.redesign_builders import _dgx_f9_suprimentos as f9
        from modules.operacional.controllers.redesign_builders import _frente_10 as f10
        from modules.people_management.hr.services import conformidade_vigilante as cv
    except ImportError as e:
        print(f"FALHOU: frente F9 não existe ({e}) — não há cadeia de compras, estoque com mínimo/máximo nem kit")
        raise AssertionError("mecanismo ausente") from e

    user = f9.usuario_fixture()
    async with async_session_factory() as db:
        await f9._ensure(db)
        # 0) mecanismo
        for nome, sql in (
            ("tabela sst_uniforme_kits", "SELECT to_regclass('public.sst_uniforme_kits')"),
            ("índice de entrada única", "SELECT to_regclass('public.ux_nfe_estoque_mov_entrada')"),
            ("índice de NF conferida única", "SELECT to_regclass('public.ux_goods_receipts_invoice_key')"),
            ("índice de posse única", "SELECT to_regclass('public.ux_equip_aloc_aberta')"),
            (
                "coluna minimo",
                "SELECT 1 FROM information_schema.columns WHERE table_name='nfe_compras_estoque' AND column_name='minimo'",
            ),
        ):
            if not (await db.execute(text(sql))).scalar():
                falhas.append(f"mecanismo ausente: {nome}")
        chk = (
            await db.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='equipamentos_controlados_tipo_check'"
                )
            )
        ).scalar() or ""
        for tp in ("radio", "celular", "rastreador"):
            if tp not in chk:
                falhas.append(f"CHECK de tipo não aceita '{tp}': {chk}")
        if falhas:
            for f in falhas:
                print("FALHOU:", f)
            raise AssertionError(f"{len(falhas)} mecanismo(s) ausente(s)")

        await _limpar(db)
        try:
            # fixtures base
            for c, d in (("FIXF9-A", f"{FIX} A"), ("FIXF9-B", f"{FIX} B")):
                await db.execute(
                    text(
                        "INSERT INTO nfe_compras_estoque (item_code, descricao, unidade, qty_on_hand, unit_cost, avg_cost, grupo, minimo, maximo, origem) VALUES (:c, :d, 'UN', 0, 10, 10, 'material', 10, 50, 'manual')"
                    ),
                    {"c": c, "d": d},
                )
            sup = (
                await db.execute(
                    text(
                        "INSERT INTO suppliers (id, condominio_id, cpf_cnpj, name, supplier_type, category, status, created_at, updated_at) VALUES (gen_random_uuid(), CAST(:c AS uuid), :cnpj, :n, 'pessoa_juridica', 'material', 'ativo', now(), now()) RETURNING id::text"
                    ),
                    {"c": f9.COND_MATRIZ, "cnpj": CNPJ_FIX, "n": f"{FIX} LTDA"},
                )
            ).scalar()
            await db.commit()

            # 1) solicitação → pedido: soma dos itens
            r = await f9.compra_solicitacao(
                user,
                {"titulo": FIX, "urgencia": "urgente", "itens": "FIXF9-A | 3 | fixture\nFIXF9-B | 2 | fixture"},
                db,
            )
            sid = r["id"]
            await f9.compra_solicitacao_status(user, {"id": sid, "status": "aprovada"}, db)
            p = await f9.compra_pedido(
                user, {"requisition_id": sid, "supplier_id": sup, "condicao_pagamento_id": ""}, db
            )
            oid = p["id"]
            soma_sol, soma_ped, sem_origem = (
                await db.execute(
                    text(
                        "SELECT (SELECT sum(quantity) FROM purchase_requisition_items WHERE requisition_id = CAST(:s AS uuid)), "
                        "(SELECT sum(quantity_ordered) FROM purchase_order_items WHERE order_id = CAST(:o AS uuid)), "
                        "(SELECT count(*) FROM purchase_order_items WHERE order_id = CAST(:o AS uuid) AND requisition_item_id IS NULL)"
                    ),
                    {"s": sid, "o": oid},
                )
            ).first()
            if soma_sol != soma_ped or soma_sol != 5 or sem_origem:
                falhas.append(
                    f"pedido não copia a solicitação: Σsol={soma_sol} Σped={soma_ped} itens sem origem={sem_origem}"
                )
            st = (
                await db.execute(
                    text("SELECT status FROM purchase_requisitions WHERE id = CAST(:s AS uuid)"), {"s": sid}
                )
            ).scalar()
            if st != "atendida":
                falhas.append(f"solicitação com pedido deveria estar 'atendida', está '{st}'")

            # 2a) receber manual: um movimento por item, saldo entra, repetir é recusado
            await f9.compra_pedido_enviar(user, {"id": oid}, db)
            await f9.compra_pedido_receber(user, {"id": oid}, db)
            try:
                await f9.compra_pedido_receber(user, {"id": oid}, db)
                falhas.append("receber o mesmo pedido duas vezes foi aceito")
            except HTTPException as e:
                if e.status_code != 409:
                    falhas.append(f"segundo recebimento deveria ser 409, foi {e.status_code}")
            movs, sa, sb = (
                await db.execute(
                    text(
                        "SELECT (SELECT count(*) FROM nfe_estoque_movimentos WHERE tipo='entrada' AND ref_chave = :n), "
                        "(SELECT qty_on_hand FROM nfe_compras_estoque WHERE item_code='FIXF9-A'), (SELECT qty_on_hand FROM nfe_compras_estoque WHERE item_code='FIXF9-B')"
                    ),
                    {"n": p["numero"]},
                )
            ).first()
            if movs != 2 or float(sa) != 3 or float(sb) != 2:
                falhas.append(f"recebimento manual: movimentos={movs} (esperado 2), saldo A={sa} (3), B={sb} (2)")

            # 2b) NF-e já lançada pelo sync: conferir registra 1 movimento por item, NÃO soma saldo, e repetir é 409
            p2 = await f9.compra_pedido(user, {"supplier_id": sup, "itens": "FIXF9-A | 4 | 10\nFIXF9-B | 6 | 10"}, db)
            await f9.compra_pedido_enviar(user, {"id": p2["id"]}, db)
            nid = (
                await db.execute(
                    text(
                        "INSERT INTO nfe_entradas (chave_acesso, numero, emitente_cnpj, emitente_nome, data_emissao, valor_total, xml_raw, processada, status) "
                        "VALUES (:k, 'F9', :c, :n, current_date, 100, :x, true, 'recebida') RETURNING id"
                    ),
                    {"k": CHAVE_FIX, "c": CNPJ_FIX, "n": f"{FIX} LTDA", "x": XML_FIX},
                )
            ).scalar()
            await db.commit()
            r = await f9.compra_nf_conferir(
                user, {"nfe_id": nid, "order_id": ""}, db
            )  # casa por CNPJ + valor (100 = 4×10 + 6×10)
            try:
                await f9.compra_nf_conferir(user, {"nfe_id": nid, "order_id": p2["id"]}, db)
                falhas.append("conferir a mesma NF-e duas vezes foi aceito")
            except HTTPException as e:
                if e.status_code != 409:
                    falhas.append(f"segunda conferência deveria ser 409, foi {e.status_code}")
            movs, dup, sa, sb, recs = (
                await db.execute(
                    text(
                        "SELECT (SELECT count(*) FROM nfe_estoque_movimentos WHERE tipo='entrada' AND ref_chave = :k), "
                        "(SELECT count(*) FROM (SELECT ref_chave, item_code FROM nfe_estoque_movimentos WHERE tipo='entrada' AND ref_chave IS NOT NULL GROUP BY 1,2 HAVING count(*) > 1) d), "
                        "(SELECT qty_on_hand FROM nfe_compras_estoque WHERE item_code='FIXF9-A'), (SELECT qty_on_hand FROM nfe_compras_estoque WHERE item_code='FIXF9-B'), "
                        "(SELECT count(*) FROM goods_receipts WHERE invoice_key = :k)"
                    ),
                    {"k": CHAVE_FIX},
                )
            ).first()
            if movs != 2 or dup or recs != 1 or float(sa) != 3 or float(sb) != 2:
                falhas.append(
                    f"NF-e: movimentos={movs} (2), duplicados={dup} (0), recebimentos={recs} (1), saldo A={sa} (3, sync já somou), B={sb} (2)"
                )

            # 3) status de estoque == régua
            casos = [
                ((0, 10, 50), "Zerado"),
                ((5, None, None), "Mínimo não informado"),
                ((5, 10, 50), "Abaixo do mínimo"),
                ((60, 10, 50), "Acima do máximo"),
                ((11, 10, 50), "Próximo do mínimo"),
                ((12, 10, 50), "Próximo do mínimo"),
                ((13, 10, 50), "Regular"),
                ((30, 10, None), "Regular"),
            ]
            for args, esperado in casos:
                if f9.status_estoque(*args)[0] != esperado:
                    falhas.append(f"status_estoque{args} = {f9.status_estoque(*args)[0]!r}, esperado {esperado!r}")
            n_mat = 0
            for code, q, mi, ma, sql_st in (
                await db.execute(text(SQL_STATUS), {"margem": f9.MARGEM_PROXIMO})
            ).fetchall():
                n_mat += 1
                if f9.status_estoque(q, mi, ma)[0] != sql_st:
                    falhas.append(
                        f"{code}: tela diz {f9.status_estoque(q, mi, ma)[0]!r}, SQL diz {sql_st!r} (saldo {q}, mín {mi}, máx {ma})"
                    )

            # 4) rastreador: tipo aceito, posse única
            eq = await f9.equipamento_movel(
                user,
                {"tipo": "rastreador", "numero_serie": "FIXTURE-DGX-F9-R1", "modelo": FIX, "plano_mensal": "49,90"},
                db,
            )
            pessoas = (
                await db.execute(
                    text(
                        "SELECT id::text FROM employees WHERE status='ativo' AND coalesce(is_homologacao,false)=false ORDER BY nome LIMIT 2"
                    )
                )
            ).fetchall()
            if len(pessoas) < 2:
                falhas.append("sandbox sem 2 ativos para provar posse única")
            else:
                await cv.entregar(db, equipamento_id=eq["id"], employee_id=pessoas[0][0])
                try:
                    await cv.entregar(db, equipamento_id=eq["id"], employee_id=pessoas[1][0])
                    falhas.append("rastreador entregue a duas pessoas ao mesmo tempo")
                except ValueError:
                    pass
                abertas = (
                    await db.execute(
                        text(
                            "SELECT count(*) FROM equipamentos_controlados_alocacoes WHERE equipamento_id = CAST(:e AS uuid) AND devolvido_em IS NULL"
                        ),
                        {"e": eq["id"]},
                    )
                ).scalar()
                if abertas != 1:
                    falhas.append(f"posses abertas do rastreador = {abertas}, esperado 1")
                await cv.devolver(db, equipamento_id=eq["id"])
            dobras = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM (SELECT equipamento_id FROM equipamentos_controlados_alocacoes WHERE devolvido_em IS NULL GROUP BY 1 HAVING count(*) > 1) d"
                    )
                )
            ).scalar()
            if dobras:
                falhas.append(f"{dobras} equipamento(s) com duas posses abertas")

            # 5) kit da função: N itens → N solicitações por pessoa com CPF
            g = []
            for item, tam in ((f"{FIX} CAMISA", "M"), (f"{FIX} CALCA", "42")):
                g.append(
                    (
                        await db.execute(
                            text(
                                "INSERT INTO sst_uniforme_grade (item, tamanho, sku_norm, minimo, maximo, atual) VALUES (:i, :t, :s, 0, 1000, 1000) RETURNING id"
                            ),
                            {"i": item, "t": tam, "s": f10.sku_norm(item, tam)},
                        )
                    ).scalar()
                )
            await db.commit()
            funcao = (
                await db.execute(
                    text(
                        "SELECT upper(cargo) FROM employees WHERE status='ativo' AND data_demissao IS NULL AND coalesce(is_homologacao,false)=false AND coalesce(cargo,'')<>'' "
                        "AND regexp_replace(coalesce(cpf,''),'\\D','','g') <> '' GROUP BY 1 ORDER BY count(*), 1 LIMIT 1"
                    )
                )
            ).scalar()
            for gid in g:
                await f9.kit_uniforme(user, {"funcao": funcao, "grade_id": gid, "quantidade": 1}, db)
            # marca o kit como fixture (a função é real; as entregas nascem `created_by` = fixture)
            await db.execute(
                text("UPDATE sst_uniforme_kits SET created_by = :f WHERE grade_id = ANY(:g)"), {"f": FIX, "g": g}
            )
            await db.commit()
            r = await f9.entregar_kit(db, user, funcao, None, "reposicao", None)
            entregas, pessoas_ent = (
                await db.execute(
                    text(
                        "SELECT count(*), count(DISTINCT employee_id) FROM sst_uniforme_entregas WHERE created_by = :f"
                    ),
                    {"f": FIX},
                )
            ).first()
            if (
                r["itens_do_kit"] != 2
                or entregas != 2 * r["pessoas"]
                or pessoas_ent != r["pessoas"]
                or r["pessoas"] < 1
            ):
                falhas.append(
                    f"kit de {funcao}: {r['itens_do_kit']} item(ns) × {r['pessoas']} pessoa(s) → {entregas} entrega(s) para {pessoas_ent} pessoa(s)"
                )
            print(
                f"cadeia: Σsol={soma_sol} Σped={soma_ped} · recebimento manual 2 mov · NF-e {movs} mov, {recs} conferência · "
                f"materiais conferidos na régua: {n_mat} · rastreador posse única ok · kit {funcao}: 2 × {r['pessoas']} = {entregas}"
            )
        finally:
            await db.rollback()
            await _limpar(db)

    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL desvios: {len(falhas)}")
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) na cadeia de suprimentos")
    print(
        "OK suprimentos: solicitação→pedido→NF fecha, entrada única por chave, status == régua, posse única, kit entrega N itens"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
