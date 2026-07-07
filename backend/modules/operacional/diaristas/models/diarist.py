"""Models de Diaristas."""

from datetime import date, datetime, time
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from core.models.base import Base


class DiaristType(StrEnum):
    """Tipos de diarista."""

    LIMPEZA = "limpeza"
    FAXINA = "faxina"
    JARDINAGEM = "jardinagem"
    MANUTENCAO = "manutencao"
    COZINHA = "cozinha"
    PASSADEIRA = "passadeira"
    CUIDADOR = "cuidador"
    BABA = "baba"
    MOTORISTA = "motorista"
    OUTRO = "outro"


class DiaristStatus(StrEnum):
    """Status do diarista."""

    ATIVO = "ativo"
    INATIVO = "inativo"
    SUSPENSO = "suspenso"
    BLOQUEADO = "bloqueado"
    FERIAS = "ferias"
    AFASTADO = "afastado"
    DESLIGADO = "desligado"


class DocumentType(StrEnum):
    """Tipos de documento."""

    CPF = "cpf"
    RG = "rg"
    CNH = "cnh"
    CTPS = "ctps"
    PIS = "pis"
    TITULO_ELEITOR = "titulo_eleitor"
    RESERVISTA = "reservista"
    PASSAPORTE = "passaporte"


class AssignmentType(StrEnum):
    """Tipos de alocacao. Valores uppercase para alinhar com PG ENUM assignment_type."""

    CONDOMINIO = "CONDOMINIO"
    UNIDADE = "UNIDADE"
    AREA_COMUM = "AREA_COMUM"


class AssignmentStatus(StrEnum):
    """Status da alocacao. Valores uppercase para alinhar com PG ENUM assignment_status."""

    ATIVO = "ATIVO"
    PAUSADO = "PAUSADO"
    ENCERRADO = "ENCERRADO"
    CANCELADO = "CANCELADO"


class RecurrenceType(StrEnum):
    """Tipos de recorrencia. Valores uppercase para alinhar com PG ENUM recurrence_type."""

    AVULSO = "AVULSO"
    SEMANAL = "SEMANAL"
    QUINZENAL = "QUINZENAL"
    MENSAL = "MENSAL"


class ScheduleStatus(StrEnum):
    """Status da agenda. Valores uppercase para alinhar com PG ENUM schedule_status."""

    AGENDADO = "AGENDADO"
    CONFIRMADO = "CONFIRMADO"
    EM_ANDAMENTO = "EM_ANDAMENTO"
    CONCLUIDO = "CONCLUIDO"
    CANCELADO = "CANCELADO"
    NAO_COMPARECEU = "NAO_COMPARECEU"


class PaymentStatus(StrEnum):
    """Status do pagamento. Valores uppercase para alinhar com PG ENUM payment_status."""

    PENDENTE = "PENDENTE"
    APROVADO = "APROVADO"
    PAGO = "PAGO"
    CANCELADO = "CANCELADO"
    ESTORNADO = "ESTORNADO"


class PaymentMethod(StrEnum):
    """Metodos de pagamento."""

    DINHEIRO = "dinheiro"
    PIX = "pix"
    TRANSFERENCIA = "transferencia"
    DEPOSITO = "deposito"
    CHEQUE = "cheque"
    CARTAO = "cartao"


class Weekday(StrEnum):
    """Dias da semana."""

    SEGUNDA = "segunda"
    TERCA = "terca"
    QUARTA = "quarta"
    QUINTA = "quinta"
    SEXTA = "sexta"
    SABADO = "sabado"
    DOMINGO = "domingo"


