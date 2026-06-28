"""Schemas Pydantic para modulo Fiscal - NF-e, NFS-e, SPED, Retencoes."""
# pylint: disable=too-few-public-methods,missing-class-docstring

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

# ============================================================
# Enums para Schemas
# ============================================================


class TaxRegimeEnum(StrEnum):
    """Regime tributario."""

    SIMPLES_NACIONAL = "simples_nacional"
    LUCRO_PRESUMIDO = "lucro_presumido"
    LUCRO_REAL = "lucro_real"
    MEI = "mei"
    ISENTO = "isento"


class NFeTipoEnum(StrEnum):
    """Tipo de NF-e."""

    ENTRADA = "entrada"
    SAIDA = "saida"


class NFeStatusEnum(StrEnum):
    """Status da NF-e."""

    RASCUNHO = "rascunho"
    VALIDANDO = "validando"
    ASSINADA = "assinada"
    ENVIADA = "enviada"
    AUTORIZADA = "autorizada"
    DENEGADA = "denegada"
    REJEITADA = "rejeitada"
    CANCELADA = "cancelada"
    INUTILIZADA = "inutilizada"


class NFSeStatusEnum(StrEnum):
    """Status da NFS-e."""

    RASCUNHO = "rascunho"
    VALIDANDO = "validando"
    ENVIANDO = "enviando"
    PROCESSANDO = "processando"
    AUTORIZADA = "autorizada"
    REJEITADA = "rejeitada"
    CANCELADA = "cancelada"
    SUBSTITUIDA = "substituida"


class SPEDTipoEnum(StrEnum):
    """Tipo de arquivo SPED."""

    EFD_ICMS_IPI = "efd_icms_ipi"
    EFD_CONTRIBUICOES = "efd_contribuicoes"
    ECD = "ecd"
    ECF = "ecf"
    REINF = "reinf"
    ESOCIAL = "esocial"


class SPEDStatusEnum(StrEnum):
    """Status do arquivo SPED."""

    GERANDO = "gerando"
    GERADO = "gerado"
    VALIDANDO = "validando"
    VALIDADO = "validado"
    ERRO_VALIDACAO = "erro_validacao"
    ASSINANDO = "assinando"
    ASSINADO = "assinado"
    TRANSMITINDO = "transmitindo"
    TRANSMITIDO = "transmitido"
    ERRO_TRANSMISSAO = "erro_transmissao"
    ACEITO = "aceito"
    RECUSADO = "recusado"


class ObrigacaoStatusEnum(StrEnum):
    """Status de obrigacao fiscal."""

    PENDENTE = "pendente"
    EM_ANDAMENTO = "em_andamento"
    CONCLUIDA = "concluida"
    ATRASADA = "atrasada"
    CANCELADA = "cancelada"


# ============================================================
# CFOP Schemas
# ============================================================


class CFOPBase(BaseModel):
    """Base para CFOP."""

    codigo: str = Field(..., min_length=4, max_length=4, description="Codigo CFOP")
    descricao: str = Field(..., min_length=5, max_length=500)
    descricao_resumida: str | None = Field(None, max_length=100)
    tipo: str = Field(..., description="entrada ou saida")
    grupo: str = Field(..., min_length=1, max_length=1, description="1,2,3,5,6,7")
    natureza: str | None = Field(None, max_length=30)

    # Tributacao
    gera_credito_icms: bool = False
    gera_debito_icms: bool = False
    gera_credito_ipi: bool = False
    gera_debito_ipi: bool = False
    gera_pis_cofins: bool = True

    # Movimentacao
    movimenta_estoque: bool = True
    movimenta_financeiro: bool = True
    movimenta_contabilidade: bool = True

    # Zona Franca
    zfm_aplicavel: bool = False
    zfm_isenta_icms: bool = False
    zfm_isenta_ipi: bool = False
    zfm_suspende_pis_cofins: bool = False

    # CFOP correspondente
    cfop_correspondente: str | None = Field(None, max_length=4)

    # Contas contabeis
    conta_contabil_debito: str | None = Field(None, max_length=20)
    conta_contabil_credito: str | None = Field(None, max_length=20)


class CFOPCreate(CFOPBase):
    """Schema para criar CFOP."""


class CFOPUpdate(BaseModel):
    """Schema para atualizar CFOP."""

    descricao: str | None = Field(None, max_length=500)
    descricao_resumida: str | None = Field(None, max_length=100)
    natureza: str | None = Field(None, max_length=30)
    gera_credito_icms: bool | None = None
    gera_debito_icms: bool | None = None
    gera_credito_ipi: bool | None = None
    gera_debito_ipi: bool | None = None
    gera_pis_cofins: bool | None = None
    movimenta_estoque: bool | None = None
    movimenta_financeiro: bool | None = None
    movimenta_contabilidade: bool | None = None
    zfm_aplicavel: bool | None = None
    zfm_isenta_icms: bool | None = None
    zfm_isenta_ipi: bool | None = None
    zfm_suspende_pis_cofins: bool | None = None
    cfop_correspondente: str | None = Field(None, max_length=4)
    conta_contabil_debito: str | None = Field(None, max_length=20)
    conta_contabil_credito: str | None = Field(None, max_length=20)
    active: bool | None = None


class CFOPResponse(CFOPBase):
    """Response de CFOP."""

    id: UUID
    created_at: datetime
    updated_at: datetime | None
    active: bool
    is_entrada: bool
    is_saida: bool
    is_interestadual: bool
    is_exterior: bool

    class Config:
        from_attributes = True


