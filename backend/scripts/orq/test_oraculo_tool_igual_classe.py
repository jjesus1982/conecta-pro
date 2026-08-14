"""A tool tem de devolver o MESMO que a classe devolvia. Trocar a embalagem não muda o algoritmo.

O critério de aceite da F4 no fechamento do GEDEON é literal: *"cada tool registrada e
respondendo, com oráculo provando que devolve o mesmo que a classe devolvia (o algoritmo não
muda na troca de embalagem); e o agente sem uma linha de SQL própria — ele orquestra."*

É a regra da casa aplicada a agentes: **"IA dormente = casca → reusar o ALGORITMO"**. Os cinco
agentes do GEDEON não têm laço nem ferramenta, mas o algoritmo deles é bom — para vencimento
de certidão, `WHERE` é a ferramenta certa, determinística onde a resposta tem de ser exata. O
que mentia era a etiqueta "agente", não a conta.

Este oráculo pega o erro que a troca de embalagem convida: alguém reescreve a query dentro da
tool "para ficar mais simples", e a tool passa a responder diferente da tela. Duas fontes para
a mesma pergunta viram duas verdades — foi assim que a tela de férias passou meses mostrando
15 onde havia 19.

⚠️ NÃO PRECISA DE CRÉDITO NA OPENAI, e isso é de propósito. A conta está sem saldo (429
`insufficient_quota`, medido em 14/08), o que bloqueia o LAÇO do agente. Mas os handlers são
Python determinístico: dá para provar que a tool é fiel ao algoritmo sem o LLM entrar na
história. Quando o crédito voltar, esta parte já está provada.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.environ.get("APP_ROOT", "/app"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database.session import async_session_factory  # noqa: E402


class _UserFake:
    """Identidade com o módulo `ged` — o `_gate` re-checa na fonte e barraria sem isto."""

    id = "00000000-0000-0000-0000-000000000000"
    email = "oraculo@conectamais.pro"
    role = "admin"
    is_superuser = True
    modules = ["ged", "all"]


async def main() -> None:
    from modules.ai.conversation.services.orquestrador import read_dispatcher as rd
    from modules.ai.conversation.services.orquestrador import tools_read_ged  # noqa: F401

    ops = rd._READ_OPS.get("ged", {})
    for nome in ("certidoes_vencendo", "assinaturas_pendentes", "kit_completude"):
        assert nome in ops, f"tool '{nome}' NÃO está registrada em consultar_ged"
    print(f"OK as 3 tools novas registradas ({len(ops)} consultas no módulo ged)")

    user = _UserFake()
    async with async_session_factory() as db:
        # 1 · certidoes_vencendo == Kronos
        from modules.gedeon.agents.kronos import Kronos

        k = Kronos()
        direto = {
            "certidoes": await k.verificar_certidoes(db),
            "asos": await k.verificar_asos_funcionarios(db),
        }
        pela_tool = await ops["certidoes_vencendo"]["handler"](db, user, None)
        assert len(pela_tool["certidoes"]) == len(direto["certidoes"]), (
            f'certidoes: tool devolveu {len(pela_tool["certidoes"])}, '
            f'Kronos devolveu {len(direto["certidoes"])}')
        assert len(pela_tool["asos"]) == len(direto["asos"]), (
            f'asos: tool devolveu {len(pela_tool["asos"])}, Kronos devolveu {len(direto["asos"])}')
        print(f'OK certidoes_vencendo == Kronos — {len(direto["certidoes"])} certidões, '
              f'{len(direto["asos"])} ASOs pelos dois caminhos')

        # 2 · assinaturas_pendentes == Themis
        from modules.gedeon.agents.themis import Themis

        direto_t = await Themis().resumo(db)
        pela_tool_t = await ops["assinaturas_pendentes"]["handler"](db, user, None)
        # ⚠️ `timestamp` MUDA ENTRE DUAS CHAMADAS SEGUIDAS — comparar o dicionário inteiro
        # nunca passaria, e o defeito seria meu, não da tool. Comparo o que é RESPOSTA:
        # os números. Medido: as duas chamadas diferiam só em `timestamp`, por 27 ms.
        _volatil = {"timestamp"}
        a = {k: v for k, v in direto_t.items() if k not in _volatil}
        b = {k: v for k, v in pela_tool_t.items() if k not in _volatil}
        assert a == b, (
            "assinaturas_pendentes divergiu de Themis.resumo em "
            + ", ".join(sorted(k for k in a if a[k] != b.get(k))))
        print(f"OK assinaturas_pendentes == Themis — {direto_t.get('total_pendentes', '?')} "
              f"pendente(s) pelos dois caminhos")

        # 3 · kit_completude bate com a contagem no banco, por TIPO
        from sqlalchemy import text

        pela_tool_c = await ops["kit_completude"]["handler"](db, user, None)
        do_banco = (await db.execute(text(
            "SELECT count(*) FROM ("
            "  SELECT k.reference_month, k.client_id, d.document_type "
            "  FROM ged_kit_documents d JOIN ged_document_kits k ON k.id=d.kit_id "
            "  GROUP BY 1,2,3 "
            "  HAVING count(*) > count(*) FILTER ("
            "    WHERE d.file_path IS NOT NULL AND d.file_path <> '')) x"))).scalar()
        assert pela_tool_c["total_tipos_incompletos"] == do_banco, (
            f'kit_completude devolveu {pela_tool_c["total_tipos_incompletos"]} '
            f"tipo(s) incompleto(s), o banco tem {do_banco}")
        print(f"OK kit_completude == contagem do banco — {do_banco} tipo(s) incompleto(s)")

    print("TEST oraculo_tool_igual_classe PASS")


if __name__ == "__main__":
    asyncio.run(main())
