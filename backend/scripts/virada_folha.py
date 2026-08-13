#!/usr/bin/env python3
"""Ensaio da VIRADA DA FOLHA: a nossa folha vira a autoritativa numa competência.

O que a virada é: hoje o holerite que o funcionário vê no portal é o da **Portte**
(`source_system='portte'`, `published`). O nosso está calculado ao lado, em `draft`. Virar
é publicar o nosso e despublicar o da Portte — para o funcionário, é o mesmo documento
trocando de origem.

Por que é delicado: a troca acontece por pessoa, e enquanto ela acontece existe uma janela
em que a pessoa pode ter **dois** holerites visíveis (o antigo e o novo) ou **nenhum**.
Documento trabalhista não pode ter nenhuma das duas janelas. Por isso a virada de cada
pessoa é UM commit — `PaySlipRepository.publish()` despublica o anterior e publica o novo
juntos — e por isso este script vira **uma competência de cada vez**.

ENSAIO É O PADRÃO. Sem `--aplicar` nada é gravado; a lista dos pares aparece com o Δ de
cada um, para alguém conferir linha a linha antes.

  # ver o que aconteceria em julho (não grava nada)
  docker exec -e PYTHONPATH=/app conecta-pro-backend \\
    python3 /app/scripts/virada_folha.py --mes 7 --ano 2026

  # aplicar (são ~51, acima do teto de 20 → exige --forcar)
  ... --mes 7 --ano 2026 --aplicar --forcar

  # CAMINHO DE VOLTA — devolve a competência ao estado anterior
  ... --mes 7 --ano 2026 --desfazer --aplicar --forcar

O caminho de volta funciona porque a virada não apaga nada: o holerite da Portte vai para
`cancelled` e o nosso volta para `draft`. Nenhuma linha é removida, nenhum valor é
reescrito — só o campo `status` anda, nos dois sentidos.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/scripts/qa")  # _mutacao mora lá

from _mutacao import Mutacao  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from core.database.session import async_session_factory, engine  # noqa: E402
from modules.hr.employee_portal.repositories.payslip_repository import (  # noqa: E402
    PaySlipRepository,
)

# `NOSSO` e `DELES` são o eixo da virada. Se um dia a origem mudar de nome, é aqui.
NOSSO, DELES = "conecta", "portte"
VISIVEIS = ["published", "rectified", "contested", "paid"]  # lista: vai como array p/ ANY()

SQL_PARES = text(
    "SELECT n.id::text AS nosso_id, p.id::text AS deles_id, e.nome AS nome, "
    "       n.net_salary AS nosso_liq, p.net_salary AS deles_liq, "
    "       (n.net_salary - p.net_salary) AS delta "
    "FROM hr_payslips n "
    "JOIN hr_payslips p ON p.employee_id = n.employee_id "
    "                  AND p.reference_year = n.reference_year "
    "                  AND p.reference_month = n.reference_month "
    "                  AND p.source_system = :deles AND p.status = ANY(:vis) "
    "LEFT JOIN employees e ON e.id = n.employee_id "
    "WHERE n.source_system = :nosso AND n.status = 'draft' "
    "  AND n.reference_year = :ano AND n.reference_month = :mes "
    "ORDER BY abs(n.net_salary - p.net_salary) DESC, e.nome"
)

SQL_SEM_PAR = text(
    "SELECT count(*) FROM hr_payslips n WHERE n.source_system = :nosso "
    "  AND n.status = 'draft' AND n.reference_year = :ano AND n.reference_month = :mes "
    "  AND NOT EXISTS (SELECT 1 FROM hr_payslips p WHERE p.employee_id = n.employee_id "
    "                  AND p.reference_year = n.reference_year "
    "                  AND p.reference_month = n.reference_month "
    "                  AND p.source_system = :deles AND p.status = ANY(:vis))"
)

SQL_DESFAZER = text(
    "SELECT n.id::text AS nosso_id, p.id::text AS deles_id, e.nome AS nome "
    "FROM hr_payslips n "
    "JOIN hr_payslips p ON p.employee_id = n.employee_id "
    "                  AND p.reference_year = n.reference_year "
    "                  AND p.reference_month = n.reference_month "
    "                  AND p.source_system = :deles AND p.status = 'cancelled' "
    "LEFT JOIN employees e ON e.id = n.employee_id "
    "WHERE n.source_system = :nosso AND n.status = ANY(:vis) "
    "  AND n.reference_year = :ano AND n.reference_month = :mes ORDER BY e.nome"
)


async def _contagem(db, ano: int, mes: int) -> dict[str, int]:
    rows = (await db.execute(text(
        "SELECT coalesce(source_system,'?') AS origem, status, count(*) AS n "
        "FROM hr_payslips WHERE reference_year = :ano AND reference_month = :mes "
        "GROUP BY 1,2 ORDER BY 1,2"
    ), {"ano": ano, "mes": mes})).mappings().all()
    return {f"{r['origem']}/{r['status']}": r["n"] for r in rows}


def _mostrar(titulo: str, c: dict[str, int]) -> None:
    print(f"  {titulo}: " + (" · ".join(f"{k}={v}" for k, v in sorted(c.items())) or "vazio"))


async def _virar(db, linhas) -> None:
    """Publica os nossos — `publish()` despublica o par da Portte no MESMO commit."""
    repo = PaySlipRepository(db)
    for r in linhas:
        await repo.publish(uuid.UUID(r["nosso_id"]))


async def _desfazer(db, linhas) -> None:
    """Volta na ordem inversa: republica o da Portte e devolve o nosso ao rascunho."""
    repo = PaySlipRepository(db)
    for r in linhas:
        await repo.publish(uuid.UUID(r["deles_id"]))
        nosso = await repo.get_by_id(uuid.UUID(r["nosso_id"]))
        if nosso:
            nosso.status = "draft"
            nosso.published_at = None
            nosso.published_by = None
        await db.commit()


async def _dobrados(db, ano: int, mes: int) -> int:
    """Funcionários com MAIS DE UM holerite visível — o que a virada não pode deixar."""
    return (await db.execute(text(
        "SELECT count(*) FROM (SELECT employee_id FROM hr_payslips "
        "WHERE reference_year=:ano AND reference_month=:mes AND status = ANY(:vis) "
        "GROUP BY employee_id HAVING count(*) > 1) x"
    ), {"ano": ano, "mes": mes, "vis": VISIVEIS})).scalar() or 0


async def _simular(ano: int, mes: int) -> int:
    """Ensaio COMPLETO: vira, confere, desfaz, confere — e joga a transação fora.

    O ensaio normal (`Mutacao.confirmar`) mostra a lista mas não executa nada, então não
    prova que o caminho de volta funciona — e caminho de volta que nunca foi percorrido é
    promessa, não caminho. Aqui o ciclo inteiro roda de verdade contra o banco de verdade,
    dentro de uma transação externa que é descartada no fim.

    `join_transaction_mode="create_savepoint"` faz o `commit()` de dentro do repositório
    virar RELEASE SAVEPOINT: nada escapa. Sem isso, esta função publicaria o holerite de
    51 pessoas em produção — que é decisão do Jordan, não de um script de ensaio.
    """
    par = {"ano": ano, "mes": mes, "nosso": NOSSO, "deles": DELES, "vis": VISIVEIS}
    print(f"\n══ SIMULAÇÃO ida-e-volta — competência {mes:02d}/{ano} ══")
    print("   (roda de verdade contra o banco e descarta a transação no fim)\n")

    async with engine.connect() as conn:
        trans = await conn.begin()
        Sessao = async_sessionmaker(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        async with Sessao() as db:
            linhas = (await db.execute(SQL_PARES, par)).mappings().all()
            _mostrar("ANTES  ", await _contagem(db, ano, mes))
            if not linhas:
                print("\nNenhum par a virar nesta competência. Nada provado.")
                await trans.rollback()
                return 1

            await _virar(db, linhas)
            _mostrar("VIRADA ", await _contagem(db, ano, mes))
            dobrados = await _dobrados(db, ano, mes)
            print(f"           funcionários com mais de um holerite visível: {dobrados}")

            await _desfazer(db, linhas)
            _mostrar("VOLTA  ", await _contagem(db, ano, mes))
            volta = await _contagem(db, ano, mes)

        await trans.rollback()

    # a testemunha é uma sessão NOVA: a de dentro não serve para provar que nada vazou
    async with async_session_factory() as db:
        agora = await _contagem(db, ano, mes)
    _mostrar("BANCO  ", agora)

    problemas = []
    if dobrados:
        problemas.append(f"a virada deixou {dobrados} funcionário(s) com dois holerites")
    if volta != agora:
        problemas.append(f"o caminho de volta NÃO restaurou o estado: {volta} ≠ {agora}")
    if problemas:
        for p in problemas:
            print(f"\n🔴 {p}")
        return 1
    print(f"\n✅ virada de {len(linhas)} par(es) e volta ao estado original, sem nenhum "
          f"funcionário com dois holerites visíveis em nenhum momento.")
    print("   Nada foi gravado: a transação foi descartada.")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--mes", type=int, required=True)
    ap.add_argument("--ano", type=int, required=True)
    ap.add_argument("--desfazer", action="store_true", help="caminho de volta")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--forcar", action="store_true")
    ap.add_argument("--simular", action="store_true",
                    help="roda o ciclo INTEIRO (virar → desfazer) e joga fora no fim")
    a = ap.parse_args()

    if a.simular:
        return await _simular(a.ano, a.mes)

    par = {"ano": a.ano, "mes": a.mes, "nosso": NOSSO, "deles": DELES, "vis": VISIVEIS}
    rumo = "DESFAZER a virada" if a.desfazer else "VIRAR a folha"
    m = Mutacao(f"{rumo} de {a.mes:02d}/{a.ano}", teto=20)

    async with async_session_factory() as db:
        antes = await _contagem(db, a.ano, a.mes)
        print(f"\n══ {rumo} — competência {a.mes:02d}/{a.ano} ══")
        _mostrar("ANTES ", antes)

        if a.desfazer:
            linhas = (await db.execute(SQL_DESFAZER, par)).mappings().all()
            alvos = [(r["nosso_id"][:8], f"{r['nome'] or '—'} — volta para a Portte")
                     for r in linhas]
        else:
            linhas = (await db.execute(SQL_PARES, par)).mappings().all()
            orfaos = (await db.execute(SQL_SEM_PAR, par)).scalar() or 0
            soma_abs = sum(abs(r["delta"] or 0) for r in linhas)
            alvos = [(r["nosso_id"][:8],
                      f"{r['nome'] or '—'} — nosso R$ {r['nosso_liq']:.2f} × "
                      f"Portte R$ {r['deles_liq']:.2f} · Δ R$ {r['delta']:+.2f}")
                     for r in linhas]
            print(f"  pares: {len(linhas)} · Σ|Δ| R$ {soma_abs:.2f}")
            if orfaos:
                # não é bloqueio: publicar quem não tem par da Portte não cria duplicidade.
                # Mas é fato que alguém tem que ver antes de apertar o botão.
                print(f"  ⚠️ {orfaos} rascunho(s) NOSSO(s) sem holerite da Portte no par — "
                      f"esses seriam publicados sem nada a despublicar")

        if not m.confirmar(alvos):
            print("\n(contagem de agora, para comparar depois)")
            _mostrar("AGORA ", await _contagem(db, a.ano, a.mes))
            return 0

        await (_desfazer if a.desfazer else _virar)(db, linhas)

        m.feito(len(linhas))
        depois = await _contagem(db, a.ano, a.mes)
        _mostrar("DEPOIS", depois)

        sobra = await _dobrados(db, a.ano, a.mes)
        if sobra:
            print(f"\n🔴 {sobra} funcionário(s) ficaram com MAIS DE UM holerite visível. "
                  f"Rode o caminho de volta: --desfazer --aplicar --forcar")
            return 1
        print("\nNenhum funcionário com mais de um holerite visível.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
