"""Oráculo — Fatura como DOCUMENTO (frente W2, 24/09/2026).

Por que existe: a casa tinha o **recebível** (`receivable_accounts`, criado por `gerar_recebiveis`
a partir do contrato/competência) e não tinha a **fatura** — o papel comercial que o cliente
recebe ANTES da NFS-e, com período de prestação, itens discriminados, condição de pagamento e
número próprio. O DGX chama isso de `/Faturas` e dele nascem «GerarConta», «copiar em lote» e
«imprimir lote». Sem documento, o que o síndico vê é uma linha de contas a receber — não um
documento que ele possa conferir item a item.

Cada peça dessa frente tem um jeito próprio de mentir:
  · numerar com buraco (ou repetir número) quando dois cliques emitem ao mesmo tempo;
  · mostrar um total que não é a soma dos itens (o clássico: editou o item, esqueceu o total);
  · gerar a conta a receber DUAS vezes e cobrar o cliente em dobro;
  · copiar o lote da competência de novo e duplicar a fatura do mês;
  · cancelar uma fatura cujo dinheiro já entrou;
  · imprimir o lote e sair com menos páginas que faturas (uma colada na outra);
  · e faturar no nome de quem CONTRATA quando quem PAGA é outro CNPJ (a fonte pagadora da F12).

O que afirma (um bloco por item):
  a) `_dgx_w2_fatura.telas()` devolve as 4 telas e cada uma tem aba em `_fin_grupos`.
  b) Numeração: duas emissões CONCORRENTES (sessões separadas, `asyncio.gather`) recebem números
     distintos e consecutivos; a série inteira não tem buraco (count == max − min + 1, SQL próprio);
     emitir a mesma fatura duas vezes não consome um segundo número.
  c) `valor_total` da fatura == Σ (`quantidade` × `valor_unitario`) dos itens, recontado por SQL
     próprio — depois de incluir um item novo numa fatura já criada.
  d) `gerar_conta` é idempotente: duas chamadas devolvem o MESMO `receivable_id`, existe UM
     recebível e o `net_value` dele é igual ao `valor_total` da fatura. Não recebe (status pendente).
  e) `copiar_lote` da competência A para B duas vezes cria as faturas UMA vez só.
  f) `cancelar` recusa (409) fatura cujo recebível está pago.
  g) PDF em lote de N faturas tem N páginas (uma fatura por página).
  h) Fatura de cliente COM fonte pagadora sai no nome da FONTE (razão social + CNPJ dela), não no
     nome do cliente que assinou o contrato.

Estado medido no nascimento (sandbox 24/09/2026, cópia de produção): `fin_faturas` e
`fin_fatura_itens` não existiam (`to_regclass` → NULL); 52 recebíveis (31 de origem 'contrato',
R$ 1.110.989,70) e 0 faturas. Módulo `_dgx_w2_fatura` inexistente → VERMELHO em tudo.

Fixtures marcadas 'FIXTURE DGX W2' e apagadas ao fim (inclusive em falha).

Como roda (container efêmero contra o SANDBOX):
    ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
           | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
    docker run --rm --network conecta-staging-network -v "$PWD/backend:/app:ro" -e PYTHONPATH=/app \
      -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
      -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
      conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_w2_fatura.py

Sai 0 = verde; 1 = vermelho. Linha final `TOTAL w2_fatura: N`.
"""

from __future__ import annotations

import asyncio
import re
import sys
from datetime import date
from decimal import Decimal

FIX = "FIXTURE DGX W2"
COMP_A = "2099-03"  # competências que nenhum dado real ocupa
COMP_B = "2099-04"


async def _limpar(db) -> None:
    from sqlalchemy import text

    for sql in (
        "DELETE FROM receivable_accounts WHERE description LIKE :f",
        "DELETE FROM fin_fatura_itens WHERE fatura_id IN (SELECT id FROM fin_faturas WHERE observacao LIKE :f)",
        "DELETE FROM fin_faturas WHERE observacao LIKE :f",
    ):
        try:
            await db.execute(text(sql), {"f": f"%{FIX}%"})
        except Exception:  # noqa: BLE001 — tabela pode não existir na 1ª rodada (vermelho)
            await db.rollback()
    await db.commit()


def _paginas(pdf: bytes) -> int:
    """Conta páginas do PDF sem dependência nova: objetos `/Type /Page` que não são `/Pages`."""
    return len(re.findall(rb"/Type\s*/Page(?![s])", pdf))


