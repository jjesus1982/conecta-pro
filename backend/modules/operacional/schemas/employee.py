"""
Schemas Pydantic para Employee (Funcionário).
"""

import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class EmployeeBase(BaseModel):
    """Schema base para Employee."""

    nome: str = Field(..., min_length=1, max_length=200)
    email: EmailStr | None = None
    matricula: str | None = Field(None, max_length=50)
    cpf: str | None = Field(None, max_length=14)
    cargo: str | None = Field(None, max_length=100)
    cct_cargo_id: str | None = Field(None, description="UUID do cargo na CCT (fonte única do piso/adicionais)")
    departamento: str | None = Field(None, max_length=100)
    telefone: str | None = Field(None, max_length=20)
    status: str | None = Field(default="Ativo", max_length=50)

    @field_validator("cpf")
    @classmethod
    def validar_cpf(cls, v):
        """Valida formato de CPF."""
        if v is None:
            return v
        # Remove caracteres não numéricos
        cpf = re.sub(r"\D", "", v)
        if len(cpf) != 11:
            raise ValueError("CPF deve ter 11 dígitos")
        return cpf

    @field_validator("telefone")
    @classmethod
    def validar_telefone(cls, v):
        """Valida formato de telefone."""
        if v is None:
            return v
        # Remove caracteres não numéricos
        telefone = re.sub(r"\D", "", v)
        if len(telefone) < 10 or len(telefone) > 11:
            raise ValueError("Telefone deve ter 10 ou 11 dígitos")
        return telefone


class EmployeeCreate(EmployeeBase):
    """Schema para criação de Employee."""

    # Campos obrigatórios na criação
    nome: str = Field(..., min_length=1, max_length=200, description="Nome completo do funcionário")
    email: EmailStr = Field(..., description="Email corporativo único")
    matricula: str = Field(..., min_length=1, max_length=50, description="Matrícula única")

    # Campos opcionais
    data_admissao: str | None = None
    pis: str | None = None


class EmployeeUpdate(BaseModel):
    """Schema para atualização de Employee."""

    cargo: str | None = Field(None, max_length=100)
    cct_cargo_id: str | None = Field(None, description="UUID do cargo na CCT")
    insalubridade_percentual: float | None = Field(None, ge=0, le=40, description="Insalubridade % (por atividade/posto)")
    periculosidade_percentual: float | None = Field(None, ge=0, le=30, description="Periculosidade %")
    adicional_ronda_percentual: float | None = Field(None, ge=0, le=30, description="Adicional de ronda % (CCT)")
    departamento: str | None = Field(None, max_length=100)
    telefone: str | None = Field(None, max_length=20)
    status: str | None = Field(None, max_length=50)
    email: EmailStr | None = None

    @field_validator("telefone")
    @classmethod
    def validar_telefone(cls, v):
        """Valida formato de telefone."""
        if v is None:
            return v
        telefone = re.sub(r"\D", "", v)
        if len(telefone) < 10 or len(telefone) > 11:
            raise ValueError("Telefone deve ter 10 ou 11 dígitos")
        return telefone


class EmployeeResponse(BaseModel):
    """Schema de resposta para Employee."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    nome: str
    email: str | None = None
    matricula: str | None = None
    cargo: str | None = None
    departamento: str | None = None
    status: str | None = None
    cpf: str | None = None
    telefone: str | None = None
    data_admissao: str | None = None


class EmployeeListResponse(BaseModel):
    """Schema para listagem paginada de Employees."""

    items: list[EmployeeResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ==================== INTEGRAÇÃO SOLIDES DP ====================


class SolidesEmployeeResponse(BaseModel):
    """Schema de resposta para funcionario do Solides DP."""

    id: str
    nome: str
    email: str | None = None
    matricula: str | None = None
    cargo: str | None = None
    departamento: str | None = None
    status: str | None = None
    cpf: str | None = None
    telefone: str | None = None
    data_admissao: str | None = None
    pis: str | None = None


class SolidesEmployeeListResponse(BaseModel):
    """Schema para listagem de funcionarios do Solides."""

    items: list[SolidesEmployeeResponse]
    total: int
    source: str = "solides"
