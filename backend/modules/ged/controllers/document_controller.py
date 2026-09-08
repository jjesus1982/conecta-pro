"""Controller para Document."""

import hashlib
import logging
from pathlib import Path
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
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


