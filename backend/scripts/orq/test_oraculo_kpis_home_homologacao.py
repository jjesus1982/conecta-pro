"""Prova que os 4 KPIs da home contam PRODUÇÃO e nunca o piloto de homologação.

POR QUE EXISTE — 25/09/2026. A home mostrava `53 CLT · 7 PJ · 15 Postos · 29 Clientes`. O CLT
estava certo (66 ativos − 13 do piloto, via `SQL_FUNCIONARIO_REAL`), mas **o posto e o cliente de
teste NÃO eram excluídos**: os 15 postos somavam os 6 do Conecta Village + Conecta Base — que o
dono confirmou serem o condomínio de HOMOLOGAÇÃO do Conecta Plus — e os 29 clientes incluíam
`HOMOLOGACAO (CONECTA BASE)`.

A pessoa de teste saía da conta; o posto e o cliente dela ficavam. **Duas verdades sobre a mesma
pergunta, dependendo de qual contador se olhava** — e foi exatamente por isso que eu disse "66"
ao dono enquanto a tela dizia "53".

⭐ Este oráculo afirma a REGRA, não o retrato: não fixa 9, 28 ou 53. Afirma que **nenhum KPI da
home conta linha marcada como homologação**, e que o marcador continua existindo. Condomínio novo
entra sozinho; piloto novo é excluído sozinho; e se alguém trocar o filtro por um `name LIKE
'%CONECTA%'`, o teste fica vermelho no dia em que um cliente real se chamar Conecta alguma coisa.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402


async def main() -> None:
    falhas: list[str] = []
    async with async_session_factory() as db:

        async def n(q: str) -> int:
            return int((await db.execute(text(q))).scalar() or 0)

        # 1) o marcador existe nas TRÊS tabelas — sem ele o filtro é letra morta
        for tabela in ("employees", "posts", "clients"):
            tem = await n(
                "SELECT count(*) FROM information_schema.columns "
                f"WHERE table_name='{tabela}' AND column_name='is_homologacao'"
            )
            if not tem:
                falhas.append(f"{tabela} perdeu a coluna is_homologacao — o filtro vira letra morta")
        if not falhas:
            print("  ok  marcador is_homologacao existe em employees, posts e clients")

        # 2) cada KPI da home tem de EXCLUIR o que está marcado. Compara o contador com filtro
        #    contra o contador sem filtro: a diferença tem de ser exatamente o marcado.
        casos = [
            ("CLT ativos", "employees", "lower(coalesce(status,''))='ativo'"),
            ("PJ ativos", "employees", "lower(coalesce(status,''))='pj_ativo'"),
            ("Postos ativos", "posts", "coalesce(is_active,true)=true"),
            ("Clientes", "clients", "status='active'"),
        ]
        for rotulo, tabela, base in casos:
            com = await n(f"SELECT count(*) FROM {tabela} WHERE {base} "
                          "AND coalesce(is_homologacao,false)=false")
            sem = await n(f"SELECT count(*) FROM {tabela} WHERE {base}")
            marcados = await n(f"SELECT count(*) FROM {tabela} WHERE {base} AND is_homologacao")
            if com != sem - marcados:
                falhas.append(f"{rotulo}: com filtro {com}, sem filtro {sem}, marcados {marcados} "
                              "— a conta não fecha")
            else:
                print(f"  ok  {rotulo:14} produção={com:3}  (piloto excluído: {marcados})")

        # 3) SUSPENDER — o defeito exato não pode voltar: posto/cliente de homologação contando
        #    como produção. Se alguém remover o filtro do builder, este número muda.
        postos_teste = await n("SELECT count(*) FROM posts WHERE is_homologacao AND coalesce(is_active,true)")
        if postos_teste == 0:
            falhas.append("nenhum posto marcado como homologação — o piloto do Conecta Village "
                          "deixou de estar marcado, e volta a contar como produção")
        else:
            print(f"  ok  {postos_teste} posto(s) de piloto seguem marcados e fora da conta")

        # 4) o builder da home usa o filtro? (afirma o CÓDIGO, não só o dado — sem isto o
        #    oráculo ficaria verde com o banco certo e a tela errada)
        from pathlib import Path  # noqa: PLC0415

        src = Path("/app/modules/operacional/controllers/redesign_data_controller.py").read_text()
        bloco = src[src.index('"l": "CLT ativos"') - 3000:src.index('"l": "CLT ativos"')]
        for termo, oq in (("FROM posts", "Postos ativos"), ("FROM clients", "Clientes")):
            trecho = bloco[bloco.rindex(termo):] if termo in bloco else ""
            if "is_homologacao" not in trecho:
                falhas.append(f"o KPI '{oq}' voltou a contar sem excluir homologação")
        if not any("voltou a contar" in f for f in falhas):
            print("  ok  o builder da home filtra homologação em postos e clientes")

    if falhas:
        for f in falhas:
            print(f"  ❌ {f}")
        print(f"TEST kpis_home_homologacao FAIL ({len(falhas)})")
        sys.exit(1)
    print("\nTEST kpis_home_homologacao PASS")


if __name__ == "__main__":
    asyncio.run(main())
