"""
Schemas Pydantic das Instruções de Posto (post orders).
"""

from datetime import datetime

from pydantic import BaseModel, Field


class InstrucoesPostoResponse(BaseModel):
    """Instruções vigentes de um posto (ou vazio honesto: conteudo=None, versao=0)."""

    post_id: str
    post_nome: str
    titulo: str = "Instruções do posto"
    conteudo: str | None = None
    versao: int = 0
    updated_at: datetime | None = None
    updated_by_nome: str | None = None


class InstrucoesPostoUpdate(BaseModel):
    """Body do PUT — só gestor. Conteúdo mínimo de 10 caracteres."""

    titulo: str | None = Field(None, max_length=200)
    conteudo: str = Field(..., min_length=10)


class InstrucoesPostoListItem(BaseModel):
    """Item da lista de postos do escopo com situação das instruções."""

    post_id: str
    post_nome: str
    tem_instrucoes: bool
    versao: int = 0
    updated_at: datetime | None = None


class InstrucoesPostoListResponse(BaseModel):
    total: int
    items: list[InstrucoesPostoListItem] = Field(default_factory=list)
