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


@router.get("/balances", response_model=BankingBalancesResponse)
async def get_bank_balances(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Saldos de TODAS as contas ativas (Inter, Cora, ...) a partir do cache
    bank_accounts, sincronizado a cada 15 min pela task financial.sync_bank_balances.

    Antes esta rota consultava SÓ o Banco Inter ao vivo (lista hardcoded), o que
    escondia a Cora do "Saldo Bancário Consolidado" e travava a tela quando o
    adapter mTLS do Inter estava lento/fora. Lê só o cache (rápido e seguro) e
    inclui qualquer conta que já tenha saldo sincronizado."""
    from sqlalchemy import text as _text

    now = datetime.now().isoformat()
    balances: list[BankBalanceItem] = []

    rows = (await db.execute(_text("""
        SELECT bank_code, bank_name, account_number, account_digit,
               COALESCE(current_balance, 0)                        AS current_balance,
               COALESCE(available_balance, current_balance, 0)     AS available_balance,
               COALESCE(blocked_balance, 0)                        AS blocked_balance,
               last_balance_update
        FROM bank_accounts
        WHERE COALESCE(ativo, true) = true
          AND COALESCE(status, 'ativa') = 'ativa'
          AND (last_balance_update IS NOT NULL OR COALESCE(current_balance, 0) <> 0)
        ORDER BY is_main_account DESC NULLS LAST, current_balance DESC NULLS LAST
    """))).fetchall()

    for r in rows:
        acct = (r.account_number or "")
        if r.account_digit:
            acct = f"{acct}-{r.account_digit}"
        balances.append(BankBalanceItem(
            bank_code=str(r.bank_code or ""),
            bank_name=str(r.bank_name or ""),
            account=acct or "—",
            balance=float(r.current_balance or 0),
            available_balance=float(r.available_balance or 0),
            blocked_balance=float(r.blocked_balance or 0),
            updated_at=(r.last_balance_update.isoformat() if r.last_balance_update else now),
        ))

    total = sum(b.available_balance for b in balances)

    return BankingBalancesResponse(
        balances=balances,
        total_balance=total,
        updated_at=now,
    )


@router.get("/statement", response_model=BankingStatementResponse)
async def get_bank_statement(
    days: int = Query(default=30, ge=1, le=365),
    bank_code: str | None = Query(default=None),
    current_user=Depends(get_current_user),
):
    """Consulta extrato bancário recente."""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    transactions: list[BankTransactionItem] = []
    service = _get_banking_service()

    banks_to_query = []
    if bank_code:
        banks_to_query.append(bank_code)
    else:
        banks_to_query = ["077"]

    for code in banks_to_query:
        try:
            statement = await service.get_statement(code, start_date, end_date)
            for tx in statement.transactions:
                tx_type = "credit" if tx.amount >= 0 else "debit"
                transactions.append(
                    BankTransactionItem(
                        id=tx.transaction_id,
                        bank_code=code,
                        date=tx.date.isoformat() if tx.date else "",
                        description=tx.description or "",
                        amount=float(abs(tx.amount)),
                        type=tx_type,
                        category=str(tx.transaction_type) if tx.transaction_type else None,
                    )
                )
        except Exception as exc:
            logger.debug("Extrato indisponível para banco %s: %s", code, str(exc))

    total_credits = sum(t.amount for t in transactions if t.type == "credit")
    total_debits = sum(t.amount for t in transactions if t.type == "debit")

    return BankingStatementResponse(
        transactions=transactions,
        total_credits=total_credits,
        total_debits=total_debits,
        period_start=start_date.isoformat(),
        period_end=end_date.isoformat(),
    )


@router.get("/status", response_model=list[BankConnectionStatus])
async def get_bank_status(
    current_user=Depends(get_current_user),
):
    """Consulta status de conexão dos bancos integrados."""
    statuses: list[BankConnectionStatus] = []

    banks = [
        ("077", "Banco Inter"),
    ]

    service = _get_banking_service()

    for bank_code, bank_name in banks:
        try:
            # Tenta obter saldo como health check
            await service.get_balance(bank_code)
            statuses.append(
                BankConnectionStatus(
                    bank_code=bank_code,
                    bank_name=bank_name,
                    connected=True,
                    last_sync=datetime.now().isoformat(),
                )
            )
        except Exception as exc:
            statuses.append(
                BankConnectionStatus(
                    bank_code=bank_code,
                    bank_name=bank_name,
                    connected=False,
                    last_sync=None,
                    error=str(exc),
                )
            )

    return statuses


# Mapeamento banco_code -> (nome legível, método de geração)
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


@router.get("/boleto", include_in_schema=False)
@router.get("/boleto/list", response_model=BoletoListResponse)
async def list_boletos(
    bank_code: str | None = Query(default=None),
    status: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista boletos emitidos via Banco Inter (lê a tabela inter_cobrancas)."""
    from sqlalchemy import text as _text
    boletos: list[BoletoListItem] = []
    try:
        rows = await db.execute(_text(
            """SELECT cobranca_id_inter, valor, vencimento, pagador, status,
                      url_boleto, pix_copia_cola, barcode, linha_digitavel, descricao, created_at
               FROM inter_cobrancas
               WHERE created_at >= now() - make_interval(days => :d)
               ORDER BY created_at DESC"""), {"d": days})
        for r in rows.mappings().all():
            if status and (r["status"] or "").upper() != status.upper():
                continue
            pag = r["pagador"] if isinstance(r["pagador"], dict) else {}
            boletos.append(BoletoListItem(
                boleto_id=str(r["cobranca_id_inter"] or ""),
                bank_code="077", bank_name="Banco Inter",
                amount=float(r["valor"] or 0),
                due_date=str(r["vencimento"] or "")[:10],
                payer_name=(pag.get("nome") or "") if pag else "",
                status=r["status"] or "A_RECEBER",
                barcode=r["barcode"], digitable_line=r["linha_digitavel"],
                pdf_url=r["url_boleto"] or (r["pix_copia_cola"] or None),
                created_at=r["created_at"].isoformat() if r["created_at"] else None,
            ))
    except Exception as e:  # noqa: BLE001
        logger.warning("list_boletos (inter_cobrancas): %s", e)
    return BoletoListResponse(boletos=boletos, total=len(boletos))


@router.get("/statement/full", response_model=BankStatementFullResponse)
async def get_bank_statement_full(
    days: int = Query(default=30, ge=1, le=365),
    bank_code: str | None = Query(default=None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extrato completo com todos os campos disponíveis por transação."""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    transactions: list[BankTransactionFull] = []
    total_credits = 0.0
    total_debits = 0.0
    opening_balance = 0.0
    closing_balance = 0.0

    # Extrato a partir do CACHE bank_transactions (todas as contas: Inter, Cora, ...).
    # Antes consultava só o Inter ao vivo (banks_to_query=["077"]); a Cora — que NÃO está
    # registrada no BankingService — nunca aparecia, e o adapter mTLS ao vivo travava a
    # tela. Ler o cache inclui todas as contas, rotula o banco por linha e é A5-safe.
    from sqlalchemy import text as _text

    _where = ""
    _params: dict = {"start": start_date, "end": end_date}
    if bank_code:
        _where = " AND ba.bank_code = :bcode"
        _params["bcode"] = bank_code

    rows = (await db.execute(_text(f"""
        SELECT bt.id, bt.transaction_date, bt.amount, bt.transaction_type,
               coalesce(bt.description, bt.memo, '')                         AS description,
               coalesce(bt.counterparty_name, bt.contraparte_nome)           AS counterpart_name,
               coalesce(bt.counterparty_document, bt.contraparte_documento)  AS counterpart_document,
               bt.counterparty_bank                                          AS counterpart_bank,
               bt.balance_after, bt.reference, bt.category,
               coalesce(ba.bank_code, '')                                    AS bank_code,
               coalesce(ba.bank_name, '—')                                   AS bank_name
        FROM bank_transactions bt
        LEFT JOIN bank_accounts ba ON ba.id = bt.bank_account_id
        WHERE bt.transaction_date >= :start AND bt.transaction_date <= :end
          AND coalesce(bt.ativo, true) = true{_where}
        ORDER BY bt.transaction_date DESC NULLS LAST
        LIMIT 500
    """), _params)).fetchall()

    for r in rows:
        raw_amount = float(r.amount or 0)
        amount = abs(raw_amount)
        tx_type_str = str(r.transaction_type or "unknown")
        tl = tx_type_str.lower()
        # Direção: tipo explícito crédito/débito vence; senão o sinal do valor.
        if tl in ("credit", "credito", "c", "pix_recebido", "deposito"):
            is_credit = True
        elif tl in ("debit", "debito", "d"):
            is_credit = False
        else:
            is_credit = raw_amount >= 0

        if is_credit:
            total_credits += amount
        else:
            total_debits += amount

        transactions.append(
            BankTransactionFull(
                transaction_id=str(r.id),
                date=r.transaction_date.isoformat() if r.transaction_date else "",
                amount=amount,
                transaction_type=tx_type_str,
                type="credit" if is_credit else "debit",
                description=r.description or "",
                counterpart_name=r.counterpart_name,
                counterpart_document=r.counterpart_document,
                counterpart_bank=r.counterpart_bank,
                balance_after=float(r.balance_after) if r.balance_after is not None else None,
                reference=r.reference,
                category=r.category,
                bank_code=str(r.bank_code or ""),
                bank_name=str(r.bank_name or "—"),
            )
        )

    # closing_balance = saldo consolidado atual (todas as contas ativas)
    closing_balance = float(
        (await db.execute(_text(
            "SELECT COALESCE(SUM(COALESCE(available_balance, current_balance, 0)), 0) "
            "FROM bank_accounts WHERE COALESCE(ativo, true) = true AND COALESCE(status, 'ativa') = 'ativa'"
        ))).scalar() or 0
    )
    # Já ordenado por data desc no SQL.

    return BankStatementFullResponse(
        transactions=transactions,
        total_credits=total_credits,
        total_debits=total_debits,
        period_start=start_date.isoformat(),
        period_end=end_date.isoformat(),
        opening_balance=opening_balance,
        closing_balance=closing_balance,
    )


# ─── Novos endpoints: consulta boleto, TED, PIX recebidos, devolução ───


@router.get("/boleto/{boleto_id}", summary="Consultar boleto — barcode e PDF")
async def get_boleto(
    boleto_id: str,
    current_user=Depends(get_current_user),
):
    """Consulta boleto por ID — retorna código de barras, linha digitável e link para PDF."""
    service = _get_banking_service()
    adapter = service._adapters.get("077")
    if adapter is None:
        return {"success": False, "error": "Banco Inter não configurado"}
    return await adapter.get_boleto(boleto_id)


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


@router.post("/ted/transfer", summary="Realizar transferência TED")
async def initiate_ted(
    req: TEDRequest,
    current_user=Depends(get_current_user),
):
    """Realiza transferência TED para qualquer banco. tipo_conta: CORRENTE | POUPANCA | PAGAMENTO"""
    service = _get_banking_service()
    adapter = service._adapters.get("077")
    if adapter is None:
        return {"success": False, "error": "Banco Inter não configurado"}
    return await adapter.initiate_ted(
        req.valor,
        req.banco,
        req.agencia,
        req.conta,
        req.tipo_conta,
        req.cpf_cnpj,
        req.nome,
        req.descricao,
    )


@router.get("/pix/received", summary="Consultar PIX recebidos")
async def get_pix_received(
    data_inicio: str | None = None,
    data_fim: str | None = None,
    current_user=Depends(get_current_user),
):
    """Lista PIX recebidos na conta Inter por período."""
    service = _get_banking_service()
    adapter = service._adapters.get("077")
    if adapter is None:
        return {"success": False, "error": "Banco Inter não configurado"}
    return await adapter.get_pix_received(data_inicio, data_fim)


class PIXRefundRequest(BaseModel):
    e2e_id: str
    refund_id: str
    valor: float
    motivo: str = "Devolucao solicitada"


@router.post("/pix/refund", summary="Solicitar devolução de PIX")
async def request_pix_refund(
    req: PIXRefundRequest,
    current_user=Depends(get_current_user),
):
    """Solicita devolução (estorno) de PIX recebido."""
    service = _get_banking_service()
    adapter = service._adapters.get("077")
    if adapter is None:
        return {"success": False, "error": "Banco Inter não configurado"}
    return await adapter.request_pix_refund(
        req.e2e_id,
        req.refund_id,
        req.valor,
        req.motivo,
    )
