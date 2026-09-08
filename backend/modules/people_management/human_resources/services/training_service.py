"""
Service para Treinamento e Desenvolvimento.

Implementa logica de negocio para gestao completa de treinamentos:
- CRUD de cursos, turmas, matriculas e certificados
- Matricula de funcionarios em treinamentos
- Conclusao de treinamento e registro de presenca
- Emissao e controle de certificados
- Verificacao de treinamentos obrigatorios por posto
- Monitoramento de certificados a vencer
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.people_management.human_resources.models.training import (
    CertificateStatus,
    EnrollmentStatus,
    Training,
    TrainingCertificate,
    TrainingCourse,
    TrainingEnrollment,
    TrainingStatus,
)
from modules.people_management.human_resources.schemas.training import (
    TrainingCourseCreate,
    TrainingCourseUpdate,
    TrainingCreate,
    TrainingEnrollmentCreate,
    TrainingEnrollmentUpdate,
    TrainingUpdate,
)

logger = logging.getLogger(__name__)


class TrainingService:
    """Service para operacoes de treinamento e desenvolvimento."""

    def __init__(self, session: AsyncSession) -> None:
        """Inicializa o service."""
        self.session = session

    # CRUD - Cursos

    async def create_course(self, data: TrainingCourseCreate) -> TrainingCourse:
        """Cria um novo curso de treinamento."""
        course = TrainingCourse(
            id=uuid.uuid4(),
            **data.model_dump(),
        )
        self.session.add(course)
        await self.session.commit()
        await self.session.refresh(course)
        logger.info(f"Curso criado: {course.name} (ID: {course.id})")
        return course

    async def get_course(self, course_id: uuid.UUID) -> TrainingCourse | None:
        """Busca um curso por ID."""
        result = await self.session.execute(select(TrainingCourse).where(TrainingCourse.id == course_id))
        return result.scalar_one_or_none()

    async def list_courses(
        self,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
        is_mandatory: bool | None = None,
        is_active: bool | None = None,
    ) -> dict[str, Any]:
        """Lista cursos com filtros e paginacao."""
        query = select(TrainingCourse)
        count_query = select(func.count(TrainingCourse.id))

        if category:
            query = query.where(TrainingCourse.category == category)
            count_query = count_query.where(TrainingCourse.category == category)
        if is_mandatory is not None:
            query = query.where(TrainingCourse.is_mandatory == is_mandatory)
            count_query = count_query.where(TrainingCourse.is_mandatory == is_mandatory)
        if is_active is not None:
            query = query.where(TrainingCourse.is_active == is_active)
            count_query = count_query.where(TrainingCourse.is_active == is_active)

        total = (await self.session.execute(count_query)).scalar() or 0
        offset = (page - 1) * page_size
        query = query.order_by(TrainingCourse.name).offset(offset).limit(page_size)
        result = await self.session.execute(query)
        items = list(result.scalars().all())

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    async def update_course(self, course_id: uuid.UUID, data: TrainingCourseUpdate) -> TrainingCourse | None:
        """Atualiza um curso de treinamento."""
        course = await self.get_course(course_id)
        if not course:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(course, field, value)

        await self.session.commit()
        await self.session.refresh(course)
        logger.info(f"Curso atualizado: {course.name} (ID: {course.id})")
        return course

    async def delete_course(self, course_id: uuid.UUID) -> bool:
        """Remove um curso (soft delete via is_active=False)."""
        course = await self.get_course(course_id)
        if not course:
            return False

        course.is_active = False
        await self.session.commit()
        logger.info(f"Curso desativado: {course.name} (ID: {course.id})")
        return True

    # CRUD - Treinamentos/Turmas

    async def create_training(self, data: TrainingCreate, created_by_id: uuid.UUID | None = None) -> Training:
        """Cria uma nova turma de treinamento."""
        training = Training(
            id=uuid.uuid4(),
            created_by_id=created_by_id,
            **data.model_dump(),
        )
        self.session.add(training)
        await self.session.commit()
        await self.session.refresh(training)
        logger.info(f"Treinamento criado: {training.title} (ID: {training.id})")
        return training

    async def get_training(self, training_id: uuid.UUID) -> Training | None:
        """Busca um treinamento por ID."""
        result = await self.session.execute(select(Training).where(Training.id == training_id))
        return result.scalar_one_or_none()

    async def list_trainings(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        course_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Lista treinamentos com filtros e paginacao."""
        query = select(Training)
        count_query = select(func.count(Training.id))

        if status:
            query = query.where(Training.status == status)
            count_query = count_query.where(Training.status == status)
        if course_id:
            query = query.where(Training.course_id == course_id)
            count_query = count_query.where(Training.course_id == course_id)

        total = (await self.session.execute(count_query)).scalar() or 0
        offset = (page - 1) * page_size
        query = query.order_by(Training.start_date.desc()).offset(offset).limit(page_size)
        result = await self.session.execute(query)
        items = list(result.scalars().all())

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    async def update_training(self, training_id: uuid.UUID, data: TrainingUpdate) -> Training | None:
        """Atualiza um treinamento."""
        training = await self.get_training(training_id)
        if not training:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(training, field, value)

        await self.session.commit()
        await self.session.refresh(training)
        logger.info(f"Treinamento atualizado: {training.title} (ID: {training.id})")
        return training

    async def complete_training(self, training_id: uuid.UUID) -> Training | None:
        """Marca um treinamento como concluido.

        Atualiza o status da turma e marca todos os enrollments confirmados
        como 'attended'. Enrollments nao confirmados sao marcados como 'absent'.
        """
        training = await self.get_training(training_id)
        if not training:
            return None

        training.status = TrainingStatus.COMPLETED
        now = datetime.now(UTC)

        # Marcar confirmados como presentes
        await self.session.execute(
            update(TrainingEnrollment)
            .where(
                and_(
                    TrainingEnrollment.training_id == training_id,
                    TrainingEnrollment.status == EnrollmentStatus.CONFIRMED,
                )
            )
            .values(status=EnrollmentStatus.ATTENDED, attended_at=now)
        )

        # Marcar nao-confirmados como ausentes
        await self.session.execute(
            update(TrainingEnrollment)
            .where(
                and_(
                    TrainingEnrollment.training_id == training_id,
                    TrainingEnrollment.status == EnrollmentStatus.ENROLLED,
                )
            )
            .values(status=EnrollmentStatus.ABSENT)
        )

        await self.session.commit()
        await self.session.refresh(training)
        logger.info(f"Treinamento concluido: {training.title} (ID: {training.id})")
        return training

    # Matriculas

    async def enroll_employee(self, data: TrainingEnrollmentCreate) -> TrainingEnrollment:
        """Matricula um funcionario em um treinamento.

        Verifica se ha vagas disponiveis e se o funcionario ja nao esta matriculado.
        """
        training = await self.get_training(data.training_id)
        if not training:
            raise ValueError(f"Treinamento {data.training_id} nao encontrado.")

        if not training.has_available_slots:
            raise ValueError("Treinamento sem vagas disponiveis.")

        if not training.is_active:
            raise ValueError("Treinamento nao esta ativo para matriculas.")

        # Verificar matricula duplicada
        existing = await self.session.execute(
            select(TrainingEnrollment).where(
                and_(
                    TrainingEnrollment.training_id == data.training_id,
                    TrainingEnrollment.employee_id == data.employee_id,
                    TrainingEnrollment.status.notin_([EnrollmentStatus.CANCELLED]),
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Funcionario ja matriculado neste treinamento.")

        enrollment = TrainingEnrollment(
            id=uuid.uuid4(),
            training_id=data.training_id,
            employee_id=data.employee_id,
            status=EnrollmentStatus.ENROLLED,
        )
        self.session.add(enrollment)

        # Atualizar contador
        training.current_participants += 1

        await self.session.commit()
        await self.session.refresh(enrollment)
        logger.info(f"Funcionario {data.employee_id} matriculado no treinamento {data.training_id}")
        return enrollment

    async def update_enrollment(
        self, enrollment_id: uuid.UUID, data: TrainingEnrollmentUpdate
    ) -> TrainingEnrollment | None:
        """Atualiza uma matricula."""
        result = await self.session.execute(select(TrainingEnrollment).where(TrainingEnrollment.id == enrollment_id))
        enrollment = result.scalar_one_or_none()
        if not enrollment:
            return None

        update_data = data.model_dump(exclude_unset=True)
        now = datetime.now(UTC)

        for field, value in update_data.items():
            setattr(enrollment, field, value)

        # Auto-preencher datas de transicao
        if data.status == EnrollmentStatus.CONFIRMED and not enrollment.confirmed_at:
            enrollment.confirmed_at = now
        elif data.status == EnrollmentStatus.ATTENDED and not enrollment.attended_at:
            enrollment.attended_at = now

        await self.session.commit()
        await self.session.refresh(enrollment)
        return enrollment

    async def list_enrollments(
        self,
        training_id: uuid.UUID | None = None,
        employee_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Lista matriculas com filtros."""
        query = select(TrainingEnrollment)
        count_query = select(func.count(TrainingEnrollment.id))

        if training_id:
            query = query.where(TrainingEnrollment.training_id == training_id)
            count_query = count_query.where(TrainingEnrollment.training_id == training_id)
        if employee_id:
            query = query.where(TrainingEnrollment.employee_id == employee_id)
            count_query = count_query.where(TrainingEnrollment.employee_id == employee_id)

        total = (await self.session.execute(count_query)).scalar() or 0
        offset = (page - 1) * page_size
        query = query.order_by(TrainingEnrollment.enrolled_at.desc()).offset(offset).limit(page_size)
        result = await self.session.execute(query)
        items = list(result.scalars().all())

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    # Certificados

    async def issue_certificate(self, enrollment_id: uuid.UUID) -> TrainingCertificate:
        """Emite um certificado para uma matricula concluida.

        Gera numero unico de certificado e calcula data de validade
        baseado no curso.
        """
        result = await self.session.execute(select(TrainingEnrollment).where(TrainingEnrollment.id == enrollment_id))
        enrollment = result.scalar_one_or_none()
        if not enrollment:
            raise ValueError(f"Matricula {enrollment_id} nao encontrada.")

        if enrollment.status != EnrollmentStatus.ATTENDED:
            raise ValueError("Certificado so pode ser emitido para matriculas com presenca confirmada.")

        # Buscar curso para validade
        training = await self.get_training(enrollment.training_id)
        if not training:
            raise ValueError("Treinamento nao encontrado.")

        course_result = await self.session.execute(
            select(TrainingCourse).where(TrainingCourse.id == training.course_id)
        )
        course = course_result.scalar_one_or_none()

        # Calcular validade
        now = datetime.now(UTC)
        expires_at = None
        if course and course.validity_months:
            expires_at = now + timedelta(days=course.validity_months * 30)

        # Gerar numero do certificado
        cert_number = f"CERT-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

        certificate = TrainingCertificate(
            id=uuid.uuid4(),
            enrollment_id=enrollment_id,
            employee_id=enrollment.employee_id,
            course_id=training.course_id,
            certificate_number=cert_number,
            issued_at=now,
            expires_at=expires_at,
            status=CertificateStatus.VALID,
        )
        self.session.add(certificate)

        # Vincular ao enrollment
        enrollment.certificate_id = certificate.id

        await self.session.commit()
        await self.session.refresh(certificate)
        logger.info(f"Certificado emitido: {cert_number} para funcionario {enrollment.employee_id}")
        return certificate

    async def get_expiring_certificates(self, days_ahead: int = 30) -> list[TrainingCertificate]:
        """Busca certificados proximos do vencimento."""
        now = datetime.now(UTC)
        limit_date = now + timedelta(days=days_ahead)

        result = await self.session.execute(
            select(TrainingCertificate)
            .where(
                and_(
                    TrainingCertificate.status == CertificateStatus.VALID,
                    TrainingCertificate.expires_at.isnot(None),
                    TrainingCertificate.expires_at <= limit_date,
                    TrainingCertificate.expires_at > now,
                )
            )
            .order_by(TrainingCertificate.expires_at)
        )
        return list(result.scalars().all())

    async def check_mandatory_for_workplace(self, employee_id: uuid.UUID, workplace_type: str) -> dict[str, Any]:
        """Verifica treinamentos obrigatorios de um funcionario para tipo de posto.

        Retorna quais cursos obrigatorios o funcionario ja completou
        e quais estao pendentes.
        """
        # Buscar cursos obrigatorios para o tipo de posto
        result = await self.session.execute(
            select(TrainingCourse).where(
                and_(
                    TrainingCourse.is_mandatory.is_(True),
                    TrainingCourse.is_active.is_(True),
                )
            )
        )
        mandatory_courses = list(result.scalars().all())

        # Filtrar por tipo de posto
        relevant_courses = []
        for course in mandatory_courses:
            workplace_types = course.required_for_workplace_types or []
            if not workplace_types or workplace_type in workplace_types:
                relevant_courses.append(course)

        # Buscar certificados validos do funcionario
        now = datetime.now(UTC)
        cert_result = await self.session.execute(
            select(TrainingCertificate).where(
                and_(
                    TrainingCertificate.employee_id == employee_id,
                    TrainingCertificate.status == CertificateStatus.VALID,
                    or_(
                        TrainingCertificate.expires_at.is_(None),
                        TrainingCertificate.expires_at > now,
                    ),
                )
            )
        )
        valid_certs = list(cert_result.scalars().all())
        certified_course_ids = {cert.course_id for cert in valid_certs}

        completed = []
        pending = []
        for course in relevant_courses:
            if course.id in certified_course_ids:
                completed.append(
                    {
                        "course_id": str(course.id),
                        "name": course.name,
                        "status": "completed",
                    }
                )
            else:
                pending.append(
                    {
                        "course_id": str(course.id),
                        "name": course.name,
                        "status": "pending",
                        "category": course.category.value,
                    }
                )

        return {
            "employee_id": str(employee_id),
            "workplace_type": workplace_type,
            "total_mandatory": len(relevant_courses),
            "completed_count": len(completed),
            "pending_count": len(pending),
            "is_compliant": len(pending) == 0,
            "completed": completed,
            "pending": pending,
        }