class CFOPListResponse(BaseModel):
    """Lista de CFOPs."""

    items: list[CFOPResponse]
    total: int
    page: int
    page_size: int


class CFOPFilter(BaseModel):
    """Filtro para busca de CFOPs."""

    tipo: str | None = None
    grupo: str | None = None
    natureza: str | None = None
    zfm_aplicavel: bool | None = None
    movimenta_estoque: bool | None = None
    active: bool | None = True
    search: str | None = None


# ============================================================
# NCM Schemas
# ============================================================


class NCMBase(BaseModel):
    """Base para NCM."""

    codigo: str = Field(..., min_length=8, max_length=8, description="Codigo NCM")
    descricao: str = Field(..., min_length=5, max_length=2000)
    descricao_resumida: str | None = Field(None, max_length=200)

    # Classificacao
    capitulo: str | None = Field(None, max_length=2)
    posicao: str | None = Field(None, max_length=4)
    subposicao: str | None = Field(None, max_length=6)

    # IPI
    ipi_aliquota: Decimal | None = Field(None, ge=0, le=100)
    ipi_codigo_enquadramento: str | None = Field(None, max_length=5)
    ipi_unidade_tributavel: str | None = Field(None, max_length=6)

    # PIS/COFINS
    pis_aliquota: Decimal | None = Field(Decimal("1.65"), ge=0, le=100)
    cofins_aliquota: Decimal | None = Field(Decimal("7.6"), ge=0, le=100)
    pis_cofins_cst_entrada: str | None = Field("50", max_length=2)
    pis_cofins_cst_saida: str | None = Field("01", max_length=2)

    # ICMS
    icms_cest: str | None = Field(None, max_length=7)
    icms_st_mva: Decimal | None = Field(None, ge=0, le=500)

    # II
    ii_aliquota: Decimal | None = Field(None, ge=0, le=100)

    # Tributacao Monofasica
    tributacao_monofasica: bool = False
    aliquota_monofasica: Decimal | None = Field(None, ge=0, le=100)

    # Zona Franca
    zfm_isento_ipi: bool = False
    zfm_reduz_ii: bool = False
    zfm_percentual_reducao_ii: Decimal | None = Field(None, ge=0, le=100)

    # TIPI
    tipi_unidade: str | None = Field(None, max_length=10)
    tipi_nota: str | None = Field(None, max_length=500)

    # Vigencia
    valid_from: date | None = None
    valid_until: date | None = None


class NCMCreate(NCMBase):
    """Schema para criar NCM."""

    @field_validator("capitulo")
    @classmethod
    def extract_capitulo(cls, v: Any, info) -> Any:
        """Extrai capitulo do codigo NCM."""
        values = info.data
        if not v and "codigo" in values:
            return values["codigo"][:2]
        return v

    @field_validator("posicao")
    @classmethod
    def extract_posicao(cls, v: Any, info) -> Any:
        """Extrai posicao do codigo NCM."""
        values = info.data
        if not v and "codigo" in values:
            return values["codigo"][:4]
        return v

    @field_validator("subposicao")
    @classmethod
    def extract_subposicao(cls, v: Any, info) -> Any:
        """Extrai subposicao do codigo NCM."""
        values = info.data
        if not v and "codigo" in values:
            return values["codigo"][:6]
        return v


class NCMUpdate(BaseModel):
    """Schema para atualizar NCM."""

    descricao: str | None = Field(None, max_length=2000)
    descricao_resumida: str | None = Field(None, max_length=200)
    ipi_aliquota: Decimal | None = None
    ipi_codigo_enquadramento: str | None = None
    pis_aliquota: Decimal | None = None
    cofins_aliquota: Decimal | None = None
    icms_cest: str | None = None
    icms_st_mva: Decimal | None = None
    ii_aliquota: Decimal | None = None
    tributacao_monofasica: bool | None = None
    aliquota_monofasica: Decimal | None = None
    zfm_isento_ipi: bool | None = None
    zfm_reduz_ii: bool | None = None
    zfm_percentual_reducao_ii: Decimal | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    active: bool | None = None


class NCMResponse(NCMBase):
    """Response de NCM."""

    id: UUID
    created_at: datetime
    updated_at: datetime | None
    active: bool
    is_vigente: bool

    class Config:
        from_attributes = True


class NCMListResponse(BaseModel):
    """Lista de NCMs."""

    items: list[NCMResponse]
    total: int
    page: int
    page_size: int


class NCMFilter(BaseModel):
    """Filtro para busca de NCMs."""

    capitulo: str | None = None
    posicao: str | None = None
    tributacao_monofasica: bool | None = None
    zfm_isento_ipi: bool | None = None
    active: bool | None = True
    vigente: bool | None = True
    search: str | None = None


# ============================================================
# Retencao Federal Schemas
# ============================================================


