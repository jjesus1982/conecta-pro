"""
Controller de Integracao ERP - Licitacoes
=========================================
Endpoints para integracao entre modulos:
  Licitacao -> Operacional -> Financeiro
"""

import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.bidding.services.erp_integration_service import ERPIntegrationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/erp", tags=["Licitacoes - Integracao ERP"])


# ------------------------------------------------------------------ #
#  Schemas de request                                                #
# ------------------------------------------------------------------ #


class PostoConfig(BaseModel):
    """Configuracao de posto para conversao."""

    name: str = Field(..., description="Nome do posto")
    post_type: str = Field(default="porteiro", description="Tipo: porteiro, controlador de acesso, etc.")
    shift_type: str = Field(default="diurno", description="Turno: diurno, noturno, 12x36, etc.")
    headcount: int = Field(default=1, ge=1, description="Quantidade de funcionarios necessarios")
    address: str | None = Field(default=None, description="Endereco do posto")
    city: str | None = Field(default=None, description="Cidade")
    state: str | None = Field(default=None, description="UF")
    hourly_rate: float | None = Field(default=None, description="Valor hora")
    monthly_cost: float | None = Field(default=None, description="Custo mensal")
    requires_armed: bool = Field(default=False, description="Exige armamento")
    requires_vehicle: bool = Field(default=False, description="Exige veiculo")


class ConverterRequest(BaseModel):
    """Request para converter contrato em entidades operacionais."""

    postos: list[PostoConfig] | None = Field(
        default=None,
        description="Lista de postos a criar. Se vazio, cria posto generico.",
    )


class MedicaoRequest(BaseModel):
    """Request para gerar medicao."""

    competencia: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}$",
        description="Competencia no formato YYYY-MM",
    )
    periodo_inicio: date = Field(..., description="Data inicio do periodo")
    periodo_fim: date = Field(..., description="Data fim do periodo")


# ------------------------------------------------------------------ #
#  Endpoints                                                         #
# ------------------------------------------------------------------ #


@router.get("/status/{contract_id}")
async def get_integration_status(
    contract_id: UUID,
    current_user: CurrentActiveUser,
    db: Session = Depends(get_db),
):
    """
    Retorna o status de integracao de um contrato publico.

    Mostra o que ja foi criado em cada modulo:
    - Contrato de licitacao
    - Postos operacionais
    - Alocacoes de funcionarios
    - Medicoes
    - Faturas (pendente integracao)
    - NFS-e (pendente integracao)
    """
    service = ERPIntegrationService(db)
    try:
        return await service.status_integracao(contract_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post("/converter/{contract_id}", status_code=201)
async def converter_contrato(
    contract_id: UUID,
    current_user: CurrentActiveUser,
    data: ConverterRequest | None = None,
    db: Session = Depends(get_db),
):
    """
    Converte contrato publico em entidades operacionais.

    Cria postos de trabalho vinculados ao contrato.
    Se nenhuma configuracao de posto for informada, cria um posto
    generico baseado no objeto do contrato.
    """
    service = ERPIntegrationService(db)
    try:
        postos_config = None
        if data and data.postos:
            postos_config = [p.model_dump() for p in data.postos]
        return await service.converter_para_contrato_operacional(
            contract_id=contract_id,
            postos_config=postos_config,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/medicao/{contract_id}", status_code=201)
async def gerar_medicao(
    contract_id: UUID,
    data: MedicaoRequest,
    current_user: CurrentActiveUser,
    db: Session = Depends(get_db),
):
    """
    Gera medicao para um contrato em um periodo especifico.

    Calcula automaticamente o valor bruto baseado nos postos e
    alocacoes ativas. Aplica retencoes tributarias padrao.
    """
    service = ERPIntegrationService(db)
    try:
        return await service.gerar_medicao(
            contract_id=contract_id,
            competencia=data.competencia,
            periodo_inicio=data.periodo_inicio,
            periodo_fim=data.periodo_fim,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/fatura/{medicao_id}", status_code=201)
async def gerar_fatura(
    medicao_id: UUID,
    current_user: CurrentActiveUser,
    db: Session = Depends(get_db),
):
    """
    Gera fatura (conta a receber) a partir de medicao aprovada.

    NOTA: Integracao com modulos financeiro e NFS-e pendente.
    Retorna estrutura stub com dados da fatura.
    """
    service = ERPIntegrationService(db)
    try:
        return await service.gerar_fatura(medicao_id=medicao_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/crm/{contract_id}", status_code=201)
async def contrato_para_crm(
    contract_id: UUID,
    current_user: CurrentActiveUser,
    db: Session = Depends(get_db),
):
    """
    Vincula contrato publico ao modulo CRM (Comercial).

    Busca ou cria um registro de cliente no CRM a partir dos dados
    do orgao contratante. Degradacao graceful se o modulo CRM nao
    estiver disponivel.
    """
    service = ERPIntegrationService(db)
    try:
        return await service.contrato_para_crm(contract_id=contract_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
