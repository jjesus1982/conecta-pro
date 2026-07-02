"""
Schemas PPRA/PGR (NR-9) - Mapeamento de Riscos
==============================================

Schemas Pydantic para endpoints PPRA.
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ==============================================================================
# Risk Mapping Schemas
# ==============================================================================


class OccupationalRiskRequest(BaseModel):
    """Request para risco ocupacional."""

    categoria: str = Field(
        ...,
        description="Categoria do risco",
        pattern=r"^(fisico|quimico|biologico|ergonomico|acidente)$",
    )
    agente: str = Field(..., min_length=2, max_length=50, description="Agente de risco")
    descricao: str | None = Field(None, description="Descricao do risco")
    fonte_geradora: str = Field(..., min_length=2, max_length=200)
    meio_propagacao: str | None = Field(None, max_length=200)
    funcoes_expostas: list[str] = Field(default_factory=list)
    numero_expostos: int | None = Field(None, ge=0)
    tempo_exposicao: str | None = Field(None, max_length=50)
    probabilidade: int | None = Field(None, ge=1, le=5)
    severidade: int | None = Field(None, ge=1, le=5)
    valor_medido: float | None = None
    unidade_medida: str | None = None
    limite_tolerancia: float | None = None
    medidas_existentes: list[str] = Field(default_factory=list)
    epis_recomendados: list[str] = Field(default_factory=list)
    exames_requeridos: list[str] = Field(default_factory=list)
    prioridade: int = Field(default=3, ge=1, le=5)


class RiskMappingRequest(BaseModel):
    """Request para mapeamento de riscos."""

    setor: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Setor a mapear",
    )
    descricao_setor: str | None = Field(None, description="Descricao do setor")
    localizacao: str | None = Field(None, max_length=200)
    funcoes: list[str] = Field(
        ...,
        min_length=1,
        description="Funcoes do setor",
    )
    numero_trabalhadores: int | None = Field(None, ge=0)
    avaliador: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Nome do avaliador",
    )
    cargo_avaliador: str | None = Field(None, max_length=100)
    riscos: list[OccupationalRiskRequest] = Field(
        default_factory=list,
        description="Riscos identificados",
    )
    medidas_controle: list[str] = Field(
        default_factory=list,
        description="Medidas de controle existentes",
    )
    data_proxima_revisao: date | None = None

    @field_validator("funcoes")
    @classmethod
    def validar_funcoes(cls, v):
        if len(v) > 50:
            raise ValueError("Maximo de 50 funcoes por setor")
        return v


class RiskMappingUpdateRequest(BaseModel):
    """Request para atualizacao de mapeamento."""

    descricao_setor: str | None = None
    localizacao: str | None = None
    funcoes: list[str] | None = None
    numero_trabalhadores: int | None = None
    nivel_risco_geral: str | None = None
    data_proxima_revisao: date | None = None
    ativo: bool | None = None


class OccupationalRiskResponse(BaseModel):
    """Response de risco ocupacional."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mapeamento_id: UUID
    categoria: str
    agente: str
    descricao: str | None = None
    fonte_geradora: str
    meio_propagacao: str | None = None
    funcoes_expostas: list[str]
    numero_expostos: int | None = None
    tempo_exposicao: str | None = None
    probabilidade: int | None = None
    severidade: int | None = None
    nivel_risco: str | None = None
    valor_medido: float | None = None
    unidade_medida: str | None = None
    limite_tolerancia: float | None = None
    medidas_existentes: list[str]
    epis_recomendados: list[str]
    exames_requeridos: list[str]
    prioridade: int
    created_at: datetime


class RiskMappingResponse(BaseModel):
    """Response de mapeamento de riscos."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    setor: str
    descricao_setor: str | None = None
    localizacao: str | None = None
    funcoes: list[str] = []
    numero_trabalhadores: int | None = None
    data_avaliacao: date | None = None
    avaliador: str | None = None
    cargo_avaliador: str | None = None
    nivel_risco_geral: str | None = None
    data_proxima_revisao: date | None = None
    ativo: bool = True
    versao: int = 1
    riscos: list[OccupationalRiskResponse] = []
    created_at: datetime
    updated_at: datetime | None = None


class RiskMappingListResponse(BaseModel):
    """Response de lista de mapeamentos."""

    items: list[RiskMappingResponse]
    total: int
    page: int = 1
    size: int = 20


class RiskMappingSummary(BaseModel):
    """Resumo de mapeamento para listagens."""

    id: UUID
    setor: str
    data_avaliacao: date
    nivel_risco_geral: str | None = None
    total_riscos: int
    total_funcoes: int
    ativo: bool


# ==============================================================================
# Control Measure Schemas
# ==============================================================================


class ControlMeasureRequest(BaseModel):
    """Request para medida de controle."""

    mapeamento_id: UUID = Field(..., description="ID do mapeamento")
    tipo: str = Field(
        ...,
        description="Tipo da medida",
        pattern=r"^(eliminacao|substituicao|controle_engenharia|sinalizacao|controle_administrativo|epi|epc)$",
    )
    descricao: str = Field(..., min_length=10, description="Descricao da medida")
    riscos_controlados: list[UUID] = Field(
        default_factory=list,
        description="IDs dos riscos controlados",
    )
    responsavel: str | None = Field(None, max_length=100)
    data_prevista: date | None = None
    custo_estimado: float | None = Field(None, ge=0)


class ControlMeasureUpdateRequest(BaseModel):
    """Request para atualizacao de medida de controle."""

    descricao: str | None = None
    status: str | None = Field(
        None,
        pattern=r"^(pendente|em_andamento|implementada|cancelada)$",
    )
    responsavel: str | None = None
    data_prevista: date | None = None
    data_implementacao: date | None = None
    eficaz: bool | None = None
    data_verificacao: date | None = None
    observacoes: str | None = None
    custo_estimado: float | None = None


class ControlMeasureResponse(BaseModel):
    """Response de medida de controle."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mapeamento_id: UUID
    tipo: str
    descricao: str
    riscos_controlados: list[UUID]
    status: str
    responsavel: str | None = None
    data_prevista: date | None = None
    data_implementacao: date | None = None
    eficaz: bool | None = None
    data_verificacao: date | None = None
    observacoes: str | None = None
    custo_estimado: float | None = None
    created_at: datetime
    updated_at: datetime | None = None


# ==============================================================================
# Risk Category Info
# ==============================================================================


class RiskCategoryInfo(BaseModel):
    """Informacoes de categoria de risco."""

    id: str
    nome: str
    exemplos: list[str]
    cor_mapa: str


class RiskCategoriesResponse(BaseModel):
    """Response com categorias de risco."""

    categorias: list[RiskCategoryInfo]
    niveis_risco: list[str]
