"""
Schemas para Simples Nacional.

Pydantic models para validação de entrada/saída da API.
"""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class AnexoSimplesEnum(StrEnum):
    """Anexos do Simples Nacional."""

    ANEXO_I = "I"
    ANEXO_II = "II"
    ANEXO_III = "III"
    ANEXO_IV = "IV"
    ANEXO_V = "V"


class TipoReceitaEnum(StrEnum):
    """Tipo de receita."""

    REVENDA_MERCADORIAS = "revenda"
    VENDA_PRODUCAO = "producao"
    SERVICOS = "servicos"
    LOCACAO_BENS = "locacao"


class SituacaoOpcaoEnum(StrEnum):
    """Situação da opção pelo Simples."""

    OPTANTE = "optante"
    NAO_OPTANTE = "nao_optante"
    EXCLUIDO = "excluido"
    IMPEDIDO = "impedido"


# ============== Schemas de Entrada ==============


class SimularCalculoRequest(BaseModel):
    """Request para simular cálculo."""

    receita_mensal: Decimal = Field(..., gt=0, description="Receita do mês")
    rbt12: Decimal = Field(..., gt=0, description="Receita Bruta dos últimos 12 meses")
    folha_12_meses: Decimal | None = Field(None, ge=0, description="Folha de salários 12 meses (para Fator R)")

    class Config:
        json_schema_extra = {
            "example": {"receita_mensal": "50000.00", "rbt12": "600000.00", "folha_12_meses": "180000.00"}
        }


class ReceitaRequest(BaseModel):
    """Dados de receita."""

    valor_bruto: Decimal = Field(..., gt=0, description="Valor bruto da receita")
    tipo_receita: TipoReceitaEnum = Field(default=TipoReceitaEnum.SERVICOS, description="Tipo de receita")
    anexo: AnexoSimplesEnum = Field(default=AnexoSimplesEnum.ANEXO_III, description="Anexo aplicável")
    deducoes: Decimal = Field(default=Decimal("0"), ge=0, description="Deduções permitidas")

    class Config:
        json_schema_extra = {
            "example": {"valor_bruto": "50000.00", "tipo_receita": "servicos", "anexo": "III", "deducoes": "0"}
        }


class CalcularPGDASDRequest(BaseModel):
    """Request para calcular PGDAS-D."""

    competencia: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="Competência (YYYY-MM)")
    receitas: list[ReceitaRequest] = Field(..., min_length=1, description="Lista de receitas do mês")
    rbt12: Decimal = Field(..., gt=0, description="Receita Bruta 12 meses")
    folha_12_meses: Decimal | None = Field(None, ge=0, description="Folha de salários 12 meses")

    class Config:
        json_schema_extra = {
            "example": {
                "competencia": "2026-01",
                "receitas": [{"valor_bruto": "50000.00", "tipo_receita": "servicos", "anexo": "III"}],
                "rbt12": "600000.00",
                "folha_12_meses": "180000.00",
            }
        }


class GerarDASRequest(BaseModel):
    """Request para gerar DAS."""

    competencia: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="Competência (YYYY-MM)")
    receitas: list[ReceitaRequest] = Field(..., min_length=1, description="Lista de receitas")
    rbt12: Decimal = Field(..., gt=0, description="Receita Bruta 12 meses")
    folha_12_meses: Decimal | None = Field(None, ge=0, description="Folha de salários 12 meses")
    data_vencimento: str | None = Field(
        None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Data de vencimento (YYYY-MM-DD)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "competencia": "2026-01",
                "receitas": [{"valor_bruto": "50000.00", "tipo_receita": "servicos"}],
                "rbt12": "600000.00",
                "data_vencimento": "2026-02-20",
            }
        }


class CalcularFatorRRequest(BaseModel):
    """Request para calcular Fator R."""

    folha_12_meses: Decimal = Field(..., ge=0, description="Folha de salários 12 meses")
    rbt12: Decimal = Field(..., gt=0, description="Receita Bruta 12 meses")

    class Config:
        json_schema_extra = {"example": {"folha_12_meses": "180000.00", "rbt12": "600000.00"}}


# ============== Schemas de Resposta ==============


class ComposicaoTributosResponse(BaseModel):
    """Composição dos tributos no DAS."""

    irpj: str
    csll: str
    cofins: str
    pis: str
    cpp: str
    icms: str
    iss: str


class SimulacaoResponse(BaseModel):
    """Response da simulação."""

    receita_mensal: str
    rbt12: str
    fator_r: str | None = None
    anexo: str
    faixa: int
    aliquota_nominal: str
    valor_deduzir: str
    aliquota_efetiva: str
    valor_devido: str
    composicao: ComposicaoTributosResponse


class ReceitaResponse(BaseModel):
    """Receita processada."""

    tipo: str
    anexo: str
    valor_bruto: str
    deducoes: str
    valor_liquido: str


class PGDASDResponse(BaseModel):
    """Response do PGDAS-D."""

    competencia: str
    cnpj: str
    razao_social: str
    data_apuracao: str
    rbt12: str
    receita_mes: str
    aliquota_efetiva: str
    aliquota_percentual: str
    valor_devido: str
    receitas: list[ReceitaResponse]
    transmitida: bool
    numero_recibo: str | None = None


class DASResponse(BaseModel):
    """Response do DAS."""

    numero_documento: str
    competencia: str
    data_vencimento: str
    valor_principal: str
    valor_multa: str
    valor_juros: str
    valor_total: str
    codigo_barras: str | None = None
    linha_digitavel: str | None = None
    composicao: ComposicaoTributosResponse
    situacao: str


class DASGeradoResponse(BaseModel):
    """Response da geração de DAS."""

    pgdasd: PGDASDResponse
    das: DASResponse


class FatorRResponse(BaseModel):
    """Response do cálculo do Fator R."""

    folha_12_meses: str
    rbt12: str
    fator_r: str
    fator_r_percentual: str
    anexo_aplicavel: str
    observacao: str


class FaixaAliquotaResponse(BaseModel):
    """Faixa de alíquota."""

    faixa: int
    receita_inicio: str
    receita_fim: str
    aliquota_nominal: str
    valor_deduzir: str


class TabelaAliquotasResponse(BaseModel):
    """Tabela de alíquotas."""

    anexo: str
    descricao: str
    faixas: list[FaixaAliquotaResponse]


class AnexoResponse(BaseModel):
    """Anexo do Simples."""

    codigo: str
    descricao: str


class AnexosResponse(BaseModel):
    """Lista de anexos."""

    anexos: list[AnexoResponse]
    anexo_atual: str


class TipoReceitaResponse(BaseModel):
    """Tipo de receita."""

    codigo: str
    descricao: str


class TiposReceitaResponse(BaseModel):
    """Lista de tipos de receita."""

    tipos: list[TipoReceitaResponse]


class OpcaoSimplesResponse(BaseModel):
    """Situação da opção pelo Simples."""

    cnpj: str
    razao_social: str
    situacao: str
    data_opcao: str | None = None
    enquadramento: str
    simei: bool


class StatusSimplesResponse(BaseModel):
    """Status do Simples Nacional."""

    cnpj: str
    razao_social: str
    anexo_principal: str
    anexo_descricao: str
    portal_simples: str
    limite_receita_anual: float
    limite_receita_anual_formatado: str | None = None
    operacoes_disponiveis: list[str]
