"""Controller para Document."""

import hashlib
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from core.security.file_validator import ged_file_validator
from modules.ged.models.document import (
    DocumentCategory,
    DocumentConfidentiality,
    DocumentType,
)
from modules.ged.schemas.document import (
    DocumentCreate,
    DocumentResponse,
)
from modules.ged.services.document_service import DocumentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["GED - Documentos"])


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    folder_id: str = Form(...),
    document_type: str = Form(default="outro"),
    category: str = Form(default="outro"),
    confidentiality: str = Form(default="interno"),
    description: str | None = Form(None),
    employee_id: str | None = Form(None),
    valid_until: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> DocumentResponse:
    """Upload de documento com arquivo.

    ``employee_id`` e ``valid_until`` são opcionais e persistidos quando enviados
    (usados pela tela dp/documentos p/ vincular o colaborador e a data de validade).
    """
    try:
        # Validar arquivo (tamanho, tipo MIME, magic number)
        content = await ged_file_validator.validate_file(file)

        # Diretório de upload
        upload_dir = Path("/app/uploads/ged")
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Calcular checksum SHA-256
        checksum = hashlib.sha256(content).hexdigest()

        # Nome único do arquivo
        file_extension = Path(file.filename or "file").suffix.lstrip(".")
        if not file_extension:
            file_extension = "bin"
        unique_filename = f"{checksum}.{file_extension}"
        file_path = upload_dir / unique_filename

        # Salvar arquivo
        with open(file_path, "wb") as f:
            f.write(content)

        # Criar documento no banco
        service = DocumentService(db)
        document_data = DocumentCreate(
            title=title,
            description=description,
            folder_id=folder_id,
            employee_id=employee_id or None,
            valid_until=(valid_until or None),
            document_type=DocumentType(document_type),
            category=DocumentCategory(category),
            confidentiality=DocumentConfidentiality(confidentiality),
            file_name=file.filename or "file",
            file_extension=file_extension,
            file_path=str(file_path),
            file_size_bytes=len(content),
            mime_type=file.content_type or "application/octet-stream",
            checksum=checksum,
            owner_id=str(current_user.id) if hasattr(current_user, "id") else current_user["id"],
            created_by=str(current_user.id) if hasattr(current_user, "id") else current_user["id"],
        )

        logger.info(f"Upload realizado: {file.filename} ({len(content)} bytes)")
        result = await service.create(document_data)

        # Disparar processamento IA em background (nao bloqueia resposta)
        from modules.ged.tasks.ai_processing import process_document_ai

        background_tasks.add_task(process_document_ai, str(result.id))
        logger.info("IA Background agendado para documento %s", result.id)

        return result

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Erro ao fazer upload de documento: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno ao fazer upload: {str(e)}",
        ) from e


