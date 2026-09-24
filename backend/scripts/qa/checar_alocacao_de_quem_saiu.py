#!/usr/bin/env python3
"""Alocação ATIVA de quem não trabalha mais: a cobertura do posto mente para cima.

Origem (13/09/2026): 4 pessoas demitidas entre 22/07 e 24/08 continuavam alocadas em
MICHELANGELO, LARANJEIRAS, PRIME ARENA e IDEAL FLORES. O painel contava as quatro como
vigilante alocado — e é justamente esse número que dispara o alarme de posto
descoberto. O alarme ficava calado com o posto vazio.

Ninguém errou ao não encerrar: a demissão entra por IMPORTAÇÃO (Sólides/Tangerino), e
nenhum caminho do app escreve em `employee_alocacoes`. Não há onde pendurar a baixa
automática — então a instrumentação é aqui: o descasamento aparece no dia seguinte em
vez de meses depois.

Encerrar é `ativo=false` e `data_fim = employees.data_demissao` (a alocação terminou
quando a pessoa saiu, não hoje).

    docker exec -e PYTHONPATH=/app conecta-pro-backend \
        python3 /app/scripts/qa/checar_alocacao_de_quem_saiu.py

Linha canônica: `TOTAL: <n> alocação(ões) ativa(s) de quem saiu`. Exit 1 se houver.

Fora do escopo de propósito: `status='suspenso'` SEM data de demissão. Suspensão é
temporária e a pessoa volta para o mesmo posto — encerrar ali perderia o vínculo.

DUAS TABELAS, e esta trava enxergava UMA (corrigido em 24/09/2026)
------------------------------------------------------------------
A casa tem **duas** tabelas de alocação vivas, e esta trava só lia `employee_alocacoes`:

    allocations .......... 89 linhas, 69 ativas, 67 pessoas — importada por 69 módulos
    employee_alocacoes ... 73 linhas, 51 ativas, 51 pessoas — importada por 21 módulos

Medido em 24/09: a trava acusou **1** caso (Meire, no Villa dos Pássaros) e havia mais
**4** em `allocations` que ela não via — Fernando Miguel (demitido 22/07, Michelangelo),
Daniel Souza (24/08, Ideal Flores), Jonathan Mendes (22/07, Laranjeiras) e uma linha com
o próprio dono em status `candidato` alocado no Villa Dei Fiori.

A lição é a de sempre nesta casa: **conte a população antes**. Trava que lê uma tabela
quando existem duas mede a coisa errada e devolve verde de mentira.

Enquanto as duas existirem, esta trava lê as DUAS e diz de qual veio cada achado.
Unificar as tabelas é outra frente; enquanto não acontece, a vigilância não pode escolher
uma e torcer.
"""

from __future__ import annotations

import asyncio
from pathlib import Path


async def main() -> int:
    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415

    if not Path("/app/scripts").is_dir():
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    async with async_session_factory() as db:
        #: As DUAS tabelas de alocação, na mesma forma. `origem` vai para a saída: quem for
        #: encerrar precisa saber em qual tabela mexer, e elas têm nomes de coluna diferentes.
        FONTES = (
            (
                "employee_alocacoes",
                "SELECT e.nome, e.status, e.data_demissao, "
                "       coalesce(c.nome,'(posto sem nome)') AS posto, a.funcao, a.data_inicio "
                "FROM employee_alocacoes a "
                "JOIN employees e ON e.id = a.employee_id "
                "LEFT JOIN condominios c ON c.id = a.condominio_id "
                "WHERE a.ativo = true "
                "  AND e.data_demissao IS NOT NULL "
                "  AND e.data_demissao <= CURRENT_DATE",
            ),
            (
                "allocations",
                "SELECT e.nome, e.status, e.data_demissao, "
                "       coalesce(cl.name,'(posto sem nome)') AS posto, a.role, a.start_date "
                "FROM allocations a "
                "JOIN employees e ON e.id = a.employee_id "
                "LEFT JOIN posts p ON p.id = a.post_id "
                "LEFT JOIN clients cl ON cl.id = p.client_id "
                "WHERE a.is_active = true AND a.status = 'active' "
                "  AND e.data_demissao IS NOT NULL "
                "  AND e.data_demissao <= CURRENT_DATE",
            ),
        )
        linhas = []
        for origem, sql in FONTES:
            for r in (await db.execute(text(sql + " ORDER BY e.data_demissao"))).all():
                linhas.append((*r, origem))

        # O suspenso não é achado, mas é informação: se virar demissão, vira achado.
        suspensos = (
            await db.execute(
                text(
                    "SELECT count(*) FROM employee_alocacoes a JOIN employees e ON e.id=a.employee_id "
                    "WHERE a.ativo=true AND e.status='suspenso' AND e.data_demissao IS NULL"
                )
            )
        ).scalar() or 0

    for nome, status, dem, posto, funcao, ini, origem in linhas:
        dias = ""
        try:
            from datetime import date  # noqa: PLC0415

            dias = f", {(date.today() - dem).days} dias atrás"
        except Exception:  # noqa: BLE001
            pass
        print(f"   {posto:<16} {nome} — {funcao}")
        print(f"      saiu em {dem} (status '{status}'{dias}), alocado desde {ini} e ainda contando")
        print(f"      tabela: {origem} — encerrar é nela, e as colunas diferem entre as duas")

    if suspensos:
        print(f"\n   ({suspensos} alocação(ões) de gente suspensa — fora do escopo, suspensão é temporária)")
    print(f"\nTOTAL: {len(linhas)} alocação(ões) ativa(s) de quem saiu")
    return 1 if linhas else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