class RetencaoFederalBase(BaseModel):
    """Base para configuracao de retencao federal."""

    nome: str = Field(..., min_length=3, max_length=100)
    codigo_servico: str | None = Field(None, max_length=20)
    descricao: str | None = Field(None, max_length=500)

    # Tipo de servico
    servico_vigilancia: bool = False
    servico_limpeza: bool = False
    servico_locacao_mao_obra: bool = False
    servico_construcao_civil: bool = False

    # INSS (11%)
    inss_retido: bool = True
    inss_aliquota: Decimal = Field(Decimal("11.00"), ge=0, le=100)
    inss_base_minima: Decimal | None = Field(None, ge=0)

    # Liminar INSS
    inss_liminar_ativa: bool = False
    inss_liminar_numero: str | None = Field(None, max_length=50)
    inss_liminar_vara: str | None = Field(None, max_length=100)
    inss_liminar_data: date | None = None
    inss_liminar_validade: date | None = None
    inss_liminar_texto: str | None = Field(None, max_length=1000)

    # IR (1.5%)
    ir_retido: bool = True
    ir_aliquota: Decimal = Field(Decimal("1.50"), ge=0, le=100)
    ir_base_minima: Decimal = Field(Decimal("666.66"), ge=0)

    # CSLL (1%)
    csll_retido: bool = True
    csll_aliquota: Decimal = Field(Decimal("1.00"), ge=0, le=100)

    # PIS (0.65%)
    pis_retido: bool = True
    pis_aliquota: Decimal = Field(Decimal("0.65"), ge=0, le=100)

    # COFINS (3%)
    cofins_retido: bool = True
    cofins_aliquota: Decimal = Field(Decimal("3.00"), ge=0, le=100)

    # PCC base minima
    pcc_base_minima: Decimal = Field(Decimal("215.05"), ge=0)

    # ISS
    iss_retido: bool = False
    iss_aliquota: Decimal | None = Field(None, ge=0, le=5)

    # Cliente especifico
    cliente_id: UUID | None = None
    cliente_aceita_liminar: bool | None = None

    # Vigencia
    valid_from: date = Field(default_factory=date.today)
    valid_until: date | None = None


class RetencaoFederalCreate(RetencaoFederalBase):
    """Schema para criar configuracao de retencao."""

    condominio_id: UUID


class RetencaoFederalUpdate(BaseModel):
    """Schema para atualizar configuracao de retencao."""

    nome: str | None = Field(None, max_length=100)
    descricao: str | None = Field(None, max_length=500)
    servico_vigilancia: bool | None = None
    servico_limpeza: bool | None = None
    servico_locacao_mao_obra: bool | None = None
    servico_construcao_civil: bool | None = None
    inss_retido: bool | None = None
    inss_aliquota: Decimal | None = None
    inss_base_minima: Decimal | None = None
    inss_liminar_ativa: bool | None = None
    inss_liminar_numero: str | None = None
    inss_liminar_vara: str | None = None
    inss_liminar_data: date | None = None
    inss_liminar_validade: date | None = None
    inss_liminar_texto: str | None = None
    ir_retido: bool | None = None
    ir_aliquota: Decimal | None = None
    ir_base_minima: Decimal | None = None
    csll_retido: bool | None = None
    csll_aliquota: Decimal | None = None
    pis_retido: bool | None = None
    pis_aliquota: Decimal | None = None
    cofins_retido: bool | None = None
    cofins_aliquota: Decimal | None = None
    pcc_base_minima: Decimal | None = None
    iss_retido: bool | None = None
    iss_aliquota: Decimal | None = None
    cliente_id: UUID | None = None
    cliente_aceita_liminar: bool | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    active: bool | None = None


class RetencaoFederalResponse(RetencaoFederalBase):
    """Response de configuracao de retencao."""

    id: UUID
    condominio_id: UUID
    aliquota_pcc: Decimal
    created_at: datetime
    updated_at: datetime | None
    active: bool

    class Config:
        from_attributes = True


class RetencaoFederalListResponse(BaseModel):
    """Lista de configuracoes de retencao."""

    items: list[RetencaoFederalResponse]
    total: int


class CalculoRetencaoRequest(BaseModel):
    """Request para calculo de retencoes."""

    valor_servico: Decimal = Field(..., gt=0)
    retencao_id: UUID | None = None
    cliente_aceita_liminar: bool = False
    tipo_servico: str | None = None


class CalculoRetencaoResponse(BaseModel):
    """Response do calculo de retencoes."""

    valor_servico: Decimal
    inss: Decimal
    ir: Decimal
    csll: Decimal
    pis: Decimal
    cofins: Decimal
    iss: Decimal
    total: Decimal
    valor_liquido: Decimal
    liminar_aplicada: bool
    liminar_numero: str | None = None
    detalhamento: dict[str, Any]


# ============================================================
# NF-e Schemas
# ============================================================


