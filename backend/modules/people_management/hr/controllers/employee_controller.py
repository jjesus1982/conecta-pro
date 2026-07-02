"""
Controller de Funcionários — Departamento Pessoal.

Endpoints CRUD para gestão de funcionários na visão DP.
"""

import asyncio
import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.hr.publishers import publish_funcionario_atualizado
from modules.people_management.hr.schemas.employee import (
    DPEmployeeList,
    DPEmployeeRead,
    DPEmployeeUpdate,
)
from modules.people_management.hr.services.cadastro_import_service import CadastroImportService
from modules.people_management.hr.services.employee_service import EmployeeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employees", tags=["DP - Funcionários"])


@router.post("/import-cadastro", summary="Importar cadastro (CSV do contador/Onvio)")
async def importar_cadastro(
    file: UploadFile = File(...),
    sobrescrever: bool = Query(
        False, description="True força os valores da planilha; False (padrão) só preenche campos vazios"
    ),
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Sobe uma planilha CSV (casa por CPF) e completa o cadastro dos funcionários
    (RG, CTPS, endereço, filiação, estado civil, etc.). Idempotente."""
    conteudo = await file.read()
    if not conteudo:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    service = CadastroImportService(db)
    resultado = await service.import_csv(conteudo, sobrescrever=sobrescrever)
    if not resultado.get("sucesso"):
        raise HTTPException(status_code=422, detail=resultado.get("erro", "Falha ao importar."))
    return resultado


@router.get(
    "",
    summary="Listar Funcionários",
    response_model=DPEmployeeList,
    description="Retorna lista paginada de funcionários ativos com suporte a busca por nome, CPF e matrícula.",
)
async def list_employees(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Página"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por página"),
    search: str | None = Query(None, description="Busca por nome, CPF ou matrícula"),
) -> Any:
    """Lista funcionários ativos com paginação e busca."""
    service = EmployeeService(db)
    return await service.get_active_employees(page=page, page_size=page_size, search=search)


@router.get(
    "/stats",
    summary="Estatísticas de Funcionários",
    description="Retorna lista paginada de funcionários ativos com suporte a busca por nome, CPF e matrícula.",
)
async def get_employees_stats(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna contadores de funcionários por status."""
    result = await db.execute(
        text("SELECT status, is_active, COUNT(*) as qtd FROM employees GROUP BY status, is_active")
    )
    rows = result.mappings().all()
    # Verdade única: "ativo" é status == 'ativo' (alinha com a lista /employees, que filtra por status).
    # is_active fica sujo em demitidos/afastados e inflava o contador — não usar mais aqui.
    ativos = sum(r["qtd"] for r in rows if str(r.get("status") or "").lower() == "ativo")
    total = sum(r["qtd"] for r in rows)
    inativos = total - ativos
    return {"total": total, "ativos": ativos, "inativos": inativos, "por_status": [dict(r) for r in rows]}


@router.get(
    "/discipline",
    summary="Visão Geral Disciplinar",
    description="Retorna lista paginada de funcionários ativos com suporte a busca por nome, CPF e matrícula.",
)
async def list_discipline_overview(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Any:
    """Lista medidas disciplinares ativas de todos os funcionários."""
    try:
        result = await db.execute(
            text(
                "SELECT da.id::text, da.employee_id::text, e.nome as employee_name, "
                "da.action_type, da.description, da.status, da.created_at::text "
                "FROM disciplinary_actions da "
                "JOIN employees e ON da.employee_id = e.id "
                "ORDER BY da.created_at DESC "
                "LIMIT :limit OFFSET :offset"
            ),
            {"limit": page_size, "offset": (page - 1) * page_size},
        )
        rows = result.mappings().all()
        count_result = await db.execute(text("SELECT COUNT(*) FROM disciplinary_actions"))
        total = count_result.scalar() or 0
        return {
            "items": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }
    except Exception:
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 1}


@router.get(
    "/search",
    summary="Buscar Funcionários",
    response_model=DPEmployeeList,
    description="Retorna lista paginada de funcionários ativos com suporte a busca por nome, CPF e matrícula.",
)
async def search_employees(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    q: str = Query("", description="Busca por nome, CPF ou matrícula"),
    status: str | None = Query(None, description="Filtrar por status (ativo/inativo)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Any:
    """Busca funcionários por nome, CPF ou matrícula."""
    service = EmployeeService(db)
    return await service.get_active_employees(
        page=page,
        page_size=page_size,
        search=q or None,
    )


@router.get(
    "/{employee_id}",
    summary="Buscar Funcionário por ID",
    response_model=DPEmployeeRead,
    description="Retorna lista paginada de funcionários ativos com suporte a busca por nome, CPF e matrícula.",
)
async def get_employee(
    employee_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna dados DP de um funcionário."""
    service = EmployeeService(db)
    employee = await service.get_by_id(employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Funcionário não encontrado")
    return employee


@router.get(
    "/{employee_id}/profile",
    summary="Perfil Completo do Funcionário",
    description="Retorna lista paginada de funcionários ativos com suporte a busca por nome, CPF e matrícula.",
)
async def get_employee_full_profile(
    employee_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna perfil completo do funcionário (dados + benefícios + contrato)."""
    service = EmployeeService(db)
    profile = await service.get_employee_full_profile(employee_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Funcionário não encontrado")
    return profile


@router.get(
    "/cpf/{cpf}",
    summary="Buscar Funcionário por CPF",
    response_model=DPEmployeeRead,
    description="Retorna lista paginada de funcionários ativos com suporte a busca por nome, CPF e matrícula.",
)
async def get_employee_by_cpf(
    cpf: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Busca funcionário por CPF."""
    service = EmployeeService(db)
    employee = await service.get_by_cpf(cpf)
    if not employee:
        raise HTTPException(status_code=404, detail="Funcionário não encontrado")
    return employee


@router.patch(
    "/{employee_id}",
    summary="Atualizar Funcionário",
    response_model=DPEmployeeRead,
    description="Retorna lista paginada de funcionários ativos com suporte a busca por nome, CPF e matrícula.",
)
async def update_employee(
    employee_id: str,
    data: DPEmployeeUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Atualiza dados DP de um funcionário."""
    service = EmployeeService(db)
    update_data = data.model_dump(exclude_unset=True)
    employee = await service.update_employee(employee_id, update_data)
    if not employee:
        raise HTTPException(status_code=404, detail="Funcionário não encontrado")
    await db.commit()
    asyncio.create_task(
        publish_funcionario_atualizado(
            funcionario_id=employee_id,
            funcionario_nome=str(getattr(employee, "nome", "") or ""),
            campos_alterados=list(update_data.keys()),
        )
    )
    return employee


# =============================================================================
# CONSIGNADOS E PENSÕES (Deduções fixas)
# =============================================================================


class DeductionCreate(BaseModel):
    """Schema para criar dedução do funcionário."""

    tipo: str = Field(..., pattern="^(consignado|pensao_alimenticia|emprestimo|outros)$")
    descricao: str = Field(..., min_length=3, max_length=200)
    valor: float | None = Field(None, ge=0)
    percentual: float | None = Field(None, ge=0, le=100)
    base_calculo: str = Field("fixo", pattern="^(bruto|liquido|fixo)$")
    total_parcelas: int | None = Field(None, ge=1)
    data_inicio: str = Field(...)
    data_fim: str | None = None


@router.get(
    "/{employee_id}/deductions",
    summary="Listar Deduções do Funcionário",
    description="Retorna lista paginada de funcionários ativos com suporte a busca por nome, CPF e matrícula.",
)
async def list_deductions(
    employee_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    ativo: bool = True,
) -> Any:
    """Lista deduções (consignados, pensões) de um funcionário."""
    result = await db.execute(
        text(
            "SELECT id, tipo, descricao, valor, percentual, base_calculo, "
            "parcela_atual, total_parcelas, data_inicio::text, data_fim::text, ativo "
            "FROM employee_deductions WHERE employee_id = :eid "
            "AND ativo = :ativo ORDER BY tipo, descricao"
        ),
        {"eid": employee_id, "ativo": ativo},
    )
    rows = result.mappings().all()
    return {"employee_id": employee_id, "total": len(rows), "items": [dict(r) for r in rows]}


@router.post(
    "/{employee_id}/deductions",
    summary="Criar Dedução",
    status_code=201,
    description="Retorna lista paginada de funcionários ativos com suporte a busca por nome, CPF e matrícula.",
)
async def create_deduction(
    employee_id: str,
    data: DeductionCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Cria nova dedução para um funcionário."""
    result = await db.execute(
        text(
            "INSERT INTO employee_deductions "
            "(employee_id, tipo, descricao, valor, percentual, base_calculo, "
            "total_parcelas, data_inicio, data_fim) "
            "VALUES (:eid, :tipo, :desc, :val, :pct, :base, :parcelas, :inicio, :fim) "
            "RETURNING id"
        ),
        {
            "eid": employee_id,
            "tipo": data.tipo,
            "desc": data.descricao,
            "val": data.valor,
            "pct": data.percentual,
            "base": data.base_calculo,
            "parcelas": data.total_parcelas,
            "inicio": (date.fromisoformat(str(data.data_inicio)[:10]) if data.data_inicio else None),
            "fim": (date.fromisoformat(str(data.data_fim)[:10]) if data.data_fim else None),
        },
    )
    new_id = result.scalar_one()
    await db.commit()
    return {"id": str(new_id), "employee_id": employee_id, "tipo": data.tipo, "descricao": data.descricao}
