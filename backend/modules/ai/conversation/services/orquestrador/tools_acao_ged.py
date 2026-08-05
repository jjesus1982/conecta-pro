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
from datetime import date
from typing import Any

from sqlalchemy import text

from .acoes.base import ROLES_KIT_OP, propor
from .acoes.rascunho import criar_rascunho, registrar_executor
from .agir_dispatcher import registrar_acao

# Reusa a lista canônica de tipos válidos (não fabricar/duplicar).
from modules.gedeon.services.kit_ficha_service import TIPOS_EVENTO
# Tipos válidos de intercorrência (fonte única no consultor GED).
from modules.gedeon.services.consultor_service import TIPOS_INTERCORRENCIA


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


# ──────────────────────────────────────────────────────────────────────────────
# INTERCORRÊNCIAS (GEDEON) via CENTRAL DE RASCUNHOS — registrar/tratar/excluir.
# O HANDLER (chat) só grava um AgentDraft inerte via `criar_rascunho` — NUNCA
# executa. A execução real (INSERT/UPDATE/DELETE em gedeon_intercorrencias) roda
# SÓ na aprovação, pelo EXECUTOR registrado, que reusa os MESMOS serviços de
# domínio do consultor GED (consultor_service.registrar/tratar/excluir).
# Aprovador = ROLES_KIT_OP (admin + gerente_operacional), coerente c/ o kit.
# ──────────────────────────────────────────────────────────────────────────────


async def _propor_registrar_intercorrencia(
    db, user, scope, *, condominio: str = "", tipo: str = "", descricao: str = "",
    competencia: str = "", funcionario: str = "", data: str = "",
    impacto_folha: Any = True, **_
) -> dict[str, Any]:
    condominio = (condominio or "").strip()
    tipo_n = (tipo or "").strip().lower()
    descricao = (descricao or "").strip()
    if len(condominio) < 2:
        return {"erro": "condominio (>=2 chars) é obrigatório"}
    if tipo_n not in TIPOS_INTERCORRENCIA:
        return {"erro": f"tipo inválido; use um de: {', '.join(sorted(TIPOS_INTERCORRENCIA))}"}
    if len(descricao) < 2:
        return {"erro": "descricao (>=2 chars) é obrigatória"}
    comp = (competencia or "").strip()[:7] or None
    func = (funcionario or "").strip() or None
    dt = (data or "").strip()
    if dt:
        try:
            date.fromisoformat(dt[:10])
        except (TypeError, ValueError):
            return {"erro": "data inválida (esperado AAAA-MM-DD)"}
    dt = dt[:10] or None
    # impacto_folha aceita bool ou string; default True (a maioria das intercorrências mexe na folha).
    impacto = str(impacto_folha).strip().lower() not in ("false", "0", "nao", "não", "n", "")
    # 🟡 se afeta a folha (revisão mais atenta), 🔵 se não.
    gate = "🟡" if impacto else "🔵"

    chave = f"{condominio}|{comp or ''}|{tipo_n}|{func or ''}|{dt or ''}|{descricao}"
    idem = f"interc_reg:{hashlib.sha1(chave.encode('utf-8')).hexdigest()[:16]}"
    return await criar_rascunho(
        db, user, tipo="registrar_intercorrencia", modulo="ged", gate=gate,
        requires_otp=False, roles_aprovador=ROLES_KIT_OP, idempotency_key=idem,
        titulo="Registrar intercorrência (rascunho)",
        resumo=f"Aprovar REGISTRA a intercorrência '{tipo_n}' em {condominio}"
               + (f" ({comp})" if comp else "")
               + (f", func. {func}" if func else "")
               + (f", data {dt}" if dt else "")
               + (" — IMPACTA A FOLHA" if impacto else "")
               + f": “{descricao[:120]}”. Só a aprovação grava; a IA não registra nada agora.",
        payload={"condominio": condominio, "tipo": tipo_n, "descricao": descricao,
                 "competencia": comp, "funcionario": func, "data_evento": dt,
                 "impacto_folha": impacto},
    )


async def _resolver_intercorrencia(db, ref: str):
    """Resolve um id de intercorrência (read-only) → (id:int, mapping) ou (None, None)."""
    from modules.gedeon.services import consultor_service as _cs
    await _cs._ensure_schema(db)  # cria tabelas vazias se faltarem (idempotente); não é a ação
    try:
        iid = int(str(ref).strip())
    except (TypeError, ValueError):
        return None, None
    row = (await db.execute(text(
        "SELECT id, condominio, tipo, status FROM gedeon_intercorrencias WHERE id = :i"),
        {"i": iid})).mappings().first()
    return (iid, row) if row else (None, None)


