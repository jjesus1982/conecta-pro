"""
My Trainings Controller — Consulta de treinamentos do funcionario.

Endpoints:
- GET /portal/my-trainings/enrollments
- GET /portal/my-trainings/certificates
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.people_management.employee_portal.auth import CurrentEmployeeId

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Treinamentos"])


class TrainingEnrollmentResponse(BaseModel):
    """Matricula em treinamento do funcionario."""

    id: str | None = None
    training_title: str | None = None
    course_name: str | None = None
    status: str | None = None
    enrolled_at: str | None = None

    model_config = ConfigDict(from_attributes=True)


class TrainingCertificateResponse(BaseModel):
    """Certificado de treinamento do funcionario."""

    id: str | None = None
    certificate_number: str | None = None
    course_name: str | None = None
    issued_at: str | None = None
    expires_at: str | None = None
    status: str | None = None

    model_config = ConfigDict(from_attributes=True)


@router.get(
    "/my-trainings/enrollments",
    response_model=list[TrainingEnrollmentResponse],
    summary="Minhas matriculas em treinamentos",
    description="Retorna lista de matriculas em treinamentos do funcionario.",
)
async def get_my_enrollments(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna matriculas em treinamentos do funcionario autenticado."""
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from modules.people_management.human_resources.models.training import (
            Training,
            TrainingEnrollment,
        )

        result = await db.execute(
            select(TrainingEnrollment)
            .where(TrainingEnrollment.employee_id == str(employee_id))
            .options(
                selectinload(TrainingEnrollment.training).selectinload(Training.course),
            )
        )
        enrollments = result.scalars().all()

        items = []
        for enrollment in enrollments:
            training = getattr(enrollment, "training", None)
            course = getattr(training, "course", None) if training else None

            items.append(
                TrainingEnrollmentResponse(
                    id=str(enrollment.id),
                    training_title=getattr(training, "title", None) if training else None,
                    course_name=getattr(course, "name", None) if course else None,
                    status=str(enrollment.status.value) if enrollment.status else None,
                    enrolled_at=str(enrollment.enrolled_at) if enrollment.enrolled_at else None,
                )
            )

        return items

    except (ImportError, Exception) as e:
        logger.warning(f"Erro ao buscar matriculas do funcionario {employee_id}: {e}")

    return []


@router.get(
    "/my-trainings/certificates",
    response_model=list[TrainingCertificateResponse],
    summary="Meus certificados de treinamento",
    description="Retorna lista de certificados de treinamento do funcionario.",
)
async def get_my_certificates(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna certificados de treinamento do funcionario autenticado."""
    try:
        from sqlalchemy import select

        from modules.people_management.human_resources.models.training import (
            TrainingCertificate,
            TrainingCourse,
        )

        result = await db.execute(
            select(TrainingCertificate).where(TrainingCertificate.employee_id == str(employee_id))
        )
        certificates = result.scalars().all()

        items = []
        for cert in certificates:
            # Tentar buscar nome do curso
            course_name = None
            try:
                course_result = await db.execute(select(TrainingCourse).where(TrainingCourse.id == cert.course_id))
                course = course_result.scalar_one_or_none()
                if course:
                    course_name = course.name
            except Exception:
                pass

            items.append(
                TrainingCertificateResponse(
                    id=str(cert.id),
                    certificate_number=cert.certificate_number,
                    course_name=course_name,
                    issued_at=str(cert.issued_at) if cert.issued_at else None,
                    expires_at=str(cert.expires_at) if cert.expires_at else None,
                    status=str(cert.status.value) if cert.status else None,
                )
            )

        return items

    except (ImportError, Exception) as e:
        logger.warning(f"Erro ao buscar certificados do funcionario {employee_id}: {e}")

    return []
