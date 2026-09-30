#!/usr/bin/env python3
"""Oráculo: a fronteira entre os dois CNPJs é decidida pela CLASSE, nunca chutada.

O QUE ESTE ORÁCULO IMPEDE DE VOLTAR (medido em 30/09/2026)
`proposal_items.empresa_id` é NOT NULL desde 28/08. Nada resolvia esse campo no caminho
do POST /crm/proposals: o item chegava ao INSERT com None, o Postgres devolvia
NotNullViolationError e o FastAPI transformava em 500 "Internal Server Error". Seis
chamadas do Jordan morreram assim no mesmo dia, todas com a mesma mensagem muda.

Traceback real capturado antes da correção:
    asyncpg.exceptions.NotNullViolationError: null value in column "empresa_id"
    of relation "proposal_items" violates not-null constraint

Este oráculo afirma a REGRA, não a fotografia:
  1. item sem classe e sem empresa NÃO grava NULL — recusa NOMEANDO o item
  2. material e servico_tecnico saem pela Eletrônica; mao_de_obra pela Patrimonial
  3. material NUNCA sai pela Patrimonial, nem quando alguém carimba o item à mão
  4. a empresa padrão da proposta só alcança item que não declarou classe
"""

import sys

sys.path.insert(0, "/app")

from modules.crm.services.classe_fiscal import (  # noqa: E402
    ELETRONICA,
    PATRIMONIAL,
    derivar_tipo_negocio,
    recusa_por_empresa,
    resolver_empresa_dos_itens,
)

falhas = []


def checar(nome, cond, detalhe=""):
    (print(f"ok    {nome}") if cond else falhas.append(f"{nome} — {detalhe}"))
    if not cond:
        print(f"FALHA {nome} — {detalhe}")


# 1. sem classe e sem empresa → recusa, e a recusa NOMEIA o item
itens = [{"name": "Item de teste"}]
faltando = resolver_empresa_dos_itens(itens, None)
checar("recusa item sem classe", len(faltando) == 1, f"faltando={faltando}")
checar("item continua sem empresa (nunca NULL no banco)", itens[0].get("empresa_id") is None, itens[0])
checar("a recusa nomeia o item", "Item de teste" in faltando[0], faltando)
checar(
    "a recusa ensina o que preencher",
    "classe_fiscal" in recusa_por_empresa(faltando),
    recusa_por_empresa(faltando)[:80],
)

# 2. a classe decide a empresa
casos = [("material", ELETRONICA), ("servico_tecnico", ELETRONICA), ("mao_de_obra", PATRIMONIAL)]
for classe, esperado in casos:
    it = [{"name": f"x {classe}", "classe_fiscal": classe}]
    assert not resolver_empresa_dos_itens(it, None)
    checar(
        f"{classe} → {'ELETRONICA' if esperado == ELETRONICA else 'PATRIMONIAL'}",
        it[0]["empresa_id"] == esperado,
        it[0],
    )

# 2b. aceita a classe escrita com acento/hífen (o operador digita, não escolhe de lista)
it = [{"name": "y", "classe_fiscal": "Mão-de-obra"}]
resolver_empresa_dos_itens(it, None)
checar("classe com acento e hífen é entendida", it[0].get("empresa_id") == PATRIMONIAL, it[0])

# 3. material NUNCA pela Patrimonial — nem pela empresa padrão, nem por carimbo à mão
it = [{"name": "Leitor facial", "classe_fiscal": "material"}]
resolver_empresa_dos_itens(it, "patrimonial")
checar("padrão patrimonial não arrasta material", it[0]["empresa_id"] == ELETRONICA, it[0])

it = [{"name": "Leitor facial", "classe_fiscal": "material", "empresa_id": PATRIMONIAL}]
faltando = resolver_empresa_dos_itens(it, None)
checar("carimbo contraditório é RECUSADO, não aceito em silêncio", len(faltando) == 1, it[0])
checar("a recusa explica a contradição", "PATRIMONIAL" in (faltando[0] if faltando else ""), faltando)

# 4. empresa padrão só alcança quem não declarou classe
itens = [{"name": "Posto 12x36", "classe_fiscal": "mao_de_obra"}, {"name": "Cabo UTP"}]
faltando = resolver_empresa_dos_itens(itens, "eletronica")
checar("padrão alcança o item sem classe", not faltando and itens[1]["empresa_id"] == ELETRONICA, itens)
checar("padrão NÃO sobrepõe a classe do outro item", itens[0]["empresa_id"] == PATRIMONIAL, itens[0])

# 5. tipo de negócio sai da NATUREZA, não do valor
checar("só material → D", derivar_tipo_negocio([{"classe_fiscal": "material"}]) == "D")
checar(
    "material + serviço técnico → B",
    derivar_tipo_negocio([{"classe_fiscal": "material"}, {"classe_fiscal": "servico_tecnico"}]) == "B",
)
checar("mão de obra → A", derivar_tipo_negocio([{"classe_fiscal": "mao_de_obra"}]) == "A")
checar("só serviço técnico avulso → C", derivar_tipo_negocio([{"classe_fiscal": "servico_tecnico"}]) == "C")
checar(
    "recorrente vence a derivação → A", derivar_tipo_negocio([{"classe_fiscal": "material"}], recorrente=True) == "A"
)
checar(
    "valor alto não muda o tipo (Maiápolis R$ 23.160 é avulso)",
    derivar_tipo_negocio([{"classe_fiscal": "servico_tecnico", "unit_price": 23160}]) == "C",
)

print()
if falhas:
    print(f"VEREDITO: {len(falhas)} falha(s)")
    for f in falhas:
        print("  -", f)
    sys.exit(1)
print("VEREDITO: a fronteira fiscal é decidida pela classe, e o que não tem classe é recusado")
