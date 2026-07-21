"""Primeiro acesso do FUNCIONÁRIO (link público) — fluxo do Jordan (2026-07-21).

Os 50 CLT nunca logaram. Jordan manda UM link; o funcionário:
  1) informa o CPF (tela 1) — tem que bater com funcionário ATIVO (CPF falso = barrado);
  2) vê os dados já cadastrados e completa o que falta (tela 2) — só avança com 100%;
  3) cadastra o rosto (tela 3);
  4) cai no Portal do Funcionário.
A senha dele é OBRIGATORIAMENTE o CPF (não cria senha nova). Logins seguintes:
e-mail cadastrado + CPF, OU reconhecimento facial. Ver [[project_ponto_teste_launch]].

Segurança: cada passo além do CPF exige um TOKEN TEMPORÁRIO (scope='primeiro_acesso')
emitido no /identificar — ninguém grava cadastro de outro sem passar pelo CPF.
Grava DIRETO em `employees` (fonte única → transborda p/ DP/folha/eSocial/operacional).
"""
from __future__ import annotations

import json
import math
import re
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.auth.jwt import create_access_token, create_refresh_token
from core.auth.security import get_password_hash
from core.config import settings
from core.database.session import get_sync_db_dependency
from modules.people_management.employee_portal.controllers.my_data_controller import (
    ONBOARDING_REQUIRED_FIELDS,
    SELF_EDITABLE_FIELDS,
)

router = APIRouter(prefix="/primeiro-acesso", tags=["Portal - Primeiro acesso do funcionário"])

_SCOPE = "primeiro_acesso"


