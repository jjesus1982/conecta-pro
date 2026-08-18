"""Adapter Asaas (Asaas IP S.A.) — PIX de saída por chave + CONSULTA DE CHAVE.

Por que a Asaas entrou: a Efí **recusou** a abertura de conta em 17/08/2026, e o
problema de origem não mudou — a folha e as diárias são da **Patrimonial**, e o Cora,
banco dela, não envia PIX por API. Hoje o pagamento sai pelo Inter, que é da
**Eletrônica**, e vira mútuo entre empresas todo mês.

⭐ **O que só ela dá: consulta de chave PIX.** Digitar a chave e ver o nome do titular
antes de pagar — o que o app do banco faz e o nosso sistema não fazia. O
`validate_pix_key` do Inter aponta para um endpoint que responde 404, engole o erro e
devolve `None`: nunca validou nada. Sondei seis formatos de endpoint e o escopo
`dict.read` não está liberado para a nossa aplicação no Inter.

⚠️ **Idempotência do envio: NÃO documentada.** A Efí prometia no endpoint ("reenviar o
mesmo idEnvio garante que nenhum valor seja debitado mais de uma vez"); na Asaas eu não
achei essa promessa — existe `externalReference`, que é identificador no nosso sistema,
sem compromisso de deduplicação. **Isso não é detalhe:** num lote de 54 pagamentos, um
timeout no meio deixa sem saber se aquela pessoa recebeu, e reenviar pode pagar duas
vezes. Enquanto a Asaas não confirmar por escrito, o reenvio deste adapter exige
consultar antes — ver `enviar_pix(confirmar_antes=True)`.

Autenticação: chave de API no header `access_token` (não é OAuth2/mTLS como Inter e
Efí). Mais simples de escrever, e um padrão a menos que já dominamos.

Endpoints — documentação navegada com navegador em 18/08/2026 (`docs.asaas.com`, 505
endpoints na referência). Conferidos um a um, não de memória:

    GET  /v3/pix/addressKeys/external?type=&key=  → consulta de chave (DICT)
    POST /v3/transfers                            → transferência (PIX ou TED)
    GET  /v3/transfers/{id}                       → status
    POST /v3/transfers/{id}/cancel                → cancelar
    GET  /v3/finance/balance                      → saldo
    GET  /v3/financialTransactions                → extrato (conciliação)
    GET  /v3/pix/transactions?endToEndIdentifier= → transação Pix pelo E2E do Bacen

⚠️ Dois erros que eu tinha escrito de cabeça e a documentação desmentiu:
  · a consulta de chave NÃO leva a chave no path — é caminho fixo com query params;
  · a transferência exige `pixAddressKeyType` (CPF/CNPJ/EMAIL/PHONE/EVP), campo que a
    primeira versão nem mandava.

⚠️ **GET com body devolve 403.** Está escrito na página de códigos HTTP deles.

⚠️ **Cota: 25.000 requisições por conta a cada 12h**, além do rate limit por endpoint
(cabeçalhos `RateLimit-*`, 429 ao estourar). Consultar a chave antes de cada envio gasta
DUAS chamadas por pessoa — uma folha de 54 gasta 108.

Eventos de webhook (7): TRANSFER_CREATED · TRANSFER_PENDING · TRANSFER_IN_BANK_PROCESSING
· TRANSFER_BLOCKED · TRANSFER_DONE · TRANSFER_FAILED · TRANSFER_CANCELLED.

⚠️ Webhook é **at least once**: o mesmo evento pode chegar mais de uma vez, então o
handler precisa ser idempotente. E se a nossa ponta falhar **15 vezes seguidas** a fila é
INTERROMPIDA — os eventos continuam sendo gerados e não chegam, e o que ficar parado mais
de **14 dias é apagado para sempre**. Por isso o endpoint tem que responder 2xx rápido e
processar depois, nunca processar de forma síncrona.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx

from .base import (
    AccountBalance,
    BankCredentials,
    BankingAdapterError,
    BaseBankingAdapter,
    PaymentStatus,
)

logger = logging.getLogger(__name__)

#: Asaas → o vocabulário compartilhado dos adapters. `BLOCKED` vira PENDING de
#: propósito: bloqueado é análise em curso, não fracasso — tratar como FAILED faria o
#: sistema desistir de um pagamento que ainda pode sair, e alguém pagaria de novo.
STATUS_ASAAS = {
    "PENDING": PaymentStatus.PENDING,
    "BANK_PROCESSING": PaymentStatus.PROCESSING,
    "IN_BANK_PROCESSING": PaymentStatus.PROCESSING,
    "BLOCKED": PaymentStatus.PENDING,
    "DONE": PaymentStatus.COMPLETED,
    "FAILED": PaymentStatus.FAILED,
    "CANCELLED": PaymentStatus.CANCELLED,
}


class AsaasError(BankingAdapterError):
    """Erro da Asaas. `retryavel` diz se dá para repetir a MESMA requisição."""

    def __init__(self, msg: str, *, status: int | None = None,
                 retryavel: bool = False, corpo: Any = None):
        super().__init__(msg)
        self.status = status
        self.retryavel = retryavel
        self.corpo = corpo


class ChavePixInvalida(AsaasError):
    """A chave não existe no DICT. Diferente de erro de rede: não adianta repetir."""


class AsaasAdapter(BaseBankingAdapter):
    BANK_CODE = "461"          # Asaas IP S.A.
    BANK_NAME = "Asaas"
    BASE_PRODUCAO = "https://api.asaas.com/v3"
    BASE_SANDBOX = "https://api-sandbox.asaas.com/v3"

    def __init__(self, credentials: BankCredentials):
        super().__init__(credentials)

    @property
    def base_url(self) -> str:
        prod = (self.credentials.environment or "").lower() in ("production", "producao")
        return self.BASE_PRODUCAO if prod else self.BASE_SANDBOX

    def _headers(self) -> dict[str, str]:
        return {
            "access_token": self.credentials.client_secret or "",
            "Content-Type": "application/json",
            "User-Agent": "ConectaPRO/1.0",
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    async def authenticate(self) -> bool:
        """Não há fluxo de token: a chave de API já é a credencial. Valida chamando o
        saldo — sem isso, "autenticado" seria só a ausência de teste."""
        await self.get_balance()
        return True


    @staticmethod
    def tipo_de_chave(chave: str) -> str:
        """CPF · CNPJ · EMAIL · PHONE · EVP — o enum que a Asaas exige.

        Ordem importa: e-mail primeiro (tem @), depois telefone (começa com + ou tem 12+
        dígitos), depois documento por contagem. EVP é o aleatório de 32+ caracteres.
        """
        c = (chave or "").strip()
        if "@" in c:
            return "EMAIL"
        dig = "".join(ch for ch in c if ch.isdigit())
        if c.startswith("+") or len(dig) in (12, 13):
            return "PHONE"
        if len(dig) == 14:
            return "CNPJ"
        if len(dig) == 11:
            return "CPF"
        return "EVP"

    @staticmethod
    def _rate_limit(r: httpx.Response) -> dict[str, int]:
        """Lê os cabeçalhos de limite. A Asaas devolve `RateLimit-Remaining` e
        `RateLimit-Reset`, e tem COTA de 25.000 requisições por conta a cada 12h —
        um lote de folha que consulta chave antes de cada envio gasta duas por pessoa.
        Ignorar isso é descobrir o teto no meio do pagamento."""
        def _i(nome: str) -> int:
            try:
                return int(r.headers.get(nome, "") or -1)
            except ValueError:
                return -1
        return {"limite": _i("RateLimit-Limit"), "restante": _i("RateLimit-Remaining"),
                "reset_s": _i("RateLimit-Reset")}

    # ── o motivo de existir: conferir a chave ANTES de pagar ──────────────────
    async def validate_pix_key(self, key: str, tipo: str | None = None) -> dict[str, Any] | None:
        """Consulta o DICT e devolve o titular da chave.

        `None` significa **não sei** (a consulta falhou); chave inexistente levanta
        `ChavePixInvalida`. Os dois casos são diferentes e confundi-los é o defeito do
        adapter do Inter, que devolvia `None` para tudo e parecia validar.
        """
        try:
            async with self._client() as cli:
                # ⚠️ Caminho FIXO + query params. A primeira versão punha a chave no
                # path (`/pix/addressKeys/{key}`) — inventado por mim, não é a API.
                # E NUNCA mandar body em GET: a Asaas devolve 403 quando isso acontece.
                r = await cli.get("/pix/addressKeys/external", headers=self._headers(),
                                  params={"type": tipo or self.tipo_de_chave(key), "key": key})
        except httpx.TransportError as exc:
            logger.warning("Asaas: consulta de chave %s falhou no transporte: %s", key[:6], exc)
            return None

        if r.status_code == 200:
            # Formato CONFERIDO contra a API em 18/08/2026 (sandbox, chave EVP real):
            #   {type, key, ispb, ispbName, financialInstitution:{name,code,bank},
            #    owner:{name, cpfCnpj}}
            # O titular vem ANINHADO em `owner` — não existe `ownerName` no topo. E o
            # banco vem em `financialInstitution`, não em `bank`/`bankName`, que era o
            # que eu lia: o campo voltava vazio e o operador não veria a instituição.
            d = r.json() or {}
            dono = d.get("owner") or {}
            inst = d.get("financialInstitution") or {}
            return {
                "chave": key,
                "tipo": d.get("type") or d.get("addressKeyType"),
                "titular": dono.get("name") or d.get("ownerName"),
                "documento": dono.get("cpfCnpj") or d.get("cpfCnpj"),
                "banco": inst.get("name") or d.get("ispbName"),
                "banco_codigo": inst.get("code") or (inst.get("bank") or {}).get("code"),
                "ispb": d.get("ispb"),
            }
        if r.status_code == 404:
            # 404 com corpo VAZIO = chave válida no formato, mas não registrada no DICT.
            # Confirmado contra a API: uma chave EVP recém-criada devolve 200, e um
            # CPF/CNPJ legítimo porém não cadastrado devolve 404 sem corpo.
            raise ChavePixInvalida(f"chave PIX não registrada no DICT: {key}",
                                   status=404, corpo=r.text[:200])
        if r.status_code == 400:
            # 400 traz JSON explicando: {"errors":[{"code":..., "description":...}]}.
            # É chave MALFORMADA, não inexistente — casos diferentes, e os dois
            # significam "não pague".
            motivo = r.text[:200]
            try:
                motivo = (r.json().get("errors") or [{}])[0].get("description") or motivo
            except Exception:  # noqa: BLE001 - corpo não-JSON não pode derrubar a consulta
                pass
            raise ChavePixInvalida(f"chave PIX inválida: {motivo}", status=400, corpo=r.text[:200])
        logger.warning("Asaas: consulta de chave devolveu %s", r.status_code)
        return None

    # ── money-out ─────────────────────────────────────────────────────────────
    async def enviar_pix(self, *, valor: Decimal, chave: str, referencia: str,
                         descricao: str = "", confirmar_antes: bool = True) -> dict[str, Any]:
        """Transferência PIX por chave.

        ⚠️ `confirmar_antes=True` por padrão porque a Asaas **não documenta
        idempotência**. Antes de enviar, procura transferência já existente com o mesmo
        `externalReference`; se achar, devolve a existente em vez de mandar de novo.
        Não é garantia do banco — é a rede que dá para armar do nosso lado, e some no dia
        em que eles confirmarem deduplicação por escrito.
        """
        if confirmar_antes:
            ja = await self.buscar_por_referencia(referencia)
            if ja:
                logger.warning("Asaas: transferência %s já existe (%s) — não reenviando",
                               referencia, ja.get("id"))
                return {**ja, "ja_existia": True}

        corpo = {
            "value": float(Decimal(str(valor))),
            "pixAddressKey": chave,
            # O TIPO da chave é campo próprio (`pixAddressKeyType`) e a primeira versão
            # deste adapter não o mandava. Sem ele a Asaas precisa adivinhar, e chave de
            # telefone que "parece" CPF é como se paga a pessoa errada.
            "pixAddressKeyType": self.tipo_de_chave(chave),
            "operationType": "PIX",
            "externalReference": referencia,
        }
        if descricao:
            corpo["description"] = descricao[:255]
        try:
            async with self._client() as cli:
                r = await cli.post("/transfers", headers=self._headers(), json=corpo)
        except httpx.TransportError as exc:
            # Transporte caiu: NÃO é seguro reenviar às cegas sem idempotência do banco.
            raise AsaasError(f"transporte no envio {referencia}: {exc}", retryavel=False) from exc

        if r.status_code in (200, 201):
            return r.json()
        if r.status_code == 429 or r.status_code >= 500:
            raise AsaasError(f"Asaas {r.status_code} no envio {referencia}",
                             status=r.status_code, retryavel=True, corpo=r.text[:300])
        raise AsaasError(f"Asaas recusou o envio {referencia}: {r.status_code}",
                         status=r.status_code, retryavel=False, corpo=r.text[:300])

    async def buscar_por_referencia(self, referencia: str) -> dict[str, Any] | None:
        """Transferência já enviada com esse `externalReference`, se houver."""
        try:
            async with self._client() as cli:
                r = await cli.get("/transfers", headers=self._headers(),
                                  params={"externalReference": referencia, "limit": 1})
            if r.status_code == 200:
                dados = (r.json() or {}).get("data") or []
                return dados[0] if dados else None
        except Exception as exc:  # noqa: BLE001 — consulta é rede de segurança, não gate
            logger.warning("Asaas: busca por referência %s falhou: %s", referencia, exc)
        return None

    async def get_payment_status(self, payment_id: str) -> dict[str, Any]:
        async with self._client() as cli:
            r = await cli.get(f"/transfers/{payment_id}", headers=self._headers())
        if r.status_code == 200:
            return r.json()
        raise AsaasError(f"status {payment_id}: {r.status_code}", status=r.status_code,
                         retryavel=r.status_code >= 500, corpo=r.text[:200])

    @staticmethod
    def mapear_status(status: str | None) -> PaymentStatus | None:
        """Asaas → `PaymentStatus`. `None` quando desconhecido: inventar equivalência de
        status de pagamento é como se marca pago o que falhou."""
        return STATUS_ASAAS.get((status or "").upper()) if status else None

    # ── leitura ───────────────────────────────────────────────────────────────
    async def get_balance(self) -> AccountBalance:
        async with self._client() as cli:
            r = await cli.get("/finance/balance", headers=self._headers())
        if r.status_code != 200:
            raise AsaasError(f"saldo Asaas {r.status_code}", status=r.status_code,
                             corpo=r.text[:200])
        saldo = Decimal(str((r.json() or {}).get("balance", 0)))
        return AccountBalance(available=saldo, blocked=Decimal("0"), total=saldo)

    async def get_statement(self, start_date: date, end_date: date):
        """Extrato — implementado em `asaas_sync_service`, não aqui.

        Declarado em vez de devolver lista vazia: extrato vazio faria a conciliação
        concluir que não houve movimento, que é pior que não ter extrato.
        """
        raise NotImplementedError(
            "extrato da Asaas: GET /v3/financialTransactions, paginado. Implementar no "
            "asaas_sync_service, no molde de cora_sync_service (191 linhas).")

    async def initiate_pix(self, *args, **kwargs):  # noqa: D102
        raise NotImplementedError("use enviar_pix(referencia=...): sem idempotência do "
                                  "banco, a referência é obrigatória para a rede de segurança.")

    async def initiate_payment(self, *args, **kwargs):  # noqa: D102
        raise NotImplementedError("Asaas neste adapter é só PIX de saída por chave.")

    async def cancel_payment(self, payment_id: str) -> dict[str, Any]:
        async with self._client() as cli:
            r = await cli.post(f"/transfers/{payment_id}/cancel", headers=self._headers())
        if r.status_code in (200, 201):
            return r.json()
        raise AsaasError(f"cancelamento {payment_id}: {r.status_code}", status=r.status_code,
                         corpo=r.text[:200])


def credenciais_asaas_do_env() -> BankCredentials:
    """Credenciais da conta Asaas (Patrimonial, CNPJ 66.014.833/0001-10)."""
    return BankCredentials(
        client_id="asaas",
        client_secret=os.getenv("ASAAS_API_KEY", ""),
        environment=os.getenv("ASAAS_ENV", "sandbox"),
    )