class Diarist(Base):
    """Model de Diarista."""

    __tablename__ = "diarists"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ativo = Column(Boolean, default=True, nullable=False)

    # Dados pessoais
    nome = Column(String(200), nullable=False)
    cpf = Column(String(14), nullable=False, index=True)
    rg = Column(String(20))
    data_nascimento = Column(Date)

    # Contato
    telefone = Column(String(20))
    telefone_emergencia = Column(String(20))
    email = Column(String(255))
    foto_url = Column(String(500))

    # Endereco
    endereco = Column(String(500))
    cidade = Column(String(100))
    estado = Column(String(2))
    cep = Column(String(10))

    # Profissional
    tipos_servico = Column(ARRAY(String), default=[])  # Array de tipos (diarist_type_array[] no banco)
    especialidades = Column(ARRAY(String), default=[])  # Array de strings
    experiencia_anos = Column(Integer, default=0)
    referencias = Column(JSONB, default=dict)  # JSONB
    documentos = Column(JSONB, default=dict)  # JSONB

    # Disponibilidade
    dias_disponiveis = Column(ARRAY(String), default=[])  # Array de weekday (weekday_array[] no banco)
    hora_inicio_disponivel = Column(Time, default=time(8, 0))
    hora_fim_disponivel = Column(Time, default=time(17, 0))
    aceita_hora_extra = Column(Boolean, default=True)

    # Financeiro
    valor_hora = Column(Numeric(10, 2))
    valor_diaria = Column(Numeric(10, 2), nullable=False, default=150.00)
    valor_hora_extra = Column(Numeric(10, 2), default=25.00)

    # Dados bancarios
    banco = Column(String(100))
    agencia = Column(String(20))
    conta = Column(String(30))
    tipo_conta = Column(String(20))
    pix = Column(String(100))

    # Status
    status = Column(String(30), nullable=False, default=DiaristStatus.ATIVO.value, index=True)

    # Metricas
    avaliacao_media = Column(Numeric(3, 2), default=0)
    total_avaliacoes = Column(Integer, default=0)
    total_servicos = Column(Integer, default=0)

    # Relacionamentos
    assignments = relationship("DiaristAssignment", back_populates="diarist")
    schedules = relationship("DiaristSchedule", back_populates="diarist")
    payments = relationship("DiaristPayment", back_populates="diarist")
    evaluations = relationship("DiaristEvaluation", back_populates="diarist")

    @property
    def is_ativo(self) -> bool:
        """Verifica se diarista esta ativo."""
        return self.status == DiaristStatus.ATIVO.value and self.ativo

    @property
    def is_disponivel(self) -> bool:
        """Verifica se diarista esta disponivel."""
        return self.is_ativo and self.status not in [
            DiaristStatus.FERIAS.value,
            DiaristStatus.AFASTADO.value,
        ]

    @property
    def idade(self) -> int | None:
        """Calcula idade."""
        if not self.data_nascimento:
            return None
        today = date.today()
        return (
            today.year
            - self.data_nascimento.year
            - ((today.month, today.day) < (self.data_nascimento.month, self.data_nascimento.day))
        )

    def ativar(self) -> None:
        """Ativa diarista."""
        self.status = DiaristStatus.ATIVO.value
        self.ativo = True

    def inativar(self) -> None:
        """Inativa diarista."""
        self.status = DiaristStatus.INATIVO.value
        self.ativo = False

    def suspender(self) -> None:
        """Suspende diarista."""
        self.status = DiaristStatus.SUSPENSO.value

    def bloquear(self) -> None:
        """Bloqueia diarista."""
        self.status = DiaristStatus.BLOQUEADO.value

    def desbloquear(self) -> None:
        """Desbloqueia diarista."""
        self.status = DiaristStatus.ATIVO.value

    def iniciar_ferias(self) -> None:
        """Inicia periodo de ferias."""
        self.status = DiaristStatus.FERIAS.value

    def afastar(self) -> None:
        """Afasta diarista."""
        self.status = DiaristStatus.AFASTADO.value

    def desligar(self) -> None:
        """Desliga diarista."""
        self.status = DiaristStatus.DESLIGADO.value
        self.ativo = False

    def atualizar_metricas(self, servicos: int = 1) -> None:
        """Atualiza metricas."""
        self.total_servicos = (self.total_servicos or 0) + servicos

    def atualizar_avaliacao(self, nota: float) -> None:
        """Atualiza media de avaliacao."""
        total = self.total_avaliacoes or 0
        media = float(self.avaliacao_media or 0)
        nova_media = ((media * total) + nota) / (total + 1)
        self.avaliacao_media = round(nova_media, 2)
        self.total_avaliacoes = total + 1


