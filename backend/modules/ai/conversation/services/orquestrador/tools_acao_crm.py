"""Fase 6 (balde FAZER) — 3 ações CRM reversíveis (🔵) via propor→aprovar.

No chat, quem tem o módulo `crm` PROPÕE ações reversíveis; cada uma grava um PENDENTE
na tabela nativa via `acoes.base.propor` e NENHUMA executa (a IA nunca efetiva):
- criar_lead:      leads          status 'new'      (qualificar/ganhar é humano, na tela CRM)
- criar_tarefa:    crm_tasks      status 'pending'  (concluir é humano)
- anotar_cliente:  crm_client_notes (nota marcada "aguardando aprovação")

São todas 🔵 reversíveis (nada de dinheiro/eSocial); aprovador = ROLES_COMERCIAL.
Registram via `registrar_acao` (o agir_dispatcher colapsa em agir_crm(acao, dados)).
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import date
from typing import Any

from sqlalchemy import text

from .acoes.base import ROLES_COMERCIAL, propor
from .agir_dispatcher import registrar_acao

# ───────────────────────── criar_lead (🔵) ──────────────────────────────────


async def _propor_criar_lead(
    db, user, scope, *, name: str, phone: str = "", email: str = "",
    company: str = "", source: str = "other", **_
) -> dict[str, Any]:
    name = (name or "").strip()
    if len(name) < 2:
        return {"erro": "name (nome do contato, >=2 chars) é obrigatório"}
    chave = (phone or "").strip() or (email or "").strip()
    idem = f"lead:{name}:{chave}"

    async def _inserir(db) -> str:
        # Idempotência NATIVA (defesa em profundidade, molde onda_a): não duplica um
        # lead NOVO (status inerte) com o mesmo nome + telefone/email — SELECT-existing
        # antes do INSERT, mesmo que o precheck do sino não pegue.
        existente = (await db.execute(text(
            "SELECT id::text FROM leads "
            "WHERE status = 'new' AND name = :nome "
            "  AND coalesce(phone,'') = :ph AND coalesce(email,'') = :em LIMIT 1"),
            {"nome": name, "ph": (phone or "").strip(), "em": (email or "").strip()})).scalar()
        if existente:
            return existente

        lid = str(uuid.uuid4())
        # assigned_to_id tem FK ENFORCED p/ users(id) (ON DELETE SET NULL). Subquery
        # valida a existência em 1 round-trip (usuário real → grava id; senão NULL),
        # nunca estoura IntegrityError dentro de propor(). status/score/probability/
        # expected_value/is_active são NOT NULL sem default no banco → supridos aqui.
        await db.execute(text("""
            INSERT INTO leads
                (id, name, email, phone, company, source, status,
                 score, probability, expected_value, notes,
                 assigned_to_id, is_active, created_at, updated_at)
            VALUES
                (:id, :name, :email, :phone, :company, :source, 'new',
                 0, 0, 0, :notes,
                 (SELECT id FROM users WHERE id = :uid), true, now(), now())
        """), {"id": lid, "name": name, "email": (email or "").strip() or None,
               "phone": (phone or "").strip() or None,
               "company": (company or "").strip() or None,
               "source": (source or "other").strip() or "other",
               "notes": "[proposto via IA] aguardando aprovação",
               "uid": str(getattr(user, "id", None))})
        return lid

    return await propor(
        db, user=user, scope=scope, dominio="lead", gate="🔵",
        roles_aprovador=ROLES_COMERCIAL, idempotency_key=idem,
        titulo="[Proposta] Criar lead",
        corpo=f"Novo lead '{name}'"
              + (f" ({chave})" if chave else "")
              + ". Nasce 'novo' — aguarda sua aprovação/qualificação.",
        action_url="/crm/leads",
        tool="propor_criar_lead",
        args={"name": name, "phone": phone, "email": email, "company": company, "source": source},
        entity_type="lead", inserir=_inserir,
    )


# ───────────────────────── criar_tarefa (🔵) ─────────────────────────────────


async def _propor_criar_tarefa(
    db, user, scope, *, title: str, due_date: str = "", description: str = "",
    priority: str = "medium", **_
) -> dict[str, Any]:
    title = (title or "").strip()
    if len(title) < 2:
        return {"erro": "title (título da tarefa, >=2 chars) é obrigatório"}
    venc_date = None
    if due_date:
        try:
            venc_date = date.fromisoformat(due_date)
        except (TypeError, ValueError):
            return {"erro": "due_date inválido (esperado AAAA-MM-DD)"}
    idem = f"tarefa:{title}:{due_date or ''}"

    async def _inserir(db) -> str:
        # Idempotência NATIVA: não duplica tarefa ABERTA (status inerte 'pending') com
        # o mesmo título + vencimento. due_date é coluna `date` — bind como date nativo.
        existente = (await db.execute(text(
            "SELECT id::text FROM crm_tasks "
            "WHERE status = 'pending' AND title = :ttl "
            "  AND due_date IS NOT DISTINCT FROM :venc LIMIT 1"),
            {"ttl": title, "venc": venc_date})).scalar()
        if existente:
            return existente

        tid = str(uuid.uuid4())
        await db.execute(text("""
            INSERT INTO crm_tasks
                (id, title, description, status, priority, due_date,
                 created_by_id, created_at, updated_at)
            VALUES
                (:id, :ttl, :desc, 'pending', :prio, :venc,
                 (SELECT id FROM users WHERE id = :uid), now(), now())
        """), {"id": tid, "ttl": title, "desc": (description or "").strip() or None,
               "prio": (priority or "medium").strip() or "medium", "venc": venc_date,
               "uid": str(getattr(user, "id", None))})
        return tid

    return await propor(
        db, user=user, scope=scope, dominio="tarefa", gate="🔵",
        roles_aprovador=ROLES_COMERCIAL, idempotency_key=idem,
        titulo="[Proposta] Criar tarefa",
        corpo=f"Tarefa '{title}'" + (f" (venc. {due_date})" if due_date else "")
              + " nasce 'pendente' — aguarda sua aprovação.",
        action_url="/crm/tarefas",
        tool="propor_criar_tarefa",
        args={"title": title, "due_date": due_date, "priority": priority},
        entity_type="crm_task", inserir=_inserir,
    )


# ───────────────────────── anotar_cliente (🔵) ───────────────────────────────

#: Marcador do autor: a nota nasce visível SÓ na ficha interna (staff), NUNCA no
#: caminho customer-facing do José Luís (notas_por_telefone filtra por
#: phone_canonical, que deixamos NULL de propósito no estado pendente).
_AUTOR_PENDENTE = "IA (aguardando aprovacao)"


async def _propor_anotar_cliente(
    db, user, scope, *, cliente_ref: str, nota: str, **_
) -> dict[str, Any]:
    cliente_ref = (cliente_ref or "").strip()
    nota = (nota or "").strip()
    if not cliente_ref or len(nota) < 2:
        return {"erro": "cliente_ref e nota (>=2 chars) são obrigatórios"}

    # Reusa o resolvedor READ-ONLY do CRM (só SELECT; não chama anotar_cliente, que
    # commitaria a nota LIVE — isso seria executar).
    from modules.crm.services.orchestration import _resolve_cliente_ref
    info = await _resolve_cliente_ref(db, cliente_ref)

    autor = f"{_AUTOR_PENDENTE} — {getattr(user, 'email', None) or getattr(user, 'id', '')}"
    nota_txt = f"[PROPOSTA — aguardando aprovação] {nota}"[:4000]
    nota_hash = hashlib.sha1(nota.encode("utf-8")).hexdigest()[:12]
    idem = f"anota:{cliente_ref}:{nota_hash}"

    async def _inserir(db) -> str:
        # Idempotência NATIVA: não duplica a MESMA nota pendente p/ o mesmo cliente.
        existente = (await db.execute(text(
            "SELECT id::text FROM crm_client_notes "
            "WHERE autor LIKE :marca AND coalesce(cliente_ref,'') = :ref "
            "  AND nota = :nota LIMIT 1"),
            {"marca": _AUTOR_PENDENTE + "%", "ref": cliente_ref, "nota": nota_txt})).scalar()
        if existente:
            return existente

        nid = str(uuid.uuid4())
        # phone_canonical = NULL de propósito: mantém a nota pendente FORA do caminho
        # customer-facing do José Luís (notas_por_telefone). A ficha interna (staff) a
        # mostra marcada "aguardando aprovação" — superfície de revisão do aprovador.
        await db.execute(text("""
            INSERT INTO crm_client_notes
                (id, cliente_id, cliente_ref, cliente_nome, phone_canonical, nota, autor, created_at)
            VALUES
                (:id, :cid, :ref, :nome, NULL, :nota, :autor, now())
        """), {"id": nid, "cid": info["cliente_id"], "ref": cliente_ref,
               "nome": info["cliente_nome"], "nota": nota_txt, "autor": autor})
        return nid

    return await propor(
        db, user=user, scope=scope, dominio="anotacao", gate="🔵",
        roles_aprovador=ROLES_COMERCIAL, idempotency_key=idem,
        titulo="[Proposta] Anotar cliente",
        corpo=f"Anotação proposta p/ '{info['cliente_nome']}': “{nota[:120]}”. "
              f"Aguarda sua aprovação (fica só na ficha interna até lá).",
        action_url="/crm/clientes",
        tool="propor_anotar_cliente",
        args={"cliente_ref": cliente_ref, "nota": nota},
        entity_type="crm_client_note", inserir=_inserir,
    )


# ───────────────────────── registro (dispatcher agir_crm) ────────────────────

registrar_acao("crm", "criar_lead",
               "criar um lead. dados: name (obrigatório), phone, email, company, source. "
               "Nasce 'novo' (aguarda qualificação humana).",
               _propor_criar_lead)
registrar_acao("crm", "criar_tarefa",
               "criar uma tarefa/lembrete. dados: title (obrigatório), due_date (AAAA-MM-DD), "
               "description, priority. Nasce 'pendente'.",
               _propor_criar_tarefa)
registrar_acao("crm", "anotar_cliente",
               "anotar (append) na ficha de um cliente. dados: cliente_ref (id/CNPJ/nome, "
               "obrigatório), nota (obrigatório). Fica 'aguardando aprovação'.",
               _propor_anotar_cliente)


if __name__ == "__main__":
    import asyncio
    import os

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from .agir_dispatcher import montar_acao_dispatchers
    from .tool_registry import get_tool, tools_for_modules

    SENT = "__TESTE_F6FAZER__"

    class _U:
        id = "00000000-0000-0000-0000-0000000000ff"
        role = "funcionario"
        email = "teste-f6@conectapro.local"
        permissions = ["module:crm"]

    class _USemCrm:
        id = "00000000-0000-0000-0000-0000000000fe"
        role = "funcionario"
        email = "sem-crm@conectapro.local"
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
        agir = get_tool("agir_crm")
        assert agir is not None and agir.module == "crm", "agir_crm não registrado no módulo crm"

        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        async with Session() as db:
            lead_ids: list[str] = []
            task_ids: list[str] = []
            note_ids: list[str] = []
            try:
                disp = agir.handler  # o _fazer_acao_dispatch(crm)

                # ── (a) criar_lead: cria 1 PENDENTE inerte + idempotente + não executa ──
                nome_lead = f"{SENT} Lead"
                r = await disp(db, _U(), _S(), acao="criar_lead",
                               dados={"name": nome_lead, "phone": "92999990000", "source": "whatsapp"})
                assert r.get("status") == "pendente" and not r.get("duplicado"), r
                lid = r["entity_id"]; lead_ids.append(lid)
                st = (await db.execute(text("SELECT status FROM leads WHERE id=:i"), {"i": lid})).scalar()
                assert st == "new", f"lead nasceu {st}, esperado 'new' (inerte, não executado)"
                # NÃO executou: nenhum lead sentinela ficou qualificado/ganho
                exec_leads = (await db.execute(text(
                    "SELECT count(*) FROM leads WHERE name LIKE :n AND status <> 'new'"),
                    {"n": SENT + "%"})).scalar()
                assert exec_leads == 0, "lead sentinela mudou de status (executado) — não deveria"
                # idempotência: 2ª chamada não duplica
                r2 = await disp(db, _U(), _S(), acao="criar_lead",
                                dados={"name": nome_lead, "phone": "92999990000", "source": "whatsapp"})
                assert r2.get("duplicado") is True, r2
                n_lead = (await db.execute(text(
                    "SELECT count(*) FROM leads WHERE name = :n AND status='new'"),
                    {"n": nome_lead})).scalar()
                assert n_lead == 1, f"idempotência lead falhou: {n_lead} linhas"
                print("TESTE a1 (criar_lead: PENDENTE inerte 'new', não executa, idempotente) PASS")

                # ── (a) criar_tarefa ──
                titulo = f"{SENT} Tarefa"
                rt = await disp(db, _U(), _S(), acao="criar_tarefa",
                                dados={"title": titulo, "due_date": "2099-12-31"})
                assert rt.get("status") == "pendente", rt
                tid = rt["entity_id"]; task_ids.append(tid)
                stt = (await db.execute(text("SELECT status FROM crm_tasks WHERE id=:i"), {"i": tid})).scalar()
                assert stt == "pending", f"tarefa nasceu {stt}, esperado 'pending'"
                exec_tasks = (await db.execute(text(
                    "SELECT count(*) FROM crm_tasks WHERE title LIKE :n AND status <> 'pending'"),
                    {"n": SENT + "%"})).scalar()
                assert exec_tasks == 0, "tarefa sentinela concluída (executada) — não deveria"
                rt2 = await disp(db, _U(), _S(), acao="criar_tarefa",
                                 dados={"title": titulo, "due_date": "2099-12-31"})
                assert rt2.get("duplicado") is True, rt2
                print("TESTE a2 (criar_tarefa: PENDENTE inerte 'pending', não executa, idempotente) PASS")

                # ── (a) anotar_cliente ──
                nota_txt = f"{SENT} nota de teste"
                ra = await disp(db, _U(), _S(), acao="anotar_cliente",
                                dados={"cliente_ref": "CLIENTE-INEXISTENTE-SENTINELA", "nota": nota_txt})
                assert ra.get("status") == "pendente", ra
                nid = ra["entity_id"]; note_ids.append(nid)
                row = (await db.execute(text(
                    "SELECT autor, phone_canonical FROM crm_client_notes WHERE id=:i"), {"i": nid})).mappings().first()
                assert row["autor"].startswith(_AUTOR_PENDENTE), f"nota sem marca de pendente: {row['autor']}"
                assert row["phone_canonical"] is None, "nota pendente NÃO pode ter phone (vazaria p/ José Luís)"
                ra2 = await disp(db, _U(), _S(), acao="anotar_cliente",
                                 dados={"cliente_ref": "CLIENTE-INEXISTENTE-SENTINELA", "nota": nota_txt})
                assert ra2.get("duplicado") is True, ra2
                print("TESTE a3 (anotar_cliente: nota pendente marcada, fora do José Luís, idempotente) PASS")

                # ── (b) acao inválida → recusa + opções (fail-closed) ──
                rb = await disp(db, _U(), _S(), acao="deletar_tudo", dados={})
                assert rb.get("status") == "recusado" and "opções" in rb.get("motivo", ""), rb
                assert "criar_lead" in rb["motivo"] and "anotar_cliente" in rb["motivo"], rb
                print("TESTE b (acao inválida → recusa listando opções) PASS")

                # ── (c) _gate sem crm → PermissionError; agir_crm no belt de crm ──
                try:
                    await disp(db, _USemCrm(), _S(), acao="criar_lead", dados={"name": "x"})
                    raise AssertionError("esperado PermissionError para usuário sem módulo crm")
                except PermissionError:
                    pass
                nomes_crm = {t.name for t in tools_for_modules({"crm"})}
                nomes_fin = {t.name for t in tools_for_modules({"financeiro"})}
                assert "agir_crm" in nomes_crm, nomes_crm
                assert "agir_crm" not in nomes_fin, "agir_crm vazou p/ outro módulo (RBAC quebrado)"
                print("TESTE c (_gate sem crm → PermissionError; agir_crm só no belt de crm) PASS")

                # ── (d) prova global: NADA foi executado (só PENDENTES inertes) ──
                print("TESTE d (as 3 ações PROPÕEM sem executar: lead 'new', tarefa 'pending', "
                      "nota 'aguardando aprovação') PASS")
                print("\nTODAS AS PROVAS DE tools_acao_crm.py PASSARAM")
            finally:
                if lead_ids:
                    await db.execute(text("DELETE FROM leads WHERE id = ANY(:i)"), {"i": lead_ids})
                    await db.execute(text(
                        "DELETE FROM audit_logs WHERE details->>'entity_id' = ANY(:i)"), {"i": lead_ids})
                if task_ids:
                    await db.execute(text("DELETE FROM crm_tasks WHERE id = ANY(:i)"), {"i": task_ids})
                    await db.execute(text(
                        "DELETE FROM audit_logs WHERE details->>'entity_id' = ANY(:i)"), {"i": task_ids})
                if note_ids:
                    await db.execute(text("DELETE FROM crm_client_notes WHERE id = ANY(:i)"), {"i": note_ids})
                    await db.execute(text(
                        "DELETE FROM audit_logs WHERE details->>'entity_id' = ANY(:i)"), {"i": note_ids})
                await _limpar(db, "lead:%" + SENT + "%")
                await _limpar(db, "tarefa:%" + SENT + "%")
                await _limpar(db, "anota:%")
                await db.commit()
                rem_l = (await db.execute(text(
                    "SELECT count(*) FROM leads WHERE name LIKE :n"), {"n": SENT + "%"})).scalar()
                rem_t = (await db.execute(text(
                    "SELECT count(*) FROM crm_tasks WHERE title LIKE :n"), {"n": SENT + "%"})).scalar()
                rem_n = (await db.execute(text(
                    "SELECT count(*) FROM crm_client_notes WHERE nota LIKE :n"), {"n": "%" + SENT + "%"})).scalar()
                assert rem_l == 0 and rem_t == 0 and rem_n == 0, \
                    f"remanescentes lead={rem_l} tarefa={rem_t} nota={rem_n}"
                print("LIMPEZA OK — 0 remanescentes (leads/crm_tasks/crm_client_notes/audit/sino)")
        await eng.dispose()

    asyncio.run(main())
