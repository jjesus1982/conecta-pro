"""Oráculo: render com variável faltando FALHA — nunca gera PDF com lacuna.

É a trava mais importante deste módulo. Contrato que sai com `{{ valor_mensal_fmt }}`
impresso, ou com "CNPJ nº " seguido de nada, vai para assinatura assim. Erro visível é
melhor que documento silenciosamente incompleto.

Guarda DUAS falhas distintas, porque o Jinja só pega a primeira:
  · variável AUSENTE do contexto  → StrictUndefined estoura (motor do DP)
  · variável PRESENTE porém VAZIA → StrictUndefined deixa passar; quem barra é a
    verificação `variaveis_vazias`, escrita justamente para fechar esse buraco.

Roda no container.
"""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.crm.services import contract_render as R

MODELO = "de86045d-9c7c-46d5-83ec-4d0907ead116"
CASO = "CTR-2026-00019"


async def main() -> None:
    async with async_session_factory() as db:
        tpl = (await db.execute(text(
            "SELECT name, service_type, content_template, clauses FROM contract_templates "
            "WHERE id::text = :t"), {"t": MODELO})).mappings().first()
        assert tpl, "modelo de referência sumiu"
        ctx, _ = await R.montar_contexto(db, CASO, dict(tpl))

        # 1 · AUSENTE — o motor do DP tem de estourar
        parcial = dict(ctx)
        parcial.pop("valor_mensal_fmt")
        try:
            R.renderizar(tpl["content_template"], parcial)
            raise AssertionError("render passou SEM valor_mensal_fmt — StrictUndefined não está ativo")
        except R.RenderError:
            print("OK 1 · variável ausente derruba o render (StrictUndefined ativo)")

        # 2 · VAZIA — o Jinja deixaria passar; a verificação própria tem de pegar
        vazio = dict(ctx)
        vazio["contratada_cnpj"] = ""
        faltas = R.variaveis_vazias(vazio, tpl["content_template"])
        assert "contratada_cnpj" in faltas, (
            "variável vazia passou despercebida — geraria contrato com 'CNPJ nº ' em branco")
        renderiza_mesmo_assim = R.renderizar(tpl["content_template"], vazio)
        assert "{{" not in renderiza_mesmo_assim, "sanidade: Jinja não deveria deixar marcação"
        print(f"OK 2 · variável vazia é barrada antes do PDF ({len(faltas)} detectada(s))")

        # 3 · o contexto COMPLETO passa — senão a trava viraria bloqueio permanente
        assert not R.variaveis_vazias(ctx, tpl["content_template"]), (
            "o contexto completo do caso de aceite tem variável vazia — a trava está apertada demais")
        print("OK 3 · contexto completo renderiza (a trava não é bloqueio permanente)")


if __name__ == "__main__":
    asyncio.run(main())
