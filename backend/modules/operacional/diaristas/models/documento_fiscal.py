"""
Models de Documentos Fiscais para Diaristas.

Fornece modelos para:
- RPA (Recibo de Pagamento Autônomo)
- Retenções (INSS, ISS, IRRF)
- Eventos e-Social
- NFS-e (referência)
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from core.database import Base

# =============================================================================
# ENUMS
# =============================================================================


class TipoDocumentoFiscal(StrEnum):
    """Tipos de documento fiscal."""

    RPA = "rpa"  # Recibo de Pagamento Autônomo
    NFSE = "nfse"  # Nota Fiscal de Serviços Eletrônica
    RECIBO_SIMPLES = "recibo_simples"
    DECLARACAO = "declaracao"


class StatusDocumentoFiscal(StrEnum):
    """Status do documento fiscal."""

    RASCUNHO = "rascunho"
    EMITIDO = "emitido"
    CANCELADO = "cancelado"
    SUBSTITUIDO = "substituido"


class TipoRetencao(StrEnum):
    """Tipos de retenção fiscal."""

    INSS = "inss"  # Instituto Nacional do Seguro Social
    ISS = "iss"  # Imposto Sobre Serviços
    IRRF = "irrf"  # Imposto de Renda Retido na Fonte
    PIS = "pis"  # Programa de Integração Social
    COFINS = "cofins"  # Contribuição para o Financiamento da Seguridade Social
    CSLL = "csll"  # Contribuição Social sobre o Lucro Líquido


class TipoEventoESocial(StrEnum):
    """Tipos de evento e-Social relacionados a autônomos."""

    S2300 = "S-2300"  # Trabalhador Sem Vínculo - Início
    S2306 = "S-2306"  # Trabalhador Sem Vínculo - Alteração Contratual
    S2399 = "S-2399"  # Trabalhador Sem Vínculo - Término
    S1200 = "S-1200"  # Remuneração de Trabalhador vinculado ao RGPS
    S1210 = "S-1210"  # Pagamentos de Rendimentos do Trabalho


class StatusEventoESocial(StrEnum):
    """Status do evento e-Social."""

    PENDENTE = "pendente"
    ENVIADO = "enviado"
    PROCESSANDO = "processando"
    ACEITO = "aceito"
    REJEITADO = "rejeitado"
    RETIFICADO = "retificado"


# =============================================================================
# MODELS
# =============================================================================


class DocumentoFiscal(Base):
    """
    Documento fiscal (RPA, NFS-e, etc) emitido para diaristas.
    """

    __tablename__ = "documentos_fiscais_diaristas"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Identificação
    numero = Column(String(50), unique=True, nullable=False)
    tipo = Column(SQLEnum(TipoDocumentoFiscal), nullable=False, default=TipoDocumentoFiscal.RPA)
    status = Column(SQLEnum(StatusDocumentoFiscal), nullable=False, default=StatusDocumentoFiscal.RASCUNHO)

    # Relacionamentos
    diarist_id = Column(
        PG_UUID(as_uuid=True), ForeignKey("diaristas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_id = Column(
        PG_UUID(as_uuid=True), ForeignKey("diarist_payments.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Período e datas
    competencia = Column(String(7), nullable=False)  # YYYY-MM
    data_emissao = Column(Date, nullable=False, default=date.today)
    data_pagamento = Column(Date, nullable=True)

    # Valores
    valor_bruto = Column(Numeric(12, 2), nullable=False, default=0)
    valor_inss = Column(Numeric(12, 2), nullable=False, default=0)
    valor_iss = Column(Numeric(12, 2), nullable=False, default=0)
    valor_irrf = Column(Numeric(12, 2), nullable=False, default=0)
    valor_outras_retencoes = Column(Numeric(12, 2), nullable=False, default=0)
    valor_liquido = Column(Numeric(12, 2), nullable=False, default=0)

    # Dados do prestador
    prestador_cpf = Column(String(14), nullable=False)
    prestador_nome = Column(String(200), nullable=False)
    prestador_endereco = Column(String(500), nullable=True)
    prestador_municipio = Column(String(100), nullable=True)
    prestador_uf = Column(String(2), nullable=True)
    prestador_pis = Column(String(20), nullable=True)

    # Dados do tomador
    tomador_cnpj = Column(String(18), nullable=False)
    tomador_razao_social = Column(String(200), nullable=False)
    tomador_endereco = Column(String(500), nullable=True)

    # Descrição do serviço
    descricao_servico = Column(Text, nullable=False)
    codigo_servico = Column(String(20), nullable=True)  # Código LC 116/2003
    cnae = Column(String(10), nullable=True)

    # Cálculos detalhados
    base_calculo_inss = Column(Numeric(12, 2), nullable=True)
    aliquota_inss = Column(Numeric(5, 2), nullable=True)  # Ex: 11.00
    base_calculo_iss = Column(Numeric(12, 2), nullable=True)
    aliquota_iss = Column(Numeric(5, 2), nullable=True)  # Ex: 5.00
    base_calculo_irrf = Column(Numeric(12, 2), nullable=True)
    aliquota_irrf = Column(Numeric(5, 2), nullable=True)  # Ex: 15.00

    # Observações e histórico
    observacoes = Column(Text, nullable=True)
    historico_alteracoes = Column(JSONB, nullable=True)

    # NFS-e (quando aplicável)
    nfse_numero = Column(String(50), nullable=True)
    nfse_codigo_verificacao = Column(String(100), nullable=True)
    nfse_url = Column(String(500), nullable=True)

    # Arquivo PDF
    pdf_url = Column(String(500), nullable=True)

    # Metadados
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(PG_UUID(as_uuid=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relacionamentos
    retencoes = relationship("RetencaoFiscal", back_populates="documento", cascade="all, delete-orphan")

    # Índices
    __table_args__ = (
        Index("ix_doc_fiscal_competencia", "competencia"),
        Index("ix_doc_fiscal_prestador_cpf", "prestador_cpf"),
        Index("ix_doc_fiscal_status", "status"),
    )

    def __repr__(self):
        return f"<DocumentoFiscal {self.numero} - {self.tipo.value}>"

    @property
    def total_retencoes(self) -> Decimal:
        """Retorna total de retenções."""
        return self.valor_inss + self.valor_iss + self.valor_irrf + self.valor_outras_retencoes

    def calcular_liquido(self):
        """Recalcula valor líquido."""
        self.valor_liquido = self.valor_bruto - self.total_retencoes


class RetencaoFiscal(Base):
    """
    Retenção fiscal detalhada de um documento.
    """

    __tablename__ = "retencoes_fiscais_diaristas"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Relacionamento
    documento_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("documentos_fiscais_diaristas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Tipo e valores
    tipo = Column(SQLEnum(TipoRetencao), nullable=False)
    base_calculo = Column(Numeric(12, 2), nullable=False)
    aliquota = Column(Numeric(5, 2), nullable=False)  # Percentual
    valor = Column(Numeric(12, 2), nullable=False)

    # Fundamentação legal
    fundamentacao_legal = Column(String(200), nullable=True)
    codigo_receita = Column(String(20), nullable=True)  # DARF

    # Observações
    observacoes = Column(Text, nullable=True)

    # Metadados
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos
    documento = relationship("DocumentoFiscal", back_populates="retencoes")

    def __repr__(self):
        return f"<RetencaoFiscal {self.tipo.value} - R$ {self.valor}>"


class EventoESocial(Base):
    """
    Eventos e-Social relacionados a trabalhadores autônomos.
    """

    __tablename__ = "eventos_esocial_diaristas"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Identificação
    tipo_evento = Column(SQLEnum(TipoEventoESocial), nullable=False)
    status = Column(SQLEnum(StatusEventoESocial), nullable=False, default=StatusEventoESocial.PENDENTE)

    # Relacionamentos
    diarist_id = Column(
        PG_UUID(as_uuid=True), ForeignKey("diaristas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    documento_id = Column(
        PG_UUID(as_uuid=True), ForeignKey("documentos_fiscais_diaristas.id", ondelete="SET NULL"), nullable=True
    )

    # Dados do evento
    competencia = Column(String(7), nullable=False)  # YYYY-MM
    id_evento = Column(String(50), unique=True, nullable=True)  # ID gerado pelo e-Social
    numero_recibo = Column(String(100), nullable=True)  # Recibo de envio

    # XML do evento
    xml_envio = Column(Text, nullable=True)
    xml_retorno = Column(Text, nullable=True)

    # Dados específicos do evento (JSON)
    dados_evento = Column(JSONB, nullable=True)

    # Processamento
    data_envio = Column(DateTime, nullable=True)
    data_processamento = Column(DateTime, nullable=True)
    mensagem_retorno = Column(Text, nullable=True)
    codigo_retorno = Column(String(20), nullable=True)

    # Retificação
    evento_retificado_id = Column(PG_UUID(as_uuid=True), ForeignKey("eventos_esocial_diaristas.id"), nullable=True)

    # Metadados
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(PG_UUID(as_uuid=True), nullable=True)

    # Índices
    __table_args__ = (
        Index("ix_evento_esocial_competencia", "competencia"),
        Index("ix_evento_esocial_tipo", "tipo_evento"),
        Index("ix_evento_esocial_status", "status"),
    )

    def __repr__(self):
        return f"<EventoESocial {self.tipo_evento.value} - {self.status.value}>"


class TabelaINSS(Base):
    """
    Tabela de alíquotas do INSS para contribuintes individuais.
    Atualizada anualmente.
    """

    __tablename__ = "tabela_inss"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Vigência
    vigencia_inicio = Column(Date, nullable=False)
    vigencia_fim = Column(Date, nullable=True)

    # Faixas e alíquotas
    faixas = Column(JSONB, nullable=False)
    # Estrutura:
    # [
    #     {"ate": 1412.00, "aliquota": 7.5},
    #     {"ate": 2666.68, "aliquota": 9.0},
    #     {"ate": 4000.03, "aliquota": 12.0},
    #     {"ate": 7786.02, "aliquota": 14.0},
    # ]

    # Teto
    teto_contribuicao = Column(Numeric(12, 2), nullable=False)

    # Para autônomos
    aliquota_autonomo = Column(Numeric(5, 2), nullable=False, default=Decimal("11.00"))

    # Metadados
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column("is_ativo", Boolean, default=True, nullable=False)  # coluna real do banco e is_ativo

    def __repr__(self):
        return f"<TabelaINSS vigência {self.vigencia_inicio}>"


class TabelaIRRF(Base):
    """
    Tabela de alíquotas do IRRF.
    Atualizada anualmente.
    """

    __tablename__ = "tabela_irrf"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Vigência
    vigencia_inicio = Column(Date, nullable=False)
    vigencia_fim = Column(Date, nullable=True)

    # Faixas e alíquotas
    faixas = Column(JSONB, nullable=False)
    # Estrutura:
    # [
    #     {"ate": 2259.20, "aliquota": 0, "deducao": 0},
    #     {"ate": 2826.65, "aliquota": 7.5, "deducao": 169.44},
    #     {"ate": 3751.05, "aliquota": 15.0, "deducao": 381.44},
    #     {"ate": 4664.68, "aliquota": 22.5, "deducao": 662.77},
    #     {"acima": 4664.68, "aliquota": 27.5, "deducao": 896.00},
    # ]

    # Dedução por dependente
    deducao_dependente = Column(Numeric(12, 2), nullable=False)

    # Metadados
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column("is_ativo", Boolean, default=True, nullable=False)  # coluna real do banco e is_ativo

    def __repr__(self):
        return f"<TabelaIRRF vigência {self.vigencia_inicio}>"
