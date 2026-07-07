"""Schemas Pydantic para Diaristas."""

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from modules.operacional.diaristas.models.diarist import (
    AssignmentType,
    PaymentMethod,
    RecurrenceType,
    Weekday,
)

# === Diarist Schemas ===


class DiaristBase(BaseModel):
    """Schema base de Diarista."""

    nome: str = Field(..., min_length=2, max_length=200)
    cpf: str = Field(..., min_length=11, max_length=14)
    rg: str | None = Field(None, max_length=20)
    data_nascimento: date | None = None

    email: str | None = Field(None, max_length=255)
    telefone: str | None = Field(None, max_length=20)
    telefone_emergencia: str | None = Field(None, max_length=20)
    foto_url: str | None = Field(None, max_length=500)

    endereco: str | None = Field(None, max_length=500)
    cidade: str | None = Field(None, max_length=100)
    estado: str | None = Field(None, max_length=2)
    cep: str | None = Field(None, max_length=10)

    tipos_servico: list[str] | None = Field(default_factory=list)
    especialidades: list[str] | None = Field(default_factory=list)
    experiencia_anos: int | None = Field(0, ge=0)
    referencias: dict | None = Field(default_factory=dict)
    documentos: dict | None = Field(default_factory=dict)

    dias_disponiveis: list[str] | None = Field(default_factory=list)
    hora_inicio_disponivel: time | None = Field(default=time(8, 0))
    hora_fim_disponivel: time | None = Field(default=time(17, 0))
    aceita_hora_extra: bool | None = True

    valor_hora: Decimal | None = Field(None, ge=0)
    valor_diaria: Decimal = Field(..., ge=0)
    valor_hora_extra: Decimal | None = Field(Decimal("25.00"), ge=0)

    banco: str | None = Field(None, max_length=100)
    agencia: str | None = Field(None, max_length=20)
    conta: str | None = Field(None, max_length=30)
    tipo_conta: str | None = Field(None, max_length=20)
    pix: str | None = Field(None, max_length=100)


class DiaristCreate(DiaristBase):
    """Schema de criacao de Diarista."""

    pass


class DiaristUpdate(BaseModel):
    """Schema de atualizacao de Diarista."""

    nome: str | None = Field(None, min_length=2, max_length=200)
    data_nascimento: date | None = None

    email: str | None = Field(None, max_length=255)
    telefone: str | None = Field(None, max_length=20)
    telefone_emergencia: str | None = Field(None, max_length=20)
    foto_url: str | None = Field(None, max_length=500)

    endereco: str | None = Field(None, max_length=500)
    cidade: str | None = Field(None, max_length=100)
    estado: str | None = Field(None, max_length=2)
    cep: str | None = Field(None, max_length=10)

    tipos_servico: list[str] | None = None
    especialidades: list[str] | None = None
    experiencia_anos: int | None = Field(None, ge=0)
    referencias: dict | None = None
    documentos: dict | None = None

    dias_disponiveis: list[str] | None = None
    hora_inicio_disponivel: time | None = None
    hora_fim_disponivel: time | None = None
    aceita_hora_extra: bool | None = None

    valor_hora: Decimal | None = Field(None, ge=0)
    valor_diaria: Decimal | None = Field(None, ge=0)
    valor_hora_extra: Decimal | None = Field(None, ge=0)

    banco: str | None = Field(None, max_length=100)
    agencia: str | None = Field(None, max_length=20)
    conta: str | None = Field(None, max_length=30)
    tipo_conta: str | None = Field(None, max_length=20)
    pix: str | None = Field(None, max_length=100)


