"""Prova o roteamento por tier (sem chamar o LLM): cada identidade real recebe o tier
e o conjunto de tools corretos. Gestor NUNCA recebe tool de financeiro."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _fixtures import exigir_usuario_com_colaborador, exigir_usuario_com_escopo  # noqa: E402

from core.database import async_session_factory  # noqa: E402
from modules.ai.conversation.controllers.consultor_escopado_controller import (  # noqa: E402
    _resolver_tier_e_tools,
)

# O oráculo não pede PAPEL nem PESSOA: pede o ESCOPO que ele afirma. Duas versões já
# quebraram aqui — por e-mail (`egonzaga@conectamais.pro` saiu da empresa) e por papel
# (`supervisor`, que em 18/09/2026 não tem NENHUM ativo). Ver `exigir_usuario_com_escopo`.
ESCOPO_GESTOR = {"dp", "ged", "operacional", "sst"}


async def main() -> None:
    async with async_session_factory() as db:
        # GESTOR
        gonzaga, quem = await exigir_usuario_com_escopo(db, ESCOPO_GESTOR)
        print(f"gestor de hoje: {quem}")
        scope, tools = await _resolver_tier_e_tools(db, gonzaga)
        nomes = {t.name for t in tools}
        assert scope.tier == "gestor", scope
        assert "panorama_operacional" in nomes and "panorama_financeiro" not in nomes, nomes
        # self de DADO (meu_ponto, meu_holerite…) é o que o gestor não pode ter. A meta-tool
        # `o_que_voce_faz` (F4, 23/08/2026) é módulo "self" por ser sobre o próprio agente e
        # vai para todo tier — o oráculo congelava "nenhuma self" e reprovava a melhoria.
        self_dado = [t.name for t in tools if t.module == "self" and t.name != "o_que_voce_faz"]
        assert not self_dado, f"gestor não deve ter tools self de dado: {self_dado}"
        print("OK gestor: tier=gestor, módulos org-wide, SEM financeiro/self")

        # LÍDER — precisa de vínculo de colaborador para o escopo de posto resolver
        erika = await exigir_usuario_com_colaborador(db, "lider")
        scope, tools = await _resolver_tier_e_tools(db, erika)
        nomes = {t.name for t in tools}
        assert scope.tier == "lider" and scope.post_ids, scope
        assert "posto_escala_hoje" in nomes and "meu_ponto" in nomes and "justificar_ajuste_de_ponto" in nomes, nomes
        print("OK líder: tier=lider, posto-scoped + self + justificar")

        # CLT
        celiane = await exigir_usuario_com_colaborador(db, "funcionario")
        scope, tools = await _resolver_tier_e_tools(db, celiane)
        nomes = {t.name for t in tools}
        assert scope.tier == "clt" and scope.employee_id, scope
        # A regra, não a fotografia. Este assert já foi `nomes == {…4 tools…}` e passou a
        # reprovar uma MELHORIA: o auto-atendimento ganhou meu_trct_doc, meu_aviso_previo_doc,
        # meu_espelho_ponto_doc e meu_holerite_doc — todas self, todas legítimas. Lista
        # congelada transforma cada capacidade nova em "falha". O que importa é o INVARIANTE:
        # o núcleo continua lá e nada org-wide entra.
        NUCLEO_CLT = {"meu_ponto", "meu_holerite", "minha_escala", "justificar_ajuste_de_ponto"}
        assert nomes >= NUCLEO_CLT, f"CLT perdeu tool do núcleo: {NUCLEO_CLT - nomes}"
        vazou = {n for n in nomes if n.startswith(("panorama_", "consultar_", "listar_"))}
        assert not vazou, f"CLT recebeu tool org-wide: {vazou}"
        assert not any(t.module in ("operacional", "financeiro") for t in tools), nomes
        print(f"OK CLT: tier=clt, {len(nomes)} tools self (núcleo + docs), nenhuma org-wide")
    print("TEST endpoint_roteamento PASS")


if __name__ == "__main__":
    asyncio.run(main())
