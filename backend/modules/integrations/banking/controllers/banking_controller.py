"""
Controller para operações bancárias (Banco Inter).

Endpoints para consulta de saldos, extratos e status de conexão.
"""

import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from core.auth.dependencies import get_current_user
from core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

CREDENTIALS_FILE = Path("/opt/conecta-pro/credentials/.env.credentials")


def _load_credentials_env() -> dict[str, str]:
    """Carrega variáveis do arquivo .env.credentials se existir."""
    env_vars: dict[str, str] = {}
    if CREDENTIALS_FILE.exists():
        for line in CREDENTIALS_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


router = APIRouter(prefix="/banking", tags=["Banking"])


async def _salvar_cobranca_no_receivable(
    receivable_id: str,
    tipo: str,
    dados: dict,
    db=None,
) -> None:
    """
    Salva dados de boleto/PIX gerado de volta no receivable_account.
    Fecha o ciclo: gerar cobrança → salvar → exibir no modal.
    """
    import psycopg2

    database_url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()

        if tipo == "boleto":
            cur.execute(
                """
                UPDATE receivable_accounts SET
                    boleto_generated = TRUE,
                    boleto_id = %s,
                    boleto_barcode = %s,
                    boleto_digitable_line = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    dados.get("boleto_id", ""),
                    dados.get("barcode", ""),
                    dados.get("digitable_line", dados.get("linha_digitavel", "")),
                    receivable_id,
                ),
            )
        elif tipo == "pix":
            cur.execute(
                """
                UPDATE receivable_accounts SET
                    pix_generated = TRUE,
                    pix_txid = %s,
                    pix_copy_paste = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    dados.get("charge_id", dados.get("txid", "")),
                    dados.get("pix_copy_paste", ""),
                    receivable_id,
                ),
            )

        conn.commit()
        cur.close()
        conn.close()
        logger.info("Cobrança %s salva no receivable %s", tipo, receivable_id)
    except Exception as exc:
        logger.warning("Erro ao salvar cobrança no receivable %s: %s", receivable_id, exc)


# --- Response Schemas ---


class BankBalanceItem(BaseModel):
    bank_code: str
    bank_name: str
    account: str
    balance: float
    available_balance: float
    blocked_balance: float
    updated_at: str


class BankingBalancesResponse(BaseModel):
    balances: list[BankBalanceItem]
    total_balance: float
    updated_at: str


class BankTransactionItem(BaseModel):
    id: str
    bank_code: str
    date: str
    description: str
    amount: float
    type: str  # credit | debit
    category: str | None = None
    balance_after: float | None = None


class BankingStatementResponse(BaseModel):
    transactions: list[BankTransactionItem]
    total_credits: float
    total_debits: float
    period_start: str
    period_end: str


class BankConnectionStatus(BaseModel):
    bank_code: str
    bank_name: str
    connected: bool
    last_sync: str | None = None
    error: str | None = None


class BoletoGenerateRequest(BaseModel):
    bank_code: str  # "077" = Inter
    amount: float
    due_date: str  # formato ISO: "2026-03-15"
    payer_name: str
    payer_document: str  # CPF ou CNPJ
    description: str
    receivable_id: str | None = None  # ID do receivable_account para salvar boleto gerado
    payer_address: str | None = None
    payer_number: str | None = None
    payer_neighborhood: str | None = None
    payer_city: str | None = None
    payer_state: str | None = None
    payer_zip: str | None = None


class BoletoResponse(BaseModel):
    success: bool
    bank_code: str
    bank_name: str
    boleto_id: str | None = None
    barcode: str | None = None
    digitable_line: str | None = None
    pdf_url: str | None = None
    pix_qrcode: str | None = None
    pix_copy_paste: str | None = None
    amount: float
    due_date: str
    payer_name: str
    created_at: str
    error: str | None = None


class BoletoListItem(BaseModel):
    boleto_id: str
    bank_code: str
    bank_name: str
    amount: float
    due_date: str
    payer_name: str
    status: str
    barcode: str | None = None
    digitable_line: str | None = None
    pdf_url: str | None = None
    created_at: str | None = None