class NFeItemBase(BaseModel):
    """Base para item de NF-e."""

    numero_item: int = Field(..., ge=1)
    produto_id: UUID | None = None
    codigo_produto: str = Field(..., max_length=60)
    descricao: str = Field(..., max_length=120)
    ncm: str = Field(..., min_length=8, max_length=8)
    cfop: str = Field(..., min_length=4, max_length=4)

    unidade: str = Field(..., max_length=6)
    quantidade: Decimal = Field(..., gt=0)
    valor_unitario: Decimal = Field(..., gt=0)
    valor_total: Decimal | None = None

    # Descontos/Acrescimos
    valor_desconto: Decimal = Field(Decimal("0"), ge=0)
    valor_frete: Decimal = Field(Decimal("0"), ge=0)
    valor_seguro: Decimal = Field(Decimal("0"), ge=0)
    valor_outros: Decimal = Field(Decimal("0"), ge=0)

    # ICMS
    icms_origem: str = Field("0", max_length=1)
    icms_cst: str | None = Field(None, max_length=3)
    icms_csosn: str | None = Field(None, max_length=3)
    icms_base_calculo: Decimal = Field(Decimal("0"), ge=0)
    icms_aliquota: Decimal = Field(Decimal("0"), ge=0, le=100)
    icms_valor: Decimal = Field(Decimal("0"), ge=0)

    # IPI
    ipi_cst: str | None = Field(None, max_length=2)
    ipi_base_calculo: Decimal = Field(Decimal("0"), ge=0)
    ipi_aliquota: Decimal = Field(Decimal("0"), ge=0, le=100)
    ipi_valor: Decimal = Field(Decimal("0"), ge=0)

    # PIS
    pis_cst: str | None = Field(None, max_length=2)
    pis_base_calculo: Decimal = Field(Decimal("0"), ge=0)
    pis_aliquota: Decimal = Field(Decimal("0"), ge=0, le=100)
    pis_valor: Decimal = Field(Decimal("0"), ge=0)

    # COFINS
    cofins_cst: str | None = Field(None, max_length=2)
    cofins_base_calculo: Decimal = Field(Decimal("0"), ge=0)
    cofins_aliquota: Decimal = Field(Decimal("0"), ge=0, le=100)
    cofins_valor: Decimal = Field(Decimal("0"), ge=0)

    @model_validator(mode="before")
    @classmethod
    def calculate_total(cls, data: Any) -> Any:
        """Calcula valor total do item se nao informado."""
        if isinstance(data, dict):
            if data.get("valor_total") is None:
                qtd = data.get("quantidade", Decimal("0"))
                unit = data.get("valor_unitario", Decimal("0"))
                desc = data.get("valor_desconto", Decimal("0"))
                if qtd is not None and unit is not None:
                    data["valor_total"] = (Decimal(str(qtd)) * Decimal(str(unit))) - Decimal(str(desc))
        return data


class NFeItemCreate(NFeItemBase):
    """Schema para criar item de NF-e."""


class NFeItemResponse(NFeItemBase):
    """Response de item de NF-e."""

    id: UUID
    nfe_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class NFeBase(BaseModel):
    """Base para NF-e."""

    tipo: NFeTipoEnum = NFeTipoEnum.SAIDA
    finalidade: str = Field("1", max_length=1)  # 1-Normal, 2-Complementar, etc

    # Identificacao
    serie: int = Field(1, ge=1, le=999)
    numero: int | None = Field(None, ge=1)
    natureza_operacao: str = Field(..., max_length=60)
    data_emissao: datetime = Field(default_factory=datetime.now)
    data_saida_entrada: datetime | None = None

    # Emitente (pre-configurado ou informado)
    emitente_cnpj: str = Field(..., min_length=14, max_length=14)
    emitente_razao_social: str = Field(..., max_length=60)
    emitente_ie: str | None = Field(None, max_length=14)
    emitente_uf: str = Field(..., min_length=2, max_length=2)
    emitente_crt: str = Field("1", max_length=1)  # 1-Simples, 2-SN Exc, 3-Normal

    # Destinatario
    destinatario_cpf_cnpj: str = Field(..., max_length=14)
    destinatario_razao_social: str = Field(..., max_length=60)
    destinatario_ie: str | None = Field(None, max_length=14)
    destinatario_email: str | None = Field(None, max_length=60)
    destinatario_uf: str = Field(..., min_length=2, max_length=2)
    destinatario_logradouro: str = Field(..., max_length=60)
    destinatario_numero: str = Field(..., max_length=60)
    destinatario_bairro: str = Field(..., max_length=60)
    destinatario_municipio: str = Field(..., max_length=60)
    destinatario_cep: str = Field(..., min_length=8, max_length=8)
    destinatario_telefone: str | None = Field(None, max_length=14)

    # Frete
    modalidade_frete: str = Field("9", max_length=1)  # 0-Emit, 1-Dest, 9-SemFrete
    transportadora_cnpj: str | None = Field(None, max_length=14)
    transportadora_razao_social: str | None = Field(None, max_length=60)

    # Pagamento
    forma_pagamento: str = Field("0", max_length=2)  # 0-AVista, 1-APrazo
    meio_pagamento: str = Field("99", max_length=2)  # 01-Dinheiro, 99-Outros
    valor_pagamento: Decimal | None = Field(None, ge=0)

    # Informacoes adicionais
    informacoes_complementares: str | None = Field(None, max_length=5000)
    informacoes_fisco: str | None = Field(None, max_length=2000)

    # Zona Franca
    is_zfm: bool = False
    suframa_destinatario: str | None = Field(None, max_length=9)


class NFeCreate(NFeBase):
    """Schema para criar NF-e."""

    condominio_id: UUID
    itens: list[NFeItemCreate] = Field(..., min_items=1)


class NFeUpdate(BaseModel):
    """Schema para atualizar NF-e (apenas rascunho)."""

    natureza_operacao: str | None = Field(None, max_length=60)
    data_saida_entrada: datetime | None = None
    destinatario_email: str | None = Field(None, max_length=60)
    modalidade_frete: str | None = None
    informacoes_complementares: str | None = None
    informacoes_fisco: str | None = None


class NFeResponse(NFeBase):
    """Response de NF-e."""

    id: UUID
    condominio_id: UUID
    chave_acesso: str | None
    status: NFeStatusEnum
    protocolo_autorizacao: str | None
    data_autorizacao: datetime | None
    motivo_rejeicao: str | None

    # Totais
    valor_total_produtos: Decimal
    valor_total_icms: Decimal
    valor_total_ipi: Decimal
    valor_total_pis: Decimal
    valor_total_cofins: Decimal
    valor_total_frete: Decimal
    valor_total_seguro: Decimal
    valor_total_desconto: Decimal
    valor_total_outros: Decimal
    valor_total_nota: Decimal

    itens: list[NFeItemResponse]

    created_at: datetime
    updated_at: datetime | None
    active: bool

    class Config:
        from_attributes = True