class DiaristResponse(BaseModel):
    """Schema de resposta de Diarista."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime | None = None
    ativo: bool = True

    nome: str
    cpf: str
    rg: str | None = None
    data_nascimento: date | None = None

    telefone: str | None = None
    telefone_emergencia: str | None = None
    email: str | None = None
    foto_url: str | None = None

    endereco: str | None = None
    cidade: str | None = None
    estado: str | None = None
    cep: str | None = None

    tipos_servico: list[str] = []
    especialidades: list[str] = []
    experiencia_anos: int = 0
    referencias: dict = {}
    documentos: dict = {}

    dias_disponiveis: list[str] = []
    hora_inicio_disponivel: time | None = None
    hora_fim_disponivel: time | None = None
    aceita_hora_extra: bool = True

    valor_hora: Decimal | None = None
    valor_diaria: Decimal
    valor_hora_extra: Decimal | None = None

    banco: str | None = None
    agencia: str | None = None
    conta: str | None = None
    tipo_conta: str | None = None
    pix: str | None = None

    status: str

    avaliacao_media: Decimal = Decimal("0")
    total_avaliacoes: int = 0
    total_servicos: int = 0


class DiaristListResponse(BaseModel):
    """Schema de lista de diaristas."""

    items: list[DiaristResponse]
    total: int
    page: int
    page_size: int
    pages: int


class DiaristStatsResponse(BaseModel):
    """Schema de estatisticas de diaristas."""

    total: int = 0
    ativos: int = 0
    inativos: int = 0
    bloqueados: int = 0
    por_tipo: dict = {}
    media_avaliacao_geral: float = 0.0
    total_diarias_mes: int = 0
    total_valor_mes: float = 0.0


# === Assignment Schemas ===


class DiaristAssignmentBase(BaseModel):
    """Schema base de Alocacao."""

    diarist_id: UUID
    tipo: AssignmentType = AssignmentType.CONDOMINIO
    servico_tipo: str = Field(..., max_length=50)
    servico_descricao: str | None = None
    local_servico: str | None = Field(None, max_length=200)
    unidade_id: UUID | None = None
    area_comum: str | None = Field(None, max_length=100)

    data_inicio: date
    data_fim: date | None = None
    horario_inicio: time | None = Field(default=time(8, 0))
    horario_fim: time | None = Field(default=time(17, 0))
    carga_horaria: int | None = Field(8, ge=1, le=12)

    recorrencia: RecurrenceType = RecurrenceType.AVULSO
    dias_semana: list[Weekday] | None = Field(default_factory=list)
    intervalo_dias: int | None = Field(None, ge=1)
    total_ocorrencias: int | None = Field(None, ge=1)

    valor_acordado: Decimal = Field(..., ge=0)
    valor_adicional: Decimal | None = Field(Decimal("0"), ge=0)
    desconto: Decimal | None = Field(Decimal("0"), ge=0)
    forma_pagamento: PaymentMethod | None = None

    contratante_nome: str | None = Field(None, max_length=200)
    instrucoes: str | None = None
    observacoes: str | None = None
    materiais_necessarios: list[str] | None = Field(default_factory=list)


class DiaristAssignmentCreate(DiaristAssignmentBase):
    """Schema de criacao de Alocacao."""

    condominio_id: UUID


class DiaristAssignmentUpdate(BaseModel):
    """Schema de atualizacao de Alocacao."""

    servico_descricao: str | None = None
    local_servico: str | None = Field(None, max_length=200)
    unidade_id: UUID | None = None
    area_comum: str | None = Field(None, max_length=100)

    data_fim: date | None = None
    horario_inicio: time | None = None
    horario_fim: time | None = None
    carga_horaria: int | None = Field(None, ge=1, le=12)

    valor_adicional: Decimal | None = Field(None, ge=0)
    desconto: Decimal | None = Field(None, ge=0)

    instrucoes: str | None = None
    observacoes: str | None = None
    materiais_necessarios: list[str] | None = None


class DiaristAssignmentResponse(BaseModel):
    """Schema de resposta de Alocacao."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    condominio_id: UUID
    diarist_id: UUID
    tipo: str
    status: str

    servico_tipo: str
    servico_descricao: str | None = None
    local_servico: str | None = None
    unidade_id: UUID | None = None
    area_comum: str | None = None

    data_inicio: date
    data_fim: date | None = None
    horario_inicio: time | None = None
    horario_fim: time | None = None
    carga_horaria: int = 8

    recorrencia: str
    dias_semana: list[str] = []
    total_ocorrencias: int | None = None
    ocorrencias_realizadas: int = 0

    valor_acordado: Decimal
    valor_adicional: Decimal = Decimal("0")
    desconto: Decimal = Decimal("0")
    valor_total: Decimal | None = None
    forma_pagamento: str | None = None

    contratante_nome: str | None = None
    aprovado_at: datetime | None = None

    instrucoes: str | None = None
    observacoes: str | None = None
    materiais_necessarios: list[str] = []

    created_at: datetime
    updated_at: datetime | None = None


