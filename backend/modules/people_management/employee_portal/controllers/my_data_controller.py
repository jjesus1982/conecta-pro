"""
My Data Controller — Dados pessoais do funcionario.

Endpoints:
- GET /portal/my-data
- PUT /portal/my-data
"""

import logging
import os
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Meus Dados"])


# =========================================================================== #
# ONBOARDING — campos obrigatórios (gaps do S-2200 eSocial).
# FONTE ÚNICA: todos gravam em `employees` (mesma tabela lida pelo DP).
# Nunca aceitar cargo/salário/status/matrícula (gestão do DP).
# =========================================================================== #

# Campos obrigatórios do onboarding, mapeados para colunas REAIS de `employees`.
# label = rótulo humano exibido na tela de completar cadastro.
ONBOARDING_REQUIRED_FIELDS: dict[str, str] = {
    "telefone": "Telefone / celular",
    "cep": "CEP",
    "logradouro": "Endereço (rua/avenida)",
    "bairro": "Bairro",
    "cidade": "Cidade",
    "nome_mae": "Nome da mãe",
    "nome_pai": "Nome do pai",
    "naturalidade": "Naturalidade (cidade de nascimento)",
    "nacionalidade": "Nacionalidade",
    "rg": "RG",
    "estado_civil": "Estado civil",
    # PIS NÃO é obrigatório (regra do Jordan: nem todo mundo tem PIS — é a única
    # exceção). Continua coletável (SELF_EDITABLE_FIELDS), só não bloqueia/nag.
}

# Campos que o funcionário pode gravar (dados pessoais/contato do PRÓPRIO cadastro).
# Superconjunto dos obrigatórios + campos opcionais de contato/endereço.
# NUNCA inclui cargo, salário, status, matrícula, admissão, CPF, dados bancários.
SELF_EDITABLE_FIELDS: set[str] = {
    "telefone",
    "celular",
    "email",
    # Endereço estruturado (fonte única no employees).
    "cep",
    "logradouro",
    "numero",
    "complemento",
    "bairro",
    "cidade",
    "uf",
    # Documentos/filiação pessoais (gaps eSocial).
    "nome_mae",
    "nome_pai",
    "naturalidade",
    "nacionalidade",
    "rg",
    "rg_orgao",
    "rg_uf",
    "estado_civil",
    "pis",
    # Contato de emergência.
    "contato_emergencia",
    "telefone_emergencia",
}


class MyDataResponse(BaseModel):
    """Dados pessoais do funcionario."""

    nome: str | None = None
    cpf: str | None = None
    cargo: str | None = None
    data_admissao: str | None = None
    telefone: str | None = None
    celular: str | None = None
    email: str | None = None
    # Endereço: composto (compat com a UI antiga) + estruturado (fonte única).
    endereco: str | None = None
    cep: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = None
    # Documentos / filiação (gaps eSocial S-2200).
    nome_mae: str | None = None
    nome_pai: str | None = None
    naturalidade: str | None = None
    nacionalidade: str | None = None
    rg: str | None = None
    rg_orgao: str | None = None
    rg_uf: str | None = None
    estado_civil: str | None = None
    pis: str | None = None
    # Emergência.
    contato_emergencia: str | None = None
    telefone_emergencia: str | None = None

    model_config = ConfigDict(from_attributes=True)


class UpdateMyDataRequest(BaseModel):
    """Campos que o funcionario pode alterar pelo portal.

    Cobre TODOS os campos do onboarding (dados pessoais/contato).
    Cargo/salário/status/matrícula/CPF NUNCA entram aqui.
    """

    telefone: str | None = Field(None, max_length=20)
    celular: str | None = Field(None, max_length=20)
    email: str | None = Field(None, max_length=255)
    # Endereço estruturado (fonte única em employees).
    cep: str | None = Field(None, max_length=10)
    logradouro: str | None = Field(None, max_length=255)
    numero: str | None = Field(None, max_length=20)
    complemento: str | None = Field(None, max_length=100)
    bairro: str | None = Field(None, max_length=100)
    cidade: str | None = Field(None, max_length=100)
    uf: str | None = Field(None, max_length=2)
    # Compat: endereço em campo único (mapeado para logradouro se estruturado ausente).
    endereco: str | None = Field(None, max_length=500)
    # Documentos / filiação (gaps eSocial).
    nome_mae: str | None = Field(None, max_length=255)
    nome_pai: str | None = Field(None, max_length=255)
    naturalidade: str | None = Field(None, max_length=100)
    nacionalidade: str | None = Field(None, max_length=50)
    rg: str | None = Field(None, max_length=20)
    rg_orgao: str | None = Field(None, max_length=20)
    rg_uf: str | None = Field(None, max_length=2)
    estado_civil: str | None = Field(None, max_length=20)
    pis: str | None = Field(None, max_length=20)
    # Emergência.
    contato_emergencia: str | None = Field(None, max_length=255)
    telefone_emergencia: str | None = Field(None, max_length=20)

    # extra="forbid": qualquer campo NÃO listado (cargo, salário, status, matrícula,
    # cpf, data_admissao, dados bancários...) é REJEITADO com 422. O funcionário só
    # grava dados pessoais/contato do próprio cadastro.
    model_config = ConfigDict(from_attributes=True, extra="forbid")