class NFeListResponse(BaseModel):
    """Lista de NF-e."""

    items: list[NFeResponse]
    total: int
    page: int
    page_size: int


class NFeFilter(BaseModel):
    """Filtro para busca de NF-e."""

    tipo: NFeTipoEnum | None = None
    status: NFeStatusEnum | None = None
    serie: int | None = None
    numero_inicial: int | None = None
    numero_final: int | None = None
    data_emissao_inicial: date | None = None
    data_emissao_final: date | None = None
    destinatario_cpf_cnpj: str | None = None
    chave_acesso: str | None = None
    search: str | None = None


class NFeEmitirRequest(BaseModel):
    """Request para emitir NF-e."""

    nfe_id: UUID
    ambiente: str = Field("2", description="1-Producao, 2-Homologacao")


class NFeEmitirResponse(BaseModel):
    """Response da emissao de NF-e."""

    nfe_id: UUID
    status: NFeStatusEnum
    chave_acesso: str | None
    protocolo: str | None
    mensagem: str
    xml_autorizado: str | None
    pdf_danfe: str | None


class NFeCancelarRequest(BaseModel):
    """Request para cancelar NF-e."""

    nfe_id: UUID
    justificativa: str = Field(..., min_length=15, max_length=255)


class NFeInutilizarRequest(BaseModel):
    """Request para inutilizar numeracao."""

    serie: int
    numero_inicial: int
    numero_final: int
    justificativa: str = Field(..., min_length=15, max_length=255)


# ============================================================
# NFS-e Schemas
# ============================================================


class NFSeBase(BaseModel):
    """Base para NFS-e."""

    # Identificacao
    numero_rps: int | None = None
    serie_rps: str = Field("A", max_length=5)
    tipo_rps: str = Field("1", max_length=1)  # 1-RPS, 2-Cupom
    natureza_operacao: str = Field("1", max_length=1)  # 1-Tributada, 2-Isenta, etc
    regime_especial: str | None = Field(None, max_length=1)

    data_emissao: datetime = Field(default_factory=datetime.now)
    data_competencia: date = Field(default_factory=date.today)

    # Prestador
    prestador_cnpj: str = Field(..., min_length=14, max_length=14)
    prestador_inscricao_municipal: str | None = Field(None, max_length=15)
    prestador_razao_social: str = Field(..., max_length=150)

    # Tomador
    tomador_cpf_cnpj: str = Field(..., max_length=14)
    tomador_razao_social: str = Field(..., max_length=150)
    tomador_email: str | None = Field(None, max_length=80)
    tomador_inscricao_municipal: str | None = Field(None, max_length=15)
    tomador_logradouro: str = Field(..., max_length=125)
    tomador_numero: str = Field(..., max_length=10)
    tomador_complemento: str | None = Field(None, max_length=60)
    tomador_bairro: str = Field(..., max_length=60)
    tomador_municipio: str = Field(..., max_length=60)
    tomador_uf: str = Field(..., min_length=2, max_length=2)
    tomador_cep: str = Field(..., min_length=8, max_length=8)
    tomador_telefone: str | None = Field(None, max_length=20)

    # Servico
    codigo_servico: str = Field(..., max_length=20)  # LC 116
    descricao_servico: str = Field(..., max_length=2000)
    codigo_cnae: str | None = Field(None, max_length=7)
    codigo_tributacao_municipio: str | None = Field(None, max_length=20)

    # Valores
    valor_servicos: Decimal = Field(..., gt=0)
    valor_deducoes: Decimal = Field(Decimal("0"), ge=0)
    valor_desconto_condicionado: Decimal = Field(Decimal("0"), ge=0)
    valor_desconto_incondicionado: Decimal = Field(Decimal("0"), ge=0)

    # ISS
    iss_aliquota: Decimal = Field(..., ge=0, le=5)
    iss_valor: Decimal | None = Field(None, ge=0)
    iss_retido: bool = False

    # Retencoes federais
    pis_valor: Decimal = Field(Decimal("0"), ge=0)
    cofins_valor: Decimal = Field(Decimal("0"), ge=0)
    inss_valor: Decimal = Field(Decimal("0"), ge=0)
    ir_valor: Decimal = Field(Decimal("0"), ge=0)
    csll_valor: Decimal = Field(Decimal("0"), ge=0)
    outras_retencoes: Decimal = Field(Decimal("0"), ge=0)

    # Liminar INSS
    inss_liminar_aplicada: bool = False
    inss_liminar_numero: str | None = Field(None, max_length=50)
    inss_liminar_texto: str | None = Field(None, max_length=500)

    # Informacoes adicionais
    discriminacao: str | None = Field(None, max_length=2000)
    observacao: str | None = Field(None, max_length=1000)


class NFSeCreate(NFSeBase):
    """Schema para criar NFS-e."""

    condominio_id: UUID


class NFSeUpdate(BaseModel):
    """Schema para atualizar NFS-e (apenas rascunho)."""

    tomador_email: str | None = Field(None, max_length=80)
    descricao_servico: str | None = Field(None, max_length=2000)
    discriminacao: str | None = None
    observacao: str | None = None


