"""
Models PPRA/PGR (NR-9) - Programa de Prevencao de Riscos Ambientais
===================================================================

Modelos para gerenciamento de riscos ocupacionais e mapeamento.
"""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.models import Base


class RiskCategory(StrEnum):
    """Categorias de risco ocupacional conforme NR-9."""

    FISICO = "fisico"  # Verde no mapa de riscos
    QUIMICO = "quimico"  # Vermelho
    BIOLOGICO = "biologico"  # Marrom
    ERGONOMICO = "ergonomico"  # Amarelo
    ACIDENTE = "acidente"  # Azul


class RiskLevel(StrEnum):
    """Niveis de risco (matriz de probabilidade x severidade)."""

    TRIVIAL = "trivial"
    TOLERAVEL = "toleravel"
    MODERADO = "moderado"
    SUBSTANCIAL = "substancial"
    INTOLERAVEL = "intoleravel"


class RiskAgent(StrEnum):
    """Agentes de risco comuns."""

    # Fisicos
    RUIDO = "ruido"
    VIBRACOES = "vibracoes"
    TEMPERATURAS_EXTREMAS = "temperaturas_extremas"
    RADIACAO_IONIZANTE = "radiacao_ionizante"
    RADIACAO_NAO_IONIZANTE = "radiacao_nao_ionizante"
    PRESSOES_ANORMAIS = "pressoes_anormais"
    UMIDADE = "umidade"

    # Quimicos
    POEIRAS = "poeiras"
    FUMOS = "fumos"
    NEVOAS = "nevoas"
    GASES = "gases"
    VAPORES = "vapores"
    PRODUTOS_QUIMICOS = "produtos_quimicos"

    # Biologicos
    VIRUS = "virus"
    BACTERIAS = "bacterias"
    FUNGOS = "fungos"
    PARASITAS = "parasitas"
    BACILOS = "bacilos"

    # Ergonomicos
    POSTURA_INADEQUADA = "postura_inadequada"
    MOVIMENTOS_REPETITIVOS = "movimentos_repetitivos"
    ESFORCO_FISICO_INTENSO = "esforco_fisico_intenso"
    TRABALHO_NOTURNO = "trabalho_noturno"
    MONOTONIA = "monotonia"

    # Acidentes
    ELETRICIDADE = "eletricidade"
    MAQUINAS_EQUIPAMENTOS = "maquinas_equipamentos"
    QUEDAS = "quedas"
    INCENDIO = "incendio"
    ANIMAIS_PECONHENTOS = "animais_peconhentos"


class ControlType(StrEnum):
    """Tipos de medidas de controle."""

    ELIMINACAO = "eliminacao"
    SUBSTITUICAO = "substituicao"
    CONTROLE_ENGENHARIA = "controle_engenharia"
    SINALIZACAO = "sinalizacao"
    CONTROLE_ADMINISTRATIVO = "controle_administrativo"
    EPI = "epi"
    EPC = "epc"


class RiskMapping(Base):
    """
    Mapeamento de Riscos por Setor.

    Representa o mapeamento de riscos ocupacionais de um setor especifico,
    conforme NR-9 (PPRA/PGR).
    """

    __tablename__ = "health_risk_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identificacao do setor
    setor = Column(String(100), nullable=False, index=True)
    descricao_setor = Column(Text, nullable=True)
    localizacao = Column(String(200), nullable=True)

    # Funcoes do setor — funcao (singular) é NOT NULL na tabela; antes não estava mapeada no
    # model, então o INSERT a deixava NULL e violava a constraint.
    funcao = Column(String(100), nullable=False, default="geral")
    funcoes = Column(JSONB, default=list)
    numero_trabalhadores = Column(Integer, nullable=True)

    # Avaliacao
    data_avaliacao = Column(Date, nullable=False, default=date.today)
    avaliador = Column(String(100), nullable=False)
    cargo_avaliador = Column(String(100), nullable=True)

    # Nivel de risco geral do setor
    nivel_risco_geral = Column(String(20), nullable=True)

    # Proxima revisao
    data_proxima_revisao = Column(Date, nullable=True)

    # Status
    ativo = Column(Boolean, default=True)
    versao = Column(Integer, default=1)

    # Auditoria
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)

    # Relacionamentos
    riscos = relationship("OccupationalRisk", back_populates="mapeamento", cascade="all, delete-orphan")
    medidas_controle = relationship("ControlMeasure", back_populates="mapeamento", cascade="all, delete-orphan")

    # Indices
    __table_args__ = (
        Index("idx_mapping_setor_ativo", "setor", "ativo"),
        Index("idx_mapping_data", "data_avaliacao"),
    )

    def __repr__(self) -> str:
        return f"<RiskMapping {self.setor} - {self.data_avaliacao}>"


