"""Prestadores PJ — GERADOR de link de autocadastro (RH/admin).

Permite ao RH criar um prestador PJ (nome + empresa + papel) e o sistema **pré-semeia** o
registro (empresa_id EXPLÍCITO, tipo_contrato='pj', status='pj_pendente', token individual) e
devolve o **link pronto** `/autocadastro-pj?token=…` para mandar à pessoa. Fim do pré-seed manual.

Gotchas respeitados: `empresa_id` setado EXPLÍCITO (nunca o DEFAULT cego = Patrimonial);
`tipo_contrato='pj'`; token único por pessoa (o token carrega a identidade — não casar por nome).
"""
import secrets
import uuid as _uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_active_user
from core.database.session import get_sync_db_dependency
from core.models import User

router = APIRouter(prefix="/prestadores-pj", tags=["RH - Prestadores PJ (gerador de link)"])

# slug → empresa_id (EXPLÍCITO — o banco tem DEFAULT cego = Patrimonial)
_EMPRESAS = {
    "eletronica": "619a3df1-8bce-49ce-b77a-04f80a0e8491",
    "patrimonial": "7d79ed12-d480-4906-b2e0-2b2c4d299bab",
}


class NovoPrestadorBody(BaseModel):
    nome: str
    empresa: str  # 'eletronica' | 'patrimonial'
    papel: str | None = None
    cpf: str | None = None


def _gera_token(db: Session) -> str:
    for _ in range(12):
        t = "pj-" + secrets.token_hex(5)
        if not db.execute(text("SELECT 1 FROM employees WHERE autocadastro_token = :t"), {"t": t}).fetchone():
            return t
    raise HTTPException(status_code=500, detail="Não foi possível gerar um token único.")


@router.post("", status_code=201)
def criar_prestador(
    body: NovoPrestadorBody,
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Cria (pré-semeia) um prestador PJ e devolve o link individual de autocadastro."""
    nome = (body.nome or "").strip()
    if not nome:
        raise HTTPException(status_code=422, detail="Informe o nome do prestador.")
    emp_key = (body.empresa or "").strip().lower()
    empresa_id = _EMPRESAS.get(emp_key)
    if not empresa_id:
        raise HTTPException(status_code=422, detail="Empresa inválida (use 'eletronica' ou 'patrimonial').")
    token = _gera_token(db)
    eid = str(_uuid.uuid4())
    db.execute(
        text("INSERT INTO employees (id, nome, cpf, tipo_contrato, empresa_id, status, papel_pj, "
             " autocadastro_token, created_at, updated_at) "
             "VALUES (CAST(:i AS uuid), :n, :cpf, 'pj', CAST(:emp AS uuid), 'pj_pendente', :papel, :t, now(), now())"),
        {"i": eid, "n": nome, "cpf": (body.cpf or None), "emp": empresa_id, "papel": (body.papel or None), "t": token},
    )
    db.commit()
    empresa_nome = db.execute(text("SELECT nome_fantasia FROM empresas WHERE id::text=:e"), {"e": empresa_id}).scalar()
    return {"id": eid, "nome": nome, "empresa": empresa_nome, "empresa_slug": emp_key,
            "papel": body.papel, "token": token, "link": f"/autocadastro-pj?token={token}"}


@router.get("/links-empresa")
def links_empresa(
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Os 2 LINKS FIXOS de empresa (autocadastro livre — 'manda e esquece'). A pessoa preenche
    tudo; a empresa vem do link (não da escolha dela)."""
    from modules.people_management.employee_portal.controllers.pj_autocadastro_controller import _TOKENS_EMPRESA
    saida = []
    for token, emp_id in _TOKENS_EMPRESA.items():
        nome = db.execute(text("SELECT nome_fantasia FROM empresas WHERE id::text=:e"), {"e": emp_id}).scalar()
        saida.append({"empresa": nome, "empresa_id": emp_id, "token": token, "link": f"/autocadastro-pj?token={token}"})
    return {"links": saida}


@router.get("")
def listar_prestadores(
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Lista os prestadores PJ (com status do autocadastro + link pra recopiar)."""
    rows = db.execute(
        text("SELECT e.id::text AS id, e.nome, e.papel_pj, e.status, e.cnpj_pendente, e.cnpj, "
             " e.autocadastro_token, emp.nome_fantasia AS empresa, e.created_at "
             "FROM employees e LEFT JOIN empresas emp ON emp.id = e.empresa_id "
             "WHERE e.tipo_contrato = 'pj' AND e.autocadastro_token IS NOT NULL "
             "ORDER BY e.created_at DESC NULLS LAST"),
    ).mappings().all()
    return {
        "prestadores": [
            {
                "id": r["id"], "nome": r["nome"], "papel": r["papel_pj"], "empresa": r["empresa"],
                "status": r["status"],
                "status_label": "Concluído" if r["status"] == "pj_ativo" else "Aguardando",
                "cnpj": r["cnpj"] or ("pendente" if r["cnpj_pendente"] else None),
                "token": r["autocadastro_token"], "link": f"/autocadastro-pj?token={r['autocadastro_token']}",
                "criado_em": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
    }


@router.post("/{prestador_id}/regenerar-link")
def regenerar_link(
    prestador_id: str,
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Gera um novo token (invalida o link antigo) — útil se o link vazar."""
    row = db.execute(
        text("SELECT status FROM employees WHERE id::text=:i AND tipo_contrato='pj'"), {"i": prestador_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Prestador não encontrado.")
    if row["status"] == "pj_ativo":
        raise HTTPException(status_code=409, detail="Cadastro já concluído — não precisa de novo link.")
    token = _gera_token(db)
    db.execute(text("UPDATE employees SET autocadastro_token=:t, updated_at=now() WHERE id::text=:i"),
               {"t": token, "i": prestador_id})
    db.commit()
    return {"token": token, "link": f"/autocadastro-pj?token={token}"}