class NFSeResponse(NFSeBase):
    """Response de NFS-e."""

    id: UUID
    condominio_id: UUID
    status: NFSeStatusEnum
    numero_nfse: str | None
    codigo_verificacao: str | None
    link_nfse: str | None
    protocolo: str | None
    data_processamento: datetime | None
    mensagem_retorno: str | None

    # Valores calculados
    valor_liquido: Decimal
    total_retencoes: Decimal

    created_at: datetime
    updated_at: datetime | None
    active: bool

    class Config:
        from_attributes = True


class NFSeListResponse(BaseModel):
    """Lista de NFS-e."""

    items: list[NFSeResponse]
    total: int
    page: int
    page_size: int


class NFSeFilter(BaseModel):
    """Filtro para busca de NFS-e."""

    status: NFSeStatusEnum | None = None
    data_emissao_inicial: date | None = None
    data_emissao_final: date | None = None
    competencia_mes: int | None = None
    competencia_ano: int | None = None
    tomador_cpf_cnpj: str | None = None
    codigo_servico: str | None = None
    numero_nfse: str | None = None
    search: str | None = None


class NFSeEmitirRequest(BaseModel):
    """Request para emitir NFS-e."""

    nfse_id: UUID
    ambiente: str = Field("2", description="1-Producao, 2-Homologacao")


class NFSeEmitirResponse(BaseModel):
    """Response da emissao de NFS-e."""

    nfse_id: UUID
    status: NFSeStatusEnum
    numero_nfse: str | None
    codigo_verificacao: str | None
    link_nfse: str | None
    protocolo: str | None
    mensagem: str
    xml: str | None
    pdf: str | None


class NFSeCancelarRequest(BaseModel):
    """Request para cancelar NFS-e."""

    nfse_id: UUID
    codigo_cancelamento: str = Field(..., max_length=4)
    motivo_cancelamento: str | None = Field(None, max_length=255)


# ============================================================
# SPED Schemas
# ============================================================


class SPEDFileBase(BaseModel):
    """Base para arquivo SPED."""

    tipo: SPEDTipoEnum
    ano: int = Field(..., ge=2000, le=2100)
    mes: int | None = Field(None, ge=1, le=12)
    finalidade: str = Field("0", max_length=1)  # 0-Original, 1-Retificadora
    perfil: str | None = Field(None, max_length=1)  # A, B, C


class SPEDFileCreate(SPEDFileBase):
    """Schema para criar arquivo SPED."""

    condominio_id: UUID


class SPEDFileResponse(SPEDFileBase):
    """Response de arquivo SPED."""

    id: UUID
    condominio_id: UUID
    status: SPEDStatusEnum
    nome_arquivo: str | None
    hash_arquivo: str | None
    tamanho_bytes: int | None

    # Transmissao
    recibo_transmissao: str | None
    data_transmissao: datetime | None
    protocolo_entrega: str | None
    data_processamento: datetime | None

    # Erros
    total_erros: int
    total_avisos: int
    erros: list[dict[str, Any]] | None
    avisos: list[dict[str, Any]] | None

    # Resumo
    resumo: dict[str, Any] | None

    created_at: datetime
    updated_at: datetime | None
    active: bool

    class Config:
        from_attributes = True


class SPEDFileListResponse(BaseModel):
    """Lista de arquivos SPED."""

    items: list[SPEDFileResponse]
    total: int
    page: int
    page_size: int


class SPEDFilter(BaseModel):
    """Filtro para busca de arquivos SPED."""

    tipo: SPEDTipoEnum | None = None
    status: SPEDStatusEnum | None = None
    ano: int | None = None
    mes: int | None = None


class SPEDGerarRequest(BaseModel):
    """Request para gerar arquivo SPED."""

    tipo: SPEDTipoEnum
    ano: int
    mes: int | None = None
    finalidade: str = Field("0", description="0-Original, 1-Retificadora")


class SPEDValidarRequest(BaseModel):
    """Request para validar arquivo SPED."""

    sped_id: UUID


class SPEDTransmitirRequest(BaseModel):
    """Request para transmitir arquivo SPED."""

    sped_id: UUID
    ambiente: str = Field("2", description="1-Producao, 2-Homologacao")


# ============================================================
# Obrigacao Fiscal Schemas
# ============================================================


class ObrigacaoFiscalBase(BaseModel):
    """Base para obrigacao fiscal."""

    tipo: str = Field(..., max_length=30)  # DAS, DCTF, DIRF, EFD, etc
    nome: str = Field(..., max_length=100)
    descricao: str | None = Field(None, max_length=500)
    competencia_mes: int | None = Field(None, ge=1, le=12)
    competencia_ano: int = Field(..., ge=2000, le=2100)
    data_vencimento: date
    valor_devido: Decimal | None = Field(None, ge=0)


class ObrigacaoFiscalCreate(ObrigacaoFiscalBase):
    """Schema para criar obrigacao fiscal."""

    condominio_id: UUID


class ObrigacaoFiscalUpdate(BaseModel):
    """Schema para atualizar obrigacao fiscal."""

    data_vencimento: date | None = None
    valor_devido: Decimal | None = None
    valor_pago: Decimal | None = None
    data_pagamento: date | None = None
    numero_recibo: str | None = None
    observacoes: str | None = None
    status: ObrigacaoStatusEnum | None = None