class OccupationalRisk(Base):
    """
    Risco Ocupacional Identificado.

    Representa um risco especifico identificado no mapeamento.
    """

    __tablename__ = "health_occupational_risks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mapeamento_id = Column(UUID(as_uuid=True), ForeignKey("health_risk_mappings.id"), nullable=False)

    # Identificacao do risco
    categoria = Column(String(20), nullable=False)  # fisico, quimico, etc
    agente = Column(String(50), nullable=False)  # ruido, poeira, etc
    descricao = Column(Text, nullable=True)

    # Fonte geradora
    fonte_geradora = Column(String(200), nullable=False)
    meio_propagacao = Column(String(200), nullable=True)

    # Funcoes expostas
    funcoes_expostas = Column(JSONB, default=list)
    numero_expostos = Column(Integer, nullable=True)
    tempo_exposicao = Column(String(50), nullable=True)  # "8h/dia", "intermitente", etc

    # Avaliacao de risco — tipos alinhados à tabela real (varchar/text), não Integer/Float
    # (a tabela guarda como texto; o mismatch causava "Unknown PG numeric type: 25").
    probabilidade = Column(String(20), nullable=True)  # 1-5
    severidade = Column(String(20), nullable=True)  # 1-5
    nivel_risco = Column(String(20), nullable=True)  # trivial a intoleravel

    # Valores medidos (quando aplicavel)
    valor_medido = Column(Float, nullable=True)
    unidade_medida = Column(String(20), nullable=True)
    limite_tolerancia = Column(String(50), nullable=True)

    # Medidas existentes
    medidas_existentes = Column(JSONB, default=list)

    # EPIs recomendados
    epis_recomendados = Column(JSONB, default=list)

    # Exames medicos relacionados
    exames_requeridos = Column(JSONB, default=list)

    # Prioridade de acao
    prioridade = Column(Integer, default=3)  # 1-5

    # Auditoria
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    mapeamento = relationship("RiskMapping", back_populates="riscos")

    # Indices
    __table_args__ = (
        Index("idx_risk_categoria", "categoria"),
        Index("idx_risk_nivel", "nivel_risco"),
    )

    def __repr__(self) -> str:
        return f"<OccupationalRisk {self.agente} - {self.nivel_risco}>"

    def calcular_nivel_risco(self) -> str:
        """Calcula o nivel de risco baseado em probabilidade x severidade."""
        if not self.probabilidade or not self.severidade:
            return RiskLevel.MODERADO.value

        score = self.probabilidade * self.severidade

        if score <= 2:
            return RiskLevel.TRIVIAL.value
        elif score <= 4:
            return RiskLevel.TOLERAVEL.value
        elif score <= 9:
            return RiskLevel.MODERADO.value
        elif score <= 16:
            return RiskLevel.SUBSTANCIAL.value
        else:
            return RiskLevel.INTOLERAVEL.value


class ControlMeasure(Base):
    """
    Medida de Controle.

    Acoes para eliminacao, reducao ou controle de riscos.
    """

    __tablename__ = "health_control_measures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mapeamento_id = Column(UUID(as_uuid=True), ForeignKey("health_risk_mappings.id"), nullable=False)

    # Identificacao
    tipo = Column(String(30), nullable=False)  # EPI, EPC, administrativo, etc
    descricao = Column(Text, nullable=False)

    # Riscos controlados
    riscos_controlados = Column(JSONB, default=list)  # IDs dos riscos

    # Implementacao
    status = Column(String(20), nullable=False, default="pendente")
    responsavel = Column(String(100), nullable=True)
    data_prevista = Column(Date, nullable=True)
    data_implementacao = Column(Date, nullable=True)

    # Eficacia
    eficaz = Column(Boolean, nullable=True)
    data_verificacao = Column(Date, nullable=True)
    observacoes = Column(Text, nullable=True)

    # Custo estimado
    custo_estimado = Column(Float, nullable=True)

    # Auditoria
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    mapeamento = relationship("RiskMapping", back_populates="medidas_controle")

    def __repr__(self) -> str:
        return f"<ControlMeasure {self.tipo} - {self.status}>"
