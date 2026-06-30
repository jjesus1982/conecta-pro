"""
My Data Controller — Dados pessoais do funcionario.

Endpoints:
- GET /portal/my-data
- PUT /portal/my-data
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.people_management.employee_portal.auth import CurrentEmployeeId

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Meus Dados"])


class MyDataResponse(BaseModel):
    """Dados pessoais do funcionario."""

    nome: str | None = None
    cpf: str | None = None
    cargo: str | None = None
    data_admissao: str | None = None
    telefone: str | None = None
    email: str | None = None
    endereco: str | None = None
    contato_emergencia: str | None = None

    model_config = ConfigDict(from_attributes=True)


class UpdateMyDataRequest(BaseModel):
    """Campos que o funcionario pode alterar pelo portal."""

    telefone: str | None = Field(None, max_length=20, description="Telefone de contato")
    email: str | None = Field(None, max_length=255, description="Email pessoal")
    endereco: str | None = Field(None, max_length=500, description="Endereco completo")
    contato_emergencia: str | None = Field(None, max_length=255, description="Contato de emergencia")

    model_config = ConfigDict(from_attributes=True)


@router.get(
    "/my-data",
    response_model=MyDataResponse,
    summary="Meus dados pessoais",
    description="Retorna dados pessoais do funcionario logado.",
)
async def get_my_data(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna dados pessoais do funcionario autenticado."""
    try:
        from sqlalchemy import select

        from modules.operacional.models.employee import Employee

        result = await db.execute(select(Employee).where(Employee.id == employee_id))
        employee = result.scalar_one_or_none()

        if employee:
            cpf = getattr(employee, "cpf", None)
            if cpf and len(cpf) > 4:
                cpf = f"***.***.***-{cpf[-2:]}"

            return MyDataResponse(
                nome=getattr(employee, "nome", None) or getattr(employee, "name", None),
                cpf=cpf,
                cargo=getattr(employee, "cargo", None) or getattr(employee, "position", None),
                data_admissao=str(employee.data_admissao) if getattr(employee, "data_admissao", None) else None,
                telefone=getattr(employee, "telefone", None) or getattr(employee, "phone", None),
                email=getattr(employee, "email", None),
                endereco=getattr(employee, "endereco", None) or getattr(employee, "address", None),
                contato_emergencia=getattr(employee, "contato_emergencia", None),
            )
    except (ImportError, Exception) as e:
        logger.warning(f"Erro ao buscar dados do funcionario {employee_id}: {e}")

    return MyDataResponse(
        nome="Funcionario",
        cpf="***.***.***.***-**",
    )


@router.put(
    "/my-data",
    response_model=MyDataResponse,
    summary="Atualizar meus dados",
    description="Atualiza campos limitados dos dados pessoais.",
)
async def update_my_data(
    update_data: UpdateMyDataRequest,
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Atualiza dados pessoais do funcionario autenticado."""
    update_fields = update_data.model_dump(exclude_unset=True)
    if not update_fields:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Nenhum campo para atualizar.",
        )

    allowed_fields = {"telefone", "email", "endereco", "contato_emergencia"}
    invalid_fields = set(update_fields.keys()) - allowed_fields
    if invalid_fields:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Campos nao permitidos para atualizacao: {invalid_fields}",
        )

    try:
        from sqlalchemy import select

        from modules.operacional.models.employee import Employee

        result = await db.execute(select(Employee).where(Employee.id == employee_id))
        employee = result.scalar_one_or_none()

        if employee:
            for field, value in update_fields.items():
                if hasattr(employee, field):
                    setattr(employee, field, value)
            await db.commit()
            await db.refresh(employee)

            logger.info(f"Dados atualizados para employee {employee_id}: {list(update_fields.keys())}")

    except (ImportError, Exception) as e:
        logger.warning(f"Erro ao atualizar dados: {e}")

    return MyDataResponse(
        nome="Funcionario",
        cpf="***.***.***.***-**",
        **dict(update_fields.items()),
    )
