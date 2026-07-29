"""Fase 5.6a (LT2) — Rota de revisão do detector de anomalia de pagamento.

Controller NOVO e enxuto (a casca antiga `fraud_controller.py` está quebrada —
ver docstring de `services/anomalia_pagamentos.py`; NÃO reaproveitada aqui).

READ-ONLY sobre `inter_payments` sempre: NENHUM endpoint deste arquivo age
sobre o pagamento (não bloqueia, não cancela, não aprova, não reenvia). As
duas ações de escrita mudam SOMENTE o `status` do ALERTA em `fraud_alerts` —
são ações HUMANAS (nunca automáticas), gated à diretoria (role admin, mesma
população que resolve `resolver_usuarios_por_roles(['admin'])` no sino) e
auditadas em `audit_logs` (via `agent_audit`, mesmo pacote da Fase 5.2a.3/5.5).

GET  /ai/fraud/anomalias/pendentes         → lista status='pending' (suspeitas
                                              ainda não revisadas por ninguém).
POST /ai/fraud/anomalias/{id}/confirmar    → status→'confirmed': a diretoria
                                              confirma que a suspeita é
                                              legítima (qualquer ação sobre o
                                              pagamento em si acontece FORA
                                              deste endpoint, por outro fluxo
                                              gated/OTP já existente).
POST /ai/fraud/anomalias/{id}/descartar    → status→'false_positive': a
                                              diretoria descarta como ruído
                                              estatístico.
Um alerta só pode ser revisado enquanto está 'pending' (409 se já revisado —
evita dupla revisão/objetos concorrentes pisando um no outro).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user, get_db

router = APIRouter(prefix="/ai/fraud", tags=["AI - Anomalia Pagamentos"])


async def require_diretoria(user=Depends(get_current_active_user)):
    """Gate diretoria: role == 'admin' — mesma população que recebe o aviso
    no sino (`resolver_usuarios_por_roles(('admin',))`). Confirmar/descartar
    é SEMPRE ação humana, nunca disparada automaticamente pelo detector."""
    if (getattr(user, "role", "") or "").lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Revisão de anomalias de pagamento restrita à diretoria (admin)",
        )
    return user


class DescartarIn(BaseModel):
    motivo: str | None = None


_SELECT_PENDENTES = """
    SELECT id, alert_number, severity, status, title, summary,
           entity_name, transaction_id, transaction_type, transaction_value,
           risk_score, confidence_score, indicators, detected_at, created_at
    FROM fraud_alerts
    WHERE status = 'pending' AND category = 'payment'
    ORDER BY detected_at DESC
"""


def _serializar(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(r["id"]),
        "alert_number": r["alert_number"],
        "severity": r["severity"],
        "status": r["status"],
        "title": r["title"],
        "summary": r["summary"],
        "beneficiario": r["entity_name"],
        "payment_id": str(r["transaction_id"]) if r.get("transaction_id") else None,
        "payment_type": r.get("transaction_type"),
        "valor": r.get("transaction_value"),
        "risk_score": r.get("risk_score"),
        "confidence_score": r.get("confidence_score"),
        "indicators": r.get("indicators"),
        "detected_at": r["detected_at"].isoformat() if r.get("detected_at") else None,
    }


@router.get(
    "/anomalias/pendentes",
    summary="Lista suspeitas de anomalia de pagamento pendentes de revisão — diretoria",
)
async def listar_pendentes(
    user=Depends(require_diretoria),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    rows = (await db.execute(text(_SELECT_PENDENTES))).mappings().all()
    return [_serializar(dict(r)) for r in rows]


async def _carregar_pending(db: AsyncSession, alerta_id: UUID) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                "SELECT id, alert_number, status, entity_name, transaction_value "
                "FROM fraud_alerts WHERE id = :id"
            ),
            {"id": str(alerta_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Alerta de anomalia não encontrado")
    if row["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Alerta já foi revisado (status atual: '{row['status']}')",
        )
    return dict(row)


async def _auditar(db: AsyncSession, alerta: dict[str, Any], *, novo_status: str, user: Any) -> None:
    """Best-effort: auditoria nunca derruba a revisão humana em si."""
    try:
        from modules.ai.conversation.services.garantia import agent_audit

        autor = getattr(user, "email", None) or getattr(user, "id", None) or "diretoria"
        await agent_audit.registrar_acao_agente(
            db,
            origem="anomalia_pagamentos",
            pergunta=f"revisão alerta {alerta.get('alert_number')} por {autor}",
            resposta=(
                f"[{novo_status}] beneficiário={alerta.get('entity_name')} "
                f"valor={alerta.get('transaction_value')}"
            ),
            modelo="humano",
            tier="diretoria",
            provider="human",
            groundedness_ok=True,
        )
    except Exception:  # noqa: BLE001
        pass


@router.post(
    "/anomalias/{alerta_id}/confirmar",
    summary="Confirma a suspeita como legítima (ação humana) — diretoria",
)
async def confirmar_anomalia(
    alerta_id: UUID,
    user=Depends(require_diretoria),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    alerta = await _carregar_pending(db, alerta_id)
    await db.execute(
        text(
            "UPDATE fraud_alerts SET status = 'confirmed', confirmed_by = :uid, "
            "confirmed_at = now(), updated_at = now() WHERE id = :id"
        ),
        {"uid": str(getattr(user, "id", None)), "id": str(alerta_id)},
    )
    await db.commit()
    await _auditar(db, alerta, novo_status="confirmed", user=user)
    return {
        "ok": True,
        "id": str(alerta_id),
        "alert_number": alerta["alert_number"],
        "status": "confirmed",
    }


@router.post(
    "/anomalias/{alerta_id}/descartar",
    summary="Descarta a suspeita como falso positivo (ação humana) — diretoria",
)
async def descartar_anomalia(
    alerta_id: UUID,
    body: DescartarIn,
    user=Depends(require_diretoria),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    alerta = await _carregar_pending(db, alerta_id)
    await db.execute(
        text(
            "UPDATE fraud_alerts SET status = 'false_positive', resolved_by = :uid, "
            "resolved_at = now(), resolution_type = 'false_positive', "
            "resolution_notes = :notas, updated_at = now() WHERE id = :id"
        ),
        {
            "uid": str(getattr(user, "id", None)),
            "notas": (body.motivo or "")[:2000],
            "id": str(alerta_id),
        },
    )
    await db.commit()
    await _auditar(db, alerta, novo_status="false_positive", user=user)
    return {
        "ok": True,
        "id": str(alerta_id),
        "alert_number": alerta["alert_number"],
        "status": "false_positive",
    }
