"""Controller para contas a pagar."""

import logging
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_session
from modules.financial.models.payable_account import PayableStatus
from modules.financial.publishers import publish_pagamento_realizado
from modules.financial.schemas.payable import (
    PayableAccountCreate,
    PayableAccountFilter,
    PayableAccountListResponse,
    PayableAccountResponse,
    PayableAccountStats,
    PayableAccountUpdate,
    PayableBulkApproveRequest,
    PayableBulkPaymentRequest,
    PayableInstallmentRenegotiateRequest,
    PayableInstallmentResponse,
    PayableInstallmentUpdate,
    PayablePaymentCreate,
    PayablePaymentReconcileRequest,
    PayablePaymentResponse,
    PayablePaymentReverseRequest,
    PayableScheduleRequest,
)
from modules.financial.services.payable_service import PayableService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payables", tags=["Contas a Pagar"])


def get_service(session: AsyncSession = Depends(get_session)) -> PayableService:
    """Retorna instância do service."""
    return PayableService(session)


# ==================== CONTAS ====================


@router.post(
    "",
    response_model=PayableAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar conta a pagar",
)
async def create_account(
    data: PayableAccountCreate,
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> PayableAccountResponse:
    """Cria uma nova conta a pagar."""
    try:
        account = await service.create_account(data, current_user.id)
        return PayableAccountResponse.model_validate(account)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao criar conta: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar conta a pagar",
        )


