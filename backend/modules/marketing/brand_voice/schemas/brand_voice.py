"""
Schemas Pydantic do brand_voice — request/response do endpoint.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PersonalityTrait(BaseModel):
    """Um traco da personalidade da marca."""

    label: str = Field(..., min_length=2, max_length=50, examples=["Profissional"])
    description: str = Field(..., min_length=5, max_length=300)


class ToneRule(BaseModel):
    """Uma regra de tom de voz."""

    title: str = Field(..., min_length=2, max_length=80, examples=["Formal mas acessivel"])
    description: str = Field(..., min_length=5, max_length=300)


class BrandVoiceResponse(BaseModel):
    """Brand voice retornado pelo endpoint GET."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    condominio_id: UUID
    personality: list[PersonalityTrait] = Field(default_factory=list)
    tone_of_voice: list[ToneRule] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    avoid_list: list[str] = Field(default_factory=list)
    slogan: Optional[str] = None

    updated_by_user_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class BrandVoiceUpdate(BaseModel):
    """Payload pra PUT — todos os campos opcionais (parcial)."""

    personality: Optional[list[PersonalityTrait]] = None
    tone_of_voice: Optional[list[ToneRule]] = None
    keywords: Optional[list[str]] = Field(
        default=None,
        min_length=3,
        max_length=20,
        description="Entre 3 e 20 palavras-chave",
    )
    avoid_list: Optional[list[str]] = None
    slogan: Optional[str] = Field(default=None, max_length=300)
