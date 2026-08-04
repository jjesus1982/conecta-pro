"""Fase 6 (balde FAZER) — ação GED reversível (🔵) via propor→aprovar.

No chat, quem tem o módulo `ged` PROPÕE um evento no kit/ficha (GEDEON); grava um
PENDENTE via `acoes.base.propor` — e NADA executa.

MITIGAÇÃO (target sem status inerte): os eventos de kit NÃO vivem em tabela nem
têm campo de status — são um array JSON append-only em disco
(`/app/uploads/kit_checklists/{competencia}__{cond}.json`, via
`kit_ficha_service.add_evento`). Não há "linha PENDENTE" nem transação onde
encaixar. Então o estado PENDENTE do evento vive INTEIRAMENTE na camada de
proposta (sino + auditoria append-only), que `propor()` já torna durável de forma
atômica e idempotente. `_inserir` gera um id sintético e NÃO escreve nada no JSON
— a IA nunca toca a ficha viva do kit. Ao APROVAR na tela de kits, o humano
dispara o `add_evento` real. A idempotência é a nativa do `propor` (chave =
competência+condomínio+tipo+funcionário+data no communication_notifications).
# ponytail: pending vive só no sino/audit (kit é JSON sem status);
# quando o kit ganhar tabela+status próprio, migrar _inserir p/ INSERT inerte.

Reversível 🔵 (nada de dinheiro/eSocial); aprovador = ('admin',
'gerente_operacional') (ROLES_KIT_OP — literalmente a diretoria de kit/operação).
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Any

from .acoes.base import ROLES_KIT_OP, propor
from .agir_dispatcher import registrar_acao

# Reusa a lista canônica de tipos válidos (não fabricar/duplicar).
from modules.gedeon.services.kit_ficha_service import TIPOS_EVENTO


async def _propor_registrar_evento_kit(
    db, user, scope, *, competencia: str = "", condominio: str = "", tipo: str = "",
    descricao: str = "", funcionario: str = "", data: str = "", **_
) -> dict[str, Any]:
    competencia = (competencia or "").strip()
    condominio = (condominio or "").strip()
    tipo = (tipo or "").strip()
    descricao = (descricao or "").strip()
    if not competencia or not condominio:
        return {"erro": "competencia (MM.AAAA) e condominio são obrigatórios"}
    if tipo not in TIPOS_EVENTO:
        return {"erro": f"tipo inválido; use um de: {', '.join(TIPOS_EVENTO)}"}
    if len(descricao) < 2:
        return {"erro": "descricao (>=2 chars) é obrigatória"}

    func = (funcionario or "").strip()
    dt = (data or "").strip()
    chave = f"{competencia}|{condominio}|{tipo}|{func}|{dt}|{descricao}"
    idem = f"kitevt:{hashlib.sha1(chave.encode('utf-8')).hexdigest()[:16]}"

    async def _inserir(db) -> str:
        # MITIGAÇÃO: kit é JSON sem status/tabela — o pendente vive no sino+audit
        # (idempotência nativa do propor). NÃO escreve na ficha viva; a IA nunca
        # executa. Só devolve um id sintético p/ correlacionar a proposta.
        return str(uuid.uuid4())

    corpo = (f"Evento de kit '{tipo}' p/ {condominio} ({competencia})"
             + (f", func. {func}" if func else "")
             + (f", data {dt}" if dt else "")
             + f": “{descricao[:120]}”. Aguarda sua aprovação na tela de kits — "
             + "nada é gravado na ficha até lá.")

    return await propor(
        db, user=user, scope=scope, dominio="kit_evento", gate="🔵",
        roles_aprovador=ROLES_KIT_OP, idempotency_key=idem,
        titulo="[Proposta] Registrar evento no kit",
        corpo=corpo,
        action_url="/modulos/gestao-pessoas/ged/kits",
        tool="propor_registrar_evento_kit",
        args={"competencia": competencia, "condominio": condominio, "tipo": tipo,
              "descricao": descricao, "funcionario": func, "data": dt},
        entity_type="gedeon_kit_evento", inserir=_inserir,
    )


registrar_acao("ged", "registrar_evento_kit",
               "registrar um evento na ficha/kit de um condomínio. dados: competencia "
               "(MM.AAAA, obrig.), condominio (obrig.), tipo (obrig., um de: "
               + ", ".join(TIPOS_EVENTO) + "), descricao (obrig.), funcionario, data. "
               "Fica pendente — a gravação na ficha é humana.",
               _propor_registrar_evento_kit)


if __name__ == "__main__":
    import asyncio
    import os

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from . import tools_acao_ged as _self
    from .agir_dispatcher import montar_acao_dispatchers
    from .tool_registry import get_tool, tools_for_modules

    SENT = "__TESTE_F6FAZER_GED__"

    class _U:
        id = "00000000-0000-0000-0000-0000000000ff"
        role = "funcionario"
        email = "teste-f6ged@conectapro.local"
        permissions = ["module:ged"]

    class _USemGed:
        id = "00000000-0000-0000-0000-0000000000fe"
        role = "funcionario"
        email = "sem-ged@conectapro.local"
        permissions = ["module:financeiro"]

    class _S:
        tier = "gestor"

    async def _limpar(db, idem_like: str) -> None:
        ids = [x for x in (await db.execute(text(
            "SELECT id::text FROM communication_notifications "
            "WHERE extra_data->>'idempotency_key' LIKE :k"), {"k": idem_like})).scalars().all()]
        if ids:
            await db.execute(text("DELETE FROM communication_notifications WHERE id = ANY(:i)"), {"i": ids})
        await db.commit()

    async def main() -> None:
        montar_acao_dispatchers()
        agir = get_tool("agir_ged")
        assert agir is not None and agir.module == "ged", "agir_ged não registrado no módulo ged"

        # PROVA "não executa": se o caminho tocar o gravador real add_evento, falha.
        import modules.gedeon.services.kit_ficha_service as kfs
        chamou = {"add_evento": False}
        orig_add = kfs.add_evento

        def _boom(*a, **k):
            chamou["add_evento"] = True
            raise AssertionError("add_evento (gravação real na ficha) NÃO pode ser chamado")

        kfs.add_evento = _boom

        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        async with Session() as db:
            try:
                disp = agir.handler
                dados = {"competencia": "12.2099", "condominio": f"{SENT} Cond",
                         "tipo": "observacao", "descricao": f"{SENT} evento de teste"}

                # ── (a) registrar_evento_kit: 1 PENDENTE no sino, não grava ficha, idempotente ──
                r = await disp(db, _U(), _S(), acao="registrar_evento_kit", dados=dados)
                assert r.get("status") == "pendente" and not r.get("duplicado"), r
                assert chamou["add_evento"] is False, "gravou na ficha (executou) — não deveria"
                # pendente vive no sino como proposta_acao (reference_type)
                rt = (await db.execute(text(
                    "SELECT reference_type FROM communication_notifications "
                    "WHERE reference_id = :rid LIMIT 1"), {"rid": r["entity_id"]})).scalar()
                assert rt == "proposta_acao", f"proposta não chegou ao sino: {rt}"
                # idempotência: 2ª chamada idêntica → duplicado (chave nativa do propor)
                r2 = await disp(db, _U(), _S(), acao="registrar_evento_kit", dados=dados)
                assert r2.get("duplicado") is True, r2
                assert chamou["add_evento"] is False, "gravou na ficha na 2ª chamada"
                print("TESTE a (registrar_evento_kit: PENDENTE no sino, NÃO grava ficha, idempotente) PASS")

                # ── (b) acao inválida → recusa + opções ──
                rb = await disp(db, _U(), _S(), acao="apagar_kit", dados={})
                assert rb.get("status") == "recusado" and "opções" in rb.get("motivo", ""), rb
                assert "registrar_evento_kit" in rb["motivo"], rb
                print("TESTE b (acao inválida → recusa listando opções) PASS")

                # ── (c) _gate sem ged → PermissionError; agir_ged só no belt de ged ──
                try:
                    await disp(db, _USemGed(), _S(), acao="registrar_evento_kit", dados=dados)
                    raise AssertionError("esperado PermissionError p/ usuário sem módulo ged")
                except PermissionError:
                    pass
                assert "agir_ged" in {t.name for t in tools_for_modules({"ged"})}
                assert "agir_ged" not in {t.name for t in tools_for_modules({"financeiro"})}, \
                    "agir_ged vazou p/ outro módulo (RBAC quebrado)"
                print("TESTE c (_gate sem ged → PermissionError; agir_ged só no belt de ged) PASS")

                # ── (d) prova: PROPÔS sem executar (add_evento nunca chamado) ──
                assert chamou["add_evento"] is False
                print("TESTE d (registrar_evento_kit PROPÕE sem executar: ficha JSON intocada) PASS")
                print("\nTODAS AS PROVAS DE tools_acao_ged.py PASSARAM")
            finally:
                kfs.add_evento = orig_add
                await _limpar(db, "kitevt:%")
                rem = (await db.execute(text(
                    "SELECT count(*) FROM communication_notifications "
                    "WHERE extra_data->>'idempotency_key' LIKE 'kitevt:%' "
                    "  AND body LIKE :s"), {"s": "%" + SENT + "%"})).scalar()
                assert rem == 0, f"remanescentes sino={rem}"
                print("LIMPEZA OK — 0 remanescentes (sino/audit); ficha JSON nunca tocada")
        await eng.dispose()

    asyncio.run(main())
