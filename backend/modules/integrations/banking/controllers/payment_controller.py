"""
Payment Controller — Pagamentos via Banco Inter
Suporte: boletos, DARF, tributos, lotes
"""

import os

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_session


def _build_inter_adapter():
    from modules.integrations.banking.adapters.base import BankCredentials
    from modules.integrations.banking.adapters.inter import InterAdapter

    creds = BankCredentials(
        client_id=os.getenv("INTER_CLIENT_ID", ""),
        client_secret=os.getenv("INTER_CLIENT_SECRET", ""),
        certificate_path=os.getenv("INTER_CERT_PATH", "") or None,
        private_key_path=os.getenv("INTER_KEY_PATH", "") or None,
        environment=os.getenv("INTER_ENVIRONMENT", "production"),
    )
    return InterAdapter(creds)


router = APIRouter(
    prefix="/banking/payment",
    tags=["Banking — Pagamentos"],
)


class BarcodePaymentRequest(BaseModel):
    codigo_barras: str
    valor: float | None = None
    data_pagamento: str | None = None
    descricao: str = ""
    payable_id: str | None = None


class DARFRequest(BaseModel):
    cnpj_cpf: str = "35710481000103"
    periodo_apuracao: str  # YYYY-MM ou YYYY-MM-DD
    numero_referencia: str  # apenas números, max 30
    valor_principal: float
    valor_multa: float = 0
    valor_juros: float = 0
    codigo_receita: str = "6015"  # 6015=IRPJ 2372=CSLL 0561=COFINS 8109=PIS 2100=INSS
    data_vencimento: str | None = None
    descricao: str = "Pagamento DARF"
    nome_empresa: str = "CONECTAMAIS ELETRONICA LTDA"
    telefone_empresa: str = "92986465328"


class BatchPaymentItem(BaseModel):
    codigo_barras: str
    valor: float | None = None
    data_pagamento: str | None = None
    descricao: str = ""
    meu_identificador: str = ""


class BatchPaymentRequest(BaseModel):
    pagamentos: list[BatchPaymentItem]


@router.post("/barcode", summary="Pagar boleto/convênio/tributo por código de barras")
async def pay_barcode(
    request: BarcodePaymentRequest,
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """
    Paga boleto bancário, conta de água/luz/telefone ou tributo.
    Se payable_id informado, atualiza conta a pagar automaticamente.
    """
    adapter = _build_inter_adapter()
    resultado = await adapter.pay_barcode(
        request.codigo_barras,
        request.valor,
        request.data_pagamento,
        request.descricao,
    )

    # Atualizar payable se informado e pagamento bem-sucedido
    if resultado.get("success") and request.payable_id:
        try:
            await db.execute(
                text(
                    "UPDATE payable_accounts SET "
                    "status = 'pago', paid_at = NOW(), "
                    "paid_value = :valor, "
                    "transacao_bancaria_id = :transacao_id, "
                    "updated_at = NOW() "
                    "WHERE id = :payable_id"
                ),
                {
                    "valor": request.valor or 0,
                    "transacao_id": resultado.get("payment_id", ""),
                    "payable_id": request.payable_id,
                },
            )
            await db.commit()
            resultado["payable_atualizado"] = True
        except Exception as e:
            resultado["payable_erro"] = str(e)

    return resultado


@router.post("/darf", summary="Pagar DARF (IRPJ, CSLL, COFINS, PIS, INSS)")
async def pay_darf(
    request: DARFRequest,
    _user: dict = Depends(get_current_user),
) -> dict:
    """
    Paga DARF via API Inter.
    Códigos de receita mais usados:
    - 6015: IRPJ
    - 2372: CSLL
    - 0561: COFINS
    - 8109: PIS/PASEP
    - 2100: INSS Patronal
    """
    adapter = _build_inter_adapter()
    return await adapter.pay_darf(
        request.cnpj_cpf,
        request.periodo_apuracao,
        request.numero_referencia,
        request.valor_principal,
        request.valor_multa,
        request.valor_juros,
        request.codigo_receita,
        request.data_vencimento,
        request.descricao,
        request.nome_empresa,
        request.telefone_empresa,
    )


@router.post("/batch", summary="Pagamento em lote — múltiplos boletos/tributos")
async def pay_batch(
    request: BatchPaymentRequest,
    _user: dict = Depends(get_current_user),
) -> dict:
    """
    Realiza múltiplos pagamentos em uma única requisição.
    Ideal para pagamento de várias contas simultaneamente.
    """
    adapter = _build_inter_adapter()
    pagamentos = [p.model_dump() for p in request.pagamentos]
    return await adapter.pay_batch(pagamentos)


@router.get("/list", summary="Listar pagamentos realizados")
async def list_payments(
    data_inicio: str = Query(default=None),
    data_fim: str = Query(default=None),
    tipo: str = Query(default=None, description="BOLETO | PIX | TED | DARF"),
    _user: dict = Depends(get_current_user),
) -> dict:
    """
    Lista pagamentos realizados por período.
    tipo: BOLETO | PIX | TED | DARF
    """
    adapter = _build_inter_adapter()
    return await adapter.get_payment_list(data_inicio, data_fim, tipo)


@router.post("/cancel/{payment_id}", summary="Cancelar pagamento agendado")
async def cancel_payment(
    payment_id: str,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Cancela pagamento agendado (antes da data de execução)."""
    adapter = _build_inter_adapter()
    ok = await adapter.cancel_payment(payment_id)  # adapter devolve bool
    return {
        "success": bool(ok),
        "payment_id": payment_id,
        "mensagem": "Pagamento cancelado." if ok
        else "Não foi possível cancelar (pagamento não encontrado ou já executado).",
    }
