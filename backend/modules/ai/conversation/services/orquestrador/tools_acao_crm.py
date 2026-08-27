"""Fase 6 (balde FAZER) — ações CRM reversíveis (🔵) via propor→aprovar.

No chat, quem tem o módulo `crm` PROPÕE ações reversíveis; cada uma grava um PENDENTE
na tabela nativa via `acoes.base.propor` e NENHUMA executa (a IA nunca efetiva):
- criar_lead:            leads              status 'new'      (qualificar/ganhar é humano, na tela CRM)
- criar_tarefa:          crm_tasks          status 'pending'  (concluir é humano)
- anotar_cliente:        crm_client_notes   (nota marcada "aguardando aprovação")
- criar_relatorio_visita: crm_visit_reports  status 'rascunho' (montar/PDF/lead é humano)
- criar_reuniao:         crm_meetings       status 'sugerido'  (confirmar é humano; lembrete só p/ 'confirmado')
- registrar_followup:    crm_followups      status 'proposto' + phone NULL (envio é humano — NÃO 'agendado')

São todas 🔵 reversíveis (nada de dinheiro/eSocial); aprovador = ROLES_COMERCIAL.
Registram via `registrar_acao` (o agir_dispatcher colapsa em agir_crm(acao, dados)).
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from .acoes.base import ROLES_COMERCIAL, ROLES_MONEY, propor
from .acoes.rascunho import criar_rascunho, registrar_executor
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

        # Dedup por CONTATO (match_key_br: DDD + 8 últimos dígitos) — mesma regra dos
        # outros 9 caminhos. O SELECT acima casa nome+telefone+email LITERAIS, então
        # telefone com máscara ou nome escrito diferente escapava e duplicava.
        from modules.crm.repositories.lead_repository import LeadRepository

        _dup = await LeadRepository(db).find_duplicate(
            phone=(phone or "").strip() or None, email=(email or "").strip() or None
        )
        if _dup:
            return str(_dup.id)

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


# ───────────────────────── criar_relatorio_visita (🔵) ───────────────────────


async def _propor_criar_relatorio_visita(
    db, user, scope, *, cliente_nome: str, panorama: str = "", data_visita: str = "", **_
) -> dict[str, Any]:
    cliente_nome = (cliente_nome or "").strip()
    if len(cliente_nome) < 2:
        return {"erro": "cliente_nome (>=2 chars) é obrigatório"}
    dv = None
    if data_visita:
        try:
            dv = date.fromisoformat(str(data_visita)[:10])
        except (TypeError, ValueError):
            return {"erro": "data_visita inválida (esperado AAAA-MM-DD)"}
    idem = f"visita:{cliente_nome.lower()}:{dv.isoformat() if dv else ''}"

    async def _inserir(db) -> str:
        # Idempotência NATIVA: não duplica um relatório RASCUNHO (status inerte, o mesmo
        # que a tela cria) do mesmo cliente + data de visita. 'rascunho' é o estado inerte:
        # só a ação humana (montar/PDF/lead) o torna 'finalizado' e produz efeito.
        existente = (await db.execute(text(
            "SELECT id::text FROM crm_visit_reports "
            "WHERE status = 'rascunho' AND lower(cliente_nome) = :nome "
            "  AND data_visita IS NOT DISTINCT FROM :dv LIMIT 1"),
            {"nome": cliente_nome.lower(), "dv": dv})).scalar()
        if existente:
            return existente

        rid = str(uuid.uuid4())
        # status='rascunho' explícito (= server_default; inerte). criado_por marca o autor.
        await db.execute(text("""
            INSERT INTO crm_visit_reports
                (id, cliente_nome, panorama, data_visita, achados, status, criado_por,
                 created_at, updated_at)
            VALUES
                (CAST(:id AS uuid), :nome, :pan, :dv, '[]'::jsonb, 'rascunho', :por, now(), now())
        """), {"id": rid, "nome": cliente_nome[:255],
               "pan": (panorama or "").strip() or None, "dv": dv,
               "por": f"[proposto via IA] {getattr(user, 'email', None) or getattr(user, 'id', '')}"[:120]})
        return rid

    return await propor(
        db, user=user, scope=scope, dominio="visita", gate="🔵",
        roles_aprovador=ROLES_COMERCIAL, idempotency_key=idem,
        titulo="[Proposta] Criar relatório de visita",
        corpo=f"Relatório de visita p/ '{cliente_nome}'"
              + (f" ({data_visita})" if data_visita else "")
              + ". Nasce 'rascunho' — aguarda sua revisão (montar/PDF/lead é humano).",
        action_url="/crm/visitas",
        tool="propor_criar_relatorio_visita",
        args={"cliente_nome": cliente_nome, "panorama": panorama, "data_visita": data_visita},
        entity_type="crm_visit_report", inserir=_inserir,
    )


# ───────────────────────── criar_reuniao (🔵) ────────────────────────────────


async def _propor_criar_reuniao(
    db, user, scope, *, titulo: str, quando_iso: str, cliente_nome: str = "",
    local: str = "", tipo: str = "reuniao", notes: str = "", **_
) -> dict[str, Any]:
    titulo = (titulo or "").strip()
    if len(titulo) < 2:
        return {"erro": "titulo (>=2 chars) é obrigatório"}
    if not quando_iso:
        return {"erro": "quando_iso (AAAA-MM-DDTHH:MM) é obrigatório"}
    try:
        quando = datetime.fromisoformat(str(quando_iso).replace("Z", ""))
        if quando.tzinfo is None:  # espelha o controller: Manaus (UTC-4)
            quando = quando.replace(tzinfo=timezone(timedelta(hours=-4)))
    except (TypeError, ValueError):
        return {"erro": "quando_iso inválido (use AAAA-MM-DDTHH:MM)"}
    idem = f"reuniao:{titulo.lower()}:{quando.isoformat()}"

    async def _inserir(db) -> str:
        # Idempotência NATIVA: não duplica uma reunião 'sugerido' (status inerte, o mesmo
        # que sugerir_reuniao cria) com mesmo título+horário. 'sugerido' é inerte: o
        # lembrete automático (crm.lembrete_reuniao) só dispara p/ 'confirmado' (humano).
        existente = (await db.execute(text(
            "SELECT id::text FROM crm_meetings "
            "WHERE status = 'sugerido' AND lower(titulo) = :t AND quando = :q LIMIT 1"),
            {"t": titulo.lower(), "q": quando})).scalar()
        if existente:
            return existente

        mid = str(uuid.uuid4())
        await db.execute(text("""
            INSERT INTO crm_meetings
                (id, titulo, cliente_nome, quando, local, tipo, status, lembrete_enviado,
                 notes, criado_por, created_at, updated_at)
            VALUES
                (CAST(:id AS uuid), :t, :c, :q, :loc, :tp, 'sugerido', false, :nt, :por, now(), now())
        """), {"id": mid, "t": titulo[:255], "c": (cliente_nome or "").strip() or None,
               "q": quando, "loc": (local or "").strip() or None,
               "tp": (tipo or "reuniao").strip() or "reuniao",
               "nt": (notes or "").strip() or None,
               "por": f"[proposto via IA] {getattr(user, 'email', None) or getattr(user, 'id', '')}"[:120]})
        return mid

    return await propor(
        db, user=user, scope=scope, dominio="reuniao", gate="🔵",
        roles_aprovador=ROLES_COMERCIAL, idempotency_key=idem,
        titulo="[Proposta] Agendar reunião",
        corpo=f"Reunião '{titulo}'" + (f" c/ {cliente_nome}" if cliente_nome else "")
              + f" em {quando_iso}. Nasce 'sugerido' — aguarda sua confirmação (o lembrete só sai após confirmar).",
        action_url="/crm/reunioes",
        tool="propor_criar_reuniao",
        args={"titulo": titulo, "quando_iso": quando_iso, "cliente_nome": cliente_nome,
              "local": local, "tipo": tipo},
        entity_type="crm_meeting", inserir=_inserir,
    )


# ───────────────────────── registrar_followup (🔵) ───────────────────────────

#: status INERTE do follow-up proposto. NÃO usar 'agendado': o worker
#: crm.enviar_followups_agendados ENVIA por WhatsApp todo 'agendado' com phone_e164
#: NOT NULL — isso seria executar (customer-facing). 'proposto' não é consumido por
#: nenhum worker; e phone_e164/phone_canonical=NULL é o suspenders (mesmo padrão do
#: anotar_cliente): mesmo que o status escorregasse, sem telefone nada é enviado.
_FUP_STATUS_PROPOSTO = "proposto"


async def _propor_registrar_followup(
    db, user, scope, *, mensagem: str, deal_id: str = "", lead_id: str = "",
    cliente_id: str = "", canal: str = "whatsapp", template: str = "", **_
) -> dict[str, Any]:
    mensagem = (mensagem or "").strip()
    if len(mensagem) < 2:
        return {"erro": "mensagem (>=2 chars) é obrigatória"}
    ref = (deal_id or lead_id or cliente_id or "").strip()
    msg_hash = hashlib.sha1(mensagem.encode("utf-8")).hexdigest()[:12]
    idem = f"followup:{ref}:{msg_hash}"

    def _uuid_ou_none(v: str):
        v = (v or "").strip()
        if not v:
            return None
        try:
            return str(uuid.UUID(v))
        except (TypeError, ValueError):
            return None

    d_id, l_id, c_id = _uuid_ou_none(deal_id), _uuid_ou_none(lead_id), _uuid_ou_none(cliente_id)

    async def _inserir(db) -> str:
        # Idempotência NATIVA: não duplica um follow-up 'proposto' com a mesma mensagem
        # p/ a mesma referência (deal/lead/cliente).
        existente = (await db.execute(text(
            "SELECT id::text FROM crm_followups "
            "WHERE status = :st AND mensagem = :msg "
            "  AND deal_id IS NOT DISTINCT FROM CAST(:d AS uuid) "
            "  AND lead_id IS NOT DISTINCT FROM CAST(:l AS uuid) "
            "  AND cliente_id IS NOT DISTINCT FROM CAST(:c AS uuid) LIMIT 1"),
            {"st": _FUP_STATUS_PROPOSTO, "msg": mensagem, "d": d_id, "l": l_id, "c": c_id})).scalar()
        if existente:
            return existente

        fid = str(uuid.uuid4())
        # phone_e164/phone_canonical = NULL de propósito: mantém o follow-up FORA do
        # caminho de envio do worker (que exige phone_e164 IS NOT NULL). status='proposto'
        # (não 'agendado') é a defesa primária; o telefone NULL é o suspenders.
        await db.execute(text("""
            INSERT INTO crm_followups
                (id, deal_id, cliente_id, lead_id, phone_e164, phone_canonical, canal,
                 template, mensagem, status, criado_por, detalhe, created_at, updated_at)
            VALUES
                (CAST(:id AS uuid), CAST(:d AS uuid), CAST(:c AS uuid), CAST(:l AS uuid),
                 NULL, NULL, :canal, :tpl, :msg, :st, :por,
                 '[proposto via IA] aguardando aprovação', now(), now())
        """), {"id": fid, "d": d_id, "c": c_id, "l": l_id,
               "canal": (canal or "whatsapp").strip() or "whatsapp",
               "tpl": (template or "").strip() or None, "msg": mensagem,
               "st": _FUP_STATUS_PROPOSTO,
               "por": f"[proposto via IA] {getattr(user, 'email', None) or getattr(user, 'id', '')}"[:120]})
        return fid

    return await propor(
        db, user=user, scope=scope, dominio="followup", gate="🔵",
        roles_aprovador=ROLES_COMERCIAL, idempotency_key=idem,
        titulo="[Proposta] Registrar follow-up",
        corpo=f"Follow-up proposto: “{mensagem[:120]}”. Nasce 'proposto' (sem telefone, "
              f"fora do envio automático) — o envio ao cliente é humano.",
        action_url="/crm/followups",
        tool="propor_registrar_followup",
        args={"mensagem": mensagem, "deal_id": deal_id, "lead_id": lead_id,
              "cliente_id": cliente_id, "canal": canal},
        entity_type="crm_followup", inserir=_inserir,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Ações PESADAS (diretoria) via CENTRAL DE RASCUNHOS — criar/ativar CONTRATO e
# ENVIAR proposta ao cliente. O HANDLER (chat) só grava um AgentDraft inerte via
# `criar_rascunho` — NUNCA executa. A execução real roda SÓ na aprovação, pelo
# EXECUTOR registrado (`registrar_executor`), que reusa os MESMOS serviços de
# domínio do clássico/REDESIGN-1 (ContractRepository.create, activate_contract,
# send_proposal). Aprovador = ROLES_MONEY (diretoria). enviar_proposta é EXTERNO/
# LGPD (vai AO CLIENTE) → resumo inequívoco; sem OTP (não é dinheiro), gate 🔴.
# ──────────────────────────────────────────────────────────────────────────────


def _slug(s: str) -> str:
    return "".join(c for c in (s or "").strip().lower() if c.isalnum() or c in " -")[:60].strip()


async def _propor_criar_contrato(
    db, user, scope, *, cliente="", cliente_nome="", produto="", valor="",
    prazo="", vigencia_meses="", **_
) -> dict[str, Any]:
    cli = str(cliente or cliente_nome or "").strip()
    if len(cli) < 2:
        return {"erro": "cliente (nome/razão social, >=2 chars) é obrigatório"}
    # Resolve o cliente p/ um id REAL (read-only) — o executor precisa de client_id
    # válido p/ ContractRepository.create. Falha cedo se o cliente não existe.
    from modules.crm.services.orchestration import _resolve_cliente_ref
    info = await _resolve_cliente_ref(db, cli)
    if not info.get("cliente_id"):
        return {"erro": f"cliente '{cli}' não encontrado no CRM — cadastre-o antes de criar o contrato."}
    prod = str(produto or "").strip()
    val = str(valor or "").strip()
    prz = str(prazo or vigencia_meses or "").strip()
    try:
        monthly = float(val.replace(".", "").replace(",", ".")) if val else 0.0
    except (ValueError, TypeError):
        monthly = 0.0
    nome_contrato = (f"Contrato {prod} — {info['cliente_nome']}" if prod
                     else f"Contrato — {info['cliente_nome']}")[:200]
    detalhe = ", ".join(x for x in (prod, f"R$ {val}" if val else "", f"{prz} meses" if prz else "") if x)
    return await criar_rascunho(
        db, user, tipo="criar_contrato", modulo="crm", gate="🟡", requires_otp=False,
        roles_aprovador=ROLES_MONEY,
        idempotency_key=f"contrato_criar:{_slug(cli)}:{_slug(val)}",
        titulo="Criar contrato (rascunho)",
        resumo=f"Aprovar CRIA o contrato de '{info['cliente_nome']}'"
               + (f" ({detalhe})" if detalhe else "")
               + " como RASCUNHO (status DRAFT) — revise cláusulas/valor. Só a aprovação cria.",
        payload={"client_id": info["cliente_id"], "name": nome_contrato,
                 "monthly_value": monthly, "description": (prod or None)},
    )


async def _propor_ativar_contrato(
    db, user, scope, *, contrato_id="", contrato_numero="", numero="", contract_id="", **_
) -> dict[str, Any]:
    ref = str(contrato_id or contract_id or contrato_numero or numero or "").strip()
    if not ref:
        return {"erro": "contrato_id ou contrato_numero é obrigatório"}
    # Resolve p/ o id REAL (read-only) — o executor chama activate_contract(contract_id).
    row = (await db.execute(text(
        "SELECT id::text AS id, contract_number, status::text AS status FROM contracts "
        "WHERE id::text = :ref OR contract_number = :ref LIMIT 1"), {"ref": ref})).mappings().first()
    if not row:
        return {"erro": f"contrato '{ref}' não encontrado."}
    return await criar_rascunho(
        db, user, tipo="ativar_contrato", modulo="crm", gate="🔴", requires_otp=False,
        roles_aprovador=ROLES_MONEY,
        idempotency_key=f"contrato_ativar:{_slug(ref)}",
        titulo="ATIVAR contrato (vigência)",
        resumo=f"Aprovar ATIVA o contrato {row['contract_number']} — coloca-o EM VIGÊNCIA "
               f"(passa a valer, lança MRR/faturamento). Confira assinatura e dados antes; "
               f"só a aprovação ativa.",
        payload={"contract_id": row["id"], "contract_number": row["contract_number"]},
    )


async def _propor_enviar_proposta(
    db, user, scope, *, proposta_id="", proposal_id="", numero="", cliente="", **_
) -> dict[str, Any]:
    ref = str(proposta_id or proposal_id or numero or "").strip()
    if not ref:
        return {"erro": "proposta_id (ou numero da proposta) é obrigatório"}
    # Resolve p/ o id REAL (read-only) — o executor chama send_proposal(proposal_id).
    row = (await db.execute(text(
        "SELECT id::text AS id, coalesce(number,'') AS number, coalesce(client_name,'') AS client_name "
        "FROM proposals WHERE id::text = :ref OR number = :ref LIMIT 1"), {"ref": ref})).mappings().first()
    if not row:
        return {"erro": f"proposta '{ref}' não encontrada."}
    cli = str(cliente or row["client_name"] or "").strip()
    return await criar_rascunho(
        db, user, tipo="enviar_proposta", modulo="crm", gate="🔴", requires_otp=False,
        roles_aprovador=ROLES_MONEY,
        idempotency_key=f"proposta_enviar:{_slug(ref)}",
        titulo="ENVIAR proposta AO CLIENTE",
        resumo=f"⚠️ EXTERNO/LGPD: aprovar ENVIA a proposta {row['number'] or ref}"
               + (f" AO CLIENTE '{cli}'" if cli else " AO CLIENTE")
               + " (e-mail externo — sai da empresa). CONFIRA destinatário e conteúdo; "
                 "só a aprovação dispara o envio ao cliente.",
        payload={"proposal_id": row["id"], "number": row["number"], "cliente": cli},
    )


# ── Executores (rodam SÓ na aprovação, via executar_rascunho) ─────────────────
# Reusam os MESMOS serviços de domínio do clássico/REDESIGN-1. Imports locais p/
# o call-time resolver o attr do módulo (permite monkeypatch no teste de bancada).


async def _exec_criar_contrato(db, aprovador_user, payload: dict) -> str:
    from decimal import Decimal

    from modules.crm.repositories.contract_repository import ContractRepository
    from modules.crm.schemas.contract import ContractCreate
    data = ContractCreate(
        client_id=str(payload["client_id"]),
        name=str(payload["name"])[:200],
        monthly_value=Decimal(str(payload.get("monthly_value") or "0")),
        start_date=date.today().isoformat(),
        description=(payload.get("description") or None),
    )
    c = await ContractRepository(db).create(data, created_by_id=str(getattr(aprovador_user, "id", None)))
    return str(c.id)


async def _exec_ativar_contrato(db, aprovador_user, payload: dict) -> str:
    from modules.crm.controllers.contract_controller import activate_contract
    c = await activate_contract(
        contract_id=str(payload["contract_id"]), current_user=aprovador_user, db=db)
    return str(getattr(c, "id", payload["contract_id"]))


async def _exec_enviar_proposta(db, aprovador_user, payload: dict) -> str:
    from modules.crm.controllers.proposal_controller import send_proposal
    p = await send_proposal(
        proposal_id=str(payload["proposal_id"]), current_user=aprovador_user, db=db)
    return str(getattr(p, "id", payload["proposal_id"]))


registrar_executor("criar_contrato", _exec_criar_contrato)
registrar_executor("ativar_contrato", _exec_ativar_contrato)
registrar_executor("enviar_proposta", _exec_enviar_proposta)


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
registrar_acao("crm", "criar_relatorio_visita",
               "iniciar um relatório de visita técnica/comercial. dados: cliente_nome "
               "(obrigatório), panorama, data_visita (AAAA-MM-DD). Nasce 'rascunho' "
               "(montar/PDF/lead é humano).",
               _propor_criar_relatorio_visita)
registrar_acao("crm", "criar_reuniao",
               "agendar uma reunião. dados: titulo (obrigatório), quando_iso "
               "(AAAA-MM-DDTHH:MM, obrigatório), cliente_nome, local, tipo, notes. "
               "Nasce 'sugerido' (confirmação é humana).",
               _propor_criar_reuniao)
registrar_acao("crm", "registrar_followup",
               "registrar um follow-up p/ um cliente/lead/deal. dados: mensagem "
               "(obrigatório), deal_id/lead_id/cliente_id, canal, template. Nasce "
               "'proposto' sem telefone (o envio ao cliente é humano).",
               _propor_registrar_followup)
registrar_acao("crm", "criar_contrato",
               "Criar um RASCUNHO de contrato na Central — aprovação = diretoria. dados: "
               "cliente (obrig.), produto, valor, prazo. NÃO cria nada agora; o contrato "
               "(status DRAFT) só é criado quando a diretoria aprovar na Central.",
               _propor_criar_contrato)
registrar_acao("crm", "ativar_contrato",
               "Propor a ATIVAÇÃO (vigência) de um contrato na Central — aprovação = "
               "diretoria. dados: contrato_id ou contrato_numero (obrig.). NÃO ativa "
               "agora; a ativação (MRR/faturamento) só roda ao aprovar na Central.",
               _propor_ativar_contrato)
registrar_acao("crm", "enviar_proposta",
               "Propor o ENVIO de uma proposta AO CLIENTE (EXTERNO/LGPD) na Central — "
               "aprovação = diretoria. dados: proposta_id (obrig.), cliente. NÃO envia "
               "agora; o envio ao cliente só dispara ao aprovar na Central.",
               _propor_enviar_proposta)


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

        # PROVA "não executa/envia" (ações pesadas): se o caminho tocar QUALQUER
        # executor real (criar/ativar contrato, enviar proposta ao cliente), estoura.
        import modules.crm.repositories.contract_repository as _crepo
        import modules.crm.services.proposal_delivery as _pdel
        executou = {"n": 0}

        def _boom(nome):
            async def _b(*a, **k):
                executou["n"] += 1
                raise AssertionError(f"executor real {nome} NÃO pode ser chamado pela IA")
            return _b
        _orig = (_crepo.ContractRepository.create,
                 _crepo.ContractRepository.update_status,
                 _pdel.send_proposal_email)
        _crepo.ContractRepository.create = _boom("ContractRepository.create")
        _crepo.ContractRepository.update_status = _boom("ContractRepository.update_status")
        _pdel.send_proposal_email = _boom("proposal_delivery.send_proposal_email")

        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        async with Session() as db:
            lead_ids: list[str] = []
            task_ids: list[str] = []
            note_ids: list[str] = []
            visit_ids: list[str] = []
            meet_ids: list[str] = []
            fup_ids: list[str] = []
            heavy_ids: list[str] = []
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

                # ── (a) criar_relatorio_visita: 1 PENDENTE inerte 'rascunho', não executa, idempotente ──
                cli_v = f"{SENT} Cliente Visita"
                rv = await disp(db, _U(), _S(), acao="criar_relatorio_visita",
                                dados={"cliente_nome": cli_v, "data_visita": "2099-06-01",
                                       "panorama": "porte médio"})
                assert rv.get("status") == "pendente" and not rv.get("duplicado"), rv
                vid = rv["entity_id"]; visit_ids.append(vid)
                stv = (await db.execute(text("SELECT status FROM crm_visit_reports WHERE id=:i"), {"i": vid})).scalar()
                assert stv == "rascunho", f"visita nasceu {stv}, esperado 'rascunho' (inerte)"
                exec_v = (await db.execute(text(
                    "SELECT count(*) FROM crm_visit_reports WHERE cliente_nome LIKE :n AND status <> 'rascunho'"),
                    {"n": SENT + "%"})).scalar()
                assert exec_v == 0, "visita sentinela finalizada (executada) — não deveria"
                rv2 = await disp(db, _U(), _S(), acao="criar_relatorio_visita",
                                 dados={"cliente_nome": cli_v, "data_visita": "2099-06-01"})
                assert rv2.get("duplicado") is True, rv2
                print("TESTE a4 (criar_relatorio_visita: PENDENTE inerte 'rascunho', não executa, idempotente) PASS")

                # ── (a) criar_reuniao: 1 PENDENTE inerte 'sugerido', não executa, idempotente ──
                tit_m = f"{SENT} Reuniao"
                rm = await disp(db, _U(), _S(), acao="criar_reuniao",
                                dados={"titulo": tit_m, "quando_iso": "2099-06-02T14:30", "cliente_nome": "ACME"})
                assert rm.get("status") == "pendente" and not rm.get("duplicado"), rm
                mid = rm["entity_id"]; meet_ids.append(mid)
                row_m = (await db.execute(text(
                    "SELECT status, lembrete_enviado FROM crm_meetings WHERE id=:i"), {"i": mid})).mappings().first()
                assert row_m["status"] == "sugerido", f"reunião nasceu {row_m['status']}, esperado 'sugerido'"
                assert row_m["lembrete_enviado"] is False, "reunião pendente não pode ter lembrete enviado"
                exec_m = (await db.execute(text(
                    "SELECT count(*) FROM crm_meetings WHERE titulo LIKE :n AND status = 'confirmado'"),
                    {"n": SENT + "%"})).scalar()
                assert exec_m == 0, "reunião sentinela confirmada (executada) — não deveria"
                rm2 = await disp(db, _U(), _S(), acao="criar_reuniao",
                                 dados={"titulo": tit_m, "quando_iso": "2099-06-02T14:30", "cliente_nome": "ACME"})
                assert rm2.get("duplicado") is True, rm2
                print("TESTE a5 (criar_reuniao: PENDENTE inerte 'sugerido' (lembrete só p/ confirmado), idempotente) PASS")

                # ── (a) registrar_followup: 1 PENDENTE inerte 'proposto' SEM telefone, não envia, idempotente ──
                msg_f = f"{SENT} follow-up de teste"
                rf = await disp(db, _U(), _S(), acao="registrar_followup", dados={"mensagem": msg_f})
                assert rf.get("status") == "pendente" and not rf.get("duplicado"), rf
                fid = rf["entity_id"]; fup_ids.append(fid)
                row_f = (await db.execute(text(
                    "SELECT status, phone_e164 FROM crm_followups WHERE id=:i"), {"i": fid})).mappings().first()
                assert row_f["status"] == _FUP_STATUS_PROPOSTO, f"followup nasceu {row_f['status']}, esperado 'proposto'"
                assert row_f["phone_e164"] is None, "followup pendente NÃO pode ter telefone (worker enviaria)"
                # o worker só envia 'agendado' com phone: sentinela nunca vira 'agendado'/'enviado'
                exec_f = (await db.execute(text(
                    "SELECT count(*) FROM crm_followups WHERE mensagem LIKE :n AND status IN ('agendado','enviado')"),
                    {"n": SENT + "%"})).scalar()
                assert exec_f == 0, "followup sentinela ficou 'agendado'/'enviado' (executado) — não deveria"
                rf2 = await disp(db, _U(), _S(), acao="registrar_followup", dados={"mensagem": msg_f})
                assert rf2.get("duplicado") is True, rf2
                print("TESTE a6 (registrar_followup: PENDENTE inerte 'proposto' sem telefone, não envia, idempotente) PASS")

                # ── (a-pesadas) CENTRAL DE RASCUNHOS: criar/ativar contrato + enviar
                #    proposta viram AgentDraft inerte (status='rascunho', p/ DIRETORIA).
                #    O handler NUNCA executa (boom nos serviços reais → executou==0); os
                #    refs são resolvidos de linhas REAIS (o rascunho é inerte, não cria/
                #    ativa/envia — a execução real só roda na aprovação, coberta pelo
                #    scripts/orq/test_central_crm.py).
                cli_real = (await db.execute(text(
                    "SELECT name FROM clients WHERE coalesce(ativo,true)=true ORDER BY name LIMIT 1"))).scalar()
                ct_real = (await db.execute(text(
                    "SELECT contract_number FROM contracts WHERE contract_number IS NOT NULL LIMIT 1"))).scalar()
                prop_real = (await db.execute(text("SELECT id::text FROM proposals LIMIT 1"))).scalar()
                pesadas = [
                    ("criar_contrato", {"cliente": cli_real, "produto": "Portaria", "valor": "5000"}, "🟡", cli_real),
                    ("ativar_contrato", {"contrato_numero": ct_real}, "🔴", ct_real),
                    ("enviar_proposta", {"proposta_id": prop_real}, "🔴", prop_real),
                ]
                for acao, dados, gate_exp, ref_real in pesadas:
                    if not ref_real:
                        print(f"TESTE a-pesadas[{acao}] SKIP (sem dado real p/ resolver ref)")
                        continue
                    r = await disp(db, _U(), _S(), acao=acao, dados=dados)
                    assert r.get("status") == "rascunho" and not r.get("duplicado"), (acao, r)
                    did = r["draft_id"]; heavy_ids.append(did)
                    row = (await db.execute(text(
                        "SELECT tipo, modulo, status, gate FROM agent_drafts WHERE id = CAST(:i AS uuid)"),
                        {"i": did})).mappings().first()
                    assert row and row["tipo"] == acao and row["modulo"] == "crm" \
                        and row["status"] == "rascunho" and row["gate"] == gate_exp, \
                        (acao, dict(row) if row else None)
                    # idempotência: 2ª chamada não duplica o rascunho vivo
                    r2 = await disp(db, _U(), _S(), acao=acao, dados=dados)
                    assert r2.get("duplicado") is True, (acao, r2)
                # enviar_proposta 🔴: resumo inequívoco de que vai AO CLIENTE (externo/LGPD)
                if prop_real:
                    resumo_env = (await db.execute(text(
                        "SELECT resumo FROM agent_drafts WHERE tipo='enviar_proposta' "
                        "AND id = ANY(CAST(:i AS uuid[]))"), {"i": heavy_ids})).scalar()
                    assert resumo_env and "CLIENTE" in resumo_env.upper() and "LGPD" in resumo_env.upper(), resumo_env
                # ref obrigatória → recusa (sem rascunho)
                assert "erro" in await disp(db, _U(), _S(), acao="ativar_contrato", dados={})
                assert "erro" in await disp(db, _U(), _S(), acao="enviar_proposta", dados={})
                # executor registrado p/ cada tipo (mas NÃO chamado na criação)
                from .acoes.rascunho import EXECUTORES
                assert {"criar_contrato", "ativar_contrato", "enviar_proposta"} <= set(EXECUTORES), set(EXECUTORES)
                assert executou["n"] == 0, "executor real de contrato/proposta foi chamado na CRIAÇÃO"
                print("TESTE a-pesadas (criar/ativar contrato + enviar proposta → AgentDraft "
                      "'rascunho' p/ DIRETORIA, resumo AO CLIENTE/LGPD, executor registrado "
                      "mas NÃO roda na criação, idempotente) PASS")

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

                # ── (d) prova global: NADA foi executado/enviado (só PENDENTES inertes) ──
                assert executou["n"] == 0, "executor real de contrato/proposta rodou (IA executou/enviou)"
                print("TESTE d (as 6 leves PROPÕEM sem executar + as 3 pesadas p/ DIRETORIA: "
                      "contrato NUNCA criado/ativado, proposta NUNCA enviada ao cliente) PASS")
                print("\nTODAS AS PROVAS DE tools_acao_crm.py PASSARAM")
            finally:
                _crepo.ContractRepository.create = _orig[0]
                _crepo.ContractRepository.update_status = _orig[1]
                _pdel.send_proposal_email = _orig[2]
                if heavy_ids:  # pesadas = AgentDraft + sino (reference_id=draft) + audit (entity_id=draft)
                    await db.execute(text(
                        "DELETE FROM communication_notifications WHERE reference_id = ANY(:i)"), {"i": heavy_ids})
                    await db.execute(text(
                        "DELETE FROM audit_logs WHERE details->>'entity_id' = ANY(:i)"), {"i": heavy_ids})
                    await db.execute(text(
                        "DELETE FROM agent_drafts WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": heavy_ids})
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
                for tbl, ids in (("crm_visit_reports", visit_ids), ("crm_meetings", meet_ids),
                                 ("crm_followups", fup_ids)):
                    if ids:
                        await db.execute(text(f"DELETE FROM {tbl} WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": ids})
                        await db.execute(text(
                            "DELETE FROM audit_logs WHERE details->>'entity_id' = ANY(:i)"), {"i": ids})
                await _limpar(db, "lead:%" + SENT + "%")
                await _limpar(db, "tarefa:%" + SENT + "%")
                await _limpar(db, "anota:%")
                await _limpar(db, "visita:%" + SENT.lower() + "%")
                await _limpar(db, "reuniao:%" + SENT.lower() + "%")
                await _limpar(db, "followup:%")
                await db.commit()
                rem_l = (await db.execute(text(
                    "SELECT count(*) FROM leads WHERE name LIKE :n"), {"n": SENT + "%"})).scalar()
                rem_t = (await db.execute(text(
                    "SELECT count(*) FROM crm_tasks WHERE title LIKE :n"), {"n": SENT + "%"})).scalar()
                rem_n = (await db.execute(text(
                    "SELECT count(*) FROM crm_client_notes WHERE nota LIKE :n"), {"n": "%" + SENT + "%"})).scalar()
                rem_v = (await db.execute(text(
                    "SELECT count(*) FROM crm_visit_reports WHERE cliente_nome LIKE :n"), {"n": SENT + "%"})).scalar()
                rem_m = (await db.execute(text(
                    "SELECT count(*) FROM crm_meetings WHERE titulo LIKE :n"), {"n": SENT + "%"})).scalar()
                rem_f = (await db.execute(text(
                    "SELECT count(*) FROM crm_followups WHERE mensagem LIKE :n"), {"n": SENT + "%"})).scalar()
                rem_d = (await db.execute(text(
                    "SELECT count(*) FROM agent_drafts WHERE id = ANY(CAST(:i AS uuid[]))"),
                    {"i": heavy_ids or ["00000000-0000-0000-0000-000000000000"]})).scalar()
                assert rem_l == 0 and rem_t == 0 and rem_n == 0 and rem_v == 0 and rem_m == 0 \
                    and rem_f == 0 and rem_d == 0, \
                    f"remanescentes lead={rem_l} tarefa={rem_t} nota={rem_n} visita={rem_v} " \
                    f"reuniao={rem_m} followup={rem_f} rascunho={rem_d}"
                print("LIMPEZA OK — 0 remanescentes (leads/crm_tasks/crm_client_notes/"
                      "crm_visit_reports/crm_meetings/crm_followups/agent_drafts/audit/sino)")
        await eng.dispose()

    asyncio.run(main())


# ── ATUALIZAR CLIENTE (lacuna 1 de 14: editar registro que já existe) ─────────────────
# Medido em 24/08/2026: das 112 tools do MCP barradas sem equivalente in-process, 43 eram
# lacuna real, e 14 delas são "editar/arquivar registro existente". O motor in-process CRIA,
# LÊ e gera documento — mas não EDITAVA. Na prática: pelo chat o Jordan cria um cliente e
# anota nele, e não corrigia o CNPJ de um cliente já cadastrado.
#
# ⚠️ `update_client` vive em `modules/clients`, NÃO no crm — o `crm/client_controller.py` não
# tem PUT nenhum. Fica registrado porque o próximo vai procurar no CRM, como eu procurei.

#: Campos que são CADASTRO: corrigir qualquer um deles é reversível e não move dinheiro.
_CLIENTE_CADASTRAL = frozenset({
    "name", "trading_name", "document_number", "email", "phone", "mobile", "whatsapp",
    "website", "segment", "notes", "municipal_registration", "state_registration",
    "address_street", "address_number", "address_complement", "address_neighborhood",
    "address_city", "address_state", "address_zipcode",
    "financial_contact_name", "financial_contact_email", "financial_contact_phone",
    "technical_contact_name", "technical_contact_email", "technical_contact_phone",
})

#: Campos do MESMO endpoint que mudam CONDIÇÃO COMERCIAL. O grau tem de sair do CAMPO, nunca
#: do nome da tool: `atualizar_cliente` soa cadastral e `credit_limit` é dinheiro. É a mesma
#: lição das 54 etiquetas erradas do manifesto — o nome diz cadastro e o corpo faz dinheiro.
#:
#: DECISÃO DO JORDAN, 24/08/2026 — estes ficam NA TELA, POR ENQUANTO. O raciocínio dele:
#:   "O valor do chat é corrigir dado errado rápido — CNPJ digitado errado, endereço velho.
#:    Limite de crédito não é correção, é decisão comercial, e decisão comercial se toma
#:    olhando o histórico do cliente, que a tela mostra e o chat não."
#: Ganho colateral: a tool fica 🟡 limpo, sem nascer com dois graus.
#: ⚠️ A data está aqui de propósito. Decisão de produto sem data envelhece como o comentário
#: que dizia "zero batidas de almoço" e continuou sendo lido quando já havia 288: verdadeiro
#: sobre agosto, falso sobre novembro, e quem lê acredita. Se ele mudar de ideia, é uma linha
#: — `credit_limit` sai daqui e entra em 🔴 com OTP.
_CLIENTE_COMERCIAL = frozenset({"credit_limit", "payment_terms", "billing_day", "status",
                                "is_vip", "client_type", "account_manager_id", "sales_rep_id"})


async def _propor_atualizar_cliente(db, user, scope, *, cliente="", **campos) -> dict[str, Any]:
    ref = str(cliente or "").strip()
    if not ref:
        return {"erro": "informe o cliente (CNPJ, código ou nome)"}
    campos = {k: v for k, v in campos.items() if v not in (None, "")}
    if not campos:
        return {"erro": "informe ao menos um campo para corrigir (ex.: document_number, email)"}

    desconhecidos = sorted(set(campos) - _CLIENTE_CADASTRAL - _CLIENTE_COMERCIAL)
    if desconhecidos:
        return {"erro": f"campo(s) que não existem no cadastro: {desconhecidos}"}
    comerciais = sorted(set(campos) & _CLIENTE_COMERCIAL)
    if comerciais:
        # Fail-closed por CAMPO: recuso em vez de propor em 🟡. Limite de crédito e prazo de
        # pagamento são decisão comercial do Jordan, não correção de cadastro.
        return {"erro": f"{comerciais} muda CONDIÇÃO COMERCIAL, não cadastro — isso não passa "
                        f"por aqui; peça ao Jordan pela tela de clientes."}

    row = (await db.execute(text(
        "SELECT id::text AS id, name, document_number, email, phone FROM clients "
        "WHERE id::text = :r OR document_number = :r OR upper(name) = upper(:r) "
        "OR upper(trading_name) = upper(:r) LIMIT 1"), {"r": ref})).mappings().first()
    if not row:
        return {"erro": f"cliente '{ref}' não encontrado pelo id, CNPJ ou nome."}

    # De→Para no resumo: aprovar sem ver o valor ANTERIOR é aprovar às cegas.
    antes = {k: row.get(k) for k in campos if k in row}
    mudancas = "; ".join(
        f"{k}: {antes.get(k) if antes.get(k) not in (None, '') else '(vazio)'} → {v}"
        for k, v in campos.items())
    return await criar_rascunho(
        db, user, tipo="atualizar_cliente", modulo="crm", gate="🟡", requires_otp=False,
        roles_aprovador=ROLES_COMERCIAL,
        idempotency_key=f"cliente_atualizar:{row['id']}:{_slug(mudancas)[:40]}",
        titulo=f"Corrigir cadastro de {row['name']}",
        resumo=f"Aprovar CORRIGE o cadastro de {row['name']}. {mudancas}. "
               f"Só cadastro — nada de limite de crédito, prazo ou status.",
        payload={"client_id": row["id"], "campos": campos, "nome": row["name"]},
    )


async def _exec_atualizar_cliente(db, aprovador_user, payload: dict) -> str:
    """Executa NA APROVAÇÃO, com a identidade de quem aprovou — nunca a de quem propôs."""
    from uuid import UUID  # noqa: PLC0415

    from core.database.session import SyncSessionLocal  # noqa: PLC0415
    from modules.clients.controllers.client_controller import update_client  # noqa: PLC0415
    from modules.clients.schemas.client_schemas import ClientUpdate  # noqa: PLC0415
    from modules.clients.services.client_service import ClientService  # noqa: PLC0415

    # `update_client` é async mas o serviço dele é SÍNCRONO (o controller roda com
    # `Depends(get_db)` sync). Sessão própria, como em `_espelho_render`.
    with SyncSessionLocal() as s:
        cli = await update_client(current_user=aprovador_user,
                                  client_id=UUID(str(payload["client_id"])),
                                  data=ClientUpdate(**payload["campos"]),
                                  service=ClientService(s))
    return str(getattr(cli, "id", payload["client_id"]))


registrar_executor("atualizar_cliente", _exec_atualizar_cliente)
registrar_acao("crm", "atualizar_cliente",
               "CORRIGIR o cadastro de um cliente que já existe (CNPJ digitado errado, e-mail, "
               "telefone, endereço, nome). dados: cliente (CNPJ, código ou nome — obrig.) + os "
               "campos a corrigir (document_number, name, email, phone, address_city…). "
               "Vira rascunho: a correção só é gravada quando um humano aprovar. NÃO mexe em "
               "limite de crédito, prazo de pagamento nem status.",
               _propor_atualizar_cliente)


# ── ATUALIZAR PROPOSTA (2ª das 14) ───────────────────────────────────────────────────
# ⚠️ MÓDULO: `crm/controllers/proposal_controller.py:445`. Existem DUAS `update_proposal` no
# repositório (a outra é de `bidding`) — `grep -l | head -1` devolve a errada.

#: Cadastro e texto da proposta: corrigir é reversível e não mexe no dinheiro dela.
_PROPOSTA_CADASTRAL = frozenset({
    "title", "description", "client_name", "client_email", "client_phone", "client_company",
    "client_document", "client_address", "notes", "terms_conditions", "subject", "message",
    "recipient_email", "valid_until",
})

#: O MESMO endpoint que corrige um e-mail muda desconto, imposto, parcelamento e STATUS.
#: Desconto e imposto são o valor da proposta; status move o funil. Grau sai do CAMPO.
_PROPOSTA_VALOR = frozenset({
    "discount_type", "discount_value", "discount_reason", "taxes", "payment_terms",
    "payment_conditions", "installments", "status", "proposal_type",
})


async def _propor_atualizar_proposta(db, user, scope, *, proposta="", **campos) -> dict[str, Any]:
    ref = str(proposta or "").strip()
    if not ref:
        return {"erro": "informe a proposta (número ou id)"}
    campos = {k: v for k, v in campos.items() if v not in (None, "")}
    if not campos:
        return {"erro": "informe ao menos um campo para corrigir (ex.: client_document, title)"}

    desconhecidos = sorted(set(campos) - _PROPOSTA_CADASTRAL - _PROPOSTA_VALOR)
    if desconhecidos:
        return {"erro": f"campo(s) que a proposta não tem: {desconhecidos}"}
    valor = sorted(set(campos) & _PROPOSTA_VALOR)
    if valor:
        return {"erro": f"{valor} muda o VALOR ou o ESTÁGIO da proposta, não o cadastro dela "
                        f"— isso não passa por aqui; use a tela de propostas."}

    row = (await db.execute(text(
        # ⚠️ a coluna é `number`, NÃO `proposal_number` — medido no information_schema, não suposto.
        "SELECT id::text AS id, number, title, client_name, client_document, status::text "
        "FROM proposals WHERE id::text = :r OR number = :r LIMIT 1"),
        {"r": ref})).mappings().first()
    if not row:
        return {"erro": f"proposta '{ref}' não encontrada pelo número ou id."}

    antes = {k: row.get(k) for k in campos if k in row}
    mudancas = "; ".join(
        f"{k}: {antes.get(k) if antes.get(k) not in (None, '') else '(vazio)'} → {v}"
        for k, v in campos.items())
    return await criar_rascunho(
        db, user, tipo="atualizar_proposta", modulo="crm", gate="🟡", requires_otp=False,
        roles_aprovador=ROLES_COMERCIAL,
        idempotency_key=f"proposta_atualizar:{row['id']}:{_slug(mudancas)[:40]}",
        titulo=f"Corrigir proposta {row['number']}",
        resumo=f"Aprovar CORRIGE a proposta {row['number']} "
               f"({row['client_name']}, status {row['status']}). {mudancas}. "
               f"Só cadastro/texto — desconto, imposto e status não passam por aqui.",
        payload={"proposal_id": row["id"], "campos": campos,
                 "numero": row["number"]},
    )


async def _exec_atualizar_proposta(db, aprovador_user, payload: dict) -> str:
    """Executa NA APROVAÇÃO, com a identidade de quem aprovou."""
    # ⚠️ `crm`, não `bidding` — são duas `update_proposal` no repositório.
    from modules.crm.controllers.proposal_controller import update_proposal  # noqa: PLC0415
    from modules.crm.schemas.proposal import ProposalUpdate  # noqa: PLC0415

    p = await update_proposal(proposal_id=str(payload["proposal_id"]),
                              data=ProposalUpdate(**payload["campos"]),
                              current_user=aprovador_user, db=db)
    return str(getattr(p, "id", payload["proposal_id"]))


registrar_executor("atualizar_proposta", _exec_atualizar_proposta)
registrar_acao("crm", "atualizar_proposta",
               "CORRIGIR o cadastro/texto de uma proposta que já existe (nome ou CNPJ do "
               "cliente, título, descrição, validade, condições em texto). dados: proposta "
               "(número ou id — obrig.) + os campos (client_document, client_name, title, "
               "description, valid_until, terms_conditions…). Vira rascunho: só grava quando "
               "um humano aprovar. NÃO mexe em desconto, imposto, parcelamento nem status.",
               _propor_atualizar_proposta)


# ── REATIVAR LEAD (3ª das 14) ────────────────────────────────────────────────────────
# Rota PATCH /crm/leads/{id}/status · corrotina `crm/…/lead_controller.py:201`.
_LEAD_STATUS = ("new", "contacted", "qualified", "proposal", "negotiation", "won", "lost")

#: 'won' NÃO passa por aqui: marcar lead como ganho é fechamento comercial, e fechamento tem
#: caminho próprio (aceitar_proposta / close_opportunity), com o que ele arrasta junto —
#: comissão, contrato, MRR. Reativar é trazer de volta, não declarar vitória.
_LEAD_STATUS_PERMITIDO = ("new", "contacted", "qualified", "proposal", "negotiation")


async def _propor_reativar_lead(db, user, scope, *, lead="", status="contacted",
                                motivo="", **_) -> dict[str, Any]:
    ref = str(lead or "").strip()
    if not ref:
        return {"erro": "informe o lead (id, nome ou empresa)"}
    novo = str(status or "contacted").strip().lower()
    if novo not in _LEAD_STATUS_PERMITIDO:
        if novo in _LEAD_STATUS:
            return {"erro": f"'{novo}' é fechamento comercial, não reativação — use a tela "
                            f"ou o caminho de proposta. Aqui: {', '.join(_LEAD_STATUS_PERMITIDO)}"}
        return {"erro": f"status inválido; use um de: {', '.join(_LEAD_STATUS_PERMITIDO)}"}

    row = (await db.execute(text(
        "SELECT id::text AS id, name, company, status::text AS status FROM leads "
        "WHERE id::text = :r OR upper(name) = upper(:r) OR upper(company) = upper(:r) "
        "LIMIT 1"), {"r": ref})).mappings().first()
    if not row:
        return {"erro": f"lead '{ref}' não encontrado por id, nome ou empresa."}
    if row["status"] == novo:
        return {"erro": f"o lead {row['name']} já está em '{novo}' — nada a mudar."}

    return await criar_rascunho(
        db, user, tipo="reativar_lead", modulo="crm", gate="🟡", requires_otp=False,
        roles_aprovador=ROLES_COMERCIAL,
        idempotency_key=f"lead_status:{row['id']}:{novo}",
        titulo=f"Reativar lead {row['name']}",
        resumo=f"Aprovar move o lead {row['name']}"
               + (f" ({row['company']})" if row["company"] else "")
               + f" de '{row['status']}' para '{novo}'."
               + (f" Motivo: {motivo[:120]}." if motivo else "")
               + " Só reativação — fechamento (won) não passa por aqui.",
        payload={"lead_id": row["id"], "status": novo, "notes": motivo or None,
                 "nome": row["name"], "de": row["status"]},
    )


async def _exec_reativar_lead(db, aprovador_user, payload: dict) -> str:
    from modules.crm.controllers.lead_controller import update_lead_status  # noqa: PLC0415
    from modules.crm.schemas.lead import LeadStatusUpdate  # noqa: PLC0415

    lead = await update_lead_status(
        lead_id=str(payload["lead_id"]),
        data=LeadStatusUpdate(status=payload["status"], notes=payload.get("notes")),
        current_user=aprovador_user, db=db)
    return str(getattr(lead, "id", payload["lead_id"]))


registrar_executor("reativar_lead", _exec_reativar_lead)
registrar_acao("crm", "reativar_lead",
               "REATIVAR um lead frio, trazendo-o de volta ao funil. dados: lead (id, nome ou "
               "empresa — obrig.), status (new|contacted|qualified|proposal|negotiation, "
               "padrão contacted), motivo. Vira rascunho. NÃO marca como ganho ('won'): "
               "fechamento tem caminho próprio, com comissão e contrato junto.",
               _propor_reativar_lead)


# ── MARCAR DEAL PERDIDO (4ª das 14) ──────────────────────────────────────────────────
# Rota POST /crm/opportunities/{id}/close · corrotina `close_opportunity`.
_MOTIVOS_PERDA = ("price", "competitor", "no_budget", "no_decision", "timing",
                  "product_fit", "no_response", "other")


async def _propor_marcar_deal_perdido(db, user, scope, *, deal="", motivo="",
                                      concorrente="", observacao="", **_) -> dict[str, Any]:
    ref = str(deal or "").strip()
    if not ref:
        return {"erro": "informe o deal (id ou título)"}
    m = str(motivo or "").strip().lower()
    if m not in _MOTIVOS_PERDA:
        return {"erro": f"motivo da perda é obrigatório; use um de: {', '.join(_MOTIVOS_PERDA)}"}

    row = (await db.execute(text(
        # ⚠️ a coluna é `value`, NÃO `estimated_value`.
        "SELECT id::text AS id, title, value, stage::text AS stage FROM opportunities "
        "WHERE id::text = :r OR upper(title) = upper(:r) LIMIT 1"), {"r": ref})).mappings().first()
    if not row:
        return {"erro": f"deal '{ref}' não encontrado por id ou título."}

    # 🟡 e não 🔵: fechar como perdido tira o deal da PREVISÃO. Não move dinheiro que saiu,
    # mas muda o forecast que o Jordan usa para decidir — merece um humano confirmando.
    return await criar_rascunho(
        db, user, tipo="marcar_deal_perdido", modulo="crm", gate="🟡", requires_otp=False,
        roles_aprovador=ROLES_COMERCIAL,
        idempotency_key=f"deal_perdido:{row['id']}",
        titulo=f"Marcar deal PERDIDO: {row['title']}",
        resumo=f"Aprovar FECHA o deal '{row['title']}' como PERDIDO (motivo: {m}"
               + (f", concorrente: {concorrente}" if concorrente else "")
               + f"). Ele sai da previsão de vendas — valor estimado "
               + f"R$ {float(row['value'] or 0):,.2f}, estágio atual {row['stage']}.",
        payload={"opportunity_id": row["id"], "motivo": m,
                 "concorrente": concorrente or None, "observacao": observacao or None,
                 "titulo": row["title"]},
    )


async def _exec_marcar_deal_perdido(db, aprovador_user, payload: dict) -> str:
    from modules.crm.controllers.opportunity_controller import close_opportunity  # noqa: PLC0415
    from modules.crm.schemas.opportunity import OpportunityClose  # noqa: PLC0415

    o = await close_opportunity(
        opportunity_id=str(payload["opportunity_id"]),
        data=OpportunityClose(won=False, loss_reason=payload["motivo"],
                              competitor=payload.get("concorrente"),
                              notes=payload.get("observacao")),
        current_user=aprovador_user, db=db)
    return str(getattr(o, "id", payload["opportunity_id"]))


registrar_executor("marcar_deal_perdido", _exec_marcar_deal_perdido)
registrar_acao("crm", "marcar_deal_perdido",
               "Fechar um deal como PERDIDO. dados: deal (id ou título — obrig.), motivo "
               "(obrig., um de: " + ", ".join(_MOTIVOS_PERDA) + "), concorrente, observacao. "
               "Vira rascunho — o deal sai da previsão de vendas só quando um humano aprovar.",
               _propor_marcar_deal_perdido)


# ── CRIAR CLIENTE (5ª das 14) ────────────────────────────────────────────────────────
# ⚠️ MÓDULO: `clients/controllers/client_controller.py:67`. Há DUAS `create_client` no
# repositório (a outra é do GED) — conferir o caminho, não o nome.
# O in-process já criava LEAD; cliente é outra coisa: lead é quem talvez compre, cliente é
# quem já é da casa e passa a existir para contrato, NFS-e e cobrança.


async def _propor_criar_cliente(db, user, scope, *, nome="", cnpj="", email="",
                                telefone="", cidade="", uf="", **_) -> dict[str, Any]:
    nome = str(nome or "").strip()
    doc = "".join(ch for ch in str(cnpj or "") if ch.isdigit())
    if not nome:
        return {"erro": "nome do cliente é obrigatório"}
    if len(doc) not in (11, 14):
        return {"erro": "CNPJ (14 dígitos) ou CPF (11) é obrigatório — sem documento o "
                        "cliente não serve para contrato nem NFS-e"}

    ja = (await db.execute(text(
        "SELECT name, code FROM clients WHERE document_number = :d LIMIT 1"),
        {"d": doc})).mappings().first()
    if ja:
        # Antes de propor, checa duplicata: cliente repetido quebra MRR, cobrança e a régua
        # de dedup. Recusar aqui é mais barato que reconciliar depois.
        return {"erro": f"já existe cliente com esse documento: {ja['name']} "
                        f"({ja['code']}). Para corrigir os dados dele, use atualizar_cliente."}

    campos = {"name": nome, "document_number": doc}
    for k, v in (("email", email), ("phone", telefone),
                 ("address_city", cidade), ("address_state", uf)):
        if str(v or "").strip():
            campos[k] = str(v).strip()

    return await criar_rascunho(
        db, user, tipo="criar_cliente", modulo="crm", gate="🟡", requires_otp=False,
        roles_aprovador=ROLES_COMERCIAL,
        idempotency_key=f"cliente_criar:{doc}",
        titulo=f"Cadastrar cliente {nome}",
        resumo=f"Aprovar CADASTRA o cliente {nome} (doc {doc})"
               + (f", {cidade}/{uf}" if cidade else "")
               + ". Ele passa a existir para contrato, NFS-e e cobrança. "
               + "Nasce sem limite de crédito e sem condição comercial — isso é da tela.",
        payload={"campos": campos, "nome": nome, "documento": doc},
    )


async def _exec_criar_cliente(db, aprovador_user, payload: dict) -> str:
    from core.database.session import SyncSessionLocal  # noqa: PLC0415
    # ⚠️ `modules.clients`, NÃO o do GED nem o do crm (que sequer tem create).
    from modules.clients.controllers.client_controller import create_client  # noqa: PLC0415
    from modules.clients.schemas.client_schemas import ClientCreate  # noqa: PLC0415
    from modules.clients.services.client_service import ClientService  # noqa: PLC0415

    with SyncSessionLocal() as s:
        cli = await create_client(data=ClientCreate(**payload["campos"]),
                                  current_user=aprovador_user, service=ClientService(s))
    return str(getattr(cli, "id", payload["documento"]))


registrar_executor("criar_cliente", _exec_criar_cliente)
registrar_acao("crm", "criar_cliente",
               "CADASTRAR um cliente novo. dados: nome (obrig.), cnpj (CNPJ ou CPF, obrig.), "
               "email, telefone, cidade, uf. Vira rascunho — só existe depois que um humano "
               "aprovar. Recusa se já houver cliente com o mesmo documento. Nasce sem limite "
               "de crédito e sem condição comercial.",
               _propor_criar_cliente)


# ── ATUALIZAR CONTRATO (6ª das 14) — a que exige o grau mais fino ────────────────────
# ⚠️⚠️ MÓDULO: `crm/controllers/contract_controller.py:618`. Existem QUATRO `update_contract`
# no repositório: crm (esta), clients, bidding e **people_management/hr** — a última escreve
# CONTRATO DE TRABALHO de CLT. Usar a errada é editar o vínculo de 56 pessoas, em território
# do T2. `grep -l | head -1` devolve a de clients. Confira sempre o caminho.

#: Cadastro e texto do contrato: corrigir nome ou descrição não move dinheiro nem prazo.
_CONTRATO_CADASTRAL = frozenset({"name", "description"})

#: DINHEIRO. `monthly_value` VIRA MRR — é o número que o Jordan usa para saber o tamanho da
#: casa. `setup_fee` e `total_value` são cobrança. Nada disso é correção de cadastro.
_CONTRATO_DINHEIRO = frozenset({"monthly_value", "total_value", "setup_fee",
                                "adjustment_fixed_percent", "adjustment_index",
                                "adjustment_enabled"})

#: VIGÊNCIA e RENOVAÇÃO: mudam quando o contrato vale e quando renova sozinho. Um
#: `auto_renewal` alterado por engano renova um contrato que a empresa ia encerrar.
_CONTRATO_VIGENCIA = frozenset({"end_date", "auto_renewal", "renewal_period_months",
                                "renewal_notification_days", "notice_period_days",
                                "grace_period_days"})


async def _propor_atualizar_contrato(db, user, scope, *, contrato="", **campos) -> dict[str, Any]:
    ref = str(contrato or "").strip()
    if not ref:
        return {"erro": "informe o contrato (número ou id)"}
    campos = {k: v for k, v in campos.items() if v not in (None, "")}
    if not campos:
        return {"erro": "informe ao menos um campo (name, description)"}

    # Fail-closed em TRÊS níveis, e a ordem importa: dinheiro primeiro, porque é o que dói.
    dinheiro = sorted(set(campos) & _CONTRATO_DINHEIRO)
    if dinheiro:
        return {"erro": f"{dinheiro} muda o VALOR do contrato — e valor de contrato vira MRR. "
                        f"Isso não passa pelo chat; é da tela de contratos, com o Jordan."}
    vigencia = sorted(set(campos) & _CONTRATO_VIGENCIA)
    if vigencia:
        return {"erro": f"{vigencia} muda VIGÊNCIA ou RENOVAÇÃO — um auto_renewal alterado por "
                        f"engano renova contrato que ia ser encerrado. Use a tela."}
    fora = sorted(set(campos) - _CONTRATO_CADASTRAL)
    if fora:
        # Fail-closed no DESCONHECIDO: campo que eu não classifiquei não vira 🟡 por omissão.
        return {"erro": f"campo(s) não liberado(s) por aqui: {fora}. Só nome e descrição — "
                        f"o resto do contrato é decisão comercial."}

    row = (await db.execute(text(
        "SELECT id::text AS id, contract_number, name, status::text AS status, monthly_value "
        "FROM contracts WHERE id::text = :r OR contract_number = :r LIMIT 1"),
        {"r": ref})).mappings().first()
    if not row:
        return {"erro": f"contrato '{ref}' não encontrado pelo número ou id."}

    antes = {k: row.get(k) for k in campos if k in row}
    mudancas = "; ".join(
        f"{k}: {antes.get(k) if antes.get(k) not in (None, '') else '(vazio)'} → {v}"
        for k, v in campos.items())
    return await criar_rascunho(
        db, user, tipo="atualizar_contrato", modulo="crm", gate="🟡", requires_otp=False,
        roles_aprovador=ROLES_COMERCIAL,
        idempotency_key=f"contrato_atualizar:{row['id']}:{_slug(mudancas)[:40]}",
        titulo=f"Corrigir contrato {row['contract_number']}",
        resumo=f"Aprovar CORRIGE o contrato {row['contract_number']} (status {row['status']}, "
               f"mensal R$ {float(row['monthly_value'] or 0):,.2f} — INALTERADO). {mudancas}. "
               f"Só nome e descrição: valor, vigência e renovação não passam por aqui.",
        payload={"contract_id": row["id"], "campos": campos,
                 "numero": row["contract_number"]},
    )


async def _exec_atualizar_contrato(db, aprovador_user, payload: dict) -> str:
    # ⚠️ `modules.crm`, NUNCA `people_management.hr` — aquela é contrato de TRABALHO.
    from modules.crm.controllers.contract_controller import update_contract  # noqa: PLC0415
    from modules.crm.schemas.contract import ContractUpdate  # noqa: PLC0415

    c = await update_contract(contract_id=str(payload["contract_id"]),
                              data=ContractUpdate(**payload["campos"]),
                              current_user=aprovador_user, db=db)
    return str(getattr(c, "id", payload["contract_id"]))


registrar_executor("atualizar_contrato", _exec_atualizar_contrato)
registrar_acao("crm", "atualizar_contrato",
               "CORRIGIR o nome ou a descrição de um contrato que já existe. dados: contrato "
               "(número ou id — obrig.), name, description. Vira rascunho. NÃO mexe em valor "
               "mensal (vira MRR), vigência, renovação, reajuste nem multa — isso é da tela.",
               _propor_atualizar_contrato)


# ── CONFIRMAR REUNIÃO (9ª das 14) ────────────────────────────────────────────────────
# Rota POST /crm/reunioes/confirmar · `crm/…/growth_controller.py:1770`.
async def _propor_confirmar_reuniao(db, user, scope, *, reuniao="", **_) -> dict[str, Any]:
    ref = str(reuniao or "").strip()
    if not ref:
        return {"erro": "informe a reunião (id, título ou nome do cliente)"}
    row = (await db.execute(text(
        "SELECT id::text AS id, titulo, cliente_nome, quando, status::text AS status "
        "FROM crm_meetings WHERE id::text = :r OR upper(titulo) = upper(:r) "
        "OR upper(cliente_nome) = upper(:r) ORDER BY quando DESC LIMIT 1"),
        {"r": ref})).mappings().first()
    if not row:
        return {"erro": f"reunião '{ref}' não encontrada por id, título ou cliente."}
    if (row["status"] or "").lower() == "confirmada":
        return {"erro": f"a reunião '{row['titulo']}' já está confirmada."}
    return await criar_rascunho(
        db, user, tipo="confirmar_reuniao", modulo="crm", gate="🟡", requires_otp=False,
        roles_aprovador=ROLES_COMERCIAL,
        idempotency_key=f"reuniao_confirmar:{row['id']}",
        titulo=f"Confirmar reunião: {row['titulo']}",
        resumo=f"Aprovar CONFIRMA a reunião '{row['titulo']}' com {row['cliente_nome']} "
               f"em {row['quando']}. Status atual: {row['status']}.",
        payload={"meeting_id": row["id"], "titulo": row["titulo"]},
    )


async def _exec_confirmar_reuniao(db, aprovador_user, payload: dict) -> str:
    from modules.crm.controllers.growth_controller import confirmar_reuniao_ep  # noqa: PLC0415
    from modules.crm.controllers.growth_controller import MeetingActionIn  # noqa: PLC0415

    await confirmar_reuniao_ep(data=MeetingActionIn(meeting_id=str(payload["meeting_id"])),
                               db=db)
    return str(payload["meeting_id"])


registrar_executor("confirmar_reuniao", _exec_confirmar_reuniao)
registrar_acao("crm", "confirmar_reuniao",
               "CONFIRMAR uma reunião agendada. dados: reuniao (id, título ou nome do cliente "
               "— obrig.). Vira rascunho: a confirmação só vale depois da aprovação.",
               _propor_confirmar_reuniao)


# ── ADICIONAR ACHADOS À VISITA (10ª das 14) ──────────────────────────────────────────
# Rota POST /crm/visitas/achados · service `crm/services/visit_reports.py:80`.
async def _propor_adicionar_achados_visita(db, user, scope, *, visita="", achados="",
                                           **_) -> dict[str, Any]:
    ref = str(visita or "").strip()
    if not ref:
        return {"erro": "informe a visita (id ou nome do cliente)"}
    itens = [a.strip() for a in (achados.split(";") if isinstance(achados, str) else achados or [])
             if str(a).strip()]
    if not itens:
        return {"erro": "informe ao menos um achado (separe por ';')"}

    # Nome PARCIAL é o caso normal de quem digita: o cliente é
    # "VEGA MANAUS TRANSPORTE DE PASSAGEIROS LTDA" e a pessoa escreve "VEGA".
    # Exato primeiro (quem sabe o nome inteiro não deve ser punido por homônimo), e só então
    # o parcial. ⚠️ Parcial que casa MAIS DE UM não escolhe: devolve as opções e pergunta —
    # anexar achado no relatório errado é sujar a visita de outro cliente.
    achadas = (await db.execute(text(
        "SELECT id::text AS id, cliente_nome, status::text AS status, "
        "       (upper(cliente_nome) = upper(:r) OR id::text = :r) AS exato "
        "FROM crm_visit_reports "
        "WHERE id::text = :r OR upper(cliente_nome) = upper(:r) "
        "   OR cliente_nome ILIKE '%' || :r || '%' "
        "ORDER BY exato DESC, created_at DESC LIMIT 6"), {"r": ref})).mappings().all()
    if not achadas:
        return {"erro": f"relatório de visita '{ref}' não encontrado por id ou nome do cliente "
                        f"(tentei nome exato e parcial)."}
    exatas = [a for a in achadas if a["exato"]]
    if exatas:
        row = exatas[0]
    elif len(achadas) > 1:
        opcoes = " · ".join(f"{a['cliente_nome']} ({a['status']})" for a in achadas[:5])
        return {"erro": f"'{ref}' casa com {len(achadas)} relatórios de visita — diga qual: "
                        f"{opcoes}"}
    else:
        row = achadas[0]

    return await criar_rascunho(
        db, user, tipo="adicionar_achados_visita", modulo="crm", gate="🟡",
        requires_otp=False, roles_aprovador=ROLES_COMERCIAL,
        idempotency_key=f"visita_achados:{row['id']}:{_slug(';'.join(itens))[:36]}",
        titulo=f"Anexar {len(itens)} achado(s) à visita de {row['cliente_nome']}",
        resumo=f"Aprovar ANEXA ao relatório de visita de {row['cliente_nome']} "
               f"(status {row['status']}): " + " · ".join(i[:70] for i in itens[:5])
               + (f" (+{len(itens)-5})" if len(itens) > 5 else "") + ".",
        payload={"ref": row["id"], "achados": itens, "cliente": row["cliente_nome"]},
    )


async def _exec_adicionar_achados_visita(db, aprovador_user, payload: dict) -> str:
    from modules.crm.services.visit_reports import adicionar_achados  # noqa: PLC0415

    await adicionar_achados(db, str(payload["ref"]), list(payload["achados"]))
    return str(payload["ref"])


registrar_executor("adicionar_achados_visita", _exec_adicionar_achados_visita)
registrar_acao("crm", "adicionar_achados_visita",
               "ANEXAR achados (notas de vistoria) a um relatório de visita existente. dados: "
               "visita (id ou nome do cliente — obrig.), achados (texto; separe vários por "
               "';'). Vira rascunho — só entra no relatório depois da aprovação.",
               _propor_adicionar_achados_visita)


# ── DEFINIR META DE CONTRATOS DO MÊS (11ª das 14) ────────────────────────────────────
# Rota POST /crm/quotas · `crm/…/growth_controller.py:1093` (UPSERT por seller+ano+mês).
# ⚠️ Meta não é dinheiro que sai, mas é a RÉGUA contra a qual o desempenho é medido — mexer
# nela muda o retrato de quem bateu e quem não bateu. Por isso 🟡 e com o valor ANTERIOR no
# resumo: aprovar meta sem ver a de antes é aprovar às cegas.
async def _propor_definir_meta_contratos_mes(db, user, scope, *, mes=None, ano=None,
                                             vendedor="", quantidade=None, valor=None,
                                             **_) -> dict[str, Any]:
    if quantidade is None and valor is None:
        return {"erro": "informe quantidade (nº de contratos) e/ou valor (R$) da meta"}
    hoje = (await db.execute(text(
        "SELECT (now() AT TIME ZONE 'America/Manaus')::date"))).scalar()
    m, a = int(mes or hoje.month), int(ano or hoje.year)
    if not (1 <= m <= 12):
        return {"erro": "mês inválido"}

    sid, snome = None, None
    if str(vendedor or "").strip():
        v = (await db.execute(text(
            "SELECT id::text AS id, name FROM users WHERE upper(name) = upper(:v) "
            "OR email = :v LIMIT 1"), {"v": vendedor.strip()})).mappings().first()
        if not v:
            return {"erro": f"vendedor '{vendedor}' não encontrado — para meta da EMPRESA, "
                            f"omita o vendedor."}
        sid, snome = v["id"], v["name"]

    atual = (await db.execute(text(
        "SELECT target_value, target_count FROM crm_quotas WHERE period_year = :a "
        "AND period_month = :m AND coalesce(seller_id::text, '') = coalesce(:s, '')"),
        {"a": a, "m": m, "s": sid})).mappings().first()
    de = (f"hoje: {atual['target_count'] or '—'} contrato(s) / "
          f"R$ {float(atual['target_value'] or 0):,.2f}" if atual else "hoje: sem meta definida")

    return await criar_rascunho(
        db, user, tipo="definir_meta_contratos_mes", modulo="crm", gate="🟡",
        requires_otp=False, roles_aprovador=ROLES_COMERCIAL,
        idempotency_key=f"meta:{a}-{m:02d}:{sid or 'empresa'}:{quantidade}:{valor}",
        titulo=f"Meta {m:02d}/{a}" + (f" — {snome}" if snome else " — EMPRESA"),
        resumo=f"Aprovar DEFINE a meta de {m:02d}/{a} "
               + (f"para {snome}" if snome else "da EMPRESA") + ": "
               + (f"{quantidade} contrato(s)" if quantidade is not None else "")
               + (" e " if quantidade is not None and valor is not None else "")
               + (f"R$ {float(valor):,.2f}" if valor is not None else "")
               + f". ({de}). Meta é a régua do desempenho — mexer nela muda quem bateu.",
        payload={"seller_id": sid, "seller_name": snome, "period_year": a,
                 "period_month": m, "target_count": quantidade, "target_value": valor},
    )


async def _exec_definir_meta_contratos_mes(db, aprovador_user, payload: dict) -> str:
    from modules.crm.controllers.growth_controller import QuotaIn, upsert_quota  # noqa: PLC0415

    await upsert_quota(data=QuotaIn(
        seller_id=payload.get("seller_id"), seller_name=payload.get("seller_name"),
        period_year=payload["period_year"], period_month=payload["period_month"],
        target_value=payload.get("target_value"),
        target_count=payload.get("target_count")), db=db)
    return f"{payload['period_year']}-{payload['period_month']:02d}"


registrar_executor("definir_meta_contratos_mes", _exec_definir_meta_contratos_mes)
registrar_acao("crm", "definir_meta_contratos_mes",
               "DEFINIR a meta comercial do mês (quantidade de contratos e/ou valor). dados: "
               "mes, ano (padrão: o corrente), vendedor (omita para meta da EMPRESA), "
               "quantidade, valor. Vira rascunho e mostra a meta anterior — meta é a régua do "
               "desempenho, então mexer nela muda o retrato de quem bateu.",
               _propor_definir_meta_contratos_mes)


# ── CRIAR PROPOSTAS EM LOTE (13ª das 14) — a Central entende lote ─────────────────────
# ⭐ O DESENHO É O PONTO. Um rascunho único NÃO representa um lote: a importação em lote
# produz resultado PARCIAL por natureza (9 criadas, 3 com erro) e ninguém consegue "aprovar
# metade". Então cada proposta vira UMA DECISÃO própria, e o lote é só o agrupamento:
#
#     N rascunhos · mesmo `lote_id` · cada um aprova, falha e aparece sozinho
#     a Central agrupa, mostra "i/N" e oferece UM clique que aprova o lote inteiro
#
# Assim o parcial é REPRESENTÁVEL: 9 viram 'executado' e 3 viram 'falha', cada uma com o seu
# motivo. Com um rascunho só, o aprovador leria "criar 12 propostas" e receberia um resultado
# que a Central não teria como contar — a tela mentiria sobre o que foi aprovado.
import uuid as _uuid


async def _propor_criar_propostas_lote(db, user, scope, *, propostas=None, **_) -> dict[str, Any]:
    itens = propostas if isinstance(propostas, list) else []
    if not itens:
        return {"erro": "informe `propostas`: uma lista de {titulo, cliente, valor?}"}
    if len(itens) > 50:
        return {"erro": f"lote de {len(itens)} é grande demais; divida em partes de até 50"}

    normal: list[dict] = []
    for i, p in enumerate(itens, 1):
        if not isinstance(p, dict):
            return {"erro": f"item {i} não é um objeto {{titulo, cliente}}"}
        tit = str(p.get("titulo") or p.get("title") or "").strip()
        cli = str(p.get("cliente") or p.get("client_name") or "").strip()
        if not tit or not cli:
            # Fail-closed no ITEM: um item ruim não vira lote pela metade em silêncio.
            return {"erro": f"item {i} sem titulo e/ou cliente — corrija antes de propor o lote"}
        normal.append({"title": tit, "client_name": cli,
                       **({"total_value": float(p["valor"])} if p.get("valor") else {})})

    lote = str(_uuid.uuid4())
    criados, erros = [], []
    for pos, campos in enumerate(normal, 1):
        r = await criar_rascunho(
            db, user, tipo="criar_proposta_do_lote", modulo="crm", gate="🟡",
            requires_otp=False, roles_aprovador=ROLES_COMERCIAL,
            idempotency_key=f"lote:{lote}:{pos}",
            titulo=f"[lote {pos}/{len(normal)}] Proposta: {campos['title'][:50]}",
            resumo=f"Aprovar CRIA a proposta '{campos['title']}' para {campos['client_name']}"
                   + (f" (R$ {campos['total_value']:,.2f})" if "total_value" in campos else "")
                   + f". Item {pos} de {len(normal)} do mesmo lote — cada um aprova e falha "
                   + "sozinho, e a Central oferece aprovar o lote de uma vez.",
            payload={"campos": campos, "lote_id": lote, "lote_pos": pos,
                     "lote_total": len(normal)},
        )
        (criados if (r.get("draft_id") or r.get("duplicado")) else erros).append(
            {"pos": pos, "titulo": campos["title"], "r": str(r)[:80]})

    return {"status": "rascunho", "lote_id": lote, "rascunhos": len(criados),
            "falhas": len(erros), "erros": erros or None,
            "mensagem": f"{len(criados)} rascunho(s) na Central, agrupados no lote "
                        f"{lote[:8]}…. Aprove um a um ou o lote inteiro — o resultado "
                        f"parcial fica visível item a item."}


async def _exec_criar_proposta_do_lote(db, aprovador_user, payload: dict) -> str:
    from modules.crm.controllers.proposal_controller import create_proposal  # noqa: PLC0415
    from modules.crm.schemas.proposal import ProposalCreate  # noqa: PLC0415

    p = await create_proposal(data=ProposalCreate(**payload["campos"]),
                              current_user=aprovador_user, db=db)
    return str(getattr(p, "id", ""))


registrar_executor("criar_proposta_do_lote", _exec_criar_proposta_do_lote)
registrar_acao("crm", "criar_propostas_lote",
               "CRIAR VÁRIAS propostas de uma vez (importação em lote). dados: propostas = "
               "lista de {titulo, cliente, valor?}, até 50. Cada proposta vira UM rascunho "
               "próprio, agrupado por lote na Central: você aprova uma a uma ou o lote "
               "inteiro, e o que falhar aparece item a item com o motivo.",
               _propor_criar_propostas_lote)


# ── SALVAR O ORÇAMENTO COMO PROPOSTA NO CRM ────────────────────────────────────────────
# `gerar_orcamento_itens_doc` produz o PDF e não grava nada. Esta ação GRAVA: o orçamento
# vira `proposals` + `proposal_items` no CRM, com número, validade e histórico.
#
# ⭐ O PREÇO É CONGELADO NA PROPOSTA, não na aprovação. Entre propor e aprovar o catálogo
# pode mudar (o Bling reimportado, um preço corrigido na tela), e uma proposta que muda de
# valor sozinha entre o "quero isso" e o "aprovado" é armadilha. O payload leva a linha
# inteira já resolvida; o executor só grava — e o resumo mostra o total que será gravado,
# para quem aprova ver o número antes de clicar.
#
# ⭐ `code` DO ITEM PASSA A SER PREENCHIDO. Os 162 itens que existiam tinham code NULL em
# 162 — nenhum vinha de catálogo. Daqui em diante o SKU viaja com a linha, e é ele que vai
# permitir cruzar proposta × catálogo × NCM sem adivinhar por descrição.

async def _propor_criar_orcamento(db, user, scope, *, cliente=None, titulo=None,
                                  itens=None, validade_dias=15, observacoes=None,
                                  **_) -> dict[str, Any]:
    from modules.crm.services import catalogo as _cat

    if not str(cliente or "").strip():
        return {"erro": "informe o cliente (nome ou CNPJ do cadastro)."}
    if not str(titulo or "").strip():
        return {"erro": "informe o título/objeto do orçamento (ex.: 'CFTV — bloco A')."}

    cli = (await db.execute(text(
        "SELECT id::text AS id, name, document_number, email, phone "
        "FROM clients WHERE upper(name) = upper(:r) OR id::text = :r "
        "   OR regexp_replace(coalesce(document_number,''), '[^0-9]', '', 'g') = "
        "      regexp_replace(:r, '[^0-9]', '', 'g') "
        "ORDER BY (upper(name) = upper(:r)) DESC LIMIT 1"),
        {"r": str(cliente).strip()})).mappings().first()
    if not cli:
        return {"erro": f"cliente {cliente!r} não existe no cadastro — não crio cliente "
                        f"de passagem. Cadastre antes, ou confira o nome."}

    linhas, lastro, recusa = await _cat.resolver_itens(db, itens)
    if recusa:
        return {"erro": recusa}

    total = sum(x["qtd"] * x["valor_unit"] for x in linhas)
    try:
        dias = max(1, min(int(validade_dias), 180))
    except (TypeError, ValueError):
        return {"erro": f"validade_dias inválida: {validade_dias!r}"}

    def _rs(v: float) -> str:
        return f"R$ {v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")

    resumo_itens = "; ".join(
        f"{x['qtd']:g}× {x['descricao'][:38]} @ {_rs(x['valor_unit'])}"
        for x in linhas[:5]) + (f" (+{len(linhas) - 5})" if len(linhas) > 5 else "")

    return await criar_rascunho(
        db, user, tipo="criar_orcamento", modulo="crm",
        gate="🟡", requires_otp=False, roles_aprovador=ROLES_COMERCIAL,
        idempotency_key=f"orcamento:{_slug(cli['name'])}:{_slug(titulo)}:{total:.2f}",
        titulo=f"GRAVAR orçamento no CRM — {cli['name'][:40]}",
        resumo=(f"Aprovar CRIA a proposta '{titulo}' para {cli['name']} com "
                f"{len(linhas)} item(ns), total {_rs(total)}, válida por {dias} dias. "
                f"Itens: {resumo_itens}. "
                f"Preço congelado agora — aprovar grava ESTE valor. "
                f"Lastro: {'; '.join(lastro) if lastro else 'valores informados na conversa'}. "
                f"NÃO envia ao cliente: enviar é outra aprovação."),
        payload={"client_name": cli["name"], "client_document": cli["document_number"],
                 "client_email": cli["email"], "client_phone": cli["phone"],
                 "title": str(titulo)[:255], "description": (observacoes or None),
                 "valid_dias": dias, "total": total,
                 "itens": linhas},
    )


async def _exec_criar_orcamento(db, aprovador_user, payload: dict) -> str:
    from datetime import timedelta

    from modules.crm.controllers.proposal_controller import create_proposal
    from modules.crm.schemas.proposal import ProposalCreate, ProposalItemCreate

    itens = [
        ProposalItemCreate(
            code=(x.get("codigo") or None), name=str(x["descricao"])[:255],
            unit=str(x.get("unidade") or "un")[:20], quantity=float(x["qtd"]),
            unit_price=float(x["valor_unit"]), sort_order=i)
        for i, x in enumerate(payload.get("itens") or [])
    ]
    # `proposal_type` sai da NATUREZA das linhas, não do default do schema. O tipo
    # aparece no documento e no funil; deixar tudo como SERVICE descreveria errado uma
    # proposta de material — e é justamente material que o Jordan passou a orçar.
    from modules.crm.models.proposal import ProposalType

    tipos = {x.get("tipo") or "material" for x in (payload.get("itens") or [])}
    ptipo = (ProposalType.MIXED if len(tipos) > 1
             else ProposalType.SERVICE if tipos == {"servico"}
             else ProposalType.PRODUCT)

    data = ProposalCreate(
        title=str(payload["title"])[:255],
        description=(payload.get("description") or None),
        proposal_type=ptipo,
        client_name=str(payload["client_name"])[:255],
        client_document=(payload.get("client_document") or None),
        client_email=(payload.get("client_email") or None),
        client_phone=(payload.get("client_phone") or None),
        valid_until=(date.today() + timedelta(days=int(payload.get("valid_dias") or 15))),
        items=itens,
    )
    p = await create_proposal(data=data, current_user=aprovador_user, db=db)
    return str(getattr(p, "id", "") or "")


registrar_executor("criar_orcamento", _exec_criar_orcamento)

registrar_acao("crm", "criar_orcamento",
               "GRAVAR um orçamento como proposta no CRM (número, validade, itens). "
               "dados: cliente (nome ou CNPJ do cadastro), titulo, itens (lista com sku "
               "do catálogo OU descricao+valor_unit, qtd, unidade, tipo), validade_dias "
               "(padrão 15), observacoes. O preço é congelado agora. Nasce RASCUNHO: só a "
               "aprovação grava, e ENVIAR ao cliente é outra aprovação.",
               _propor_criar_orcamento)


# ── MOVER DEAL DE ESTÁGIO ──────────────────────────────────────────────────────────────
# 27/08/2026: 46 deals empilhados em `proposal` há 24 dias, R$ 596.881. O Bartolo lia o
# funil e não o movia — só sabia `marcar_deal_perdido`, um assessor que só registra derrota.
#
# ⭐ `closed_won` NÃO passa por aqui. Fechar venda vira MRR e contrato; é decisão do dono,
# com a porta própria (`POST /opportunities/{id}/close`). Uma frase no chat não fecha venda.

_ESTAGIOS_PERMITIDOS = frozenset({
    "prospecting", "qualification", "proposal", "negotiation",
})
#: Fora desta lista, recusa. `closed_won`/`closed_lost` são nomeados para a mensagem de
#: recusa poder EXPLICAR, em vez de dizer só "inválido".
_ESTAGIOS_FECHAMENTO = frozenset({"closed_won", "closed_lost"})


async def _propor_mover_estagio_deal(db, user, scope, *, deal=None, estagio=None,
                                     motivo=None, **_) -> dict[str, Any]:
    ref = str(deal or "").strip()
    novo = str(estagio or "").strip().lower()
    if not ref:
        return {"erro": "informe o deal (título ou id)"}
    if novo in _ESTAGIOS_FECHAMENTO:
        return {"erro": f"'{novo}' é FECHAMENTO e não passa por aqui: ganhar vira MRR e "
                        f"contrato, e perder tem `marcar_deal_perdido` com motivo. "
                        f"Mova só dentro do funil aberto."}
    if novo not in _ESTAGIOS_PERMITIDOS:
        return {"erro": f"estágio {novo!r} não existe. Use um de: "
                        f"{', '.join(sorted(_ESTAGIOS_PERMITIDOS))}."}

    row = (await db.execute(text(
        "SELECT id::text AS id, title, stage::text AS stage, "
        "       coalesce(value, 0) AS value "
        "FROM opportunities "
        "WHERE id::text = :r OR upper(title) = upper(:r) "
        "ORDER BY (upper(title) = upper(:r)) DESC LIMIT 1"),
        {"r": ref})).mappings().first()
    if not row:
        return {"erro": f"deal {ref!r} não existe no funil — não crio deal de passagem."}
    if row["stage"] == novo:
        return {"erro": f"o deal '{row['title'][:40]}' JÁ está em {novo}."}

    valor = float(row["value"] or 0)
    return await criar_rascunho(
        db, user, tipo="mover_estagio_deal", modulo="crm",
        gate="🟡", requires_otp=False, roles_aprovador=ROLES_COMERCIAL,
        idempotency_key=f"deal_estagio:{_slug(row['title'])}:{novo}",
        titulo=f"MOVER deal para {novo} — {row['title'][:38]}",
        resumo=(f"Aprovar move o deal '{row['title'][:50]}' "
                f"(R$ {valor:,.2f}) de {row['stage']} para {novo}. "
                f"{('Motivo: ' + str(motivo)[:120] + '. ') if motivo else ''}"
                f"Isso muda o funil e a previsão de receita."),
        payload={"opportunity_id": row["id"], "title": row["title"],
                 "de": row["stage"], "para": novo, "motivo": (motivo or None)},
    )


async def _exec_mover_estagio_deal(db, aprovador_user, payload: dict) -> str:
    from modules.crm.controllers.opportunity_controller import update_opportunity_stage
    from modules.crm.schemas.opportunity import OpportunityStageUpdate

    o = await update_opportunity_stage(
        opportunity_id=str(payload["opportunity_id"]),
        data=OpportunityStageUpdate(stage=payload["para"],
                                    notes=(payload.get("motivo") or None)),
        current_user=aprovador_user, db=db)
    return str(getattr(o, "id", payload["opportunity_id"]))


registrar_executor("mover_estagio_deal", _exec_mover_estagio_deal)

registrar_acao("crm", "mover_estagio_deal",
               "MOVER um deal de estágio no funil. dados: deal (título ou id), estagio "
               "(prospecting | qualification | proposal | negotiation), motivo. "
               "FECHAR (ganho/perdido) NÃO passa por aqui. Nasce rascunho.",
               _propor_mover_estagio_deal)


# ── ENVIAR PROPOSTA PELO WHATSAPP · CADASTRAR O NÚMERO DO CLIENTE ─────────────────────
# 27/08/2026: 10 propostas sem resposta há 64 dias em média, TODAS por e-mail. O WhatsApp
# é onde o cliente responde — e a rota já existia, mandando PDF + link de assinatura e
# rastreando em `crm_followups`.
#
# ⚠️ ENVIO É IRREVERSÍVEL E EXTERNO. Depois que sai, não há desfazer. Por isso o resumo
# NOMEIA o destinatário: quem aprova precisa ver para quem vai ANTES de clicar. É a mesma
# regra do `enviar_proposta` por e-mail, que já usa ROLES_MONEY pelo mesmo motivo — o
# risco aqui não é dinheiro, é a empresa falando com o cliente errado.

async def _propor_enviar_proposta_whatsapp(db, user, scope, *, proposta=None,
                                           **_) -> dict[str, Any]:
    ref = str(proposta or "").strip()
    if not ref:
        return {"erro": "informe a proposta (número ou id)"}

    row = (await db.execute(text(
        "SELECT p.id::text AS id, p.number, p.status::text AS status, "
        "       coalesce(p.total, 0) AS total, "
        "       coalesce(p.client_name, '') AS cliente, "
        "       coalesce(c.whatsapp, c.phone, '') AS numero "
        "FROM proposals p "
        "LEFT JOIN clients c ON upper(c.name) = upper(p.client_name) "
        "WHERE p.id::text = :r OR upper(p.number) = upper(:r) LIMIT 1"),
        {"r": ref})).mappings().first()
    if not row:
        return {"erro": f"proposta {ref!r} não existe."}
    if not str(row["numero"] or "").strip():
        return {"erro": f"o cliente '{row['cliente'][:40]}' não tem WhatsApp cadastrado. "
                        f"Cadastre com `cadastrar_whatsapp` — eu não invento número."}

    return await criar_rascunho(
        db, user, tipo="enviar_proposta_whatsapp", modulo="crm",
        gate="🟡", requires_otp=False, roles_aprovador=ROLES_MONEY,
        idempotency_key=f"prop_wa:{_slug(row['number'] or row['id'])}",
        titulo=f"ENVIAR proposta {row['number']} por WhatsApp",
        resumo=(f"⚠️ EXTERNO: aprovar ENVIA a proposta {row['number']} "
                f"(R$ {float(row['total'] or 0):,.2f}) para {row['cliente'][:40]} "
                f"no WhatsApp {row['numero']} — PDF + link de assinatura. "
                f"CONFIRA o destinatário: envio não tem desfazer."),
        payload={"proposal_id": row["id"], "number": row["number"],
                 "cliente": row["cliente"], "numero": row["numero"]},
    )


async def _exec_enviar_proposta_whatsapp(db, aprovador_user, payload: dict) -> str:
    from modules.crm.controllers.proposal_controller import send_proposal_whatsapp

    # confirmar=True: o preview já foi o RASCUNHO que o humano leu e aprovou.
    await send_proposal_whatsapp(
        proposal_id=str(payload["proposal_id"]), current_user=aprovador_user,
        confirmar=True, db=db)
    return str(payload["proposal_id"])


async def _propor_cadastrar_whatsapp(db, user, scope, *, cliente=None, numero=None,
                                     **_) -> dict[str, Any]:
    from modules.crm.services.phone import to_e164_br

    ref = str(cliente or "").strip()
    num = str(numero or "").strip()
    if not ref or not num:
        return {"erro": "informe o cliente (CNPJ, id ou nome) e o número com DDD"}
    e164 = to_e164_br(num)
    if not e164:
        return {"erro": f"número inválido: {num!r}. Use DDD+número (ex.: 92 99123-4567)."}

    row = (await db.execute(text(
        "SELECT id::text AS id, name FROM clients "
        "WHERE id::text = :r OR upper(name) = upper(:r) "
        "   OR regexp_replace(coalesce(document_number, ''), '[^0-9]', '', 'g') = "
        "      regexp_replace(:r, '[^0-9]', '', 'g') LIMIT 1"),
        {"r": ref})).mappings().first()
    if not row:
        return {"erro": f"cliente {ref!r} não existe no cadastro."}

    return await criar_rascunho(
        db, user, tipo="cadastrar_whatsapp", modulo="crm",
        gate="🟡", requires_otp=False, roles_aprovador=ROLES_COMERCIAL,
        idempotency_key=f"wa_cad:{_slug(row['name'])}:{e164}",
        titulo=f"CADASTRAR WhatsApp de {row['name'][:38]}",
        resumo=(f"Aprovar grava {e164} como WhatsApp de {row['name'][:50]}. "
                f"É por este número que a empresa vai falar com ele — confira antes."),
        payload={"cnpj_ou_id": row["id"], "numero": num, "e164": e164,
                 "cliente": row["name"]},
    )


async def _exec_cadastrar_whatsapp(db, aprovador_user, payload: dict) -> str:
    from modules.crm.controllers.growth_controller import (
        WhatsAppCadastroIn, cadastrar_whatsapp,
    )

    await cadastrar_whatsapp(
        data=WhatsAppCadastroIn(cnpj_ou_id=str(payload["cnpj_ou_id"]),
                                numero=str(payload["numero"])),
        db=db)
    return str(payload["cnpj_ou_id"])


registrar_executor("enviar_proposta_whatsapp", _exec_enviar_proposta_whatsapp)
registrar_executor("cadastrar_whatsapp", _exec_cadastrar_whatsapp)

registrar_acao("crm", "enviar_proposta_whatsapp",
               "ENVIAR uma proposta ao cliente pelo WhatsApp (PDF + link de assinatura). "
               "dados: proposta (número ou id). EXTERNO e irreversível — nasce rascunho e "
               "só a aprovação envia.",
               _propor_enviar_proposta_whatsapp)

registrar_acao("crm", "cadastrar_whatsapp",
               "CADASTRAR o WhatsApp de um cliente. dados: cliente (CNPJ, id ou nome), "
               "numero (com DDD). Nasce rascunho.",
               _propor_cadastrar_whatsapp)


# ── FOLLOW-UP EM LOTE E OPT-OUT ───────────────────────────────────────────────────────
# ⚠️ MAIOR ALCANCE DESTE PLANO: um toque em lote fala com TODOS os clientes que têm
# proposta pendente ao mesmo tempo. Erro aqui não atinge um cliente — atinge a carteira.
# Por isso o rascunho carrega o PREVIEW REAL (a rota já sabe fazer, com confirmar=False)
# e o resumo diz QUANTOS serão tocados. Quem aprova precisa saber o alcance, não só o texto.

async def _propor_followup_em_lote(db, user, scope, *, mensagem=None,
                                   **_) -> dict[str, Any]:
    from modules.crm.services import orchestration as _O

    texto = str(mensagem or "").strip()
    if not texto:
        return {"erro": "informe a mensagem do toque — não disparo texto vazio para a "
                        "carteira inteira."}
    if len(texto) < 10:
        return {"erro": f"mensagem curta demais ({len(texto)} caracteres) para ir a "
                        f"dezenas de clientes. Escreva o toque completo."}

    # PREVIEW REAL: `confirmar=False` devolve quem seria tocado SEM tocar ninguém.
    previa = await _O.followup_em_lote(db, mensagem=texto, confirmar=False)
    # A chave é `qtd` — conferido com a sonda do Step 5. `total` não existe neste
    # retorno, e presumir chave de dicionário é a mesma classe de erro que inventar coluna.
    alvos = previa.get("qtd") or len(previa.get("clientes") or [])

    return await criar_rascunho(
        db, user, tipo="followup_em_lote", modulo="crm",
        gate="🟡", requires_otp=False, roles_aprovador=ROLES_MONEY,
        idempotency_key=f"lote:{_slug(texto[:40])}",
        titulo=f"TOQUE EM LOTE — {alvos} cliente(s)",
        resumo=(f"⚠️ EXTERNO E EM LOTE: aprovar envia esta mensagem para {alvos} "
                f"cliente(s) com proposta pendente, DE UMA VEZ. Texto: "
                f"\"{texto[:160]}\". Não há desfazer para nenhum deles."),
        payload={"mensagem": texto, "alvos": alvos},
    )


async def _exec_followup_em_lote(db, aprovador_user, payload: dict) -> str:
    from modules.crm.services import orchestration as _O

    res = await _O.followup_em_lote(db, mensagem=str(payload["mensagem"]),
                                    confirmar=True)
    return str(res.get("enviados") or res.get("total") or 0)


async def _propor_optout_whatsapp(db, user, scope, *, numero=None, motivo=None,
                                  **_) -> dict[str, Any]:
    from modules.crm.services.phone import canonical_br

    num = str(numero or "").strip()
    if not num:
        return {"erro": "informe o número que não deve mais receber follow-up"}
    c = canonical_br(num)
    if not c:
        return {"erro": f"número inválido: {num!r}"}

    return await criar_rascunho(
        db, user, tipo="optout_whatsapp", modulo="crm",
        gate="🟡", requires_otp=False, roles_aprovador=ROLES_COMERCIAL,
        idempotency_key=f"optout:{c}",
        titulo=f"OPT-OUT de follow-up — {c}",
        resumo=(f"Aprovar marca {c} como opt-out: ele NÃO recebe mais follow-up "
                f"automático. {('Motivo: ' + str(motivo)[:100] + '. ') if motivo else ''}"
                f"É proteção do cliente — na dúvida, aprove."),
        payload={"numero": num, "canonical": c, "motivo": (motivo or None)},
    )


async def _exec_optout_whatsapp(db, aprovador_user, payload: dict) -> str:
    from modules.crm.controllers.growth_controller import OptoutIn, followup_optout

    await followup_optout(
        data=OptoutIn(numero=str(payload["numero"]),
                      motivo=(payload.get("motivo") or None)),
        db=db)
    return str(payload["canonical"])


registrar_executor("followup_em_lote", _exec_followup_em_lote)
registrar_executor("optout_whatsapp", _exec_optout_whatsapp)

registrar_acao("crm", "followup_em_lote",
               "TOQUE EM LOTE em todos os clientes com proposta pendente. dados: mensagem "
               "(obrigatória, mínimo 10 caracteres). O rascunho mostra QUANTOS serão "
               "tocados. EXTERNO e irreversível — só a aprovação dispara.",
               _propor_followup_em_lote)

registrar_acao("crm", "optout_whatsapp",
               "Marcar um número como OPT-OUT (não recebe mais follow-up). dados: numero, "
               "motivo.",
               _propor_optout_whatsapp)
