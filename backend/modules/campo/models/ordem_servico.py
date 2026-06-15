"""
Model de Ordem de Servico (OS) - Modulo Campo
==============================================

Gestao de Ordens de Servico para equipes externas.
Estilo Auvo: Instalacoes, Manutencoes, Visitas Tecnicas, Suporte.
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


class TipoOS(StrEnum):
    """Tipo de Ordem de Servico."""

    INSTALACAO = "instalacao"
    MANUTENCAO_PREVENTIVA = "manutencao_preventiva"
    MANUTENCAO_CORRETIVA = "manutencao_corretiva"
    VISITA_TECNICA = "visita_tecnica"
    VISITA_COMERCIAL = "visita_comercial"
    VISTORIA = "vistoria"
    SUPORTE = "suporte"
    RETIRADA = "retirada"
    TROCA = "troca"
    ATIVACAO = "ativacao"
    DESATIVACAO = "desativacao"
    OUTRO = "outro"


class StatusOS(StrEnum):
    """Status da Ordem de Servico."""

    RASCUNHO = "rascunho"
    ABERTA = "aberta"
    AGENDADA = "agendada"
    AGUARDANDO_PECA = "aguardando_peca"
    AGUARDANDO_CLIENTE = "aguardando_cliente"
    EM_DESLOCAMENTO = "em_deslocamento"
    EM_ANDAMENTO = "em_andamento"
    PAUSADA = "pausada"
    CONCLUIDA = "concluida"
    CANCELADA = "cancelada"
    REAGENDADA = "reagendada"


class PrioridadeOS(StrEnum):
    """Prioridade da OS."""

    BAIXA = "baixa"
    NORMAL = "normal"
    ALTA = "alta"
    URGENTE = "urgente"
    EMERGENCIA = "emergencia"


class OrigemOS(StrEnum):
    """Origem da solicitacao."""

    CLIENTE = "cliente"
    CONTRATO = "contrato"
    PREVENTIVA = "preventiva"
    MONITORAMENTO = "monitoramento"
    COMERCIAL = "comercial"
    INTERNA = "interna"


# =============================================================================
# MODEL
# =============================================================================


class OrdemServico(Base):
    """
    Ordem de Servico para equipes de campo.

    Gerencia todo o ciclo de vida de um atendimento:
    - Abertura e agendamento
    - Atribuicao de tecnico
    - Execucao com checklist
    - Materiais e custos
    - Avaliacao do cliente
    """

    __tablename__ = "ordens_servico"
    __table_args__ = (
        Index("ix_os_cliente_status", "cliente_id", "status"),
        Index("ix_os_tecnico_data", "tecnico_id", "data_agendada"),
        Index("ix_os_contrato", "contrato_id"),
        Index("ix_os_numero", "numero"),
        {},
    )

    # =========================================================================
    # Identificacao
    # =========================================================================
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    numero = Column(String(50), unique=True, nullable=False, index=True)
    # Formato: OS-2026-00001

    # =========================================================================
    # Classificacao
    # =========================================================================
    # native_enum=False: as colunas são varchar(50) no banco (não existe tipo PG statusos/
    # tipoos/etc). Sem isto o SQLAlchemy emite cast ::statusos e qualquer filtro/dashboard
    # dá 500. Continua persistindo/lendo pelo NOME do membro (ex.: 'ABERTA').
    tipo = Column(Enum(TipoOS, native_enum=False, length=50), nullable=False, default=TipoOS.MANUTENCAO_CORRETIVA)
    status = Column(Enum(StatusOS, native_enum=False, length=50), nullable=False, default=StatusOS.ABERTA, index=True)
    prioridade = Column(Enum(PrioridadeOS, native_enum=False, length=50), nullable=False, default=PrioridadeOS.NORMAL)
    origem = Column(Enum(OrigemOS, native_enum=False, length=50), nullable=False, default=OrigemOS.CLIENTE)

    # =========================================================================
    # Cliente e Contrato
    # =========================================================================
    # FK a nível de ORM removida (a tabela referenciada vive em outro módulo/schema e nem
    # sempre está no metadata na hora do flush -> NoReferencedTableError quebrava agendar/
    # concluir/cancelar). Colunas + índices mantidos; integridade fica no constraint do banco.
    cliente_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    contrato_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Contato no local
    contato_nome = Column(String(200))
    contato_telefone = Column(String(20))
    contato_email = Column(String(255))

    # =========================================================================
    # Localizacao
    # =========================================================================
    endereco_servico = Column(String(500), nullable=False)
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
    data_abertura = Column(DateTime, nullable=False, default=datetime.utcnow)
    data_agendada = Column(Date, index=True)
    horario_inicio_previsto = Column(Time)
    horario_fim_previsto = Column(Time)
    duracao_estimada_minutos = Column(Integer, default=60)
    janela_atendimento = Column(String(50))  # Ex: "08:00-12:00", "tarde"

    # =========================================================================
    # Execucao
    # =========================================================================
    tecnico_id = Column(UUID(as_uuid=True), ForeignKey("public.campo_tecnicos.id"), nullable=True, index=True)
    tecnico_auxiliar_id = Column(UUID(as_uuid=True), ForeignKey("public.campo_tecnicos.id"), nullable=True)

    # Timestamps de execucao
    data_inicio_deslocamento = Column(DateTime)
    data_chegada = Column(DateTime)
    checkin_at = Column(DateTime)
    checkout_at = Column(DateTime)
    data_conclusao = Column(DateTime)

    # Geolocalizacao do check-in/out
    checkin_latitude = Column(Numeric(10, 8))
    checkin_longitude = Column(Numeric(11, 8))
    checkout_latitude = Column(Numeric(10, 8))
    checkout_longitude = Column(Numeric(11, 8))

    # Duracao real
    tempo_deslocamento_minutos = Column(Integer)
    tempo_execucao_minutos = Column(Integer)
    tempo_total_minutos = Column(Integer)

    # =========================================================================
    # Descricao do Servico
    # =========================================================================
    titulo = Column(String(300))
    descricao = Column(Text)
    problema_relatado = Column(Text)
    solucao_aplicada = Column(Text)
    observacoes_internas = Column(Text)
    instrucoes_cliente = Column(Text)

    # =========================================================================
    # Equipamentos (se aplicavel)
    # =========================================================================
    equipamento_id = Column(UUID(as_uuid=True), nullable=True)  # FK ORM removida (ver cliente_id)
    equipamento_tipo = Column(String(100))
    equipamento_modelo = Column(String(100))
    equipamento_serie = Column(String(100))
    equipamentos_relacionados = Column(JSONB, default=list)
    # Lista de IDs de equipamentos envolvidos

    # =========================================================================
    # Checklist
    # =========================================================================
    checklist_template_id = Column(UUID(as_uuid=True), nullable=True)
    checklist_respostas = Column(JSONB, default=dict)
    checklist_concluido = Column(Boolean, default=False)
    checklist_concluido_at = Column(DateTime)

    # =========================================================================
    # Materiais
    # =========================================================================
    materiais_previstos = Column(JSONB, default=list)
    # [{id, nome, quantidade, valor_unitario}]
    materiais_utilizados = Column(JSONB, default=list)
    # [{id, nome, quantidade, valor_unitario, baixa_estoque}]
    materiais_adicionais = Column(JSONB, default=list)
    # Materiais nao previstos que foram usados

    # =========================================================================
    # Financeiro
    # =========================================================================
    valor_mao_obra = Column(Numeric(10, 2), default=Decimal("0.00"))
    valor_materiais = Column(Numeric(10, 2), default=Decimal("0.00"))
    valor_deslocamento = Column(Numeric(10, 2), default=Decimal("0.00"))
    valor_adicional = Column(Numeric(10, 2), default=Decimal("0.00"))
    descricao_adicional = Column(String(300))
    valor_desconto = Column(Numeric(10, 2), default=Decimal("0.00"))
    motivo_desconto = Column(String(300))
    valor_total = Column(Numeric(10, 2), default=Decimal("0.00"))

    # Cobranca
    is_cobrado = Column(Boolean, default=True)
    is_garantia = Column(Boolean, default=False)
    is_cortesia = Column(Boolean, default=False)
    motivo_isencao = Column(String(300))

    # Faturamento
    faturado = Column(Boolean, default=False)
    fatura_id = Column(UUID(as_uuid=True), nullable=True)
    data_faturamento = Column(Date)

    # =========================================================================
    # Avaliacao do Cliente
    # =========================================================================
    avaliacao_nota = Column(Integer)  # 1-5
    avaliacao_comentario = Column(Text)
    avaliacao_data = Column(DateTime)
    avaliacao_enviada = Column(Boolean, default=False)
    avaliacao_link = Column(String(500))

    # =========================================================================
    # Assinatura Digital
    # =========================================================================
    assinatura_cliente_url = Column(String(500))
    assinatura_cliente_nome = Column(String(200))
    assinatura_cliente_documento = Column(String(20))
    assinatura_data = Column(DateTime)

    # =========================================================================
    # Fotos e Documentos
    # =========================================================================
    fotos_antes = Column(JSONB, default=list)
    # [{url, descricao, timestamp}]
    fotos_durante = Column(JSONB, default=list)
    fotos_depois = Column(JSONB, default=list)
    documentos = Column(JSONB, default=list)
    # [{url, nome, tipo, timestamp}]

    # =========================================================================
    # Reagendamento
    # =========================================================================
    reagendamentos = Column(Integer, default=0)
    ultimo_reagendamento_motivo = Column(String(300))
    ultimo_reagendamento_data = Column(DateTime)
    os_origem_id = Column(UUID(as_uuid=True), ForeignKey("ordens_servico.id"), nullable=True)
    # Se for reagendamento, referencia a OS original

    # =========================================================================
    # Cancelamento
    # =========================================================================
    cancelada_por = Column(UUID(as_uuid=True), nullable=True)
    cancelada_at = Column(DateTime)
    motivo_cancelamento = Column(Text)

    # =========================================================================
    # SLA
    # =========================================================================
    sla_horas = Column(Integer)  # Tempo maximo para atendimento
    sla_vencimento = Column(DateTime)
    sla_cumprido = Column(Boolean)
    sla_tempo_resposta_minutos = Column(Integer)

    # =========================================================================
    # Integracao
    # =========================================================================
    ticket_origem_id = Column(String(100))  # ID do ticket que gerou a OS
    ticket_sistema = Column(String(50))  # Sistema de origem (helpdesk, etc)

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
    # tecnico = relationship("CampoTecnico", foreign_keys=[tecnico_id], back_populates="ordens_servico")
    # cliente = relationship("Client", back_populates="ordens_servico")
    # contrato = relationship("Contract", back_populates="ordens_servico")

    # =========================================================================
    # Propriedades
    # =========================================================================
    @property
    def is_aberta(self) -> bool:
        """Verifica se OS esta aberta."""
        return self.status in [
            StatusOS.ABERTA,
            StatusOS.AGENDADA,
            StatusOS.AGUARDANDO_PECA,
            StatusOS.AGUARDANDO_CLIENTE,
        ]

    @property
    def is_em_execucao(self) -> bool:
        """Verifica se OS esta em execucao."""
        return self.status in [StatusOS.EM_DESLOCAMENTO, StatusOS.EM_ANDAMENTO, StatusOS.PAUSADA]

    @property
    def is_finalizada(self) -> bool:
        """Verifica se OS foi finalizada."""
        return self.status in [StatusOS.CONCLUIDA, StatusOS.CANCELADA]

    @property
    def is_atrasada(self) -> bool:
        """Verifica se OS esta atrasada (SLA vencido)."""
        if self.sla_vencimento and not self.is_finalizada:
            return datetime.utcnow() > self.sla_vencimento
        return False

    @property
    def pode_iniciar(self) -> bool:
        """Verifica se OS pode ser iniciada."""
        return self.status == StatusOS.AGENDADA and self.tecnico_id is not None

    @property
    def tempo_em_campo_minutos(self) -> int | None:
        """Calcula tempo em campo (checkin ate checkout)."""
        if self.checkin_at and self.checkout_at:
            delta = self.checkout_at - self.checkin_at
            return int(delta.total_seconds() / 60)
        return None

    # =========================================================================
    # Metodos
    # =========================================================================
    def gerar_numero(self, sequencial: int) -> str:
        """Gera numero da OS no formato OS-YYYY-NNNNN."""
        ano = datetime.utcnow().year
        self.numero = f"OS-{ano}-{sequencial:05d}"
        return self.numero

    def agendar(self, data: date, horario_inicio: time, horario_fim: time = None, tecnico_id: str = None):
        """Agenda a OS."""
        self.data_agendada = data
        self.horario_inicio_previsto = horario_inicio
        self.horario_fim_previsto = horario_fim
        if tecnico_id:
            self.tecnico_id = tecnico_id
        self.status = StatusOS.AGENDADA

    def iniciar_deslocamento(self):
        """Marca inicio do deslocamento."""
        self.status = StatusOS.EM_DESLOCAMENTO
        self.data_inicio_deslocamento = datetime.utcnow()

    def fazer_checkin(self, latitude: float = None, longitude: float = None):
        """Registra chegada no local."""
        self.status = StatusOS.EM_ANDAMENTO
        self.checkin_at = datetime.utcnow()
        self.data_chegada = self.checkin_at
        if latitude:
            self.checkin_latitude = Decimal(str(latitude))
        if longitude:
            self.checkin_longitude = Decimal(str(longitude))
        # Calcular tempo de deslocamento
        if self.data_inicio_deslocamento:
            delta = self.checkin_at - self.data_inicio_deslocamento
            self.tempo_deslocamento_minutos = int(delta.total_seconds() / 60)

    def fazer_checkout(self, latitude: float = None, longitude: float = None):
        """Registra saida do local."""
        self.checkout_at = datetime.utcnow()
        if latitude:
            self.checkout_latitude = Decimal(str(latitude))
        if longitude:
            self.checkout_longitude = Decimal(str(longitude))
        # Calcular tempo de execucao
        if self.checkin_at:
            delta = self.checkout_at - self.checkin_at
            self.tempo_execucao_minutos = int(delta.total_seconds() / 60)
        # Calcular tempo total
        if self.tempo_deslocamento_minutos:
            self.tempo_total_minutos = (self.tempo_deslocamento_minutos or 0) + (self.tempo_execucao_minutos or 0)
        else:
            self.tempo_total_minutos = self.tempo_execucao_minutos

    def pausar(self, motivo: str = None):
        """Pausa a OS."""
        self.status = StatusOS.PAUSADA
        if motivo:
            self.observacoes_internas = (self.observacoes_internas or "") + f"\n[PAUSA] {motivo}"

    def retomar(self):
        """Retoma OS pausada."""
        self.status = StatusOS.EM_ANDAMENTO

    def concluir(self, solucao: str = None):
        """Conclui a OS."""
        self.status = StatusOS.CONCLUIDA
        self.data_conclusao = datetime.utcnow()
        if solucao:
            self.solucao_aplicada = solucao
        # Verificar SLA
        if self.sla_vencimento:
            self.sla_cumprido = self.data_conclusao <= self.sla_vencimento

    def cancelar(self, motivo: str, cancelado_por: str):
        """Cancela a OS."""
        self.status = StatusOS.CANCELADA
        self.motivo_cancelamento = motivo
        self.cancelada_por = cancelado_por
        self.cancelada_at = datetime.utcnow()

    def reagendar(self, nova_data: date, motivo: str):
        """Reagenda a OS."""
        self.status = StatusOS.REAGENDADA
        self.data_agendada = nova_data
        self.reagendamentos += 1
        self.ultimo_reagendamento_motivo = motivo
        self.ultimo_reagendamento_data = datetime.utcnow()

    def calcular_valores(self):
        """Calcula valor total da OS."""
        self.valor_total = (
            (self.valor_mao_obra or Decimal("0.00"))
            + (self.valor_materiais or Decimal("0.00"))
            + (self.valor_deslocamento or Decimal("0.00"))
            + (self.valor_adicional or Decimal("0.00"))
            - (self.valor_desconto or Decimal("0.00"))
        )
        return self.valor_total

    def registrar_avaliacao(self, nota: int, comentario: str = None):
        """Registra avaliacao do cliente."""
        self.avaliacao_nota = nota
        self.avaliacao_comentario = comentario
        self.avaliacao_data = datetime.utcnow()

    def registrar_assinatura(self, url: str, nome: str, documento: str = None):
        """Registra assinatura digital do cliente."""
        self.assinatura_cliente_url = url
        self.assinatura_cliente_nome = nome
        self.assinatura_cliente_documento = documento
        self.assinatura_data = datetime.utcnow()

    def adicionar_foto(self, tipo: str, url: str, descricao: str = None):
        """Adiciona foto a OS (antes, durante, depois)."""
        foto = {"url": url, "descricao": descricao, "timestamp": datetime.utcnow().isoformat()}
        if tipo == "antes":
            if not self.fotos_antes:
                self.fotos_antes = []
            self.fotos_antes.append(foto)
        elif tipo == "durante":
            if not self.fotos_durante:
                self.fotos_durante = []
            self.fotos_durante.append(foto)
        elif tipo == "depois":
            if not self.fotos_depois:
                self.fotos_depois = []
            self.fotos_depois.append(foto)

    def definir_sla(self, horas: int):
        """Define SLA para a OS."""
        self.sla_horas = horas
        self.sla_vencimento = datetime.utcnow() + timedelta(hours=horas)

    def __repr__(self) -> str:
        return f"<OrdemServico {self.numero} - {self.status.value}>"


# Importar timedelta para o metodo definir_sla
from datetime import timedelta  # noqa: E402
