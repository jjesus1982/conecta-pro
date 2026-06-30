"""Scheduler Controller - REST API Endpoints.

Sprint 35 - Task Scheduler.
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_active_user
from core.database import get_db  # noqa: F401
from core.database.session import get_sync_db_dependency
from modules.scheduler.models.scheduled_task import TaskCategory, TaskStatus, TaskType
from modules.scheduler.models.task_execution import ExecutionStatus

# Queue models used via schemas
from modules.scheduler.schemas.scheduler_schemas import (
    ExecutionLogResponse,
    ExecutionResponse,
    LockCreate,
    LockResponse,
    QueueItemCreate,
    QueueItemResponse,
    QueueStatsResponse,
    TaskCreate,
    TaskListResponse,
    TaskResponse,
    TaskStatsResponse,
    TaskUpdate,
    TriggerTaskRequest,
    TriggerTaskResponse,
    WorkerResponse,
    WorkerStatsResponse,
)
from modules.scheduler.services.scheduler_service import SchedulerService
from modules.scheduler.services.task_executor import TaskExecutor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])


def get_scheduler_service(db: Session = Depends(get_sync_db_dependency)) -> SchedulerService:
    """Dependency para obter o SchedulerService."""
    return SchedulerService(db)


# ==================== Task Endpoints ====================


@router.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar tarefa agendada",
)
def create_task(
    data: TaskCreate,
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
):
    """Cria uma nova tarefa agendada."""
    try:
        task = service.create_task(
            tenant_id=(getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2"),
            created_by=current_user.id,
            **data.model_dump(exclude_none=True),
        )
        return task
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/tasks",
    response_model=TaskListResponse,
    summary="Listar tarefas",
)
def list_tasks(
    status: TaskStatus | None = None,
    category: TaskCategory | None = None,
    task_type: TaskType | None = None,
    queue_name: str | None = None,
    tags: str | None = Query(None, description="Tags separadas por vírgula"),
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
):
    """Lista tarefas com filtros."""
    tags_list = tags.split(",") if tags else None
    skip = (page - 1) * page_size

    tasks, total = service.list_tasks(
        tenant_id=(getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2"),
        status=status,
        category=category,
        task_type=task_type,
        queue_name=queue_name,
        tags=tags_list,
        search=search,
        skip=skip,
        limit=page_size,
    )

    return TaskListResponse(
        items=tasks,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    summary="Buscar tarefa por ID",
)
def get_task(
    task_id: UUID,
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
):
    """Busca uma tarefa por ID."""
    task = service.get_task(
        task_id, (getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2")
    )
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return task


@router.patch(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    summary="Atualizar tarefa",
)
def update_task(
    task_id: UUID,
    data: TaskUpdate,
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
):
    """Atualiza uma tarefa."""
    try:
        task = service.update_task(
            task_id=task_id,
            tenant_id=(getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2"),
            updated_by=current_user.id,
            **data.model_dump(exclude_none=True),
        )
        if not task:
            raise HTTPException(status_code=404, detail="Tarefa não encontrada")
        return task
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover tarefa",
)
def delete_task(
    task_id: UUID,
    hard_delete: bool = False,
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
):
    """Remove uma tarefa."""
    deleted = service.delete_task(
        task_id, (getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2"), hard_delete
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")


@router.post(
    "/tasks/{task_id}/activate",
    response_model=TaskResponse,
    summary="Ativar tarefa",
)
def activate_task(
    task_id: UUID,
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
):
    """Ativa uma tarefa."""
    task = service.activate_task(
        task_id, (getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2")
    )
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return task


@router.post(
    "/tasks/{task_id}/pause",
    response_model=TaskResponse,
    summary="Pausar tarefa",
)
def pause_task(
    task_id: UUID,
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
):
    """Pausa uma tarefa."""
    task = service.pause_task(
        task_id, (getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2")
    )
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return task


@router.post(
    "/tasks/{task_id}/trigger",
    response_model=TriggerTaskResponse,
    summary="Disparar tarefa manualmente",
)
def trigger_task(
    task_id: UUID,
    data: TriggerTaskRequest | None = None,
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
    db: Session = Depends(get_db),
):
    """Dispara uma tarefa para execução imediata."""
    task = service.get_task(
        task_id, (getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2")
    )
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    # Sobrescrever argumentos se fornecidos
    if data:
        if data.override_args:
            task.handler_args = {**task.handler_args, **data.override_args}
        if data.override_kwargs:
            task.handler_kwargs = {**task.handler_kwargs, **data.override_kwargs}

    executor = TaskExecutor(db)
    execution = executor.execute_task_now(task, triggered_by=current_user.id)

    return TriggerTaskResponse(
        task_id=task.id,
        execution_id=execution.id,
        run_id=execution.run_id,
        status=execution.status,
        message="Tarefa disparada com sucesso",
    )


@router.get(
    "/tasks/stats/summary",
    response_model=TaskStatsResponse,
    summary="Estatísticas de tarefas",
)
def get_task_stats(
    period_days: int = Query(30, ge=1, le=365),
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
):
    """Retorna estatísticas das tarefas."""
    return service.get_task_stats(
        (getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2"), period_days
    )


# ==================== Execution Endpoints ====================


@router.get(
    "/executions",
    response_model=list[ExecutionResponse],
    summary="Listar execuções",
)
def list_executions(
    task_id: UUID | None = None,
    status: ExecutionStatus | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
):
    """Lista execuções com filtros."""
    skip = (page - 1) * page_size

    executions, _ = service.list_executions(
        tenant_id=(getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2"),
        task_id=task_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=page_size,
    )

    return executions


@router.get(
    "/executions/{execution_id}",
    response_model=ExecutionResponse,
    summary="Buscar execução por ID",
)
def get_execution(
    execution_id: UUID,
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
):
    """Busca uma execução por ID."""
    execution = service.get_execution(
        execution_id, (getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2")
    )
    if not execution:
        raise HTTPException(status_code=404, detail="Execução não encontrada")
    return execution


@router.get(
    "/executions/{execution_id}/logs",
    response_model=list[ExecutionLogResponse],
    summary="Listar logs da execução",
)
def get_execution_logs(
    execution_id: UUID,
    level: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
):
    """Lista logs de uma execução."""
    execution = service.get_execution(
        execution_id, (getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2")
    )
    if not execution:
        raise HTTPException(status_code=404, detail="Execução não encontrada")

    query = execution.logs
    if level:
        from modules.scheduler.models.task_execution import TaskExecutionLog

        query = query.filter(TaskExecutionLog.level == level)

    return query.order_by(TaskExecutionLog.timestamp.asc()).limit(limit).all()


@router.post(
    "/executions/{execution_id}/cancel",
    response_model=ExecutionResponse,
    summary="Cancelar execução",
)
def cancel_execution(
    execution_id: UUID,
    reason: str = "Cancelled by user",
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Cancela uma execução pendente."""
    executor = TaskExecutor(db)
    execution = executor.cancel_execution(execution_id, reason)
    if not execution:
        raise HTTPException(
            status_code=400,
            detail="Não foi possível cancelar a execução",
        )
    return execution


