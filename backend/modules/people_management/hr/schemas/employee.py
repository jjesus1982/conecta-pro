"""
Schemas Pydantic para Employee no contexto do Departamento Pessoal.

Visão DP-específica do funcionário: dados pessoais, trabalhistas e financeiros.
"""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DPEmployeeRead(BaseModel):
    """Schema de leitura de Employee para o DP."""

    model_config = ConfigDict(from_attributes=True)

    id: str | UUID
    nome: str
    nome_social: str | None = None
    cpf: str | None = None
    rg: str | None = None
    rg_orgao: str | None = None
    rg_uf: str | None = None
    email: str | None = None
    matricula: str | None = None
    cargo: str | None = None
    departamento: str | None = None
    status: str | None = None
    is_active: bool | None = None
    data_admissao: date | None = None
    data_demissao: date | None = None
    salario_base: float | None = None
    pis: str | None = None
    ctps_numero: str | None = None
    ctps_serie: str | None = None
    ctps_uf: str | None = None
    ctps_data_emissao: date | None = None
    telefone: str | None = None
    celular: str | None = None
    data_nascimento: date | None = None
    sexo: str | None = None
    estado_civil: str | None = None
    nacionalidade: str | None = None
    naturalidade: str | None = None
    nome_mae: str | None = None
    nome_pai: str | None = None
    # Endereço
    cep: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = None
    # Bancário
    banco: str | None = None
    agencia: str | None = None
    conta: str | None = None
    tipo_conta: str | None = None
    pix: str | None = None
    # Documentos extras
    titulo_eleitor: str | None = None
    zona_eleitoral: str | None = None
    secao_eleitoral: str | None = None
    certificado_reservista: str | None = None
    cnh_numero: str | None = None
    cnh_categoria: str | None = None
    cnh_validade: date | None = None
    # Vigilância
    curso_vigilante: str | None = None
    curso_vigilante_validade: date | None = None
    cnv: str | None = None
    cnv_validade: date | None = None
    # Contrato
    tipo_contrato: str | None = None
    regime_trabalho: str | None = None
    jornada_trabalho: str | None = None
    carga_horaria_semanal: float | None = None
    # Dependentes
    dependentes: list | dict | None = None
    contato_emergencia: str | None = None
    telefone_emergencia: str | None = None


class DPEmployeeList(BaseModel):
    """Schema para listagem paginada de Employees no DP."""

    model_config = ConfigDict(from_attributes=True)

    items: list[DPEmployeeRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class DPEmployeeUpdate(BaseModel):
    """Schema para atualização de dados DP do Employee — todos os campos editáveis."""

    # Dados pessoais
    nome: str | None = Field(None, max_length=200)
    nome_social: str | None = Field(None, max_length=200)
    cpf: str | None = Field(None, max_length=14)
    rg: str | None = Field(None, max_length=20)
    rg_orgao: str | None = Field(None, max_length=20)
    rg_uf: str | None = Field(None, max_length=2)
    data_nascimento: date | None = None
    sexo: str | None = Field(None, max_length=1)
    estado_civil: str | None = Field(None, max_length=30)
    nacionalidade: str | None = Field(None, max_length=50)
    naturalidade: str | None = Field(None, max_length=100)
    nome_mae: str | None = Field(None, max_length=200)
    nome_pai: str | None = Field(None, max_length=200)
    # Contato
    email: str | None = Field(None, max_length=200)
    telefone: str | None = Field(None, max_length=20)
    celular: str | None = Field(None, max_length=20)
    contato_emergencia: str | None = Field(None, max_length=100)
    telefone_emergencia: str | None = Field(None, max_length=20)
    # Endereço
    cep: str | None = Field(None, max_length=10)
    logradouro: str | None = Field(None, max_length=200)
    numero: str | None = Field(None, max_length=20)
    complemento: str | None = Field(None, max_length=100)
    bairro: str | None = Field(None, max_length=100)
    cidade: str | None = Field(None, max_length=100)
    uf: str | None = Field(None, max_length=2)
    # Profissional
    cargo: str | None = Field(None, max_length=100)
    cct_cargo_id: str | None = Field(None, description="UUID do cargo na CCT")
    departamento: str | None = Field(None, max_length=100)
    salario_base: float | None = None
    # Adicionais por funcionário (individuais, por posto/atividade)
    insalubridade_percentual: float | None = Field(None, ge=0, le=40)
    periculosidade_percentual: float | None = Field(None, ge=0, le=30)
    adicional_ronda_percentual: float | None = Field(None, ge=0, le=30)
    status: str | None = Field(None, max_length=50)
    tipo_contrato: str | None = Field(None, max_length=30)
    regime_trabalho: str | None = Field(None, max_length=30)
    jornada_trabalho: str | None = Field(None, max_length=50)
    carga_horaria_semanal: float | None = None
    data_admissao: date | None = None
    data_demissao: date | None = None
    # Documentos trabalhistas
    pis: str | None = Field(None, max_length=20)
    ctps_numero: str | None = Field(None, max_length=20)
    ctps_serie: str | None = Field(None, max_length=10)
    ctps_uf: str | None = Field(None, max_length=2)
    ctps_data_emissao: date | None = None
    titulo_eleitor: str | None = Field(None, max_length=20)
    zona_eleitoral: str | None = Field(None, max_length=10)
    secao_eleitoral: str | None = Field(None, max_length=10)
    certificado_reservista: str | None = Field(None, max_length=20)
    cnh_numero: str | None = Field(None, max_length=20)
    cnh_categoria: str | None = Field(None, max_length=5)
    cnh_validade: date | None = None
    # Vigilância
    curso_vigilante: str | None = Field(None, max_length=100)
    curso_vigilante_validade: date | None = None
    cnv: str | None = Field(None, max_length=30)
    cnv_validade: date | None = None
    # Bancário
    banco: str | None = Field(None, max_length=50)
    agencia: str | None = Field(None, max_length=20)
    conta: str | None = Field(None, max_length=30)
    tipo_conta: str | None = Field(None, max_length=20)
    pix: str | None = Field(None, max_length=100)
    # Dependentes e observações
    dependentes: list | dict | None = None
    observacoes: str | None = None