def _endereco_composto(employee: Any) -> str | None:
    """Monta o endereço de exibição a partir das colunas estruturadas."""
    partes: list[str] = []
    logradouro = getattr(employee, "logradouro", None)
    numero = getattr(employee, "numero", None)
    if logradouro:
        partes.append(f"{logradouro}, {numero}" if numero else logradouro)
    for campo in ("bairro", "cidade"):
        val = getattr(employee, campo, None)
        if val:
            partes.append(val)
    uf = getattr(employee, "uf", None)
    if uf:
        partes.append(uf)
    cep = getattr(employee, "cep", None)
    if cep:
        partes.append(f"CEP {cep}")
    return " - ".join(partes) if partes else None


def _build_my_data_response(employee: Any) -> MyDataResponse:
    """Serializa o Employee (fonte única) para a resposta do portal, com CPF mascarado."""
    cpf = getattr(employee, "cpf", None)
    if cpf and len(cpf) > 4:
        cpf = f"***.***.***-{cpf[-2:]}"
    return MyDataResponse(
        nome=getattr(employee, "nome", None) or getattr(employee, "name", None),
        cpf=cpf,
        cargo=getattr(employee, "cargo", None) or getattr(employee, "position", None),
        data_admissao=str(employee.data_admissao)
        if getattr(employee, "data_admissao", None)
        else None,
        telefone=getattr(employee, "telefone", None) or getattr(employee, "phone", None),
        celular=getattr(employee, "celular", None),
        email=getattr(employee, "email", None),
        endereco=_endereco_composto(employee),
        cep=getattr(employee, "cep", None),
        logradouro=getattr(employee, "logradouro", None),
        numero=getattr(employee, "numero", None),
        complemento=getattr(employee, "complemento", None),
        bairro=getattr(employee, "bairro", None),
        cidade=getattr(employee, "cidade", None),
        uf=getattr(employee, "uf", None),
        nome_mae=getattr(employee, "nome_mae", None),
        nome_pai=getattr(employee, "nome_pai", None),
        naturalidade=getattr(employee, "naturalidade", None),
        nacionalidade=getattr(employee, "nacionalidade", None),
        rg=getattr(employee, "rg", None),
        rg_orgao=getattr(employee, "rg_orgao", None),
        rg_uf=getattr(employee, "rg_uf", None),
        estado_civil=getattr(employee, "estado_civil", None),
        pis=getattr(employee, "pis", None),
        contato_emergencia=getattr(employee, "contato_emergencia", None),
        telefone_emergencia=getattr(employee, "telefone_emergencia", None),
    )


def _compute_onboarding_status(employee: Any) -> dict[str, Any]:
    """Computa o status do onboarding a partir dos campos obrigatórios em `employees`.

    Um campo conta como preenchido se tem valor não-vazio (após strip).
    """
    faltantes: list[dict[str, str]] = []
    ok: list[str] = []
    for campo, label in ONBOARDING_REQUIRED_FIELDS.items():
        valor = getattr(employee, campo, None)
        preenchido = valor is not None and str(valor).strip() != ""
        if preenchido:
            ok.append(campo)
        else:
            faltantes.append({"campo": campo, "label": label})
    # MODO TRANSIÇÃO (rollout do ponto próprio 01/08): enquanto o cadastro completo
    # não vem da Sólides, o pendente NÃO bloqueia — o funcionário bate ponto e completa
    # depois (banner persistente). `bloqueante=true` só quando PONTO_ONBOARDING_BLOQUEANTE
    # for ligado (default false). O DP acompanha a completude pelo painel.
    bloqueante = os.getenv("PONTO_ONBOARDING_BLOQUEANTE", "false").lower() == "true"
    # Reconhecimento facial: cadastrar o rosto é OBRIGATÓRIO (decisão do Jordan) — sem ele
    # o funcionário não bate ponto (gate rígido em /ponto/facial/batida). Diferente dos
    # campos de dados (modo transição), a facial é sempre exigida antes de bater.
    facial_cadastrada = bool(getattr(employee, "biometria_facial", False))
    return {
        "pendente": len(faltantes) > 0,
        "bloqueante": bloqueante and len(faltantes) > 0,
        "modo_transicao": not bloqueante,
        "total_obrigatorios": len(ONBOARDING_REQUIRED_FIELDS),
        "total_ok": len(ok),
        "campos_ok": ok,
        "campos_faltantes": faltantes,
        "facial_cadastrada": facial_cadastrada,
        "facial_pendente": not facial_cadastrada,
    }


async def _load_employee(db: AsyncSession, employee_id: Any) -> Any:
    from sqlalchemy import select

    from modules.operacional.models.employee import Employee

    result = await db.execute(select(Employee).where(Employee.id == str(employee_id)))
    return result.scalar_one_or_none()