# === Schedule Schemas ===


class DiaristScheduleBase(BaseModel):
    """Schema base de Agenda. Campos alinhados com tabela diarist_schedules."""

    diarist_id: UUID
    assignment_id: UUID | None = None
    condominio_id: UUID | None = None
    unidade_id: UUID | None = None
    data_trabalho: date
    hora_inicio: time | None = time(8, 0)
    hora_fim: time | None = time(17, 0)
    valor_previsto: Decimal | None = Field(None, ge=0)
    tarefas: list[str] | None = Field(default_factory=list)
    observacoes: str | None = None


class DiaristScheduleCreate(DiaristScheduleBase):
    """Schema de criacao de Agenda."""

    condominio_id: UUID


class DiaristScheduleUpdate(BaseModel):
    """Schema de atualizacao de Agenda."""

    hora_inicio: time | None = None
    hora_fim: time | None = None

    servico_descricao: str | None = None
    local_servico: str | None = Field(None, max_length=200)
    tarefas: list[str] | None = None

    valor_base: Decimal | None = Field(None, ge=0)
    valor_adicional: Decimal | None = Field(None, ge=0)
    valor_desconto: Decimal | None = Field(None, ge=0)
    observacoes: str | None = None


class DiaristScheduleResponse(BaseModel):
    """Schema de resposta de Agenda.

    Alinhado com colunas reais: data_trabalho, hora_inicio, hora_fim,
    checkin_real, checkout_real, valor_previsto, valor_final.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    condominio_id: UUID
    diarist_id: UUID
    assignment_id: UUID | None = None

    # Campos reais do banco
    data_trabalho: date
    hora_inicio: time | None = None
    hora_fim: time | None = None

    checkin_real: datetime | None = None
    checkout_real: datetime | None = None

    status: str

    # Financeiro
    valor_previsto: Decimal | None = None
    valor_final: Decimal | None = None

    # Tarefas
    tarefas: list[str] | None = []
    observacoes: str | None = None

    created_at: datetime
    updated_at: datetime | None = None


class CheckinRequest(BaseModel):
    """Schema de check-in."""

    schedule_id: UUID
    latitude: float | None = None
    longitude: float | None = None
    foto_url: str | None = Field(None, max_length=500)


class CheckoutRequest(BaseModel):
    """Schema de check-out."""

    schedule_id: UUID
    latitude: float | None = None
    longitude: float | None = None
    foto_url: str | None = Field(None, max_length=500)
    tarefas_concluidas: list[str] | None = Field(default_factory=list)
    ocorrencias: list[dict] | None = Field(default_factory=list)
    materiais_usados: list[dict] | None = Field(default_factory=list)


# === Payment Schemas ===


class DiaristPaymentBase(BaseModel):
    """Schema base de Pagamento."""

    diarist_id: UUID
    assignment_id: UUID | None = None

    periodo_inicio: date
    periodo_fim: date
    competencia: str | None = Field(None, max_length=7)

    valor_diarias: Decimal = Field(..., ge=0)
    quantidade_diarias: int | None = Field(0, ge=0)
    valor_horas_extras: Decimal | None = Field(Decimal("0"), ge=0)
    quantidade_horas_extras: Decimal | None = Field(Decimal("0"), ge=0)
    valor_adicional: Decimal | None = Field(Decimal("0"), ge=0)
    descricao_adicional: str | None = None
    valor_desconto: Decimal | None = Field(Decimal("0"), ge=0)
    descricao_desconto: str | None = None

    inss_retido: Decimal | None = Field(Decimal("0"), ge=0)
    iss_retido: Decimal | None = Field(Decimal("0"), ge=0)
    irrf_retido: Decimal | None = Field(Decimal("0"), ge=0)
    outras_retencoes: Decimal | None = Field(Decimal("0"), ge=0)

    forma_pagamento: PaymentMethod | None = None
    data_vencimento: date | None = None
    observacoes: str | None = None

    schedules_ids: list[UUID] | None = Field(default_factory=list)


class DiaristPaymentCreate(DiaristPaymentBase):
    """Schema de criacao de Pagamento."""

    condominio_id: UUID


class DiaristPaymentUpdate(BaseModel):
    """Schema de atualizacao de Pagamento."""

    valor_adicional: Decimal | None = Field(None, ge=0)
    descricao_adicional: str | None = None
    valor_desconto: Decimal | None = Field(None, ge=0)
    descricao_desconto: str | None = None

    inss_retido: Decimal | None = Field(None, ge=0)
    iss_retido: Decimal | None = Field(None, ge=0)
    irrf_retido: Decimal | None = Field(None, ge=0)
    outras_retencoes: Decimal | None = Field(None, ge=0)

    data_vencimento: date | None = None
    observacoes: str | None = None


class DiaristPaymentResponse(BaseModel):
    """Schema de resposta de Pagamento."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    condominio_id: UUID
    diarist_id: UUID
    assignment_id: UUID | None = None

    periodo_inicio: date
    periodo_fim: date
    competencia: str | None = None

    valor_diarias: Decimal
    quantidade_diarias: int = 0
    valor_horas_extras: Decimal = Decimal("0")
    quantidade_horas_extras: Decimal = Decimal("0")
    valor_adicional: Decimal = Decimal("0")
    valor_desconto: Decimal = Decimal("0")
    valor_bruto: Decimal | None = None
    valor_liquido: Decimal | None = None

    inss_retido: Decimal = Decimal("0")
    iss_retido: Decimal = Decimal("0")
    irrf_retido: Decimal = Decimal("0")
    outras_retencoes: Decimal = Decimal("0")

    status: str
    forma_pagamento: str | None = None
    data_vencimento: date | None = None
    data_pagamento: date | None = None
    comprovante_url: str | None = None

    aprovado_at: datetime | None = None
    observacoes: str | None = None

    created_at: datetime
    updated_at: datetime | None = None


