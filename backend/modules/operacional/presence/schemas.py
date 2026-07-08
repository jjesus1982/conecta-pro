"""
Schemas Pydantic do Quadro de Presença ao vivo (Operacional).
"""

from datetime import date, datetime, time

from pydantic import BaseModel, Field


class FuncionarioTurno(BaseModel):
    """Funcionário esperado num turno do dia, com a presença REAL apurada."""

    employee_id: str
    nome: str
    cargo: str | None = None
    shift_id: str
    turno_inicio: time
    turno_fim: time
    status: str = Field(description="presente | atrasado | ausente | aguardando")
    presenca_em: datetime | None = Field(
        None, description="Hora da 1ª batida do dia (fonte='ponto') ou do check-in manual (fonte='manual'); null sem presença"
    )
    fonte: str | None = Field(None, description="'ponto' | 'manual' | null (sem presença)")
    facial_match: bool | None = Field(None, description="Só quando fonte='ponto'")
    dentro_geofence: bool | None = Field(None, description="Só quando fonte='ponto'")


class ExtraPresenca(BaseModel):
    """Funcionário COM batida no dia mas SEM turno escalado no dia."""

    employee_id: str
    nome: str
    presenca_em: datetime
    fonte: str = Field("ponto", description="Extra só existe por batida real")


class PostoPresenca(BaseModel):
    post_id: str
    post_nome: str
    esperados: int
    presentes: int
    atrasados: int
    ausentes: int
    aguardando: int
    funcionarios: list[FuncionarioTurno] = Field(default_factory=list)
    extras: list[ExtraPresenca] = Field(default_factory=list)


class ResumoPresenca(BaseModel):
    esperados: int
    presentes: int
    atrasados: int
    ausentes: int
    aguardando: int
    extras: int


class QuadroPresenca(BaseModel):
    """Quadro de presença do dia — escala × batidas reais, escopado por posto."""

    data: date
    atualizado_em: datetime = Field(description="Hora local de Manaus (America/Manaus) da geração do quadro")
    batidas_sincronizadas_ate: datetime | None = Field(
        None, description="Última batida sincronizada do Sólides (hora Manaus) — se anterior a agora, o quadro pode estar defasado"
    )
    resumo: ResumoPresenca
    postos: list[PostoPresenca] = Field(default_factory=list)
    sem_posto: list[ExtraPresenca] = Field(
        default_factory=list,
        description="Batidas de quem não tem turno hoje NEM alocação ativa (visível só para gestores)",
    )


class CheckinManualBody(BaseModel):
    observacao: str | None = Field(None, max_length=500)
