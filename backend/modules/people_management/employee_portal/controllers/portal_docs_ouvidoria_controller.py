"""Portal do Funcionário — UPLOAD de documento (→ ficha) + OUVIDORIA sigilosa.

Pedido do Jordan (2026-07-21):
1) O funcionário logado envia um documento (atestado médico, comprovante, RG, outros)
   pelo Meu Espaço → cai na FICHA (`hr_employee_documents`, a mesma que o DP lê).
   ATESTADO MÉDICO também abre uma JUSTIFICATIVA de ponto PENDENTE (`gp_justifications`)
   pro DP aprovar — só então o espelho abona (aprovação humana, nunca automática).
2) Canal de OUVIDORIA: o funcionário abre uma reclamação de forma SIGILOSA, podendo
   escolher se identificar ou permanecer ANÔNIMO (aí não guardamos o employee_id).
"""
from __future__ import annotations

import json
import os
import re
import secrets
import uuid as _uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_active_user
from core.database.session import get_sync_db_dependency
from core.models import User
from modules.people_management.employee_portal.controllers.self_service_controller import _employee_id

router = APIRouter(prefix="/self-service", tags=["Portal - Documentos & Ouvidoria"])

_TIPOS = {
    "atestado_medico": "Atestado médico",
    "comprovante": "Comprovante",
    "rg": "RG / Documento",
    "declaracao": "Declaração",
    "outros": "Outros",
}
_EXT = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png"}
_COND_FALLBACK = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"  # mesma default das certidões KYC
_MAX = 12_000_000


def _storage_base() -> Path:
    base = Path(os.environ.get("GED_STORAGE_PATH", "/app/uploads")) / "funcionario"
    return base


# ─────────────────────────────────────────────────────────────────────────────
# 1) UPLOAD de documento → ficha (+ atestado → justificativa pendente)
# ─────────────────────────────────────────────────────────────────────────────
def _registrar_risco_psicossocial(db: Session, fator_slug: str) -> None:
    """NR-1: garante um item de risco psicossocial no inventário (gp_risks) para o fator.
    O SST depois avalia nível + define medidas de controle. Idempotente por risk_id —
    o volume de manifestações vira o INDICADOR (contado a partir de ouvidoria_manifestacoes)."""
    label = _FATORES_PSICOSSOCIAIS.get(fator_slug)
    if not label:
        return
    rid = "PSICO-" + fator_slug
    if db.execute(text("SELECT 1 FROM gp_risks WHERE risk_id = :r"), {"r": rid}).fetchone():
        db.execute(text("UPDATE gp_risks SET updated_at = now() WHERE risk_id = :r"), {"r": rid})
        return
    db.execute(
        text(
            "INSERT INTO gp_risks (risk_id, categoria, descricao, nivel, status, fonte_geradora, created_at, updated_at) "
            "VALUES (:r, 'psicossocial', :d, 'baixo', 'identificado', "
            "'Canal de escuta / ouvidoria (NR-1 — risco psicossocial)', now(), now())"
        ),
        {"r": rid, "d": label},
    )


class OuvidoriaBody(BaseModel):
    categoria: str | None = None
    mensagem: str
    anonimo: bool = True


_FATORES_PSICOSSOCIAIS = {
    "assedio_moral": "Assédio moral",
    "assedio_sexual": "Assédio sexual",
    "sobrecarga": "Sobrecarga / jornada excessiva",
    "violencia": "Violência / agressão no trabalho",
    "discriminacao": "Discriminação",
    "relacao_lideranca": "Conflitos / relação com a liderança",
    "saude_mental": "Saúde mental / estresse",
}



