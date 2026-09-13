"""Schemas — conformidade de vigilante (frente 05). Usados pelo controller do DP e pelas ações do redesign."""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

TipoCurso = Literal["formacao", "reciclagem_patrimonial", "reciclagem_escolta_armada", "reciclagem_vspp", "outro"]
TipoEquipamento = Literal["armamento", "colete"]


class CursoCreate(BaseModel):
    employee_id: UUID
    tipo: TipoCurso
    data_conclusao: date
    #: None = usa `system_configs.vigilante.reciclagem_validade_meses`
    validade_meses: int | None = Field(None, gt=0, le=120)
    local: str | None = Field(None, max_length=120)
    certificado_url: str | None = Field(None, max_length=2000)


class EquipamentoCreate(BaseModel):
    tipo: TipoEquipamento
    numero_serie: str = Field(..., min_length=1, max_length=60)
    modelo: str | None = Field(None, max_length=80)
    calibre: str | None = Field(None, max_length=20)


class EntregaCreate(BaseModel):
    employee_id: UUID
    observacao: str | None = Field(None, max_length=2000)


class DevolucaoCreate(BaseModel):
    observacao: str | None = Field(None, max_length=2000)


class NomeDeGuerraUpdate(BaseModel):
    #: identificação operacional — NÃO é `nome_social` (tratamento)
    nome_de_guerra: str | None = Field(None, max_length=60)
