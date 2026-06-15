"""
Schemas de Ordem de Servico - Modulo Campo
==========================================

Pydantic schemas para validacao e serializacao de OS.
"""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# ENUMS (importados do model)
# =============================================================================
from modules.campo.models.ordem_servico import (
    OrigemOS,
    PrioridadeOS,
    StatusOS,
    TipoOS,
)

# =============================================================================
# SCHEMAS BASE
# =============================================================================


class MaterialItem(BaseModel):
    """Schema para item de material."""

    id: UUID | None = None
    nome: str
    codigo: str | None = None
    quantidade: int = 1
    valor_unitario: Decimal | None = None
    baixa_estoque: bool = False


class FotoItem(BaseModel):
    """Schema para foto."""

    url: str
    descricao: str | None = None
    timestamp: datetime | None = None


class DocumentoItem(BaseModel):
    """Schema para documento."""

    url: str
    nome: str
    tipo: str | None = None
    timestamp: datetime | None = None


# =============================================================================
# CREATE SCHEMAS
# =============================================================================


class OrdemServicoCreate(BaseModel):
    """Schema para criacao de OS."""

    model_config = ConfigDict(from_attributes=True)

    # Classificacao
    tipo: TipoOS = TipoOS.MANUTENCAO_CORRETIVA
    prioridade: PrioridadeOS = PrioridadeOS.NORMAL
    origem: OrigemOS = OrigemOS.CLIENTE

    # Cliente
    cliente_id: UUID
    contrato_id: UUID | None = None
    contato_nome: str | None = Field(None, max_length=200)
    contato_telefone: str | None = Field(None, max_length=20)
    contato_email: str | None = Field(None, max_length=255)

    # Localizacao
    endereco_servico: str = Field(..., min_length=5, max_length=500)
    endereco_complemento: str | None = Field(None, max_length=200)
    bairro: str | None = Field(None, max_length=100)
    cidade: str | None = Field(None, max_length=100)
    estado: str | None = Field(None, max_length=2)
    cep: str | None = Field(None, max_length=10)
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    ponto_referencia: str | None = Field(None, max_length=300)

    # Agendamento
    data_agendada: date | None = None
    horario_inicio_previsto: time | None = None
    horario_fim_previsto: time | None = None
    duracao_estimada_minutos: int = 60
    janela_atendimento: str | None = Field(None, max_length=50)

    # Tecnico
    tecnico_id: UUID | None = None
    tecnico_auxiliar_id: UUID | None = None

    # Descricao
    titulo: str | None = Field(None, max_length=300)
    descricao: str | None = None
    problema_relatado: str | None = None
    instrucoes_cliente: str | None = None

    # Equipamento
    equipamento_id: UUID | None = None
    equipamento_tipo: str | None = Field(None, max_length=100)
    equipamento_modelo: str | None = Field(None, max_length=100)
    equipamento_serie: str | None = Field(None, max_length=100)

    # Checklist
    checklist_template_id: UUID | None = None

    # Materiais previstos
    materiais_previstos: list[MaterialItem] | None = None

    # Financeiro
    valor_mao_obra: Decimal | None = None
    valor_deslocamento: Decimal | None = None
    is_cobrado: bool = True
    is_garantia: bool = False
    is_cortesia: bool = False
    motivo_isencao: str | None = Field(None, max_length=300)

    # SLA
    sla_horas: int | None = None

    # Integracao
    ticket_origem_id: str | None = Field(None, max_length=100)
    ticket_sistema: str | None = Field(None, max_length=50)

    # Metadata
    tags: list[str] | None = None