async def main() -> int:  # noqa: C901, PLR0912, PLR0915 — um bloco por afirmação, linear de propósito
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []
    total = 0

    # a) módulo + telas + abas
    try:
        from modules.financial.services import fin_faturas as svc
        from modules.operacional.controllers.redesign_builders import _dgx_w2_fatura as w2
        from modules.operacional.controllers.redesign_builders._fin_grupos import GRUPOS
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: módulo da frente W2 não importa: {e}")
        print("TOTAL w2_fatura: 1 falha")
        return 1
    abas = {tid for _g, _t, _s, tabs in GRUPOS for tid, _l in tabs}

    async with async_session_factory() as db:
        await _limpar(db)
        try:
            telas = await w2.telas(db, {})
            for tid in w2.IDS:
                total += 1
                if tid not in telas:
                    falhas.append(f"a) telas() não devolve '{tid}'")
                elif tid not in abas:
                    falhas.append(f"a) tela '{tid}' sem aba em _fin_grupos (tela sem porta não existe)")

            cli = (
                await db.execute(text("SELECT id::text, name FROM clients WHERE ativo ORDER BY name LIMIT 1"))
            ).first()
            if not cli:
                print("FALHOU: sandbox sem cliente ativo — não dá para provar nada")
                print("TOTAL w2_fatura: 1 falha")
                return 1

            def _nova(comp: str, itens: list[dict], **kw) -> dict:
                return {
                    "cliente_id": cli[0],
                    "competencia": comp,
                    "vencimento": date(2099, int(comp[5:7]), 10),
                    "descricao_padrao": f"{FIX} serviços de {comp}",
                    "observacao": FIX,
                    "itens": itens,
                    **kw,
                }

            it1 = [
                {"descricao": f"{FIX} posto diurno", "quantidade": Decimal("2"), "valor_unitario": Decimal("100.00")}
            ]
            f1 = await svc.criar(db, _nova(COMP_A, it1), "oraculo")
            f2 = await svc.criar(db, _nova(COMP_A, it1, cliente_id=cli[0]), "oraculo")

            # b) numeração — duas emissões CONCORRENTES em sessões separadas
            async def _emitir(fid: int) -> int:
                async with async_session_factory() as s2:
                    return await svc.emitir(s2, fid, "oraculo")

            n1, n2 = await asyncio.gather(_emitir(f1), _emitir(f2))
            total += 1
            if n1 == n2 or abs(n1 - n2) != 1:
                falhas.append(f"b) emissões concorrentes deram números {n1} e {n2} (esperado distintos e consecutivos)")
            total += 1
            r = (
                await db.execute(
                    text("SELECT count(*), min(numero), max(numero) FROM fin_faturas WHERE numero IS NOT NULL")
                )
            ).first()
            if r[0] and r[0] != (r[2] - r[1] + 1):
                falhas.append(f"b) série com buraco: {r[0]} faturas numeradas entre {r[1]} e {r[2]}")
            total += 1
            try:
                await svc.emitir(db, f1, "oraculo")
                falhas.append("b) emitir a mesma fatura duas vezes foi aceito (consumiria outro número)")
            except Exception:  # noqa: BLE001 — recusa esperada
                await db.rollback()
            depois = (await db.execute(text("SELECT max(numero) FROM fin_faturas"))).scalar()
            total += 1
            if int(depois or 0) != max(n1, n2):
                falhas.append(f"b) a 2ª emissão da mesma fatura mexeu na série: max virou {depois}")

            # c) total == Σ itens (SQL próprio), inclusive depois de incluir item
            f3 = await svc.criar(db, _nova(COMP_A, it1), "oraculo")
            await svc.item_incluir(
                db,
                f3,
                {
                    "descricao": f"{FIX} adicional noturno",
                    "quantidade": Decimal("1"),
                    "valor_unitario": Decimal("55.50"),
                },
            )
            r = (
                await db.execute(
                    text(
                        "SELECT f.valor_total, (SELECT coalesce(sum(i.quantidade * i.valor_unitario),0) "
                        "  FROM fin_fatura_itens i WHERE i.fatura_id = f.id) FROM fin_faturas f WHERE f.id = :i"
                    ),
                    {"i": f3},
                )
            ).first()
            total += 1
            if Decimal(str(r[0])) != Decimal(str(r[1])).quantize(Decimal("0.01")):
                falhas.append(f"c) valor_total {r[0]} ≠ Σ itens {r[1]}")

            # d) gerar_conta idempotente e do valor da fatura
            # o serviço usa o ORM (ReceivableService): carrega o metadata das FKs como o app faz.
            import core.models  # noqa: F401
            import modules.clients.models  # noqa: F401
            import modules.financial.models  # noqa: F401

            await svc.emitir(db, f3, "oraculo")
            uid = (await db.execute(text("SELECT id FROM users WHERE email='jjesus@conectamais.pro'"))).scalar()
            c1 = await svc.gerar_conta(db, f3, uid)
            c2 = await svc.gerar_conta(db, f3, uid)
            total += 1
            if c1["receivable_id"] != c2["receivable_id"] or c2.get("criado"):
                falhas.append(f"d) gerar_conta não é idempotente: {c1} vs {c2}")
            r = (
                await db.execute(
                    text(
                        "SELECT count(*), max(net_value), max(status) FROM receivable_accounts "
                        " WHERE id = CAST(:r AS uuid)"
                    ),
                    {"r": c1["receivable_id"]},
                )
            ).first()
            fat_total = (await db.execute(text("SELECT valor_total FROM fin_faturas WHERE id=:i"), {"i": f3})).scalar()
            total += 1
            if r[0] != 1 or Decimal(str(r[1])) != Decimal(str(fat_total)):
                falhas.append(f"d) recebível: {r[0]} linha(s), valor {r[1]} ≠ fatura {fat_total}")
            total += 1
            if r[2] != "pendente":
                falhas.append(f"d) gerar_conta RECEBEU (status {r[2]}) — devia só registrar o devido")

            # e) copiar em lote não duplica competência já copiada
            l1 = await svc.copiar_lote(db, COMP_A, COMP_B, None, "oraculo")
            l2 = await svc.copiar_lote(db, COMP_A, COMP_B, None, "oraculo")
            n_b = (
                await db.execute(
                    text("SELECT count(*) FROM fin_faturas WHERE competencia=:c AND observacao LIKE :f"),
                    {"c": COMP_B, "f": f"%{FIX}%"},
                )
            ).scalar()
            total += 1
            if not (l1["copiadas"] >= 1 and l2["copiadas"] == 0 and n_b == l1["copiadas"]):
                falhas.append(f"e) copiar lote 2×: {l1['copiadas']}/{l2['copiadas']} copiadas, {n_b} em {COMP_B}")

            # f) cancelar recusa fatura com recebível pago
            await db.execute(
                text("UPDATE receivable_accounts SET status='paga' WHERE id = CAST(:r AS uuid)"),
                {"r": c1["receivable_id"]},
            )
            await db.commit()
            total += 1
            try:
                await svc.cancelar(db, f3, "oraculo")
                falhas.append("f) cancelar aceitou fatura com recebível PAGO")
            except Exception as e:  # noqa: BLE001
                await db.rollback()
                if getattr(e, "status_code", None) != 409:
                    falhas.append(
                        f"f) cancelar recusou com {getattr(e, 'status_code', type(e).__name__)}, esperado 409"
                    )

            # f2) cancelar ACEITA fatura com conta a receber ainda PENDENTE — o que barra é o
            #     dinheiro recebido, não a existência do título (regressão vista na prova HTTP:
            #     `gerar_conta` marcava «enviada» e travava o cancelamento do que ninguém pagou).
            f5 = await svc.criar(db, _nova(COMP_A, it1), "oraculo")
            await svc.emitir(db, f5, "oraculo")
            c5 = await svc.gerar_conta(db, f5, uid)
            st5 = (
                await db.execute(
                    text("SELECT status FROM receivable_accounts WHERE id = CAST(:r AS uuid)"),
                    {"r": c5["receivable_id"]},
                )
            ).scalar()
            total += 1
            try:
                await svc.cancelar(db, f5, "oraculo")
                fin = (await db.execute(text("SELECT status FROM fin_faturas WHERE id=:i"), {"i": f5})).scalar()
                if fin != "cancelada":
                    falhas.append(f"f2) cancelar não cancelou: fatura ficou {fin}")
            except Exception as e:  # noqa: BLE001
                await db.rollback()
                falhas.append(f"f2) cancelar recusou fatura com recebível {st5} (não pago): {e}")

            # g) PDF em lote: N páginas para N faturas
            ids = [
                int(x)
                for x in (
                    await db.execute(
                        text(
                            "SELECT id FROM fin_faturas WHERE observacao LIKE :f AND numero IS NOT NULL ORDER BY numero"
                        ),
                        {"f": f"%{FIX}%"},
                    )
                )
                .scalars()
                .all()
            ]
            total += 1
            if len(ids) < 2:
                falhas.append(f"g) esperava ≥ 2 faturas emitidas para provar o lote, há {len(ids)}")
            else:
                pdf = await svc.pdf_lote(db, ids)
                n_pag = _paginas(pdf)
                if not pdf.startswith(b"%PDF-") or n_pag != len(ids):
                    falhas.append(f"g) PDF em lote de {len(ids)} faturas tem {n_pag} página(s)")

            # i) aviso de cobrança dobrada: contrato que já tem título de «Gerar do mês» na mesma
            #    competência. O aviso não trava nada — mas se o SQL dele estiver errado ele nunca
            #    aparece, e aí é verde cego numa tela de dinheiro.
            ctr = (
                await db.execute(
                    text("SELECT id::text FROM contracts WHERE status='active' ORDER BY contract_number LIMIT 1")
                )
            ).scalar()
            cond_id = (await db.execute(text("SELECT condominio_id FROM receivable_accounts LIMIT 1"))).scalar()
            await db.execute(
                text(
                    "INSERT INTO receivable_accounts (id, condominio_id, code, description, gross_value, net_value, "
                    "  issue_date, due_date, status, origem, competencia_mes, competencia_ano, metadata, "
                    "  created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :cond, :code, :d, 10, 10, :dt, :dt, 'pendente', 'contrato', "
                    "  :m, :a, CAST(:meta AS jsonb), now(), now())"
                ),
                {
                    "cond": cond_id,
                    "code": "REC-ORQW2-" + COMP_A.replace("-", ""),
                    "d": f"{FIX} titulo do mes",
                    "dt": date(2099, 3, 10),
                    "m": 3,
                    "a": 2099,
                    "meta": '{"contract_id": "' + str(ctr) + '", "origem": "contrato"}',
                },
            )
            await db.commit()
            f6 = await svc.criar(db, _nova(COMP_A, it1, contrato_id=ctr), "oraculo")
            await svc.emitir(db, f6, "oraculo")
            r6 = await svc.gerar_conta(db, f6, uid)
            total += 1
            if "ATEN\u00c7\u00c3O" not in r6["message"]:
                falhas.append(f"i) contrato com titulo de «Gerar do mes» no mes nao avisou: {r6['message']}")

            # h) fonte pagadora: a fatura sai no nome de quem PAGA
            fp = (
                await db.execute(
                    text(
                        "INSERT INTO crm_fontes_pagadoras (cliente_id, razao_social, cnpj, email_nf) "
                        "VALUES (CAST(:c AS uuid), :rz, :cnpj, NULL) "
                        "ON CONFLICT (cliente_id, cnpj) DO UPDATE SET razao_social = EXCLUDED.razao_social RETURNING id"
                    ),
                    {"c": cli[0], "rz": f"{FIX} ADMINISTRADORA LTDA", "cnpj": "99999999000199"},
                )
            ).scalar()
            await db.commit()
            f4 = await svc.criar(db, _nova(COMP_A, it1, fonte_pagadora_id=int(fp)), "oraculo")
            d_sem = await svc.dados_documento(db, f3)
            d_com = await svc.dados_documento(db, f4)
            total += 1
            if d_com["sacado"] != f"{FIX} ADMINISTRADORA LTDA" or d_com["sacado_documento"] != "99999999000199":
                falhas.append(
                    f"h) fatura com fonte pagadora saiu como «{d_com['sacado']}» ({d_com['sacado_documento']})"
                )
            total += 1
            if d_sem["sacado"] != cli[1]:
                falhas.append(
                    f"h) fatura SEM fonte pagadora devia sair no cliente «{cli[1]}», saiu «{d_sem['sacado']}»"
                )
        finally:
            await db.rollback()
            await _limpar(db)
            try:
                await db.execute(text("DELETE FROM crm_fontes_pagadoras WHERE razao_social LIKE :f"), {"f": f"%{FIX}%"})
                await db.commit()
            except Exception:  # noqa: BLE001
                await db.rollback()

    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL w2_fatura: {total} checagens · {len(falhas)} falha(s)")
    if falhas:
        return 1
    print(
        "OK w2_fatura: telas com porta, numeração sem buraco sob concorrência, total == Σ itens, "
        "GerarConta idempotente e sem receber, lote copiado uma vez só, cancelar barra recebível pago, "
        "impressão em lote com uma fatura por página, fonte pagadora no lugar do cliente"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
