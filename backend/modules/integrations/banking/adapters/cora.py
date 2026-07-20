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

    @staticmethod
    def _idem_key(operacao: str, referencia: str) -> str:
        """Idempotency-Key DETERMINÍSTICA (UUID v5) por operação+referência de
        negócio: o RETRY da mesma operação reusa a mesma chave e o Cora
        deduplica (evita boleto/pagamento em dobro). Formato UUID exigido §0."""
        import uuid as _uuid
        return str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"cora:{operacao}:{referencia}"))

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
    # COBRANÇA (recebimento) — boleto registrado + PIX QR na MESMA emissão
    # Referência: docs/CORA_API_REFERENCIA_COMPLETA §3 (valores em CENTAVOS;
    # mínimo R$5,00; Idempotency-Key obrigatório; PIX pago cancela o barcode)
    # ------------------------------------------------------------------

    async def criar_cobranca(
        self,
        *,
        code: str,
        cliente_nome: str,
        cliente_documento: str,
        valor_centavos: int,
        descricao: str,
        vencimento: date,
        cliente_email: str | None = None,
        formas: list[str] | None = None,
    ) -> dict:
        """Emite cobrança (boleto+PIX) pela conta Cora da Patrimonial.

        `code` = NOSSO id de conciliação (ecoado nas consultas). Retorna o dict
        da invoice (id inv_..., payment_options.bank_slip, pix.emv).
        """
        import uuid

        if valor_centavos < 500:
            raise BankingAdapterError("Cora: cobrança mínima é R$5,00 (500 centavos)")
        await self.ensure_authenticated()
        payload = {
            "code": code,
            "customer": {
                "name": cliente_nome[:60],
                "document": {"identity": "".join(c for c in cliente_documento if c.isdigit())},
                **({"email": cliente_email[:60]} if cliente_email else {}),
            },
            "services": [{"name": descricao[:60], "description": descricao[:100], "amount": valor_centavos}],
            "payment_terms": {"due_date": vencimento.isoformat()},
            "payment_forms": formas or ["BANK_SLIP", "PIX"],
        }
        async with self._client() as cli:
            resp = await cli.post(
                "/v2/invoices/",
                headers={**self._auth_headers(), "Idempotency-Key": self._idem_key("cobranca", code),
                         "Content-Type": "application/json"},
                json=payload,
            )
        if resp.status_code not in (200, 201):
            raise BankingAdapterError(f"Cora cobrança HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    async def consultar_cobranca(self, invoice_id: str) -> dict:
        await self.ensure_authenticated()
        async with self._client() as cli:
            resp = await cli.get(f"/v2/invoices/{invoice_id}", headers=self._auth_headers())
        if resp.status_code != 200:
            raise BankingAdapterError(f"Cora consulta HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    async def cancelar_cobranca(self, invoice_id: str) -> bool:
        """Cancela boleto NÃO pago (204). REC-0006 = já pago (não cancela)."""
        import uuid

        await self.ensure_authenticated()
        async with self._client() as cli:
            resp = await cli.delete(
                f"/v2/invoices/{invoice_id}",
                headers={**self._auth_headers(), "Idempotency-Key": self._idem_key("cancel-cob", invoice_id)},
            )
        if resp.status_code == 204:
            return True
        raise BankingAdapterError(f"Cora cancelamento HTTP {resp.status_code}: {resp.text[:200]}")

    # ------------------------------------------------------------------
    # SAÍDA DE DINHEIRO (produção) — o gate humano do ERP (OTP) é OBRIGATÓRIO
    # ANTES de chamar estes métodos. A API do Cora ainda devolve INITIATED até
    # a aprovação no app (config D7); o webhook payment.approved/completed fecha
    # o loop. Referência: docs/CORA_API_REFERENCIA_COMPLETA §4.
    # ------------------------------------------------------------------

    async def iniciar_pagamento_boleto(
        self, *, linha_digitavel: str, code: str, agendar_para: date | None = None
    ) -> dict:
        """Inicia pagamento de boleto por linha digitável. Retorna dict (id pay_...,
        status INITIATED). NÃO liquida sozinho enquanto D7 não estiver desligado."""
        import uuid

        await self.ensure_authenticated()
        payload: dict = {"digitable_line": "".join(c for c in linha_digitavel if c.isdigit()), "code": code}
        if agendar_para:
            payload["scheduled_at"] = agendar_para.isoformat()
        async with self._client() as cli:
            resp = await cli.post(
                "/payments/initiate",
                headers={**self._auth_headers(), "Idempotency-Key": self._idem_key("pgto-boleto", code),
                         "Content-Type": "application/json"},
                json=payload,
            )
        if resp.status_code not in (200, 201):
            raise BankingAdapterError(f"Cora pagamento HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    async def iniciar_darf(self, *, code: str, data: dict) -> dict:
        """Inicia pagamento de DARF (sem código de barras). `data` conforme §4.2:
        name, code(receita), identity, type='DARF', reference_date, due_date,
        amount{main,fine?,interest?}."""
        import uuid

        await self.ensure_authenticated()
        async with self._client() as cli:
            resp = await cli.post(
                "/payments/darf/initiate",
                headers={**self._auth_headers(), "Idempotency-Key": self._idem_key("darf", code),
                         "Content-Type": "application/json"},
                json={"code": code, "data": data},
            )
        if resp.status_code not in (200, 201):
            raise BankingAdapterError(f"Cora DARF HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    async def consultar_pagamento(self, payment_id: str) -> dict:
        """Consulta pagamento por id. Obs (§4.5): a lista /payments só mostra
        INITIATED — pós-aprovação acompanhe pelo webhook/extrato."""
        await self.ensure_authenticated()
        async with self._client() as cli:
            resp = await cli.get(f"/payments/{payment_id}", headers=self._auth_headers())
        if resp.status_code != 200:
            raise BankingAdapterError(f"Cora consulta pagto HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    async def cancelar_pagamento(self, payment_id: str) -> bool:
        """Cancela pagamento ainda não aprovado (204). PAY-0006 = não iniciado."""
        import uuid

        await self.ensure_authenticated()
        async with self._client() as cli:
            resp = await cli.delete(
                f"/payments/initiate/{payment_id}",
                headers={**self._auth_headers(), "Idempotency-Key": self._idem_key("cancel-pgto", payment_id)},
            )
        return resp.status_code == 204

    # Contrato BaseBankingAdapter: PIX POR CHAVE não existe na API pública do
    # Cora (§4.4) — para folha/diaristas usa-se transferência por dados
    # bancários OU o padrão "pago pelo app + conciliação".
    async def initiate_payment(self, request: PaymentRequest) -> PaymentResponse:
        if not request.barcode:
            raise NotImplementedError(
                "Cora: pagamento genérico exige linha digitável (barcode) — "
                "PIX por chave não é suportado pela API pública."
            )
        raw = await self.iniciar_pagamento_boleto(
            linha_digitavel=request.barcode,
            code=request.description or "pagamento",
            agendar_para=request.scheduled_date,
        )
        from modules.integrations.banking.adapters.base import PaymentStatus

        return PaymentResponse(
            payment_id=raw.get("id", ""),
            status=PaymentStatus.PENDING,  # INITIATED no Cora = aguardando aprovação
            amount=Decimal(int(raw.get("amount", 0))) / 100,
            error_message="Aguardando aprovação (Cora: INITIATED até D7)",
        )

    async def get_payment_status(self, payment_id: str) -> PaymentResponse:
        raw = await self.consultar_pagamento(payment_id)
        from modules.integrations.banking.adapters.base import PaymentStatus

        mapa = {"INITIATED": PaymentStatus.PENDING, "approved": PaymentStatus.PROCESSING,
                "completed": PaymentStatus.COMPLETED, "reproved": PaymentStatus.CANCELLED,
                "error": PaymentStatus.FAILED}
        return PaymentResponse(
            payment_id=payment_id,
            status=mapa.get(raw.get("status", ""), PaymentStatus.PENDING),
            amount=Decimal(int(raw.get("amount", 0))) / 100,
        )

    async def cancel_payment(self, payment_id: str) -> bool:
        return await self.cancelar_pagamento(payment_id)

    async def validate_pix_key(self, pix_key: str) -> PixKey:  # noqa: ARG002
        raise NotImplementedError(
            "Cora não expõe validação/envio de PIX por chave na API pública (§4.4)."
        )

    async def initiate_pix(self, request: PaymentRequest) -> PaymentResponse:  # noqa: ARG002
        raise NotImplementedError(
            "Cora: envio de PIX por chave não existe na API pública (§4.4) — "
            "use transferência por dados bancários ou 'pago pelo app + conciliação'."
        )