class DiaristAssignment(Base):
    """Model de Alocacao de Diarista.

    Alinhado com a tabela real diarist_assignments no PostgreSQL.
    Colunas reais: id, created_at, updated_at, ativo, diarist_id, condominio_id,
    unidade_id, tipo, descricao, data_inicio, data_fim, recorrencia, dias_semana,
    hora_inicio, hora_fim, valor_acordado, status, observacoes
    """

    __tablename__ = "diarist_assignments"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ativo = Column(Boolean, default=True, nullable=False)

    diarist_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("diarists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    condominio_id = Column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    unidade_id = Column(PG_UUID(as_uuid=True))

    # Tipo e status
    tipo = Column(String(30), nullable=False, default=AssignmentType.CONDOMINIO.value, index=True)
    status = Column(String(30), nullable=False, default=AssignmentStatus.ATIVO.value, index=True)

    # Servico
    descricao = Column(Text)

    # Periodo
    data_inicio = Column(Date, nullable=False)
    data_fim = Column(Date)
    hora_inicio = Column(Time, default=time(8, 0))
    hora_fim = Column(Time, default=time(17, 0))

    # Recorrencia
    recorrencia = Column(String(30), nullable=False, default=RecurrenceType.AVULSO.value)
    dias_semana = Column(JSONB, default=list)

    # Financeiro
    valor_acordado = Column(Numeric(10, 2), nullable=False)

    # Observacoes
    observacoes = Column(Text)

    # Relacionamentos
    diarist = relationship("Diarist", back_populates="assignments")
    schedules = relationship("DiaristSchedule", back_populates="assignment")

    __table_args__ = (Index("ix_diarist_assignments_periodo", "data_inicio", "data_fim"),)

    @property
    def is_ativo(self) -> bool:
        """Verifica se alocacao esta ativa."""
        return self.status == AssignmentStatus.ATIVO.value

    @property
    def is_recorrente(self) -> bool:
        """Verifica se e recorrente."""
        return self.recorrencia != RecurrenceType.AVULSO.value

    @property
    def dias_restantes(self) -> int | None:
        """Calcula dias restantes."""
        if not self.data_fim:
            return None
        return (self.data_fim - date.today()).days

    def confirmar(self) -> None:
        """Confirma alocacao (torna ativa)."""
        self.status = AssignmentStatus.ATIVO.value

    def iniciar(self) -> None:
        """Inicia alocacao (torna ativa)."""
        self.status = AssignmentStatus.ATIVO.value

    def concluir(self) -> None:
        """Conclui alocacao (encerra)."""
        self.status = AssignmentStatus.ENCERRADO.value

    def cancelar(self, motivo: str, cancelado_por: str) -> None:
        """Cancela alocacao."""
        self.status = AssignmentStatus.CANCELADO.value
        self.motivo_cancelamento = motivo
        self.cancelado_por = UUID(cancelado_por)
        self.cancelado_at = datetime.utcnow()

    def suspender(self) -> None:
        """Suspende alocacao (pausa)."""
        self.status = AssignmentStatus.PAUSADO.value

    def aprovar(self, aprovador_id: str) -> None:
        """Aprova alocacao (torna ativa)."""
        self.aprovador_id = UUID(aprovador_id)
        self.aprovado_at = datetime.utcnow()
        self.status = AssignmentStatus.ATIVO.value

    def calcular_valor_total(self) -> None:
        """Calcula valor total."""
        base = float(self.valor_acordado or 0)
        adicional = float(self.valor_adicional or 0)
        desconto = float(self.desconto or 0)
        self.valor_total = base + adicional - desconto


class DiaristSchedule(Base):
    """Model de Agenda de Diarista.

    Mapeado para a tabela real do banco com colunas existentes.
    """

    __tablename__ = "diarist_schedules"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ativo = Column(Boolean, default=True, nullable=False)

    diarist_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("diarists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assignment_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("diarist_assignments.id", ondelete="CASCADE"),
        index=True,
    )
    condominio_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    unidade_id = Column(PG_UUID(as_uuid=True))

    # Data e horario (nomes reais do banco)
    data_trabalho = Column(Date, nullable=False, index=True)
    hora_inicio = Column(Time, nullable=False, default=time(8, 0))
    hora_fim = Column(Time, nullable=False, default=time(17, 0))

    # Check-in/out (nomes reais do banco)
    checkin_real = Column(DateTime)
    checkout_real = Column(DateTime)
    checkin_latitude = Column(Numeric(10, 8))
    checkin_longitude = Column(Numeric(11, 8))
    checkout_latitude = Column(Numeric(10, 8))
    checkout_longitude = Column(Numeric(11, 8))

    # Financeiro
    valor_previsto = Column(Numeric(10, 2))
    valor_final = Column(Numeric(10, 2))

    # Status (ENUM PostgreSQL schedule_status com valores uppercase)
    status = Column(
        PG_ENUM(
            "AGENDADO",
            "CONFIRMADO",
            "EM_ANDAMENTO",
            "CONCLUIDO",
            "CANCELADO",
            "NAO_COMPARECEU",
            name="schedule_status",
            create_type=False,
        ),
        nullable=False,
        default="AGENDADO",
        index=True,
    )

    # Tarefas e observacoes
    tarefas = Column(ARRAY(String), default=[])
    observacoes = Column(Text)

    # Relacionamentos
    diarist = relationship("Diarist", back_populates="schedules")
    assignment = relationship("DiaristAssignment", back_populates="schedules")

    __table_args__ = (Index("ix_diarist_schedules_data_diarist", "data_trabalho", "diarist_id"),)

    @property
    def is_confirmado(self) -> bool:
        """Verifica se esta confirmado."""
        return self.status == ScheduleStatus.CONFIRMADO.value

    @property
    def is_concluido(self) -> bool:
        """Verifica se esta concluido."""
        return self.status == ScheduleStatus.CONCLUIDO.value

    @property
    def teve_checkin(self) -> bool:
        """Verifica se teve check-in."""
        return self.checkin_real is not None

    @property
    def teve_checkout(self) -> bool:
        """Verifica se teve check-out."""
        return self.checkout_real is not None

    @property
    def duracao_minutos(self) -> int | None:
        """Calcula duracao em minutos."""
        if not self.checkin_real or not self.checkout_real:
            return None
        delta = self.checkout_real - self.checkin_real
        return int(delta.total_seconds() / 60)

    def confirmar(self) -> None:
        """Confirma agenda."""
        self.status = ScheduleStatus.CONFIRMADO.value

    def fazer_checkin(
        self,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> None:
        """Registra check-in."""
        self.checkin_real = datetime.utcnow()
        self.checkin_latitude = latitude
        self.checkin_longitude = longitude
        self.status = ScheduleStatus.EM_ANDAMENTO.value

    def fazer_checkout(
        self,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> None:
        """Registra check-out."""
        self.checkout_real = datetime.utcnow()
        self.checkout_latitude = latitude
        self.checkout_longitude = longitude
        self.status = ScheduleStatus.CONCLUIDO.value

    def marcar_falta(self, motivo: str | None = None) -> None:
        """Marca como nao compareceu."""
        self.status = ScheduleStatus.NAO_COMPARECEU.value
        self.motivo_status = motivo

    def cancelar(self, motivo: str | None = None) -> None:
        """Cancela agenda."""
        self.status = ScheduleStatus.CANCELADO.value

    def calcular_valor_final(self) -> None:
        """Define valor final igual ao previsto."""
        self.valor_final = self.valor_previsto


class DiaristPayment(Base):
    """Model de Pagamento de Diarista.

    Mapeado para a tabela real do banco com colunas existentes.
    """

    __tablename__ = "diarist_payments"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ativo = Column(Boolean, default=True, nullable=False)

    diarist_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("diarists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    condominio_id = Column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Datas
    data_referencia = Column(Date, nullable=False)
    data_vencimento = Column(Date)
    data_pagamento = Column(Date)

    # Valores
    valor_bruto = Column(Numeric(10, 2))
    retencao_inss = Column(Numeric(10, 2), default=0)
    retencao_iss = Column(Numeric(10, 2), default=0)
    retencao_irrf = Column(Numeric(10, 2), default=0)
    outros_descontos = Column(Numeric(10, 2), default=0)
    valor_liquido = Column(Numeric(10, 2))

    # Pagamento
    forma_pagamento = Column(String(30))
    comprovante_url = Column(String(500))
    status = Column(
        PG_ENUM("PENDENTE", "APROVADO", "PAGO", "CANCELADO", "ESTORNADO", name="payment_status", create_type=False),
        nullable=False,
        default="PENDENTE",
        index=True,
    )

    # Schedules incluidos
    schedules_ids = Column(JSONB, default=list)

    # Descricao
    descricao = Column(Text)

    # Relacionamentos
    diarist = relationship("Diarist", back_populates="payments")

    @property
    def is_pago(self) -> bool:
        """Verifica se esta pago."""
        return self.status == PaymentStatus.PAGO.value

    @property
    def is_vencido(self) -> bool:
        """Verifica se esta vencido."""
        if not self.data_vencimento:
            return False
        return date.today() > self.data_vencimento and self.status == PaymentStatus.PENDENTE.value

    @property
    def total_retencoes(self) -> float:
        """Calcula total de retencoes."""
        return (
            float(self.retencao_inss or 0)
            + float(self.retencao_iss or 0)
            + float(self.retencao_irrf or 0)
            + float(self.outros_descontos or 0)
        )

    def calcular_valores(self) -> None:
        """Calcula valores bruto e liquido."""
        bruto = float(self.valor_bruto or 0)
        self.valor_liquido = bruto - self.total_retencoes

    def pagar(
        self,
        data_pagamento: date | None = None,
        comprovante_url: str | None = None,
    ) -> None:
        """Registra pagamento."""
        self.status = PaymentStatus.PAGO.value
        self.data_pagamento = data_pagamento or date.today()
        if comprovante_url:
            self.comprovante_url = comprovante_url


class DiaristEvaluation(Base):
    """Model de Avaliacao de Diarista.

    Alinhado com a tabela real diarist_evaluations no PostgreSQL.
    Colunas reais: id, created_at, updated_at, ativo, diarist_id, schedule_id,
    avaliador_id, nota_geral, nota_pontualidade, nota_qualidade,
    nota_comportamento, nota_comunicacao, comentario, recomendaria
    """

    __tablename__ = "diarist_evaluations"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ativo = Column(Boolean, default=True, nullable=False)

    diarist_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("diarists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    schedule_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("diarist_schedules.id", ondelete="SET NULL"),
        index=True,
    )
    avaliador_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Notas (1-5)
    nota_geral = Column(Integer, nullable=False)
    nota_pontualidade = Column(Integer)
    nota_qualidade = Column(Integer)
    nota_comportamento = Column(Integer)
    nota_comunicacao = Column(Integer)

    # Feedback
    comentario = Column(Text)
    recomendaria = Column(Boolean, default=True)

    # Relacionamentos
    diarist = relationship("Diarist", back_populates="evaluations")

    @property
    def media_notas(self) -> float:
        """Calcula media das notas."""
        notas = [
            n
            for n in [
                self.nota_geral,
                self.nota_pontualidade,
                self.nota_qualidade,
                self.nota_comportamento,
                self.nota_comunicacao,
            ]
            if n is not None
        ]
        if not notas:
            return 0.0
        return round(sum(notas) / len(notas), 2)
