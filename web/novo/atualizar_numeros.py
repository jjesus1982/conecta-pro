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

SQL = {
    "colaboradores": "select count(*) from employees where is_active is true",
    "clientes": "select count(*) from condominiums",
    "postos": "select count(*) from posts where COALESCE(status,'active') in ('active','ativo')",
    "alocacoes": "select count(*) from allocations where COALESCE(status,'')='active'",
}

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
    dados["apurado_em"] = date.today().isoformat()
    destino = pathlib.Path(__file__).parent / "numeros.json"
    destino.write_text(json.dumps(dados, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"  {destino}")
    for k, v in dados.items():
        print(f"    {k:16} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
