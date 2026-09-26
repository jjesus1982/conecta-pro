"""
Schemas para SPED Fiscal (EFD ICMS/IPI).

Pydantic models para validação de entrada/saída da API.
"""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class FinalidadeArquivoEnum(StrEnum):
    """Finalidade do arquivo SPED."""

    ORIGINAL = "0"
    SUBSTITUTO = "1"


class PerfilArquivoEnum(StrEnum):
    """Perfil de apresentação."""

    PERFIL_A = "A"
    PERFIL_B = "B"
    PERFIL_C = "C"


class TipoItemEnum(StrEnum):
    """Tipo de item."""

    MERCADORIA_REVENDA = "00"
    MATERIA_PRIMA = "01"
    EMBALAGEM = "02"
    PRODUTO_PROCESSO = "03"
    PRODUTO_ACABADO = "04"
    SUBPRODUTO = "05"
    PRODUTO_INTERMEDIARIO = "06"
    MATERIAL_USO_CONSUMO = "07"
    ATIVO_IMOBILIZADO = "08"
    SERVICOS = "09"
    OUTROS = "10"


# ============== Schemas de Entrada ==============


class ParticipanteRequest(BaseModel):
    """Dados do participante."""

    codigo: str = Field(..., max_length=60)
    nome: str = Field(..., max_length=100)
    cnpj_cpf: str = Field(..., min_length=11, max_length=14)
    inscricao_estadual: str | None = Field(None, max_length=14)
    codigo_municipio: str | None = Field(None, max_length=7)
    uf: str | None = Field(None, max_length=2)
    endereco: str | None = Field(None, max_length=60)
    cep: str | None = Field(None, max_length=8)

    class Config:
        json_schema_extra = {
            "example": {
                "codigo": "FORN001",
                "nome": "Fornecedor Exemplo Ltda",
                "cnpj_cpf": "12345678000190",
                "inscricao_estadual": "123456789",
                "uf": "SP",
            }
        }


class ProdutoRequest(BaseModel):
    """Dados do produto."""

    codigo: str = Field(..., max_length=60)
    descricao: str = Field(..., max_length=200)
    codigo_barras: str | None = Field(None, max_length=14)
    unidade: str = Field(default="UN", max_length=6)
    tipo_item: TipoItemEnum = Field(default=TipoItemEnum.MERCADORIA_REVENDA)
    ncm: str | None = Field(None, max_length=8)
    cest: str | None = Field(None, max_length=7)
    aliquota_icms: Decimal = Field(default=Decimal("0"), ge=0)

    class Config:
        json_schema_extra = {
            "example": {
                "codigo": "PROD001",
                "descricao": "Produto Exemplo",
                "ncm": "84713012",
                "unidade": "UN",
                "tipo_item": "00",
            }
        }


class ItemDocumentoRequest(BaseModel):
    """Item do documento fiscal."""

    codigo_produto: str = Field(..., max_length=60)
    quantidade: Decimal = Field(..., gt=0)
    valor_unitario: Decimal = Field(..., gt=0)
    valor_total: Decimal = Field(..., gt=0)
    cfop: str = Field(..., min_length=4, max_length=4)
    cst_icms: str = Field(default="00", max_length=3)
    valor_icms: Decimal = Field(default=Decimal("0"), ge=0)


class DocumentoFiscalRequest(BaseModel):
    """Dados do documento fiscal."""

    tipo: str = Field(..., description="55=NF-e, 57=CT-e, 65=NFC-e")
    chave: str = Field(..., min_length=44, max_length=44)
    numero: str = Field(..., max_length=9)
    serie: str = Field(..., max_length=3)
    data_emissao: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    data_entrada_saida: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    codigo_participante: str = Field(..., max_length=60)
    valor_total: Decimal = Field(..., gt=0)
    valor_icms: Decimal = Field(default=Decimal("0"), ge=0)
    valor_ipi: Decimal = Field(default=Decimal("0"), ge=0)
    valor_pis: Decimal = Field(default=Decimal("0"), ge=0)
    valor_cofins: Decimal = Field(default=Decimal("0"), ge=0)
    cfop: str = Field(..., min_length=4, max_length=4)
    itens: list[ItemDocumentoRequest] | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "tipo": "55",
                "chave": "35260100000000000000550010000000011000000011",
                "numero": "1",
                "serie": "1",
                "data_emissao": "2026-01-15",
                "data_entrada_saida": "2026-01-15",
                "codigo_participante": "FORN001",
                "valor_total": "10000.00",
                "valor_icms": "1800.00",
                "cfop": "1102",
            }
        }


