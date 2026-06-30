"""
Models EPI (NR-6) - Equipamentos de Protecao Individual
========================================================

Modelos para gerenciamento de EPIs e entregas.
"""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.models import Base


class EPICategory(StrEnum):
    """Categorias de EPI conforme NR-6."""

    CABECA = "cabeca"  # A - Protecao da cabeca
    OLHOS = "olhos"  # B - Protecao dos olhos
    FACE = "face"  # C - Protecao da face
    AUDITIVO = "auditivo"  # D - Protecao auditiva
    RESPIRATORIO = "respiratorio"  # E - Protecao respiratoria
    TRONCO = "tronco"  # F - Protecao do tronco
    MEMBROS_SUPERIORES = "membros_superiores"  # G - Membros superiores
    MEMBROS_INFERIORES = "membros_inferiores"  # H - Membros inferiores
    CORPO_INTEIRO = "corpo_inteiro"  # I - Corpo inteiro
    QUEDAS = "quedas"  # J - Protecao contra quedas


class EPIStatus(StrEnum):
    """Status do EPI no inventario."""

    DISPONIVEL = "disponivel"
    ENTREGUE = "entregue"
    EM_USO = "em_uso"
    DANIFICADO = "danificado"
    VENCIDO = "vencido"
    DESCARTADO = "descartado"


class DeliveryReason(StrEnum):
    """Motivos de entrega de EPI."""

    ADMISSAO = "admissao"
    SUBSTITUICAO = "substituicao"
    DESGASTE = "desgaste"
    PERDA = "perda"
    TROCA_FUNCAO = "troca_funcao"
    VENCIMENTO = "vencimento"
    DEVOLUCAO = "devolucao"


class EPI(Base):
    """
    Cadastro de EPI.

    Modelo base para tipos de EPIs disponiveis.
    """

    __tablename__ = "health_epi_catalog"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identificacao
    nome = Column(String(100), nullable=False)
    descricao = Column(Text, nullable=True)
    codigo_interno = Column(String(30), nullable=True, unique=True)

    # Classificacao NR-6
    categoria = Column(String(30), nullable=False, index=True)

    # Certificacao
    ca_number = Column("ca_numero", String(20), nullable=False, index=True)  # DB col = ca_numero
    ca_validade = Column(Date, nullable=True)

    # Fabricante
    fabricante = Column(String(100), nullable=False)
    modelo = Column(String(100), nullable=True)

    # Vida util
    validade_dias = Column(Integer, nullable=False, default=365)

    # Especificacoes tecnicas
    especificacoes = Column(JSONB, default=dict)

    # Riscos protegidos
    riscos_protegidos = Column(JSONB, default=list)

    # Instrucoes
    instrucoes_uso = Column(Text, nullable=True)
    instrucoes_higienizacao = Column(Text, nullable=True)
    instrucoes_armazenamento = Column(Text, nullable=True)

    # Imagem
    imagem_url = Column(String(500), nullable=True)

    # Status
    ativo = Column(Boolean, default=True, index=True)

    # Auditoria
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)

    # Relacionamentos
    entregas = relationship("EPIDelivery", back_populates="epi", foreign_keys="[EPIDelivery.epi_id]")
    estoque = relationship("EPIInventory", back_populates="epi", uselist=False, foreign_keys="[EPIInventory.epi_id]")

    # Indices
    __table_args__ = (
        Index("idx_epi_categoria_ativo", "categoria", "ativo"),
        Index("idx_epi_ca", "ca_numero"),
    )

    def __repr__(self) -> str:
        return f"<EPI {self.nome} - CA {self.ca_number}>"

    @property
    def ca_esta_valido(self) -> bool:
        """Verifica se o CA esta dentro da validade."""
        if not self.ca_validade:
            return True
        return date.today() <= self.ca_validade


