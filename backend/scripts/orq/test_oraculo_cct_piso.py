#!/usr/bin/env python3
"""A folha respeita o piso da CCT — e todo ativo tem como ser conferido contra ele.

`cct_cargos` tem 51 cargos com piso, e o piso vira dinheiro na folha todo mês. Não havia
nenhuma checagem de que a folha o respeita. Pagar abaixo do piso da categoria é diferença
salarial devida com reflexos em férias, 13º, FGTS e INSS — e prescreve em cinco anos, não
no fechamento do mês.

Somos AGENTES DE PORTARIA, CCT SINDECOMPRESTS AM000613/2025. A base é o PISO da categoria
(R$1.670 em 2026), **nunca** o mínimo federal (R$1.621) — confundir os dois é a forma mais
fácil de pagar a menos e achar que está legal.

DUAS AFIRMAÇÕES, e a segunda é a que quase ficou de fora:

  (A) nenhum ativo com salário-base ABAIXO do piso do cargo dele na CCT;
  (B) todo ativo TEM vínculo com um cargo da CCT (`cct_cargo_id`) e salário-base.

Sem (B), (A) fica verde por não ter o que comparar — é o mesmo defeito do aviso prévio do
KEYSON, onde a regra lia um campo vazio e concluía "nada a alertar". Medido em 13/08: **3
de 52 ativos** não têm `cct_cargo_id` (ALEXANDRE, KELLY, NAILSON). Eram invisíveis para
qualquer conferência de piso, e continuariam invisíveis se este oráculo só olhasse quem já
está ligado. Foram 5 na primeira medição: dois eram cadastro de bancada
(`COLABORADOR TESTE HOMOLOGACAO`, `TESTE PONTO (JORDAN)`), excluídos junto com o total.

(B) NÃO reprova hoje, conta e aparece: os 3 são cadastro incompleto, não pagamento errado,
e um vermelho que só o DP pode calar preenchendo cadastro não deve travar a varredura
diária. (A) reprova.

Receita:
  docker exec -e PYTHONPATH=/app conecta-pro-backend \\
    python3 /app/scripts/orq/test_oraculo_cct_piso.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402

# `cct_cargo_id` é o vínculo REAL. Casar por nome de cargo não serve: medi e o texto diverge
# em acentuação ("AGENTE DE SERVIÇOS GERAIS" no cadastro × "SERVICOS" na CCT), e um LEFT
# JOIN por nome devolve piso NULO — que numa comparação `<` some silenciosamente e faz o
# oráculo dizer "nenhum abaixo do piso" sobre gente que ele nem olhou.
SQL_ABAIXO = text(
    "SELECT e.nome AS nome, e.cargo AS cargo, e.salario_base AS base, "
    "       c.piso_salarial AS piso, (c.piso_salarial - e.salario_base) AS falta "
    "FROM employees e JOIN cct_cargos c ON c.id = e.cct_cargo_id "
    "WHERE lower(coalesce(e.status,'')) = 'ativo' "
    "  AND e.salario_base IS NOT NULL AND c.piso_salarial IS NOT NULL "
    "  AND e.salario_base < c.piso_salarial "
    "ORDER BY (c.piso_salarial - e.salario_base) DESC"
)

# cadastros de bancada não entram na conta — a mesma exclusão de `test_oraculo_ponto_folha`,
# e pelo mesmo motivo: não são gente, e contá-los infla a dívida com ruído.
_NAO_E_GENTE = ("  AND upper(coalesce(e.nome,'')) NOT LIKE '%HOMOLOGA%' "
                "  AND upper(coalesce(e.nome,'')) NOT LIKE '%TESTE%' ")

SQL_SEM_VINCULO = text(
    "SELECT e.nome AS nome, coalesce(e.cargo,'—') AS cargo, "
    "       e.cct_cargo_id IS NULL AS sem_cct, e.salario_base IS NULL AS sem_base "
    "FROM employees e "
    "WHERE lower(coalesce(e.status,'')) = 'ativo' "
    "  AND (e.cct_cargo_id IS NULL OR e.salario_base IS NULL) "
    + _NAO_E_GENTE +
    "ORDER BY e.nome"
)


async def main() -> int:
    async with async_session_factory() as db:
        ativos = (await db.execute(text(
            "SELECT count(*) FROM employees e WHERE lower(coalesce(e.status,'')) = 'ativo' "
            + _NAO_E_GENTE
        ))).scalar()
        pisos = (await db.execute(text(
            "SELECT count(*) FROM cct_cargos WHERE is_active AND piso_salarial IS NOT NULL"
        ))).scalar()
        abaixo = (await db.execute(SQL_ABAIXO)).mappings().all()
        sem_vinculo = (await db.execute(SQL_SEM_VINCULO)).mappings().all()

    conferiveis = ativos - len(sem_vinculo)
    print(f"ativos: {ativos} · cargos com piso na CCT: {pisos} · "
          f"conferíveis contra o piso: {conferiveis}")

    print(f"(B) sem como conferir: {len(sem_vinculo)}")
    for r in sem_vinculo:
        falta = " · ".join(
            x for x in ("sem cct_cargo_id" if r["sem_cct"] else "",
                        "sem salario_base" if r["sem_base"] else "") if x
        )
        print(f"      {r['nome']} ({r['cargo']}) — {falta}")

    print(f"(A) abaixo do piso: {len(abaixo)}")
    for r in abaixo:
        print(f"    ✗ {r['nome']} ({r['cargo']}): base R$ {r['base']:.2f} < "
              f"piso R$ {r['piso']:.2f} — faltam R$ {r['falta']:.2f}/mês")

    if abaixo:
        print(f"FALHA: {len(abaixo)} ativo(s) com salário-base abaixo do piso da CCT — "
              f"diferença salarial devida, com reflexos em férias, 13º, FGTS e INSS")
        print("TEST oraculo_cct_piso FAIL")
        return 1

    if sem_vinculo:
        print(f"\nOS {len(sem_vinculo)} DE (B) NÃO ESTÃO APROVADOS — estão FORA DA CONTA. "
              f"Nenhuma conferência de piso os alcança enquanto o cadastro não ligar cargo "
              f"da CCT e salário-base. É cadastro, não pagamento errado, por isso não "
              f"reprova; mas o verde de (A) vale para {conferiveis} pessoas, não para "
              f"{ativos}.")
    print("TEST oraculo_cct_piso PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