class OrdemServicoUpdate(BaseModel):
    """Schema para atualizacao de OS."""

    model_config = ConfigDict(from_attributes=True)

    tipo: TipoOS | None = None
    prioridade: PrioridadeOS | None = None

    # Contato
    contato_nome: str | None = Field(None, max_length=200)
    contato_telefone: str | None = Field(None, max_length=20)
    contato_email: str | None = Field(None, max_length=255)

    # Localizacao
    endereco_servico: str | None = Field(None, max_length=500)
    endereco_complemento: str | None = Field(None, max_length=200)
    bairro: str | None = Field(None, max_length=100)
    cidade: str | None = Field(None, max_length=100)
    estado: str | None = Field(None, max_length=2)
    cep: str | None = Field(None, max_length=10)
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    ponto_referencia: str | None = Field(None, max_length=300)

    # Agendamento
    data_agendada: date | None = None
    horario_inicio_previsto: time | None = None
    horario_fim_previsto: time | None = None
    duracao_estimada_minutos: int | None = None
    janela_atendimento: str | None = Field(None, max_length=50)

    # Tecnico
    tecnico_id: UUID | None = None
    tecnico_auxiliar_id: UUID | None = None

    # Descricao
    titulo: str | None = Field(None, max_length=300)
    descricao: str | None = None
    problema_relatado: str | None = None
    solucao_aplicada: str | None = None
    observacoes_internas: str | None = None
    instrucoes_cliente: str | None = None

    # Equipamento
    equipamento_id: UUID | None = None

    # Checklist
    checklist_template_id: UUID | None = None
    checklist_respostas: dict | None = None

    # Materiais
    materiais_previstos: list[MaterialItem] | None = None
    materiais_utilizados: list[MaterialItem] | None = None

    # Financeiro
    valor_mao_obra: Decimal | None = None
    valor_materiais: Decimal | None = None
    valor_deslocamento: Decimal | None = None
    valor_adicional: Decimal | None = None
    descricao_adicional: str | None = Field(None, max_length=300)
    valor_desconto: Decimal | None = None
    motivo_desconto: str | None = Field(None, max_length=300)

    # SLA
    sla_horas: int | None = None

    # Metadata
    tags: list[str] | None = None


# =============================================================================
# READ SCHEMAS
# =============================================================================


class OrdemServicoRead(BaseModel):
    """Schema completo de leitura de OS."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    numero: str
    tipo: TipoOS
    status: StatusOS
    prioridade: PrioridadeOS
    origem: OrigemOS

    # Cliente
    cliente_id: UUID
    cliente_nome: str | None = None
    cliente_telefone: str | None = None
    cliente_email: str | None = None
    contrato_id: UUID | None = None
    contato_nome: str | None = None
    contato_telefone: str | None = None
    contato_email: str | None = None
    # Origem / integração (ex.: ticket aberto pelo José Luís via WhatsApp)
    ticket_sistema: str | None = None
    ticket_origem_id: str | None = None

    # Localizacao
    endereco_servico: str
    endereco_complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    estado: str | None = None
    cep: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None

    # Agendamento
    data_abertura: datetime
    data_agendada: date | None = None
    horario_inicio_previsto: time | None = None
    horario_fim_previsto: time | None = None
    duracao_estimada_minutos: int | None = None

    # Execucao
    tecnico_id: UUID | None = None
    tecnico_nome: str | None = None
    tecnico_auxiliar_id: UUID | None = None
    checkin_at: datetime | None = None
    checkout_at: datetime | None = None
    data_conclusao: datetime | None = None
    tempo_execucao_minutos: int | None = None

    # Descricao
    titulo: str | None = None
    descricao: str | None = None
    problema_relatado: str | None = None
    solucao_aplicada: str | None = None

    # Equipamento
    equipamento_id: UUID | None = None
    equipamento_tipo: str | None = None

    # Checklist
    checklist_template_id: UUID | None = None
    checklist_concluido: bool = False

    # Materiais
    materiais_previstos: list[Any] | None = None
    materiais_utilizados: list[Any] | None = None

    # Financeiro
    valor_mao_obra: Decimal | None = None
    valor_materiais: Decimal | None = None
    valor_deslocamento: Decimal | None = None
    valor_total: Decimal | None = None
    is_cobrado: bool = True
    faturado: bool = False

    # Avaliacao
    avaliacao_nota: int | None = None
    avaliacao_comentario: str | None = None

    # Assinatura
    assinatura_cliente_url: str | None = None
    assinatura_cliente_nome: str | None = None

    # Fotos
    fotos_antes: list[Any] | None = None
    fotos_depois: list[Any] | None = None

    # SLA
    sla_horas: int | None = None
    sla_vencimento: datetime | None = None
    sla_cumprido: bool | None = None

    # Reagendamento
    reagendamentos: int = 0

    # Metadata
    tags: list[str] | None = None
    created_at: datetime
    updated_at: datetime
    is_active: bool


class OrdemServicoListItem(BaseModel):
    """Schema resumido para listagem de OS."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    numero: str
    tipo: TipoOS
    status: StatusOS
    prioridade: PrioridadeOS

    cliente_id: UUID
    endereco_servico: str
    cidade: str | None = None

    data_agendada: date | None = None
    horario_inicio_previsto: time | None = None

    tecnico_id: UUID | None = None

    titulo: str | None = None

    valor_total: Decimal | None = None
    avaliacao_nota: int | None = None

    sla_vencimento: datetime | None = None

    created_at: datetime


