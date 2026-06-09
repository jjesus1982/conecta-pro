"""
Model de Visita - Modulo Campo
==============================

Gestao de Visitas Tecnicas e Comerciais.
Utilizado por tecnicos e vendedores para atendimentos externos.
"""

from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, Column, Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, Time
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.models.base import Base

# =============================================================================
# ENUMS
# =============================================================================


class TipoVisita(StrEnum):
    """Tipo de Visita."""

    TECNICA = "tecnica"
    COMERCIAL = "comercial"
    VISTORIA = "vistoria"
    PROSPECCAO = "prospeccao"
    ORCAMENTO = "orcamento"
    DEMONSTRACAO = "demonstracao"
    ASSINATURA_CONTRATO = "assinatura_contrato"
    ACOMPANHAMENTO = "acompanhamento"
    OUTRO = "outro"


class StatusVisita(StrEnum):
    """Status da Visita."""

    RASCUNHO = "rascunho"
    AGENDADA = "agendada"
    CONFIRMADA = "confirmada"
    EM_DESLOCAMENTO = "em_deslocamento"
    REALIZADA = "realizada"
    CANCELADA = "cancelada"
    REAGENDADA = "reagendada"
    NAO_COMPARECEU = "nao_compareceu"


class ResultadoVisita(StrEnum):
    """Resultado da Visita."""

    SUCESSO = "sucesso"
    PARCIAL = "parcial"
    SEM_SUCESSO = "sem_sucesso"
    CLIENTE_AUSENTE = "cliente_ausente"
    ENDERECO_NAO_ENCONTRADO = "endereco_nao_encontrado"
    REAGENDAMENTO = "reagendamento"
    AGUARDANDO_RETORNO = "aguardando_retorno"


class TipoResponsavel(StrEnum):
    """Tipo de responsavel pela visita."""

    TECNICO = "tecnico"
    VENDEDOR = "vendedor"
    SUPERVISOR = "supervisor"
    CONSULTOR = "consultor"


class OrigemVisita(StrEnum):
    """Origem da visita."""

    LEAD = "lead"
    CLIENTE = "cliente"
    INDICACAO = "indicacao"
    PROSPECCAO_ATIVA = "prospeccao_ativa"
    CAMPANHA_MARKETING = "campanha_marketing"
    INTERNA = "interna"


# =============================================================================
# MODEL
# =============================================================================


