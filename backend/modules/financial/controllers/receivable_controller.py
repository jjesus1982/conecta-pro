"""Controller para contas a receber."""

import logging
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_session
from modules.financial.models.receivable_account import ReceivableStatus
from modules.financial.publishers import (
    publish_inadimplencia_detectada,
    publish_pagamento_recebido,
)
from modules.financial.schemas.receivable import (
    ReceivableAccountCreate,
    ReceivableAccountFilter,
    ReceivableAccountListResponse,
    ReceivableAccountResponse,
    ReceivableAccountStats,
    ReceivableAccountUpdate,
    ReceivableInstallmentRenegotiateRequest,
    ReceivableInstallmentResponse,
    ReceivableInstallmentUpdate,
    ReceivablePaymentCreate,
    ReceivablePaymentResponse,
    ReceivableProtestRequest,
    ReceivableWriteOffRequest,
)
from modules.financial.services.receivable_ai_service import ReceivableAIService
from modules.financial.services.receivable_service import ReceivableService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/receivables", tags=["Contas a Receber"])


def get_service(session: AsyncSession = Depends(get_session)) -> ReceivableService:
    """Retorna instancia do service."""
    return ReceivableService(session)


def get_ai_service(session: AsyncSession = Depends(get_session)) -> ReceivableAIService:
    """Retorna instancia do AI service."""
    return ReceivableAIService(session)


# ==================== CONTAS ====================


@router.post(
    "",
    response_model=ReceivableAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar conta a receber",
)
async def create_account(
    data: ReceivableAccountCreate,
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> ReceivableAccountResponse:
    """Cria uma nova conta a receber."""
    try:
        account = await service.create_account(data, current_user.id)
        return ReceivableAccountResponse.model_validate(account)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao criar conta: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar conta a receber",
        )


