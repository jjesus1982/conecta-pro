"""Controller para endpoints de Diaristas."""

import asyncio
import logging
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user, require_roles
from core.database import get_db
from modules.operacional.diaristas.models.diarist import (
    AssignmentStatus,
    DiaristStatus,
    DiaristType,
    PaymentStatus,
    ScheduleStatus,
)
from modules.operacional.diaristas.schemas.diarist_schemas import (
    BatchScheduleCreate,
    BatchScheduleResponse,
    CheckinRequest,
    CheckoutRequest,
    DiaristAssignmentCreate,
    DiaristAssignmentResponse,
    DiaristAvailabilityResponse,
    DiaristCreate,
    DiaristEvaluationCreate,
    DiaristEvaluationResponse,
    DiaristListResponse,
    DiaristPaymentCreate,
    DiaristPaymentResponse,
    DiaristPerformanceResponse,
    DiaristResponse,
    DiaristScheduleCreate,
    DiaristScheduleResponse,
    DiaristSuggestionResponse,
    DiaristUpdate,
    PayrollGenerateRequest,
    PayrollReportResponse,
    ScheduleOptimizationResponse,
)
from modules.operacional.diaristas.services.diarist_ai_service import DiaristAIService
from modules.operacional.diaristas.services.diarist_service import DiaristService
from modules.operacional.publishers import (
    publish_diarista_checkin,
    publish_diarista_checkout,
    publish_diarista_criada,
    publish_diarista_pagamento,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diaristas", tags=["Diaristas"])


def get_diarist_service(db: Session = Depends(get_db)) -> DiaristService:
    """Dependency para DiaristService."""
    return DiaristService(db)


def get_ai_service(db: Session = Depends(get_db)) -> DiaristAIService:
    """Dependency para DiaristAIService."""
    return DiaristAIService(db)


# ==================== CONSULTA CPF ====================


@router.get("/consulta-cpf/{cpf}")
async def consulta_cpf(
    cpf: str,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Consulta dados pelo CPF: primeiro na base interna, depois API externa."""
    import httpx
    from sqlalchemy import text

    cpf_limpo = cpf.replace(".", "").replace("-", "").replace(" ", "")

    if len(cpf_limpo) != 11 or not cpf_limpo.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CPF invalido",
        )

    # 1. Buscar na base interna (employees)
    try:
        result = await db.execute(
            text("SELECT nome, email, telefone, data_nascimento FROM employees WHERE cpf = :cpf LIMIT 1"),
            {"cpf": cpf_limpo},
        )
        row = result.fetchone()
        if row:
            return {
                "found": True,
                "source": "interno",
                "nome": row[0] or "",
                "email": row[1] or "",
                "telefone": row[2] or "",
                "data_nascimento": str(row[3]) if row[3] else "",
            }
    except Exception as e:
        logger.warning(f"Erro ao buscar employee por CPF: {e}")

    # 2. Buscar na base interna (diarists - evitar duplicata)
    try:
        result = await db.execute(
            text("SELECT nome, email, telefone FROM diarists WHERE cpf = :cpf LIMIT 1"),
            {"cpf": cpf_limpo},
        )
        row = result.fetchone()
        if row:
            return {
                "found": True,
                "source": "diarista_existente",
                "nome": row[0] or "",
                "email": row[1] or "",
                "telefone": row[2] or "",
                "data_nascimento": "",
                "aviso": "CPF ja cadastrado como diarista",
            }
    except Exception as e:
        logger.warning(f"Erro ao buscar diarist por CPF: {e}")

    # 3. Tentar API externa (BrasilAPI)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"https://brasilapi.com.br/api/cpf/v1/{cpf_limpo}")
            if response.status_code == 200:
                data = response.json()
                return {
                    "found": True,
                    "source": "receita",
                    "nome": data.get("nome", ""),
                    "data_nascimento": data.get("data_nascimento", ""),
                    "situacao": data.get("situacao", ""),
                }
    except Exception as e:
        logger.warning(f"Erro ao consultar API externa: {e}")

    return {"found": False, "nome": "", "message": "CPF nao encontrado"}


# ==================== DIARIST ENDPOINTS (rotas literais primeiro) ====================


@router.post(
    "/",
    response_model=DiaristResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin", "sindico"))],
)
async def create_diarist(
    data: DiaristCreate,
    service: DiaristService = Depends(get_diarist_service),
) -> DiaristResponse:
    """Cria uma nova diarista."""
    try:
        diarist = await service.create_diarist(data)
        asyncio.create_task(
            publish_diarista_criada(
                diarist_id=str(diarist.id),
                nome=str(getattr(diarist, "nome", "") or getattr(diarist, "name", "")),
            )
        )
        return DiaristResponse.model_validate(diarist)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("", response_model=DiaristListResponse)
@router.get(
    "/", response_model=DiaristListResponse, include_in_schema=False
)  # espelho barra-final (redirect_slashes=False)
async def list_diarists(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status_filter: DiaristStatus | None = Query(None, alias="status"),
    tipo: DiaristType | None = None,
    search: str | None = None,
    service: DiaristService = Depends(get_diarist_service),
    _: dict = Depends(get_current_user),
) -> DiaristListResponse:
    """Lista diaristas com filtros."""
    diarists = await service.list_diarists(
        skip=skip,
        limit=limit,
        status=status_filter,
        tipo=tipo,
        search=search,
    )
    total = len(diarists)
    page = (skip // limit) + 1 if limit > 0 else 1
    page_size = limit
    pages = max(1, (total + limit - 1) // limit) if limit > 0 else 1

    return DiaristListResponse(
        items=[DiaristResponse.model_validate(d) for d in diarists],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/available")
async def get_available_diarists(
    data: date,
    tipo: DiaristType | None = None,
    service: DiaristService = Depends(get_diarist_service),
    _: dict = Depends(get_current_user),
) -> list[DiaristResponse]:
    """Busca diaristas disponíveis para uma data."""
    diarists = await service.get_available_diarists(
        data=data,
        tipo=tipo,
    )
    return [DiaristResponse.model_validate(d) for d in diarists]


# ==================== ASSIGNMENT ENDPOINTS ====================


@router.post(
    "/assignments",
    response_model=DiaristAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin", "sindico"))],
)
async def create_assignment(
    data: DiaristAssignmentCreate,
    service: DiaristService = Depends(get_diarist_service),
) -> DiaristAssignmentResponse:
    """Cria uma alocação de diarista."""
    try:
        assignment = await service.create_assignment(data)
        return DiaristAssignmentResponse.model_validate(assignment)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/assignments", response_model=list[DiaristAssignmentResponse])
async def list_assignments(
    diarist_id: UUID | None = None,
    status_filter: AssignmentStatus | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service: DiaristService = Depends(get_diarist_service),
    _: dict = Depends(get_current_user),
) -> list[DiaristAssignmentResponse]:
    """Lista alocações."""
    assignments = await service.list_assignments(
        diarist_id=diarist_id,
        status=status_filter,
        skip=skip,
        limit=limit,
    )
    return [DiaristAssignmentResponse.model_validate(a) for a in assignments]


@router.get(
    "/assignments/{assignment_id}",
    response_model=DiaristAssignmentResponse,
)
async def get_assignment(
    assignment_id: UUID,
    service: DiaristService = Depends(get_diarist_service),
    _: dict = Depends(get_current_user),
) -> DiaristAssignmentResponse:
    """Busca alocação por ID."""
    assignment = await service.get_assignment(assignment_id)
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alocação não encontrada",
        )
    return DiaristAssignmentResponse.model_validate(assignment)


@router.post(
    "/assignments/{assignment_id}/cancel",
    dependencies=[Depends(require_roles("admin", "sindico"))],
)
async def cancel_assignment(
    assignment_id: UUID,
    service: DiaristService = Depends(get_diarist_service),
) -> dict[str, str]:
    """Cancela uma alocação."""
    if not await service.cancel_assignment(assignment_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alocação não encontrada",
        )
    return {"message": "Alocação cancelada com sucesso"}


# ==================== SCHEDULE ENDPOINTS ====================


@router.post(
    "/schedules/batch",
    response_model=BatchScheduleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin", "sindico"))],
)
async def create_batch_schedules(
    data: BatchScheduleCreate,
    service: DiaristService = Depends(get_diarist_service),
) -> BatchScheduleResponse:
    """Cria escala diaria em lote para uma data."""
    try:
        result = await service.create_batch_schedules(data)
        return BatchScheduleResponse(
            total_criados=result["total_criados"],
            total_erros=result["total_erros"],
            erros=result["erros"],
            schedules=[DiaristScheduleResponse.model_validate(s) for s in result["schedules"]],
        )
    except Exception as e:
        logger.error(f"Erro ao criar escala em lote: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao criar escala em lote: {str(e)}",
        )


@router.post(
    "/schedules",
    response_model=DiaristScheduleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin", "sindico", "porteiro"))],
)
async def create_schedule(
    data: DiaristScheduleCreate,
    service: DiaristService = Depends(get_diarist_service),
) -> DiaristScheduleResponse:
    """Cria um agendamento avulso."""
    try:
        schedule = await service.create_schedule(data)
        return DiaristScheduleResponse.model_validate(schedule)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/schedules", response_model=list[DiaristScheduleResponse])
async def list_schedules(
    diarist_id: UUID | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    status_filter: ScheduleStatus | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service: DiaristService = Depends(get_diarist_service),
    _: dict = Depends(get_current_user),
) -> list[DiaristScheduleResponse]:
    """Lista agendamentos."""
    schedules = await service.list_schedules(
        diarist_id=diarist_id,
        data_inicio=data_inicio,
        data_fim=data_fim,
        status=status_filter,
        skip=skip,
        limit=limit,
    )
    return [DiaristScheduleResponse.model_validate(s) for s in schedules]


@router.get("/schedules/today", response_model=list[DiaristScheduleResponse])
async def get_today_schedules(
    service: DiaristService = Depends(get_diarist_service),
    _: dict = Depends(get_current_user),
) -> list[DiaristScheduleResponse]:
    """Busca agendamentos de hoje."""
    schedules = await service.get_today_schedules()
    return [DiaristScheduleResponse.model_validate(s) for s in schedules]


@router.get(
    "/schedules/{schedule_id}",
    response_model=DiaristScheduleResponse,
)
async def get_schedule(
    schedule_id: UUID,
    service: DiaristService = Depends(get_diarist_service),
    _: dict = Depends(get_current_user),
) -> DiaristScheduleResponse:
    """Busca agendamento por ID."""
    schedule = await service.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agendamento não encontrado",
        )
    return DiaristScheduleResponse.model_validate(schedule)


@router.post(
    "/schedules/{schedule_id}/confirm",
    response_model=DiaristScheduleResponse,
    dependencies=[Depends(require_roles("admin", "sindico", "porteiro"))],
)
async def confirm_schedule(
    schedule_id: UUID,
    service: DiaristService = Depends(get_diarist_service),
) -> DiaristScheduleResponse:
    """Confirma um agendamento."""
    schedule = await service.confirm_schedule(schedule_id)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agendamento não pode ser confirmado",
        )
    return DiaristScheduleResponse.model_validate(schedule)


@router.post(
    "/schedules/{schedule_id}/cancel",
    response_model=DiaristScheduleResponse,
    dependencies=[Depends(require_roles("admin", "sindico"))],
)
async def cancel_schedule(
    schedule_id: UUID,
    motivo: str | None = None,
    service: DiaristService = Depends(get_diarist_service),
) -> DiaristScheduleResponse:
    """Cancela um agendamento."""
    try:
        schedule = await service.cancel_schedule(schedule_id, motivo)
        if not schedule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agendamento não encontrado",
            )
        return DiaristScheduleResponse.model_validate(schedule)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/schedules/checkin",
    response_model=DiaristScheduleResponse,
    dependencies=[Depends(require_roles("admin", "sindico", "porteiro"))],
)
async def register_checkin(
    data: CheckinRequest,
    service: DiaristService = Depends(get_diarist_service),
) -> DiaristScheduleResponse:
    """Registra check-in."""
    schedule = await service.register_checkin(data)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Check-in não pode ser registrado",
        )
    asyncio.create_task(
        publish_diarista_checkin(
            schedule_id=str(schedule.id),
            diarist_id=str(getattr(schedule, "diarist_id", "") or ""),
        )
    )
    return DiaristScheduleResponse.model_validate(schedule)


@router.post(
    "/schedules/checkout",
    response_model=DiaristScheduleResponse,
    dependencies=[Depends(require_roles("admin", "sindico", "porteiro"))],
)
async def register_checkout(
    data: CheckoutRequest,
    service: DiaristService = Depends(get_diarist_service),
) -> DiaristScheduleResponse:
    """Registra check-out."""
    schedule = await service.register_checkout(data)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Check-out não pode ser registrado",
        )
    asyncio.create_task(
        publish_diarista_checkout(
            schedule_id=str(schedule.id),
            diarist_id=str(getattr(schedule, "diarist_id", "") or ""),
        )
    )
    return DiaristScheduleResponse.model_validate(schedule)


# ==================== PAYMENT ENDPOINTS ====================


@router.get(
    "/payments/payroll-report",
    response_model=PayrollReportResponse,
    dependencies=[Depends(require_roles("admin", "sindico"))],
)
async def get_payroll_report(
    competencia: str = Query(..., min_length=7, max_length=7, description="YYYY-MM"),
    condominio_id: UUID | None = None,
    service: DiaristService = Depends(get_diarist_service),
    _: dict = Depends(get_current_user),
) -> PayrollReportResponse:
    """Gera relatorio de fechamento de folha para uma competencia."""
    try:
        result = await service.generate_payroll_report(
            competencia=competencia,
            condominio_id=condominio_id,
        )
        return PayrollReportResponse(**result)
    except Exception as e:
        logger.error(f"Erro ao gerar relatorio de folha: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao gerar relatorio: {str(e)}",
        )


@router.post(
    "/payments/payroll-generate",
    dependencies=[Depends(require_roles("admin", "sindico"))],
)
async def generate_payroll_payments(
    data: PayrollGenerateRequest,
    service: DiaristService = Depends(get_diarist_service),
) -> dict[str, Any]:
    """Gera pagamentos em lote a partir do fechamento de folha."""
    try:
        result = await service.generate_payroll_payments(data)
        return {
            "competencia": result["competencia"],
            "total_gerados": result["total_gerados"],
            "total_erros": result["total_erros"],
            "erros": result["erros"],
        }
    except Exception as e:
        logger.error(f"Erro ao gerar pagamentos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao gerar pagamentos: {str(e)}",
        )


@router.post(
    "/payments",
    response_model=DiaristPaymentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin", "sindico"))],
)
async def create_payment(
    data: DiaristPaymentCreate,
    service: DiaristService = Depends(get_diarist_service),
) -> DiaristPaymentResponse:
    """Cria um pagamento."""
    try:
        payment = await service.create_payment(data)
        return DiaristPaymentResponse.model_validate(payment)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/payments", response_model=list[DiaristPaymentResponse])
async def list_payments(
    diarist_id: UUID | None = None,
    status_filter: PaymentStatus | None = Query(None, alias="status"),
    data_inicio: date | None = None,
    data_fim: date | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service: DiaristService = Depends(get_diarist_service),
    _: dict = Depends(get_current_user),
) -> list[DiaristPaymentResponse]:
    """Lista pagamentos."""
    payments = await service.list_payments(
        diarist_id=diarist_id,
        status=status_filter,
        data_inicio=data_inicio,
        data_fim=data_fim,
        skip=skip,
        limit=limit,
    )
    return [DiaristPaymentResponse.model_validate(p) for p in payments]


@router.get("/payments/pending", response_model=list[DiaristPaymentResponse])
async def get_pending_payments(
    service: DiaristService = Depends(get_diarist_service),
    _: dict = Depends(get_current_user),
) -> list[DiaristPaymentResponse]:
    """Lista pagamentos pendentes."""
    payments = await service.get_pending_payments()
    return [DiaristPaymentResponse.model_validate(p) for p in payments]


@router.get(
    "/payments/{payment_id}",
    response_model=DiaristPaymentResponse,
)
async def get_payment(
    payment_id: UUID,
    service: DiaristService = Depends(get_diarist_service),
    _: dict = Depends(get_current_user),
) -> DiaristPaymentResponse:
    """Busca pagamento por ID."""
    payment = await service.get_payment(payment_id)
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pagamento não encontrado",
        )
    return DiaristPaymentResponse.model_validate(payment)


@router.post(
    "/payments/{payment_id}/process",
    response_model=DiaristPaymentResponse,
    dependencies=[Depends(require_roles("admin", "sindico"))],
)
async def process_payment(
    payment_id: UUID,
    data_pagamento: date,
    comprovante: str | None = None,
    service: DiaristService = Depends(get_diarist_service),
) -> DiaristPaymentResponse:
    """Processa pagamento."""
    payment = await service.process_payment(
        payment_id=payment_id,
        data_pagamento=data_pagamento,
        comprovante=comprovante,
    )
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pagamento não pode ser processado",
        )
    asyncio.create_task(
        publish_diarista_pagamento(
            payment_id=str(payment.id),
            diarist_id=str(getattr(payment, "diarist_id", "") or ""),
            valor=float(getattr(payment, "valor", 0) or 0),
        )
    )
    return DiaristPaymentResponse.model_validate(payment)


@router.post(
    "/payments/generate",
    response_model=DiaristPaymentResponse,
    dependencies=[Depends(require_roles("admin", "sindico"))],
)
async def generate_payment(
    diarist_id: UUID,
    data_inicio: date,
    data_fim: date,
    service: DiaristService = Depends(get_diarist_service),
) -> DiaristPaymentResponse:
    """Gera pagamento a partir de agendamentos concluídos."""
    payment = await service.generate_payment_from_schedules(
        diarist_id=diarist_id,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum agendamento concluído no período",
        )
    return DiaristPaymentResponse.model_validate(payment)


# ==================== EVALUATION ENDPOINTS ====================


@router.post(
    "/evaluations",
    response_model=DiaristEvaluationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_evaluation(
    data: DiaristEvaluationCreate,
    service: DiaristService = Depends(get_diarist_service),
    _: dict = Depends(get_current_user),
) -> DiaristEvaluationResponse:
    """Cria uma avaliação."""
    try:
        evaluation = await service.create_evaluation(data)
        return DiaristEvaluationResponse.model_validate(evaluation)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/evaluations", response_model=list[DiaristEvaluationResponse])
async def list_evaluations(
    diarist_id: UUID | None = None,
    nota_minima: int | None = Query(None, ge=1, le=5),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service: DiaristService = Depends(get_diarist_service),
    _: dict = Depends(get_current_user),
) -> list[DiaristEvaluationResponse]:
    """Lista avaliações."""
    evaluations = await service.list_evaluations(
        diarist_id=diarist_id,
        nota_minima=nota_minima,
        skip=skip,
        limit=limit,
    )
    return [DiaristEvaluationResponse.model_validate(e) for e in evaluations]


@router.get(
    "/evaluations/{evaluation_id}",
    response_model=DiaristEvaluationResponse,
)
async def get_evaluation(
    evaluation_id: UUID,
    service: DiaristService = Depends(get_diarist_service),
    _: dict = Depends(get_current_user),
) -> DiaristEvaluationResponse:
    """Busca avaliação por ID."""
    evaluation = await service.get_evaluation(evaluation_id)
    if not evaluation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Avaliação não encontrada",
        )
    return DiaristEvaluationResponse.model_validate(evaluation)


# ==================== AI ENDPOINTS ====================


@router.get("/ai/suggest", response_model=list[DiaristSuggestionResponse])
async def suggest_diarists(
    data: date,
    tipo: DiaristType | None = None,
    duracao_horas: int = Query(8, ge=1, le=12),
    priorizar_conhecidas: bool = True,
    condominio_id: UUID | None = Query(None),
    ai_service: DiaristAIService = Depends(get_ai_service),
    _: dict = Depends(get_current_user),
) -> list[DiaristSuggestionResponse]:
    """Sugere diaristas para uma data usando IA."""
    return await ai_service.suggest_diarists(
        data=data,
        tipo=tipo,
        duracao_horas=duracao_horas,
        priorizar_conhecidas=priorizar_conhecidas,
        condominio_id=condominio_id,
    )


@router.get("/ai/availability", response_model=list[DiaristAvailabilityResponse])
async def analyze_availability(
    data_inicio: date,
    data_fim: date,
    tipo: DiaristType | None = None,
    condominio_id: UUID | None = Query(None),
    ai_service: DiaristAIService = Depends(get_ai_service),
    _: dict = Depends(get_current_user),
) -> list[DiaristAvailabilityResponse]:
    """Analisa disponibilidade de diaristas em um período."""
    return await ai_service.analyze_availability(
        data_inicio=data_inicio,
        data_fim=data_fim,
        tipo=tipo,
        condominio_id=condominio_id,
    )


@router.get(
    "/ai/performance/{diarist_id}",
    response_model=DiaristPerformanceResponse,
)
async def analyze_performance(
    diarist_id: UUID,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    ai_service: DiaristAIService = Depends(get_ai_service),
    _: dict = Depends(get_current_user),
) -> DiaristPerformanceResponse:
    """Analisa performance de uma diarista usando IA."""
    try:
        return await ai_service.analyze_performance(
            diarist_id=diarist_id,
            data_inicio=data_inicio,
            data_fim=data_fim,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get("/ai/optimize", response_model=ScheduleOptimizationResponse)
async def optimize_schedule(
    data_inicio: date,
    data_fim: date,
    budget: Decimal | None = None,
    condominio_id: UUID | None = Query(None),
    ai_service: DiaristAIService = Depends(get_ai_service),
    _: dict = Depends(get_current_user),
) -> ScheduleOptimizationResponse:
    """Otimiza agendamentos usando IA (condominio_id opcional = todos)."""
    return await ai_service.optimize_schedule(
        data_inicio=data_inicio,
        data_fim=data_fim,
        budget=budget,
        condominio_id=condominio_id,
    )


# ==================== STATISTICS ENDPOINTS ====================


@router.get("/statistics/general")
async def get_general_statistics(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    service: DiaristService = Depends(get_diarist_service),
    _: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Retorna estatísticas de diaristas do condomínio."""
    return await service.get_condominio_statistics(
        data_inicio=data_inicio,
        data_fim=data_fim,
    )


@router.get("/statistics/ranking")
async def get_top_diarists(
    limit: int = Query(10, ge=1, le=50),
    service: DiaristService = Depends(get_diarist_service),
    _: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Retorna ranking das melhores diaristas."""
    return await service.get_top_diarists(
        limit=limit,
    )


# ==================== DIARIST BY ID ENDPOINTS (devem ficar por ultimo) ====================
# IMPORTANTE: Rotas com /{diarist_id} capturam qualquer path.
# Todas as rotas literais (/available, /schedules, /payments, etc.)
# DEVEM ser declaradas ANTES deste bloco.


@router.get("/{diarist_id}", response_model=DiaristResponse)
async def get_diarist(
    diarist_id: UUID,
    service: DiaristService = Depends(get_diarist_service),
    _: dict = Depends(get_current_user),
) -> DiaristResponse:
    """Busca diarista por ID."""
    diarist = await service.get_diarist(diarist_id)
    if not diarist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diarista não encontrada",
        )
    return DiaristResponse.model_validate(diarist)


@router.put(
    "/{diarist_id}",
    response_model=DiaristResponse,
    dependencies=[Depends(require_roles("admin", "sindico"))],
)
async def update_diarist(
    diarist_id: UUID,
    data: DiaristUpdate,
    service: DiaristService = Depends(get_diarist_service),
) -> DiaristResponse:
    """Atualiza diarista."""
    diarist = await service.update_diarist(diarist_id, data)
    if not diarist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diarista não encontrada",
        )
    return DiaristResponse.model_validate(diarist)


@router.post(
    "/{diarist_id}/activate",
    response_model=DiaristResponse,
    dependencies=[Depends(require_roles("admin", "sindico"))],
)
async def activate_diarist(
    diarist_id: UUID,
    service: DiaristService = Depends(get_diarist_service),
) -> DiaristResponse:
    """Ativa uma diarista."""
    diarist = await service.activate_diarist(diarist_id)
    if not diarist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diarista não encontrada",
        )
    return DiaristResponse.model_validate(diarist)


@router.post(
    "/{diarist_id}/deactivate",
    response_model=DiaristResponse,
    dependencies=[Depends(require_roles("admin", "sindico"))],
)
async def deactivate_diarist(
    diarist_id: UUID,
    service: DiaristService = Depends(get_diarist_service),
) -> DiaristResponse:
    """Desativa uma diarista."""
    diarist = await service.deactivate_diarist(diarist_id)
    if not diarist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diarista não encontrada",
        )
    return DiaristResponse.model_validate(diarist)


@router.delete(
    "/{diarist_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("admin"))],
)
async def delete_diarist(
    diarist_id: UUID,
    service: DiaristService = Depends(get_diarist_service),
) -> None:
    """Remove diarista (soft delete)."""
    if not await service.delete_diarist(diarist_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diarista não encontrada",
        )


@router.get("/{diarist_id}/metrics")
async def get_diarist_metrics(
    diarist_id: UUID,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    service: DiaristService = Depends(get_diarist_service),
    _: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Retorna métricas da diarista."""
    return await service.get_diarist_metrics(
        diarist_id=diarist_id,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