@router.get(
    "",
    summary="Listar contas a pagar",
)
async def list_accounts(  # pylint: disable=too-many-locals
    condominio_id: UUID | None = Query(None, description="ID do condomínio"),
    search: str | None = Query(None, description="Busca na descrição"),
    supplier_id: UUID | None = Query(None, description="Filtrar por fornecedor"),
    category_id: UUID | None = Query(None, description="Filtrar por categoria"),
    status_filter: str | None = Query(None, alias="status", description="Status"),
    due_date_start: date | None = Query(None, description="Vencimento inicial"),
    due_date_end: date | None = Query(None, description="Vencimento final"),
    is_recurring: bool | None = Query(None, description="Apenas recorrentes"),
    is_overdue: bool | None = Query(None, description="Apenas vencidas"),
    min_value: float | None = Query(None, description="Valor mínimo"),
    max_value: float | None = Query(None, description="Valor máximo"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service: PayableService = Depends(get_service),
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """Lista contas a pagar com filtros, retornando wrapper paginado."""
    # fallback JWT — inferir condominio_id do usuário logado; None = visão global (admin)
    effective_cid = condominio_id or getattr(current_user, "condominio_id", None)
    filters = PayableAccountFilter(
        search=search,
        supplier_id=supplier_id,
        category_id=category_id,
        status=PayableStatus(status_filter) if status_filter else None,
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
        "data": [PayableAccountListResponse.model_validate(a) for a in accounts],
        "meta": {
            "total": total,
            "page": page,
            "per_page": limit,
            "total_pages": (total + limit - 1) // limit if limit else 1,
        },
    }


@router.get(
    "/stats",
    response_model=PayableAccountStats,
    summary="Estatísticas de contas a pagar",
)
async def get_stats(
    condominio_id: UUID | None = Query(None, description="ID do condomínio (opcional)"),
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> PayableAccountStats:
    """Retorna estatísticas de contas a pagar."""
    return await service.get_stats(condominio_id)


@router.get(
    "/overdue",
    response_model=list[PayableAccountListResponse],
    summary="Contas vencidas",
)
async def get_overdue(
    condominio_id: UUID | None = Query(None, description="ID do condomínio (opcional)"),
    limit: int = Query(100, ge=1, le=500),
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[PayableAccountListResponse]:
    """Retorna contas vencidas."""
    accounts = await service.get_overdue_accounts(condominio_id, limit)
    return [PayableAccountListResponse.model_validate(a) for a in accounts]


@router.get(
    "/due-soon",
    response_model=list[PayableAccountListResponse],
    summary="Contas a vencer",
)
async def get_due_soon(
    condominio_id: UUID | None = Query(None, description="ID do condomínio"),
    days: int = Query(7, ge=1, le=90, description="Dias para vencimento"),
    limit: int = Query(100, ge=1, le=500),
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[PayableAccountListResponse]:
    """Retorna contas a vencer nos próximos dias."""
    accounts = await service.get_due_soon_accounts(condominio_id, days, limit)
    return [PayableAccountListResponse.model_validate(a) for a in accounts]


@router.get(
    "/payables-aging",
    summary="Aging de contas a pagar",
)
async def get_payables_aging(
    condominio_id: UUID | None = Query(None),
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Relatório de aging — contas a pagar vencidas por faixa de dias."""
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
        FROM payable_accounts
        WHERE status NOT IN ('pago', 'cancelado')
          AND ativo = TRUE
          {filters}
        GROUP BY 1
        ORDER BY 1
    """)

    result = await service.session.execute(query, params)
    rows = result.fetchall()

    faixas = [{"faixa": r.faixa, "quantidade": r.quantidade, "valor_total": float(r.valor_total)} for r in rows]
    return {
        "aging_date": str(today),
        "tipo": "contas_pagar",
        "faixas": faixas,
        "total_em_aberto": sum(f["valor_total"] for f in faixas),
        "total_vencido": sum(f["valor_total"] for f in faixas if f["faixa"] != "a_vencer"),
    }


@router.get(
    "/aging",
    summary="Aging de contas a pagar (alias)",
)
async def get_payables_aging_short(
    condominio_id: UUID | None = Query(None),
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Alias para /payables-aging — relatório de aging por faixas de dias."""
    return await get_payables_aging(condominio_id, service, current_user)


@router.get(
    "/{account_id}",
    response_model=PayableAccountResponse,
    summary="Buscar conta a pagar",
)
async def get_account(
    account_id: UUID,
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> PayableAccountResponse:
    """Busca conta por ID."""
    account = await service.get_account(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta não encontrada",
        )
    return PayableAccountResponse.model_validate(account)


@router.put(
    "/{account_id}",
    response_model=PayableAccountResponse,
    summary="Atualizar conta a pagar",
)
async def update_account(
    account_id: UUID,
    data: PayableAccountUpdate,
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> PayableAccountResponse:
    """Atualiza uma conta a pagar."""
    try:
        account = await service.update_account(account_id, data, current_user.id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta não encontrada",
            )
        return PayableAccountResponse.model_validate(account)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir conta a pagar",
)
async def delete_account(
    account_id: UUID,
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> None:
    """Exclui uma conta a pagar (soft delete)."""
    try:
        deleted = await service.delete_account(account_id, current_user.id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta não encontrada",
            )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==================== APROVAÇÃO ====================


@router.post("/{account_id}/approve", response_model=PayableAccountResponse, summary="Aprovar conta", status_code=201)
async def approve_account(
    account_id: UUID,
    notes: str | None = None,
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> PayableAccountResponse:
    """Aprova uma conta para pagamento."""
    try:
        account = await service.approve_account(account_id, current_user.id, notes)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta não encontrada",
            )
        return PayableAccountResponse.model_validate(account)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/bulk-approve", summary="Aprovar múltiplas contas", status_code=201)
async def bulk_approve(
    data: PayableBulkApproveRequest,
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> dict[str, int]:
    """Aprova múltiplas contas."""
    success, errors = await service.bulk_approve(data, current_user.id)
    return {
        "success_count": success,
        "error_count": errors,
        "total": len(data.account_ids),
    }


@router.post("/{account_id}/reject", response_model=PayableAccountResponse, summary="Rejeitar conta", status_code=201)
async def reject_account(
    account_id: UUID,
    reason: str = Query(..., min_length=5, description="Motivo da rejeição"),
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> PayableAccountResponse:
    """Rejeita uma conta."""
    try:
        account = await service.reject_account(account_id, current_user.id, reason)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta não encontrada",
            )
        return PayableAccountResponse.model_validate(account)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==================== AGENDAMENTO ====================


@router.post(
    "/{account_id}/schedule", response_model=PayableAccountResponse, summary="Agendar pagamento", status_code=201
)
async def schedule_payment(
    account_id: UUID,
    data: PayableScheduleRequest,
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> PayableAccountResponse:
    """Agenda pagamento de uma conta."""
    try:
        account = await service.schedule_payment(account_id, data, current_user.id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta não encontrada",
            )
        return PayableAccountResponse.model_validate(account)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==================== PARCELAS ====================


@router.get(
    "/{account_id}/installments",
    response_model=list[PayableInstallmentResponse],
    summary="Listar parcelas",
)
async def list_installments(
    account_id: UUID,
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[PayableInstallmentResponse]:
    """Lista parcelas de uma conta."""
    installments = await service.list_installments(account_id)
    return [PayableInstallmentResponse.model_validate(i) for i in installments]


@router.get(
    "/installments/pending",
    response_model=list[PayableInstallmentResponse],
    summary="Parcelas pendentes",
)
async def get_pending_installments(
    condominio_id: UUID | None = Query(None, description="ID do condomínio"),
    due_date_start: date | None = Query(None),
    due_date_end: date | None = Query(None),
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[PayableInstallmentResponse]:
    """Retorna parcelas pendentes."""
    installments = await service.get_pending_installments(condominio_id, due_date_start, due_date_end)
    return [PayableInstallmentResponse.model_validate(i) for i in installments]


@router.put(
    "/installments/{installment_id}",
    response_model=PayableInstallmentResponse,
    summary="Atualizar parcela",
)
async def update_installment(
    installment_id: UUID,
    data: PayableInstallmentUpdate,
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> PayableInstallmentResponse:
    """Atualiza uma parcela."""
    try:
        installment = await service.update_installment(installment_id, data)
        if not installment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parcela não encontrada",
            )
        return PayableInstallmentResponse.model_validate(installment)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/installments/{installment_id}/renegotiate",
    response_model=PayableInstallmentResponse,
    summary="Renegociar parcela",
    status_code=201,
)
async def renegotiate_installment(
    installment_id: UUID,
    data: PayableInstallmentRenegotiateRequest,
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> PayableInstallmentResponse:
    """Renegocia uma parcela."""
    try:
        installment = await service.renegotiate_installment(installment_id, data, current_user.id)
        if not installment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parcela não encontrada",
            )
        return PayableInstallmentResponse.model_validate(installment)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==================== PAGAMENTOS ====================


@router.post(
    "/installments/{installment_id}/pay",
    response_model=PayablePaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar pagamento",
)
async def register_payment(
    installment_id: UUID,
    data: PayablePaymentCreate,
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> PayablePaymentResponse:
    """Registra pagamento de uma parcela."""
    try:
        payment = await service.register_payment(installment_id, data, current_user.id)
        # Publisher GEDEON Event Bus — pagamento realizado
        try:
            import asyncio

            asyncio.create_task(
                publish_pagamento_realizado(
                    payment_id=str(payment.id),
                    installment_id=str(installment_id),
                    valor=float(getattr(payment, "amount_paid", 0) or 0),
                    fornecedor=str(getattr(payment, "fornecedor_nome", "") or ""),
                    cliente_id=str(getattr(payment, "cliente_id", "") or ""),
                )
            )
        except Exception:
            pass
        return PayablePaymentResponse.model_validate(payment)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/bulk-payment", summary="Pagamento em lote", status_code=201)
async def bulk_payment(
    data: PayableBulkPaymentRequest,
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Processa pagamento em lote."""
    success, errors, payment_ids = await service.bulk_payment(data, current_user.id)
    return {
        "success_count": success,
        "error_count": errors,
        "total": len(data.installment_ids),
        "payment_ids": [str(p) for p in payment_ids],
    }


@router.post(
    "/payments/{payment_id}/reverse",
    response_model=PayablePaymentResponse,
    summary="Estornar pagamento",
    status_code=201,
)
async def reverse_payment(
    payment_id: UUID,
    data: PayablePaymentReverseRequest,
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> PayablePaymentResponse:
    """Estorna um pagamento."""
    try:
        payment = await service.reverse_payment(payment_id, data, current_user.id)
        if not payment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pagamento não encontrado",
            )
        return PayablePaymentResponse.model_validate(payment)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/payments/{payment_id}/reconcile",
    response_model=PayablePaymentResponse,
    summary="Reconciliar pagamento",
    status_code=201,
)
async def reconcile_payment(
    payment_id: UUID,
    data: PayablePaymentReconcileRequest,
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> PayablePaymentResponse:
    """Reconcilia pagamento com extrato bancário."""
    try:
        payment = await service.reconcile_payment(payment_id, data, current_user.id)
        if not payment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pagamento não encontrado",
            )
        return PayablePaymentResponse.model_validate(payment)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/payments/pending-reconciliation",
    response_model=list[PayablePaymentResponse],
    summary="Pagamentos pendentes de reconciliação",
)
async def get_pending_reconciliation(
    condominio_id: UUID | None = Query(None, description="ID do condomínio"),
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[PayablePaymentResponse]:
    """Retorna pagamentos pendentes de reconciliação."""
    payments = await service.get_pending_reconciliation(condominio_id)
    return [PayablePaymentResponse.model_validate(p) for p in payments]


# ==================== RECORRÊNCIA ====================


@router.post("/process-recurring", summary="Processar contas recorrentes", status_code=201)
async def process_recurring(
    condominio_id: UUID | None = Query(None, description="ID do condomínio"),
    reference_date: date | None = None,
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict[str, Any]:
    """Processa contas recorrentes e gera novas."""
    accounts = await service.process_recurring_accounts(condominio_id, reference_date)
    return {
        "created_count": len(accounts),
        "account_ids": [str(a.id) for a in accounts],
    }


# ==================== AUTO-CRIAR DE NOTAS FISCAIS ====================


@router.post("/auto-criar", summary="Criar contas a pagar automaticamente de NFS-e e NF-e recebidas")
async def auto_criar_payables(
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """
    Processa todas as notas fiscais recebidas sem conta a pagar vinculada.
    Cria payable para cada NFS-e e NF-e de entrada.
    """
    from modules.financial.services.payable_auto_service import processar_todas_pendentes

    resultado = await processar_todas_pendentes(db)
    return {"status": "ok", "resultado": resultado}


@router.post("/auto-criar/{nota_id}", summary="Criar conta a pagar para nota específica")
async def auto_criar_payable_nota(
    nota_id: str,
    tipo: str = Query(default="nfse", description="Tipo da nota: nfse ou nfe"),
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Cria conta a pagar para uma nota fiscal específica."""
    from modules.financial.services.payable_auto_service import (
        criar_payable_de_nfe_entrada,
        criar_payable_de_nfse_entrada,
    )

    if tipo == "nfse":
        resultado = await criar_payable_de_nfse_entrada(db, nota_id)
    else:
        resultado = await criar_payable_de_nfe_entrada(db, nota_id)
    return {"status": "ok", "resultado": resultado}


@router.get("/aging/pdf", summary="Aging em PDF (marca Conecta)")
async def payable_aging_pdf(
    condominio_id: UUID | None = Query(None),
    service: PayableService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
):
    from fastapi.responses import Response as _R

    from modules.financial.services.relatorio_financeiro_pdf import gerar_relatorio_pdf

    dados = await get_payables_aging(condominio_id=condominio_id, service=service, current_user=current_user)
    linhas = [
        (f"{(fx.get('faixa') or '').replace('_', ' ').capitalize()} ({fx.get('quantidade', 0)})", fx.get("valor_total", 0))
        for fx in dados.get("faixas", [])
    ]
    secoes = [{"titulo": "Por faixa de vencimento", "linhas": linhas or [("(sem títulos em aberto)", "")]}]
    secoes.append({"titulo": "Totais", "linhas": [
        ("Total em aberto", dados.get("total_em_aberto", 0)),
        ("Total vencido", dados.get("total_vencido", 0), True)]})
    pdf = gerar_relatorio_pdf("Contas a Pagar — Aging", f"Posição em {dados.get('aging_date', '')}", secoes)
    return _R(content=pdf, media_type="application/pdf",
              headers={"Content-Disposition": 'inline; filename="aging_payable.pdf"'})
