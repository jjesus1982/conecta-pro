"""Adapter Banco Cora (403) — conta PJ da CONECTAMAIS PATRIMONIAL LTDA.

Multi-CNPJ E4. Referência completa da API: docs/CORA_API_REFERENCIA_COMPLETA_2026-07-17.md.

v1 (read-only + cobrança futura):
- authenticate: OAuth2 client_credentials + mTLS (SEM client_secret — a
  autenticação é o par certificado/chave emitido pela Cora + client_id).
  Token dura 24h; renovação = repetir a chamada.
- get_balance: GET /third-party/account/balance (centavos!).
- get_statement: GET /bank-statement/statement (paginado; perPage < 500;
  datas inválidas retornam 500 — validar antes).

SAÍDA DE DINHEIRO: NÃO implementada de propósito. Na Cora, pagamentos via API
ficam INITIATED até aprovação no app (pendência D7 do plano: desativar como no
Inter). Até lá, initiate_payment/initiate_pix levantam NotImplementedError com
mensagem honesta — nunca simular pagamento (regra da casa).

Env: CORA_CLIENT_ID, CORA_CERT_PATH, CORA_KEY_PATH, CORA_BASE_URL,
CORA_ENVIRONMENT, CORA_APROVACAO (api|app).
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx

from modules.integrations.banking.adapters.base import (
    AccountBalance,
    AccountType,
    AuthenticationError,
    BankCredentials,
    BankingAdapterError,
    BankStatement,
    BankTransaction,
    BaseBankingAdapter,
    PaymentRequest,
    PaymentResponse,
    PixKey,
    TransactionType,
)

logger = logging.getLogger(__name__)

_SAIDA_BLOQUEADA = (
    "Saída de dinheiro via API Cora ainda não habilitada: pagamentos iniciados "
    "por API exigem aprovação no app da Cora (pendência D7 — desativar a "
    "exigência como foi feito no Inter, ou operar no modo 'pago pelo app' com "
    "conciliação). Nunca simular pagamento."
)

_TIPO_MAP = {
    "PIX": TransactionType.PIX,
    "TRANSFER": TransactionType.TED,
    "PAYMENT": TransactionType.BOLETO,
    "FEE": TransactionType.TARIFA,
}


def credenciais_cora_do_env() -> BankCredentials:
    """Credenciais da conta Cora (Patrimonial) a partir do env (dois .env alinhados)."""
    return BankCredentials(
        client_id=os.getenv("CORA_CLIENT_ID", ""),
        client_secret="",  # Cora Integração Direta NÃO usa client_secret
        certificate_path=os.getenv("CORA_CERT_PATH", "/app/credentials/cora/production_certificate.pem"),
        private_key_path=os.getenv("CORA_KEY_PATH", "/app/credentials/cora/production_private-key.key"),
        environment=os.getenv("CORA_ENVIRONMENT", "production"),
    )


class CoraAdapter(BaseBankingAdapter):
    """Adapter do Banco Cora (Integração Direta, mTLS)."""

    BANK_CODE = "403"
    BANK_NAME = "Cora SCD"
    API_BASE_URL_SANDBOX = "https://matls-clients.api.stage.cora.com.br"
    API_BASE_URL_PRODUCTION = "https://matls-clients.api.cora.com.br"

    def __init__(self, credentials: BankCredentials | None = None) -> None:
        super().__init__(credentials or credenciais_cora_do_env())
        if not self.credentials.client_id:
            raise AuthenticationError("CORA_CLIENT_ID ausente no ambiente")

    def _client(self) -> httpx.AsyncClient:
        cert = (self.credentials.certificate_path, self.credentials.private_key_path)
        return httpx.AsyncClient(base_url=self.base_url, cert=cert, timeout=40)

    async def authenticate(self) -> bool:
        async with self._client() as cli:
            resp = await cli.post(
                "/token",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                content=f"grant_type=client_credentials&client_id={self.credentials.client_id}",
            )
        if resp.status_code != 200:
            raise AuthenticationError(
                f"Cora /token HTTP {resp.status_code}: {resp.text[:200]}"
            )
        data = resp.json()
        self._access_token = data["access_token"]
        # 24h nominais; renova com 1h de folga
        self._token_expires_at = datetime.now() + timedelta(seconds=int(data.get("expires_in", 86400)) - 3600)
        logger.info("Cora autenticado (token até %s)", self._token_expires_at)
        return True

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token}"}

    async def get_balance(self) -> AccountBalance:
        await self.ensure_authenticated()
        async with self._client() as cli:
            resp = await cli.get("/third-party/account/balance", headers=self._auth_headers())
        if resp.status_code != 200:
            raise BankingAdapterError(f"Cora saldo HTTP {resp.status_code}: {resp.text[:200]}")
        centavos = int(resp.json().get("balance", 0))
        valor = Decimal(centavos) / 100
        return AccountBalance(available=valor, blocked=Decimal("0"), total=valor)

    async def get_statement(
        self,
        start_date: date,
        end_date: date,
        account: str | None = None,
    ) -> BankStatement:
        """Extrato paginado. Valores em centavos na API → Decimal em reais aqui."""
        await self.ensure_authenticated()
        transacoes: list[BankTransaction] = []
        saldo_inicial = saldo_final = Decimal("0")
        page = 1
        async with self._client() as cli:
            while True:
                resp = await cli.get(
                    "/bank-statement/statement",
                    headers=self._auth_headers(),
                    params={
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                        "page": page,
                        "perPage": 200,  # doc: >~500 dá 503/504
                    },
                )
                if resp.status_code != 200:
                    raise BankingAdapterError(
                        f"Cora extrato HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                data = resp.json()
                if page == 1:
                    saldo_inicial = Decimal(int((data.get("start") or {}).get("balance", 0))) / 100
                saldo_final = Decimal(int((data.get("end") or {}).get("balance", 0))) / 100
                entries = data.get("entries") or []
                for e in entries:
                    trx = e.get("transaction") or {}
                    contraparte = trx.get("counterParty") or {}
                    tipo_api = (trx.get("type") or "").upper()
                    valor = Decimal(int(e.get("amount", 0))) / 100
                    if (e.get("type") or "").upper() == "DEBIT":
                        valor = -valor
                    transacoes.append(
                        BankTransaction(
                            transaction_id=e.get("id") or trx.get("id") or "",
                            date=datetime.fromisoformat(str(e.get("createdAt", "")).replace("+00", "+00:00")),
                            amount=valor,
                            transaction_type=_TIPO_MAP.get(tipo_api, TransactionType.CREDIT if valor >= 0 else TransactionType.DEBIT),
                            description=trx.get("description") or tipo_api,
                            counterpart_name=contraparte.get("name"),
                            counterpart_document=contraparte.get("identity"),
                            reference=trx.get("id"),
                        )
                    )
                if len(entries) < 200:
                    break
                page += 1
        return BankStatement(
            account_agency="0001",
            account_number=account or "",
            account_type=AccountType.CHECKING,
            start_date=start_date,
            end_date=end_date,
            opening_balance=saldo_inicial,
            closing_balance=saldo_final,
            transactions=transacoes,
            bank_code=self.BANK_CODE,
            bank_name=self.BANK_NAME,
        )

    # ------------------------------------------------------------------
    # SAÍDA DE DINHEIRO — bloqueada até D7 (honestidade > conveniência)
    # ------------------------------------------------------------------

    async def initiate_payment(self, request: PaymentRequest) -> PaymentResponse:  # noqa: ARG002
        raise NotImplementedError(_SAIDA_BLOQUEADA)

    async def get_payment_status(self, payment_id: str) -> PaymentResponse:  # noqa: ARG002
        raise NotImplementedError(_SAIDA_BLOQUEADA)

    async def cancel_payment(self, payment_id: str) -> bool:  # noqa: ARG002
        raise NotImplementedError(_SAIDA_BLOQUEADA)

    async def validate_pix_key(self, pix_key: str) -> PixKey:  # noqa: ARG002
        raise NotImplementedError(
            "Cora não expõe validação/envio de PIX por chave na API pública "
            "(ver referência §4.4) — agenda de beneficiários usa dados bancários."
        )

    async def initiate_pix(self, request: PaymentRequest) -> PaymentResponse:  # noqa: ARG002
        raise NotImplementedError(_SAIDA_BLOQUEADA)