def _so_digitos(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


def _emp_ativo_por_cpf(db: Session, cpf: str) -> dict[str, Any] | None:
    """Funcionário ATIVO real (não homolog, não PJ) cujo CPF (só dígitos) bate."""
    dig = _so_digitos(cpf)
    if len(dig) != 11:
        return None
    row = db.execute(
        text(
            "SELECT CAST(id AS TEXT) AS id, nome, email, cargo, matricula "
            "FROM employees "
            "WHERE regexp_replace(coalesce(cpf,''), '\\D', '', 'g') = :d "
            "  AND status = 'ativo' AND coalesce(is_homologacao, false) = false "
            "  AND (tipo_contrato = 'clt' OR tipo_contrato IS NULL) "
            "  AND (tipo_contrato IS DISTINCT FROM 'pj') "
            "LIMIT 1"
        ),
        {"d": dig},
    ).mappings().first()
    return dict(row) if row else None


def _dados_e_faltantes(db: Session, employee_id: str) -> tuple[dict, list[dict]]:
    """Valores atuais dos campos editáveis + lista de obrigatórios que ainda faltam."""
    cols = ", ".join(sorted(SELF_EDITABLE_FIELDS))
    row = db.execute(
        text(f"SELECT {cols} FROM employees WHERE CAST(id AS TEXT) = :e"),
        {"e": employee_id},
    ).mappings().first()
    atuais = {k: (v if v is not None else "") for k, v in dict(row or {}).items()}
    faltantes = [
        {"campo": campo, "label": label}
        for campo, label in ONBOARDING_REQUIRED_FIELDS.items()
        if not str(atuais.get(campo, "") or "").strip()
    ]
    return atuais, faltantes


def _token_primeiro_acesso(employee_id: str, cpf_dig: str) -> str:
    return create_access_token(
        subject=employee_id,
        extra_data={"scope": _SCOPE, "employee_id": employee_id, "cpf": cpf_dig},
        expires_delta=timedelta(minutes=40),
    )


def _emp_do_token(authorization: str | None) -> str:
    """Valida o token temporário do primeiro acesso e devolve o employee_id."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sessão de primeiro acesso ausente.")
    tok = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(tok, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=401, detail="Sessão de primeiro acesso inválida ou expirada.")
    if payload.get("scope") != _SCOPE or not payload.get("employee_id"):
        raise HTTPException(status_code=403, detail="Token não é de primeiro acesso.")
    return str(payload["employee_id"])


# ─────────────────────────────────────────────────────────────────────────────
class IdentificarBody(BaseModel):
    cpf: str


@router.post("/identificar")
def identificar(body: IdentificarBody, db: Session = Depends(get_sync_db_dependency)) -> dict[str, Any]:
    """Tela 1: CPF → confirma que é funcionário ativo e devolve dados + o que falta."""
    dig = _so_digitos(body.cpf)
    if len(dig) != 11:
        raise HTTPException(status_code=422, detail="CPF inválido — informe os 11 dígitos.")
    emp = _emp_ativo_por_cpf(db, dig)
    if not emp:
        raise HTTPException(
            status_code=404,
            detail="CPF não encontrado entre os funcionários ativos. Fale com o RH.",
        )
    atuais, faltantes = _dados_e_faltantes(db, emp["id"])
    ja_tem_rosto = bool(
        db.execute(
            text("SELECT face_descriptor IS NOT NULL FROM employees WHERE CAST(id AS TEXT)=:e"),
            {"e": emp["id"]},
        ).scalar()
    )
    return {
        "token": _token_primeiro_acesso(emp["id"], dig),
        "nome": emp["nome"],
        "email": emp["email"],
        "cargo": emp["cargo"],
        "matricula": emp["matricula"],
        "dados": atuais,
        "faltantes": faltantes,
        "cadastro_completo": len(faltantes) == 0,
        "ja_tem_rosto": ja_tem_rosto,
    }


class CompletarBody(BaseModel):
    campos: dict[str, str]


@router.post("/completar")
def completar(
    body: CompletarBody,
    authorization: str | None = Header(None),
    db: Session = Depends(get_sync_db_dependency),
) -> dict[str, Any]:
    """Tela 2: grava os campos preenchidos DIRETO em employees (fonte única)."""
    emp_id = _emp_do_token(authorization)
    # só aceita campos editáveis pelo funcionário (nunca cargo/salário/status/CPF)
    sets, params = [], {"e": emp_id}
    for k, v in (body.campos or {}).items():
        if k in SELF_EDITABLE_FIELDS and str(v or "").strip():
            sets.append(f"{k} = :{k}")
            params[k] = str(v).strip()
    if sets:
        db.execute(
            text(f"UPDATE employees SET {', '.join(sets)}, updated_at = now() WHERE CAST(id AS TEXT) = :e"),
            params,
        )
        db.commit()
    atuais, faltantes = _dados_e_faltantes(db, emp_id)
    return {"dados": atuais, "faltantes": faltantes, "cadastro_completo": len(faltantes) == 0}


@router.post("/buscar-pis")
def buscar_pis(
    authorization: str | None = Header(None),
    db: Session = Depends(get_sync_db_dependency),
) -> dict[str, Any]:
    """Busca o PIS/NIS por CPF via API (p/ os poucos que não sabem). Hoje: 46/50 já têm
    PIS no cadastro; se não houver API ligada, devolve encontrado=false e a pessoa
    preenche manual — NUNCA trava."""
    emp_id = _emp_do_token(authorization)
    atual = db.execute(text("SELECT pis, cpf FROM employees WHERE CAST(id AS TEXT)=:e"), {"e": emp_id}).mappings().first()
    if atual and str(atual.get("pis") or "").strip():
        return {"encontrado": True, "pis": atual["pis"], "fonte": "cadastro"}
    # TODO: ligar Infosimples/robô CPF→NIS. Sem API ligada ainda → manual.
    return {
        "encontrado": False,
        "mensagem": "Não foi possível buscar o PIS automaticamente. Preencha manualmente ou "
        "deixe em branco se não tiver.",
    }


class ConcluirBody(BaseModel):
    descriptor: list[float] = Field(..., min_length=64, max_length=512)


@router.post("/concluir")
def concluir(
    body: ConcluirBody,
    authorization: str | None = Header(None),
    db: Session = Depends(get_sync_db_dependency),
) -> dict[str, Any]:
    """Tela 3: exige cadastro 100%, cadastra o rosto, define a SENHA = CPF e ativa o
    acesso. O front então loga pelo /auth/login normal (e-mail + CPF)."""
    emp_id = _emp_do_token(authorization)
    _, faltantes = _dados_e_faltantes(db, emp_id)
    if faltantes:
        raise HTTPException(
            status_code=422,
            detail=f"Complete o cadastro antes de cadastrar o rosto — faltam: "
            f"{', '.join(f['label'] for f in faltantes)}.",
        )
    emp = db.execute(
        text("SELECT email, regexp_replace(coalesce(cpf,''),'\\D','','g') AS cpf FROM employees WHERE CAST(id AS TEXT)=:e"),
        {"e": emp_id},
    ).mappings().first()
    if not emp or not emp["email"]:
        raise HTTPException(status_code=409, detail="Cadastro sem e-mail — fale com o RH.")
    # 1) cadastra o rosto (mesmo destino do enroll do self-service)
    db.execute(
        text(
            "UPDATE employees SET face_descriptor = :d, biometria_facial = true, "
            "face_enrolled_at = (now() AT TIME ZONE 'America/Manaus'), updated_at = now() "
            "WHERE CAST(id AS TEXT) = :e"
        ),
        {"d": json.dumps(body.descriptor), "e": emp_id},  # MESMO formato do enroll oficial (JSON)
    )
    # 2) senha = CPF (Jordan: nunca cria senha nova) + ativa o login vinculado
    senha_hash = get_password_hash(emp["cpf"])
    upd = db.execute(
        text("UPDATE users SET password_hash = :p, is_active = true, updated_at = now() "
             "WHERE CAST(employee_id AS TEXT) = :e"),
        {"p": senha_hash, "e": emp_id},
    )
    if upd.rowcount == 0:
        raise HTTPException(status_code=409, detail="Sua conta de acesso não está criada — fale com o RH.")
    db.commit()
    return {"success": True, "email": emp["email"], "portal_url": "/modulos/meu-espaco"}


# ─── Login por reconhecimento facial (1:N — tipo desbloqueio de celular) ─────
router_auth = APIRouter(tags=["Portal - Login facial"])

_FACE_MATCH_MAX = 0.5   # distância euclidiana máx p/ aceitar (auth estrita; enroll usa 0.68)
_FACE_MARGIN = 0.06     # o melhor tem que ser claramente melhor que o 2º (anti-ambiguidade)


def _dist(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(n)))


class LoginFacialBody(BaseModel):
    descriptor: list[float] = Field(..., min_length=64, max_length=512)


@router_auth.post("/login-facial")
def login_facial(body: LoginFacialBody, db: Session = Depends(get_sync_db_dependency)) -> dict[str, Any]:
    """Login por rosto: compara contra TODOS os funcionários ativos com rosto (1:N) e
    loga o que casar, com margem anti-ambiguidade. Sem match confiável → 401 (e-mail+CPF)."""
    alvo = body.descriptor
    rows = db.execute(
        text(
            "SELECT CAST(id AS TEXT) AS id, nome, face_descriptor FROM employees "
            "WHERE face_descriptor IS NOT NULL AND status='ativo' "
            "  AND coalesce(is_homologacao,false)=false"
        )
    ).mappings().all()
    best_id = best_nome = None
    best_d = second_d = 1e9
    for r in rows:
        try:
            stored = json.loads(r["face_descriptor"])
        except (TypeError, ValueError):
            continue
        d = _dist(alvo, stored)
        if d < best_d:
            second_d, best_d = best_d, d
            best_id, best_nome = r["id"], r["nome"]
        elif d < second_d:
            second_d = d
    if best_id is None or best_d > _FACE_MATCH_MAX:
        raise HTTPException(status_code=401, detail="Rosto não reconhecido. Entre com e-mail e CPF.")
    if second_d - best_d < _FACE_MARGIN:
        raise HTTPException(status_code=401, detail="Rosto ambíguo. Por segurança, entre com e-mail e CPF.")
    user = db.execute(
        text("SELECT CAST(id AS TEXT) AS id, email, name, role, is_active, "
             " CAST(condominio_id AS TEXT) AS condominio_id "
             "FROM users WHERE CAST(employee_id AS TEXT)=:e"),
        {"e": best_id},
    ).mappings().first()
    if not user or not user["is_active"]:
        raise HTTPException(status_code=403, detail="Acesso ainda não ativado. Faça o primeiro acesso.")
    extra = {"email": user["email"], "role": user["role"]}
    if user["condominio_id"]:
        extra["condominio_id"] = user["condominio_id"]
    access = create_access_token(subject=user["id"], extra_data=extra)
    refresh = create_refresh_token(subject=user["id"])
    return {
        "access_token": access, "refresh_token": refresh, "token_type": "Bearer",
        "reconhecido": best_nome,
        "user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]},
    }