# ==================== Queue Endpoints ====================


@router.post(
    "/queue",
    response_model=QueueItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Adicionar item à fila",
)
def enqueue_item(
    data: QueueItemCreate,
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
):
    """Adiciona um item diretamente à fila."""
    item = service.enqueue(
        tenant_id=(getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2"),
        created_by=current_user.id,
        **data.model_dump(exclude_none=True),
    )
    return item


@router.get(
    "/queue",
    response_model=list[QueueItemResponse],
    summary="Listar itens da fila",
)
def list_queue_items(
    queue_name: str = "default",
    status: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Lista itens da fila."""
    from modules.scheduler.models.task_queue import TaskQueue

    query = db.query(TaskQueue).filter(
        TaskQueue.tenant_id == (getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2"),
        TaskQueue.queue_name == queue_name,
    )

    if status:
        query = query.filter(TaskQueue.status == status)

    return (
        query.order_by(
            TaskQueue.priority_value.asc(),
            TaskQueue.enqueued_at.asc(),
        )
        .limit(limit)
        .all()
    )


@router.get(
    "/queue/stats",
    response_model=QueueStatsResponse,
    summary="Estatísticas da fila",
)
def get_queue_stats(
    queue_name: str = "default",
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
):
    """Retorna estatísticas de uma fila."""
    return service.get_queue_stats(queue_name)


@router.delete(
    "/queue/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover item da fila",
)
def delete_queue_item(
    item_id: UUID,
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Remove um item da fila."""
    from modules.scheduler.models.task_queue import QueueStatus, TaskQueue

    item = (
        db.query(TaskQueue)
        .filter(
            TaskQueue.id == item_id,
            TaskQueue.tenant_id == (getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2"),
        )
        .first()
    )

    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    if item.status not in [QueueStatus.PENDING, QueueStatus.DEFERRED]:
        raise HTTPException(
            status_code=400,
            detail="Apenas itens pendentes podem ser removidos",
        )

    item.status = QueueStatus.CANCELLED
    db.commit()


# ==================== Worker Endpoints ====================


@router.get(
    "/workers",
    response_model=list[WorkerResponse],
    summary="Listar workers",
)
def list_workers(
    status: str | None = None,
    queue_name: str | None = None,
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Lista workers registrados."""
    from modules.scheduler.models.task_worker import TaskWorker

    query = db.query(TaskWorker).filter(TaskWorker.active.is_(True))

    if status:
        query = query.filter(TaskWorker.status == status)
    if queue_name:
        query = query.filter(TaskWorker.queues.contains([queue_name]))

    return query.order_by(TaskWorker.registered_at.desc()).all()


@router.get(
    "/workers/{worker_id}",
    response_model=WorkerResponse,
    summary="Buscar worker por ID",
)
def get_worker(
    worker_id: str,
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Busca um worker por ID."""
    from modules.scheduler.models.task_worker import TaskWorker

    worker = db.query(TaskWorker).filter(TaskWorker.worker_id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker não encontrado")
    return worker


@router.get(
    "/workers/stats/summary",
    response_model=WorkerStatsResponse,
    summary="Estatísticas de workers",
)
def get_worker_stats(
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Retorna estatísticas dos workers."""
    from modules.scheduler.models.task_worker import TaskWorker, WorkerStatus

    workers = db.query(TaskWorker).filter(TaskWorker.active.is_(True)).all()

    total = len(workers)
    idle = sum(1 for w in workers if w.status == WorkerStatus.IDLE)
    busy = sum(1 for w in workers if w.status == WorkerStatus.BUSY)
    offline = sum(1 for w in workers if w.status == WorkerStatus.OFFLINE)
    active = idle + busy

    total_tasks = sum(w.total_tasks_processed for w in workers)
    total_concurrency = sum(w.concurrency for w in workers)
    total_in_progress = sum(w.tasks_in_progress for w in workers)

    avg_utilization = (total_in_progress / total_concurrency * 100) if total_concurrency > 0 else 0

    return WorkerStatsResponse(
        total_workers=total,
        active_workers=active,
        idle_workers=idle,
        busy_workers=busy,
        offline_workers=offline,
        total_tasks_processed=total_tasks,
        total_concurrency=total_concurrency,
        avg_utilization=avg_utilization,
    )


# ==================== Lock Endpoints ====================


@router.post(
    "/locks",
    response_model=LockResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Adquirir lock",
)
def acquire_lock(
    data: LockCreate,
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
):
    """Adquire um lock distribuído."""
    lock = service.acquire_lock(
        tenant_id=(getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2"),
        owner_id=str(current_user.id),
        owner_hostname="api",
        **data.model_dump(exclude_none=True),
    )
    if not lock:
        raise HTTPException(
            status_code=409,
            detail="Lock já está em uso",
        )
    return lock


@router.delete(
    "/locks/{lock_key}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Liberar lock",
)
def release_lock(
    lock_key: str,
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
):
    """Libera um lock."""
    released = service.release_lock(
        tenant_id=(getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2"),
        lock_key=lock_key,
        owner_id=str(current_user.id),
    )
    if not released:
        raise HTTPException(
            status_code=404,
            detail="Lock não encontrado ou não pertence a você",
        )


@router.post(
    "/locks/{lock_key}/renew",
    response_model=LockResponse,
    summary="Renovar lock",
)
def renew_lock(
    lock_key: str,
    ttl_seconds: int = Query(3600, ge=1, le=86400),
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
):
    """Renova um lock existente."""
    lock = service.renew_lock(
        tenant_id=(getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2"),
        lock_key=lock_key,
        owner_id=str(current_user.id),
        ttl_seconds=ttl_seconds,
    )
    if not lock:
        raise HTTPException(
            status_code=404,
            detail="Lock não encontrado ou não pode ser renovado",
        )
    return lock


@router.get(
    "/locks",
    response_model=list[LockResponse],
    summary="Listar locks ativos",
)
def list_locks(
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Lista locks ativos do tenant."""
    from modules.scheduler.models.task_lock import LockStatus, TaskLock

    return (
        db.query(TaskLock)
        .filter(
            TaskLock.tenant_id == (getattr(current_user, "tenant_id", None) or "841a3906-5410-4047-a076-bc7bce95ffd2"),
            TaskLock.status == LockStatus.ACQUIRED,
            TaskLock.expires_at > datetime.utcnow(),
        )
        .all()
    )


# ==================== Scheduler Operations ====================


@router.post(
    "/scheduler/run-cycle",
    summary="Executar ciclo do scheduler",
)
def run_scheduler_cycle(
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
):
    """Executa manualmente um ciclo do scheduler."""
    # Apenas admin pode executar
    if current_user.role not in ["admin", "system"]:
        raise HTTPException(status_code=403, detail="Acesso negado")

    results = service.run_scheduler_cycle()
    return {
        "status": "ok",
        "message": "Ciclo executado",
        **results,
    }


@router.get(
    "/scheduler/due-tasks",
    response_model=list[TaskResponse],
    summary="Listar tarefas pendentes",
)
def get_due_tasks(
    limit: int = Query(100, ge=1, le=500),
    current_user=Depends(get_current_active_user),
    service: SchedulerService = Depends(get_scheduler_service),
):
    """Lista tarefas que devem ser executadas agora."""
    return service.get_due_tasks(limit)
