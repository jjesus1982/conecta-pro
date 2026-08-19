"""Oráculo: contrato renderizado por MODELO traz o texto jurídico inteiro.

O defeito que ele guarda: até 19/08 o ERP registrava o contrato e não guardava o contrato.
`GET /contracts/{id}/pdf` montava um molde fixo de 3 páginas com nome, valor e vigência,
enquanto o contrato real — 12 cláusulas, 27 mil caracteres — vivia num .docx fora do
sistema. Isso custou uma tarde ao Jordan.

Afirma a REGRA, não a fotografia: para TODO contrato que tenha modelo e dado completo, o
texto renderizado contém TODAS as cláusulas declaradas no modelo. Não fixa "12" nem o nome
do Green Hills — se amanhã o modelo tiver 14 cláusulas, o oráculo continua valendo.

Roda no container.
"""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.crm.services.contract_render import RenderError, renderizar_contrato

# O caso que originou tudo. Fica explícito porque é o teste de aceite do Jordan.
CASO = "CTR-2026-00019"
MODELO = "de86045d-9c7c-46d5-83ec-4d0907ead116"


async def main() -> None:
    async with async_session_factory() as db:
        res = await renderizar_contrato(db, CASO, MODELO)

        assert not res.clausulas_faltando, (
            f"{len(res.clausulas_faltando)} cláusula(s) do modelo não apareceram no texto: "
            + "; ".join(res.clausulas_faltando[:3]))
        assert res.n_clausulas >= 10, (
            f"o modelo só declara {res.n_clausulas} cláusulas — contrato de portaria tem 12; "
            "modelo truncado gera contrato incompleto")
        assert "{{" not in res.texto and "{%" not in res.texto, (
            "sobrou marcação Jinja no texto renderizado — isso vai impresso para a assinatura")
        assert len(res.pdf) > 40_000, f"PDF pequeno demais ({len(res.pdf)} bytes) — molde de 3 páginas?"
        print(f"OK 1 · {CASO}: {res.n_clausulas} cláusulas, todas presentes · "
              f"texto {len(res.texto)} chars · PDF {len(res.pdf) // 1024} KB")

        # a regra vale para QUALQUER contrato com modelo e dado completo, não só o caso
        outros = (await db.execute(text("""
            SELECT c.contract_number FROM contracts c
            WHERE c.template_id IS NOT NULL AND coalesce(c.is_active, true)
              AND c.contract_number <> :caso
            LIMIT 5"""), {"caso": CASO})).scalars().all()
        checados = 0
        for num in outros:
            try:
                r = await renderizar_contrato(db, num)
            except RenderError:
                continue  # recusa por dado faltando é comportamento CERTO, não falha
            assert not r.clausulas_faltando, f"{num}: cláusula do modelo ausente no texto"
            checados += 1
        print(f"OK 2 · a regra vale além do caso: {checados} outro(s) contrato(s) renderizado(s) "
              f"sem cláusula faltando ({len(outros) - checados} recusado(s) por dado incompleto)")


if __name__ == "__main__":
    asyncio.run(main())
