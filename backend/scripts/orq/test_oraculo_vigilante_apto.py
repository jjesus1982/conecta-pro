"""Oráculo — ninguém ESCALADO HOJE está inapto como vigilante, e nenhuma arma existe sem controle (frente 05, 12/09/2026).

Por que existe: vigilante com reciclagem vencida em posto é interdição, não multa. E o modo de
falha da casa não é "a data está errada", é "a data não está" — 12 pessoas sem telefone no
cadastro provam que o dado faltante é a regra. Um `coalesce` transformaria ausência em "válido".

O que afirma (a régua vive em `hr/services/conformidade_vigilante`, importada, não copiada):
  1. A regra pura `avaliar()` trata ausência como inaptidão e data passada como vencida — afirmado
     com datas fixas, para que o oráculo não vire uma fotografia do banco.
  2. Todo escalado hoje SUJEITO à régua (função exige credencial; sem a chave
     `vigilante.funcoes_exigem_credencial`, todos) tem CNV com validade futura E curso/reciclagem
     com `vence_em` futuro. SEM DATA reprova.
  3. Nenhuma arma sem controle: flag `porte_arma` sem entrega por série, ou posto armado com gente
     escalada e sem arma em posse.
  4. O DDL da frente está aplicado (sem `vigilante_cursos`, nenhum curso pode existir — e a
     varredura da meia-noite precisa dizer isso com nome, não com traceback).

Estado medido no nascimento (12/09/2026, staging = cópia de produção): 28 escalados hoje, 0 com
CNV, 0 com curso, 0 vigilantes por cargo, chave de funções ausente → 28 "sem dado". VERMELHO
honesto: o sistema não sabe quem é vigilante nem quando a reciclagem vence. Verde só quando o DP
cadastrar a chave de funções e/ou cursos e CNV de quem estiver sujeito.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date


def _regra_pura() -> list[str]:
    from modules.people_management.hr.services.conformidade_vigilante import avaliar

    hoje = date(2026, 9, 12)
    casos = [
        ((None, None), 2, "ausência total"),
        ((date(2027, 1, 1), None), 1, "CNV ok, curso ausente"),
        ((None, date(2027, 1, 1)), 1, "curso ok, CNV ausente"),
        ((date(2026, 9, 11), date(2027, 1, 1)), 1, "CNV vencida ontem"),
        ((date(2027, 1, 1), date(2026, 9, 11)), 1, "reciclagem vencida ontem"),
        ((date(2026, 9, 12), date(2026, 9, 12)), 0, "vence hoje ainda vale"),
        ((date(2027, 1, 1), date(2027, 1, 1)), 0, "tudo válido"),
    ]
    falhas = []
    for (cnv, curso), n, rot in casos:
        got = avaliar(cnv, curso, hoje)
        if len(got) != n:
            falhas.append(f"regra pura — {rot}: esperava {n} motivo(s), veio {got}")
    return falhas


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db

    falhas = _regra_pura()
    gen = get_db()
    db = await gen.__anext__()

    ddl = (
        (
            await db.execute(
                text(
                    "SELECT to_regclass('vigilante_cursos') IS NOT NULL AS cursos, "
                    "to_regclass('equipamentos_controlados_alocacoes') IS NOT NULL AS aloc, "
                    "EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='employees' "
                    "AND column_name='nome_de_guerra') AS guerra"
                )
            )
        )
        .mappings()
        .one()
    )
    if not (ddl["cursos"] and ddl["aloc"] and ddl["guerra"]):
        falhas.append(
            f"DDL da frente 05 não aplicado neste banco: {dict(ddl)} — ver auditoria/frentes/FRENTE_05_vigilante.md"
        )
        for f in falhas:
            print("FALHOU:", f)
        raise AssertionError(f"{len(falhas)} desvio(s)")

    from modules.people_management.hr.services import conformidade_vigilante as cv

    funcoes = await cv.funcoes_exigem_credencial(db)
    escalados = await cv.aptidao(db, so_escalados_hoje=True)
    sujeitos = [p for p in escalados if p["sujeito"]]
    inaptos = [p for p in sujeitos if not p["apto"]]
    sem_dado = [p for p in inaptos if any("sem" in m for m in p["motivos"])]
    for p in inaptos:
        falhas.append(f"{p['nome']} ({p['cargo'] or 'sem cargo'} · {p['posto']}): " + "; ".join(p["motivos"]))

    armas = await cv.armas_sem_controle(db)
    for a in armas:
        falhas.append(f"arma sem controle — {a['nome']}: {a['motivo']}")

    print(
        f"escalados hoje: {len(escalados)} · sujeitos à régua: {len(sujeitos)} "
        f"({'chave de funções ausente → todos' if funcoes is None else 'funções: ' + ', '.join(funcoes)}) · "
        f"aptos: {len(sujeitos) - len(inaptos)} · inaptos: {len(inaptos)} (sem dado: {len(sem_dado)}) · "
        f"armas sem controle: {len(armas)}"
    )
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(
            f"{len(falhas)} desvio(s): vigilante escalado sem aptidão provada ou arma sem controle. "
            "Cadastrar curso/CNV em Gestão de Pessoas → Vigilante, ou definir a chave "
            f"`{cv.CHAVE_FUNCOES}` se a função não exige credencial."
        )
    print("OK vigilante: todo escalado sujeito à régua tem CNV e reciclagem válidas; toda arma tem série e responsável")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