@router.get(
    "",
    summary="Listar contas a receber",
)
async def list_accounts(  # pylint: disable=too-many-locals
    condominio_id: UUID | None = Query(None, description="ID do condomínio"),
    search: str | None = Query(None, description="Busca na descricao"),
    customer_id: UUID | None = Query(None, description="Filtrar por cliente"),
    unidade_id: UUID | None = Query(None, description="Filtrar por unidade"),
    category_id: UUID | None = Query(None, description="Filtrar por categoria"),
    status_filter: str | None = Query(None, alias="status", description="Status"),
    due_date_start: date | None = Query(None, description="Vencimento inicial"),
    due_date_end: date | None = Query(None, description="Vencimento final"),
    is_recurring: bool | None = Query(None, description="Apenas recorrentes"),
    is_overdue: bool | None = Query(None, description="Apenas vencidas"),
    min_value: float | None = Query(None, description="Valor minimo"),
    max_value: float | None = Query(None, description="Valor maximo"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service: ReceivableService = Depends(get_service),
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """Lista contas a receber com filtros, retornando wrapper paginado."""
    # fallback JWT — inferir condominio_id do usuário logado; None = visão global (admin)
    effective_cid = condominio_id or getattr(current_user, "condominio_id", None)
    filters = ReceivableAccountFilter(
        search=search,
        customer_id=customer_id,
        unidade_id=unidade_id,
        category_id=category_id,
        status=ReceivableStatus(status_filter) if status_filter else None,
        due_date_start=due_date_start,
        due_date_end=due_date_end,
        is_recurring=is_recurring,
        is_overdue=is_overdue,
        min_value=str(min_value) if min_value else None,
        max_value=str(max_value) if max_value else None,
    )

    accounts, total = await service.list_accounts(effective_cid, filters, skip, limit)
    page = (skip // limit) + 1 if limit else 1
    # Gap 3: formato {data, meta} conforme spec
    return {
        "data": [ReceivableAccountListResponse.model_validate(a) for a in accounts],
        "meta": {
            "total": total,
            "page": page,
            "per_page": limit,
            "total_pages": (total + limit - 1) // limit if limit else 1,
        },
    }


@router.get(
    "/stats",
    response_model=ReceivableAccountStats,
    summary="Estatisticas de contas a receber",
)
async def get_stats(
    condominio_id: UUID | None = Query(None, description="ID do condomínio (opcional)"),
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ReceivableAccountStats:
    """Retorna estatisticas de contas a receber."""
    return await service.get_stats(condominio_id)


@router.get(
    "/overdue",
    response_model=list[ReceivableAccountListResponse],
    summary="Contas vencidas",
)
async def get_overdue(
    condominio_id: UUID | None = Query(None, description="ID do condomínio (opcional)"),
    limit: int = Query(100, ge=1, le=500),
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[ReceivableAccountListResponse]:
    """Retorna contas vencidas."""
    accounts = await service.get_overdue_accounts(condominio_id, limit)
    return [ReceivableAccountListResponse.model_validate(a) for a in accounts]


@router.get(
    "/receivables-aging",
    summary="Aging de contas a receber",
)
async def get_receivables_aging(
    condominio_id: UUID | None = Query(None),
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Relatório de aging — contas a receber vencidas por faixa de dias."""
    from sqlalchemy import text

    today = date.today()
    filters = "AND condominio_id = :cid" if condominio_id else ""
    params: dict[str, Any] = {"today": today}
    if condominio_id:
        params["cid"] = condominio_id

    query = text(f"""
        SELECT
            CASE
                WHEN :today - due_date BETWEEN 1 AND 30  THEN 'ate_30_dias'
                WHEN :today - due_date BETWEEN 31 AND 60 THEN '31_a_60_dias'
                WHEN :today - due_date BETWEEN 61 AND 90 THEN '61_a_90_dias'
                WHEN :today - due_date > 90              THEN 'acima_90_dias'
                ELSE 'a_vencer'
            END AS faixa,
            COUNT(*)                           AS quantidade,
            COALESCE(SUM(net_value), 0)        AS valor_total
        FROM receivable_accounts
        WHERE status NOT IN ('paga', 'cancelada', 'cancelado')
          {filters}
        GROUP BY 1
        ORDER BY 1
    """)

    result = await service.session.execute(query, params)
    rows = result.fetchall()

    faixas = [{"faixa": r.faixa, "quantidade": r.quantidade, "valor_total": float(r.valor_total)} for r in rows]
    return {
        "aging_date": str(today),
        "tipo": "contas_receber",
        "faixas": faixas,
        "total_em_aberto": sum(f["valor_total"] for f in faixas),
        "total_vencido": sum(f["valor_total"] for f in faixas if f["faixa"] != "a_vencer"),
    }


@router.get(
    "/aging",
    summary="Aging de contas a receber (alias)",
)
async def get_receivables_aging_short(
    condominio_id: UUID | None = Query(None),
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Alias para /receivables-aging — relatório de aging por faixas de dias."""
    return await get_receivables_aging(condominio_id, service, current_user)


@router.get(
    "/{account_id}",
    response_model=ReceivableAccountResponse,
    summary="Buscar conta a receber",
)
async def get_account(
    account_id: UUID,
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ReceivableAccountResponse:
    """Busca conta por ID."""
    account = await service.get_account(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta nao encontrada",
        )
    return ReceivableAccountResponse.model_validate(account)


@router.put(
    "/{account_id}",
    response_model=ReceivableAccountResponse,
    summary="Atualizar conta a receber",
)
async def update_account(
    account_id: UUID,
    data: ReceivableAccountUpdate,
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> ReceivableAccountResponse:
    """Atualiza uma conta a receber."""
    try:
        account = await service.update_account(account_id, data, current_user.id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta nao encontrada",
            )
        return ReceivableAccountResponse.model_validate(account)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir conta a receber",
)
async def delete_account(
    account_id: UUID,
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> None:
    """Exclui uma conta a receber (soft delete)."""
    try:
        deleted = await service.delete_account(account_id, current_user.id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta nao encontrada",
            )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==================== CANCELAMENTO/SUSPENSAO ====================


@router.post(
    "/{account_id}/cancel", response_model=ReceivableAccountResponse, summary="Cancelar conta", status_code=201
)
async def cancel_account(
    account_id: UUID,
    reason: str = Query(..., min_length=5, description="Motivo do cancelamento"),
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> ReceivableAccountResponse:
    """Cancela uma conta a receber."""
    try:
        account = await service.cancel_account(account_id, current_user.id, reason)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta nao encontrada",
            )
        return ReceivableAccountResponse.model_validate(account)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{account_id}/suspend", response_model=ReceivableAccountResponse, summary="Suspender conta", status_code=201
)
async def suspend_account(
    account_id: UUID,
    reason: str = Query(..., min_length=5, description="Motivo da suspensao"),
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> ReceivableAccountResponse:
    """Suspende uma conta a receber."""
    try:
        account = await service.suspend_account(account_id, current_user.id, reason)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta nao encontrada",
            )
        # Publisher GEDEON Event Bus — inadimplência detectada
        try:
            import asyncio

            asyncio.create_task(
                publish_inadimplencia_detectada(
                    account_id=str(account_id),
                    tipo="suspensao",
                    motivo=reason,
                    cliente_id=str(getattr(account, "cliente_id", "") or ""),
                    valor=float(getattr(account, "amount", 0) or 0),
                )
            )
        except Exception:
            pass
        return ReceivableAccountResponse.model_validate(account)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==================== PROTESTO/BAIXA ====================


@router.post(
    "/{account_id}/protest", response_model=ReceivableAccountResponse, summary="Enviar para protesto", status_code=201
)
async def protest_account(
    account_id: UUID,
    data: ReceivableProtestRequest,
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> ReceivableAccountResponse:
    """Envia conta para protesto."""
    try:
        account = await service.protest_account(account_id, current_user.id, data.protest_number)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta nao encontrada",
            )
        # Publisher GEDEON Event Bus — inadimplência: protesto
        try:
            import asyncio

            asyncio.create_task(
                publish_inadimplencia_detectada(
                    account_id=str(account_id),
                    tipo="protesto",
                    motivo=f"Protesto #{data.protest_number}",
                    cliente_id=str(getattr(account, "cliente_id", "") or ""),
                    valor=float(getattr(account, "amount", 0) or 0),
                )
            )
        except Exception:
            pass
        return ReceivableAccountResponse.model_validate(account)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{account_id}/write-off",
    response_model=ReceivableAccountResponse,
    summary="Baixar conta (perda, status_code=201)",
)
async def write_off_account(
    account_id: UUID,
    data: ReceivableWriteOffRequest,
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> ReceivableAccountResponse:
    """Baixa conta como perda."""
    try:
        account = await service.write_off_account(account_id, current_user.id, data.reason)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta nao encontrada",
            )
        # Publisher GEDEON Event Bus — inadimplência: baixa como perda
        try:
            import asyncio

            asyncio.create_task(
                publish_inadimplencia_detectada(
                    account_id=str(account_id),
                    tipo="baixa_perda",
                    motivo=data.reason,
                    cliente_id=str(getattr(account, "cliente_id", "") or ""),
                    valor=float(getattr(account, "amount", 0) or 0),
                )
            )
        except Exception:
            pass
        return ReceivableAccountResponse.model_validate(account)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==================== PARCELAS ====================


@router.get(
    "/installments/pending",
    response_model=list[ReceivableInstallmentResponse],
    summary="Parcelas pendentes",
)
async def get_pending_installments(
    condominio_id: UUID | None = Query(None, description="ID do condomínio"),
    due_date_start: date | None = Query(None),
    due_date_end: date | None = Query(None),
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[ReceivableInstallmentResponse]:
    """Retorna parcelas pendentes."""
    installments = await service.get_pending_installments(condominio_id, due_date_start, due_date_end)
    return [ReceivableInstallmentResponse.model_validate(i) for i in installments]


@router.get(
    "/{account_id}/installments",
    response_model=list[ReceivableInstallmentResponse],
    summary="Listar parcelas",
)
async def list_installments(
    account_id: UUID,
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[ReceivableInstallmentResponse]:
    """Lista parcelas de uma conta."""
    installments = await service.list_installments(account_id)
    return [ReceivableInstallmentResponse.model_validate(i) for i in installments]


@router.get(
    "/installments/{installment_id}",
    response_model=ReceivableInstallmentResponse,
    summary="Buscar parcela",
)
async def get_installment(
    installment_id: UUID,
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ReceivableInstallmentResponse:
    """Busca parcela por ID."""
    installment = await service.get_installment(installment_id)
    if not installment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parcela nao encontrada",
        )
    return ReceivableInstallmentResponse.model_validate(installment)


@router.put(
    "/installments/{installment_id}",
    response_model=ReceivableInstallmentResponse,
    summary="Atualizar parcela",
)
async def update_installment(
    installment_id: UUID,
    data: ReceivableInstallmentUpdate,
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ReceivableInstallmentResponse:
    """Atualiza uma parcela."""
    try:
        installment = await service.update_installment(installment_id, data)
        if not installment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parcela nao encontrada",
            )
        return ReceivableInstallmentResponse.model_validate(installment)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/installments/{installment_id}/renegotiate",
    response_model=ReceivableInstallmentResponse,
    summary="Renegociar parcela",
    status_code=201,
)
async def renegotiate_installment(
    installment_id: UUID,
    data: ReceivableInstallmentRenegotiateRequest,
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> ReceivableInstallmentResponse:
    """Renegocia uma parcela."""
    try:
        installment = await service.renegotiate_installment(installment_id, data, current_user.id)
        if not installment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parcela nao encontrada",
            )
        return ReceivableInstallmentResponse.model_validate(installment)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==================== BOLETO/PIX ====================


# ==================== RECEBIMENTOS ====================


@router.post(
    "/installments/{installment_id}/pay",
    response_model=ReceivablePaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar recebimento",
)
async def register_payment(
    installment_id: UUID,
    data: ReceivablePaymentCreate,
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> ReceivablePaymentResponse:
    """Registra recebimento de uma parcela."""
    try:
        payment = await service.register_payment(installment_id, data, current_user.id)
        # Publisher GEDEON Event Bus — pagamento recebido
        try:
            import asyncio

            asyncio.create_task(
                publish_pagamento_recebido(
                    payment_id=str(payment.id),
                    installment_id=str(installment_id),
                    valor=float(getattr(payment, "amount_paid", 0) or 0),
                    cliente_id=str(getattr(payment, "cliente_id", "") or ""),
                    condominio_id=str(getattr(payment, "condominio_id", "") or ""),
                )
            )
        except Exception:
            pass
        return ReceivablePaymentResponse.model_validate(payment)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==================== NOTIFICACOES ====================


# ==================== ACORDO ====================


# ==================== DIVIDAS ====================


# ==================== IA ====================


@router.get("/aging/pdf", summary="Aging em PDF (marca Conecta)")
async def receivable_aging_pdf(
    condominio_id: UUID | None = Query(None),
    service: ReceivableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
):
    from fastapi.responses import Response as _R

    from modules.financial.services.relatorio_financeiro_pdf import aging_pdf_bytes

    dados = await get_receivables_aging(condominio_id=condominio_id, service=service, current_user=current_user)
    pdf = aging_pdf_bytes(dados, "Contas a Receber — Aging")
    return _R(content=pdf, media_type="application/pdf",
              headers={"Content-Disposition": 'inline; filename="aging_receivable.pdf"'})


# ── Cobrança bancária da conta a receber (07/09/2026) ────────────────────────────────────
# Boleto/PIX nasce aqui, não no app do banco: Eletrônica → Inter, Patrimonial → Cora, pela
# empresa credora da conta. Emitir é registrar a cobrança no banco; dinheiro não sai.
@router.post("/{receivable_id}/emitir-cobranca", summary="Emite boleto/PIX no banco da empresa credora")
async def emitir_cobranca_recebivel(
    receivable_id: UUID,
    preview: bool = Query(False, description="true = só mostra o que seria emitido"),
    current_user: dict = Depends(get_current_user),
) -> dict:
    from starlette.concurrency import run_in_threadpool

    from modules.financial.services.cobranca_recebivel_service import emitir

    r = await run_in_threadpool(emitir, str(receivable_id), preview)
    if r.get("erro"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=r["erro"])
    return r


@router.post("/emitir-cobranca-por-nota/{chave_acesso}", summary="Fluxo nota → boleto: emite a cobrança da conta a receber que corresponde à NFS-e")
async def emitir_cobranca_por_nota(
    chave_acesso: str,
    preview: bool = Query(False, description="true = só mostra o que seria emitido"),
    current_user: dict = Depends(get_current_user),
) -> dict:
    from starlette.concurrency import run_in_threadpool

    from modules.financial.services.cobranca_recebivel_service import emitir_por_nota

    r = await run_in_threadpool(emitir_por_nota, chave_acesso, preview)
    if r.get("erro"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=r["erro"])
    return r


@router.post("/emitir-cobrancas-mes", summary="Emite boleto/PIX de todas as contas em aberto do mês ainda sem cobrança")
async def emitir_cobrancas_mes(
    ano: int = Query(..., ge=2020, le=2100), mes: int = Query(..., ge=1, le=12),
    preview: bool = Query(True, description="false = emite de verdade"),
    current_user: dict = Depends(get_current_user),
) -> dict:
    from starlette.concurrency import run_in_threadpool

    from modules.financial.services.cobranca_recebivel_service import emitir_pendentes_mes

    return await run_in_threadpool(emitir_pendentes_mes, ano, mes, preview)
