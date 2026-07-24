"""Ação 🟡 propor→aprovar: CLT justifica um ajuste de ponto -> registro PENDENTE p/ o DP.

NUNCA aplica na folha nem edita gp_clock_punches. Grava 1 linha em gp_justifications
(status default 'pendente'); o DP aprova downstream (reviewed_by/reviewed_at). Escopo:
scope.employee_id (a pessoa só justifica o PRÓPRIO ponto). Idempotência: não duplica um
pendente idêntico (mesmo employee_id + motivo + punch_id) ainda em aberto."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text

from .tool_registry import ToolDef, register

_ARGS = {
    "type": "object",
    "properties": {
        "motivo": {"type": "string", "minLength": 3, "maxLength": 1000,
                   "description": "A justificativa do colaborador (obrigatória)."},
        "tipo": {"type": "string", "enum": ["ajuste", "atraso", "falta"], "description": "Tipo (default 'ajuste')."},
        "categoria": {"type": "string",
                      "enum": ["transito", "saude", "familiar", "transporte_publico", "acidente", "outro"]},
        "punch_id": {"type": "string", "description": "ID da batida relacionada (opcional)."},
    },
    "required": ["motivo"],
}


async def _justificar_ponto(
    db, user, scope, *, motivo: str, tipo: str = "ajuste", categoria: str = "outro",
    punch_id: str | None = None, **_
) -> dict[str, Any]:
    emp = getattr(scope, "employee_id", None) if scope else None
    if not emp:
        return {"status": "aguardando dado", "motivo": "usuário sem colaborador vinculado — não é possível justificar"}
    motivo = (motivo or "").strip()
    if len(motivo) < 3:
        return {"erro": "descreva a justificativa (mínimo 3 caracteres)"}

    # m11 — pertencimento: se veio punch_id, a batida TEM de ser do próprio colaborador
    # (scope.employee_id). Não pertence => recusa limpa sem revelar existência e sem gravar.
    if punch_id:
        dono = (await db.execute(
            text(
                "SELECT 1 FROM gp_clock_punches WHERE punch_id = :pid AND employee_id::text = :emp LIMIT 1"
            ),
            {"pid": punch_id, "emp": emp},
        )).scalar()
        if not dono:
            return {"status": "recusado", "motivo": "batida não encontrada"}

    # Idempotência: um pendente idêntico ainda em aberto não é duplicado.
    existente = (await db.execute(
        text(
            "SELECT justification_id FROM gp_justifications "
            "WHERE employee_id = :e AND reason = :r AND status = 'pendente' "
            "AND (punch_id IS NOT DISTINCT FROM :p) LIMIT 1"
        ),
        {"e": emp, "r": motivo, "p": punch_id},
    )).scalar()
    if existente:
        return {"justification_id": existente, "status": "pendente", "duplicado": True}

    jid = str(uuid.uuid4())
    await db.execute(
        text(
            "INSERT INTO gp_justifications "
            "(justification_id, punch_id, employee_id, justification_type, reason, category, status, source) "
            "VALUES (:jid, :p, :e, :t, :r, :c, 'pendente', 'consultor_ia')"
        ),
        {"jid": jid, "p": punch_id, "e": emp, "t": tipo, "r": motivo, "c": categoria},
    )
    await db.commit()
    return {
        "justification_id": jid, "status": "pendente",
        "aviso": "Sua justificativa foi ENVIADA ao DP para aprovação. O ponto NÃO foi alterado; "
                 "só reflete na folha após o DP aprovar.",
    }


JUSTIFICAR_TOOL: ToolDef = register(ToolDef(
    "justificar_ajuste_de_ponto", "self",
    "Enviar ao DP uma justificativa/ajuste do MEU ponto (fica PENDENTE de aprovação; não altera a folha).",
    _ARGS, _justificar_ponto, scope_kind="self",
))
