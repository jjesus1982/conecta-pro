"""
Schemas para NFS-e Padrao Nacional.

Pydantic models para validacao de entrada/saida da API.
Preparacao para migracao do padrao ABRASF para o Padrao Nacional de NFS-e.

Portal: https://www.gov.br/nfse
Documentacao: https://www.gov.br/nfse/pt-br/acesso-a-informacao/manuais
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AmbienteNacionalEnum(StrEnum):
    """Ambientes do Padrao Nacional."""

    PRODUCAO = "producao"
    HOMOLOGACAO = "homologacao"


class TipoTributacaoEnum(StrEnum):
    """Tipos de tributacao no Padrao Nacional."""

    TRIBUTACAO_MUNICIPIO = "1"
    TRIBUTACAO_FORA_MUNICIPIO = "2"
    ISENCAO = "3"
    IMUNE = "4"
    EXIGIBILIDADE_SUSPENSA_JUDICIAL = "5"
    EXIGIBILIDADE_SUSPENSA_ADM = "6"
    EXPORTACAO_SERVICO = "7"


class RegimeEspecialEnum(StrEnum):
    """Regimes especiais de tributacao."""

    SEM_REGIME = "0"
    MICROEMPRESA = "1"
    ESTIMATIVA = "2"
    SOCIEDADE_PROFISSIONAIS = "3"
    COOPERATIVA = "4"
    MEI = "5"
    ME_EPP_SIMPLES = "6"


class MotivoCancelamentoEnum(StrEnum):
    """Motivos de cancelamento no Padrao Nacional."""

    ERRO_EMISSAO = "1"
    SERVICO_NAO_PRESTADO = "2"
    ERRO_PREENCHIMENTO = "3"
    DUPLICIDADE = "4"


class DPSStatusEnum(StrEnum):
    """Status da DPS/NFS-e no Padrao Nacional."""

    PENDENTE = "pendente"
    PROCESSANDO = "processando"
    AUTORIZADA = "autorizada"
    CANCELADA = "cancelada"
    SUBSTITUIDA = "substituida"
    ERRO = "erro"
    PREPARACAO = "preparacao"  # Status especial para ambiente de preparacao


# ============== Schemas de Entrada ==============


class PrestadorNacionalRequest(BaseModel):
    """Dados do prestador no Padrao Nacional."""

    cnpj: str = Field(..., min_length=14, max_length=18, description="CNPJ do prestador (14 digitos)")
    inscricao_municipal: str = Field(..., min_length=1, max_length=15, description="Inscricao municipal do prestador")
    codigo_municipio: str = Field(
        default="1302603",  # Manaus
        min_length=7,
        max_length=7,
        description="Codigo IBGE do municipio (7 digitos)",
    )
    razao_social: str = Field(..., min_length=2, max_length=150, description="Razao social do prestador")
    nome_fantasia: str | None = Field(None, max_length=60, description="Nome fantasia do prestador")
    regime_especial: RegimeEspecialEnum = Field(
        default=RegimeEspecialEnum.ME_EPP_SIMPLES, description="Regime especial de tributacao"
    )
    optante_simples: bool = Field(default=True, description="Se e optante do Simples Nacional")

    @field_validator("cnpj")
    @classmethod
    def validar_cnpj(cls, v: str) -> str:
        """Remove formatacao e valida tamanho."""
        doc = v.replace(".", "").replace("-", "").replace("/", "")
        if len(doc) != 14:
            raise ValueError("CNPJ deve ter 14 digitos")
        return doc


class TomadorNacionalRequest(BaseModel):
    """Dados do tomador no Padrao Nacional."""

    cpf_cnpj: str = Field(
        ..., min_length=11, max_length=18, description="CPF (11 digitos) ou CNPJ (14 digitos) do tomador"
    )
    razao_social: str = Field(..., min_length=2, max_length=150, description="Nome ou razao social do tomador")
    logradouro: str = Field(..., min_length=1, max_length=125, description="Logradouro do endereco")
    numero: str = Field(default="S/N", max_length=10, description="Numero do endereco")
    complemento: str | None = Field(None, max_length=60, description="Complemento do endereco")
    bairro: str = Field(..., min_length=1, max_length=60, description="Bairro")
    codigo_municipio: str = Field(default="1302603", min_length=7, max_length=7, description="Codigo IBGE do municipio")
    uf: str = Field(default="AM", min_length=2, max_length=2, description="Estado (UF)")
    cep: str = Field(..., min_length=8, max_length=10, description="CEP (8 digitos)")
    email: str | None = Field(None, max_length=80, description="Email do tomador")
    telefone: str | None = Field(None, max_length=20, description="Telefone do tomador")
    inscricao_municipal: str | None = Field(
        None, max_length=15, description="Inscricao municipal do tomador (se houver)"
    )

    @field_validator("cpf_cnpj")
    @classmethod
    def validar_cpf_cnpj(cls, v: str) -> str:
        """Remove formatacao e valida tamanho."""
        doc = v.replace(".", "").replace("-", "").replace("/", "")
        if len(doc) not in [11, 14]:
            raise ValueError("CPF deve ter 11 digitos ou CNPJ 14 digitos")
        return doc

    @field_validator("cep")
    @classmethod
    def validar_cep(cls, v: str) -> str:
        """Remove formatacao do CEP."""
        cep = v.replace("-", "").replace(".", "")
        if len(cep) != 8:
            raise ValueError("CEP deve ter 8 digitos")
        return cep


class ServicoNacionalRequest(BaseModel):
    """Dados do servico no Padrao Nacional."""

    codigo_tributacao_nacional: str = Field(
        default="110201",
        description="Código de tributação nacional (cTribNac), 6 dígitos: Item+Subitem+Desdobro "
        "da LC 116/2003. 110201=vigilância, 071001=limpeza/portaria. NÃO é o código NBS.",
    )
    descricao: str = Field(..., min_length=10, max_length=2000, description="Descricao detalhada do servico prestado")
    valor_servico: Decimal = Field(..., gt=0, description="Valor total do servico")
    valor_deducao: Decimal = Field(default=Decimal("0"), ge=0, description="Valor de deducoes permitidas")
    valor_desconto_incondicionado: Decimal = Field(
        default=Decimal("0"), ge=0, description="Valor de desconto incondicionado"
    )
    valor_desconto_condicionado: Decimal = Field(
        default=Decimal("0"), ge=0, description="Valor de desconto condicionado"
    )
    codigo_cnae: str | None = Field(None, max_length=7, description="Codigo CNAE da atividade")
    aliquota_iss: Decimal = Field(default=Decimal("0.05"), ge=0, le=1, description="Aliquota do ISS (0.05 = 5%)")
    iss_retido: bool = Field(default=False, description="Se o ISS sera retido pelo tomador")


class EmitirDPSRequest(BaseModel):
    """Request para emissao de DPS (Declaracao de Prestacao de Servicos)."""

    empresa: str | None = Field(
        None,
        description="Qual CNPJ do grupo emite: 'conecta_eletronica' | 'conecta_patrimonial' "
        "(aceita 'eletronica'/'patrimonial' ou o CNPJ). Vazio = Eletrônica (legado). "
        "Define o certificado que assina — não só o CNPJ do XML.",
    )
    prestador: PrestadorNacionalRequest | None = Field(
        None, description="Dados do prestador (opcional, usa config padrao se nao informado)"
    )
    tomador: TomadorNacionalRequest
    servico: ServicoNacionalRequest
    competencia: str | None = Field(
        None, pattern=r"^\d{4}-\d{2}$", description="Competencia no formato YYYY-MM (default: mes atual)"
    )
    tipo_tributacao: TipoTributacaoEnum = Field(
        default=TipoTributacaoEnum.TRIBUTACAO_MUNICIPIO, description="Tipo de tributacao"
    )
    dry_run: bool = Field(default=False, description="Se True, gera e assina XML sem transmitir ao Portal Nacional")

    class Config:
        json_schema_extra = {
            "example": {
                "tomador": {
                    "cpf_cnpj": "12345678901234",
                    "razao_social": "Empresa Cliente LTDA",
                    "logradouro": "Av. Eduardo Ribeiro",
                    "numero": "1000",
                    "bairro": "Centro",
                    "codigo_municipio": "1302603",
                    "uf": "AM",
                    "cep": "69010001",
                    "email": "contato@empresa.com.br",
                },
                "servico": {
                    "codigo_tributacao_nacional": "110201",
                    "descricao": "Servicos de vigilancia patrimonial armada conforme contrato 001/2026",
                    "valor_servico": "15000.00",
                    "aliquota_iss": "0.05",
                    "iss_retido": False,
                },
                "competencia": "2026-01",
                "tipo_tributacao": "1",
            }
        }


class ConsultarDPSRequest(BaseModel):
    """Request para consulta de DPS por ID."""

    id_dps: str = Field(..., description="ID da DPS")


class ConsultarNFSeNacionalRequest(BaseModel):
    """Request para consulta de NFS-e por numero nacional."""

    numero_nfse: str = Field(..., description="Numero nacional da NFS-e")


class CancelarNFSeNacionalRequest(BaseModel):
    """Request para cancelamento de NFS-e no Padrao Nacional."""

    numero_nfse: str = Field(..., description="Numero nacional da NFS-e a cancelar")
    motivo_cancelamento: MotivoCancelamentoEnum = Field(
        default=MotivoCancelamentoEnum.ERRO_EMISSAO, description="Motivo do cancelamento"
    )
    justificativa: str | None = Field(None, max_length=255, description="Justificativa detalhada do cancelamento")

    class Config:
        json_schema_extra = {
            "example": {
                "numero_nfse": "NFSe-NAC-123456789",
                "motivo_cancelamento": "1",
                "justificativa": "Erro no valor do servico",
            }
        }


class SubstituirNFSeNacionalRequest(BaseModel):
    """Request para substituicao de NFS-e no Padrao Nacional."""

    numero_nfse_substituida: str = Field(..., description="Numero nacional da NFS-e a ser substituida")
    tomador: TomadorNacionalRequest
    servico: ServicoNacionalRequest

    class Config:
        json_schema_extra = {
            "example": {
                "numero_nfse_substituida": "NFSe-NAC-123456789",
                "tomador": {
                    "cpf_cnpj": "12345678901234",
                    "razao_social": "Empresa Cliente LTDA",
                    "logradouro": "Av. Eduardo Ribeiro",
                    "numero": "1000",
                    "bairro": "Centro",
                    "codigo_municipio": "1302603",
                    "uf": "AM",
                    "cep": "69010001",
                },
                "servico": {
                    "codigo_tributacao_nacional": "110201",
                    "descricao": "Servicos de vigilancia patrimonial - CORRECAO",
                    "valor_servico": "16000.00",
                    "aliquota_iss": "0.05",
                },
            }
        }


# ============== Schemas de Saida ==============


class DPSResponse(BaseModel):
    """Response padrao de DPS/NFS-e Nacional."""

    id_dps: str | None = Field(None, description="ID da DPS")
    numero_nfse: str | None = Field(None, description="Numero nacional da NFS-e")
    numero_dps: str | None = Field(None, description="Numero da DPS")
    chave_acesso: str | None = Field(None, description="Chave de acesso da NFS-e")
    status: DPSStatusEnum = Field(..., description="Status da operacao")
    mensagem: str | None = Field(None, description="Mensagem de retorno")
    data_emissao: datetime | None = Field(None, description="Data/hora da emissao")
    payload_json: dict[str, Any] | None = Field(None, description="Payload JSON enviado")


class EmitirDPSResponse(DPSResponse):
    """Response para emissao de DPS."""

    valor_servico: Decimal | None = Field(None, description="Valor do servico")
    valor_iss: Decimal | None = Field(None, description="Valor do ISS")
    valor_liquido: Decimal | None = Field(None, description="Valor liquido")
    tomador_cpf_cnpj: str | None = Field(None, description="CPF/CNPJ do tomador")
    previsao_migracao: str | None = Field(None, description="Previsao de migracao")

    class Config:
        json_schema_extra = {
            "example": {
                "id_dps": "DPS-2026-000001",
                "numero_dps": "000001",
                "status": "preparacao",
                "mensagem": "Padrao Nacional ainda nao disponivel. Payload preparado para migracao.",
                "data_emissao": "2026-01-16T10:30:00",
                "valor_servico": "15000.00",
                "valor_iss": "750.00",
                "valor_liquido": "14250.00",
                "tomador_cpf_cnpj": "12345678901234",
                "previsao_migracao": "2026",
            }
        }


class ConsultarNFSeNacionalResponse(BaseModel):
    """Response para consulta de NFS-e Nacional."""

    numero_nfse: str | None = None
    id_dps: str | None = None
    status: DPSStatusEnum
    data_emissao: datetime | None = None
    chave_acesso: str | None = None
    valor_servico: Decimal | None = None
    valor_iss: Decimal | None = None
    tomador: dict[str, Any] | None = None
    prestador: dict[str, Any] | None = None
    servico: dict[str, Any] | None = None
    mensagem: str | None = None


class CancelarNFSeNacionalResponse(BaseModel):
    """Response para cancelamento de NFS-e Nacional."""

    numero_nfse: str
    status: DPSStatusEnum
    data_cancelamento: datetime | None = None
    protocolo: str | None = None
    mensagem: str | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "numero_nfse": "NFSe-NAC-123456789",
                "status": "preparacao",
                "mensagem": "Cancelamento preparado para quando migracao estiver disponivel",
            }
        }


class StatusMigracaoResponse(BaseModel):
    """Response para status da migracao."""

    municipio: str
    codigo_ibge: str
    padrao_atual: str
    provedor_atual: str
    migracao_prevista: str
    status: str
    notas: list[str]
    links_uteis: dict[str, str]


class ComparacaoPadroesResponse(BaseModel):
    """Response para comparacao entre padroes."""

    abrasf_204: dict[str, Any]
    padrao_nacional: dict[str, Any]
    recomendacao: str


class MapeamentoServicoResponse(BaseModel):
    """Response para mapeamento de servicos ABRASF -> NBS."""

    codigo_abrasf: str
    codigo_nbs: str
    descricao: str


class StatusConexaoNacionalResponse(BaseModel):
    """Response para validacao de conexao com Padrao Nacional."""

    ambiente: str
    cnpj: str
    url_base: str
    status_api: str
    certificado_configurado: bool
    certificado_valido: bool | None = None
    certificado_expira: str | None = None
    migracao_disponivel: bool
    mensagem: str | None = None


class EventoNFSeResponse(BaseModel):
    """Response para eventos de NFS-e."""

    numero_nfse: str
    tipo_evento: str
    data_evento: datetime
    descricao: str
    protocolo: str | None = None
