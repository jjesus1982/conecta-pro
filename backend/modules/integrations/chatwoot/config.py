"""
Configuracao do modulo chatwoot_integration.

Le variaveis de ambiente prefixadas com CHATWOOT_*. Valores
default sao seguros pra dev (apontam pra Chatwoot local que
ainda nao existe). Producao define via .env (responsabilidade
do Jordan no deploy, Slice futuro).
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChatwootSettings(BaseSettings):
    """Configuracao do cliente Chatwoot (PRD Sec. 6.1 - cwi_account_config)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CHATWOOT_",
        case_sensitive=False,
        extra="ignore",
    )

    # URL base do Chatwoot fazer.ai (sem barra no final)
    # Producao alvo: https://chat.conectamais.pro
    base_url: str = Field(
        default="http://localhost:3003",
        description="URL base da instancia Chatwoot",
    )

    # ID da conta no Chatwoot (criada manualmente via UI durante setup)
    account_id: int = Field(
        default=1,
        description="ID numerico da conta Chatwoot",
    )

    # Token de API (gerado via UI do Chatwoot, perfil do bot)
    api_token: SecretStr = Field(
        default=SecretStr(""),
        description="Personal Access Token de um agente bot",
    )

    # Secret pra validar HMAC dos webhooks Chatwoot -> Conecta PRO
    webhook_secret: SecretStr = Field(
        default=SecretStr(""),
        description="HMAC-SHA256 secret pra verificar webhooks",
    )

    # Configs do cliente HTTP
    http_timeout_seconds: float = Field(
        default=10.0,
        description="Timeout de cada request (Sec. 7.2 do PRD)",
    )
    http_max_retries: int = Field(
        default=3,
        description="Numero maximo de tentativas em caso de falha transitoria",
    )
    http_retry_backoff_base_seconds: float = Field(
        default=0.5,
        description="Backoff base pra retry exponencial (0.5, 1.0, 2.0, ...)",
    )

    @property
    def api_base(self) -> str:
        """Caminho base da API REST: /api/v1/accounts/{account_id}."""
        return f"{self.base_url.rstrip('/')}/api/v1/accounts/{self.account_id}"


@lru_cache
def get_chatwoot_settings() -> ChatwootSettings:
    """Cacheia o settings (Pydantic recomenda)."""
    return ChatwootSettings()