@router.get("/search")
async def search_documents(
    q: str = Query("", description="Texto de busca"),
    document_type: str | None = Query(None, alias="document_type"),
    category: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    origin: str | None = Query(None),
    signed: str | None = Query(None),
    client_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Busca documentos em ged_documents e ged_kit_documents (UNION)."""
    from sqlalchemy import text as sql_text

    items: list[dict[str, Any]] = []
    q_val = q.strip() if q else ""

    # --- Parte 1: ged_documents (uploads avulsos) ---
    # Excluir quando filtros específicos de kit estão ativos
    if not client_id and (not origin or origin == "ged"):
        ged_cond = ["1=1"]
        ged_p: dict[str, Any] = {}
        if q_val:
            ged_cond.append(
                "(LOWER(title) LIKE :q OR LOWER(description) LIKE :q "
                "OR LOWER(file_name) LIKE :q OR LOWER(ocr_text) LIKE :q)"
            )
            ged_p["q"] = f"%{q_val.lower()}%"
        if document_type:
            ged_cond.append("document_type = :dtype")
            ged_p["dtype"] = document_type
        if category:
            ged_cond.append("category = :cat")
            ged_p["cat"] = category
        if status_filter:
            ged_cond.append("status = :st")
            ged_p["st"] = status_filter
        if signed is not None and signed != "":
            ged_cond.append("is_signed = :sgn")
            ged_p["sgn"] = signed.lower() == "true"

        ged_result = await db.execute(
            sql_text(
                "SELECT id::text, title, document_type, "
                "is_signed, status, created_at, category "
                f"FROM ged_documents WHERE {' AND '.join(ged_cond)} "
                "ORDER BY created_at DESC LIMIT :lim"
            ),
            {**ged_p, "lim": limit},
        )
        for r in ged_result.mappings().all():
            items.append(
                {
                    "id": str(r["id"]),
                    "title": r["title"],
                    "name": r["title"],
                    "document_type": r["document_type"] or "—",
                    "kit_id": None,
                    "kit_name": None,
                    "employee_name": None,
                    "signed": bool(r["is_signed"]),
                    "status": r["status"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    "category": r["category"],
                    "origin": "ged",
                }
            )

    # --- Parte 2: ged_kit_documents (documentos reais dos kits) ---
    # Excluir apenas quando filtros exclusivos de ged_documents estão ativos
    if not category and (not origin or origin != "ged"):
        kit_cond = ["1=1"]
        kit_p: dict[str, Any] = {}
        if q_val:
            kit_cond.append("(LOWER(gkd.document_name) LIKE :q OR LOWER(e.nome) LIKE :q OR LOWER(gc.name) LIKE :q)")
            kit_p["q"] = f"%{q_val.lower()}%"
        if document_type:
            kit_cond.append("gkd.document_type = :dtype")
            kit_p["dtype"] = document_type
        if origin:
            kit_cond.append("gkd.source_module = :origin")
            kit_p["origin"] = origin
        if signed is not None and signed != "":
            kit_cond.append("gkd.is_signed = :sgn")
            kit_p["sgn"] = signed.lower() == "true"
        if client_id:
            kit_cond.append("dk.client_id::text = :cid")
            kit_p["cid"] = client_id

        kit_result = await db.execute(
            sql_text(
                "SELECT gkd.id::text, gkd.document_name AS title, "
                "gkd.document_type, gkd.kit_id::text AS kit_id, "
                "gc.name AS kit_name, e.nome AS employee_name, "
                "gkd.is_signed, gkd.source_module AS origin, gkd.created_at "
                "FROM ged_kit_documents gkd "
                "LEFT JOIN ged_document_kits dk ON dk.id = gkd.kit_id "
                "LEFT JOIN ged_clients gc ON gc.id = dk.client_id "
                "LEFT JOIN employees e ON e.id = gkd.employee_id::uuid "
                f"WHERE {' AND '.join(kit_cond)} "
                "ORDER BY gkd.created_at DESC LIMIT :lim"
            ),
            {**kit_p, "lim": limit},
        )
        for r in kit_result.mappings().all():
            items.append(
                {
                    "id": str(r["id"]),
                    "title": r["title"],
                    "name": r["title"],
                    "document_type": r["document_type"] or "—",
                    "kit_id": r["kit_id"],
                    "kit_name": r["kit_name"],
                    "employee_name": r["employee_name"],
                    "signed": bool(r["is_signed"]),
                    "status": None,
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    "category": None,
                    "origin": r["origin"],
                }
            )

    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    items = items[:limit]

    return {
        "total": len(items),
        "query": q,
        "items": items,
    }


@router.get("/{document_id:uuid}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentResponse:
    """Busca documento por ID."""
    service = DocumentService(db)
    document = await service.get_by_id(str(document_id))
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento não encontrado")
    return document


@router.get("/{document_id:uuid}/download")
async def download_file(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> FileResponse:
    """Faz download do arquivo do documento."""
    service = DocumentService(db)
    document = await service.get_by_id(str(document_id))
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento não encontrado")

    file_path = Path(document.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Arquivo não encontrado no sistema")

    # Registra o download
    await service.download(str(document_id))

    return FileResponse(
        path=str(file_path),
        filename=document.file_name,
        media_type=document.mime_type,
    )


