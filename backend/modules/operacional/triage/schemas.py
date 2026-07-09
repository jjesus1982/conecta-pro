"""
Schemas Pydantic do módulo de Triagem (painel do gestor).
"""

from datetime import date, datetime

from pydantic import BaseModel, Field


class OcorrenciaPorPosto(BaseModel):
    post_id: str
    post_nome: str
    abertas: int


class OcorrenciaItem(BaseModel):
    id: str
    code: str
    title: str
    severity: str
    post_nome: str | None = None
    occurred_at: datetime
    status: str


class OcorrenciasPainel(BaseModel):
    abertas_total: int
    por_severidade: dict[str, int] = Field(default_factory=dict)
    por_posto: list[OcorrenciaPorPosto] = Field(default_factory=list)
    lista: list[OcorrenciaItem] = Field(default_factory=list)


class PassagemHoje(BaseModel):
    post_nome: str
    turno: str
    author_nome: str
    resumo: str
    pendencias: str | None = None
    criada_em: datetime


class AvaliacaoPorPosto(BaseModel):
    post_nome: str
    media: float
    total: int


class AvaliacoesSemana(BaseModel):
    total: int
    media_geral: float | None = Field(None, description="None quando não há avaliações na semana")
    por_posto: list[AvaliacaoPorPosto] = Field(default_factory=list)


class PostoSemVigencia(BaseModel):
    post_id: str
    post_nome: str


class EscalaDraft(BaseModel):
    id: str
    name: str | None = None
    month: int
    year: int
    post_nome: str
    status: str


class EscalasPainel(BaseModel):
    sem_vigencia: list[PostoSemVigencia] = Field(default_factory=list)
    drafts: list[EscalaDraft] = Field(default_factory=list)


class MovimentacaoProgramada(BaseModel):
    """Evento programado (fim de alocação, férias, retorno, vaga aberta)."""

    data: date
    tipo: str  # fim_alocacao | inicio_ferias | retorno_ferias | vaga
    descricao: str


class PresencaPorPosto(BaseModel):
    post_nome: str
    dias_esperados: int
    dias_presentes: int
    taxa: float | None = Field(None, description="presentes/esperados; None quando 0 esperados")


class PresencaGeral(BaseModel):
    esperados: int
    presentes: int
    taxa: float | None = Field(None, description="presentes/esperados; None quando 0 esperados")


class Presenca30d(BaseModel):
    """Absenteísmo dos últimos 30 dias (turnos agendados × presença real)."""

    por_posto: list[PresencaPorPosto] = Field(default_factory=list)
    geral: PresencaGeral


class PainelTriagem(BaseModel):
    """Painel consolidado de triagem operacional (só gestores)."""

    ocorrencias: OcorrenciasPainel
    passagens_hoje: list[PassagemHoje] = Field(default_factory=list)
    avaliacoes_semana: AvaliacoesSemana
    escalas: EscalasPainel
    movimentacoes: list[MovimentacaoProgramada] = Field(default_factory=list)
    presenca_30d: Presenca30d
