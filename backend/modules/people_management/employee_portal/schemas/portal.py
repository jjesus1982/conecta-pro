"""
Schemas do portal principal — login, dashboard.
"""

from pydantic import BaseModel, ConfigDict, Field


class PortalLoginRequest(BaseModel):
    """Request para autenticacao no portal do funcionario.

    Dois modos de login:
    - CPF + senha (padrao)
    - CPF + data de nascimento (alternativo, para primeiro acesso)
    """

    cpf: str = Field(..., min_length=11, max_length=14, description="CPF do funcionario")
    password: str | None = Field(None, min_length=4, description="Senha do portal")
    data_nascimento: str | None = Field(
        None,
        description="Data de nascimento YYYY-MM-DD (alternativa a senha)",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )

    model_config = ConfigDict(from_attributes=True)


class PortalLoginResponse(BaseModel):
    """Response apos autenticacao bem-sucedida."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int = 28800
    employee_name: str
    employee_id: str

    model_config = ConfigDict(from_attributes=True)


class PortalDashboard(BaseModel):
    """Dados do dashboard principal do portal."""

    name: str
    position: str | None = None
    workplace: str | None = None
    next_shift: str | None = None
    pending_documents: int = 0
    unread_notifications: int = 0

    model_config = ConfigDict(from_attributes=True)
