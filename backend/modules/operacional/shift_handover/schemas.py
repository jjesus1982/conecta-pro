"""
Schemas Pydantic do módulo de Passagem de Turno.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class PassagemTurnoCreate(BaseModel):
    """Payload de criação de passagem de turno."""

    post_id: str | None = Field(
        None,
        description="Posto da passagem. Opcional se o autor lidera exatamente 1 posto.",
    )
    turno: str = Field(..., min_length=1, max_length=30, description="Turno (livre: diurno/noturno/...)")
    resumo: str = Field(..., min_length=5, description="Resumo do turno")
    pendencias: str | None = Field(None, description="Pendências deixadas para o próximo turno")
    data_turno: date | None = Field(None, description="Data do turno (default: hoje)")

    @field_validator("turno", "resumo", "pendencias")
    @classmethod
    def strip_text(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v


class PassagemTurnoResponse(BaseModel):
    """Passagem de turno completa (com nome do posto)."""

    id: str
    post_id: str
    post_nome: str | None = None
    author_user_id: str
    author_nome: str
    turno: str
    resumo: str
    pendencias: str | None = None
    data_turno: date
    criada_em: datetime
    lida_por: list[dict[str, Any]] = Field(default_factory=list)


class PassagemTurnoListResponse(BaseModel):
    """Lista de passagens + a passagem anterior (leitura do turno seguinte)."""

    items: list[PassagemTurnoResponse]
    anterior: PassagemTurnoResponse | None = None


class PassagemLidaResponse(BaseModel):
    """Resultado da confirmação de leitura."""

    id: str
    ja_lida: bool = Field(..., description="True se o usuário já tinha confirmado leitura antes")
    lida_por: list[dict[str, Any]]
