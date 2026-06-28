"""Controllers para o modulo de Contabilidade."""

import logging
import os
import uuid
from datetime import date, datetime
from decimal import Decimal

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user
from core.database.session import get_sync_db_dependency
from modules.financial.models.accounting_account import (
    AccountClassification,
    AccountingAccount,
    AccountNature,
    AccountStatus,
    AccountType,
)
from modules.financial.models.accounting_period import AccountingPeriod, PeriodStatus, PeriodType
from modules.financial.models.chart_of_accounts import ChartOfAccounts, ChartStatus, ChartType
from modules.financial.models.cost_center import CostCenter, CostCenterStatus, CostCenterType
from modules.financial.models.journal_entry import (
    EntryOrigin,
    EntryStatus,
    EntryType,
    JournalEntry,
    JournalEntryLine,
)
from modules.financial.models.trial_balance import (
    BalanceStatus,
    BalanceType,
    TrialBalance,
    TrialBalanceItem,
)
from modules.financial.repositories.accounting_repository import (
    AccountingAccountRepository,
    AccountingPeriodRepository,
    ChartOfAccountsRepository,
    CostCenterRepository,
    JournalEntryLineRepository,
    JournalEntryRepository,
    TrialBalanceItemRepository,
    TrialBalanceRepository,
)
from modules.financial.schemas.accounting_schemas import (
    AccountingAccountCreate,
    AccountingAccountListResponse,
    AccountingAccountResponse,
    AccountingAccountUpdate,
    AccountingPeriodCreate,
    AccountingPeriodListResponse,
    AccountingPeriodResponse,
    AccountStats,
    AccountTreeResponse,
    BalanceStats,
    ChartOfAccountsCreate,
    ChartOfAccountsResponse,
    ChartOfAccountsUpdate,
    ChartStats,
    CostCenterCreate,
    CostCenterListResponse,
    CostCenterResponse,
    CostCenterStats,
    CostCenterUpdate,
    JournalEntryApprovalRequest,
    JournalEntryCreate,
    JournalEntryLineResponse,
    JournalEntryListResponse,
    JournalEntryResponse,
    JournalEntryReversalRequest,
    JournalStats,
    PeriodCloseRequest,
    PeriodReopenRequest,
    PeriodStats,
    TrialBalanceCreate,
    TrialBalanceItemResponse,
    TrialBalanceListResponse,
    TrialBalanceResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accounting", tags=["Contabilidade"])


# =============================================================================
# ChartOfAccounts Endpoints
# =============================================================================


@router.get("/charts", response_model=list[ChartOfAccountsResponse])
async def list_charts(
    condominio_id: uuid.UUID | None = Query(None),
    chart_type: ChartType | None = None,
    chart_status: ChartStatus | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> list[ChartOfAccountsResponse]:
    """Lista planos de contas."""
    try:
        repo = ChartOfAccountsRepository(db)
        _cond_id = condominio_id or getattr(_current_user, "condominio_id", None)
        charts = repo.list_all(
            condominio_id=_cond_id,
            chart_type=chart_type,
            status=chart_status,
            skip=skip,
            limit=limit,
        )
        return [ChartOfAccountsResponse.model_validate(c) for c in charts]
    except Exception as e:
        logger.error(f"Erro ao listar planos de contas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar planos de contas",
        ) from e


@router.get("/charts/active", response_model=ChartOfAccountsResponse)
async def get_active_chart(
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> ChartOfAccountsResponse:
    """Retorna plano de contas ativo."""
    repo = ChartOfAccountsRepository(db)
    chart = repo.get_active(getattr(_current_user, "condominio_id", None))

    if not chart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhum plano de contas ativo encontrado",
        )

    return ChartOfAccountsResponse.model_validate(chart)


@router.get("/charts/stats", response_model=ChartStats)
async def get_chart_stats(
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> ChartStats:
    """Retorna estatisticas dos planos de contas."""
    try:
        repo = ChartOfAccountsRepository(db)
        stats = repo.get_stats(getattr(_current_user, "condominio_id", None))
        return ChartStats(**stats)
    except Exception as e:
        logger.error(f"Erro ao obter estatisticas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter estatisticas",
        ) from e


@router.post("/charts", response_model=ChartOfAccountsResponse, status_code=201)
async def create_chart(
    data: ChartOfAccountsCreate,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> ChartOfAccountsResponse:
    """Cria um novo plano de contas."""
    try:
        repo = ChartOfAccountsRepository(db)

        # Verifica codigo duplicado
        existing = repo.get_by_code(data.code, getattr(_current_user, "condominio_id", None))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Plano de contas com codigo {data.code} ja existe",
            )

        chart = ChartOfAccounts(
            condominio_id=getattr(_current_user, "condominio_id", None),
            status=ChartStatus.DRAFT,
            created_by=_current_user.id,
            **data.model_dump(exclude={"chart_type", "standard"}),
        )

        if data.chart_type:
            chart.chart_type = data.chart_type
        if data.standard:
            chart.standard = data.standard

        chart = repo.create(chart)
        db.commit()

        logger.info(f"Plano de contas criado: {chart.code}")
        return ChartOfAccountsResponse.model_validate(chart)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao criar plano de contas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar plano de contas",
        ) from e


@router.get("/charts/{chart_id}", response_model=ChartOfAccountsResponse)
async def get_chart(
    chart_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> ChartOfAccountsResponse:
    """Busca plano de contas por ID."""
    repo = ChartOfAccountsRepository(db)
    chart = repo.get_by_id(chart_id)

    if not chart or chart.condominio_id != getattr(_current_user, "condominio_id", None):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plano de contas nao encontrado",
        )

    return ChartOfAccountsResponse.model_validate(chart)


@router.patch("/charts/{chart_id}", response_model=ChartOfAccountsResponse)
async def update_chart(
    chart_id: uuid.UUID,
    data: ChartOfAccountsUpdate,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> ChartOfAccountsResponse:
    """Atualiza plano de contas."""
    try:
        repo = ChartOfAccountsRepository(db)
        chart = repo.get_by_id(chart_id)

        if not chart or chart.condominio_id != getattr(_current_user, "condominio_id", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plano de contas nao encontrado",
            )

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(chart, field, value)

        chart.updated_by = _current_user.id
        chart = repo.update(chart)
        db.commit()

        return ChartOfAccountsResponse.model_validate(chart)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao atualizar plano de contas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao atualizar plano de contas",
        ) from e


@router.post("/charts/{chart_id}/activate", status_code=201)
async def activate_chart(
    chart_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Ativa plano de contas."""
    try:
        repo = ChartOfAccountsRepository(db)
        chart = repo.get_by_id(chart_id)

        if not chart or chart.condominio_id != getattr(_current_user, "condominio_id", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plano de contas nao encontrado",
            )

        # Desativa plano ativo atual
        current_active = repo.get_active(getattr(_current_user, "condominio_id", None))
        if current_active and current_active.id != chart.id:
            current_active.status = ChartStatus.INACTIVE
            repo.update(current_active)

        chart.status = ChartStatus.ACTIVE
        chart.activated_at = datetime.utcnow()
        chart.activated_by = _current_user.id
        repo.update(chart)
        db.commit()

        return {"message": "Plano de contas ativado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao ativar plano de contas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao ativar plano de contas",
        ) from e


# =============================================================================
# AccountingAccount Endpoints
# =============================================================================


@router.get("/accounts", response_model=list[AccountingAccountResponse])
async def list_accounts(
    chart_id: uuid.UUID | None = None,
    account_type: AccountType | None = None,
    nature: AccountNature | None = None,
    classification: AccountClassification | None = None,
    account_status: AccountStatus | None = None,
    parent_id: uuid.UUID | None = None,
    level: int | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> list[AccountingAccountListResponse]:
    """Lista contas contabeis."""
    if not chart_id:
        chart_repo = ChartOfAccountsRepository(db)
        active_chart = chart_repo.get_active(None)
        if not active_chart:
            return []
        chart_id = active_chart.id
    try:
        repo = AccountingAccountRepository(db)
        accounts = repo.list_all(
            chart_id=chart_id,
            account_type=account_type,
            nature=nature,
            classification=classification,
            status=account_status,
            parent_id=parent_id,
            level=level,
            skip=skip,
            limit=limit,
        )
        return [AccountingAccountResponse.model_validate(a) for a in accounts]
    except Exception as e:
        logger.error(f"Erro ao listar contas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar contas",
        ) from e


@router.get("/accounts/tree", response_model=list[AccountTreeResponse])
async def get_account_tree(
    chart_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> list[AccountTreeResponse]:
    """Retorna arvore hierarquica de contas."""
    try:
        repo = AccountingAccountRepository(db)
        accounts = repo.get_account_tree(chart_id)
        return [AccountTreeResponse.model_validate(a) for a in accounts]
    except Exception as e:
        logger.error(f"Erro ao obter arvore: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter arvore de contas",
        ) from e


@router.get("/accounts/stats", response_model=AccountStats)
async def get_account_stats(
    chart_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> AccountStats:
    """Retorna estatisticas das contas."""
    try:
        repo = AccountingAccountRepository(db)
        stats = repo.get_stats(chart_id)
        return AccountStats(**stats)
    except Exception as e:
        logger.error(f"Erro ao obter estatisticas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter estatisticas",
        ) from e


@router.post("/accounts", response_model=AccountingAccountResponse, status_code=201)
async def create_account(
    data: AccountingAccountCreate,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> AccountingAccountResponse:
    """Cria uma nova conta contabil."""
    try:
        repo = AccountingAccountRepository(db)

        # Verifica codigo duplicado
        existing = repo.get_by_code(data.code, data.chart_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Conta com codigo {data.code} ja existe neste plano",
            )

        account = AccountingAccount(
            condominio_id=getattr(_current_user, "condominio_id", None),
            status=AccountStatus.ACTIVE,
            created_by=_current_user.id,
            **data.model_dump(exclude={"account_type", "nature", "classification"}),
        )

        if data.account_type:
            account.account_type = data.account_type
        if data.nature:
            account.nature = data.nature
        if data.classification:
            account.classification = data.classification

        account = repo.create(account)
        db.commit()

        logger.info(f"Conta criada: {account.code}")
        return AccountingAccountResponse.model_validate(account)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao criar conta: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar conta",
        ) from e


@router.get("/accounts/{account_id}", response_model=AccountingAccountResponse)
async def get_account(
    account_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> AccountingAccountResponse:
    """Busca conta contabil por ID."""
    repo = AccountingAccountRepository(db)
    account = repo.get_by_id(account_id)

    if not account or account.condominio_id != getattr(_current_user, "condominio_id", None):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta nao encontrada",
        )

    return AccountingAccountResponse.model_validate(account)


@router.patch("/accounts/{account_id}", response_model=AccountingAccountResponse)
async def update_account(
    account_id: uuid.UUID,
    data: AccountingAccountUpdate,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> AccountingAccountResponse:
    """Atualiza conta contabil."""
    try:
        repo = AccountingAccountRepository(db)
        account = repo.get_by_id(account_id)

        if not account or account.condominio_id != getattr(_current_user, "condominio_id", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta nao encontrada",
            )

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(account, field, value)

        account.updated_by = _current_user.id
        account = repo.update(account)
        db.commit()

        return AccountingAccountResponse.model_validate(account)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao atualizar conta: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao atualizar conta",
        ) from e


@router.get("/accounts/{account_id}/balance")
async def get_account_balance(
    account_id: uuid.UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Retorna saldo de uma conta."""
    try:
        acc_repo = AccountingAccountRepository(db)
        line_repo = JournalEntryLineRepository(db)

        account = acc_repo.get_by_id(account_id)
        if not account or account.condominio_id != getattr(_current_user, "condominio_id", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta nao encontrada",
            )

        balance = line_repo.get_account_balance(account_id, date_from, date_to)

        return {
            "account_id": str(account_id),
            "account_code": account.code,
            "account_name": account.name,
            **balance,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter saldo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter saldo",
        ) from e


# =============================================================================
# CostCenter Endpoints
# =============================================================================


@router.get("/cost-centers", response_model=list[CostCenterResponse])
async def list_cost_centers(
    center_type: CostCenterType | None = None,
    center_status: CostCenterStatus | None = None,
    parent_id: uuid.UUID | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> list[CostCenterResponse]:
    """Lista centros de custo."""
    try:
        repo = CostCenterRepository(db)
        centers = repo.list_all(
            condominio_id=getattr(_current_user, "condominio_id", None),
            center_type=center_type,
            status=center_status,
            parent_id=parent_id,
            skip=skip,
            limit=limit,
        )
        return [CostCenterResponse.model_validate(c) for c in centers]
    except Exception as e:
        logger.error(f"Erro ao listar centros de custo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar centros de custo",
        ) from e


@router.get("/cost-centers/stats", response_model=CostCenterStats)
async def get_cost_center_stats(
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> CostCenterStats:
    """Retorna estatisticas dos centros de custo."""
    try:
        repo = CostCenterRepository(db)
        stats = repo.get_stats(getattr(_current_user, "condominio_id", None))
        return CostCenterStats(**stats)
    except Exception as e:
        logger.error(f"Erro ao obter estatisticas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter estatisticas",
        ) from e


@router.post("/cost-centers", response_model=CostCenterResponse, status_code=201)
async def create_cost_center(
    data: CostCenterCreate,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> CostCenterResponse:
    """Cria um novo centro de custo."""
    try:
        repo = CostCenterRepository(db)

        # Verifica codigo duplicado
        existing = repo.get_by_code(data.code, getattr(_current_user, "condominio_id", None))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Centro de custo com codigo {data.code} ja existe",
            )

        # Filtra o payload às colunas REAIS do model (robusto contra drift schema↔model)
        _cols = {c.name for c in CostCenter.__table__.columns}
        _payload = {k: v for k, v in data.model_dump(exclude={"cost_center_type", "center_type", "allocation_method"}).items() if k in _cols}
        center = CostCenter(
            condominio_id=getattr(_current_user, "condominio_id", None),
            status=CostCenterStatus.ACTIVE,
            created_by=_current_user.id,
            **_payload,
        )

        if getattr(data, "cost_center_type", None) and hasattr(center, "center_type"):
            center.center_type = data.cost_center_type
        if data.allocation_method and hasattr(center, "allocation_method"):
            center.allocation_method = data.allocation_method

        center = repo.create(center)
        db.commit()

        logger.info(f"Centro de custo criado: {center.code}")
        return CostCenterResponse.model_validate(center)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao criar centro de custo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar centro de custo",
        ) from e


@router.get("/cost-centers/{center_id}", response_model=CostCenterResponse)
async def get_cost_center(
    center_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> CostCenterResponse:
    """Busca centro de custo por ID."""
    repo = CostCenterRepository(db)
    center = repo.get_by_id(center_id)

    if not center or center.condominio_id != getattr(_current_user, "condominio_id", None):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Centro de custo nao encontrado",
        )

    return CostCenterResponse.model_validate(center)


@router.patch("/cost-centers/{center_id}", response_model=CostCenterResponse)
async def update_cost_center(
    center_id: uuid.UUID,
    data: CostCenterUpdate,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> CostCenterResponse:
    """Atualiza centro de custo."""
    try:
        repo = CostCenterRepository(db)
        center = repo.get_by_id(center_id)

        if not center or center.condominio_id != getattr(_current_user, "condominio_id", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Centro de custo nao encontrado",
            )

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(center, field, value)

        center.updated_by = _current_user.id
        center = repo.update(center)
        db.commit()

        return CostCenterResponse.model_validate(center)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao atualizar centro de custo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao atualizar centro de custo",
        ) from e


# =============================================================================
# AccountingPeriod Endpoints
# =============================================================================


@router.get("/periods", response_model=list[AccountingPeriodResponse])
async def list_periods(
    year: int | None = None,
    period_type: PeriodType | None = None,
    period_status: PeriodStatus | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> list[AccountingPeriodResponse]:
    """Lista periodos contabeis."""
    try:
        repo = AccountingPeriodRepository(db)
        periods = repo.list_all(
            condominio_id=getattr(_current_user, "condominio_id", None),
            year=year,
            period_type=period_type,
            status=period_status,
            skip=skip,
            limit=limit,
        )
        return [AccountingPeriodResponse.model_validate(p) for p in periods]
    except Exception as e:
        logger.error(f"Erro ao listar periodos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar periodos",
        ) from e


@router.get("/periods/current", response_model=AccountingPeriodResponse)
async def get_current_period(
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> AccountingPeriodResponse:
    """Retorna periodo contabil atual."""
    repo = AccountingPeriodRepository(db)
    period = repo.get_current(getattr(_current_user, "condominio_id", None))

    if not period:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhum periodo aberto encontrado",
        )

    return AccountingPeriodResponse.model_validate(period)


@router.get("/periods/stats", response_model=PeriodStats)
async def get_period_stats(
    year: int | None = None,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> PeriodStats:
    """Retorna estatisticas dos periodos."""
    try:
        repo = AccountingPeriodRepository(db)
        stats = repo.get_stats(getattr(_current_user, "condominio_id", None), year)
        return PeriodStats(**stats)
    except Exception as e:
        logger.error(f"Erro ao obter estatisticas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter estatisticas",
        ) from e


@router.post("/periods", response_model=AccountingPeriodResponse, status_code=201)
async def create_period(
    data: AccountingPeriodCreate,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> AccountingPeriodResponse:
    """Cria um novo periodo contabil."""
    try:
        repo = AccountingPeriodRepository(db)

        # Verifica codigo duplicado
        existing = repo.get_by_code(data.code, getattr(_current_user, "condominio_id", None))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Periodo com codigo {data.code} ja existe",
            )

        period = AccountingPeriod(
            condominio_id=getattr(_current_user, "condominio_id", None),
            status=PeriodStatus.PENDING,
            created_by=_current_user.id,
            **data.model_dump(exclude={"period_type"}),
        )

        if data.period_type:
            period.period_type = data.period_type

        period = repo.create(period)
        db.commit()

        logger.info(f"Periodo criado: {period.code}")
        return AccountingPeriodResponse.model_validate(period)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao criar periodo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar periodo",
        ) from e


@router.get("/periods/{period_id}", response_model=AccountingPeriodResponse)
async def get_period(
    period_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> AccountingPeriodResponse:
    """Busca periodo por ID."""
    repo = AccountingPeriodRepository(db)
    period = repo.get_by_id(period_id)

    if not period or period.condominio_id != getattr(_current_user, "condominio_id", None):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Periodo nao encontrado",
        )

    return AccountingPeriodResponse.model_validate(period)


@router.post("/periods/{period_id}/open", status_code=201)
async def open_period(
    period_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Abre periodo contabil."""
    try:
        repo = AccountingPeriodRepository(db)
        period = repo.get_by_id(period_id)

        if not period or period.condominio_id != getattr(_current_user, "condominio_id", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Periodo nao encontrado",
            )

        if period.status != PeriodStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Periodo nao pode ser aberto",
            )

        period.status = PeriodStatus.OPEN
        period.opened_by = _current_user.id
        period.opened_at = datetime.utcnow()
        repo.update(period)
        db.commit()

        return {"message": "Periodo aberto com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao abrir periodo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao abrir periodo",
        ) from e


@router.post("/periods/{period_id}/close", status_code=201)
async def close_period(
    period_id: uuid.UUID,
    data: PeriodCloseRequest,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Fecha periodo contabil."""
    try:
        repo = AccountingPeriodRepository(db)
        period = repo.get_by_id(period_id)

        if not period or period.condominio_id != getattr(_current_user, "condominio_id", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Periodo nao encontrado",
            )

        if period.status != PeriodStatus.OPEN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Periodo nao pode ser fechado",
            )

        repo.close_period(
            period,
            closed_by=_current_user.id,
            closing_type=data.closing_type,
            notes=data.notes,
        )
        db.commit()

        return {"message": "Periodo fechado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao fechar periodo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao fechar periodo",
        ) from e


@router.post("/periods/{period_id}/reopen", status_code=201)
async def reopen_period(
    period_id: uuid.UUID,
    data: PeriodReopenRequest,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Reabre periodo contabil."""
    try:
        repo = AccountingPeriodRepository(db)
        period = repo.get_by_id(period_id)

        if not period or period.condominio_id != getattr(_current_user, "condominio_id", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Periodo nao encontrado",
            )

        if period.status != PeriodStatus.CLOSED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Periodo nao pode ser reaberto",
            )

        repo.reopen_period(
            period,
            reopened_by=_current_user.id,
            reason=data.reason,
        )
        db.commit()

        return {"message": "Periodo reaberto com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao reabrir periodo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao reabrir periodo",
        ) from e


# =============================================================================
# JournalEntry Endpoints
# =============================================================================


@router.get("/journal-entries", response_model=JournalEntryListResponse)
async def list_journal_entries(
    period_id: uuid.UUID | None = None,
    entry_type: EntryType | None = None,
    entry_status: EntryStatus | None = None,
    origin: EntryOrigin | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> JournalEntryListResponse:
    """Lista lancamentos contabeis."""
    try:
        repo = JournalEntryRepository(db)
        entries = repo.list_all(
            condominio_id=getattr(_current_user, "condominio_id", None),
            period_id=period_id,
            entry_type=entry_type,
            status=entry_status,
            origin=origin,
            date_from=date_from,
            date_to=date_to,
            skip=skip,
            limit=limit,
        )
        # Cada item é JournalEntryResponse; a resposta é o wrapper paginado (a tela lê .items)
        items = [JournalEntryResponse.model_validate(e) for e in entries]
        return JournalEntryListResponse(
            items=items,
            total=len(items),
            page=(skip // limit) + 1 if limit else 1,
            per_page=limit,
            pages=max(1, (len(items) + limit - 1) // limit) if limit else 1,
        )
    except Exception as e:
        logger.error(f"Erro ao listar lancamentos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar lancamentos",
        ) from e


@router.get("/journal-entries/pending-approval", response_model=list[JournalEntryListResponse])
async def list_pending_approval(
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> list[JournalEntryListResponse]:
    """Lista lancamentos pendentes de aprovacao."""
    try:
        repo = JournalEntryRepository(db)
        entries = repo.list_pending_approval(getattr(_current_user, "condominio_id", None))
        return [JournalEntryListResponse.model_validate(e) for e in entries]
    except Exception as e:
        logger.error(f"Erro ao listar lancamentos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar lancamentos",
        ) from e


@router.get("/journal-entries/stats", response_model=JournalStats)
async def get_journal_stats(
    period_id: uuid.UUID | None = None,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> JournalStats:
    """Retorna estatisticas dos lancamentos."""
    try:
        repo = JournalEntryRepository(db)
        stats = repo.get_stats(getattr(_current_user, "condominio_id", None), period_id)
        return JournalStats(**stats)
    except Exception as e:
        logger.error(f"Erro ao obter estatisticas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter estatisticas",
        ) from e


@router.post("/journal-entries", response_model=JournalEntryResponse, status_code=201)
async def create_journal_entry(
    data: JournalEntryCreate,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> JournalEntryResponse:
    """Cria um novo lancamento contabil."""
    try:
        repo = JournalEntryRepository(db)
        period_repo = AccountingPeriodRepository(db)

        # Verifica periodo
        period = period_repo.get_by_id(data.period_id)
        if not period or period.condominio_id != getattr(_current_user, "condominio_id", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Periodo nao encontrado",
            )

        if period.status != PeriodStatus.OPEN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Periodo nao esta aberto",
            )

        # Valida lancamento (debito = credito)
        total_debit = sum(line.debit_amount for line in data.lines)
        total_credit = sum(line.credit_amount for line in data.lines)

        if total_debit != total_credit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Lancamento desbalanceado: Debito={total_debit}, Credito={total_credit}",
            )

        entry_number = repo.generate_next_number(getattr(_current_user, "condominio_id", None))

        entry = JournalEntry(
            condominio_id=getattr(_current_user, "condominio_id", None),
            entry_number=entry_number,
            status=EntryStatus.DRAFT,
            created_by=_current_user.id,
            **data.model_dump(exclude={"entry_type", "origin", "lines"}),
        )

        if data.entry_type:
            entry.entry_type = data.entry_type
        if data.origin:
            entry.origin = data.origin

        # Cria partidas
        lines = []
        for i, line_data in enumerate(data.lines):
            line = JournalEntryLine(
                line_number=i + 1,
                **line_data.model_dump(),
            )
            lines.append(line)

        entry = repo.create_with_lines(entry, lines)
        db.commit()

        logger.info(f"Lancamento criado: {entry.entry_number}")
        return JournalEntryResponse.model_validate(entry)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao criar lancamento: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar lancamento",
        ) from e


@router.get("/journal-entries/{entry_id}", response_model=JournalEntryResponse)
async def get_journal_entry(
    entry_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> JournalEntryResponse:
    """Busca lancamento por ID."""
    repo = JournalEntryRepository(db)
    entry = repo.get_by_id(entry_id)

    if not entry or entry.condominio_id != getattr(_current_user, "condominio_id", None):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lancamento nao encontrado",
        )

    return JournalEntryResponse.model_validate(entry)


@router.get("/journal-entries/{entry_id}/lines", response_model=list[JournalEntryLineResponse])
async def get_entry_lines(
    entry_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> list[JournalEntryLineResponse]:
    """Lista partidas do lancamento."""
    entry_repo = JournalEntryRepository(db)
    line_repo = JournalEntryLineRepository(db)

    entry = entry_repo.get_by_id(entry_id, include_lines=False)
    if not entry or entry.condominio_id != getattr(_current_user, "condominio_id", None):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lancamento nao encontrado",
        )

    lines = line_repo.list_by_entry(entry_id)
    return [JournalEntryLineResponse.model_validate(line) for line in lines]


@router.post("/journal-entries/{entry_id}/post", status_code=201)
async def post_journal_entry(
    entry_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Contabiliza lancamento."""
    try:
        repo = JournalEntryRepository(db)
        entry = repo.get_by_id(entry_id)

        if not entry or entry.condominio_id != getattr(_current_user, "condominio_id", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lancamento nao encontrado",
            )

        if not entry.can_post:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lancamento nao pode ser contabilizado",
            )

        repo.post_entry(entry, _current_user.id)
        db.commit()

        return {"message": "Lancamento contabilizado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao contabilizar lancamento: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao contabilizar lancamento",
        ) from e


@router.post("/journal-entries/{entry_id}/approve", status_code=201)
async def approve_journal_entry(
    entry_id: uuid.UUID,
    data: JournalEntryApprovalRequest,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Aprova lancamento."""
    try:
        repo = JournalEntryRepository(db)
        entry = repo.get_by_id(entry_id)

        if not entry or entry.condominio_id != getattr(_current_user, "condominio_id", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lancamento nao encontrado",
            )

        if entry.status != EntryStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lancamento nao pode ser aprovado",
            )

        repo.approve_entry(entry, _current_user.id, data.notes)
        db.commit()

        return {"message": "Lancamento aprovado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao aprovar lancamento: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao aprovar lancamento",
        ) from e


@router.post("/journal-entries/{entry_id}/reject", status_code=201)
async def reject_journal_entry(
    entry_id: uuid.UUID,
    reason: str = Query(..., min_length=1),
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Rejeita lancamento."""
    try:
        repo = JournalEntryRepository(db)
        entry = repo.get_by_id(entry_id)

        if not entry or entry.condominio_id != getattr(_current_user, "condominio_id", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lancamento nao encontrado",
            )

        if entry.status != EntryStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lancamento nao pode ser rejeitado",
            )

        repo.reject_entry(entry, _current_user.id, reason)
        db.commit()

        return {"message": "Lancamento rejeitado"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao rejeitar lancamento: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao rejeitar lancamento",
        ) from e


@router.post("/journal-entries/{entry_id}/reverse", response_model=JournalEntryResponse, status_code=201)
async def reverse_journal_entry(
    entry_id: uuid.UUID,
    data: JournalEntryReversalRequest,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> JournalEntryResponse:
    """Estorna lancamento."""
    try:
        repo = JournalEntryRepository(db)
        line_repo = JournalEntryLineRepository(db)

        entry = repo.get_by_id(entry_id)
        if not entry or entry.condominio_id != getattr(_current_user, "condominio_id", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lancamento nao encontrado",
            )

        if not entry.can_reverse:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lancamento nao pode ser estornado",
            )

        # Cria lancamento de estorno
        reversal_number = repo.generate_next_number(getattr(_current_user, "condominio_id", None))

        reversal_entry = JournalEntry(
            condominio_id=getattr(_current_user, "condominio_id", None),
            period_id=entry.period_id,
            entry_number=reversal_number,
            description=f"Estorno de {entry.entry_number}: {data.reason}",
            entry_type=EntryType.REVERSAL,
            origin=entry.origin,
            status=EntryStatus.DRAFT,
            entry_date=data.reversal_date or date.today(),
            competence_date=entry.competence_date,
            is_reversal=True,
            created_by=_current_user.id,
        )

        # Inverte partidas
        original_lines = line_repo.list_by_entry(entry_id)
        reversal_lines = []

        for i, orig_line in enumerate(original_lines):
            reversal_line = JournalEntryLine(
                line_number=i + 1,
                account_id=orig_line.account_id,
                cost_center_id=orig_line.cost_center_id,
                debit_amount=orig_line.credit_amount,  # Inverte
                credit_amount=orig_line.debit_amount,  # Inverte
                description=f"Estorno: {orig_line.description or ''}",
            )
            reversal_lines.append(reversal_line)

        reversal_entry = repo.create_with_lines(reversal_entry, reversal_lines)

        # Marca original como estornado
        repo.reverse_entry(entry, reversal_entry, data.reason)
        db.commit()

        logger.info(f"Lancamento estornado: {entry.entry_number} -> {reversal_entry.entry_number}")
        return JournalEntryResponse.model_validate(reversal_entry)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao estornar lancamento: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao estornar lancamento",
        ) from e


# =============================================================================
# TrialBalance Endpoints
# =============================================================================


@router.get("/trial-balances", response_model=list[TrialBalanceListResponse])
async def list_trial_balances(
    chart_id: uuid.UUID | None = None,
    balance_type: BalanceType | None = None,
    balance_status: BalanceStatus | None = None,
    year: int | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> list[TrialBalanceListResponse]:
    """Lista balancetes."""
    try:
        repo = TrialBalanceRepository(db)
        balances = repo.list_all(
            condominio_id=getattr(_current_user, "condominio_id", None),
            chart_id=chart_id,
            balance_type=balance_type,
            status=balance_status,
            year=year,
            skip=skip,
            limit=limit,
        )
        return [TrialBalanceListResponse.model_validate(b) for b in balances]
    except Exception as e:
        logger.error(f"Erro ao listar balancetes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar balancetes",
        ) from e


@router.get("/trial-balances/latest", response_model=TrialBalanceResponse)
async def get_latest_balance(
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> TrialBalanceResponse:
    """Retorna ultimo balancete."""
    repo = TrialBalanceRepository(db)
    balance = repo.get_latest(getattr(_current_user, "condominio_id", None))

    if not balance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhum balancete encontrado",
        )

    return TrialBalanceResponse.model_validate(balance)


@router.get("/trial-balances/stats", response_model=BalanceStats)
async def get_balance_stats(
    year: int | None = None,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> BalanceStats:
    """Retorna estatisticas dos balancetes."""
    try:
        repo = TrialBalanceRepository(db)
        stats = repo.get_stats(getattr(_current_user, "condominio_id", None), year)
        return BalanceStats(**stats)
    except Exception as e:
        logger.error(f"Erro ao obter estatisticas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter estatisticas",
        ) from e


@router.post("/trial-balances", response_model=TrialBalanceResponse, status_code=201)
async def create_trial_balance(
    data: TrialBalanceCreate,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> TrialBalanceResponse:
    """Cria um novo balancete."""
    try:
        repo = TrialBalanceRepository(db)
        chart_repo = ChartOfAccountsRepository(db)
        # Repos para geracao de itens do balancete (uso futuro)
        _acc_repo = AccountingAccountRepository(db)  # noqa: F841
        _line_repo = JournalEntryLineRepository(db)  # noqa: F841

        # Verifica plano de contas
        chart = chart_repo.get_by_id(data.chart_id)
        if not chart or chart.condominio_id != getattr(_current_user, "condominio_id", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plano de contas nao encontrado",
            )

        code = repo.generate_next_code(
            getattr(_current_user, "condominio_id", None),
            data.year,
            data.month or data.reference_date.month,
        )

        balance = TrialBalance(
            condominio_id=getattr(_current_user, "condominio_id", None),
            code=code,
            status=BalanceStatus.DRAFT,
            created_by=_current_user.id,
            **data.model_dump(exclude={"balance_type", "balance_period"}),
        )

        if data.balance_type:
            balance.balance_type = data.balance_type
        if data.balance_period:
            balance.balance_period = data.balance_period

        balance = repo.create(balance)
        db.commit()

        logger.info(f"Balancete criado: {balance.code}")
        return TrialBalanceResponse.model_validate(balance)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao criar balancete: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar balancete",
        ) from e


@router.get("/trial-balances/{balance_id}", response_model=TrialBalanceResponse)
async def get_trial_balance(
    balance_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> TrialBalanceResponse:
    """Busca balancete por ID."""
    repo = TrialBalanceRepository(db)
    balance = repo.get_by_id(balance_id)

    if not balance or balance.condominio_id != getattr(_current_user, "condominio_id", None):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Balancete nao encontrado",
        )

    return TrialBalanceResponse.model_validate(balance)


@router.get("/trial-balances/{balance_id}/items", response_model=list[TrialBalanceItemResponse])
async def get_balance_items(
    balance_id: uuid.UUID,
    account_type: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=1000),
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> list[TrialBalanceItemResponse]:
    """Lista itens do balancete."""
    balance_repo = TrialBalanceRepository(db)
    item_repo = TrialBalanceItemRepository(db)

    balance = balance_repo.get_by_id(balance_id)
    if not balance or balance.condominio_id != getattr(_current_user, "condominio_id", None):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Balancete nao encontrado",
        )

    items = item_repo.list_by_balance(balance_id, account_type, skip, limit)
    return [TrialBalanceItemResponse.model_validate(item) for item in items]


@router.post("/trial-balances/{balance_id}/generate", status_code=201)
async def generate_trial_balance(  # pylint: disable=too-many-locals
    balance_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Gera balancete a partir dos lancamentos."""
    try:
        balance_repo = TrialBalanceRepository(db)
        item_repo = TrialBalanceItemRepository(db)
        acc_repo = AccountingAccountRepository(db)
        line_repo = JournalEntryLineRepository(db)

        balance = balance_repo.get_by_id(balance_id)
        if not balance or balance.condominio_id != getattr(_current_user, "condominio_id", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Balancete nao encontrado",
            )

        if balance.status not in [BalanceStatus.DRAFT, BalanceStatus.GENERATED]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Balancete nao pode ser gerado",
            )

        start_time = datetime.utcnow()

        # Remove itens anteriores
        item_repo.delete_by_balance(balance_id)

        # Busca contas do plano
        accounts = acc_repo.list_analytical(balance.chart_id)

        items = []
        total_debit = Decimal("0")
        total_credit = Decimal("0")

        for account in accounts:
            # Calcula saldos
            balance_data = line_repo.get_account_balance(
                account.id,
                balance.start_date,
                balance.end_date,
            )

            item = TrialBalanceItem(
                trial_balance_id=balance.id,
                account_id=account.id,
                account_code=account.code,
                account_name=account.name,
                account_type=account.account_type.value if account.account_type else "",
                account_nature=account.nature.value if account.nature else "",
                account_level=account.level or 1,
                is_analytical=True,
                period_debit=Decimal(str(balance_data["total_debit"])),
                period_credit=Decimal(str(balance_data["total_credit"])),
                current_balance=Decimal(str(balance_data["balance"])),
            )

            if item.current_balance >= 0:
                item.current_debit = abs(item.current_balance)
                item.current_credit = Decimal("0")
            else:
                item.current_debit = Decimal("0")
                item.current_credit = abs(item.current_balance)

            items.append(item)
            total_debit += item.current_debit
            total_credit += item.current_credit

        item_repo.create_batch(items)

        # Atualiza balancete
        end_time = datetime.utcnow()
        balance.status = BalanceStatus.GENERATED
        balance.generated_at = end_time
        balance.generated_by = _current_user.id
        balance.generation_time_ms = int((end_time - start_time).total_seconds() * 1000)
        balance.total_accounts = len(items)
        balance.total_analytical = len(items)
        balance.current_debit_total = total_debit
        balance.current_credit_total = total_credit
        balance.is_balanced = total_debit == total_credit
        balance.difference_amount = abs(total_debit - total_credit)

        balance_repo.update(balance)
        db.commit()

        return {
            "message": "Balancete gerado com sucesso",
            "total_accounts": len(items),
            "is_balanced": balance.is_balanced,
            "generation_time_ms": balance.generation_time_ms,
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao gerar balancete: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar balancete",
        ) from e


@router.post("/trial-balances/{balance_id}/approve", status_code=201)
async def approve_trial_balance(
    balance_id: uuid.UUID,
    notes: str | None = None,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Aprova balancete."""
    try:
        repo = TrialBalanceRepository(db)
        balance = repo.get_by_id(balance_id)

        if not balance or balance.condominio_id != getattr(_current_user, "condominio_id", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Balancete nao encontrado",
            )

        if not balance.can_approve:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Balancete nao pode ser aprovado",
            )

        repo.approve(balance, _current_user.id, notes)
        db.commit()

        return {"message": "Balancete aprovado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao aprovar balancete: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao aprovar balancete",
        ) from e


@router.post("/trial-balances/{balance_id}/publish", status_code=201)
async def publish_trial_balance(
    balance_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Publica balancete."""
    try:
        repo = TrialBalanceRepository(db)
        balance = repo.get_by_id(balance_id)

        if not balance or balance.condominio_id != getattr(_current_user, "condominio_id", None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Balancete nao encontrado",
            )

        if not balance.can_publish:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Balancete nao pode ser publicado",
            )

        repo.publish(balance, _current_user.id)
        db.commit()

        return {"message": "Balancete publicado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao publicar balancete: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao publicar balancete",
        ) from e


# ═══════════════════════════════════════════════════════════════
# ACCOUNTING ENTRIES — lançamentos reais da accounting_entries
# ═══════════════════════════════════════════════════════════════


def _get_raw_conn():
    """Conexão psycopg2 direta à DB."""
    url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    return psycopg2.connect(url)


@router.get("/entries")
async def list_accounting_entries(
    periodo: str | None = Query(None, description="Período YYYY-MM"),
    tipo: str | None = Query(None, description="Tipo de lançamento"),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    _current_user: dict = Depends(get_current_user),
) -> list:
    """Lista lançamentos da accounting_entries."""
    try:
        conn = _get_raw_conn()
        cur = conn.cursor()
        filters = []
        params: list = []
        if periodo:
            filters.append("periodo_competencia = %s")
            params.append(periodo)
        if tipo:
            filters.append("tipo_lancamento = %s")
            params.append(tipo)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        cur.execute(
            f"""
            SELECT id, data_lancamento::text, conta_debito, conta_credito,
                   valor::float, historico, tipo_lancamento, documento_ref,
                   periodo_competencia, status, created_at::text
            FROM accounting_entries
            {where}
            ORDER BY data_lancamento DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        cur.close()
        conn.close()
        return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        logger.error(f"Erro ao listar accounting_entries: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/dashboard")
async def accounting_dashboard(
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Dashboard resumido dos lançamentos contábeis."""
    try:
        conn = _get_raw_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                count(*) as total_lancamentos,
                coalesce(sum(CASE WHEN tipo_lancamento = 'nfse_emitida' THEN valor END), 0)::float as receita_nfse,
                coalesce(sum(CASE WHEN tipo_lancamento = 'banco_inter' THEN valor END), 0)::float as movimentacao_inter,
                coalesce(sum(valor), 0)::float as total_movimentado,
                count(DISTINCT periodo_competencia) as periodos,
                min(data_lancamento)::text as primeiro_lancamento,
                max(data_lancamento)::text as ultimo_lancamento
            FROM accounting_entries
            WHERE status = 'confirmado'
        """)
        row = cur.fetchone()
        cols = [d[0] for d in cur.description]
        summary = dict(zip(cols, row, strict=False))

        cur.execute("""
            SELECT periodo_competencia, count(*) as lancamentos, sum(valor)::float as total
            FROM accounting_entries
            WHERE status = 'confirmado'
            GROUP BY periodo_competencia
            ORDER BY periodo_competencia DESC
            LIMIT 12
        """)
        periodos = [dict(zip([d[0] for d in cur.description], r, strict=False)) for r in cur.fetchall()]

        cur.execute("""
            SELECT tipo_lancamento, count(*) as lancamentos, sum(valor)::float as total
            FROM accounting_entries
            GROUP BY tipo_lancamento
        """)
        tipos = [dict(zip([d[0] for d in cur.description], r, strict=False)) for r in cur.fetchall()]

        cur.close()
        conn.close()
        return {"summary": summary, "by_periodo": periodos, "by_tipo": tipos}
    except Exception as e:
        logger.error(f"Erro no accounting dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/balancete")
async def accounting_balancete(
    periodo: str | None = Query(None, description="Período YYYY-MM (default: último período)"),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Balancete de verificação a partir dos lançamentos contábeis."""
    try:
        conn = _get_raw_conn()
        cur = conn.cursor()

        if not periodo:
            cur.execute("SELECT max(periodo_competencia) FROM accounting_entries WHERE status='confirmado'")
            row = cur.fetchone()
            periodo = row[0] if row else None

        cur.execute(
            """
            SELECT
                conta_debito as conta,
                'debito' as natureza,
                sum(valor)::float as total,
                count(*) as lancamentos
            FROM accounting_entries
            WHERE status = 'confirmado'
              AND (%s IS NULL OR periodo_competencia = %s)
            GROUP BY conta_debito
            UNION ALL
            SELECT
                conta_credito as conta,
                'credito' as natureza,
                sum(valor)::float as total,
                count(*) as lancamentos
            FROM accounting_entries
            WHERE status = 'confirmado'
              AND (%s IS NULL OR periodo_competencia = %s)
            GROUP BY conta_credito
            ORDER BY conta, natureza
        """,
            [periodo, periodo, periodo, periodo],
        )

        rows = [dict(zip([d[0] for d in cur.description], r, strict=False)) for r in cur.fetchall()]
        total_debitos = sum(r["total"] for r in rows if r["natureza"] == "debito")
        total_creditos = sum(r["total"] for r in rows if r["natureza"] == "credito")
        cur.close()
        conn.close()

        return {
            "periodo": periodo,
            "items": rows,
            "total_debitos": total_debitos,
            "total_creditos": total_creditos,
            "equilibrado": abs(total_debitos - total_creditos) < 0.01,
        }
    except Exception as e:
        logger.error(f"Erro no balancete: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/dre")
async def accounting_dre(
    periodo: str | None = Query(None, description="Período YYYY-MM"),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """DRE simplificada a partir dos lançamentos contábeis."""
    try:
        conn = _get_raw_conn()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                sum(CASE WHEN conta_credito LIKE '3.1%%' THEN valor ELSE 0 END)::float as receita_bruta,
                sum(CASE WHEN conta_debito LIKE '3.2%%' THEN valor ELSE 0 END)::float as despesas_operacionais,
                sum(CASE WHEN tipo_lancamento = 'nfse_emitida' THEN valor ELSE 0 END)::float as receita_servicos,
                count(*) as total_lancamentos
            FROM accounting_entries
            WHERE status = 'confirmado'
              AND (%s IS NULL OR periodo_competencia = %s)
        """,
            [periodo, periodo],
        )

        row = cur.fetchone()
        cols = [d[0] for d in cur.description]
        data = dict(zip(cols, row, strict=False))

        receita = data.get("receita_bruta", 0) or 0
        despesas = data.get("despesas_operacionais", 0) or 0
        cur.close()
        conn.close()

        return {
            "periodo": periodo,
            "receita_bruta": receita,
            "deducoes": 0.0,
            "receita_liquida": receita,
            "despesas_operacionais": despesas,
            "resultado_operacional": receita - despesas,
            "receita_servicos_nfse": data.get("receita_servicos", 0),
            "total_lancamentos": data.get("total_lancamentos", 0),
        }
    except Exception as e:
        logger.error(f"Erro no DRE: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
