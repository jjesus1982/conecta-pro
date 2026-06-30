"""
Controller para Treinamento e Desenvolvimento.

Define endpoints REST para gestao de cursos, treinamentos/turmas,
matriculas e certificados.

Prefixo: /human-resources/training
"""

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.health_occupational.publishers import publish_treinamento_concluido
from modules.people_management.human_resources.models.training import (
    TrainingCategoryCourse,
    TrainingStatus,
)
from modules.people_management.human_resources.schemas.training import (
    TrainingCertificateResponse,
    TrainingCourseCreate,
    TrainingCourseListResponse,
    TrainingCourseResponse,
    TrainingCourseUpdate,
    TrainingCreate,
    TrainingEnrollmentCreate,
    TrainingEnrollmentListResponse,
    TrainingEnrollmentResponse,
    TrainingEnrollmentUpdate,
    TrainingListResponse,
    TrainingResponse,
    TrainingUpdate,
)
from modules.people_management.human_resources.services.training_service import TrainingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/training", tags=["RH - Treinamento"])


# =============================================================================
# Cursos
# =============================================================================


@router.post(
    "/courses",
    response_model=TrainingCourseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar curso de treinamento",
)
async def create_course(
    data: TrainingCourseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TrainingCourseResponse:
    """Cria um novo curso no catalogo de treinamentos."""
    service = TrainingService(db)
    try:
        course = await service.create_course(data)
        return TrainingCourseResponse.model_validate(course)
    except Exception as e:
        logger.error(f"Erro ao criar curso: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar curso de treinamento.",
        )


@router.get(
    "/courses",
    response_model=TrainingCourseListResponse,
    summary="Listar cursos de treinamento",
)
async def list_courses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: TrainingCategoryCourse | None = None,
    is_mandatory: bool | None = None,
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TrainingCourseListResponse:
    """Lista cursos com filtros e paginacao."""
    service = TrainingService(db)
    result = await service.list_courses(
        page=page,
        page_size=page_size,
        category=category.value if category else None,
        is_mandatory=is_mandatory,
        is_active=is_active,
    )
    return TrainingCourseListResponse(
        items=[TrainingCourseResponse.model_validate(c) for c in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get(
    "/courses/{course_id}",
    response_model=TrainingCourseResponse,
    summary="Buscar curso por ID",
)
async def get_course(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TrainingCourseResponse:
    """Busca um curso pelo identificador."""
    service = TrainingService(db)
    course = await service.get_course(course_id)
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Curso nao encontrado.",
        )
    return TrainingCourseResponse.model_validate(course)


@router.put(
    "/courses/{course_id}",
    response_model=TrainingCourseResponse,
    summary="Atualizar curso",
)
async def update_course(
    course_id: UUID,
    data: TrainingCourseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TrainingCourseResponse:
    """Atualiza os dados de um curso."""
    service = TrainingService(db)
    course = await service.update_course(course_id, data)
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Curso nao encontrado.",
        )
    return TrainingCourseResponse.model_validate(course)


@router.delete(
    "/courses/{course_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desativar curso",
)
async def delete_course(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> None:
    """Desativa um curso (soft delete)."""
    service = TrainingService(db)
    deleted = await service.delete_course(course_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Curso nao encontrado.",
        )


# =============================================================================
# Treinamentos/Turmas
# =============================================================================


@router.post(
    "/",
    response_model=TrainingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar treinamento/turma",
)
async def create_training(
    data: TrainingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TrainingResponse:
    """Cria uma nova turma de treinamento."""
    service = TrainingService(db)
    try:
        created_by_id = current_user.get("id") if isinstance(current_user, dict) else None
        training = await service.create_training(data, created_by_id=created_by_id)
        return TrainingResponse.model_validate(training)
    except Exception as e:
        logger.error(f"Erro ao criar treinamento: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar treinamento.",
        )


@router.get(
    "/",
    response_model=TrainingListResponse,
    summary="Listar treinamentos",
)
async def list_trainings(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    training_status: TrainingStatus | None = Query(None, alias="status"),
    course_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TrainingListResponse:
    """Lista treinamentos com filtros e paginacao."""
    service = TrainingService(db)
    result = await service.list_trainings(
        page=page,
        page_size=page_size,
        status=training_status.value if training_status else None,
        course_id=course_id,
    )
    return TrainingListResponse(
        items=[TrainingResponse.model_validate(t) for t in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


# =============================================================================
# Matriculas (Enrollments) — ANTES de /{training_id} para evitar conflito
# =============================================================================


@router.post(
    "/enrollments",
    response_model=TrainingEnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Matricular funcionario em treinamento",
)
async def enroll_employee(
    data: TrainingEnrollmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TrainingEnrollmentResponse:
    """Matricula um funcionario em um treinamento."""
    service = TrainingService(db)
    try:
        enrollment = await service.enroll_employee(data)
        return TrainingEnrollmentResponse.model_validate(enrollment)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/enrollments",
    response_model=TrainingEnrollmentListResponse,
    summary="Listar matriculas",
)
async def list_enrollments(
    training_id: UUID | None = None,
    employee_id: UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TrainingEnrollmentListResponse:
    """Lista matriculas com filtros."""
    service = TrainingService(db)
    result = await service.list_enrollments(
        training_id=training_id,
        employee_id=employee_id,
        page=page,
        page_size=page_size,
    )
    return TrainingEnrollmentListResponse(
        items=[TrainingEnrollmentResponse.model_validate(e) for e in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


# IMPORTANTE: rota literal /certificates DEVE vir antes de /{training_id},
# senão "certificates" é interpretado como UUID e dá 422 (a tela rh/certificados ficava vazia).
@router.get("/certificates", summary="Listar certificados de treinamento")
@router.get("/certificates/", include_in_schema=False)
async def list_certificates(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict:
    """Lista certificados emitidos (com nome do colaborador e do curso)."""
    total = (await db.execute(text("SELECT count(*) FROM training_certificates"))).scalar() or 0
    rows = await db.execute(
        text(
            "SELECT tc.id::text AS id, tc.certificate_number, tc.employee_id::text AS employee_id, "
            "tc.course_id::text AS course_id, e.nome AS employee_name, c.name AS course_name, "
            "tc.issued_at, tc.expires_at, tc.status "
            "FROM training_certificates tc "
            "LEFT JOIN employees e ON tc.employee_id = e.id "
            "LEFT JOIN training_courses c ON tc.course_id = c.id "
            "ORDER BY tc.issued_at DESC NULLS LAST LIMIT :limit OFFSET :offset"
        ),
        {"limit": page_size, "offset": (page - 1) * page_size},
    )
    items = [dict(r) for r in rows.mappings().all()]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get(
    "/{training_id}",
    response_model=TrainingResponse,
    summary="Buscar treinamento por ID",
)
async def get_training(
    training_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TrainingResponse:
    """Busca um treinamento pelo identificador."""
    service = TrainingService(db)
    training = await service.get_training(training_id)
    if not training:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Treinamento nao encontrado.",
        )
    return TrainingResponse.model_validate(training)


@router.put(
    "/{training_id}",
    response_model=TrainingResponse,
    summary="Atualizar treinamento",
)
async def update_training(
    training_id: UUID,
    data: TrainingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TrainingResponse:
    """Atualiza os dados de um treinamento."""
    service = TrainingService(db)
    training = await service.update_training(training_id, data)
    if not training:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Treinamento nao encontrado.",
        )
    return TrainingResponse.model_validate(training)


@router.post(
    "/{training_id}/complete", response_model=TrainingResponse, summary="Concluir treinamento", status_code=201
)
async def complete_training(
    training_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TrainingResponse:
    """Marca um treinamento como concluido e atualiza matriculas."""
    service = TrainingService(db)
    training = await service.complete_training(training_id)
    if not training:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Treinamento nao encontrado.",
        )
    asyncio.create_task(
        publish_treinamento_concluido(
            treinamento_id=str(training_id),
            funcionario_id=str(getattr(training, "employee_id", "")),
            funcionario_nome=str(getattr(training, "employee_name", "")),
            titulo=str(getattr(training, "title", "") or getattr(training, "name", "")),
            carga_horaria=float(getattr(training, "workload", 0) or 0),
            data_conclusao=str(getattr(training, "end_date", "") or ""),
        )
    )
    return TrainingResponse.model_validate(training)


@router.put(
    "/enrollments/{enrollment_id}",
    response_model=TrainingEnrollmentResponse,
    summary="Atualizar matricula",
)
async def update_enrollment(
    enrollment_id: UUID,
    data: TrainingEnrollmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TrainingEnrollmentResponse:
    """Atualiza o status ou dados de uma matricula."""
    service = TrainingService(db)
    enrollment = await service.update_enrollment(enrollment_id, data)
    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matricula nao encontrada.",
        )
    return TrainingEnrollmentResponse.model_validate(enrollment)


# =============================================================================
# Certificados
# =============================================================================


@router.post(
    "/enrollments/{enrollment_id}/certificate",
    response_model=TrainingCertificateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Emitir certificado",
)
async def issue_certificate(
    enrollment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TrainingCertificateResponse:
    """Emite um certificado para uma matricula concluida."""
    service = TrainingService(db)
    try:
        certificate = await service.issue_certificate(enrollment_id)
        return TrainingCertificateResponse.model_validate(certificate)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/certificates/expiring",
    response_model=list[TrainingCertificateResponse],
    summary="Certificados proximos do vencimento",
)
async def get_expiring_certificates(
    days_ahead: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[TrainingCertificateResponse]:
    """Lista certificados que vencerao nos proximos N dias."""
    service = TrainingService(db)
    certificates = await service.get_expiring_certificates(days_ahead=days_ahead)
    return [TrainingCertificateResponse.model_validate(c) for c in certificates]


@router.get(
    "/mandatory-check/{employee_id}",
    summary="Verificar treinamentos obrigatorios",
)
async def check_mandatory_trainings(
    employee_id: UUID,
    workplace_type: str = Query(..., description="Tipo de posto de trabalho"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Verifica treinamentos obrigatorios de um funcionario para um tipo de posto."""
    service = TrainingService(db)
    return await service.check_mandatory_for_workplace(employee_id, workplace_type)
