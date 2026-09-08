"""
Controller de Documentos do Kit — endpoints REST.

Gerencia documentos individuais dentro de kits documentais:
upload manual, assinatura digital, download e listagem.
"""

import logging
import os
import uuid
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.ged.models.kit_document import KitDocument
from modules.people_management.ged.schemas.document import (
    DocumentListResponse,
    DocumentResponse,
    DocumentUpdate,
)
from modules.people_management.ged.services.document_collector_service import (
    GED_STORAGE_BASE,
    DocumentCollectorService,
)
from modules.people_management.ged.services.export_service import ExportService
from modules.people_management.ged.services.signature_integration_service import SignatureIntegrationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["GED - Documentos"])


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    kit_id: str | None = Query(None, description="Filtrar por kit"),
    employee_id: str | None = Query(None, description="Filtrar por funcionario"),
    document_type: str | None = Query(None, description="Filtrar por tipo"),
    skip: int = Query(0, ge=0, description="Offset"),
    limit: int = Query(20, ge=1, le=100, description="Limite"),
) -> Any:
    """Lista documentos com filtros e paginacao."""
    import math

    query = select(KitDocument)
    count_query = select(func.count()).select_from(KitDocument)

    filters = []
    if kit_id:
        filters.append(KitDocument.kit_id == kit_id)
    if employee_id:
        filters.append(KitDocument.employee_id == employee_id)
    if document_type:
        filters.append(KitDocument.document_type == document_type)

    for f in filters:
        query = query.where(f)
        count_query = count_query.where(f)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Contagens de assinados
    signed_query = select(func.count()).select_from(KitDocument).where(KitDocument.is_signed.is_(True))
    for f in filters:
        signed_query = signed_query.where(f)
    signed_result = await db.execute(signed_query)
    signed_count = signed_result.scalar() or 0

    query = query.order_by(KitDocument.document_type, KitDocument.created_at)
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    documents = result.scalars().all()

    page = (skip // limit) + 1 if limit > 0 else 1
    pages = math.ceil(total / limit) if limit > 0 else 0

    items = []
    for doc in documents:
        items.append(_doc_to_response(doc))

    return DocumentListResponse(
        items=items,
        total=total,
        page=page,
        page_size=limit,
        pages=pages,
        signed_count=signed_count,
        unsigned_count=total - signed_count,
    )


@router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(..., description="Arquivo do documento"),
    kit_id: str = Form(..., description="ID do kit"),
    document_type: str = Form(..., description="Tipo do documento"),
    employee_id: str | None = Form(None, description="ID do funcionario"),
    document_name: str | None = Form(None, description="Nome customizado"),
    notes: str | None = Form(None, description="Observacoes"),
) -> Any:
    """Upload manual de documento para um kit."""
    collector = DocumentCollectorService(db)
    try:  # kit_id entra no caminho do disco: só UUID (kit_id="../x" escrevia fora do storage)
        kit_id = str(uuid.UUID(str(kit_id)))
    except ValueError:
        raise HTTPException(status_code=422, detail="kit_id inválido")

    # Determinar nome do documento
    final_name = document_name or file.filename or f"documento_{document_type}"

    # Salvar arquivo no storage
    upload_dir = os.path.join(GED_STORAGE_BASE, "uploads", kit_id)
    os.makedirs(upload_dir, exist_ok=True)

    safe_filename = f"{str(uuid4())[:8]}_{file.filename or 'doc.pdf'}"
    file_path_full = os.path.join(upload_dir, safe_filename)
    relative_path = os.path.join("uploads", kit_id, safe_filename)

    file_size = 0
    with open(file_path_full, "wb") as buffer:
        while True:
            chunk = await file.read(8192)
            if not chunk:
                break
            buffer.write(chunk)
            file_size += len(chunk)

    try:
        result = await collector.add_manual_document(
            kit_id=kit_id,
            file_path=relative_path,
            document_type=document_type,
            document_name=final_name,
            employee_id=employee_id,
            notes=notes,
            file_size_bytes=file_size,
            mime_type=file.content_type or "application/pdf",
        )
        await db.commit()

        # Buscar documento criado para retornar
        doc_result = await db.execute(select(KitDocument).where(KitDocument.id == result["id"]))
        doc = doc_result.scalar_one_or_none()
        if doc:
            return _doc_to_response(doc)
        return result

    except ValueError as e:
        # Limpar arquivo se falhar
        if os.path.exists(file_path_full):
            os.remove(file_path_full)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna detalhes de um documento pelo ID."""
    result = await db.execute(select(KitDocument).where(KitDocument.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Documento nao encontrado: {document_id}")
    return _doc_to_response(doc)


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    data: DocumentUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Atualiza metadados de um documento."""
    result = await db.execute(select(KitDocument).where(KitDocument.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Documento nao encontrado: {document_id}")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(doc, field):
            setattr(doc, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(doc)

    return _doc_to_response(doc)


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Remove um documento de um kit."""
    collector = DocumentCollectorService(db)
    try:
        result = await collector.remove_document(document_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{document_id}/sign", status_code=201)
async def sign_document(
    document_id: str,
    request: Request,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Assina digitalmente um documento.

    Calcula hash SHA-256, registra IP e user-agent para auditoria.
    """
    sig_service = SignatureIntegrationService(db)

    # Extrair metadados de auditoria do request
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    try:
        result = await sig_service.process_signature(
            document_id=document_id,
            employee_id=str(current_user.id),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Download do arquivo de um documento."""
    result = await db.execute(select(KitDocument).where(KitDocument.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Documento nao encontrado: {document_id}")

    if not doc.file_path:
        raise HTTPException(status_code=404, detail="Documento nao possui arquivo vinculado")

    # 275 documentos apontam para o Drive (URL) e 44 para uma rota interna do Inter: não são
    # arquivos em disco. E a base de path-traversal era /app/uploads fixa enquanto o path relativo
    # é resolvido contra GED_STORAGE_BASE — 60% dos downloads davam 400 (revisão 08/09/2026).
    if str(doc.file_path).startswith(("http://", "https://")):
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url=doc.file_path, status_code=307)
    if str(doc.file_path).startswith("/inter/"):
        raise HTTPException(status_code=404, detail="Comprovante bancário: abra pelo módulo Financeiro (Inter), não há arquivo no GED.")
    full_path = doc.file_path
    if not os.path.isabs(doc.file_path):
        full_path = os.path.join(GED_STORAGE_BASE, doc.file_path)

    # Path traversal protection (INV-3): o alvo tem de ficar sob uma das bases de storage
    _bases = [Path(GED_STORAGE_BASE).resolve(), Path("/app/uploads").resolve()]
    _target = Path(full_path).resolve()
    if not any(_target.is_relative_to(b) for b in _bases):
        raise HTTPException(status_code=400, detail="Path de arquivo invalido")

    if not _target.exists():
        raise HTTPException(
            status_code=404,
            detail=f"PDF nao encontrado em disco: {Path(full_path).name}",
        )

    # Registrar log de acesso
    export_svc = ExportService(db)
    await export_svc.log_access(
        kit_id=str(doc.kit_id),
        action="downloaded",
        actor_type="internal",
        actor_id=str(current_user.id),
        actor_name=getattr(current_user, "full_name", None) or str(current_user.id),
        ip=None,
        user_agent=None,
        notes=f"Download documento: {doc.document_name}",
    )
    await db.commit()

    return FileResponse(
        path=str(_target),
        filename=os.path.basename(full_path),
        media_type="application/pdf",
    )


def _doc_to_response(doc: KitDocument) -> DocumentResponse:
    """Converte KitDocument ORM para DocumentResponse."""
    file_size_display = None
    if doc.file_size_bytes:
        if doc.file_size_bytes >= 1_048_576:
            file_size_display = f"{doc.file_size_bytes / 1_048_576:.1f} MB"
        elif doc.file_size_bytes >= 1024:
            file_size_display = f"{doc.file_size_bytes / 1024:.1f} KB"
        else:
            file_size_display = f"{doc.file_size_bytes} B"

    return DocumentResponse(
        id=str(doc.id),
        kit_id=str(doc.kit_id),
        employee_id=str(doc.employee_id) if doc.employee_id else None,
        employee_name=None,  # Seria preenchido com join no Employee
        document_type=doc.document_type,
        document_name=doc.document_name,
        file_path=doc.file_path,
        file_size_bytes=doc.file_size_bytes,
        file_size_display=file_size_display,
        mime_type=doc.mime_type,
        is_signed=doc.is_signed,
        signed_at=doc.signed_at,
        signed_by=str(doc.signed_by) if doc.signed_by else None,
        signature_hash=doc.signature_hash,
        source_module=doc.source_module,
        source_record_id=str(doc.source_record_id) if doc.source_record_id else None,
        auto_generated=doc.auto_generated,
        notes=doc.notes,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


# ---------------------------------------------------------------------------
# Ingestao Historica — endpoints
# ---------------------------------------------------------------------------


@router.post("/ingestao/historica", tags=["GED - Ingestao Historica"])
async def ingestao_historica(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    folder_id: str | None = Query(None, description="ID da pasta GDrive (usa padrao se omitido)"),
):
    """
    Processa todos os ZIPs historicos da pasta Google Drive e alimenta SOPHIA.

    - Lista ZIPs na pasta KITS_FOLDER_ID
    - Extrai texto dos PDFs (PyMuPDF primario, PyPDF2 fallback)
    - Indexa cada PDF no SOPHIA para busca semantica
    - Persiste no gedeon_document_index
    """
    from modules.people_management.ged.services.ingestao_historica import (
        KITS_FOLDER,
        ingestao,
    )

    pasta = folder_id or KITS_FOLDER
    resultado = await ingestao.processar_todos_os_zips(folder_id=pasta)
    return {"pasta_gdrive": pasta, **resultado}


