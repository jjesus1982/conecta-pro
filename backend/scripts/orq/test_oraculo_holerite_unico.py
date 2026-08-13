#!/usr/bin/env python3
"""Um funcionário tem UM holerite visível por competência — e a virada não derruba o portal.

O defeito que este oráculo impede (medido em 13/08/2026):

`PaySlipRepository.get_by_employee_month_year` usava `scalar_one_or_none()`. Nada no banco
impede duas linhas: `hr_payslips` não tem índice único por (funcionário, ano, mês) — só por
`payslip_code`. Hoje há 457 holerites nossos em `draft` e 365 publicados, todos da Portte,
então a query devolve no máximo um. **A dor nasce no instante da virada**: julho já
convergiu (Σ|Δ| R$30,21 em 51 pares), e publicar a nossa sem despublicar a da Portte
levantaria `MultipleResultsFound` → HTTP 500 no holerite de TODO MUNDO daquela competência.

Três asserções, e a terceira é a que vale mais:

  (A) invariante em produção: nenhuma (funcionário, ano, mês) com mais de um visível;
  (B) `publish()` despublica o anterior da mesma competência — a virada é transacional;
  (C) MESMO com duplicidade no banco, o portal devolve UM holerite determinístico em vez
      de estourar. (A) e (B) impedem o defeito nascer; (C) prova que ele não derruba
      ninguém se nascer por outro caminho (import da Portte, correção via SQL direto).

(B) e (C) criam linhas sintéticas — este banco é produção e holerite é documento
trabalhista, então **nada pode escapar**. `repo.publish()` chama `db.commit()`, e um
`db.rollback()` no fim não desfaria um commit já emitido. A sessão do teste é ligada a uma
transação EXTERNA com `join_transaction_mode="create_savepoint"`: o `commit()` do
repositório vira `RELEASE SAVEPOINT` e o rollback da transação de fora leva tudo embora.
A conferência do fim prova que levou.

Receita:
  docker exec -e PYTHONPATH=/app conecta-pro-backend \\
    python3 /app/scripts/orq/test_oraculo_holerite_unico.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid

sys.path.insert(0, "/app")

from sqlalchemy import inspect, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from core.database.session import async_session_factory, engine  # noqa: E402
from modules.hr.employee_portal.models import PaySlip, PaySlipStatus  # noqa: E402
from modules.hr.employee_portal.repositories.payslip_repository import (  # noqa: E402
    PaySlipRepository,
)

# A lista é escrita AQUI, à mão, e NÃO importada do model de propósito — por dois motivos:
#   1. se alguém acrescentar um status visível sem pensar, o oráculo tem que discordar do
#      código em vez de concordar automaticamente;
#   2. importar `VISIVEL_AO_FUNCIONARIO` faria o oráculo morrer de ImportError ao rodar
#      contra a versão anterior do model — vermelho de ferramenta, não de defeito, e é
#      exatamente o vermelho que não prova nada.
VISIVEIS = ("published", "rectified", "contested", "paid")
SQL_DUPLICADOS = text(
    "SELECT employee_id::text AS emp, reference_year AS ano, reference_month AS mes, "
    "       count(*) AS n, string_agg(DISTINCT status, ',') AS sts, "
    "       string_agg(DISTINCT coalesce(source_system,'?'), ',') AS origem "
    "FROM hr_payslips "
    "WHERE status IN ('published','rectified','contested','paid') "
    "GROUP BY 1,2,3 HAVING count(*) > 1 ORDER BY 2 DESC, 3 DESC"
)


def _clonar(orig: PaySlip, **troca) -> PaySlip:
    """Cópia da linha com id e código novos — o UNIQUE é (condominio_id, payslip_code)."""
    cols = {c.key: getattr(orig, c.key) for c in inspect(PaySlip).mapper.column_attrs}
    cols.update(id=uuid.uuid4(), payslip_code=f"ORACULO{uuid.uuid4().hex[:8].upper()}", **troca)
    return PaySlip(**cols)


async def main() -> int:
    falhas: list[str] = []

    async with async_session_factory() as db:
        # ── (A) invariante contra a produção real ────────────────────────────
        dups = (await db.execute(SQL_DUPLICADOS)).mappings().all()
        visiveis = (await db.execute(text(
            "SELECT count(*) FROM hr_payslips "
            "WHERE status IN ('published','rectified','contested','paid')"
        ))).scalar()
        print(f"(A) holerites visíveis: {visiveis} · competências com mais de um: {len(dups)}")
        for d in dups:
            print(f"    ✗ func {d['emp'][:8]}… {d['mes']:02d}/{d['ano']}: "
                  f"{d['n']} linhas [{d['sts']}] de [{d['origem']}]")
        if dups:
            falhas.append(
                f"{len(dups)} competência(s) com mais de um holerite visível — o portal "
                f"não sabe qual é o holerite da pessoa"
            )

        base = (await db.execute(
            text("SELECT id::text FROM hr_payslips WHERE status='published' LIMIT 1")
        )).scalar()

    # ── (B) e (C) sobre linhas sintéticas, dentro de transação descartada ────
    if not base:
        print("(B)(C) NÃO VERIFICADO: nenhum holerite publicado para clonar")
        falhas.append("(B)(C) NÃO VERIFICADO — sem linha base, o teste não prova nada")
    else:
        async with engine.connect() as conn:
            trans = await conn.begin()
            # `create_savepoint`: o commit() de dentro do repositório vira RELEASE
            # SAVEPOINT e não escapa desta transação
            SessaoDescartavel = async_sessionmaker(
                bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
            )
            async with SessaoDescartavel() as db:
                repo = PaySlipRepository(db)
                orig = await repo.get_by_id(uuid.UUID(base))
                # competência que não existe para ninguém: não colide com dado real
                ano_livre, mes_livre = 1990, 1
                a = _clonar(orig, reference_year=ano_livre, reference_month=mes_livre,
                            reference_period=f"{ano_livre}-{mes_livre:02d}",
                            status=PaySlipStatus.PUBLISHED.value)
                b = _clonar(orig, reference_year=ano_livre, reference_month=mes_livre,
                            reference_period=f"{ano_livre}-{mes_livre:02d}",
                            status=PaySlipStatus.DRAFT.value, published_at=None)
                db.add_all([a, b])
                await db.flush()

                # (C) duas visíveis ao mesmo tempo: o portal cai ou escolhe?
                b.status = PaySlipStatus.PUBLISHED.value
                await db.flush()
                try:
                    escolhido = await repo.get_by_employee_month_year(
                        orig.employee_id, mes_livre, ano_livre
                    )
                    if escolhido is None:
                        falhas.append("(C) com duplicidade o portal devolveu NADA")
                    else:
                        print(f"(C) com 2 visíveis na mesma competência, o portal escolheu "
                              f"1 ({escolhido.payslip_code}) em vez de estourar")
                except Exception as exc:  # noqa: BLE001 — é o 500 que queremos provar ausente
                    falhas.append(
                        f"(C) o portal ESTOUROU com duplicidade ({type(exc).__name__}) — "
                        f"é o HTTP 500 no holerite de todo mundo da competência"
                    )

                # (B) publicar `a` de novo tem que derrubar `b`
                b.status = PaySlipStatus.PUBLISHED.value
                a.status = PaySlipStatus.DRAFT.value
                await db.flush()
                await repo.publish(a.id)
                await db.refresh(b)
                if b.status in VISIVEIS:
                    falhas.append(
                        f"(B) publicar não despublicou o anterior (ficou '{b.status}') — "
                        f"a virada da folha deixa dois holerites visíveis"
                    )
                else:
                    print(f"(B) ao publicar, o anterior saiu de visível para '{b.status}'")

            await trans.rollback()  # leva tudo: nada do sintético chega ao banco

        # conferência em sessão NOVA — a de dentro não serve de testemunha
        async with async_session_factory() as db:
            sobrou = (await db.execute(text(
                "SELECT count(*) FROM hr_payslips WHERE reference_year = 1990"
            ))).scalar()
        if sobrou:
            falhas.append(f"(B)(C) VAZOU: {sobrou} holerite(s) sintético(s) no banco")

    if falhas:
        for f in falhas:
            print(f"FALHA: {f}")
        print("TEST oraculo_holerite_unico FAIL")
        return 1
    print("TEST oraculo_holerite_unico PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