class BoletoListResponse(BaseModel):
    boletos: list[BoletoListItem]
    total: int


class PixChargeRequest(BaseModel):
    bank_code: str = "077"  # "077" = Inter
    amount: float  # Valor em R$
    description: str = "Cobrança Grupo Conecta Mais"
    payer_name: str | None = None
    payer_document: str | None = None
    receivable_id: str | None = None  # ID do receivable_account para salvar PIX gerado
    # Multi-CNPJ E4: default = chave da ELETRÔNICA (esta rota gera PIX pelo
    # INTER). Cobranças da PATRIMONIAL saem pelo CORA via recurring_billing/
    # CoraAdapter.criar_cobranca — NUNCA misturar chave de uma com banco da outra.
    chave_pix: str = "35710481000103"  # chave PIX Inter (Eletrônica)
    expiracao_horas: int = 24  # Validade em horas


class PixChargeResponse(BaseModel):
    success: bool
    bank_code: str
    bank_name: str
    charge_id: str | None = None
    pix_qrcode: str | None = None
    pix_copy_paste: str | None = None
    amount: float
    description: str
    chave_pix: str
    expires_at: str | None = None
    created_at: str
    error: str | None = None


class BankTransactionFull(BaseModel):
    transaction_id: str
    date: str
    amount: float
    transaction_type: str
    type: str  # 'credit' | 'debit' — direção da transação para o frontend
    description: str
    counterpart_name: str | None = None
    counterpart_document: str | None = None
    counterpart_bank: str | None = None
    balance_after: float | None = None
    reference: str | None = None
    category: str | None = None
    bank_code: str
    bank_name: str


class BankStatementFullResponse(BaseModel):
    transactions: list[BankTransactionFull]
    total_credits: float
    total_debits: float
    period_start: str
    period_end: str
    opening_balance: float
    closing_balance: float


# --- Helper ---


def _get_banking_service():
    """Retorna instância do BankingService com adapters configurados."""
    from modules.integrations.banking.adapters import BankCode, BankCredentials
    from modules.integrations.banking.services import BankingService

    service = BankingService()
    env = _load_credentials_env()

    # Registrar Inter
    inter_client_id = env.get("INTER_CLIENT_ID") or os.environ.get("INTER_CLIENT_ID")
    inter_secret = env.get("INTER_CLIENT_SECRET") or os.environ.get("INTER_CLIENT_SECRET")
    inter_cert = env.get("INTER_CERT_PATH") or os.environ.get("INTER_CERT_PATH")
    inter_key = env.get("INTER_KEY_PATH") or os.environ.get("INTER_KEY_PATH")
    inter_agency = env.get("INTER_AGENCY") or os.environ.get("INTER_AGENCY")
    inter_account = env.get("INTER_ACCOUNT") or os.environ.get("INTER_ACCOUNT")
    inter_env = env.get("INTER_ENVIRONMENT", "production")
    if inter_client_id and inter_secret and inter_cert and inter_key:
        try:
            inter_creds = BankCredentials(
                client_id=inter_client_id,
                client_secret=inter_secret,
                certificate_path=inter_cert,
                private_key_path=inter_key,
                agency=inter_agency,
                account=inter_account,
                environment=inter_env,
            )
            service.register_account(BankCode.INTER, BankCode.INTER, inter_creds)
        except Exception as exc:
            logger.warning("Falha ao registrar Inter: %s", exc)

    return service


async def _try_adapter_balance(
    service,
    bank_code: str,
    bank_name: str,
    account_label: str,
) -> BankBalanceItem | None:
    """Tenta obter saldo de um adapter registrado."""
    try:
        balance = await service.get_balance(bank_code)
        return BankBalanceItem(
            bank_code=bank_code,
            bank_name=bank_name,
            account=account_label,
            balance=float(balance.total),
            available_balance=float(balance.available),
            blocked_balance=float(balance.blocked),
            updated_at=balance.updated_at.isoformat() if balance.updated_at else datetime.now().isoformat(),
        )
    except Exception as exc:
        logger.debug("Saldo indisponível para %s: %s", bank_name, str(exc))
        return BankBalanceItem(
            bank_code=bank_code,
            bank_name=bank_name,
            account=account_label,
            balance=0,
            available_balance=0,
            blocked_balance=0,
            updated_at=datetime.now().isoformat(),
        )


