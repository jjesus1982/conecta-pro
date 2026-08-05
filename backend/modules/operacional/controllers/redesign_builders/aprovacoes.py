"""Central de Aprovações — tela ÚNICA onde o humano revisa e aprova os rascunhos que o
agente criou (agent_drafts). Auto-registrada pelo _discover_module_builders (SLUG/build/
EXTRA_MENU/router). Aprovar 🔵/🟡 EXECUTA o serviço de domínio real (via executor registrado);
🔴/requires_otp NÃO executa aqui — autoriza e manda pra tela de OTP existente (parede de
dinheiro/eSocial intocada). RBAC: só quem tem role ∈ roles_aprovador do rascunho (admin vê tudo).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.ai.conversation.models.agent_draft import AgentDraft

SLUG = "aprovacoes"

_GATE_BADGE = {"🔵": ("Baixo", "#2563EB", "#EAF0FF"),
               "🟡": ("Médio", "#B45309", "#FFFBEB"),
               "🔴": ("Alto", "#B91C1C", "#FEF2F2")}


def _is_admin(user) -> bool:
    role = (getattr(user, "role", "") or "").lower()
    perfil = (getattr(user, "perfil", "") or "").lower()
    return role == "admin" or perfil == "all"


async def build(db: AsyncSession, current_user=None) -> dict:
    """Lista os rascunhos que ESTE usuário pode aprovar. Vazio real → tabela vazia honesta."""
    role = (getattr(current_user, "role", "") or "").lower()
    if _is_admin(current_user):
        where, params = "status='rascunho'", {}
    else:
        where, params = "status='rascunho' AND :role = ANY(roles_aprovador)", {"role": role}
    rows = (await db.execute(text(
        "SELECT id, tipo, titulo, resumo, gate, requires_otp, solicitado_por_nome, created_at "
        f"FROM agent_drafts WHERE {where} ORDER BY created_at DESC LIMIT 200"), params)).fetchall()

    def _row(r):
        badge, color, bg = _GATE_BADGE.get(r[4], ("—", "#64748B", "#F1F4FA"))
        cells = [
            {"isText": True, "v": (r[1] or "").replace("_", " ").title(), "w": 600, "tc": "#0F1B3A", "ini": ""},
            {"isText": True, "v": (r[2] or "")[:80], "w": 500, "tc": "#334155", "ini": ""},
            {"isBadge": True, "v": badge, "color": color, "bg": bg},
            {"isText": True, "v": r[6] or "Agente", "w": 500, "tc": "#334155", "ini": ""},
            {"isText": True, "v": r[7].strftime("%d/%m %H:%M") if r[7] else "—", "w": 500, "tc": "#64748B", "ini": ""},
        ]
        did = str(r[0])
        requires_otp = bool(r[5])
        aprovar = {
            "title": f"Aprovar: {r[2] or r[1]}",
            "endpoint": f"/api/v1/redesign/action/aprovar-rascunho?draft_id={did}",
            "method": "POST", "btnLabel": "Aprovar", "submitLabel": "Aprovar",
            "btnStyle": "primary",
            "okMsg": ("Autorizado — conclua o envio com OTP na tela indicada."
                      if requires_otp else "Aprovado e executado. Recarregue a tela."),
            "fields": ([{"key": "otp", "label": "Código OTP (enviado ao seu e-mail)", "type": "text"}]
                       if requires_otp else []),
        }
        rejeitar = {
            "title": f"Rejeitar: {r[2] or r[1]}",
            "endpoint": f"/api/v1/redesign/action/rejeitar-rascunho?draft_id={did}",
            "method": "POST", "btnLabel": "Rejeitar", "submitLabel": "Rejeitar",
            "btnStyle": "danger", "okMsg": "Rascunho rejeitado.",
            "fields": [{"key": "motivo", "label": "Motivo (opcional)", "type": "text"}],
        }
        return {"cells": cells, "actions": [aprovar, rejeitar]}

    scr = {
        "title": "Central de Aprovações",
        "sub": (f"{len(rows)} rascunho(s) do agente aguardando sua aprovação"
                if rows else "Nenhum rascunho aguardando aprovação"),
        "cta": "Atualizar", "type": "table", "searchHint": "Buscar rascunho…",
        "grid": "1.2fr 2.2fr 0.7fr 1.2fr 0.9fr",
        "cols": ["Tipo", "Descrição", "Risco", "Solicitado por", "Criado"],
        "rows": [_row(r) for r in rows],
    }
    return {"pendentes": scr}


EXTRA_MENU = {SLUG: [{"id": "pendentes", "label": "Aprovações", "icon": "M9 12l2 2 4-4M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18"}]}

# --------------------------------------------------------------------------- #
# Ações: aprovar / rejeitar rascunho (montadas em /api/v1/redesign/action/*)
# --------------------------------------------------------------------------- #
router = APIRouter()


def _pode_aprovar(user, draft: AgentDraft) -> bool:
    if _is_admin(user):
        return True
    role = (getattr(user, "role", "") or "").lower()
    return role in [str(x).lower() for x in (draft.roles_aprovador or [])]


async def _get_rascunho(db, draft_id: str) -> AgentDraft:
    draft = (await db.execute(select(AgentDraft).where(AgentDraft.id == draft_id))).scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Rascunho não encontrado.")
    return draft


@router.post("/action/aprovar-rascunho")
async def aprovar_rascunho(
    current_user: CurrentActiveUser,
    draft_id: str,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import executar_rascunho

    draft = await _get_rascunho(db, draft_id)
    if draft.status != "rascunho":
        raise HTTPException(status_code=409, detail=f"Rascunho já está '{draft.status}'.")
    if not _pode_aprovar(current_user, draft):
        raise HTTPException(status_code=403, detail="Você não tem permissão para aprovar este rascunho.")

    # Dinheiro/eSocial: NÃO executa aqui. Autoriza e leva à tela de OTP existente (parede intocada).
    if draft.requires_otp:
        draft.status = "aprovado"
        draft.decidido_por = current_user.id
        draft.decidido_em = datetime.now(timezone.utc)
        await db.commit()
        return {"ok": True, "needsOtp": True,
                "message": "Autorizado. Conclua o envio com OTP na tela de pagamento/eSocial.",
                "action_url": (draft.payload or {}).get("action_url_execucao")}

    # 🔵/🟡 (não-dinheiro): executa o serviço de domínio REAL.
    try:
        entity_ref = await executar_rascunho(db, current_user, draft)
        draft.decidido_por = current_user.id
        draft.decidido_em = datetime.now(timezone.utc)
        await db.commit()
    except Exception as e:  # noqa: BLE001 — falha de execução vira status 'falha' durável, não 500 mudo
        await db.rollback()
        d2 = await _get_rascunho(db, draft_id)
        d2.status = "falha"
        d2.erro_execucao = str(e)[:500]
        d2.decidido_por = current_user.id
        d2.decidido_em = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Aprovado, mas a execução falhou: {e}")
    return {"ok": True, "id": entity_ref, "message": "Aprovado e executado com sucesso."}


@router.post("/action/rejeitar-rascunho")
async def rejeitar_rascunho(
    current_user: CurrentActiveUser,
    draft_id: str,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    draft = await _get_rascunho(db, draft_id)
    if draft.status != "rascunho":
        raise HTTPException(status_code=409, detail=f"Rascunho já está '{draft.status}'.")
    if not _pode_aprovar(current_user, draft):
        raise HTTPException(status_code=403, detail="Você não tem permissão para rejeitar este rascunho.")
    draft.status = "rejeitado"
    draft.erro_execucao = (payload.get("motivo") or "").strip()[:500] or None
    draft.decidido_por = current_user.id
    draft.decidido_em = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True, "message": "Rascunho rejeitado."}
