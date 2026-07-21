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
@router.post("/documentos/upload", status_code=201)
def upload_documento(
    tipo: str = Form(...),
    descricao: str | None = Form(None),
    data_inicio: str | None = Form(None),   # atestado: início do afastamento (aaaa-mm-dd)
    data_fim: str | None = Form(None),       # atestado: fim
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """O funcionário envia um documento — cai na ficha dele. Atestado médico também
    abre uma justificativa de ponto PENDENTE para o DP aprovar."""
    emp = _employee_id(current_user)
    tipo = tipo if tipo in _TIPOS else "outros"
    data = arquivo.file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Arquivo vazio.")
    if len(data) > _MAX:
        raise HTTPException(status_code=413, detail="Arquivo muito grande (máx. 12 MB).")

    pasta = _storage_base() / re.sub(r"[^a-f0-9-]", "", emp)
    pasta.mkdir(parents=True, exist_ok=True)
    ext = _EXT.get((arquivo.content_type or "").lower()) or (Path(arquivo.filename or "").suffix or ".bin")
    fpath = pasta / f"{tipo}_{_uuid.uuid4().hex[:8]}{ext}"
    fpath.write_bytes(data)

    # ficha usa o mesmo condominio_id default das certidões KYC (aparece em DP → Documentos)
    cond = _COND_FALLBACK
    titulo = _TIPOS[tipo] + (f" — {descricao.strip()}" if descricao and descricao.strip() else "")
    doc_id = db.execute(
        text(
            "INSERT INTO hr_employee_documents (id, condominio_id, employee_id, document_type, category, "
            " title, description, file_path, file_name, file_size, mime_type, status, is_published, "
            " reference_type, created_by, created_at, updated_at) "
            "VALUES (gen_random_uuid(), CAST(:c AS uuid), CAST(:e AS uuid), :dt, 'enviado_funcionario', "
            " :ti, :de, :fp, :fn, :fs, :mt, 'ativo', true, 'portal_funcionario', CAST(:e AS uuid), now(), now()) "
            "RETURNING id::text"
        ),
        {"c": str(cond or _COND_FALLBACK), "e": emp, "dt": tipo, "ti": titulo[:255],
         "de": (descricao or None), "fp": str(fpath), "fn": (arquivo.filename or fpath.name)[:255],
         "fs": len(data), "mt": arquivo.content_type},
    ).scalar()

    justificativa_id = None
    if tipo == "atestado_medico":
        # abre justificativa de ponto PENDENTE (DP aprova → espelho abona; nunca automático)
        periodo = ""
        if data_inicio:
            periodo = f" (período {data_inicio}" + (f" a {data_fim}" if data_fim else "") + ")"
        justificativa_id = db.execute(
            text(
                "INSERT INTO gp_justifications (justification_id, employee_id, justification_type, "
                " reason, category, status, attachments, source, source_id, created_at, updated_at) "
                "VALUES (:jid, CAST(:e AS uuid), 'atestado_medico', :rz, 'atestado', "
                " 'pending', CAST(:att AS jsonb), 'portal_funcionario', :sid, now(), now()) RETURNING id::text"
            ),
            {"jid": "ATM-" + secrets.token_hex(4).upper(), "e": emp,
             "rz": (f"Atestado médico enviado pelo funcionário{periodo}." + (f" {descricao.strip()}" if descricao else "")),
             "att": json.dumps([{"document_id": doc_id, "file_path": str(fpath), "data_inicio": data_inicio, "data_fim": data_fim}]),
             "sid": doc_id},
        ).scalar()
    db.commit()
    return {
        "success": True, "document_id": doc_id, "tipo": tipo,
        "na_ficha": True,
        "justificativa_pendente": bool(justificativa_id),
        "mensagem": (
            "Atestado enviado! Ficou na sua ficha e foi encaminhado ao DP para abonar seu ponto."
            if justificativa_id else "Documento enviado e anexado à sua ficha."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2) OUVIDORIA — reclamação sigilosa (anônima ou identificada)
# ─────────────────────────────────────────────────────────────────────────────
# NR-1 — fatores de risco psicossocial (a ouvidoria é o canal de IDENTIFICAÇÃO).
# Uma manifestação de qualquer destes alimenta o inventário de riscos (gp_risks).
_FATORES_PSICOSSOCIAIS = {
    "assedio_moral": "Assédio moral",
    "assedio_sexual": "Assédio sexual",
    "sobrecarga": "Sobrecarga / jornada excessiva",
    "violencia": "Violência / agressão no trabalho",
    "discriminacao": "Discriminação",
    "relacao_lideranca": "Conflitos / relação com a liderança",
    "saude_mental": "Saúde mental / estresse",
}


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