# === Evaluation Schemas ===


class DiaristEvaluationBase(BaseModel):
    """Schema base de Avaliacao."""

    diarist_id: UUID
    schedule_id: UUID | None = None

    avaliador_nome: str | None = Field(None, max_length=200)
    avaliador_tipo: str | None = Field(None, max_length=50)

    nota_geral: int = Field(..., ge=1, le=5)
    nota_pontualidade: int | None = Field(None, ge=1, le=5)
    nota_qualidade: int | None = Field(None, ge=1, le=5)
    nota_profissionalismo: int | None = Field(None, ge=1, le=5)
    nota_comunicacao: int | None = Field(None, ge=1, le=5)
    nota_cuidado: int | None = Field(None, ge=1, le=5)

    comentario: str | None = None
    pontos_positivos: list[str] | None = Field(default_factory=list)
    pontos_melhorar: list[str] | None = Field(default_factory=list)

    recomendaria: bool | None = True
    contrataria_novamente: bool | None = True

    servico_tipo: str | None = Field(None, max_length=50)
    data_servico: date | None = None

    is_anonima: bool | None = False


class DiaristEvaluationCreate(DiaristEvaluationBase):
    """Schema de criacao de Avaliacao."""

    condominio_id: UUID
    avaliador_id: UUID


class DiaristEvaluationResponse(BaseModel):
    """Schema de resposta de Avaliacao."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    condominio_id: UUID
    diarist_id: UUID
    schedule_id: UUID | None = None

    avaliador_nome: str | None = None
    avaliador_tipo: str | None = None

    nota_geral: int
    nota_pontualidade: int | None = None
    nota_qualidade: int | None = None
    nota_profissionalismo: int | None = None
    nota_comunicacao: int | None = None
    nota_cuidado: int | None = None

    comentario: str | None = None
    pontos_positivos: list[str] = []
    pontos_melhorar: list[str] = []

    recomendaria: bool = True
    contrataria_novamente: bool = True

    servico_tipo: str | None = None
    data_servico: date | None = None

    is_publicada: bool = True
    is_anonima: bool = False

    resposta: str | None = None
    resposta_at: datetime | None = None

    created_at: datetime


# === AI Schemas ===


class DiaristSuggestionResponse(BaseModel):
    """Schema de sugestao de diarista."""

    diarist_id: str
    diarist_nome: str
    diarist_tipo: str
    score: float
    motivo: str
    disponivel: bool
    valor_diaria: float
    media_avaliacao: float
    total_diarias: int


class DiaristAvailabilityResponse(BaseModel):
    """Schema de disponibilidade."""

    diarist_id: str
    diarist_nome: str
    data: date
    horario_inicio: time
    horario_fim: time
    disponivel: bool
    motivo: str | None = None


class DiaristPerformanceResponse(BaseModel):
    """Schema de performance."""

    diarist_id: str
    diarist_nome: str
    periodo: str
    total_diarias: int
    total_horas: float
    taxa_comparecimento: float
    taxa_pontualidade: float
    media_avaliacao: float
    total_recebido: float
    tendencia: str
    recomendacoes: list[str]


class ScheduleOptimizationResponse(BaseModel):
    """Schema de otimizacao de agenda."""

    data: date
    sugestoes: list[dict]
    conflitos: list[dict]
    recomendacoes: list[str]


# === Batch Schedule Schemas ===


class BatchScheduleItem(BaseModel):
    """Item individual para escala em lote."""

    diarist_id: UUID
    horario_inicio: str = Field(default="08:00", max_length=5)
    horario_fim: str = Field(default="17:00", max_length=5)
    servico_tipo: str = Field(default="limpeza", max_length=50)
    servico_descricao: str | None = None
    local_servico: str | None = Field(None, max_length=200)
    observacoes: str | None = None


class BatchScheduleCreate(BaseModel):
    """Schema para criacao de escala em lote."""

    condominio_id: UUID
    data: date
    items: list[BatchScheduleItem] = Field(..., min_length=1)


class BatchScheduleResponse(BaseModel):
    """Schema de resposta de escala em lote."""

    total_criados: int = 0
    total_erros: int = 0
    erros: list[str] = []
    schedules: list[DiaristScheduleResponse] = []


# === Payroll (Fechamento de Folha) Schemas ===


class PayrollDiaristItem(BaseModel):
    """Item de diarista no relatorio de folha."""

    model_config = ConfigDict(from_attributes=True)

    diarist_id: str
    diarist_nome: str
    cpf: str
    quantidade_diarias: int = 0
    total_horas: Decimal = Decimal("0")
    valor_diaria: Decimal = Decimal("0")
    valor_bruto: Decimal = Decimal("0")
    inss_retido: Decimal = Decimal("0")
    valor_liquido: Decimal = Decimal("0")
    pix: str | None = None
    banco: str | None = None
    agencia: str | None = None
    conta: str | None = None


class PayrollReportResponse(BaseModel):
    """Schema de resposta do relatorio de folha."""

    competencia: str  # YYYY-MM
    periodo_inicio: date
    periodo_fim: date
    total_diaristas: int = 0
    total_diarias: int = 0
    valor_bruto_total: Decimal = Decimal("0")
    inss_total: Decimal = Decimal("0")
    valor_liquido_total: Decimal = Decimal("0")
    items: list[PayrollDiaristItem] = []


class PayrollGenerateRequest(BaseModel):
    """Schema para gerar pagamentos do fechamento."""

    condominio_id: UUID
    competencia: str = Field(..., min_length=7, max_length=7)  # YYYY-MM
    diarist_ids: list[UUID] | None = None  # filtro opcional
    forma_pagamento: str | None = Field(None, max_length=30)
