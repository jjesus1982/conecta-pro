#!/usr/bin/env python3
"""Caçador: nota mandando o cliente pagar na conta de OUTRA empresa do grupo.

O QUE ACONTECEU (prompt 2 [6], medido em 30/09/2026)
A discriminação da NFS-e leva os dados bancários como TEXTO COLADO. Texto colado
envelhece, e quatro notas da PATRIMONIAL mandaram o cliente pagar no Inter com o CNPJ
da ELETRÔNICA:

    nº  1  25/06  R$ 42.544,50  Residencial Laranjeiras Village
    nº  2  25/06  R$ 42.544,50  Residencial Laranjeiras Village
    nº  3  25/06  R$ 42.544,50  Residencial Laranjeiras Village
    nº 22  20/08  R$  3.879,60  Condomínio Prime Arena
                  R$ 131.513,10 apontados para o CNPJ errado

O Jordan citou a nº 22. São quatro, e as três de junho são as maiores.

O ERRO TEM DIREÇÃO, e isso explica a causa: ZERO notas da Eletrônica citam a Cora. A
Patrimonial nasceu depois; quem redigia a discriminação dela copiava a da Eletrônica e
esquecia a linha do banco. Não é descuido aleatório, é herança de modelo.

A REGRA AFIRMADA
A discriminação de uma nota NÃO pode citar o CNPJ de outra empresa do grupo. O dado
bancário é atributo do EMITENTE (ver `crm/services/classe_fiscal.linha_bancaria`), e
citar o CNPJ do irmão é sempre erro — nunca há razão legítima.

NÃO CORRIGE NADA. Nota autorizada é decisão do contador; o que este caçador faz é
impedir que o número cresça sem ninguém ver.
"""

import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

#: SEM filtro de `cancelada` no SQL, de propósito: a contagem da população vem primeiro,
#: e o filtro aparece na SAÍDA. Na primeira versão eu filtrei aqui e o caçador disse «1
#: nota, R$ 42.544,50» — verdade, mas escondia que havia 4 com o defeito e 3 canceladas.
#: «1 achado» e «1 achado de 4» pedem conversas diferentes com o contador.
SQL = """
SELECT e.slug AS emitente, n.numero, n.data_emissao::date AS quando,
       coalesce(n.valor_servicos,0) AS valor, n.tomador_nome,
       coalesce(n.cancelada,false) AS cancelada,
       outra.slug AS cnpj_citado
  FROM nfse_emitidas_nacional n
  JOIN empresas e     ON e.id = n.empresa_id
  JOIN empresas outra ON outra.id <> n.empresa_id
 WHERE n.ambiente = 'producao'
   AND n.descricao ~ regexp_replace(outra.cnpj, '[^0-9]', '[^0-9]?', 'g')
 ORDER BY n.data_emissao
"""


#: DECLARADAS. Nota JA AUTORIZADA e decisao do contador, nao minha — e uma trava que fica
#: vermelha para sempre por algo que ninguem pode consertar deixa de ser lida. Cada linha
#: aqui e um item na mesa do Jordan, com o motivo escrito. Nota NOVA com o mesmo defeito
#: nao esta nesta lista e acende.
DECLARADAS = {
    ("conecta_patrimonial", "3"): (
        "R$ 42.544,50, Laranjeiras Village, 25/06/2026. Autorizada e VIVA, apontando para "
        "o Inter/Eletronica. Cancelar e reemitir e decisao do contador; as notas 1 e 2, "
        "mesmo valor e mesmo dia, ja foram canceladas."
    ),
}


async def main() -> int:
    async with async_session_factory() as db:
        linhas = (await db.execute(text(SQL))).mappings().all()

    novas = [r for r in linhas if not r["cancelada"] and (r["emitente"], str(r["numero"])) not in DECLARADAS]
    vivas = [r for r in linhas if not r["cancelada"]]
    canceladas = [r for r in linhas if r["cancelada"]]

    for r in linhas:
        chave = (r["emitente"], str(r["numero"]))
        marca = "cancelada   " if r["cancelada"] else "declarada   " if chave in DECLARADAS else "CONTA ERRADA"
        print(
            f"{marca}  {r['emitente']:<20} nº {r['numero']:>4}  {r['quando']}  "
            f"R$ {float(r['valor'] or 0):>12,.2f}  cita o CNPJ da {r['cnpj_citado']}"
            f"  · {(r['tomador_nome'] or '')[:34]}"
        )

    vivo = sum(float(r["valor"] or 0) for r in vivas)
    print(
        f"\n{len(linhas)} nota(s) com o CNPJ do irmao na discriminacao - "
        f"{len(canceladas)} cancelada(s) - {len(vivas)} VIVA(s), R$ {vivo:,.2f} - "
        f"{len(novas)} NAO declarada(s)"
    )
    for (emit, num), motivo in DECLARADAS.items():
        print(f"  declarada {emit} no {num}: {motivo}")
    if novas:
        print(
            "\nNota NOVA mandando pagar na conta errada - o dinheiro entra na empresa "
            "errada e a conciliacao nunca fecha."
        )
        print("A linha bancaria tem de vir de `classe_fiscal.linha_bancaria(empresa_id)`, nunca de texto colado.")
        return 1
    print("VEREDITO: nenhuma nota NOVA aponta para a conta da outra empresa.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
