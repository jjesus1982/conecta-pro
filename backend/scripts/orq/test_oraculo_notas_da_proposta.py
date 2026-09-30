#!/usr/bin/env python3
"""Oráculo: a proposta pode misturar classes fiscais; a NOTA nunca pode.

O CENÁRIO 4 DO PROMPT é o que manda: uma proposta com material + instalação + posto de
portaria para o MESMO cliente tem de gerar TRÊS notas, cada uma da empresa certa. Se
sair uma nota só, ou alguma com emitente errado, o cenário falhou.

Por que isto precisa de oráculo e não bastava o código estar certo: a regra já estava
ESCRITA no mapa de capacidades do ERP desde agosto, e mesmo assim 47 notas de
«Vigilância» (mão de obra) foram emitidas pela ELETRÔNICA. Regra documentada e não
executada é regra que não existe.

Afirma a REGRA, não a fotografia — monta as propostas, mede, e desmonta tudo no fim.
"""

import asyncio
import sys
from datetime import date

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402
from modules.crm.services import classe_fiscal as cf  # noqa: E402
from modules.crm.services import notas_da_proposta as nn  # noqa: E402

MARCA = "ORACULO NOTAS DA PROPOSTA - NAO USAR"
falhas: list[str] = []


def checar(nome, cond, detalhe=""):
    print(f"{'ok   ' if cond else 'FALHA'} {nome}" + ("" if cond else f" — {detalhe}"))
    if not cond:
        falhas.append(f"{nome} — {detalhe}")


async def _proposta(db, titulo, itens) -> str:
    pid = (
        await db.execute(
            text(
                "INSERT INTO proposals (id, number, version, client_name, title, proposal_type,"
                " subtotal, discount_value, taxes, total, installments, issue_date, status, notes,"
                " is_active, created_at, updated_at)"
                " VALUES (gen_random_uuid(), :n, 1, 'Cliente do oraculo', :t, 'mixed',"
                " 0,0,0, :tot, 1, current_date, 'draft', :m, true, now(), now()) RETURNING id::text"
            ),
            {"n": f"ORQ-{titulo[:14]}", "t": titulo, "m": MARCA, "tot": sum(i[2] for i in itens)},
        )
    ).scalar()
    for ordem, (nome, classe, valor) in enumerate(itens):
        await db.execute(
            text(
                "INSERT INTO proposal_items (id, proposal_id, empresa_id, name, unit, quantity,"
                " unit_price, discount_percent, total, sort_order, is_optional, is_active,"
                " created_at, updated_at, classe_fiscal)"
                " VALUES (gen_random_uuid(), CAST(:p AS uuid), CAST(:e AS uuid), :n, 'un', 1,"
                " :v, 0, :v, :o, false, true, now(), now(), :c)"
            ),
            {
                "p": pid,
                "e": cf.empresa_da_classe(classe) if classe else cf.ELETRONICA,
                "n": nome,
                "v": valor,
                "o": ordem,
                "c": classe,
            },
        )
    await db.commit()
    return pid


async def _limpar(db):
    await db.execute(
        text("DELETE FROM proposal_items WHERE proposal_id IN (SELECT id FROM proposals WHERE notes = :m)"),
        {"m": MARCA},
    )
    await db.execute(text("DELETE FROM proposals WHERE notes = :m"), {"m": MARCA})
    await db.commit()