class InventarioRequest(BaseModel):
    """Item do inventário."""

    codigo_item: str = Field(..., max_length=60)
    descricao: str = Field(..., max_length=200)
    unidade: str = Field(default="UN", max_length=6)
    quantidade: Decimal = Field(..., gt=0)
    valor_unitario: Decimal = Field(..., gt=0)
    valor_total: Decimal = Field(..., gt=0)
    propriedade: str = Field(default="0", description="0=próprio, 1=terceiros")
    conta_contabil: str | None = Field(None, max_length=60)

    class Config:
        json_schema_extra = {
            "example": {
                "codigo_item": "PROD001",
                "descricao": "Produto Exemplo",
                "unidade": "UN",
                "quantidade": "100",
                "valor_unitario": "50.00",
                "valor_total": "5000.00",
            }
        }


class GerarArquivoRequest(BaseModel):
    """Request para gerar arquivo SPED."""

    periodo_inicio: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    periodo_fim: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    finalidade: FinalidadeArquivoEnum = Field(default=FinalidadeArquivoEnum.ORIGINAL)
    #: Slug da empresa em `empresas`. A EFD ICMS/IPI é POR estabelecimento, e só a
    #: Eletrônica tem inscrição estadual. None = empresa principal.
    empresa_slug: str | None = Field(default=None, max_length=60)
    participantes: list[ParticipanteRequest] | None = None
    produtos: list[ProdutoRequest] | None = None
    documentos: list[DocumentoFiscalRequest] | None = None
    inventario: list[InventarioRequest] | None = None

    class Config:
        json_schema_extra = {
            "example": {"periodo_inicio": "2026-01-01", "periodo_fim": "2026-01-31", "finalidade": "0"}
        }


class CalcularApuracaoRequest(BaseModel):
    """Request para calcular apuração."""

    periodo: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    documentos: list[DocumentoFiscalRequest] = Field(..., min_length=1)

    class Config:
        json_schema_extra = {"example": {"periodo": "2026-01", "documentos": []}}


class AdicionarParticipanteRequest(BaseModel):
    """Request para adicionar participante."""

    participante: ParticipanteRequest


class AdicionarProdutoRequest(BaseModel):
    """Request para adicionar produto."""

    produto: ProdutoRequest


class AdicionarDocumentoRequest(BaseModel):
    """Request para adicionar documento."""

    documento: DocumentoFiscalRequest


class AdicionarInventarioRequest(BaseModel):
    """Request para adicionar inventário."""

    item: InventarioRequest


# ============== Schemas de Resposta ==============


class ApuracaoICMSResponse(BaseModel):
    """Apuração de ICMS."""

    periodo: str
    valor_debitos: str
    valor_creditos: str
    valor_estorno_debitos: str
    valor_estorno_creditos: str
    valor_saldo_credor_anterior: str
    valor_ajustes_debito: str
    valor_ajustes_credito: str
    saldo_apurado: str
    saldo_devedor: str
    saldo_credor: str


class ArquivoSPEDResponse(BaseModel):
    """Response do arquivo gerado."""

    periodo_inicio: str
    periodo_fim: str
    total_registros: int
    total_participantes: int
    total_produtos: int
    total_documentos: int
    total_inventario: int
    hash_md5: str
    conteudo: str


class ValidacaoArquivoResponse(BaseModel):
    """Response da validação."""

    valido: bool
    erros: list[str]
    avisos: list[str]
    total_registros: int
    hash: str


class ParticipanteResponse(BaseModel):
    """Participante cadastrado."""

    codigo: str
    nome: str
    cnpj_cpf: str
    tipo_pessoa: str


class ProdutoResponse(BaseModel):
    """Produto cadastrado."""

    codigo: str
    descricao: str
    ncm: str | None
    unidade: str


class DocumentoResponse(BaseModel):
    """Documento cadastrado."""

    tipo: str
    chave: str
    numero: str
    valor_total: str


class BlocoResponse(BaseModel):
    """Bloco do SPED."""

    codigo: str
    descricao: str


class BlocosResponse(BaseModel):
    """Lista de blocos."""

    blocos: list[BlocoResponse]


class StatusSPEDFiscalResponse(BaseModel):
    """Status do SPED Fiscal."""

    cnpj: str
    razao_social: str
    inscricao_estadual: str
    uf: str
    perfil: str
    versao_leiaute: str
    operacoes_disponiveis: list[str]
