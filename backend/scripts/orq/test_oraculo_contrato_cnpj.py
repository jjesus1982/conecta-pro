"""Oráculo: contrato de MÃO DE OBRA nunca sai pela Eletrônica — e o inverso.

Regra do Jordan (19/08): mão de obra sai pela CONECTAMAIS PATRIMONIAL (66.014.833/0001-10),
eletrônica pela CONECTAMAIS ELETRONICA (35.710.481/0001-03).

Por que existe: o .docx de origem do Green Hills assinava um contrato de PORTARIA com o
CNPJ da Eletrônica, e o contrato no banco (CTR-2026-00019) ainda aponta `empresa_id` da
Eletrônica. Errar CNPJ em contrato de prestação é problema fiscal e trabalhista, não
estético — e o erro já estava lá, gravado.

Roda no container.
"""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.crm.services import contract_render as R

CNPJ_PAT = "66.014.833/0001-10"
CNPJ_ELE = "35.710.481/0001-03"


async def main() -> None:
    # 1 · a regra pura, sem banco
    for ts in ("maodeobra", "mao_de_obra", "portaria_mao_de_obra", "limpeza"):
        c = R.resolver_contratada(ts, None)
        assert c.cnpj == CNPJ_PAT, f"'{ts}' saiu por {c.cnpj} — mão de obra é Patrimonial"
    for ts in ("manutencao_cftv", "portaria_remota", "seguranca_eletronica"):
        c = R.resolver_contratada(ts, None)
        assert c.cnpj == CNPJ_ELE, f"'{ts}' saiu por {c.cnpj} — eletrônica é Eletrônica"
    print("OK 1 · a regra separa os dois CNPJs por tipo de serviço")

    # 2 · sem fonte, RECUSA — não chuta
    for a, b in ((None, None), ("", None), (None, "")):
        try:
            R.resolver_contratada(a, b)
            raise AssertionError(f"resolveu contratada sem tipo de serviço ({a!r},{b!r}) — chutou o CNPJ")
        except R.RenderError:
            pass
    print("OK 2 · sem tipo de serviço, recusa em vez de chutar")

    # 3 · contradição entre contrato e modelo RECUSA
    try:
        R.resolver_contratada("manutencao_cftv", "portaria_mao_de_obra")
        raise AssertionError("aceitou contrato de CFTV com modelo de mão de obra")
    except R.RenderError:
        print("OK 3 · contradição contrato×modelo recusa")

    # 4 · no DADO REAL: nenhum contrato de mão de obra renderiza com o CNPJ da Eletrônica
    async with async_session_factory() as db:
        alvos = (await db.execute(text(
            "SELECT contract_number FROM contracts WHERE tipo_servico::text ILIKE '%maodeobra%' "
            "AND coalesce(is_active,true) LIMIT 12"))).scalars().all()
        conferidos = 0
        for num in alvos:
            try:
                res = await R.renderizar_contrato(db, num)
            except R.RenderError:
                continue  # recusa por dado incompleto é comportamento certo
            assert CNPJ_ELE.replace(".", "").replace("/", "").replace("-", "") not in \
                res.texto.replace(".", "").replace("/", "").replace("-", ""), \
                f"{num} é mão de obra e o texto traz o CNPJ da Eletrônica"
            assert res.contratada.cnpj == CNPJ_PAT, f"{num} saiu por {res.contratada.cnpj}"
            conferidos += 1
        print(f"OK 4 · {conferidos} contrato(s) de mão de obra renderizado(s), nenhum pela Eletrônica "
              f"({len(alvos) - conferidos} recusado(s) por dado incompleto)")


if __name__ == "__main__":
    asyncio.run(main())
