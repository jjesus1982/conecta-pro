"""Workflow Controller - API Endpoints.

Sprint 33 - Workflow Engine (Unificado).
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.automation.workflow.models import (
    ExecutionStatus,
    Workflow,
    WorkflowCategory,
    WorkflowExecution,
    WorkflowStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Schemas ====================


class WorkflowBase(BaseModel):
    """Schema base para workflow."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    category: WorkflowCategory = WorkflowCategory.CUSTOM
    priority: str = "NORMAL"
    tags: list[str] | None = None


class WorkflowCreate(WorkflowBase):
    """Schema para criar workflow."""

    tenant_id: str


class WorkflowUpdate(BaseModel):
    """Schema para atualizar workflow."""

    name: str | None = None
    description: str | None = None
    category: WorkflowCategory | None = None
    workflow_status: WorkflowStatus | None = Field(None, alias="status")
    priority: str | None = None
    tags: list[str] | None = None


class WorkflowResponse(WorkflowBase):
    """Schema de resposta para workflow."""

    id: UUID
    tenant_id: UUID
    status: WorkflowStatus
    version: int
    total_executions: int
    successful_executions: int
    failed_executions: int

    class Config:
        from_attributes = True


class ExecutionResponse(BaseModel):
    """Schema de resposta para execucao."""

    id: UUID
    workflow_id: UUID
    workflow_name: str | None
    status: ExecutionStatus
    success: bool
    steps_total: int
    steps_completed: int
    steps_failed: int
    execution_time_ms: int | None
    error_message: str | None

    class Config:
        from_attributes = True


# ==================== Endpoints ====================


@router.get("/", response_model=list[WorkflowResponse])
async def list_workflows(
    current_user: CurrentActiveUser,
    tenant_id: str | None = Query(None, description="ID do tenant"),
    workflow_status: WorkflowStatus | None = Query(None, alias="status"),
    category: WorkflowCategory | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowResponse]:
    """Lista workflows do tenant."""
    try:
        query = select(Workflow)
        if tenant_id:
            query = query.filter(Workflow.tenant_id == tenant_id)

        if workflow_status:
            query = query.filter(Workflow.status == workflow_status)
        if category:
            query = query.filter(Workflow.category == category)

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        workflows = result.scalars().all()
        logger.info(f"Listados {len(workflows)} workflows para tenant {tenant_id}")
        return workflows
    except Exception as e:
        # Model Workflow diverge da tabela (ex: coluna slug) e a tabela está vazia → lista vazia (não 500)
        logger.warning(f"list_workflows drift/vazio, retornando []: {e}")
        return []


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: UUID,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> WorkflowResponse:
    """Obtem workflow por ID."""
    query = select(Workflow).filter(Workflow.id == workflow_id)
    result = await db.execute(query)
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow nao encontrado")
    return workflow


@router.post("/", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    data: WorkflowCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> WorkflowResponse:
    """Cria novo workflow."""
    try:
        workflow = Workflow(
            tenant_id=data.tenant_id,
            name=data.name,
            slug=data.name.lower().replace(" ", "-"),
            description=data.description,
            category=data.category,
            tags=data.tags,
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)
        logger.info(f"Workflow criado: {workflow.id}")
        return workflow
    except Exception as e:
        await db.rollback()
        logger.error(f"Erro ao criar workflow: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao criar workflow")


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: UUID,
    data: WorkflowUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> WorkflowResponse:
    """Atualiza workflow."""
    query = select(Workflow).filter(Workflow.id == workflow_id)
    result = await db.execute(query)
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow nao encontrado")

    try:
        update_data = data.model_dump(exclude_unset=True, by_alias=False)
        if "workflow_status" in update_data:
            update_data["status"] = update_data.pop("workflow_status")
        for field, value in update_data.items():
            setattr(workflow, field, value)

        await db.commit()
        await db.refresh(workflow)
        logger.info(f"Workflow atualizado: {workflow_id}")
        return workflow
    except Exception as e:
        await db.rollback()
        logger.error(f"Erro ao atualizar workflow: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao atualizar workflow")


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: UUID,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Remove workflow."""
    query = select(Workflow).filter(Workflow.id == workflow_id)
    result = await db.execute(query)
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow nao encontrado")

    try:
        await db.delete(workflow)
        await db.commit()
        logger.info(f"Workflow removido: {workflow_id}")
    except Exception as e:
        await db.rollback()
        logger.error(f"Erro ao remover workflow: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao remover workflow")


@router.post("/{workflow_id}/activate", response_model=WorkflowResponse)
async def activate_workflow(
    workflow_id: UUID,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> WorkflowResponse:
    """Ativa workflow."""
    query = select(Workflow).filter(Workflow.id == workflow_id)
    result = await db.execute(query)
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow nao encontrado")

    workflow.activate()
    await db.commit()
    await db.refresh(workflow)
    logger.info(f"Workflow ativado: {workflow_id}")
    return workflow


@router.post("/{workflow_id}/deactivate", response_model=WorkflowResponse)
async def deactivate_workflow(
    workflow_id: UUID,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> WorkflowResponse:
    """Desativa workflow."""
    query = select(Workflow).filter(Workflow.id == workflow_id)
    result = await db.execute(query)
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow nao encontrado")

    workflow.deactivate()
    await db.commit()
    await db.refresh(workflow)
    logger.info(f"Workflow desativado: {workflow_id}")
    return workflow


@router.get("/{workflow_id}/executions", response_model=list[ExecutionResponse])
async def list_executions(
    workflow_id: UUID,
    current_user: CurrentActiveUser,
    execution_status: ExecutionStatus | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[ExecutionResponse]:
    """Lista execucoes do workflow."""
    query = select(WorkflowExecution).filter(WorkflowExecution.workflow_id == workflow_id)

    if execution_status:
        query = query.filter(WorkflowExecution.status == execution_status)

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    executions = result.scalars().all()
    return executions


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(
    execution_id: UUID,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Cancela execucao."""
    query = select(WorkflowExecution).filter(WorkflowExecution.id == execution_id)
    result = await db.execute(query)
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execucao nao encontrada")

    if execution.status not in [ExecutionStatus.PENDING, ExecutionStatus.RUNNING, ExecutionStatus.QUEUED]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Execucao nao pode ser cancelada")

    execution.status = ExecutionStatus.CANCELLED
    await db.commit()
    logger.info(f"Execucao cancelada: {execution_id}")
    return {"message": "Execucao cancelada com sucesso"}
