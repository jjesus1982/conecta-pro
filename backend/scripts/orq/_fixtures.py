#!/usr/bin/env python3
"""Fixtures dos oráculos: acha usuário de teste por PAPEL, nunca por e-mail.

Quatro oráculos quebraram em 11/08/2026 porque hardcodavam `egonzaga@conectamais.pro` —
pessoa que saiu, 0 linhas em `users`. O que eles testam é o PAPEL (que tools um gestor
recebe), não aquela pessoa.

Amarrar teste a e-mail de gente é dívida garantida: quebra em toda saída, e a falha
aparece como se fosse defeito de produto — foi exatamente o que aconteceu, e três das
sete "falhas" do dia eram isto.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text


@dataclass
class _U:
    """Usuário mínimo que os oráculos precisam (id, papel, permissões)."""

    id: str
    role: str
    permissions: list = field(default_factory=list)


async def usuario_por_papel(db, papel: str) -> _U | None:
    """Primeiro usuário ATIVO com o papel pedido. None se não houver.

    Devolve None em vez de explodir para o chamador escolher entre pular honestamente
    ou falhar — nem todo papel existe em toda base.
    """
    r = (await db.execute(text(
        "SELECT id::text AS id, role, permissions FROM users "
        "WHERE role = :p AND coalesce(is_active, true) "
        "ORDER BY created_at NULLS LAST LIMIT 1"
    ), {"p": papel})).first()
    if not r:
        return None
    return _U(r.id, r.role, list(r.permissions or []))


async def usuario_por_papel_com_colaborador(db, papel: str) -> _U | None:
    """Usuário ativo com o papel pedido E vinculado a um colaborador (`employee_id`).

    Existe porque alguns oráculos exigem escopo pessoal (tier CLT precisa de
    `employee_id`; líder precisa de posto). Pegar qualquer usuário do papel devolveria
    um sem vínculo e a asserção falharia por motivo errado.
    """
    r = (await db.execute(text(
        "SELECT id::text AS id, role, permissions FROM users "
        "WHERE role = :p AND coalesce(is_active, true) AND employee_id IS NOT NULL "
        "ORDER BY created_at NULLS LAST LIMIT 1"
    ), {"p": papel})).first()
    if not r:
        return None
    return _U(r.id, r.role, list(r.permissions or []))


async def exigir_usuario_com_colaborador(db, papel: str) -> _U:
    """Como acima, mas falha dizendo o que fazer."""
    u = await usuario_por_papel_com_colaborador(db, papel)
    if u is None:
        raise AssertionError(
            f"nenhum usuário ativo com papel '{papel}' E employee_id — o oráculo precisa "
            f"de alguém com vínculo de colaborador para resolver escopo pessoal."
        )
    return u


async def exigir_usuario(db, papel: str) -> _U:
    """Como `usuario_por_papel`, mas falha com mensagem que diz o que fazer."""
    u = await usuario_por_papel(db, papel)
    if u is None:
        raise AssertionError(
            f"nenhum usuário ativo com papel '{papel}' — o oráculo não pode rodar. "
            f"Crie um usuário com esse papel ou ajuste o papel esperado no oráculo."
        )
    return u


if __name__ == "__main__":
    import asyncio
    import sys

    sys.path.insert(0, "/app")
    from core.database import async_session_factory

    async def _self_check() -> None:
        async with async_session_factory() as db:
            achou = 0
            for papel in ("admin", "lider", "funcionario"):
                u = await usuario_por_papel(db, papel)
                print(f"  {papel:<14} {'OK ' + u.id[:8] if u else 'nenhum'}")
                achou += 1 if u else 0
            assert achou >= 2, "esperava achar pelo menos admin e lider"
            assert await usuario_por_papel(db, "papel_que_nao_existe") is None
            try:
                await exigir_usuario(db, "papel_que_nao_existe")
            except AssertionError as exc:
                assert "não pode rodar" in str(exc)
            else:
                raise AssertionError("exigir_usuario deveria ter falhado")
            print("self-check OK")

    asyncio.run(_self_check())
