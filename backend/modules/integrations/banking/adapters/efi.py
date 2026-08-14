"""Adapter Efí (Efí Bank, ex-Gerencianet) — PIX cash-out por API.

Por que a Efí existe aqui: o Cora **não envia PIX por API** (confirmado na doc dele —
nem por chave, nem por QR) e 99,8% do que sai da conta da Patrimonial é PIX. A Efí
envia, e liquida **sem aprovação em app** — é o que destrava pagar a folha de dentro
do sistema.

Mesma família de autenticação do `InterAdapter`: certificado (mTLS) + OAuth2
client_credentials. Por isso este arquivo se parece com `inter.py` e não com
`cora.py`.

Endpoints (documentação navegada em 14/08/2026, `dev.efipay.com.br/docs/api-pix`):

    POST /oauth/token                              → Bearer (Basic client_id:secret)
    PUT  /v3/gn/pix/{idEnvio}                      → envia PIX  ⭐ IDEMPOTENTE
    GET  /v2/gn/pix/enviados/id-envio/{idEnvio}    → status por idEnvio
    GET  /v2/gn/pix/enviados/{e2eId}               → status por e2eId
    POST /v2/gn/relatorios/extrato-conciliacao     → extrato (ASSÍNCRONO)

⭐ **Idempotência é do protocolo, não nossa.** A doc da Efí diz, textualmente, que
reenviar o mesmo `idEnvio` "garante que nenhum valor seja debitado mais de uma vez".
É o que torna seguro reprocessar um lote de folha que caiu no meio — e é a razão de
termos escolhido a Efí em vez do Asaas, onde não encontrei essa promessa.

⚠️ **Sem consulta de chave (DICT).** Varri a lista de escopos: não existe. Mitigação
acordada: enviar para a **chave CPF**. Quem não tiver chave CPF registrada devolve
erro no envio — falha, não paga errado. Chave CPF, se existe, pertence àquele CPF.

⚠️ **Limite diário pré-aprovado: R$0,30 (conta Pro) / R$1,00 (Empresas).** Alterar
exige conta Efí Empresas e pedido por escrito. Enquanto não subir, produção é teórica.

Homologação tem gatilhos DETERMINÍSTICOS por valor — ver `SANDBOX_GATILHOS`.
"""
from __future__ import annotations

import base64
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx

from .base import (
    AccountBalance,
    AccountType,
    BankCredentials,
    BankingAdapterError,
    BankStatement,
    BankTransaction,
    BaseBankingAdapter,
    PaymentStatus,
    TransactionType,
)

logger = logging.getLogger(__name__)

#: O sandbox da Efí responde pelo VALOR — dá para exercitar a máquina de estados
#: inteira sem depender de sorte. Documentado para quem for escrever o teste de
#: homologação: é isto que fecha os "confirmar no sandbox" do desenho original.
SANDBOX_GATILHOS = {
    "confirma": "R$0,01 a R$10,00 — Pix confirmado, resultado por webhook",
    "rejeita_webhook": "R$10,01 a R$20,00 — rejeitado, resultado por webhook",
    "rejeita_request": "acima de R$20,00 — rejeitado já na requisição, sem webhook",
    "duas_devolucoes": "R$4,00 — gera DUAS devoluções de R$2,00",
    "uma_devolucao": "R$5,00 — gera UMA devolução de R$5,00",
}

#: Efí → `PaymentStatus`, o mesmo vocabulário que Cora e BB usam. A primeira versão
#: deste dicionário inventava strings próprias ("LIQUIDADO"), que não casavam com
#: nada no sistema — status de pagamento em língua particular é como um pagamento
#: confirmado no banco fica "pendente" para sempre aqui dentro.
STATUS_EFI = {
    "EM_PROCESSAMENTO": PaymentStatus.PROCESSING,
    "REALIZADO": PaymentStatus.COMPLETED,
    "NAO_REALIZADO": PaymentStatus.FAILED,
    "DEVOLVIDO": PaymentStatus.RETURNED,
}


