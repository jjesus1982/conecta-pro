#!/usr/bin/env python3
"""Protocolo não é entrega: o que declaramos transmitido ao eSocial × o que o governo tem.

🏛️ SÓ LEITURA. Transmitir em QA gera evento REAL no eSocial. Este oráculo não transmite,
não retransmite e não escreve nada — ele só compara dois lados.

O DEFEITO QUE ELE VIGIA. O afastamento do RAILSON COELHO BATISTA está
`esocial_status='transmitida'` com protocolo `1.2.202607.0000000000217663514`, e o espelho
do governo tem ZERO eventos para o CPF dele. Nenhum dos 9 oráculos internos do DP pega
isso, e a razão é estrutural: **o nosso lado está coerente consigo mesmo**. Protocolo é
recibo de POSTAGEM — prova que o lote saiu, não que o evento entrou.

MAS — E ESTA É A METADE QUE QUASE FICOU DE FORA — ausência no espelho só é prova DENTRO da
janela que o espelho cobre. Medido em 13/08/2026: das 367 janelas de consulta, apenas **3**
estão `consultada`; as outras 364 estão `pendente`. O CPF do Railson tem 7 janelas e
**nenhuma foi consultada**. Concluir "não foi entregue" a partir disso seria repetir o erro
que apagou 169 transações reais no financeiro — tratar "a fonte não tem linha aqui" como
"o fato não existe", quando a fonte simplesmente não foi lida.

Por isso o veredito tem TRÊS baldes, e só um reprova:

  CONFIRMADO     declaramos transmitido e o governo tem o evento. Nada a fazer.
  DIVERGENTE     declaramos transmitido, o governo FOI PERGUNTADO sobre aquele CPF numa
                 janela que cobre a data do evento, e não tem. **Isto reprova** — é o
                 protocolo sem entrega.
  NÃO VERIFICADO declaramos transmitido e ninguém perguntou ao governo. NÃO reprova, mas
                 aparece contado: é dívida de consulta, não defeito de transmissão.
                 O Railson cai AQUI, não em DIVERGENTE.

O oráculo fica verde com dívida de consulta de propósito. Reprovar por NÃO VERIFICADO
transformaria "não sabemos" em "está errado", que é fabricar conclusão — e um vermelho
permanente que ninguém consegue calar é um vermelho que todo mundo aprende a ignorar.

Receita:
  docker exec -e PYTHONPATH=/app conecta-pro-backend \\
    python3 /app/scripts/orq/test_oraculo_esocial_entrega.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402

#: Quem, do nosso lado, declara ter transmitido — e como ler cada um.
#: `data`: a data do FATO (exame, afastamento, acidente). É ela que tem que estar dentro da
#: janela consultada; usar a data da transmissão faria a cobertura parecer melhor do que é.
DECLARANTES = [
    {"tabela": "gp_asos", "tipo": "S-2220", "data": "data_realizacao",
     "recibo": "espelho_recibo"},
    {"tabela": "sst_afastamentos", "tipo": "S-2230", "data": "data_inicio",
     "recibo": "espelho_recibo"},
    {"tabela": "gp_cats", "tipo": "S-2210", "data": "data_acidente",
     "recibo": "espelho_recibo"},
    {"tabela": "sst_s2240_transmissoes", "tipo": "S-2240", "data": "transmitida_em",
     "recibo": "recibo_s2240"},
]

#: O que, no nosso vocabulário, quer dizer "eu declarei que isto chegou ao governo".
#: `rejeitada` e `erro` NÃO entram: elas já dizem que não chegou, e são honestas.
DECLARA_ENTREGUE = ("transmitida", "aceita")

SQL = """
SELECT e.nome AS nome, e.cpf AS cpf,
       d.{data}::date AS quando,
       d.{recibo} IS NOT NULL AS tem_recibo_espelho,
       EXISTS (SELECT 1 FROM esocial_eventos_espelho x
               WHERE x.cpf_trabalhador = e.cpf AND x.tipo = :tipo) AS no_espelho,
       EXISTS (SELECT 1 FROM esocial_espelho_janelas j
               WHERE j.cpf = e.cpf AND lower(coalesce(j.status,'')) = 'consultada'
                 AND d.{data}::date BETWEEN j.dt_ini::date AND j.dt_fim::date) AS coberto
FROM {tabela} d
JOIN employees e ON CAST(e.id AS TEXT) = CAST(d.employee_id AS TEXT)
WHERE lower(coalesce(d.esocial_status,'')) = ANY(:entregue)
  AND d.{data} IS NOT NULL
ORDER BY d.{data}
"""


async def classificar(db) -> tuple[list[str], list[str], list[str], tuple[int, int]]:
    """Os três baldes + a cobertura do espelho, na sessão que quem chama abrir.

    Recebe a sessão em vez de abrir a própria para que a prova do vermelho (rodar com uma
    janela marcada como consultada e depois descartar a transação) use ESTE código, e não
    uma cópia dele.
    """
    confirmados: list[str] = []
    divergentes: list[str] = []
    nao_verificados: list[str] = []

    cobertura = (await db.execute(text(
        "SELECT count(*) FILTER (WHERE lower(coalesce(status,''))='consultada') AS lidas, "
        "       count(*) AS total FROM esocial_espelho_janelas"
    ))).first()

    for d in DECLARANTES:
        linhas = (await db.execute(
            text(SQL.format(**d)), {"tipo": d["tipo"], "entregue": list(DECLARA_ENTREGUE)}
        )).mappings().all()
        for r in linhas:
            rotulo = f"{d['tipo']} {r['nome'] or '—'} ({r['quando']})"
            if r["tem_recibo_espelho"] or r["no_espelho"]:
                confirmados.append(rotulo)
            elif r["coberto"]:
                divergentes.append(rotulo)
            else:
                nao_verificados.append(rotulo)

    return confirmados, divergentes, nao_verificados, tuple(cobertura)


async def main() -> int:
    async with async_session_factory() as db:
        confirmados, divergentes, nao_verificados, cobertura = await classificar(db)

    lidas, total = cobertura
    print(f"cobertura do espelho: {lidas} de {total} janelas consultadas "
          f"({100 * lidas // total if total else 0}%)")
    print(f"CONFIRMADO     {len(confirmados)}")
    for x in confirmados:
        print(f"    {x}")
    print(f"NÃO VERIFICADO {len(nao_verificados)}  (declaramos, ninguém perguntou ao governo)")
    for x in nao_verificados:
        print(f"    {x}")
    print(f"DIVERGENTE     {len(divergentes)}  (o governo foi perguntado e não tem)")
    for x in divergentes:
        print(f"  ✗ {x}")

    if divergentes:
        print(f"FALHA: {len(divergentes)} evento(s) declarado(s) transmitido(s) que o "
              f"governo, PERGUNTADO, não reconhece — protocolo sem entrega")
        print("TEST oraculo_esocial_entrega FAIL")
        return 1

    if nao_verificados:
        print(f"\nSEM ÂNCORA EXTERNA: {len(nao_verificados)} evento(s) que declaramos ter "
              f"entregado e ninguém de fora confirma. Não é reprovação — é o que ainda não "
              f"foi perguntado. Para virar CONFIRMADO ou DIVERGENTE, o espelho precisa ser "
              f"consultado para esses CPFs.")
    print("TEST oraculo_esocial_entrega PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
