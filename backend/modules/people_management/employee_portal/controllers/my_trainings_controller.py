"""
My Trainings Controller — Consulta de treinamentos do funcionario.

Endpoints:
- GET /portal/my-trainings/enrollments
- GET /portal/my-trainings/certificates
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict


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


