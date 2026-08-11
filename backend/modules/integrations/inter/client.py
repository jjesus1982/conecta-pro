"""D6 — InterClient: facade sobre InterAdapter com mTLS + OAuth2 + cache Redis.

Uso:
    async with InterClient() as client:
        saldo = await client.consultar_saldo()
        extrato = await client.consultar_extrato(inicio, fim)
"""

import os
from datetime import date

from modules.integrations.banking.adapters.base import BankCredentials
from modules.integrations.banking.adapters.inter import InterAdapter
from modules.integrations.inter.exceptions import InterAuthError, InterError


def _build_credentials() -> BankCredentials:
    return BankCredentials(
        client_id=os.getenv("INTER_CLIENT_ID", ""),
        client_secret=os.getenv("INTER_CLIENT_SECRET", ""),
        certificate_path=os.getenv("INTER_CERT_PATH"),
        private_key_path=os.getenv("INTER_KEY_PATH"),
        agency=os.getenv("INTER_AGENCY"),
        account=os.getenv("INTER_ACCOUNT"),
        environment=os.getenv("INTER_ENVIRONMENT", "production"),
    )


class InterClient:
    """Facade sobre InterAdapter — gerencia ciclo de vida e autenticação."""

    def __init__(self) -> None:
        self._adapter = InterAdapter(_build_credentials())

    async def __aenter__(self) -> "InterClient":
        ok = await self._adapter.authenticate()
        if not ok:
            raise InterAuthError("Falha ao autenticar com o Banco Inter (mTLS/OAuth2)")
        return self

    async def __aexit__(self, *args) -> None:
        await self._adapter.close()

    # ── Saldo ────────────────────────────────────────────────────────────────

    async def consultar_saldo(self, data: date | None = None):
        """Retorna AccountBalance com disponivel, bloqueado, total.

        `data` era aceita e IGNORADA — quem pedisse o saldo de 31/03 recebia o de
        hoje sem nenhum aviso, e acreditaria nele.
        """
        try:
            return await self._adapter.get_balance(data)
        except Exception as exc:
            raise InterError(f"Erro ao consultar saldo Inter: {exc}") from exc

    # ── Extrato ──────────────────────────────────────────────────────────────

    async def consultar_extrato(self, data_inicio: date, data_fim: date):
        """Retorna BankStatement com lista de BankTransaction."""
        try:
            return await self._adapter.get_statement(data_inicio, data_fim)
        except Exception as exc:
            raise InterError(f"Erro ao consultar extrato Inter: {exc}") from exc

    # ── Cobrança ─────────────────────────────────────────────────────────────

    async def emitir_cobranca(self, **kwargs):
        """Emite cobrança/boleto. kwargs passados direto para generate_boleto."""
        try:
            return await self._adapter.generate_boleto(**kwargs)
        except Exception as exc:
            raise InterError(f"Erro ao emitir cobrança Inter: {exc}") from exc

    async def consultar_cobranca(self, cobranca_id: str):
        """Consulta cobrança/boleto por ID."""
        try:
            return await self._adapter.get_boleto(cobranca_id)
        except Exception as exc:
            raise InterError(f"Erro ao consultar cobrança {cobranca_id}: {exc}") from exc

    async def cancelar_cobranca(self, cobranca_id: str, motivo: str = "ACERTOS"):
        """Cancela cobrança/boleto."""
        try:
            return await self._adapter.cancel_boleto(cobranca_id, motivo)
        except Exception as exc:
            raise InterError(f"Erro ao cancelar cobrança {cobranca_id}: {exc}") from exc

    # ── PIX (read-only — INV-8) ──────────────────────────────────────────────

    async def consultar_pix_recebidos(self, inicio: date | None = None, fim: date | None = None):
        """Retorna lista de PIX recebidos (somente leitura)."""
        try:
            return await self._adapter.get_pix_received()
        except Exception as exc:
            raise InterError(f"Erro ao consultar PIX recebidos: {exc}") from exc
