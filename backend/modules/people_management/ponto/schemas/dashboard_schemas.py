"""Schemas para dashboard e inconsistencias do Ponto Eletronico."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TipoInconsistencia(StrEnum):
    """Classificacao de inconsistencias de ponto."""

    FALTA_BATIDA_ENTRADA = "falta_batida_entrada"
    FALTA_BATIDA_SAIDA = "falta_batida_saida"
    JORNADA_EXCEDIDA = "jornada_excedida"
    INTRAJORNADA_NAO_CONCEDIDA = "intrajornada_nao_concedida"
    HORA_NOTURNA_NAO_CALCULADA = "hora_noturna_nao_calculada"
    ESCALA_NAO_CADASTRADA = "escala_nao_cadastrada"
    PONTO_EM_ABERTO = "ponto_em_aberto"
    FOLGA_TRABALHADA = "folga_trabalhada"


class InconsistenciaResponse(BaseModel):
    """Uma inconsistencia detectada."""

    employee_id: str
    employee_nome: str
    data: str
    tipo: TipoInconsistencia
    descricao: str
    gravidade: str = "media"
    resolvida: bool = False


class InconsistenciaResumoResponse(BaseModel):
    """Resumo de inconsistencias do periodo."""

    periodo_inicio: str
    periodo_fim: str
    total_inconsistencias: int
    por_tipo: dict[str, int] = Field(default_factory=dict)
    por_gravidade: dict[str, int] = Field(default_factory=dict)
    items: list[InconsistenciaResponse] = Field(default_factory=list)


class BancoHorasResponse(BaseModel):
    """Saldo de banco de horas de um colaborador."""

    employee_id: str
    employee_nome: str
    escala: str | None = None
    horas_trabalhadas: float = 0.0
    horas_esperadas: float = 0.0
    saldo_horas: float = 0.0
    creditos: float = 0.0
    debitos: float = 0.0
    vencimento_proximo: str | None = None
    obs: str | None = None
    detalhes: list[dict[str, Any]] = Field(default_factory=list)


class DashboardPontoResponse(BaseModel):
    """Dashboard gerencial do ponto."""

    total_colaboradores: int = 0
    presentes_hoje: int = 0
    ausentes_hoje: int = 0
    afastados: int = 0
    inconsistencias_periodo: int = 0
    sem_escala: int = 0
    pontos_em_aberto: int = 0
    banco_horas: dict[str, Any] = Field(default_factory=dict)
    por_escala: dict[str, int] = Field(default_factory=dict)
    ultima_sync_solides: str | None = None


class SyncSolidesRequest(BaseModel):
    """Request para sincronizar ponto com Solides."""

    periodo_inicio: str | None = None
    periodo_fim: str | None = None
    force: bool = False


class SyncSolidesResponse(BaseModel):
    """Resposta da sincronizacao com Solides."""

    success: bool
    message: str
    total_importados: int = 0
    total_atualizados: int = 0
    total_inconsistencias: int = 0
    erros: list[str] = Field(default_factory=list)


class AjusteRequest(BaseModel):
    """Request para ajuste manual de ponto."""

    employee_id: str
    data: str
    punch_type: str
    timestamp: str
    motivo: str = Field(..., min_length=5)
    ajustado_por: str


class ColaboradorSemEscalaResponse(BaseModel):
    """Colaborador sem escala cadastrada."""

    employee_id: str
    nome: str
    cargo: str | None = None
    data_admissao: str | None = None