class EfiError(BankingAdapterError):
    """Erro da Efí. `retryavel` diz ao orquestrador se pode reenviar o MESMO idEnvio."""

    def __init__(self, msg: str, *, status: int | None = None,
                 retryavel: bool = False, corpo: Any = None):
        super().__init__(msg)
        self.status = status
        self.retryavel = retryavel
        self.corpo = corpo


class EfiAdapter(BaseBankingAdapter):
    """Uma instância por conta pagadora (por CNPJ)."""

    BANK_CODE = "364"
    BANK_NAME = "Efí Bank"
    BASE_PRODUCAO = "https://pix.api.efipay.com.br"
    BASE_HOMOLOGACAO = "https://pix-h.api.efipay.com.br"

    def __init__(self, credentials: BankCredentials):
        super().__init__(credentials)
        self._token: str | None = None
        self._token_exp: datetime | None = None

    # ── transporte ───────────────────────────────────────────────────────────
    @property
    def base_url(self) -> str:
        return (self.BASE_PRODUCAO if (self.credentials.environment or "").lower() == "production"
                else self.BASE_HOMOLOGACAO)

    def _client(self) -> httpx.AsyncClient:
        cert = self.credentials.certificate_path
        if cert and self.credentials.private_key_path:
            cert = (self.credentials.certificate_path, self.credentials.private_key_path)
        return httpx.AsyncClient(base_url=self.base_url, cert=cert, timeout=30.0)

    async def authenticate(self) -> bool:
        basic = base64.b64encode(
            f"{self.credentials.client_id}:{self.credentials.client_secret}".encode()).decode()
        async with self._client() as cli:
            r = await cli.post("/oauth/token",
                               headers={"Authorization": f"Basic {basic}",
                                        "Content-Type": "application/json"},
                               json={"grant_type": "client_credentials"})
        if r.status_code != 200:
            raise EfiError(f"Efí OAuth {r.status_code}", status=r.status_code, corpo=r.text[:200])
        self._token = r.json()["access_token"]
        return True

    async def _headers(self) -> dict[str, str]:
        if not self._token:
            await self.authenticate()
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    # ── envio (o motivo de existir) ──────────────────────────────────────────
    async def enviar_pix(self, *, id_envio: str, valor: Decimal, chave_origem: str,
                         chave_destino: str, info_pagador: str = "") -> dict[str, Any]:
        """`PUT /v3/gn/pix/{idEnvio}`. O idEnvio é a chave de idempotência.

        Reenviar o MESMO idEnvio depois de um timeout NÃO debita duas vezes — é
        promessa da própria Efí, e é o que torna seguro reprocessar folha.

        Erro de rede vira `retryavel=True` (reenvia com o mesmo idEnvio); 4xx de
        negócio vira `retryavel=False` (chave inválida, saldo — não adianta insistir).
        """
        corpo = {
            "valor": _reais(valor),
            "pagador": {"chave": chave_origem, "infoPagador": (info_pagador or "")[:140]},
            "favorecido": {"chave": chave_destino},
        }
        try:
            async with self._client() as cli:
                r = await cli.put(f"/v3/gn/pix/{id_envio}", headers=await self._headers(),
                                  json=corpo)
        except httpx.TransportError as e:
            raise EfiError(f"transporte no envio {id_envio}: {e}", retryavel=True) from e

        if r.status_code in (200, 201, 202):
            return r.json()
        if r.status_code == 429 or r.status_code >= 500:
            raise EfiError(f"Efí {r.status_code} no envio {id_envio}", status=r.status_code,
                           retryavel=True, corpo=r.text[:300])
        raise EfiError(f"Efí recusou o envio {id_envio}: {r.status_code}",
                       status=r.status_code, retryavel=False, corpo=r.text[:300])

    async def consultar_envio(self, id_envio: str) -> dict[str, Any]:
        """Status por idEnvio. É a rede contra webhook perdido — e o que o Cora não dá
        (lá, aprovado no app vira 404 e ficamos cegos até o extrato)."""
        async with self._client() as cli:
            r = await cli.get(f"/v2/gn/pix/enviados/id-envio/{id_envio}",
                              headers=await self._headers())
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            raise EfiError("idEnvio não encontrado", status=404, retryavel=False)
        raise EfiError(f"consulta {id_envio}: {r.status_code}", status=r.status_code,
                       retryavel=r.status_code >= 500, corpo=r.text[:200])

    @staticmethod
    def mapear_status(efi_status: str | None) -> PaymentStatus | None:
        """Efí → `PaymentStatus`. Devolve None quando o status não é conhecido:
        inventar equivalência de status de pagamento é como se marca pago o que
        falhou."""
        return STATUS_EFI.get((efi_status or "").upper()) if efi_status else None

    # ── leitura ──────────────────────────────────────────────────────────────
    async def get_balance(self) -> AccountBalance:
        async with self._client() as cli:
            r = await cli.get("/v2/gn/saldo", headers=await self._headers())
        if r.status_code != 200:
            raise EfiError(f"saldo Efí {r.status_code}", status=r.status_code, corpo=r.text[:200])
        d = r.json()
        saldo = Decimal(str(d.get("saldo") or d.get("disponivel") or 0))
        return AccountBalance(available=saldo, current=saldo, blocked=Decimal("0"),
                              limit=Decimal("0"), updated_at=datetime.now())

    async def get_statement(self, start_date: date, end_date: date) -> BankStatement:
        """⚠️ O extrato da Efí é ASSÍNCRONO — `POST /v2/gn/relatorios/extrato-conciliacao`
        pede o relatório e depois se consulta o resultado. Não é igual a nenhum dos dois
        moldes que temos (Inter e Cora são síncronos), e por isso o
        `efi_sync_service` não sai de graça a partir dos existentes.

        Fica declarado em vez de fingir: devolver extrato vazio aqui faria a conciliação
        pensar que não houve movimento.
        """
        raise NotImplementedError(
            "extrato da Efí é assíncrono (POST /v2/gn/relatorios/extrato-conciliacao): "
            "pedir o relatório, aguardar e consultar. Implementar em efi_sync_service, "
            "não aqui.")

    # ── money-out pelos nomes do contrato base ───────────────────────────────
    async def initiate_pix(self, *args, **kwargs):  # noqa: D102 — ver enviar_pix
        raise NotImplementedError(
            "use enviar_pix(id_envio=...): a idempotência da Efí exige o idEnvio no path, "
            "e o contrato genérico não tem onde carregá-lo.")

    async def initiate_payment(self, *args, **kwargs):  # noqa: D102
        raise NotImplementedError("Efí neste adapter é só PIX de saída (cash-out).")

    async def get_payment_status(self, payment_id: str):  # noqa: D102
        return await self.consultar_envio(payment_id)

    async def cancel_payment(self, payment_id: str):  # noqa: D102
        raise NotImplementedError("Efí não expõe cancelamento de PIX enviado.")

    async def validate_pix_key(self, key: str):
        """A Efí NÃO tem consulta de chave. Devolve None — e None aqui significa
        "não sei", não "inválida".

        Não fingir que valida é o ponto: o `validate_pix_key` do Inter aponta para um
        endpoint que não existe (404), engole o erro e devolve None — parecia validar e
        mentia por omissão há meses. A mitigação acordada é enviar para a chave CPF.
        """
        return None


def _reais(valor: Decimal) -> str:
    """Efí espera string com 2 casas ("150.00")."""
    v = Decimal(str(valor))
    if v <= 0:
        raise ValueError("valor deve ser > 0")
    return f"{v:.2f}"


def credenciais_efi_do_env() -> BankCredentials:
    """Credenciais da conta Efí (Patrimonial, CNPJ 66.014.833/0001-10) pelo env."""
    import os

    return BankCredentials(
        client_id=os.getenv("EFI_CLIENT_ID", ""),
        client_secret=os.getenv("EFI_CLIENT_SECRET", ""),
        certificate_path=os.getenv("EFI_CERT_PATH", "/app/credentials/efi/certificado.pem"),
        private_key_path=os.getenv("EFI_KEY_PATH") or None,
        environment=os.getenv("EFI_ENV", "homologation"),
    )