async def _propor_tratar_intercorrencia(
    db, user, scope, *, intercorrencia_id: Any = "", id: Any = "", resolucao: str = "", **_
) -> dict[str, Any]:
    ref = str(intercorrencia_id or id or "").strip()
    if not ref:
        return {"erro": "intercorrencia_id é obrigatório"}
    iid, row = await _resolver_intercorrencia(db, ref)
    if not row:
        return {"erro": f"intercorrência '{ref}' não encontrada."}
    resolucao = (resolucao or "").strip()
    return await criar_rascunho(
        db, user, tipo="tratar_intercorrencia", modulo="ged", gate="🔵",
        requires_otp=False, roles_aprovador=ROLES_KIT_OP,
        idempotency_key=f"interc_trat:{iid}",
        titulo="Tratar intercorrência (rascunho)",
        resumo=f"Aprovar marca a intercorrência #{iid} ({row['condominio']} · {row['tipo']}, "
               f"hoje '{row['status']}') como TRATADA."
               + (f" Resolução: “{resolucao[:120]}”." if resolucao else "")
               + " Só a aprovação altera o status.",
        payload={"intercorrencia_id": iid, "resolucao": resolucao or None},
    )


async def _propor_excluir_intercorrencia(
    db, user, scope, *, intercorrencia_id: Any = "", id: Any = "", **_
) -> dict[str, Any]:
    ref = str(intercorrencia_id or id or "").strip()
    if not ref:
        return {"erro": "intercorrencia_id é obrigatório"}
    iid, row = await _resolver_intercorrencia(db, ref)
    if not row:
        return {"erro": f"intercorrência '{ref}' não encontrada."}
    return await criar_rascunho(
        db, user, tipo="excluir_intercorrencia", modulo="ged", gate="🟡",
        requires_otp=False, roles_aprovador=ROLES_KIT_OP,
        idempotency_key=f"interc_del:{iid}",
        titulo="EXCLUIR intercorrência (rascunho)",
        resumo=f"⚠️ DESTRUTIVO: aprovar EXCLUI DEFINITIVAMENTE a intercorrência #{iid} "
               f"({row['condominio']} · {row['tipo']}, status '{row['status']}') — "
               f"não há como desfazer. Confira antes; só a aprovação apaga.",
        payload={"intercorrencia_id": iid},
    )


# ── Executores (rodam SÓ na aprovação, via executar_rascunho) ─────────────────
# Reusam os MESMOS serviços de domínio do consultor GED. Import por-módulo no
# call-time p/ permitir monkeypatch no teste de bancada.


async def _exec_registrar_intercorrencia(db, aprovador_user, payload: dict) -> str:
    from modules.gedeon.services import consultor_service as cs
    dt = payload.get("data_evento")
    data_evento = date.fromisoformat(dt[:10]) if dt else None
    r = await cs.registrar_intercorrencia(
        db, condominio=str(payload["condominio"]), tipo=str(payload["tipo"]),
        descricao=str(payload["descricao"]), competencia=payload.get("competencia"),
        funcionario=payload.get("funcionario"), data_evento=data_evento,
        impacto_folha=bool(payload.get("impacto_folha", True)),
        created_by=str(getattr(aprovador_user, "id", None)),
    )
    return str(r["id"])


async def _exec_tratar_intercorrencia(db, aprovador_user, payload: dict) -> str:
    from modules.gedeon.services import consultor_service as cs
    r = await cs.tratar_intercorrencia(db, int(payload["intercorrencia_id"]))
    return str(r["id"])


async def _exec_excluir_intercorrencia(db, aprovador_user, payload: dict) -> str:
    from modules.gedeon.services import consultor_service as cs
    iid = int(payload["intercorrencia_id"])
    await cs.excluir_intercorrencia(db, iid)
    return str(iid)


registrar_executor("registrar_intercorrencia", _exec_registrar_intercorrencia)
registrar_executor("tratar_intercorrencia", _exec_tratar_intercorrencia)
registrar_executor("excluir_intercorrencia", _exec_excluir_intercorrencia)


registrar_acao("ged", "registrar_intercorrencia",
               "Criar um RASCUNHO p/ registrar uma intercorrência do mês na Central — "
               "aprovação = admin/gerente operacional. dados: condominio (obrig.), tipo "
               "(obrig., um de: " + ", ".join(sorted(TIPOS_INTERCORRENCIA)) + "), descricao "
               "(obrig.), competencia (YYYY-MM), funcionario, data (AAAA-MM-DD), impacto_folha. "
               "NÃO registra agora; só grava quando aprovarem na Central.",
               _propor_registrar_intercorrencia)
registrar_acao("ged", "tratar_intercorrencia",
               "Criar um RASCUNHO p/ marcar uma intercorrência como TRATADA na Central — "
               "aprovação = admin/gerente operacional. dados: intercorrencia_id (obrig.), "
               "resolucao. NÃO altera agora; o status só muda ao aprovar na Central.",
               _propor_tratar_intercorrencia)
registrar_acao("ged", "excluir_intercorrencia",
               "Criar um RASCUNHO p/ EXCLUIR (destrutivo) uma intercorrência na Central — "
               "aprovação = admin/gerente operacional. dados: intercorrencia_id (obrig.). "
               "NÃO exclui agora; só apaga ao aprovar na Central.",
               _propor_excluir_intercorrencia)


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
