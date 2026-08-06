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


#: agrupamento por ÁREA — a mesa dela é organizada por assunto (Folha/Ponto/SST/...),
#: não por nome técnico da ação.
_AREA_DRAFT = {
    "pagar_folha_lote": "Folha", "calcular_folha": "Folha", "fechar_folha": "Folha",
    "fechar_ponto": "Ponto", "justificar_ponto": "Ponto",
    "registrar_afastamento": "SST", "renovar_aso": "SST",
    "registrar_ferias": "Férias", "solicitar_ferias": "Férias",
    "registrar_desligamento": "Rescisão", "concluir_admissao": "Admissão",
    "alocar_em_posto": "Operacional", "baixar_alocacao": "Operacional",
}


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
            {"isText": True, "v": _AREA_DRAFT.get(r[1], "DP"), "w": 600, "tc": "#0F1B3A", "ini": ""},
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
        "grid": "0.9fr 1.1fr 2.0fr 0.7fr 1.0fr 0.8fr",
        "cols": ["Área", "Tipo", "Descrição", "Risco", "Solicitado por", "Criado"],
        "rows": [_row(r) for r in rows],
    }
    return {"pendentes": scr, "prazos": await _tela_prazos(db, current_user)}


# --------------------------------------------------------------------------- #
# A MESA DA PYETRA — o quadro de prazos, que é o que ela mantinha na parede
# --------------------------------------------------------------------------- #
#: os prazos NÃO vivem em `agent_drafts` — vêm dos watchers proativos, que gravam em
#: `proativo_alert_state`. Sem esta tela a Central mostra só "o que o agente propôs" e
#: deixa de fora "o que está vencendo", que é justamente a coluna do quadro dela.
_SEV_BADGE = {
    "critico": ("Crítico", "#B42318", "#FEF3F2"),
    "atencao": ("Atenção", "#B54708", "#FFFAEB"),
    "info": ("Info", "#175CD3", "#EFF8FF"),
}


async def _tela_prazos(db: AsyncSession, current_user=None) -> dict:
    """Prazos vivos do DP, do mais urgente para o menos. Vazio real = vazio honesto."""
    rows = (await db.execute(text(
        "SELECT regra, severidade, title, body, first_seen_at "
        "FROM proativo_alert_state "
        "WHERE resolved_at IS NULL AND regra LIKE 'dp_%' "
        "ORDER BY CASE severidade WHEN 'critico' THEN 0 WHEN 'atencao' THEN 1 ELSE 2 END, "
        "         first_seen_at"
    ))).fetchall()

    _AREA = {
        "dp_aviso_previo_vencendo": "Aviso prévio",
        "dp_termino_experiencia": "Términos de contrato",
        "dp_ferias_limite_gozo": "Férias",
        "dp_retorno_ferias": "Férias",
        "dp_desligamento_sem_processo": "Migração p/ o fluxo nativo",
        "dp_admissao_em_curso": "Admissões",
    }

    def _linha(r):
        badge, color, bg = _SEV_BADGE.get(r[1], ("—", "#64748B", "#F1F4FA"))
        return {"cells": [
            {"isText": True, "v": _AREA.get(r[0], r[0]), "w": 600, "tc": "#0F1B3A", "ini": ""},
            {"isBadge": True, "v": badge, "color": color, "bg": bg},
            {"isText": True, "v": (r[2] or "")[:70], "w": 600, "tc": "#0F1B3A", "ini": ""},
            {"isText": True, "v": (r[3] or "")[:150], "w": 400, "tc": "#334155", "ini": ""},
            {"isText": True, "v": r[4].strftime("%d/%m") if r[4] else "—", "w": 500,
             "tc": "#64748B", "ini": ""},
        ]}

    return {
        "title": "Prazos do DP",
        "sub": (f"{len(rows)} prazo(s) vivos — do mais urgente para o menos"
                if rows else "Nenhum prazo vencendo. Os vigias só enxergam o que já está "
                             "no fluxo nativo; o que ainda vem da Portte não aparece aqui."),
        "cta": "Atualizar", "type": "table", "searchHint": "Buscar prazo…",
        "grid": "1.1fr 0.7fr 1.8fr 2.4fr 0.6fr",
        "cols": ["Área", "Risco", "O quê", "Detalhe", "Desde"],
        "rows": [_linha(r) for r in rows],
    }


EXTRA_MENU = {SLUG: [
    {"id": "pendentes", "label": "Aprovações",
     "icon": "M9 12l2 2 4-4M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18"},
    {"id": "prazos", "label": "Prazos",
     "icon": "M12 8v4l3 3M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18"},
]}

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
