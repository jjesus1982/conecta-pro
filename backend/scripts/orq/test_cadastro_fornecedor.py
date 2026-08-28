"""Oráculo — o Jordan manda fornecedor pelo WhatsApp e ELE FICA GRAVADO (28/08/2026).

Ele perguntou "posso mandar os fornecedores pelo WhatsApp?". A medição da resposta: NÃO
existia ferramenta de fornecedor em lugar nenhum — nem no José Luís, nem no Bartolo. Ele
mandaria, o agente entenderia, e nada seria gravado. Os 58 da tabela são contrapartes de
pagamento (INSS, Receita, Prefeitura, TOTVS), 2 de tipo material, ZERO com telefone.

O que este oráculo defende:
  1. O SERVIDOR enxerga a tool (grafo real), e o CLIENTE não — cadastro é do dono.
  2. CAMINHO FELIZ: manda dois, gravou dois, e o telefone está lá. Presença de tool não é
     prova de nada — foi o que deixou a etapa 1 morta por duas horas hoje.
  3. NÃO DUPLICA: mandar o mesmo de novo atualiza, não cria um segundo. Fornecedor
     duplicado é pior que ausente — a cotação sai para o cadastro errado.
  4. NÃO SOBRESCREVE contato que já existe: recado apressado não apaga número certo.
"""
import asyncio
import re
import sys

sys.path.insert(0, "/app")

MARCA = "__ORACULO_FORN__"
FALHAS: list[str] = []


def checar(cond: bool, titulo: str, detalhe: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FALHA'} · {titulo}{(' — ' + detalhe) if detalhe else ''}")
    if not cond:
        FALHAS.append(titulo)


async def main() -> int:
    import main_production  # noqa: F401,PLC0415

    from sqlalchemy import select, text

    from core.database import async_session_factory
    from modules.financial.models.supplier import Supplier
    from modules.integrations.connectors.whatsapp import agent_service as A

    def nomes(sch):
        return {(x.get("function") or {}).get("name") for x in sch}

    checar("cadastrar_fornecedor" in nomes(A._tools_ativas(owner=True)),
           "o SERVIDOR entrega cadastrar_fornecedor ao DONO")
    checar("cadastrar_fornecedor" not in nomes(A._tools_ativas(owner=False)),
           "o CLIENTE não enxerga cadastrar_fornecedor")

    async with async_session_factory() as db:
        # limpa por NOME e por CNPJ: a 1ª versão usou um CNPJ inventado que JÁ EXISTIA no
        # banco, o cadastro virou atualização e seis checagens falharam por culpa da minha
        # entrada. Fixture tem de ser inequívoca, senão o oráculo mede o resíduo alheio.
        await db.execute(text("DELETE FROM suppliers WHERE name LIKE :m OR cpf_cnpj LIKE :c"),
                         {"m": f"{MARCA}%", "c": "999000%"})
        await db.commit()
    try:
        # 2 · caminho feliz — dois de uma vez, como ele vai mandar
        r = await A._tool_cadastrar_fornecedor({"fornecedores": [
            {"nome": f"{MARCA} Alfa Câmeras", "whatsapp": "(92) 99111-2222", "cnpj": "99.900.001/0001-11",
             "categoria": "seg_eletronica", "contato": "Marcos"},
            {"nome": f"{MARCA} Beta Cabos", "telefone": "92 98888-7777", "cnpj": "99900002000122",
             "categoria": "material"},
        ]})
        checar(len(r.get("criados") or []) == 2, "dois de uma vez viram DOIS cadastros",
               r.get("resumo", ""))

        async with async_session_factory() as db:
            linhas = (await db.execute(select(Supplier).where(
                Supplier.name.like(f"{MARCA}%")))).scalars().all()
            checar(len(linhas) == 2, "estão no banco de verdade", f"{len(linhas)} linha(s)")
            zaps = {re.sub(r"\D", "", x.whatsapp or "") for x in linhas}
            checar("92991112222" in zaps, "o telefone foi gravado, não só o nome",
                   f"{sorted(zaps)}")
            cats = {x.category for x in linhas}
            checar(cats == {"seg_eletronica", "material"}, "a categoria foi gravada", f"{cats}")

        # 3 · o mesmo de novo NÃO duplica
        r2 = await A._tool_cadastrar_fornecedor({"fornecedores": [
            {"nome": f"{MARCA} Alfa Câmeras", "contato": "Marcos Filho",
             "observacao": "melhor preço em bullet"}]})
        checar(not (r2.get("criados") or []), "mandar de novo NÃO cria um segundo",
               r2.get("resumo", ""))

        async with async_session_factory() as db:
            alfa = (await db.execute(select(Supplier).where(
                Supplier.name == f"{MARCA} Alfa Câmeras"))).scalars().first()
            checar(alfa is not None and alfa.contact_name == "Marcos",
                   "contato que JÁ existia não foi sobrescrito",
                   f"contato={getattr(alfa, 'contact_name', None)!r}")
            checar(getattr(alfa, "notes", None) == "melhor preço em bullet",
                   "campo VAZIO foi preenchido na segunda passada")

        # 4 · sem nome, recusa
        r3 = await A._tool_cadastrar_fornecedor({"fornecedores": [{"whatsapp": "92999999999"}]})
        checar(len(r3.get("recusados") or []) == 1, "fornecedor sem nome é RECUSADO")

        # 5 · sem CNPJ: recusa NOMEANDO o que falta, nunca inventa placeholder
        r4 = await A._tool_cadastrar_fornecedor({"fornecedores": [
            {"nome": f"{MARCA} Gama Sem Doc", "whatsapp": "92977776666"}]})
        rec = (r4.get("recusados") or [{}])[0]
        checar("CNPJ" in str(rec.get("motivo", "")),
               "cadastro NOVO sem CNPJ é recusado, nomeando o motivo", str(rec)[:80])
        async with async_session_factory() as db:
            n = (await db.execute(text("SELECT count(*) FROM suppliers WHERE name = :n"),
                                  {"n": f"{MARCA} Gama Sem Doc"})).scalar()
            checar(n == 0, "e NADA foi gravado com CNPJ inventado")
    finally:
        async with async_session_factory() as db:
            await db.execute(
                text("DELETE FROM suppliers WHERE name LIKE :m OR cpf_cnpj LIKE :c"),
                {"m": f"{MARCA}%", "c": "999000%"})
            await db.commit()

    print()
    if FALHAS:
        print(f"  ❌ {len(FALHAS)} FALHA(S): {', '.join(FALHAS)}")
        return 1
    print("  ✅ o que o Jordan manda pelo WhatsApp fica gravado, sem duplicar.")
    return 0


sys.exit(asyncio.run(main()))
