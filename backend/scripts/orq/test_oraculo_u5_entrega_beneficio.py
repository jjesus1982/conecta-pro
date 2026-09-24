"""Oráculo — Entrega de benefício em lote com período de apuração (DGX U5, 24/09/2026).

Por que existe: o motor da frente 03 calcula VT/VR por competência, mas não havia a ENTIDADE
"entrega" — não dava para dizer «a entrega de VR de setembro foi apurada de 01/08 a 31/08, gerou
R$ X, foi aprovada por Y e virou o título Z». O DGX tem isso em `/EntregasBeneficios`. Os jeitos de
essa entidade mentir: reapurar duplicando itens; total da entrega que não é a soma dos itens; acerto
que não bate com o que as entregas anteriores de fato entregaram; entrega aprovada que muda ao
reapurar; segundo clique em "Conta" criando dois títulos.

O que afirma (fixtures próprias, `observacao = 'FIXTURE DGX U5'`, apagadas ao fim):
  1. Serviço e builder importam; `departamento_pessoal.build()` chama `_telas_u5`; as duas tabelas existem.
  2. Apurar DUAS vezes a mesma entrega: mesmo nº de itens, 1 item por pessoa (SQL: nenhum employee_id repetido).
  3. `beneficio_entregas.total` == Σ `beneficio_entrega_itens.total` e `quantidade_pessoas` == count(total) — por SQL.
  4. Acerto contra a entrega anterior, item a item em estado `ok`: `recebido_anterior` == quantidade que
     a MESMA pessoa levou na entrega anterior (recontado por SQL); `ajuste_ponto` == direito − recebido;
     `quantidade` == max(0, planejado + ajuste); `total` == quantidade × unitário. Exige ≥ 1 item `ok`
     (regra não exercitada = vermelho).
  5. Contra-prova do motor por janela: `trabalhado` da janela 01/08–31/08 == `trabalhado_anterior`
     que o motor da frente 03 guardou para 09/2026 em `folha_beneficio_conferencia` (mesma pessoa, VR,
     estado ok) — se a janela por `periodo=` divergir do cálculo por mês, acusa.
  6. Aprovada não muda: reapurar → `EntregaTravadaError`; snapshot dos itens (md5 por SQL) idêntico; editar item → `EntregaTravadaError`.
  7. Conta idempotente: dois `gerar_conta` → o mesmo `payable_id`; UMA linha em `payable_accounts`
     com `gross_value` == total e status não pago.
  8. Apuração provisória: se algum mês da janela está aberto para alguém (SQL em time_sheets /
     gp_monthly_closings), `apuracao_definitiva` é false e o item diz «provisória».
  9. Arquivo do operador: gerado a partir dos itens (Sólides), caminho guardado, status `enviada`.

Estado medido no nascimento (staging, 24/09/2026): serviço, tabelas e telas não existiam → VERMELHO
no item 1 (import falha). Não há mês fechado no staging → item 8 exercita o caminho «provisória».

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
import tempfile
from decimal import Decimal
from uuid import UUID

FIX = "FIXTURE DGX U5"
#: mês fechado para a pessoa — mesma régua do `ponto.fechamento`, reescrita aqui de propósito
SQL_FECHADO = """
SELECT count(*) FROM (
  SELECT employee_id FROM time_sheets WHERE reference_month = :m AND reference_year = :y
     AND lower(coalesce(status,'')) IN ('fechado','aprovado','revisado','enviado_folha')
  UNION SELECT employee_id FROM gp_monthly_closings WHERE month = :m AND year = :y AND fechado IS TRUE
) f WHERE f.employee_id = :e
"""


async def main() -> int:  # noqa: C901
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []
    os.environ["UPLOADS_DIR"] = tempfile.mkdtemp(prefix="u5_")

    # 1) importa + fiação
    try:
        from modules.people_management.folha.services import beneficio_entregas as be
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: serviço folha/services/beneficio_entregas.py não importa: {e}")
        print("TOTAL u5 entrega beneficio: 1")
        return 1
    try:
        # o builder do DP importa o da U5 (router) — importar o DP primeiro evita o ciclo fora do app
        # isort: off
        from modules.operacional.controllers.redesign_builders import departamento_pessoal as dp
        from modules.operacional.controllers.redesign_builders import _dgx_u5_entrega_beneficio as u5  # noqa: F401
        # isort: on
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: builder _dgx_u5_entrega_beneficio não importa: {e}")
        print("TOTAL u5 entrega beneficio: 1")
        return 1
    if "_telas_u5" not in inspect.getsource(dp.build):
        falhas.append("departamento_pessoal.build() não chama _dgx_u5_entrega_beneficio.telas — tela sem porta")

    async with async_session_factory() as db:
        await be._ensure(db)
        for tb in ("beneficio_entregas", "beneficio_entrega_itens"):
            if not (await db.execute(text("SELECT to_regclass(:t)"), {"t": tb})).scalar():
                falhas.append(f"tabela {tb} não existe depois de _ensure")
        tipo_vr = (
            await db.execute(
                text("SELECT id FROM beneficio_tipos WHERE ativo AND tipo_primitivo = 'VR' ORDER BY id LIMIT 1")
            )
        ).scalar()
        if not tipo_vr:
            falhas.append("sem tipo VR ativo em beneficio_tipos — a F3 precisa estar aplicada")
            print("TOTAL u5 entrega beneficio:", len(falhas))
            return 1
        uid = (await db.execute(text("SELECT id::text FROM users WHERE email = 'jjesus@conectamais.pro'"))).scalar()
        payable_id = None
        arquivo = None
        try:
            # fixtures: A (manual, 08/2026) e B (apontamento 01/08–31/08 contra A, previsão 09/2026)
            a = await be.criar(
                db,
                {
                    "beneficio_tipo_id": tipo_vr,
                    "referencia": "08/2026",
                    "previsao_inicio": "01/08/2026",
                    "previsao_fim": "31/08/2026",
                    "apuracao_modo": "manual",
                    "observacao": FIX,
                },
                "oraculo u5",
            )
            ra = await be.apurar(db, a)
            b_ = await be.criar(
                db,
                {
                    "beneficio_tipo_id": tipo_vr,
                    "referencia": "09/2026",
                    "previsao_inicio": "2026-09-01",
                    "previsao_fim": "2026-09-30",
                    "apuracao_modo": "apontamento",
                    "apuracao_inicio": "2026-08-01",
                    "apuracao_fim": "2026-08-31",
                    "entrega_anterior_id": str(a),
                    "observacao": FIX,
                },
                "oraculo u5",
            )
            r1 = await be.apurar(db, b_)
            n1 = (
                await db.execute(text("SELECT count(*) FROM beneficio_entrega_itens WHERE entrega_id = :i"), {"i": b_})
            ).scalar()
            r2 = await be.apurar(db, b_)
            n2, dup = (
                await db.execute(
                    text(
                        "SELECT count(*), count(*) - count(DISTINCT employee_id) FROM beneficio_entrega_itens WHERE entrega_id = :i"
                    ),
                    {"i": b_},
                )
            ).first()
            print(f"A #{a}: {ra['pessoas']} pessoa(s) com valor / {ra['linhas']} · estados {ra['estados']}")
            print(
                f"B #{b_}: {r1['pessoas']} / {r1['linhas']} · estados {r1['estados']} · acerto {r1['acerto_feito']} · definitiva {r1['apuracao_definitiva']}"
            )
            # 2) idempotência
            if n1 != n2 or dup:
                falhas.append(f"(2) apurar duas vezes: {n1} → {n2} itens, {dup} pessoa(s) repetida(s)")
            if r1["total"] != r2["total"]:
                falhas.append(f"(2) total mudou entre apurações: {r1['total']} → {r2['total']}")
            # 3) total == Σ itens
            for ent in (a, b_):
                tot, s, np_, nc = (
                    await db.execute(
                        text(
                            "SELECT e.total, (SELECT coalesce(sum(total),0) FROM beneficio_entrega_itens WHERE entrega_id = e.id), "
                            " e.quantidade_pessoas, (SELECT count(total) FROM beneficio_entrega_itens WHERE entrega_id = e.id) "
                            "FROM beneficio_entregas e WHERE e.id = :i"
                        ),
                        {"i": ent},
                    )
                ).first()
                if Decimal(tot) != Decimal(s):
                    falhas.append(f"(3) entrega #{ent}: total {tot} ≠ Σ itens {s}")
                if np_ != nc:
                    falhas.append(f"(3) entrega #{ent}: quantidade_pessoas {np_} ≠ itens com total {nc}")
            # 4) acerto contra a anterior, recontado
            oks = (
                await db.execute(
                    text(
                        "SELECT i.employee_id::text, i.planejado, i.direito, i.recebido_anterior, i.ajuste_ponto, i.quantidade, i.unitario, i.total, "
                        " (SELECT quantidade FROM beneficio_entrega_itens x WHERE x.entrega_id = :a AND x.employee_id = i.employee_id) "
                        "FROM beneficio_entrega_itens i WHERE i.entrega_id = :b AND i.estado = 'ok'"
                    ),
                    {"a": a, "b": b_},
                )
            ).fetchall()
            if not oks:
                falhas.append("(4) nenhum item em estado ok — a regra do acerto não foi exercitada")
            for eid, plan, dire, rec, aj, qtd, unit, tot, q_ant in oks:
                if rec != q_ant:
                    falhas.append(f"(4) {eid[:8]}: recebido_anterior {rec} ≠ quantidade na entrega anterior {q_ant}")
                if aj != dire - rec:
                    falhas.append(f"(4) {eid[:8]}: ajuste {aj} ≠ direito {dire} − recebido {rec}")
                if qtd != max(0, plan + aj):
                    falhas.append(f"(4) {eid[:8]}: quantidade {qtd} ≠ max(0, {plan} + {aj})")
                if Decimal(tot) != Decimal(qtd) * Decimal(unit):
                    falhas.append(f"(4) {eid[:8]}: total {tot} ≠ {qtd} × {unit}")
            print(f"(4) itens ok conferidos: {len(oks)}")
            # 5) janela == mês do motor da frente 03
            cmp_ = (
                await db.execute(
                    text(
                        "SELECT i.employee_id::text, i.trabalhado, c.trabalhado_anterior FROM beneficio_entrega_itens i "
                        "JOIN folha_beneficio_conferencia c ON c.employee_id = i.employee_id AND c.beneficio = 'VR' "
                        " AND c.competencia = DATE '2026-09-01' AND c.trabalhado_anterior IS NOT NULL "
                        "WHERE i.entrega_id = :b AND i.trabalhado IS NOT NULL"
                    ),
                    {"b": b_},
                )
            ).fetchall()
            for eid, tj, tm in cmp_:
                if tj != tm:
                    falhas.append(f"(5) {eid[:8]}: trabalhado pela janela {tj} ≠ trabalhado_anterior do motor {tm}")
            print(f"(5) pessoas comparadas com o motor por mês: {len(cmp_)}")
            # 8) provisória
            abertos = 0
            for (eid,) in (
                await db.execute(
                    text(
                        "SELECT employee_id::text FROM beneficio_entrega_itens WHERE entrega_id = :b AND total IS NOT NULL"
                    ),
                    {"b": b_},
                )
            ).fetchall():
                if not (await db.execute(text(SQL_FECHADO), {"m": 8, "y": 2026, "e": eid})).scalar():
                    abertos += 1
            definitiva = (
                await db.execute(text("SELECT apuracao_definitiva FROM beneficio_entregas WHERE id = :b"), {"b": b_})
            ).scalar()
            n_prov = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM beneficio_entrega_itens WHERE entrega_id = :b AND total IS NOT NULL AND observacao ILIKE '%provis%'"
                    ),
                    {"b": b_},
                )
            ).scalar()
            if (abertos > 0) != (definitiva is False):
                falhas.append(f"(8) {abertos} pessoa(s) com 08/2026 aberto mas apuracao_definitiva={definitiva}")
            if abertos and n_prov != abertos:
                falhas.append(f"(8) {abertos} pessoa(s) com mês aberto, {n_prov} item(ns) dizendo «provisória»")
            print(f"(8) pessoas com 08/2026 aberto: {abertos} · definitiva={definitiva} · itens provisórios {n_prov}")
            # 6) aprovada não muda
            await be.aprovar(db, b_, "oraculo u5")
            snap_sql = (
                "SELECT md5(string_agg(concat_ws('|', employee_id, planejado, trabalhado, recebido_anterior, direito, ajuste_ponto, "
                "quantidade, unitario, total, estado), ';' ORDER BY employee_id)) FROM beneficio_entrega_itens WHERE entrega_id = :b"
            )
            snap1 = (await db.execute(text(snap_sql), {"b": b_})).scalar()
            try:
                await be.apurar(db, b_)
                falhas.append("(6) reapurar entrega aprovada NÃO foi recusado")
            except be.EntregaTravadaError:
                pass
            item = (
                await db.execute(
                    text("SELECT id FROM beneficio_entrega_itens WHERE entrega_id = :b AND total IS NOT NULL LIMIT 1"),
                    {"b": b_},
                )
            ).scalar()
            try:
                await be.editar_item(db, item, 1, "oraculo")
                falhas.append("(6) editar item de entrega aprovada NÃO foi recusado")
            except be.EntregaTravadaError:
                pass
            snap2 = (await db.execute(text(snap_sql), {"b": b_})).scalar()
            if snap1 != snap2:
                falhas.append("(6) itens da entrega aprovada mudaram")
            # 7) conta idempotente
            c1 = await be.gerar_conta(db, b_, UUID(uid))
            c2 = await be.gerar_conta(db, b_, UUID(uid))
            payable_id = c1["payable_id"]
            if c1["payable_id"] != c2["payable_id"] or not c2["ja_existia"]:
                falhas.append(f"(7) dois gerar_conta → {c1['payable_id']} e {c2['payable_id']}")
            row = (
                await db.execute(
                    text(
                        "SELECT count(*), max(gross_value), max(status::text) FROM payable_accounts WHERE id = CAST(:p AS uuid)"
                    ),
                    {"p": payable_id},
                )
            ).first()
            tot_b = (await db.execute(text("SELECT total FROM beneficio_entregas WHERE id = :b"), {"b": b_})).scalar()
            if row[0] != 1 or Decimal(row[1] or 0) != Decimal(tot_b):
                falhas.append(f"(7) payable_accounts: {row[0]} linha(s), gross {row[1]} ≠ total {tot_b}")
            if (row[2] or "").lower() in ("paga", "paid"):
                falhas.append(f"(7) título nasceu PAGO ({row[2]})")
            print(f"(7) título {payable_id[:8]}… {row[1]} status {row[2]}")
            # 9) arquivo
            nome, texto, avisos = await be.gerar_arquivo(db, b_, "solides", "oraculo u5")
            path, st = (
                await db.execute(
                    text("SELECT arquivo_operador_path, status FROM beneficio_entregas WHERE id = :b"), {"b": b_}
                )
            ).first()
            arquivo = path
            if not path or not os.path.exists(path) or st != "enviada":
                falhas.append(f"(9) arquivo {path!r} / status {st}")
            print(f"(9) {nome}: {len(texto.splitlines())} linha(s), {len(avisos)} aviso(s)")
        finally:
            await db.rollback()
            if payable_id:
                await db.execute(text("DELETE FROM payable_accounts WHERE id = CAST(:p AS uuid)"), {"p": payable_id})
            await db.execute(text("DELETE FROM beneficio_entregas WHERE observacao = :f"), {"f": FIX})
            await db.commit()
            if arquivo and os.path.exists(arquivo):
                os.unlink(arquivo)
            sobra = (
                await db.execute(text("SELECT count(*) FROM beneficio_entregas WHERE observacao = :f"), {"f": FIX})
            ).scalar()
            print(f"fixtures restantes: {sobra}")

    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL u5 entrega beneficio: {len(falhas)}")
    if not falhas:
        print("OK entrega de benefício em lote — idempotente, soma fecha, acerto bate, aprovada trava, conta única")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