@router.post("/ouvidoria", status_code=201)
def abrir_manifestacao(
    body: OuvidoriaBody,
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Abre uma manifestação de ouvidoria. Se anônima, NÃO guardamos o employee_id
    (sigilo real). Devolve um PROTOCOLO para o funcionário acompanhar."""
    msg = (body.mensagem or "").strip()
    if len(msg) < 5:
        raise HTTPException(status_code=422, detail="Descreva sua manifestação (mínimo 5 caracteres).")
    protocolo = "OUV-" + datetime.now().strftime("%y%m") + "-" + secrets.token_hex(3).upper()
    emp = None if body.anonimo else _employee_id(current_user)
    db.execute(
        text(
            "INSERT INTO ouvidoria_manifestacoes (protocolo, employee_id, anonimo, categoria, mensagem) "
            "VALUES (:p, :e, :a, :c, :m)"
        ),
        {"p": protocolo, "e": (emp if emp else None), "a": bool(body.anonimo),
         "c": (body.categoria or None), "m": msg},
    )
    # NR-1: fator psicossocial → alimenta o inventário de riscos (identificação documentada)
    if body.categoria in _FATORES_PSICOSSOCIAIS:
        _registrar_risco_psicossocial(db, body.categoria)
    db.commit()
    return {
        "success": True, "protocolo": protocolo, "anonimo": bool(body.anonimo),
        "mensagem": "Manifestação registrada com sigilo. Guarde seu protocolo para acompanhar."
        + ("" if body.anonimo else " Você pode acompanhá-la em 'Minhas manifestações'."),
    }


@router.get("/ouvidoria/minhas")
def minhas_manifestacoes(
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """As manifestações IDENTIFICADAS do funcionário (as anônimas não ficam vinculadas)."""
    emp = _employee_id(current_user)
    rows = db.execute(
        text("SELECT protocolo, categoria, mensagem, status, resposta, created_at, respondido_em "
             "FROM ouvidoria_manifestacoes WHERE employee_id=CAST(:e AS uuid) AND anonimo=false "
             "ORDER BY created_at DESC"),
        {"e": emp},
    ).mappings().all()
    return {"total": len(rows), "manifestacoes": [dict(r) for r in rows]}


# ─────────────────────────────────────────────────────────────────────────────
# 3) OUVIDORIA — lado ADMIN (só quem trata: role 'admin' = Jordan/Pyetra hoje)
# ─────────────────────────────────────────────────────────────────────────────
router_admin = APIRouter(prefix="/ouvidoria-admin", tags=["Ouvidoria (admin)"])


def _so_admin(current_user: User) -> None:
    if getattr(current_user, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="Canal restrito — apenas ouvidoria autorizada.")


@router_admin.get("")
def listar_manifestacoes(
    status: str | None = None,
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Lista as manifestações. Anônimas vêm SEM identidade (sigilo preservado)."""
    _so_admin(current_user)
    cond = "" if not status else " WHERE m.status = :st"
    rows = db.execute(
        text(
            "SELECT m.id::text, m.protocolo, m.anonimo, m.categoria, m.mensagem, m.status, m.resposta, "
            "  m.created_at, m.respondido_em, "
            "  CASE WHEN m.anonimo THEN NULL ELSE e.nome END AS autor "
            "FROM ouvidoria_manifestacoes m LEFT JOIN employees e ON e.id = m.employee_id"
            + cond + " ORDER BY m.created_at DESC"
        ),
        ({"st": status} if status else {}),
    ).mappings().all()
    abertas = sum(1 for r in rows if r["status"] == "aberta")
    return {"total": len(rows), "abertas": abertas, "manifestacoes": [dict(r) for r in rows]}


class ResponderBody(BaseModel):
    resposta: str
    status: str = "respondida"


@router_admin.post("/{manifestacao_id}/responder")
def responder(
    manifestacao_id: str,
    body: ResponderBody,
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Responde/atualiza o status de uma manifestação (a resposta fica visível ao autor
    identificado; para anônimas, fica pelo protocolo)."""
    _so_admin(current_user)
    r = db.execute(
        text("UPDATE ouvidoria_manifestacoes SET resposta=:r, status=:s, respondido_por=CAST(:u AS uuid), "
             "respondido_em=now(), updated_at=now() WHERE id::text=:i"),
        {"r": body.resposta, "s": body.status, "u": str(current_user.id), "i": manifestacao_id},
    )
    if r.rowcount == 0:
        raise HTTPException(status_code=404, detail="Manifestação não encontrada.")
    db.commit()
    return {"success": True}
