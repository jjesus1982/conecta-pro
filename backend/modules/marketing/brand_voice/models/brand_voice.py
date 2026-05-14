"""
Model: marketing_brand_voice.

1 brand voice por condomino. Substitui o conteudo hardcoded da pagina
/modulos/marketing/brand-voice por dados editaveis no banco.

Schema:
- personality: lista de {label, description}
- tone_of_voice: lista de {title, description}
- keywords: lista de strings (palavras-chave da marca)
- avoid_list: lista de strings (o que evitar)
- slogan: texto
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import BaseModel


class BrandVoiceConfig(BaseModel):
    """Configuracao de brand voice de um condomino/empresa."""

    __tablename__ = "marketing_brand_voice"
    __table_args__ = (
        # 1 brand voice por condomino (pode ser ampliado pra versionamento depois)
        UniqueConstraint("condominio_id", name="uq_marketing_brand_voice_condominio"),
    )

    condominio_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="FK condominios.id (FK adicionada na migration)",
    )

    # Conteudo do brand voice (JSONB pra flexibilidade)
    personality: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Lista de {label, description} (ex: Profissional, Confiavel, ...)",
    )
    tone_of_voice: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Lista de {title, description} (ex: Formal mas acessivel, ...)",
    )
    keywords: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)),
        nullable=False,
        default=list,
        comment="Palavras-chave da marca",
    )
    avoid_list: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="O que evitar na comunicacao",
    )
    slogan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Auditoria adicional (alem do BaseModel)
    updated_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="Ultimo usuario que editou (FK users.id, lazy)",
    )

    def __repr__(self) -> str:
        return (
            f"<BrandVoiceConfig(id={self.id}, condominio={self.condominio_id}, "
            f"keywords={len(self.keywords)}, slogan={'sim' if self.slogan else 'nao'})>"
        )