class ObrigacaoFiscalResponse(ObrigacaoFiscalBase):
    """Response de obrigacao fiscal."""

    id: UUID
    condominio_id: UUID
    # Response de dado persistido: sem constraint de input. competencia_mes=0
    # representa obrigacao ANUAL (sem mes); o ge=1 da base estourava 500.
    competencia_mes: int | None = None
    # Aceita qualquer status real do banco (ex.: "cumprida"); o enum estava
    # defasado em relacao aos valores persistidos e causava 500 na listagem.
    status: str
    valor_pago: Decimal | None
    data_pagamento: date | None
    numero_recibo: str | None
    observacoes: str | None
    dias_para_vencimento: int
    is_atrasada: bool

    created_at: datetime
    updated_at: datetime | None
    active: bool

    class Config:
        from_attributes = True


class ObrigacaoFiscalListResponse(BaseModel):
    """Lista de obrigacoes fiscais."""

    items: list[ObrigacaoFiscalResponse]
    total: int
    proximas_a_vencer: int
    atrasadas: int


class ObrigacaoFilter(BaseModel):
    """Filtro para busca de obrigacoes."""

    tipo: str | None = None
    status: ObrigacaoStatusEnum | None = None
    mes: int | None = None
    ano: int | None = None
    vencimento_inicio: date | None = None
    vencimento_fim: date | None = None


# ============================================================
# Simples Nacional / DAS Schemas
# ============================================================


class SimplesNacionalDASBase(BaseModel):
    """Base para DAS do Simples Nacional."""

    competencia_mes: int = Field(..., ge=1, le=12)
    competencia_ano: int = Field(..., ge=2000, le=2100)
    data_vencimento: date

    # Receita
    receita_bruta_mes: Decimal = Field(..., ge=0)
    receita_bruta_12_meses: Decimal = Field(..., ge=0)

    # Faixa e aliquota
    anexo: str = Field("III", max_length=5)  # III para vigilancia
    faixa: int = Field(..., ge=1, le=6)
    aliquota_nominal: Decimal = Field(..., ge=0, le=100)
    aliquota_efetiva: Decimal = Field(..., ge=0, le=100)
    parcela_deduzir: Decimal = Field(..., ge=0)

    # Valor
    valor_devido: Decimal = Field(..., ge=0)


class SimplesNacionalDASCreate(SimplesNacionalDASBase):
    """Schema para criar DAS."""

    condominio_id: UUID


class SimplesNacionalDASResponse(SimplesNacionalDASBase):
    """Response de DAS."""

    id: UUID
    condominio_id: UUID
    status: ObrigacaoStatusEnum
    numero_documento: str | None
    codigo_barras: str | None
    valor_pago: Decimal | None
    data_pagamento: date | None
    numero_recibo: str | None

    # Reparticao tributos
    reparticao_irpj: Decimal | None
    reparticao_csll: Decimal | None
    reparticao_cofins: Decimal | None
    reparticao_pis: Decimal | None
    reparticao_cpp: Decimal | None
    reparticao_iss: Decimal | None

    created_at: datetime
    updated_at: datetime | None
    active: bool

    class Config:
        from_attributes = True


class DASCalcularRequest(BaseModel):
    """Request para calcular DAS."""

    receita_bruta_mes: Decimal
    receita_bruta_12_meses: Decimal
    anexo: str = Field("III", description="III, IV ou V")
    competencia_mes: int
    competencia_ano: int


class DASCalcularResponse(BaseModel):
    """Response do calculo do DAS."""

    faixa: int
    aliquota_nominal: Decimal
    parcela_deduzir: Decimal
    aliquota_efetiva: Decimal
    valor_devido: Decimal
    reparticao: dict[str, Decimal]
    data_vencimento: date


# ============================================================
# SUFRAMA / Zona Franca Schemas
# ============================================================


class SUFRAMAConfigBase(BaseModel):
    """Base para configuracao SUFRAMA."""

    inscricao_suframa: str = Field(..., max_length=9)
    data_validade: date
    tipo_incentivo: str = Field(..., max_length=20)

    # Beneficios
    isento_ipi: bool = True
    reducao_icms: bool = True
    percentual_reducao_icms: Decimal = Field(Decimal("100"), ge=0, le=100)
    suspensao_pis_cofins: bool = True

    # Produtos incentivados
    ncms_incentivados: list[str] | None = None


class SUFRAMAConfigCreate(SUFRAMAConfigBase):
    """Schema para criar config SUFRAMA."""

    condominio_id: UUID


class SUFRAMAConfigResponse(SUFRAMAConfigBase):
    """Response de config SUFRAMA."""

    id: UUID
    condominio_id: UUID
    is_vigente: bool
    dias_para_vencimento: int

    created_at: datetime
    updated_at: datetime | None
    active: bool

    class Config:
        from_attributes = True


class SUFRAMAOperacaoBase(BaseModel):
    """Base para operacao com beneficio SUFRAMA."""

    nfe_id: UUID | None = None
    data_operacao: date
    valor_operacao: Decimal = Field(..., gt=0)
    valor_ipi_desonerado: Decimal = Field(Decimal("0"), ge=0)
    valor_icms_desonerado: Decimal = Field(Decimal("0"), ge=0)
    valor_pis_suspenso: Decimal = Field(Decimal("0"), ge=0)
    valor_cofins_suspenso: Decimal = Field(Decimal("0"), ge=0)

    # PIN (Protocolo de Ingresso)
    numero_pin: str | None = Field(None, max_length=20)
    data_pin: date | None = None
    status_pin: str | None = Field(None, max_length=20)