class Visita(Base):
    """
    Visita Tecnica ou Comercial.

    Gerencia visitas externas de tecnicos e vendedores:
    - Visitas tecnicas para levantamento ou instalacao
    - Visitas comerciais para prospecao e fechamento
    - Acompanhamento pos-venda
    - Demonstracoes de produtos/servicos
    """

    __tablename__ = "visitas"
    __table_args__ = (
        Index("ix_visita_responsavel_data", "responsavel_id", "data_visita"),
        Index("ix_visita_cliente_status", "cliente_id", "status"),
        Index("ix_visita_data", "data_visita"),
        {},
    )

    # =========================================================================
    # Identificacao
    # =========================================================================
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    numero = Column(String(50), unique=True, nullable=False, index=True)
    # Formato: VIS-2026-00001

    # =========================================================================
    # Classificacao
    # =========================================================================
    tipo = Column(Enum(TipoVisita, native_enum=False), nullable=False, default=TipoVisita.COMERCIAL)
    status = Column(Enum(StatusVisita, native_enum=False), nullable=False, default=StatusVisita.AGENDADA, index=True)
    origem = Column(Enum(OrigemVisita, native_enum=False), nullable=False, default=OrigemVisita.LEAD)

    # =========================================================================
    # Responsavel (Tecnico ou Vendedor)
    # =========================================================================
    responsavel_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    responsavel_tipo = Column(
        Enum(TipoResponsavel, native_enum=False), nullable=False, default=TipoResponsavel.VENDEDOR
    )
    responsavel_nome = Column(String(200))  # Cache para relatorios

    # =========================================================================
    # Cliente Existente (se aplicavel)
    # =========================================================================
    cliente_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    contrato_id = Column(UUID(as_uuid=True), nullable=True)

    # =========================================================================
    # Prospect (se nao for cliente existente)
    # =========================================================================
    is_prospect = Column(Boolean, default=False)
    prospect_nome = Column(String(200))
    prospect_empresa = Column(String(200))
    prospect_cargo = Column(String(100))
    prospect_telefone = Column(String(20))
    prospect_celular = Column(String(20))
    prospect_email = Column(String(255))
    prospect_website = Column(String(255))
    prospect_cnpj = Column(String(20))
    prospect_cpf = Column(String(15))

    # Lead/Oportunidade relacionada
    lead_id = Column(UUID(as_uuid=True), nullable=True)
    oportunidade_id = Column(UUID(as_uuid=True), nullable=True)

    # =========================================================================
    # Localizacao
    # =========================================================================
    endereco = Column(String(500), nullable=False)
    endereco_complemento = Column(String(200))
    bairro = Column(String(100))
    cidade = Column(String(100))
    estado = Column(String(2))
    cep = Column(String(10))
    latitude = Column(Numeric(10, 8))
    longitude = Column(Numeric(11, 8))
    ponto_referencia = Column(String(300))

    # =========================================================================
    # Agendamento
    # =========================================================================
    data_visita = Column(Date, nullable=False, index=True)
    horario_inicio = Column(Time, nullable=False)
    horario_fim = Column(Time)
    duracao_prevista_minutos = Column(Integer, default=60)

    # Confirmacao
    confirmada = Column(Boolean, default=False)
    confirmada_at = Column(DateTime)
    confirmada_por = Column(UUID(as_uuid=True), nullable=True)  # quem confirmou (uuid no banco)
    lembrete_enviado = Column(Boolean, default=False)
    lembrete_enviado_at = Column(DateTime)

    # =========================================================================
    # Execucao
    # =========================================================================
    checkin_at = Column(DateTime)
    checkout_at = Column(DateTime)
    checkin_latitude = Column(Numeric(10, 8))
    checkin_longitude = Column(Numeric(11, 8))
    checkout_latitude = Column(Numeric(10, 8))
    checkout_longitude = Column(Numeric(11, 8))

    # Duracao real
    duracao_real_minutos = Column(Integer)
    tempo_deslocamento_minutos = Column(Integer)

    # =========================================================================
    # Resultado
    # =========================================================================
    resultado = Column(Enum(ResultadoVisita, native_enum=False), nullable=True)
    data_resultado = Column(DateTime)

    # Anotacoes
    objetivo = Column(Text)  # Objetivo da visita
    descricao_atendimento = Column(Text)  # O que foi feito
    observacoes = Column(Text)  # Observacoes gerais
    observacoes_internas = Column(Text)  # Notas internas (nao compartilhar)
    proximos_passos = Column(Text)  # Acoes de follow-up

    # =========================================================================
    # Conversao Comercial (para visitas comerciais)
    # =========================================================================
    interesse_nivel = Column(String)  # 1-5 (varchar no banco)
    interesse_servicos = Column(JSONB, default=list)
    # [{servico_id, nome, interesse_nivel}]

    proposta_gerada = Column(Boolean, default=False)
    proposta_id = Column(UUID(as_uuid=True), nullable=True)
    proposta_valor = Column(Numeric(12, 2))

    contrato_fechado = Column(Boolean, default=False)
    contrato_valor = Column(Numeric(12, 2))

    # Motivo de nao fechamento
    motivo_nao_fechamento = Column(String(300))
    concorrente_escolhido = Column(String(200))

    # =========================================================================
    # Levantamento Tecnico (para visitas tecnicas)
    # =========================================================================
    levantamento = Column(JSONB, default=dict)
    # {
    #   "area_m2": 1500,
    #   "pavimentos": 3,
    #   "cameras_existentes": 12,
    #   "pontos_acesso": 4,
    #   "necessidades": ["cameras", "alarme", "portaria"],
    #   "infraestrutura_existente": "parcial",
    #   "observacoes_tecnicas": "..."
    # }

    equipamentos_identificados = Column(JSONB, default=list)
    # [{tipo, quantidade, marca, modelo, estado}]

    necessidades_identificadas = Column(JSONB, default=list)
    # [{categoria, descricao, prioridade, estimativa_valor}]

    # =========================================================================
    # Fotos e Documentos
    # =========================================================================
    fotos = Column(JSONB, default=list)
    # [{url, descricao, tipo, timestamp}]

    documentos = Column(JSONB, default=list)
    # [{url, nome, tipo, timestamp}]

    # =========================================================================
    # Reagendamento
    # =========================================================================
    reagendamentos = Column(Integer, default=0)
    ultimo_reagendamento_motivo = Column(String(300))
    ultimo_reagendamento_data = Column(DateTime)
    visita_origem_id = Column(UUID(as_uuid=True), ForeignKey("visitas.id"), nullable=True)

    # =========================================================================
    # Cancelamento
    # =========================================================================
    cancelada_por = Column(UUID(as_uuid=True), nullable=True)
    cancelada_at = Column(DateTime)
    motivo_cancelamento = Column(String(300))

    # =========================================================================
    # Follow-up
    # =========================================================================
    followup_agendado = Column(Boolean, default=False)
    followup_data = Column(DateTime)  # timestamp no banco
    followup_tipo = Column(String(50))  # "ligacao", "email", "visita", "reuniao"
    followup_observacoes = Column(Text)

    # =========================================================================
    # Integracao
    # =========================================================================
    crm_sync = Column(Boolean, default=False)
    crm_sync_at = Column(DateTime)
    external_id = Column(String(100))  # ID em sistema externo

    # =========================================================================
    # Metadata
    # =========================================================================
    tags = Column(JSONB, default=list)
    extra_metadata = Column(JSONB, default=dict)

    # Auditoria
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)

    # =========================================================================
    # Relacionamentos
    # =========================================================================
    # cliente = relationship("Client", back_populates="visitas")
    # lead = relationship("Lead", back_populates="visitas")
    # oportunidade = relationship("Opportunity", back_populates="visitas")
    # proposta = relationship("Proposal", back_populates="visitas")

    # =========================================================================
    # Propriedades
    # =========================================================================
    @property
    def is_agendada(self) -> bool:
        """Verifica se visita esta agendada."""
        return self.status in [StatusVisita.AGENDADA, StatusVisita.CONFIRMADA]

    @property
    def is_realizada(self) -> bool:
        """Verifica se visita foi realizada."""
        return self.status == StatusVisita.REALIZADA

    @property
    def is_finalizada(self) -> bool:
        """Verifica se visita foi finalizada (realizada ou cancelada)."""
        return self.status in [StatusVisita.REALIZADA, StatusVisita.CANCELADA, StatusVisita.NAO_COMPARECEU]

    @property
    def is_comercial(self) -> bool:
        """Verifica se e visita comercial."""
        return self.tipo in [TipoVisita.COMERCIAL, TipoVisita.PROSPECCAO, TipoVisita.ORCAMENTO]

    @property
    def is_tecnica(self) -> bool:
        """Verifica se e visita tecnica."""
        return self.tipo in [TipoVisita.TECNICA, TipoVisita.VISTORIA]

    @property
    def nome_contato(self) -> str:
        """Retorna nome do contato (cliente ou prospect)."""
        if self.is_prospect:
            return self.prospect_nome or "Prospect"
        return "Cliente"  # Seria substituido pelo nome real via relacionamento

    @property
    def teve_conversao(self) -> bool:
        """Verifica se houve conversao (proposta ou contrato)."""
        return self.proposta_gerada or self.contrato_fechado

    # =========================================================================
    # Metodos
    # =========================================================================
    def gerar_numero(self, sequencial: int) -> str:
        """Gera numero da visita no formato VIS-YYYY-NNNNN."""
        ano = datetime.utcnow().year
        self.numero = f"VIS-{ano}-{sequencial:05d}"
        return self.numero

    def confirmar(self, confirmado_por: str = None):
        """Confirma a visita."""
        self.status = StatusVisita.CONFIRMADA
        self.confirmada = True
        self.confirmada_at = datetime.utcnow()
        self.confirmada_por = confirmado_por

    def iniciar_deslocamento(self):
        """Marca inicio do deslocamento."""
        self.status = StatusVisita.EM_DESLOCAMENTO

    def fazer_checkin(self, latitude: float = None, longitude: float = None):
        """Registra chegada no local."""
        self.checkin_at = datetime.utcnow()
        if latitude:
            self.checkin_latitude = Decimal(str(latitude))
        if longitude:
            self.checkin_longitude = Decimal(str(longitude))

    def fazer_checkout(self, latitude: float = None, longitude: float = None):
        """Registra saida do local."""
        self.checkout_at = datetime.utcnow()
        if latitude:
            self.checkout_latitude = Decimal(str(latitude))
        if longitude:
            self.checkout_longitude = Decimal(str(longitude))
        # Calcular duracao
        if self.checkin_at:
            delta = self.checkout_at - self.checkin_at
            self.duracao_real_minutos = int(delta.total_seconds() / 60)

    def registrar_resultado(self, resultado: ResultadoVisita, descricao: str = None, proximos_passos: str = None):
        """Registra resultado da visita."""
        self.status = StatusVisita.REALIZADA
        self.resultado = resultado
        self.data_resultado = datetime.utcnow()
        if descricao:
            self.descricao_atendimento = descricao
        if proximos_passos:
            self.proximos_passos = proximos_passos

    def cancelar(self, motivo: str, cancelado_por: str):
        """Cancela a visita."""
        self.status = StatusVisita.CANCELADA
        self.motivo_cancelamento = motivo
        self.cancelada_por = cancelado_por
        self.cancelada_at = datetime.utcnow()

    def reagendar(self, nova_data: date, novo_horario: time, motivo: str):
        """Reagenda a visita."""
        self.status = StatusVisita.REAGENDADA
        self.data_visita = nova_data
        self.horario_inicio = novo_horario
        self.reagendamentos += 1
        self.ultimo_reagendamento_motivo = motivo
        self.ultimo_reagendamento_data = datetime.utcnow()
        # Resetar confirmacao
        self.confirmada = False
        self.confirmada_at = None

    def registrar_interesse(self, nivel: int, servicos: list = None):
        """Registra nivel de interesse do prospect/cliente."""
        self.interesse_nivel = nivel
        if servicos:
            self.interesse_servicos = servicos

    def gerar_proposta(self, proposta_id: str, valor: Decimal):
        """Vincula proposta gerada a partir da visita."""
        self.proposta_gerada = True
        self.proposta_id = proposta_id
        self.proposta_valor = valor

    def fechar_contrato(self, contrato_id: str, valor: Decimal):
        """Registra fechamento de contrato."""
        self.contrato_fechado = True
        self.contrato_id = contrato_id
        self.contrato_valor = valor

    def registrar_nao_fechamento(self, motivo: str, concorrente: str = None):
        """Registra motivo de nao fechamento."""
        self.motivo_nao_fechamento = motivo
        if concorrente:
            self.concorrente_escolhido = concorrente

    def agendar_followup(self, data: date, tipo: str, observacoes: str = None):
        """Agenda follow-up."""
        self.followup_agendado = True
        self.followup_data = data
        self.followup_tipo = tipo
        self.followup_observacoes = observacoes

    def adicionar_foto(self, url: str, descricao: str = None, tipo: str = "geral"):
        """Adiciona foto a visita."""
        foto = {"url": url, "descricao": descricao, "tipo": tipo, "timestamp": datetime.utcnow().isoformat()}
        if not self.fotos:
            self.fotos = []
        self.fotos.append(foto)

    def adicionar_levantamento(self, dados: dict):
        """Adiciona dados de levantamento tecnico."""
        if not self.levantamento:
            self.levantamento = {}
        self.levantamento.update(dados)

    def adicionar_necessidade(self, categoria: str, descricao: str, prioridade: int = 3, estimativa: Decimal = None):
        """Adiciona necessidade identificada."""
        necessidade = {
            "categoria": categoria,
            "descricao": descricao,
            "prioridade": prioridade,
            "estimativa_valor": float(estimativa) if estimativa else None,
            "timestamp": datetime.utcnow().isoformat(),
        }
        if not self.necessidades_identificadas:
            self.necessidades_identificadas = []
        self.necessidades_identificadas.append(necessidade)

    def __repr__(self) -> str:
        return f"<Visita {self.numero} - {self.tipo.value} - {self.status.value}>"