# --- Endpoints ---


_BANK_NAMES = {
    "077": "Banco Inter",
}



@router.post("/boleto/generate", response_model=BoletoResponse)
async def generate_boleto(
    req: BoletoGenerateRequest,
    current_user=Depends(get_current_user),
):
    """Emite boleto de cobrança via Banco Inter (077)."""
    bank_name = _BANK_NAMES.get(req.bank_code, req.bank_code)
    now_iso = datetime.now().isoformat()

    try:
        due_date_obj = date.fromisoformat(req.due_date)
    except ValueError as exc:
        return BoletoResponse(
            success=False,
            bank_code=req.bank_code,
            bank_name=bank_name,
            amount=req.amount,
            due_date=req.due_date,
            payer_name=req.payer_name,
            created_at=now_iso,
            error=f"due_date inválido: {exc}",
        )

    service = _get_banking_service()
    adapter = service._adapters.get(req.bank_code)

    if adapter is None:
        return BoletoResponse(
            success=False,
            bank_code=req.bank_code,
            bank_name=bank_name,
            amount=req.amount,
            due_date=req.due_date,
            payer_name=req.payer_name,
            created_at=now_iso,
            error=f"Banco {req.bank_code} não configurado ou sem credenciais",
        )

    try:
        from decimal import Decimal

        amount_decimal = Decimal(str(req.amount))

        if req.bank_code == "077":
            # Inter: generate_boleto
            result = await adapter.generate_boleto(
                amount=amount_decimal,
                due_date=due_date_obj,
                payer_name=req.payer_name,
                payer_document=req.payer_document,
                description=req.description,
                payer_address=req.payer_address,
                payer_number=req.payer_number,
                payer_neighborhood=req.payer_neighborhood,
                payer_city=req.payer_city,
                payer_state=req.payer_state,
                payer_zip=req.payer_zip,
            )
            # Salvar no receivable_account se informado
            if req.receivable_id and result.get("boleto_id"):
                asyncio.create_task(_salvar_cobranca_no_receivable(req.receivable_id, "boleto", result))

            return BoletoResponse(
                success=True,
                bank_code=req.bank_code,
                bank_name=bank_name,
                boleto_id=result.get("boleto_id"),
                barcode=result.get("barcode"),
                digitable_line=result.get("digitable_line"),
                pdf_url=result.get("pdf_url"),
                pix_copy_paste=result.get("pix_qrcode"),  # Inter retorna pixCopiaECola mapeado
                amount=req.amount,
                due_date=req.due_date,
                payer_name=req.payer_name,
                created_at=now_iso,
            )

        else:
            return BoletoResponse(
                success=False,
                bank_code=req.bank_code,
                bank_name=bank_name,
                amount=req.amount,
                due_date=req.due_date,
                payer_name=req.payer_name,
                created_at=now_iso,
                error=f"Emissão de boleto não suportada para banco {req.bank_code}",
            )

    except Exception as exc:
        logger.exception("Erro ao gerar boleto para banco %s: %s", req.bank_code, exc)
        return BoletoResponse(
            success=False,
            bank_code=req.bank_code,
            bank_name=bank_name,
            amount=req.amount,
            due_date=req.due_date,
            payer_name=req.payer_name,
            created_at=now_iso,
            error=str(exc),
        )