async def main() -> int:
    async with async_session_factory() as db:
        await cf.garantir_colunas(db)
        await _limpar(db)
        try:
            # ── CENÁRIO 4: as três classes na mesma proposta ────────────────────────────
            pid = await _proposta(
                db,
                "cenario4 mista",
                [
                    ("Leitor facial", "material", 4800.0),
                    ("Instalacao do controle de acesso", "servico_tecnico", 1800.0),
                    ("Posto de portaria 12x36", "mao_de_obra", 8900.0),
                ],
            )
            r = await nn.preview(db, pid)
            checar("cenário 4 sem data_execucao é RECUSADO", not r["ok"], r)
            await nn.registrar_execucao(db, pid, data_execucao=date.today(), executado_por="oraculo")
            r = await nn.preview(db, pid)
            checar(
                "cenário 4 vira TRÊS notas",
                r["ok"] and r["quantidade"] == 3,
                f"ok={r['ok']} n={r.get('quantidade')} {r.get('erro', '')[:90]}",
            )
            if r["ok"]:
                por_classe = {n["classe_fiscal"]: n for n in r["notas"]}
                checar(
                    "material → ELETRÔNICA, e é NF-e",
                    por_classe["material"]["empresa_id"] == cf.ELETRONICA
                    and por_classe["material"]["documento"] == "NF-e",
                    por_classe.get("material"),
                )
                checar(
                    "servico_tecnico → ELETRÔNICA, NFS-e, ISS 5%",
                    por_classe["servico_tecnico"]["empresa_id"] == cf.ELETRONICA
                    and por_classe["servico_tecnico"]["iss_aliquota"] == 5.0,
                    por_classe.get("servico_tecnico"),
                )
                checar(
                    "mao_de_obra → PATRIMONIAL, NFS-e, ISS 0%",
                    por_classe["mao_de_obra"]["empresa_id"] == cf.PATRIMONIAL
                    and por_classe["mao_de_obra"]["iss_aliquota"] == 0.0,
                    por_classe.get("mao_de_obra"),
                )
                checar(
                    "só a mão de obra retém INSS",
                    "inss" in por_classe["mao_de_obra"]
                    and "inss" not in por_classe["servico_tecnico"]
                    and "inss" not in por_classe["material"],
                )
                checar(
                    "NF-e de material NÃO declara ISS (paga ICMS)",
                    por_classe["material"]["iss_aliquota"] is None and por_classe["material"]["tributo"] == "ICMS",
                    por_classe["material"],
                )
                checar(
                    "cada nota leva a conta do PRÓPRIO emitente",
                    "37099007-2" in por_classe["material"]["linha_bancaria"]
                    and "7382527-7" in por_classe["mao_de_obra"]["linha_bancaria"],
                    [n["linha_bancaria"] for n in r["notas"]],
                )
                checar(
                    "a soma das notas é o total da proposta",
                    abs(sum(n["valor"] for n in r["notas"]) - 15500.0) < 0.01,
                    sum(n["valor"] for n in r["notas"]),
                )

            # ── item sem classe ABORTA, e a mensagem NOMEIA o item ──────────────────────
            pid2 = await _proposta(db, "sem classe", [("Item sem classe", None, 100.0)])
            r2 = await nn.preview(db, pid2)
            checar("item sem classe fiscal ABORTA", not r2["ok"], r2)
            checar("e a recusa nomeia o item", "Item sem classe" in (r2.get("erro") or ""), r2.get("erro"))

            # ── tipo D (só material) não exige contrato mas exige execução ──────────────
            pid3 = await _proposta(db, "so material", [("Cabo UTP", "material", 300.0)])
            r3 = await nn.preview(db, pid3)
            checar(
                "só material → tipo D e recusa sem execução",
                not r3["ok"] and "data_execucao" in (r3.get("erro") or ""),
                r3.get("erro"),
            )
            await nn.registrar_execucao(db, pid3, data_execucao=date.today(), executado_por="oraculo")
            r3 = await nn.preview(db, pid3)
            checar(
                "só material → UMA nota, NF-e da Eletrônica",
                r3["ok"] and r3["quantidade"] == 1 and r3["notas"][0]["documento"] == "NF-e",
                r3,
            )

            # ── carimbo que contradiz a classe é recusado NA EMISSÃO também ─────────────
            pid4 = await _proposta(db, "carimbo torto", [("Leitor", "material", 100.0)])
            await db.execute(
                text("UPDATE proposal_items SET empresa_id = CAST(:e AS uuid) WHERE proposal_id = CAST(:p AS uuid)"),
                {"e": cf.PATRIMONIAL, "p": pid4},
            )
            await db.commit()
            await nn.registrar_execucao(db, pid4, data_execucao=date.today(), executado_por="oraculo")
            r4 = await nn.preview(db, pid4)
            checar(
                "material carimbado com a Patrimonial é RECUSADO na emissão",
                not r4["ok"] and "PATRIMONIAL" in (r4.get("erro") or ""),
                r4.get("erro"),
            )
        finally:
            await _limpar(db)

    print()
    if falhas:
        print(f"VEREDITO: {len(falhas)} falha(s)")
        for f in falhas:
            print("  -", f)
        return 1
    print("VEREDITO: a proposta mistura, a nota separa — uma por classe, cada uma do seu CNPJ")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
