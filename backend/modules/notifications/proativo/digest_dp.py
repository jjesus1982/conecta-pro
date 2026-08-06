"""Digest diário do DP — "bom dia, N itens te esperam".

O sino é o CORAÇÃO (in-app, tempo quase real). Este digest é COMPLEMENTO: um resumo por
e-mail 1×/dia para a Pyetra não precisar ficar olhando a Central. Sem WhatsApp/Telegram
(regra do projeto: notificação interna = sino).

O que ele NÃO faz, de propósito:
  • não envia sozinho aqui — `montar_digest` só MONTA o corpo. Quem despacha é o canal
    existente (`services/channel_dispatcher`), no agendamento. Assim dá para testar o
    conteúdo sem mandar e-mail de verdade.
  • não inventa número: se não há item aberto, devolve `None` e ninguém recebe "0 itens".
    Silêncio honesto vale mais que e-mail vazio todo dia.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: ordem de exibição: o que vence primeiro e o que é irreversível aparecem no topo
_ORDEM_GATE = {"🔴": 0, "🟡": 1, "🔵": 2}


async def montar_digest(db: AsyncSession) -> dict[str, Any] | None:
    """Monta o corpo do digest a partir dos rascunhos ABERTOS da Central.

    Devolve None quando não há nada — não se manda e-mail para dizer que não há e-mail.
    """
    rows = (await db.execute(text(
        "SELECT tipo, modulo, titulo, gate, requires_otp, created_at "
        "FROM agent_drafts "
        "WHERE lower(coalesce(status,'')) IN ('rascunho','pendente','aguardando') "
        "ORDER BY created_at"
    ))).mappings().all()
    if not rows:
        return None

    itens = sorted(
        ({"titulo": r["titulo"], "gate": r["gate"] or "🔵", "modulo": r["modulo"],
          "otp": bool(r["requires_otp"])} for r in rows),
        key=lambda x: (_ORDEM_GATE.get(x["gate"], 9), x["modulo"] or ""),
    )
    n = len(itens)
    criticos = sum(1 for x in itens if x["gate"] == "🔴")

    linhas = [f"Bom dia. Você tem {n} item(ns) esperando decisão na Central."]
    if criticos:
        # concordância: "1 deles É", "3 deles SÃO" — é texto que a Pyetra lê todo dia
        v = "é irreversível ou envolve" if criticos == 1 else "são irreversíveis ou envolvem"
        linhas.append(f"{criticos} {'dele' if criticos == 1 else 'deles'} {v} dinheiro "
                      f"(marcado{'' if criticos == 1 else 's'} 🔴) — "
                      f"{'esse pede' if criticos == 1 else 'esses pedem'} sua conferência "
                      f"antes do OK.")
    linhas.append("")
    for x in itens[:20]:
        selo = f"{x['gate']}" + (" [OTP]" if x["otp"] else "")
        linhas.append(f"  {selo} {x['titulo']}")
    if n > 20:
        linhas.append(f"  … e mais {n - 20}.")
    linhas.append("")
    linhas.append("Abrir a Central: /redesign/aprovacoes")

    return {
        "assunto": f"Conecta PRO — {n} item(ns) esperando você",
        "corpo": "\n".join(linhas),
        "total": n,
        "criticos": criticos,
    }


if __name__ == "__main__":  # bancada: monta sem enviar
    import asyncio
    import os

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    async def _main() -> None:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        S = async_sessionmaker(eng, expire_on_commit=False)
        async with S() as db:
            d = await montar_digest(db)
            if d is None:
                print("digest: None (nenhum item aberto) — silêncio honesto, ninguém recebe")
            else:
                print(f"assunto: {d['assunto']}\n")
                print(d["corpo"])
                assert d["total"] > 0 and str(d["total"]) in d["assunto"]
                print("\nOK — corpo montado a partir do banco, sem envio")
        await eng.dispose()

    asyncio.run(_main())
