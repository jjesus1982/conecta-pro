"""A lista de kits da competência é a dos CONTRATOS ATIVOS nela — e o CNPJ tem de bater.

DUAS REGRAS, uma fonte. `contracts` é a única das três parametrizações que sabe QUANDO o
contrato vale: `condominios.tipo_servico` é um valor por condomínio, sem vigência;
`gedeon_kit_config` só tem `ativo`. Sem vigência, a lista de kits de uma competência é chute
— e agosto e setembro de 2026 têm listas DIFERENTES, medido:

    Segurança Eletrônica — VILLA DOS PÁSSAROS   2026-01-01 → 2026-08-31   ENCERRA em agosto
    Portaria Remota — HAWK EYE                  2026-08-01 → sem fim      ENTRA em agosto
    Manutenção — PARQUE DOS FRANCESES           2026-08-01 → 2027-07-06   1ª nota e 1º boleto

**Regra 1 — vigência.** Nunca fixe a lista em código nem derive de `tipo_servico`. Isto é o
que impede setembro sair com a lista de agosto.

**Regra 2 — CNPJ.** Kit trabalhista (`kit_mensal`) é da CONECTAMAIS PATRIMONIAL; NF e boleto
de eletrônica são da CONECTAMAIS ELETRONICA. Errar CNPJ em documento trabalhista é problema
fiscal, não estético.

🔴 O QUE ESTA REGRA PEGOU NO PRIMEIRO DIA, medido em 14/08/2026:

    CONDOMINIO PARQUE RESIDENCIAL GELAIN
      contrato de portaria_remota, emitente CONECTAMAIS ELETRONICA, kit_mensal = TRUE
      funcionários da Conecta alocados no posto: ZERO

Um kit TRABALHISTA marcado num contrato de eletrônica, sem uma única pessoa para constar
nele. Ou o `kit_mensal` está marcado por engano, ou o contrato está na empresa errada — as
duas leituras são problema, e nenhuma é minha para decidir.

⚠️ NÃO É FOTOGRAFIA: não fixa "7 kits" nem nomes de cliente. Deriva tudo de `contracts` a
cada rodada, então continua valendo quando o Green Hills entrar em setembro e o Villa dos
Pássaros sair da eletrônica.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date

sys.path.insert(0, os.environ.get("APP_ROOT", "/app"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402

#: Quem emite o quê. O nome vem de `empresas.nome_fantasia`; comparo por trecho para não
#: quebrar se alguém acertar o acento amanhã.
PATRIMONIAL, ELETRONICA = "patrimonial", "eletr"

SQL_ATIVOS = text(
    "SELECT c.id::text AS id, coalesce(cl.name,'—') AS cliente, "
    "       c.kit_mensal, coalesce(c.tipo_servico,'') AS servico, "
    "       lower(coalesce(e.nome_fantasia,'')) AS emitente, "
    "       c.start_date, c.end_date "
    "FROM contracts c "
    "LEFT JOIN clients cl ON cl.id = c.client_id "
    "LEFT JOIN empresas e ON e.id = c.empresa_id "
    "WHERE lower(coalesce(c.status::text,'')) = 'active' "
    "  AND c.start_date <= :fim "
    "  AND coalesce(c.end_date, CAST('9999-12-31' AS date)) >= :ini"
)


async def main() -> None:
    ini, fim = date(2026, 8, 1), date(2026, 8, 31)

    async with async_session_factory() as db:
        ativos = (await db.execute(SQL_ATIVOS, {"ini": ini, "fim": fim})).mappings().all()
        assert ativos, "nenhum contrato ativo na competência — o oráculo não teria o que provar"

        # regra 2 — kit trabalhista SÓ pela Patrimonial
        fora_da_patrimonial = [
            r for r in ativos
            if r["kit_mensal"] and PATRIMONIAL not in r["emitente"]
        ]
        if fora_da_patrimonial:
            det = "; ".join(
                f'{r["cliente"][:28]} ({r["servico"] or "sem tipo"}) → '
                f'{r["emitente"] or "SEM EMPRESA"}'
                for r in fora_da_patrimonial
            )
            raise AssertionError(
                f"{len(fora_da_patrimonial)} contrato(s) com kit_mensal fora da "
                f"Patrimonial — {det}"
            )
        kits = [r for r in ativos if r["kit_mensal"]]
        print(f"OK kit_mensal: {len(kits)} contrato(s), todos pela Patrimonial")

        # regra 2, o inverso — eletrônica não emite kit trabalhista, mas emite NF/boleto
        eletronica = [r for r in ativos if ELETRONICA in r["emitente"] and not r["kit_mensal"]]
        print(f"OK eletrônica: {len(eletronica)} contrato(s) a faturar na competência")

        # regra 1 — a lista muda com a competência. Se agosto e setembro derem a MESMA
        # composição, ou a vigência não está sendo lida, ou o mês não virou nada — e nos
        # dois casos alguém precisa olhar antes de montar kit.
        set_ini, set_fim = date(2026, 9, 1), date(2026, 9, 30)
        setembro = (await db.execute(
            SQL_ATIVOS, {"ini": set_ini, "fim": set_fim})).mappings().all()
        ids_ago = {r["id"] for r in ativos}
        ids_set = {r["id"] for r in setembro}
        assert ids_ago != ids_set, (
            "agosto e setembro têm exatamente os mesmos contratos — a vigência "
            "(start_date/end_date) não está separando as competências"
        )
        saem = len(ids_ago - ids_set)
        entram = len(ids_set - ids_ago)
        print(f"OK vigência separa as competências: {len(ids_ago)} em agosto, "
              f"{len(ids_set)} em setembro ({saem} sai(em), {entram} entra(m))")

        # suspenders: contrato ativo SEM empresa emitente não pode existir — é o caminho
        # silencioso para documento sair com CNPJ errado ou nenhum.
        sem_emitente = [r for r in ativos if not r["emitente"]]
        assert not sem_emitente, (
            f"{len(sem_emitente)} contrato(s) ativo(s) sem empresa emitente: "
            + ", ".join(r["cliente"][:24] for r in sem_emitente[:5])
        )
        print(f"OK todos os {len(ativos)} contratos ativos têm empresa emitente")

    print("TEST oraculo_kit_por_contrato PASS")


if __name__ == "__main__":
    asyncio.run(main())