class EPIDelivery(Base):
    """
    Entrega de EPI (Ficha de EPI).

    Registro de entrega de EPI para funcionario.
    """

    __tablename__ = "health_epi_deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referencias
    epi_id = Column(UUID(as_uuid=True), ForeignKey("health_epi_catalog.id"), nullable=False, index=True)
    funcionario_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Dados da entrega
    quantidade = Column(Integer, nullable=False, default=1)
    motivo = Column(String(30), nullable=False)  # admissao, substituicao, etc

    # CA no momento da entrega
    ca_number = Column("ca_numero", String(20), nullable=False)

    # Datas
    data_entrega = Column(DateTime, nullable=False, default=datetime.utcnow)
    data_validade = Column(Date, nullable=True)  # Validade deste EPI especifico

    # Devolucao
    devolvido = Column(Boolean, default=False)
    data_devolucao = Column(DateTime, nullable=True)
    motivo_devolucao = Column(String(100), nullable=True)
    condicao_devolucao = Column(String(50), nullable=True)  # bom, danificado, etc

    # Assinatura
    assinatura_funcionario = Column(Boolean, default=False)
    data_assinatura = Column(DateTime, nullable=True)
    assinatura_digital_url = Column(String(500), nullable=True)

    # Responsavel pela entrega
    entregue_por = Column(UUID(as_uuid=True), nullable=True)

    # Observacoes
    observacoes = Column(Text, nullable=True)

    # Treinamento
    treinamento_realizado = Column(Boolean, default=False)
    data_treinamento = Column(DateTime, nullable=True)

    # Auditoria
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    epi = relationship("EPI", back_populates="entregas")

    # Indices
    __table_args__ = (
        Index("idx_delivery_funcionario", "funcionario_id"),
        Index("idx_delivery_data", "data_entrega"),
        Index("idx_delivery_epi_funcionario", "epi_id", "funcionario_id"),
    )

    def __repr__(self) -> str:
        return f"<EPIDelivery {self.epi_id} -> {self.funcionario_id}>"

    @property
    def esta_vencido(self) -> bool:
        """Verifica se o EPI entregue esta vencido."""
        if not self.data_validade:
            return False
        return date.today() > self.data_validade

    @property
    def dias_para_vencer(self) -> int | None:
        """Dias restantes para vencimento."""
        if not self.data_validade:
            return None
        delta = self.data_validade - date.today()
        return max(0, delta.days)


class EPIInventory(Base):
    """
    Estoque de EPI.

    Controle de estoque de cada tipo de EPI.
    """

    __tablename__ = "health_epi_inventory"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    epi_id = Column(UUID(as_uuid=True), ForeignKey("health_epi_catalog.id"), nullable=False, unique=True)

    # Quantidades
    quantidade_atual = Column(Integer, nullable=False, default=0)
    quantidade_minima = Column(Integer, nullable=False, default=10)
    quantidade_maxima = Column(Integer, nullable=True)

    # Localizacao
    local_armazenamento = Column(String(100), nullable=True)

    # Controle de lote
    lote_atual = Column(String(50), nullable=True)
    data_validade_lote = Column(Date, nullable=True)

    # Custos
    custo_unitario = Column(Float, nullable=True)
    fornecedor = Column(String(100), nullable=True)

    # Ultima movimentacao
    ultima_entrada = Column(DateTime, nullable=True)
    ultima_saida = Column(DateTime, nullable=True)

    # Auditoria
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    epi = relationship("EPI", back_populates="estoque")

    def __repr__(self) -> str:
        return f"<EPIInventory {self.epi_id}: {self.quantidade_atual}>"

    @property
    def estoque_baixo(self) -> bool:
        """Verifica se o estoque esta abaixo do minimo."""
        return self.quantidade_atual < self.quantidade_minima

    @property
    def percentual_estoque(self) -> float | None:
        """Percentual do estoque em relacao ao maximo."""
        if not self.quantidade_maxima:
            return None
        return (self.quantidade_atual / self.quantidade_maxima) * 100
