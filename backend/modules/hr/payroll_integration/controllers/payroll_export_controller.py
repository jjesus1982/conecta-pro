"""Controller para exportação de folha de pagamento."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user, require_permissions
from core.database import get_db
from modules.hr.payroll_integration.models import ExportFormat, ExportStatus
from modules.hr.payroll_integration.schemas import (
    ExportDownloadResponse,
    ExportProgressResponse,
    PayrollExportCreate,
    PayrollExportListResponse,
    PayrollExportResponse,
)
from modules.hr.payroll_integration.services import PayrollExportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/exports", tags=["Payroll Exports"])




def _uget(user, key, default=None):
    """Acessa campo do usuário seja objeto User (get_current_user) ou dict — os endpoints
    usavam current_user['x'], que crashava no User ('User' object is not subscriptable)."""
    if isinstance(user, dict):
        return user.get(key, default)
    return getattr(user, key, default)
@router.post(
    "/",
    response_model=PayrollExportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar exportação",
)
async def create_export(
    data: PayrollExportCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PayrollExportResponse:
    """Cria uma nova exportação de folha."""
    try:
        service = PayrollExportService(db)
        export = await service.create_export(
            data=data,
            condominio_id=_uget(current_user, "condominio_id"),
            user_id=_uget(current_user, "id"),
        )
        logger.info(
            "Exportação criada: %s por %s",
            export.export_code,
            _uget(current_user, "email"),
        )
        return PayrollExportResponse.model_validate(export)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Erro ao criar exportação: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar exportação",
        )


@router.get(
    "/",
    response_model=PayrollExportListResponse,
    summary="Listar exportações",
)
async def list_exports(
    period_id: UUID | None = Query(None, description="Filtrar por período"),
    export_format: ExportFormat | None = Query(None, description="Formato"),
    status_filter: ExportStatus | None = Query(
        None,
        alias="status",
        description="Status",
    ),
    page: int = Query(1, ge=1, description="Página"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por página"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PayrollExportListResponse:
    """Lista exportações com filtros."""
    try:
        service = PayrollExportService(db)
        exports, total = await service.list_exports(
            condominio_id=_uget(current_user, "condominio_id"),
            period_id=period_id,
            export_format=export_format,
            status=status_filter,
            page=page,
            page_size=page_size,
        )
        return PayrollExportListResponse(
            items=[PayrollExportResponse.model_validate(e) for e in exports],
            total=total,
            page=page,
            page_size=page_size,
            pages=(total + page_size - 1) // page_size,
        )
    except Exception as e:
        logger.error("Erro ao listar exportações: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao listar exportações",
        )


@router.get(
    "/{export_id}",
    response_model=PayrollExportResponse,
    summary="Buscar exportação",
)
async def get_export(
    export_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),  # pylint: disable=unused-argument
) -> PayrollExportResponse:
    """Busca exportação por ID."""
    try:
        service = PayrollExportService(db)
        export = await service.get_export(export_id)
        if not export:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Exportação não encontrada",
            )
        return PayrollExportResponse.model_validate(export)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao buscar exportação %s: %s", export_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao buscar exportação",
        )


@router.post(
    "/{export_id}/process",
    response_model=PayrollExportResponse,
    summary="Processar exportação",
)
async def process_export(
    export_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PayrollExportResponse:
    """Processa e gera arquivo de exportação."""
    try:
        service = PayrollExportService(db)
        export = await service.process_export(
            export_id=export_id,
            condominio_id=_uget(current_user, "condominio_id"),
        )
        logger.info(
            "Exportação processada: %s por %s",
            export.export_code,
            _uget(current_user, "email"),
        )
        return PayrollExportResponse.model_validate(export)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Erro ao processar exportação %s: %s", export_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao processar exportação",
        )


@router.get(
    "/{export_id}/progress",
    response_model=ExportProgressResponse,
    summary="Progresso da exportação",
)
async def get_export_progress(
    export_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),  # pylint: disable=unused-argument
) -> ExportProgressResponse:
    """Retorna progresso da exportação."""
    try:
        service = PayrollExportService(db)
        progress = await service.get_progress(export_id)
        return progress
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("Erro ao buscar progresso: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao buscar progresso",
        )


@router.get(
    "/{export_id}/download-info",
    response_model=ExportDownloadResponse,
    summary="Info para download",
)
async def get_download_info(
    export_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ExportDownloadResponse:
    """Retorna informações para download do arquivo."""
    try:
        service = PayrollExportService(db)
        download_info = await service.get_download_info(export_id)
        logger.info(
            "Download info: %s por %s",
            export_id,
            _uget(current_user, "email"),
        )
        return download_info
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Erro ao buscar info download: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao buscar informações",
        )


@router.get(
    "/{export_id}/file",
    summary="Download do arquivo",
)
async def download_file(
    export_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> StreamingResponse:
    """Faz download do arquivo de exportação."""
    try:
        service = PayrollExportService(db)
        download_info = await service.get_download_info(export_id)

        # Em produção, buscaria o arquivo do storage
        # Por hora, retorna conteúdo de exemplo
        content = b"Export file content placeholder"

        logger.info(
            "Download arquivo: %s por %s",
            export_id,
            _uget(current_user, "email"),
        )

        return StreamingResponse(
            iter([content]),
            media_type=download_info.content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{download_info.file_name}"',
                "Content-Length": str(len(content)),
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Erro ao fazer download: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao fazer download",
        )


@router.post(
    "/{export_id}/retry",
    response_model=PayrollExportResponse,
    summary="Retentar exportação",
)
async def retry_export(
    export_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PayrollExportResponse:
    """Retenta exportação que falhou."""
    try:
        service = PayrollExportService(db)
        export = await service.retry_export(export_id)
        logger.info(
            "Exportação retentada: %s por %s",
            export.export_code,
            _uget(current_user, "email"),
        )
        return PayrollExportResponse.model_validate(export)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Erro ao retentar exportação %s: %s", export_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao retentar exportação",
        )


@router.post(
    "/{export_id}/cancel",
    response_model=PayrollExportResponse,
    summary="Cancelar exportação",
)
async def cancel_export(
    export_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PayrollExportResponse:
    """Cancela exportação em andamento."""
    try:
        service = PayrollExportService(db)
        export = await service.cancel_export(export_id)
        logger.info(
            "Exportação cancelada: %s por %s",
            export.export_code,
            _uget(current_user, "email"),
        )
        return PayrollExportResponse.model_validate(export)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Erro ao cancelar exportação %s: %s", export_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao cancelar exportação",
        )


@router.post(
    "/process-pending",
    response_model=dict,
    summary="Processar pendentes",
)
async def process_pending_exports(
    limit: int = Query(10, ge=1, le=50, description="Limite de exportações"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_permissions(["payroll:export"])),
) -> dict:
    """Processa exportações pendentes em fila."""
    try:
        service = PayrollExportService(db)
        result = await service.process_pending_exports(
            condominio_id=_uget(current_user, "condominio_id"),
            limit=limit,
        )
        logger.info(
            "Processadas %d exportações pendentes por %s",
            result["processed"],
            _uget(current_user, "email"),
        )
        return result
    except Exception as e:
        logger.error("Erro ao processar pendentes: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao processar pendentes",
        )


@router.get(
    "/formats/available",
    response_model=list,
    summary="Formatos disponíveis",
)
async def get_available_formats(
    current_user=Depends(get_current_user),  # pylint: disable=unused-argument
) -> list:
    """Retorna formatos de exportação disponíveis."""
    return [
        {
            "code": fmt.value,
            "name": fmt.name,
            "description": _get_format_description(fmt),
            "extension": _get_format_extension(fmt),
        }
        for fmt in ExportFormat
    ]


def _get_format_description(fmt: ExportFormat) -> str:
    """Retorna descrição do formato."""
    descriptions = {
        ExportFormat.CSV: "Arquivo CSV com separador configurável",
        ExportFormat.JSON: "Arquivo JSON estruturado",
        ExportFormat.TXT: "Arquivo texto posicional",
        ExportFormat.XLSX: "Planilha Excel",
        ExportFormat.XML: "Arquivo XML genérico",
        ExportFormat.CNAB240: "Arquivo bancário CNAB 240",
        ExportFormat.CNAB400: "Arquivo bancário CNAB 400",
        ExportFormat.ESOCIAL_XML: "XML para eSocial",
        ExportFormat.SEFIP: "Arquivo para SEFIP/GFIP",
        ExportFormat.CAGED: "Arquivo para CAGED",
        ExportFormat.RAIS: "Arquivo para RAIS",
        ExportFormat.DIRF: "Arquivo para DIRF",
    }
    return descriptions.get(fmt, "")


def _get_format_extension(fmt: ExportFormat) -> str:
    """Retorna extensão do arquivo."""
    extensions = {
        ExportFormat.CSV: ".csv",
        ExportFormat.JSON: ".json",
        ExportFormat.TXT: ".txt",
        ExportFormat.XLSX: ".xlsx",
        ExportFormat.XML: ".xml",
        ExportFormat.CNAB240: ".rem",
        ExportFormat.CNAB400: ".rem",
        ExportFormat.ESOCIAL_XML: ".xml",
        ExportFormat.SEFIP: ".re",
        ExportFormat.CAGED: ".txt",
        ExportFormat.RAIS: ".txt",
        ExportFormat.DIRF: ".txt",
    }
    return extensions.get(fmt, ".bin")
