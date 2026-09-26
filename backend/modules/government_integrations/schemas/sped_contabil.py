"""
Schemas para SPED Contábil (ECD).

Pydantic models para validação de entrada/saída da API.
"""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class TipoECDEnum(StrEnum):
    """Tipo de ECD."""

    LIVRO_DIARIO_GERAL = "G"
    LIVRO_DIARIO_RESUMIDO = "R"
    LIVRO_DIARIO_AUXILIAR = "A"
    LIVRO_RAZAO_AUXILIAR = "Z"
    LIVRO_BALANCETES = "B"


class NaturezaContaEnum(StrEnum):
    """Natureza da conta contábil."""

    ATIVO = "01"
    PASSIVO = "02"
    PATRIMONIO_LIQUIDO = "03"
    RESULTADO_CREDORA = "04"
    RESULTADO_DEVEDORA = "05"


class TipoContaEnum(StrEnum):
    """Tipo de conta."""

    SINTETICA = "S"
    ANALITICA = "A"


class IndicadorDCEnum(StrEnum):
    """Indicador débito/crédito."""

    DEBITO = "D"
    CREDITO = "C"


# ============== Schemas de Entrada ==============


class ContaContabilRequest(BaseModel):
    """Dados da conta contábil."""

    codigo: str = Field(..., max_length=60)
    descricao: str = Field(..., max_length=200)
    tipo: TipoContaEnum = Field(default=TipoContaEnum.ANALITICA)
    nivel: int = Field(..., ge=1, le=10)
    natureza: NaturezaContaEnum = Field(...)
    codigo_pai: str | None = Field(None, max_length=60)
    codigo_referencial: str | None = Field(None, max_length=60)
    saldo_inicial_debito: Decimal = Field(default=Decimal("0"), ge=0)
    saldo_inicial_credito: Decimal = Field(default=Decimal("0"), ge=0)

    class Config:
        json_schema_extra = {
            "example": {
                "codigo": "1.1.01",
                "descricao": "Caixa e Equivalentes de Caixa",
                "tipo": "A",
                "nivel": 3,
                "natureza": "01",
            }
        }


class LancamentoContabilRequest(BaseModel):
    """Dados do lançamento contábil."""

    numero: int = Field(..., gt=0)
    data: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    conta_debito: str = Field(..., max_length=60)
    conta_credito: str = Field(..., max_length=60)
    valor: Decimal = Field(..., gt=0)
    historico: str = Field(..., min_length=1, max_length=200)
    documento: str | None = Field(None, max_length=60)
    participante: str | None = Field(None, max_length=60)

    class Config:
        json_schema_extra = {
            "example": {
                "numero": 1,
                "data": "2026-01-15",
                "conta_debito": "1.1.01",
                "conta_credito": "3.1.01",
                "valor": "10000.00",
                "historico": "Receita de serviços prestados",
            }
        }


class BalancoPatrimonialRequest(BaseModel):
    """Dados do balanço patrimonial."""

    data_referencia: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    ativo_circulante: Decimal = Field(default=Decimal("0"), ge=0)
    ativo_nao_circulante: Decimal = Field(default=Decimal("0"), ge=0)
    passivo_circulante: Decimal = Field(default=Decimal("0"), ge=0)
    passivo_nao_circulante: Decimal = Field(default=Decimal("0"), ge=0)
    patrimonio_liquido: Decimal = Field(default=Decimal("0"))

    class Config:
        json_schema_extra = {
            "example": {
                "data_referencia": "2026-12-31",
                "ativo_circulante": "500000.00",
                "ativo_nao_circulante": "300000.00",
                "passivo_circulante": "200000.00",
                "passivo_nao_circulante": "100000.00",
                "patrimonio_liquido": "500000.00",
            }
        }


class DRERequest(BaseModel):
    """Dados da DRE."""

    periodo_inicio: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    periodo_fim: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    receita_bruta: Decimal = Field(default=Decimal("0"), ge=0)
    deducoes_receita: Decimal = Field(default=Decimal("0"), ge=0)
    custos: Decimal = Field(default=Decimal("0"), ge=0)
    despesas_operacionais: Decimal = Field(default=Decimal("0"), ge=0)
    resultado_financeiro: Decimal = Field(default=Decimal("0"))
    outras_receitas_despesas: Decimal = Field(default=Decimal("0"))
    irpj_csll: Decimal = Field(default=Decimal("0"), ge=0)

    class Config:
        json_schema_extra = {
            "example": {
                "periodo_inicio": "2026-01-01",
                "periodo_fim": "2026-12-31",
                "receita_bruta": "1200000.00",
                "deducoes_receita": "120000.00",
                "custos": "600000.00",
                "despesas_operacionais": "200000.00",
            }
        }


