"""Prova: buscar_documento_condominio entrega documento do PRÓPRIO condomínio (link/metadata),
é só BUSCA (não escreve nada — buscar != emitir), o filtro é por scope.client_id (nunca por
argumento), e injeção de client_id como kwarg é inerte.

Reforço no padrão do tier cliente (test_tools_cliente.py): dois clientes reais (GREEN HILLS /
PRIME ARENA) com conteúdo disjunto — prova que o documento de B nunca aparece na busca de A.
Read-only.

NOTA (divergência do brief): a invariante "buscar != emitir" checa as tabelas que
portal_financeiro_service REALMENTE consulta (inter_cobrancas, receivable_accounts p/ boletos;
nfse_emitidas_nacional p/ notas) — o brief citava `inter_payments`, que é a tabela de PAGAMENTOS
enviados (dinheiro que sai), não de cobranças recebidas; manter o nome original teria testado a
tabela errada e mascarado um INSERT real em inter_cobrancas."""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.ai.conversation.services.orquestrador.engine import OrqScope
from modules.ai.conversation.services.orquestrador import tool_registry as tr
from modules.ai.conversation.services.orquestrador import tools_cliente  # noqa: F401

GREEN_HILLS = "b4a13504-cffc-4505-8e91-e1bebed493ed"  # cliente A
PRIME_ARENA = "52958919-0a15-4e4f-806d-be3c75e5951b"  # cliente B (real)


def _descricoes(out: dict) -> set:
    return {str(d.get("descricao")) for d in (out.get("documentos") or [])}


async def _contagens(db) -> tuple:
    n_cobrancas = (await db.execute(text("SELECT count(*) FROM inter_cobrancas"))).scalar()
    n_receivable = (await db.execute(text("SELECT count(*) FROM receivable_accounts"))).scalar()
    n_nfse = (await db.execute(text("SELECT count(*) FROM nfse_emitidas_nacional"))).scalar()
    return n_cobrancas, n_receivable, n_nfse


async def main() -> None:
    async with async_session_factory() as db:
        tool = tr.get_tool("buscar_documento_condominio")
        assert tool is not None, "tool de documento não registrada"

        # 1) boleto do próprio condomínio: retorna estrutura de documentos OU 'aguardando dado' honesto
        out = await tool.handler(db, None, OrqScope(tier="cliente", client_id=GREEN_HILLS), tipo="boleto")
        assert ("documentos" in out) or (out.get("status") == "aguardando dado"), out
        print("OK boleto: entrega documento do próprio condomínio (ou aguardando dado honesto)")

        # 2) buscar != emitir: nenhum boleto/nota NOVO foi criado (contagens das tabelas-fonte inalteradas)
        antes = await _contagens(db)
        out2 = await tool.handler(db, None, OrqScope(tier="cliente", client_id=GREEN_HILLS), tipo="nota")
        depois = await _contagens(db)
        assert antes == depois, ("BUSCA não pode criar nada (buscar != emitir)", antes, depois)
        assert ("documentos" in out2) or (out2.get("status") == "aguardando dado"), out2
        print("OK buscar != emitir (nada criado em inter_cobrancas/receivable_accounts/nfse_emitidas_nacional)")

        # 3) sem client_id => aguardando dado
        out3 = await tool.handler(db, None, OrqScope(tier="cliente", client_id=None), tipo="boleto")
        assert out3.get("status") == "aguardando dado", out3
        print("OK sem client_id => aguardando dado")

        # 4) REFORÇO — isolamento por conteúdo entre A e B: nota de B nunca aparece na busca de A
        out_a = await tool.handler(db, None, OrqScope(tier="cliente", client_id=GREEN_HILLS), tipo="nota")
        out_b = await tool.handler(db, None, OrqScope(tier="cliente", client_id=PRIME_ARENA), tipo="nota")
        docs_a, docs_b = _descricoes(out_a), _descricoes(out_b)
        assert docs_a and docs_b, ("ambos clientes precisam ter notas p/ o teste", docs_a, docs_b)
        assert docs_a.isdisjoint(docs_b), ("VAZAMENTO: nota de B apareceu na busca de A", docs_a & docs_b)
        print(f"OK isolamento por conteúdo (nota): A={len(docs_a)} docs, B={len(docs_b)} docs, disjuntos")
        print("OK pedir documento de outro condomínio nunca revela existência (filtro é scope.client_id, sem id de doc como arg)")

        # 5) REFORÇO — injeção de client_id como kwarg é INERTE (handler descarta via **_)
        out_inj = await tool.handler(
            db, None, OrqScope(tier="cliente", client_id=GREEN_HILLS), tipo="nota", client_id=PRIME_ARENA
        )
        assert _descricoes(out_inj) == docs_a, ("INJEÇÃO VAZOU: kwarg client_id alterou o escopo", out_inj)
        assert _descricoes(out_inj).isdisjoint(docs_b), "INJEÇÃO trouxe dado de B"
        print("OK injeção de client_id como kwarg é inerte (escopo continua o do token)")
    print("TEST tool_documento_cliente PASS")


if __name__ == "__main__":
    asyncio.run(main())
