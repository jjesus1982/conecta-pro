#!/usr/bin/env python3
"""Puxa do BANCO os números que o site publica. Nada é digitado à mão.

Regra da casa: o que aparece na tela é o banco. Aqui vale igual — o site diz
"65 colaboradores" porque são 65 no ERP hoje, com a data ao lado. Se este script
não rodar, o gerador mostra selo de pendência em vez de número velho.

  python3 web/novo/atualizar_numeros.py
"""
import json
import pathlib
import subprocess
import sys
from datetime import date

# Consulta AMPLA de propósito. A primeira versão media só o que estava ativo
# HOJE e subdimensionava a empresa: 65 colaboradores quando 90 já passaram pelo
# quadro, 10 condomínios quando há 21 clientes. Número honesto e grande é melhor
# que número honesto e pequeno — e infinitamente melhor que número inflado, que
# é o único dado do site que o concorrente consegue conferir.
SQL = {
    "colaboradores_total": "select count(*) from employees",
    "colaboradores_hoje": "select count(*) from employees where is_active is true",
    "clientes": "select count(*) from clients",
    "postos": "select count(*) from posts",
    "alocacoes_total": "select count(*) from allocations",
}
# Receita Federal, CNPJ 35.710.481/0001-03: início de atividade em 05/12/2019.
# Dado público — inventar "10 anos de mercado" seria desmentido em dez segundos.
FUNDACAO = "2019-12-05"

PY_REMOTO = (
    "import asyncio,os,json,asyncpg\n"
    "async def m():\n"
    "    c=await asyncpg.connect(os.getenv('DATABASE_URL').replace('+asyncpg',''))\n"
    "    r={}\n"
    f"    for k,s in {SQL!r}.items():\n"
    "        try: r[k]=await c.fetchval(s)\n"
    "        except Exception: r[k]=None\n"
    "    print('JSON:'+json.dumps(r))\n"
    "    await c.close()\n"
    "asyncio.run(m())\n"
)


def main() -> int:
    saida = subprocess.run(
        ["docker", "exec", "conecta-pro-backend", "python3", "-c", PY_REMOTO],
        capture_output=True, text=True, timeout=120,
    )
    linha = next((x for x in saida.stdout.splitlines() if x.startswith("JSON:")), None)
    if not linha:
        print("não consegui ler o banco — o site vai mostrar pendência, não número velho")
        print(saida.stderr[-400:])
        return 1
    dados = json.loads(linha[5:])
    hoje = date.today()
    dados["apurado_em"] = hoje.isoformat()
    dados["fundacao"] = FUNDACAO
    dados["anos"] = (hoje - date(2019, 12, 5)).days // 365
    dados["dias_operacao"] = (hoje - date(2019, 12, 5)).days
    destino = pathlib.Path(__file__).parent / "numeros.json"
    destino.write_text(json.dumps(dados, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"  {destino}")
    for k, v in dados.items():
        print(f"    {k:16} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
