"""Schemas da Certificacao Humana."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CertificationCreate(BaseModel):
    """Cria uma certificacao PENDENTE para um calculo."""

    tipo_calculo: str = Field(..., description="folha_mensal|rescisao|esocial_s2210|...")
    referencia_id: str | None = None
    referencia_tipo: str | None = None
    competencia: str | None = Field(None, description="YYYY-MM")
    employee_id: str | None = None
    cliente_id: str | None = None
    calculado_valor: float | None = None
    esperado_valor: float | None = None
    divergencia: bool = False
    divergencia_desc: str | None = None
    payload: dict | None = None


class CertificationCertifyRequest(BaseModel):
    """Assina (certifica) — o trabalho humano de conferir."""

    observacao: str | None = None


class CertificationRejectRequest(BaseModel):
    """Rejeita com motivo."""

    observacao: str = Field(..., description="Motivo da rejeicao (obrigatorio)")


class CertificationResponse(BaseModel):
    """Retorno da certificacao (o pacote de conferencia)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tipo_calculo: str
    referencia_id: str | None = None
    referencia_tipo: str | None = None
    competencia: str | None = None
    employee_id: str | None = None
    cliente_id: str | None = None
    calculado_valor: float | None = None
    esperado_valor: float | None = None
    divergencia: bool = False
    divergencia_desc: str | None = None
    payload: dict | None = None
    hash_conteudo: str
    status: str
    certificado_por: str | None = None
    certificado_em: datetime | None = None
    observacao: str | None = None
    created_at: datetime | None = None
    # calculado pelo servico: a certificacao ainda vale (hash bate com o conteudo atual)?
    valida: bool | None = None
