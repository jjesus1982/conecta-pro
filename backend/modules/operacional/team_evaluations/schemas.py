"""
Schemas Pydantic do módulo de Avaliação de Equipe.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


class EquipeMembro(BaseModel):
    """Funcionário com alocação ativa em posto do escopo."""

    employee_id: str
    nome: str
    cargo: str | None = None


class AvaliacaoCreate(BaseModel):
    """Payload de criação/atualização de avaliação (1 por avaliador/funcionário/competência)."""

    post_id: str | None = Field(
        None,
        description="Posto da avaliação. Opcional: derivado da alocação ativa do funcionário.",
    )
    employee_id: str = Field(..., description="Funcionário avaliado")
    nota: int = Field(..., ge=1, le=5, description="Nota de 1 a 5")
    observacao: str | None = Field(None, description="Observação livre")
    competencia: date | None = Field(None, description="Data de competência (default: hoje)")

    @field_validator("observacao")
    @classmethod
    def strip_text(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v


class AvaliacaoResponse(BaseModel):
    """Avaliação registrada."""

    id: str
    post_id: str
    post_nome: str | None = None
    employee_id: str
    employee_nome: str | None = None
    avaliador_user_id: str
    avaliador_nome: str
    nota: int
    observacao: str | None = None
    competencia: date
    criada_em: datetime
    atualizada: bool = Field(False, description="True se atualizou avaliação já existente do dia")


class ConsolidadoFuncionario(BaseModel):
    """Consolidado de avaliações por funcionário no período."""

    employee_id: str
    nome: str
    cargo: str | None = None
    media: float = Field(..., description="Média das notas no período (2 casas)")
    total_avaliacoes: int
    tendencia: str = Field(..., description="subindo | caindo | estavel | sem_dados")
    ultima_nota: int
    ultima_em: datetime
