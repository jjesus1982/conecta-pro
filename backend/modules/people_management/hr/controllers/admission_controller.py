"""
Controller de Admissão — Departamento Pessoal.

Endpoints para o workflow de admissão de novos colaboradores.
"""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.hr.models.admission import AdmissionStatus
from modules.people_management.hr.publishers import publish_funcionario_admitido
from modules.people_management.hr.schemas.admission import (
    AdmissionProcessCreate,
    AdmissionProcessResponse,
    AdmissionProcessUpdate,
)
from modules.people_management.hr.services.admission_service import AdmissionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admissions", tags=["DP - Admissões"])


@router.get(
    "",
    summary="Listar Admissões",
    description="Retorna lista paginada de processos de admissão com filtro por status.",
)
async def list_admissions(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    status: AdmissionStatus | None = Query(None, description="Filtro por status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Any:
    """Lista processos de admissão com filtro e paginação."""
    service = AdmissionService(db)
    return await service.list_admissions(status=status, page=page, page_size=page_size)


@router.post(
    "",
    summary="Iniciar Processo de Admissão",
    response_model=AdmissionProcessResponse,
    status_code=201,
    description="Retorna lista paginada de processos de admissão com filtro por status.",
)
async def create_admission(
    data: AdmissionProcessCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Cria um novo processo de admissão."""
    service = AdmissionService(db)
    try:
        admission = await service.create_admission(data.model_dump(), created_by_id=current_user.id)
    except ValueError as e:
        # ex.: CPF de funcionário ATIVO já existe → 409 gracioso (não 500)
        raise HTTPException(status_code=409, detail=str(e))
    await db.commit()
    return admission


@router.get(
    "/checklist",
    summary="Checklist de Documentos",
    description="Retorna lista paginada de processos de admissão com filtro por status.",
)
async def get_document_checklist(
    include_security: bool = Query(True, description="Incluir documentos de vigilância"),
) -> Any:
    """Retorna checklist padrão de documentos para admissão."""
    service = AdmissionService(db=None)  # type: ignore[arg-type]
    return service.generate_document_checklist(include_security=include_security)


@router.get(
    "/stats",
    summary="Estatísticas de Admissão",
    description="Retorna lista paginada de processos de admissão com filtro por status.",
)
async def get_admission_stats(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna estatisticas dos processos de admissao."""
    from sqlalchemy import text

    r = (await db.execute(text("SELECT status, COUNT(*) as qtd FROM admission_processes GROUP BY status"))).fetchall()
    total = sum(int(row.qtd) for row in r)
    by_status = {row.status: int(row.qtd) for row in r}
    return {
        "total": total,
        "by_status": by_status,
        "documents_pending": by_status.get("documents_pending", 0),
        "medical_exam": by_status.get("medical_exam", 0),
        "contract_signing": by_status.get("contract_signing", 0),
        "completed": by_status.get("completed", 0),
    }


@router.get(
    "/{admission_id}",
    summary="Buscar Admissão",
    response_model=AdmissionProcessResponse,
    description="Retorna lista paginada de processos de admissão com filtro por status.",
)
async def get_admission(
    admission_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna detalhes de um processo de admissão."""
    service = AdmissionService(db)
    admission = await service.get_by_id(admission_id)
    if not admission:
        raise HTTPException(status_code=404, detail="Admissão não encontrada")
    return admission


@router.patch(
    "/{admission_id}",
    summary="Atualizar Admissão",
    response_model=AdmissionProcessResponse,
    description="Retorna lista paginada de processos de admissão com filtro por status.",
)
async def update_admission(
    admission_id: str,
    data: AdmissionProcessUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Atualiza dados de um processo de admissão."""
    service = AdmissionService(db)
    update_data = data.model_dump(exclude_unset=True)
    new_status = update_data.pop("status", None)

    if new_status:
        admission = await service.update_status(admission_id, new_status, data=update_data)
    else:
        admission = await service.get_by_id(admission_id)
        if admission:
            for key, value in update_data.items():
                if hasattr(admission, key) and value is not None:
                    setattr(admission, key, value)
            await db.flush()
            await db.refresh(admission)

    if not admission:
        raise HTTPException(status_code=404, detail="Admissão não encontrada")
    await db.commit()
    return admission


@router.post(
    "/{admission_id}/complete",
    summary="Concluir Admissão",
    status_code=201,
    description="Retorna lista paginada de processos de admissão com filtro por status.",
)
async def complete_admission(
    admission_id: str,
    employee_data: dict,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Conclui o processo de admissão e cria o registro de Employee."""
    service = AdmissionService(db)
    try:
        result = await service.complete_admission(admission_id, employee_data)
        await db.commit()
        asyncio.create_task(
            publish_funcionario_admitido(
                funcionario_id=str(result["employee"].id),
                funcionario_nome=str(
                    getattr(result["employee"], "nome", "") or getattr(result["employee"], "name", "")
                ),
                cargo=str(getattr(result["employee"], "cargo", "")),
                data_admissao=str(getattr(result["employee"], "data_admissao", "") or ""),
                # [Item −1/A1] cliente_id (backfill via employee_alocacoes) → GEDEON monta o kit do condomínio certo
                cliente_id=str(getattr(result["employee"], "cliente_id", "") or "") or None,
            )
        )
        return {
            "message": "Admissão concluída com sucesso",
            "admission_id": str(result["admission"].id),
            "employee_id": str(result["employee"].id),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{admission_id}/documents",
    summary="Upload de Documento",
    status_code=201,
    description="Retorna lista paginada de processos de admissão com filtro por status.",
)
async def upload_document(
    admission_id: str,
    file: UploadFile = File(...),
    document_type: str = Query("outro", description="Tipo: rg, cpf, ctps, cnv, aso, etc"),
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Upload de documento para o processo de admissao."""
    import os
    from pathlib import Path
    from uuid import uuid4

    service = AdmissionService(db)
    admission = await service.get_by_id(admission_id)
    if not admission:
        raise HTTPException(status_code=404, detail="Admissao nao encontrada")

    # Base gravável: configurável por env, com fallback para /tmp/uploads
    # (o volume padrão /app/uploads pode estar montado somente-leitura).
    base_candidates = [
        os.getenv("HR_UPLOAD_DIR"),
        "/app/uploads",
        "/tmp/uploads",
    ]
    upload_dir = None
    last_error: Exception | None = None
    for base in base_candidates:
        if not base:
            continue
        candidate = Path(base) / "admissions" / admission_id
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            # Confirma que é realmente gravável
            if os.access(candidate, os.W_OK):
                upload_dir = candidate
                break
        except OSError as exc:  # permissão, disco, etc.
            last_error = exc
            continue
    if upload_dir is None:
        raise HTTPException(
            status_code=500,
            detail=f"Nao foi possivel criar diretorio de upload gravavel: {last_error}",
        )

    ext = (file.filename or "doc").rsplit(".", 1)[-1] if file.filename else "pdf"
    file_id = str(uuid4())[:8]
    filename = f"{document_type}_{file_id}.{ext}"
    file_path = upload_dir / filename

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Update documents_received in admission
    docs = dict(admission.documents_received or {})
    docs[document_type] = {
        "filename": filename,
        "original_name": file.filename,
        "size_bytes": len(content),
        "uploaded_at": __import__("datetime").datetime.now().isoformat(),
        "path": str(file_path),
    }
    admission.documents_received = docs

    # Also mark checklist item if it matches
    checklist = dict(admission.checklist or {})
    for category, items in checklist.items():
        if isinstance(items, dict) and document_type in items:
            checklist[category] = {**items, document_type: True}
    admission.checklist = checklist

    await db.flush()
    await db.refresh(admission)
    await db.commit()

    return {
        "message": f"Documento '{document_type}' enviado com sucesso",
        "filename": filename,
        "size_bytes": len(content),
        "document_type": document_type,
        "documents_total": len(docs),
    }


@router.get(
    "/{admission_id}/documents",
    summary="Listar Documentos da Admissão",
    description="Retorna lista paginada de processos de admissão com filtro por status.",
)
async def list_documents(
    admission_id: str,
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista documentos enviados para o processo de admissao."""
    service = AdmissionService(db)
    admission = await service.get_by_id(admission_id)
    if not admission:
        raise HTTPException(status_code=404, detail="Admissao nao encontrada")

    docs = admission.documents_received or {}
    return {
        "admission_id": admission_id,
        "total": len(docs),
        "documents": [{"type": k, **v} if isinstance(v, dict) else {"type": k, "value": v} for k, v in docs.items()],
    }