# =============================================================================
# ACTION SCHEMAS
# =============================================================================


class OSAgendarRequest(BaseModel):
    """Schema para agendar OS."""

    data_agendada: date
    horario_inicio_previsto: time
    horario_fim_previsto: time | None = None
    tecnico_id: UUID | None = None


class OSCheckinRequest(BaseModel):
    """Schema para check-in."""

    latitude: Decimal | None = None
    longitude: Decimal | None = None


class OSCheckoutRequest(BaseModel):
    """Schema para check-out."""

    latitude: Decimal | None = None
    longitude: Decimal | None = None


class OSConcluirRequest(BaseModel):
    """Schema para concluir OS."""

    solucao_aplicada: str | None = None
    observacoes: str | None = None


class OSCancelarRequest(BaseModel):
    """Schema para cancelar OS."""

    motivo: str = Field(..., min_length=5, max_length=500)


class OSReagendarRequest(BaseModel):
    """Schema para reagendar OS."""

    nova_data: date
    motivo: str = Field(..., min_length=5, max_length=300)


class OSAvaliacaoRequest(BaseModel):
    """Schema para registrar avaliacao."""

    nota: int = Field(..., ge=1, le=5)
    comentario: str | None = None


class OSAssinaturaRequest(BaseModel):
    """Schema para registrar assinatura."""

    url: str
    nome: str
    documento: str | None = None


class OSFotoRequest(BaseModel):
    """Schema para adicionar foto."""

    tipo: str = Field(..., pattern="^(antes|durante|depois)$")
    url: str
    descricao: str | None = None


# =============================================================================
# FILTER/SEARCH SCHEMAS
# =============================================================================


class OSFiltro(BaseModel):
    """Schema para filtros de busca de OS."""

    tipo: TipoOS | None = None
    status: StatusOS | None = None
    prioridade: PrioridadeOS | None = None
    origem: OrigemOS | None = None

    cliente_id: UUID | None = None
    contrato_id: UUID | None = None
    tecnico_id: UUID | None = None

    data_inicio: date | None = None
    data_fim: date | None = None

    cidade: str | None = None
    estado: str | None = None

    sla_vencido: bool | None = None
    avaliado: bool | None = None
    faturado: bool | None = None

    busca: str | None = None  # Busca por numero, titulo, descricao


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================


class OSPaginatedResponse(BaseModel):
    """Response paginado de OS."""

    items: list[OrdemServicoListItem]
    total: int
    page: int
    page_size: int
    pages: int


class OSDashboardStats(BaseModel):
    """Estatisticas para dashboard de OS."""

    total_abertas: int = 0
    total_agendadas: int = 0
    total_em_andamento: int = 0
    total_concluidas_hoje: int = 0
    total_concluidas_mes: int = 0
    total_atrasadas: int = 0
    tempo_medio_atendimento_minutos: float | None = None
    avaliacao_media: float | None = None
    taxa_primeira_resolucao: float | None = None
