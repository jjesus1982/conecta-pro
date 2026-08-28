"""Oráculo — a fronteira entre os dois CNPJs no catálogo e nos itens (28/08/2026).

Escrito JUNTO com a migration, não depois. Coluna nova sem oráculo é onde nasce o NULL que
ninguém vê até o contrato errado sair assinado — e aqui "errado" custa retenção e INSS em
dobro, porque a Patrimonial está no Simples Anexo III e a Eletrônica no Lucro Real.

O que ele defende:
  1. NENHUM NULL. A migration é fail-closed, mas dado entra por outros caminhos.
  2. FK ÍNTEGRA: todo empresa_id existe em `empresas`.
  3. A REGRA DO JORDAN vale de fato: quem tem agente CLT nosso no posto é Patrimonial;
     portaria REMOTA é Eletrônica (tecnologia, sem agente).
  4. COERÊNCIA item↔produto: item cujo nome casa com o catálogo carrega a MESMA empresa.
  5. ⭐ CAMINHO FELIZ: uma proposta mista se divide em dois grupos por empresa. Se só
     testássemos "não há NULL", provaríamos que a porta fecha e nunca que ela abre — a
     lição que custou a etapa 1 hoje de manhã.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

ELETRONICA = "619a3df1-8bce-49ce-b77a-04f80a0e8491"
PATRIMONIAL = "7d79ed12-d480-4906-b2e0-2b2c4d299bab"

FALHAS: list[str] = []


def checar(cond: bool, titulo: str, detalhe: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FALHA'} · {titulo}{(' — ' + detalhe) if detalhe else ''}")
    if not cond:
        FALHAS.append(titulo)


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    async with async_session_factory() as db:
        for tab in ("crm_products", "proposal_items"):
            existe = (await db.execute(text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name=:t AND column_name='empresa_id'"), {"t": tab})).scalar()
            if not existe:
                checar(False, f"{tab}.empresa_id existe", "coluna ausente — migration não rodou")
                continue
            nulos = (await db.execute(text(
                f"SELECT count(*) FROM {tab} WHERE empresa_id IS NULL"))).scalar()  # noqa: S608
            checar(nulos == 0, f"{tab}: nenhum item sem empresa", f"{nulos} sem carimbo")
            orfaos = (await db.execute(text(
                f"SELECT count(*) FROM {tab} t WHERE t.empresa_id IS NOT NULL AND NOT EXISTS "  # noqa: S608
                "(SELECT 1 FROM empresas e WHERE e.id = t.empresa_id)"))).scalar()
            checar(orfaos == 0, f"{tab}: todo empresa_id existe em `empresas`", f"{orfaos} órfão(s)")

        if FALHAS:
            print("\n  ❌ a migration ainda não rodou — o resto não pode ser medido.")
            return 1

        # 3 · a regra do Jordan, nos dois sentidos
        erradas = (await db.execute(text(
            "SELECT count(*) FROM crm_products WHERE category ILIKE '%%mão de obra%%' "
            "AND empresa_id <> cast(:p AS uuid)"), {"p": PATRIMONIAL})).scalar()
        checar(erradas == 0, "todo item de MÃO DE OBRA é da Patrimonial", f"{erradas} fora")

        remotas = (await db.execute(text(
            "SELECT count(*) FROM crm_products WHERE unaccent(lower(name)) LIKE '%%remot%%' "
            "AND empresa_id <> cast(:e AS uuid)"), {"e": ELETRONICA})).scalar()
        checar(remotas == 0, "portaria REMOTA é da Eletrônica (dito pelo Jordan)",
               f"{remotas} fora")

        # 4 · item e produto de mesmo nome não podem divergir
        div = (await db.execute(text(
            "SELECT count(*) FROM proposal_items pi JOIN crm_products cp ON cp.name = pi.name "
            "WHERE pi.empresa_id <> cp.empresa_id"))).scalar()
        checar(div == 0, "item e produto de mesmo nome carregam a MESMA empresa",
               f"{div} divergente(s)")

        # 5 · CAMINHO FELIZ: a proposta mista se divide
        mistas = (await db.execute(text(
            "SELECT proposal_id, count(DISTINCT empresa_id) n FROM proposal_items "
            "GROUP BY 1 HAVING count(DISTINCT empresa_id) > 1"))).all()
        checar(len(mistas) > 0,
               "existe proposta MISTA e ela se divide por empresa",
               f"{len(mistas)} proposta(s) com itens das duas — viram 2 contratos")

    print()
    if FALHAS:
        print(f"  ❌ {len(FALHAS)} FALHA(S): {', '.join(FALHAS)}")
        return 1
    print("  ✅ fronteira íntegra: todo item sabe por qual CNPJ sai.")
    return 0


sys.exit(asyncio.run(main()))