@router.post("/pix/generate", response_model=PixChargeResponse)
async def generate_pix_charge(
    req: PixChargeRequest,
    current_user=Depends(get_current_user),
):
    """
    Gera cobrança PIX com QR Code dinâmico via Banco Inter.

    - Inter (077): cobrança imediata /pix/v2/cob → retorna copia-e-cola
    - Chave PIX padrão: CNPJ 35710481000103 (Conecta Mais ELETRÔNICA — Inter; Patrimonial cobra pelo Cora)
    """
    from datetime import datetime, timedelta

    bank_name = _BANK_NAMES.get(req.bank_code, req.bank_code)
    now = datetime.now()
    now_iso = now.isoformat()
    expires_at = (now + timedelta(hours=req.expiracao_horas)).isoformat()

    service = _get_banking_service()
    adapter = service._adapters.get(req.bank_code)

    if adapter is None:
        return PixChargeResponse(
            success=False,
            bank_code=req.bank_code,
            bank_name=bank_name,
            amount=req.amount,
            description=req.description,
            chave_pix=req.chave_pix,
            created_at=now_iso,
            error=f"Banco {req.bank_code} não configurado ou sem credenciais",
        )

    try:
        from decimal import Decimal

        amount_decimal = Decimal(str(req.amount))
        expiracao_segundos = req.expiracao_horas * 3600

        if req.bank_code == "077":
            result = await adapter.generate_pix_charge(
                amount=amount_decimal,
                description=req.description,
                chave_pix=req.chave_pix,
                payer_name=req.payer_name,
                payer_document=req.payer_document,
                expiracao_segundos=expiracao_segundos,
            )
        else:
            return PixChargeResponse(
                success=False,
                bank_code=req.bank_code,
                bank_name=bank_name,
                amount=req.amount,
                description=req.description,
                chave_pix=req.chave_pix,
                created_at=now_iso,
                error=f"PIX não suportado para banco {req.bank_code}",
            )

        # Salvar no receivable_account se informado
        if req.receivable_id and (result.get("charge_id") or result.get("pix_copy_paste")):
            asyncio.create_task(_salvar_cobranca_no_receivable(req.receivable_id, "pix", result))

        return PixChargeResponse(
            success=True,
            bank_code=req.bank_code,
            bank_name=bank_name,
            charge_id=result.get("charge_id"),
            pix_qrcode=result.get("pix_qrcode") or None,
            pix_copy_paste=result.get("pix_copy_paste") or None,
            amount=req.amount,
            description=req.description,
            chave_pix=req.chave_pix,
            expires_at=expires_at,
            created_at=now_iso,
        )

    except Exception as exc:
        logger.exception("Erro ao gerar PIX para banco %s: %s", req.bank_code, exc)
        error_msg = str(exc)
        # Mensagens de erro amigáveis para problemas conhecidos
        if "401" in error_msg and req.bank_code == "077":
            error_msg = (
                "PIX não habilitado na API Banco Inter. "
                "Acesse developers.inter.co → sua aplicação → habilite os escopos 'pix.read' e 'pix.write', "
                "depois solicite um novo certificado mTLS com esses escopos."
            )
        elif "403" in error_msg:
            error_msg = "Sem permissão para operação PIX neste banco. Verifique os escopos da aplicação."
        return PixChargeResponse(
            success=False,
            bank_code=req.bank_code,
            bank_name=bank_name,
            amount=req.amount,
            description=req.description,
            chave_pix=req.chave_pix,
            created_at=now_iso,
            error=error_msg,
        )


@router.delete("/boleto/{boleto_id}", summary="Cancelar boleto emitido")
async def cancel_boleto(
    boleto_id: str,
    motivo: str = "ACERTOS",
    current_user=Depends(get_current_user),
):
    """Cancela boleto. motivo: ACERTOS | APEDIDODOCLIENTE | PAGODIRETOAOCLIENTE"""  # pragma: allowlist secret
    service = _get_banking_service()
    adapter = service._adapters.get("077")
    if adapter is None:
        return {"success": False, "error": "Banco Inter não configurado"}
    return await adapter.cancel_boleto(boleto_id, motivo)


class TEDRequest(BaseModel):
    valor: float
    banco: str
    agencia: str
    conta: str
    tipo_conta: str = "CORRENTE"
    cpf_cnpj: str
    nome: str
    descricao: str = ""


class PIXRefundRequest(BaseModel):
    e2e_id: str
    refund_id: str
    valor: float
    motivo: str = "Devolucao solicitada"