class SUFRAMAOperacaoCreate(SUFRAMAOperacaoBase):
    """Schema para criar operacao SUFRAMA."""

    condominio_id: UUID


class SUFRAMAOperacaoResponse(SUFRAMAOperacaoBase):
    """Response de operacao SUFRAMA."""

    id: UUID
    condominio_id: UUID
    total_economia: Decimal

    created_at: datetime
    active: bool

    class Config:
        from_attributes = True


class SUFRAMAOperacaoListResponse(BaseModel):
    """Lista de operacoes SUFRAMA."""

    items: list[SUFRAMAOperacaoResponse]
    total: int
    total_economia_ipi: Decimal
    total_economia_icms: Decimal
    total_economia_pis_cofins: Decimal


# ============================================================
# AI Service Schemas
# ============================================================


class FiscalAIAnalyseRequest(BaseModel):
    """Request para analise fiscal por IA."""

    periodo_inicio: date
    periodo_fim: date
    incluir_nfe: bool = True
    incluir_nfse: bool = True
    incluir_retencoes: bool = True
    incluir_obrigacoes: bool = True


class FiscalAIAnalyseResponse(BaseModel):
    """Response da analise fiscal por IA."""

    resumo_periodo: dict[str, Any]
    alertas: list[dict[str, Any]]
    oportunidades: list[dict[str, Any]]
    pendencias: list[dict[str, Any]]
    recomendacoes: list[str]
    score_compliance: int  # 0-100
    projecao_impostos: dict[str, Decimal]


class FiscalAIOptimizeRequest(BaseModel):
    """Request para otimizacao tributaria por IA."""

    receita_mensal_media: Decimal
    tipo_servico: str
    uf_operacao: str
    simula_regimes: bool = True


class FiscalAIOptimizeResponse(BaseModel):
    """Response da otimizacao tributaria."""

    regime_atual: str
    carga_tributaria_atual: Decimal
    regimes_simulados: list[dict[str, Any]]
    melhor_regime: str
    economia_potencial: Decimal
    acoes_recomendadas: list[str]


class FiscalAIPredictRequest(BaseModel):
    """Request para previsao de obrigacoes."""

    meses_projecao: int = Field(6, ge=1, le=12)


class FiscalAIPredictResponse(BaseModel):
    """Response da previsao de obrigacoes."""

    projecao_mensal: list[dict[str, Any]]
    total_previsto: Decimal
    obrigacoes_futuras: list[dict[str, Any]]
    alertas_vencimento: list[dict[str, Any]]


# ============================================================
# Stats e Dashboard
# ============================================================


class FiscalStats(BaseModel):
    """Estatisticas fiscais."""

    # NF-e
    total_nfe_emitidas: int
    total_nfe_mes: int
    valor_total_nfe_mes: Decimal

    # NFS-e
    total_nfse_emitidas: int
    total_nfse_mes: int
    valor_total_nfse_mes: Decimal

    # Retencoes
    total_retencoes_mes: Decimal
    economia_liminar_inss: Decimal

    # Obrigacoes
    obrigacoes_pendentes: int
    obrigacoes_atrasadas: int
    proxima_obrigacao: dict[str, Any] | None

    # Simples Nacional
    das_mes_atual: Decimal | None
    faixa_atual: int | None
    receita_12_meses: Decimal | None

    # SUFRAMA
    economia_zfm_mes: Decimal | None
    economia_zfm_ano: Decimal | None


class FiscalDashboard(BaseModel):
    """Dashboard fiscal completo."""

    stats: FiscalStats
    notas_recentes: list[dict[str, Any]]
    obrigacoes_proximas: list[dict[str, Any]]
    alertas: list[dict[str, Any]]
    grafico_impostos: list[dict[str, Any]]
    grafico_notas: list[dict[str, Any]]


# ── Multi-Regime Tax Calculator Schemas ──────────────────────────────────────


class CalculoSimplesRequest(BaseModel):
    """Calcular DAS do Simples Nacional"""

    receita_mes: float = Field(..., description="Receita bruta do mês em R$", example=50000.00)
    rbt12: float = Field(..., description="Receita bruta acumulada 12 meses em R$", example=500000.00)
    liminares: list[str] = Field(default_factory=list, description="Liminares ativas: pis_cofins_zero, inss_nao_retido")


class CalculoLucroRealRequest(BaseModel):
    """Calcular impostos no Lucro Real"""

    receita_mes: float = Field(..., description="Receita bruta do mês em R$", example=100000.00)
    receita_trimestre: float = Field(..., description="Receita bruta do trimestre em R$", example=300000.00)
    custos_dedutiveis_mes: float = Field(default=0.0, description="Créditos PIS/COFINS do mês")


class ComparativoRegimesRequest(BaseModel):
    """Comparar Simples Nacional vs Lucro Real"""

    receita_anual: float = Field(..., description="Receita bruta anual em R$", example=1200000.00)
    custos_dedutiveis_anual: float = Field(default=0.0)
    liminares: list[str] = Field(default_factory=list)


class RetencoesNFSeRequest(BaseModel):
    """Calcular retenções na fonte para NFS-e"""

    valor_servico: float = Field(..., description="Valor da nota de serviço")
    regime_empresa: str = Field(default="simples_nacional", description="simples_nacional ou lucro_real")
    liminares: list[str] = Field(default_factory=list)


class VerificacaoLimiteSimplesRequest(BaseModel):
    rbt12: float = Field(..., description="Receita bruta 12 meses")
