"""
Model: cwi_account_config (PRD Sec. 6.1).

Mapeamento 1:N de configuracoes de conexao com instancias Chatwoot.
Normalmente sera 1 unica linha (1 conta Chatwoot), mas o design
permite varias contas no futuro (multi-tenant).
"""
from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


class CwiAccountConfig(Base, TimestampMixin):
    """Config de conexao com uma instancia Chatwoot fazer.ai."""

    __tablename__ = "cwi_account_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    chatwoot_url: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Ex: https://chat.conectamais.pro",
    )
    chatwoot_account_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="ID da conta no Chatwoot (criada via UI)",
    )
    api_access_token: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Personal Access Token de um agente bot. CRIPTOGRAFADO em prod.",
    )
    webhook_secret: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="HMAC-SHA256 secret pra validar webhooks Chatwoot -> Conecta PRO",
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    def __repr__(self) -> str:
        return (
            f"<CwiAccountConfig(id={self.id}, url={self.chatwoot_url}, "
            f"account={self.chatwoot_account_id}, active={self.active})>"
        )