class GerarArquivoRequest(BaseModel):
    """Request para gerar arquivo SPED Contábil."""

    ano_referencia: int = Field(..., ge=2000, le=2100)
    periodo_inicio: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    periodo_fim: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    numero_ordem: str = Field(default="00001", max_length=10)
    #: Slug da empresa em `empresas`. A ECD é POR CNPJ — um arquivo que misturasse as duas
    #: empresas não serve para nenhuma. None = empresa principal (Eletrônica, Lucro Real).
    empresa_slug: str | None = Field(default=None, max_length=60)
    contas: list[ContaContabilRequest] | None = None
    lancamentos: list[LancamentoContabilRequest] | None = None
    balanco: BalancoPatrimonialRequest | None = None
    dre: DRERequest | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "ano_referencia": 2026,
                "periodo_inicio": "2026-01-01",
                "periodo_fim": "2026-12-31",
                "numero_ordem": "00001",
            }
        }


class CalcularSaldosRequest(BaseModel):
    """Request para calcular saldos."""

    periodo_inicio: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    periodo_fim: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")

    class Config:
        json_schema_extra = {"example": {"periodo_inicio": "2026-01-01", "periodo_fim": "2026-12-31"}}


class AdicionarContaRequest(BaseModel):
    """Request para adicionar conta."""

    conta: ContaContabilRequest


class AdicionarLancamentoRequest(BaseModel):
    """Request para adicionar lançamento."""

    lancamento: LancamentoContabilRequest


class DefinirBalancoRequest(BaseModel):
    """Request para definir balanço."""

    balanco: BalancoPatrimonialRequest


class DefinirDRERequest(BaseModel):
    """Request para definir DRE."""

    dre: DRERequest


# ============== Schemas de Resposta ==============


class ContaContabilResponse(BaseModel):
    """Conta contábil."""

    codigo: str
    descricao: str
    tipo: str
    nivel: int
    natureza: str


class LancamentoResponse(BaseModel):
    """Lançamento contábil."""

    numero: int
    data: str
    conta_debito: str
    conta_credito: str
    valor: str
    historico: str


class SaldoPeriodicoResponse(BaseModel):
    """Saldo periódico."""

    codigo_conta: str
    periodo_inicio: str
    periodo_fim: str
    saldo_inicial_debito: str
    saldo_inicial_credito: str
    valor_debitos: str
    valor_creditos: str
    saldo_final_debito: str
    saldo_final_credito: str


class BalancoResponse(BaseModel):
    """Balanço patrimonial."""

    data_referencia: str
    ativo_circulante: str
    ativo_nao_circulante: str
    total_ativo: str
    passivo_circulante: str
    passivo_nao_circulante: str
    patrimonio_liquido: str
    total_passivo_pl: str


class DREResponse(BaseModel):
    """DRE."""

    periodo_inicio: str
    periodo_fim: str
    receita_bruta: str
    deducoes_receita: str
    receita_liquida: str
    custos: str
    lucro_bruto: str
    despesas_operacionais: str
    lucro_operacional: str
    resultado_financeiro: str
    outras_receitas_despesas: str
    lucro_antes_ir: str
    irpj_csll: str
    lucro_liquido: str


class ArquivoSPEDContabilResponse(BaseModel):
    """Response do arquivo gerado."""

    ano_referencia: int
    periodo_inicio: str
    periodo_fim: str
    total_registros: int
    total_contas: int
    total_lancamentos: int
    hash_md5: str
    conteudo: str


class ValidacaoArquivoResponse(BaseModel):
    """Response da validação."""

    valido: bool
    erros: list[str]
    avisos: list[str]
    total_registros: int
    hash: str


class BlocoContabilResponse(BaseModel):
    """Bloco do SPED Contábil."""

    codigo: str
    descricao: str


class BlocosContabilResponse(BaseModel):
    """Lista de blocos."""

    blocos: list[BlocoContabilResponse]


class TipoECDResponse(BaseModel):
    """Tipo de ECD."""

    codigo: str
    descricao: str


class TiposECDResponse(BaseModel):
    """Lista de tipos."""

    tipos: list[TipoECDResponse]


class StatusSPEDContabilResponse(BaseModel):
    """Status do SPED Contábil."""

    cnpj: str
    razao_social: str
    tipo_ecd: str
    versao_leiaute: str
    operacoes_disponiveis: list[str]
