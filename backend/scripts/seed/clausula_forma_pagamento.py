"""Insere a cláusula de forma de pagamento aprovada pelo Jordan (23/08) nos dois modelos.

Numeração adaptada a cada instrumento, e só ela: o contrato de manutenção tem 3.1/3.2/3.3,
então o texto entra como 3.4 — "parágrafo único" só existe quando o artigo tem UM parágrafo,
e ali teria quatro. No de portaria, a cláusula é texto corrido e o rótulo aprovado cabe.
"""
import asyncio
from sqlalchemy import text
from core.database import async_session_factory

CORPO = ("Os pagamentos serão efetuados à CONTRATADA por PIX, boleto bancário ou "
         "transferência, exclusivamente na seguinte conta de titularidade da CONTRATADA: "
         "{{dados_bancarios}}. Comprovante de pagamento em conta diversa da aqui indicada "
         "não quita a obrigação.")

ALVOS = [
    ("de86045d-9c7c-46d5-83ec-4d0907ead116", "PORTARIA",  f"Parágrafo único. {CORPO}"),
    ("8f2c1a44-3d5e-4b90-9c71-6ea2d0f45b18", "MANUTENÇÃO", f"3.4. {CORPO}"),
]
MARCA = "CLÁUSULA QUARTA"


async def m():
    async with async_session_factory() as db:
        for tid, nome, paragrafo in ALVOS:
            t = (await db.execute(text(
                "SELECT content_template FROM contract_templates WHERE id::text=:i"),
                {"i": tid})).scalar()
            if "dados_bancarios" in t:
                print(f"  {nome}: JÁ tem a cláusula — não duplico"); continue
            if t.count(MARCA) != 1:
                print(f"  {nome}: ABORTADO — '{MARCA}' aparece {t.count(MARCA)}x, não sei onde inserir")
                continue
            novo = t.replace(MARCA, f"{paragrafo}\n\n{MARCA}", 1)
            await db.execute(text(
                "UPDATE contract_templates SET content_template=:c, updated_at=now() "
                "WHERE id::text=:i"), {"c": novo, "i": tid})
            print(f"  {nome}: cláusula inserida (+{len(novo)-len(t)} chars)")
        await db.commit()
asyncio.run(m())
