"""
Controller para listar funcionarios do modulo Operacional.
Integração com Solides DP (Tangerino) para dados em tempo real.
"""

import logging
import os
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.models.employee import Employee
from modules.operacional.permissions import Permission, require_operacional_permission
from modules.operacional.schemas.employee import (
    EmployeeCreate,
    EmployeeListResponse,
    EmployeeResponse,
    EmployeeUpdate,
    SolidesEmployeeListResponse,
    SolidesEmployeeResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employees", tags=["Operations - Employees"])


async def _resolver_cargo_cct(db: AsyncSession, cct_cargo_id: str) -> dict | None:
    """Resolve o cargo da CCT (fonte única) por id → nome canônico + piso + adicionais."""
    try:
        row = (
            await db.execute(
                text(
                    "SELECT cargo_nome, piso_salarial, adicional_periculosidade_percentual, "
                    "adicional_insalubridade_percentual FROM cct_cargos WHERE id = :cid"
                ),
                {"cid": str(cct_cargo_id)},
            )
        ).mappings().first()
        return dict(row) if row else None
    except Exception as e:  # noqa: BLE001
        logger.warning("Falha ao resolver cargo CCT %s: %s", cct_cargo_id, e)
        return None


async def _publicar_cargo_alterado(employee: Any, cargo_anterior: str | None, current_user: Any) -> None:
    """Comunicação bidirecional: publica DP_CARGO_ALTERADO no event bus (folha/SST/GEDEON reagem)."""
    try:
        from infrastructure.event_bus import EventTypes, event_bus

        await event_bus.emit(
            EventTypes.DP_CARGO_ALTERADO,
            {
                "funcionario_id": str(employee.id),
                "funcionario_nome": employee.nome,
                "cargo_anterior": cargo_anterior,
                "cargo": employee.cargo,
                "cct_cargo_id": str(employee.cct_cargo_id) if employee.cct_cargo_id else None,
                "salario_base": float(employee.salario_base) if employee.salario_base is not None else None,
            },
            source_module="operacional",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Falha ao publicar cargo alterado (%s): %s", employee.id, e)


@router.get(
    "/",
    response_model=EmployeeListResponse,
    dependencies=[require_operacional_permission(Permission.EMPLOYEES_VIEW)],
)
async def list_employees(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Pagina atual"),
    page_size: int = Query(100, ge=1, le=500, description="Itens por pagina"),
    search: str | None = Query(None, description="Buscar por nome, email ou matricula"),
    status: str | None = Query(None, description="Filtrar por status"),
) -> EmployeeListResponse:
    """
    Lista funcionarios com paginacao e filtros.
    """
    filters: list[Any] = [Employee.is_active.is_(True)]

    if status:
        filters.append(Employee.status == status)

    if search:
        like_term = f"%{search}%"
        filters.append(
            or_(
                Employee.nome.ilike(like_term),
                Employee.email.ilike(like_term),
                Employee.matricula.ilike(like_term),
            )
        )

    # Count total
    total_result = await db.execute(select(func.count(Employee.id)).where(*filters))
    total: int = total_result.scalar_one() or 0
    total_pages = (total + page_size - 1) // page_size

    # Get items
    items_result = await db.execute(
        select(Employee).where(*filters).order_by(Employee.nome.asc()).offset((page - 1) * page_size).limit(page_size)
    )
    items: list[Employee] = items_result.scalars().all()

    return EmployeeListResponse(
        items=[
            EmployeeResponse(
                id=str(item.id),
                nome=item.nome,
                email=item.email,
                matricula=item.matricula,
                cpf=item.cpf,
                cargo=item.cargo,
                departamento=item.departamento,
                telefone=item.telefone,
                data_admissao=str(item.data_admissao) if item.data_admissao else None,
                status=item.status,
            )
            for item in items
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post(
    "/",
    response_model=EmployeeResponse,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[require_operacional_permission(Permission.EMPLOYEES_CREATE)],
)
async def create_employee(
    data: EmployeeCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    """
    Cria um novo funcionário no sistema.

    Valida:
    - Email único
    - CPF único (se fornecido)
    - Matrícula única
    """
    import uuid
    from datetime import datetime

    # Validar email único
    email_result = await db.execute(select(Employee).where(Employee.email == data.email, Employee.is_active.is_(True)))
    if email_result.scalar_one_or_none():
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail="Email já cadastrado para outro funcionário"
        )

    # Validar CPF único (se fornecido)
    if data.cpf:
        cpf_result = await db.execute(select(Employee).where(Employee.cpf == data.cpf, Employee.is_active.is_(True)))
        if cpf_result.scalar_one_or_none():
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT, detail="CPF já cadastrado para outro funcionário"
            )

    # Validar matrícula única
    matricula_result = await db.execute(
        select(Employee).where(Employee.matricula == data.matricula, Employee.is_active.is_(True))
    )
    if matricula_result.scalar_one_or_none():
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail="Matrícula já cadastrada para outro funcionário"
        )

    # Criar funcionário
    employee = Employee(
        id=uuid.uuid4(),
        nome=data.nome,
        email=data.email,
        matricula=data.matricula,
        cpf=data.cpf,
        cargo=data.cargo,
        departamento=data.departamento,
        telefone=data.telefone,
        status=data.status or "Ativo",
        is_active=True,
        created_by=current_user.id,
        created_at=datetime.utcnow(),
    )

    # Campos opcionais
    if data.data_admissao:
        try:
            from datetime import date

            employee.data_admissao = date.fromisoformat(data.data_admissao)
        except ValueError:
            pass

    if data.pis:
        employee.pis = data.pis

    # CCT como fonte única: se veio cct_cargo_id, vincula e deriva cargo + piso da CCT.
    if getattr(data, "cct_cargo_id", None):
        cct = await _resolver_cargo_cct(db, data.cct_cargo_id)
        if cct:
            employee.cct_cargo_id = data.cct_cargo_id
            employee.cargo = cct["cargo_nome"]
            if employee.salario_base is None:
                employee.salario_base = cct["piso_salarial"]

    db.add(employee)
    await db.commit()
    await db.refresh(employee)

    logger.info(
        "Funcionário criado com sucesso",
        action="create_employee",
        employee_id=str(employee.id),
        employee_nome=employee.nome,
        employee_email=employee.email,
        user_id=str(current_user.id),
        user_email=current_user.email,
    )

    return EmployeeResponse(
        id=str(employee.id),
        nome=employee.nome,
        email=employee.email,
        matricula=employee.matricula,
        cargo=employee.cargo,
        departamento=employee.departamento,
        status=employee.status,
        cpf=employee.cpf,
        telefone=employee.telefone,
    )


@router.patch(
    "/{employee_id}",
    response_model=EmployeeResponse,
    dependencies=[require_operacional_permission(Permission.EMPLOYEES_EDIT)],
)
async def update_employee(
    employee_id: UUID,
    data: EmployeeUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    """
    Atualiza dados de um funcionário.
    """
    # Busca funcionário
    result = await db.execute(select(Employee).where(Employee.id == str(employee_id)))
    employee: Employee | None = result.scalar_one_or_none()

    if not employee:
        raise HTTPException(status_code=404, detail="Funcionário não encontrado")

    # Atualiza campos
    cargo_anterior = employee.cargo
    if data.cargo is not None:
        employee.cargo = data.cargo
    if data.departamento is not None:
        employee.departamento = data.departamento
    if data.telefone is not None:
        employee.telefone = data.telefone
    if data.status is not None:
        employee.status = data.status

    # CCT fonte única: cct_cargo_id define cargo + piso canônicos.
    if getattr(data, "cct_cargo_id", None):
        cct = await _resolver_cargo_cct(db, data.cct_cargo_id)
        if cct:
            employee.cct_cargo_id = data.cct_cargo_id
            employee.cargo = cct["cargo_nome"]
            employee.salario_base = cct["piso_salarial"]

    await db.commit()
    await db.refresh(employee)

    # Comunicação bidirecional: cargo mudou → avisa os módulos (folha/SST/GEDEON).
    if employee.cargo != cargo_anterior:
        await _publicar_cargo_alterado(employee, cargo_anterior, current_user)

    logger.info(f"Funcionário {employee_id} atualizado por {current_user.email}")

    return EmployeeResponse(
        id=str(employee.id),
        nome=employee.nome,
        email=employee.email,
        matricula=employee.matricula,
        cargo=employee.cargo,
        departamento=employee.departamento,
        status=employee.status,
    )


# ==================== INTEGRAÇÃO SOLIDES DP ====================


async def _get_solides_connector() -> Any:
    """Inicializa o conector Solides com credenciais."""
    from uuid import UUID

    from modules.integrations.connectors.solides.connector import SolidesConnector

    api_token = os.getenv("SOLIDES_API_TOKEN")
    if not api_token:
        raise HTTPException(status_code=500, detail="Token Solides não configurado. Configure SOLIDES_API_TOKEN.")

    # UUID dummy para uso standalone (sem multi-tenant)
    dummy_uuid = UUID("00000000-0000-0000-0000-000000000000")

    connector = SolidesConnector(
        account_id=dummy_uuid,
        tenant_id=dummy_uuid,
        credentials={"api_token": api_token},
        config={"base_url": "https://employer.tangerino.com.br"},
    )

    await connector.setup()
    return connector


def _map_solides_employee(emp: dict[str, Any], job_roles_map: dict[int, str]) -> SolidesEmployeeResponse:
    """Mapeia dados do Solides para schema de resposta."""
    # Extrai cargo do jobRole
    job_role_id: int | None = None
    job_role_name: str | None = None

    if emp.get("jobRole"):
        if isinstance(emp["jobRole"], dict):
            job_role_id = emp["jobRole"].get("id")
            job_role_name = emp["jobRole"].get("name")
        elif isinstance(emp["jobRole"], int):
            job_role_id = emp["jobRole"]

    # Se não tem nome do cargo, busca no mapa
    if not job_role_name and job_role_id and job_role_id in job_roles_map:
        job_role_name = job_roles_map[job_role_id]

    # Extrai departamento
    department_name: str | None = None
    if emp.get("department"):
        if isinstance(emp["department"], dict):
            department_name = emp["department"].get("name")

    # Monta nome completo
    nome: str = emp.get("name", "")
    if not nome:
        nome = f"{emp.get('firstName', '')} {emp.get('lastName', '')}".strip()

    # Mapeia status (pode vir como int ou string)
    status_map: dict[str | int, str] = {
        "ACTIVE": "Ativo",
        "INACTIVE": "Inativo",
        "TERMINATED": "Demitido",
        "ON_LEAVE": "Afastado",
        "VACATION": "Férias",
        0: "Ativo",
        1: "Inativo",
        2: "Demitido",
    }
    status_raw: str | int = emp.get("status", "ACTIVE")
    status_mapped: str = status_map.get(status_raw, str(status_raw) if status_raw else "Ativo")

    # Converte data_admissao (pode vir como timestamp ou string)
    data_admissao: str | int | None = emp.get("admissionDate")
    data_admissao_str: str | None = None
    if data_admissao:
        if isinstance(data_admissao, int):
            # Timestamp em milliseconds
            from datetime import datetime

            try:
                data_admissao_str = datetime.fromtimestamp(data_admissao / 1000).strftime("%Y-%m-%d")
            except Exception:
                data_admissao_str = str(data_admissao)
        else:
            data_admissao_str = str(data_admissao)

    return SolidesEmployeeResponse(
        id=str(emp.get("id", "")),
        nome=nome,
        email=emp.get("email"),
        matricula=emp.get("registration") or emp.get("employeeCode"),
        cargo=job_role_name,
        departamento=department_name,
        status=status_mapped,
        cpf=emp.get("cpf"),
        telefone=emp.get("phone") or emp.get("cellphone"),
        data_admissao=data_admissao_str,
        pis=emp.get("pis"),
    )


@router.get(
    "/solides",
    response_model=SolidesEmployeeListResponse,
    dependencies=[require_operacional_permission(Permission.EMPLOYEES_VIEW)],
)
async def list_employees_from_solides(
    current_user: CurrentActiveUser,
    search: str | None = Query(None, description="Buscar por nome ou matricula"),
    status: str | None = Query(None, description="Filtrar por status (ACTIVE, INACTIVE, etc)"),
    only_active: bool = Query(True, description="Apenas funcionarios ativos"),
) -> SolidesEmployeeListResponse:
    """
    Lista funcionarios diretamente da API Solides DP (Tangerino).
    Dados em tempo real do sistema de RH/DP.
    """
    try:
        connector = await _get_solides_connector()

        # Busca cargos primeiro para mapear
        job_roles_result = await connector.fetch_entities("job_roles")
        job_roles_map: dict[int, str] = {}
        if job_roles_result.success and job_roles_result.data:
            for jr in job_roles_result.data:
                if jr.get("id") and jr.get("name"):
                    job_roles_map[jr["id"]] = jr["name"]

        logger.info(f"Carregados {len(job_roles_map)} cargos do Solides")

        # Busca funcionarios
        filters: dict[str, Any] = {}
        if only_active:
            filters["status"] = "ACTIVE"
        elif status:
            filters["status"] = status

        result = await connector.fetch_entities(
            entity_type="employees",
            page_size=500,
            filters=filters if filters else None,
        )

        if not result.success:
            logger.error(f"Erro ao buscar funcionarios do Solides: {result.errors}")
            raise HTTPException(status_code=502, detail="Erro ao conectar com Solides DP")

        employees: list[dict[str, Any]] = result.data or []
        logger.info(f"Recebidos {len(employees)} funcionarios do Solides")

        # Aplica filtro de busca local (API Solides não tem busca textual)
        if search:
            search_lower = search.lower()
            employees = [
                emp
                for emp in employees
                if search_lower in (emp.get("name", "") or "").lower()
                or search_lower in (emp.get("firstName", "") or "").lower()
                or search_lower in (emp.get("lastName", "") or "").lower()
                or search_lower in (emp.get("registration", "") or "").lower()
                or search_lower in (emp.get("employeeCode", "") or "").lower()
                or search_lower in (emp.get("email", "") or "").lower()
            ]

        # Mapeia para schema de resposta
        items = [_map_solides_employee(emp, job_roles_map) for emp in employees]

        # Ordena por nome
        items.sort(key=lambda x: x.nome or "")

        await connector.teardown()

        return SolidesEmployeeListResponse(
            items=items,
            total=len(items),
            source="solides",
        )

    except HTTPException:
        raise
    except (httpx.TimeoutException, TimeoutError) as e:
        logger.error(f"Timeout ao conectar com Solides DP [user={current_user.id}]: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Timeout ao conectar com Solides DP. A API pode estar lenta ou indisponível. Tente novamente em alguns instantes.",
        )
    except Exception as e:
        logger.exception(f"Erro ao buscar funcionarios do Solides [user={current_user.id}]: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
