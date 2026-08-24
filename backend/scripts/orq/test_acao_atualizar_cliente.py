#!/usr/bin/env python3
"""Oráculo: `atualizar_cliente` corrige CADASTRO, propõe, e não toca condição comercial.

Primeira das 14 lacunas de "editar registro que já existe". O motor in-process CRIAVA, LIA e
gerava documento — mas não EDITAVA: pelo chat o Jordan criava um cliente e anotava nele, e não
corrigia o CNPJ de um cliente já cadastrado.

⭐ O que este oráculo protege é o GRAU POR CAMPO. `atualizar_cliente` soa cadastral, e o MESMO
endpoint (`PUT /clients/{id}`) muda `credit_limit`, `payment_terms` e `status`. Decidir o grau
pelo NOME da tool é exatamente como o `tool_risk_manifest` errou 54 vezes: o nome diz cadastro
e o corpo faz dinheiro.

Quatro invariantes, e a última é a que separa proposta de execução:
  1. campo de CONDIÇÃO COMERCIAL é RECUSADO (não é proposto em 🟡 — é recusado)
  2. campo que não existe no cadastro é recusado
  3. cliente inexistente é recusado (nunca cria cliente "de passagem")
  4. campo cadastral vira RASCUNHO e o banco NÃO MUDA até alguém aprovar

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/test_acao_atualizar_cliente.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

#: ZZ FIXO: valor sintético que entra no rascunho. Se algum dia vazar para o cadastro, ordena
#: no fim de qualquer listagem em vez de se esconder no meio dos e-mails reais.
_MARCA = "ZZteste-oraculo@atualizar-cliente.local"


async def main() -> int:
    from sqlalchemy import select, text

    from core.database import async_session_factory
    from core.models.user import User
    import modules.ai.conversation.controllers.consultor_escopado_controller as C
    from modules.ai.conversation.services.orquestrador.agir_dispatcher import _ACOES
    from modules.ai.conversation.services.orquestrador.tools_acao_crm import (
        _propor_atualizar_cliente,
    )

    falhas: list[str] = []
    async with async_session_factory() as db:
        # ENTRADA: rascunho órfão de execução sem saída, por MARCA e nunca por id.
        await db.execute(text(
            "DELETE FROM agent_drafts WHERE tipo = 'atualizar_cliente' "
            "AND payload::text LIKE :m"), {"m": f"%{_MARCA}%"})
        await db.commit()

        if "atualizar_cliente" not in _ACOES.get("crm", {}):
            print("FALHOU: `atualizar_cliente` não está registrada em agir_crm")
            return 1

        u = (await db.execute(select(User).where(
            User.email == "jjesus@conectamais.pro"))).scalar_one()
        scope, _ = await C._resolver_tier_e_tools(db, u)
        cli = (await db.execute(text(
            "SELECT name FROM clients WHERE document_number IS NOT NULL LIMIT 1"))).scalar()
        if not cli:
            print("FALHOU: nenhum cliente com CNPJ — pré-condição do teste")
            return 1

        # 1 · condição comercial NÃO passa
        r = await _propor_atualizar_cliente(db, u, scope, cliente=cli, credit_limit=99999)
        if not r.get("erro"):
            falhas.append("credit_limit (condição comercial) foi ACEITO — o grau tem de sair "
                          "do CAMPO, não do nome da tool")

        # 2 · campo inexistente
        r = await _propor_atualizar_cliente(db, u, scope, cliente=cli, cnpj_novo="x")
        if not r.get("erro"):
            falhas.append("campo inexistente no cadastro foi aceito")

        # 3 · cliente inexistente
        r = await _propor_atualizar_cliente(db, u, scope, cliente="ZZ_NAO_EXISTE",
                                            email=_MARCA)
        if not r.get("erro"):
            falhas.append("cliente inexistente foi aceito — nunca criar cliente de passagem")

        # 4 · cadastral vira rascunho E o banco não muda
        antes = (await db.execute(text("SELECT email FROM clients WHERE name = :n"),
                                  {"n": cli})).scalar()
        r = await _propor_atualizar_cliente(db, u, scope, cliente=cli, email=_MARCA)
        if not (r.get("draft_id") or r.get("id")):
            falhas.append(f"campo cadastral não virou rascunho: {str(r)[:110]}")
        depois = (await db.execute(text("SELECT email FROM clients WHERE name = :n"),
                                   {"n": cli})).scalar()
        if antes != depois:
            falhas.append(f"A PROPOSTA GRAVOU no cadastro: {antes!r} → {depois!r}")

        # SAÍDA: por marca, sempre.
        await db.execute(text(
            "DELETE FROM agent_drafts WHERE tipo = 'atualizar_cliente' "
            "AND payload::text LIKE :m"), {"m": f"%{_MARCA}%"})
        await db.commit()

    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        return 1
    print(f"OK atualizar_cliente: 4/4 — recusa comercial, campo inexistente e cliente "
          f"inexistente; cadastral vira rascunho e o cadastro de {cli[:28]!r} não mudou")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
