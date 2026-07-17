"""Autocadastro de HOMOLOGAÇÃO — base de teste isolada da produção.

Fluxo (decisão do Jordan): um link tokenizado de autocadastro coleta os dados com o
MESMO rigor do eSocial que exigimos na produção, cria o funcionário na base de
HOMOLOGAÇÃO (cliente HOMOLOG, posto "Conecta Base" = escritório) com uma escala
atribuída automaticamente (distribui noturno/diurno/comercial), cria o login e gera
os turnos dos próximos dias. Depois o testador entra no Meu Espaço, cadastra o rosto
(facial obrigatório) e bate ponto — homologando a cadeia inteira sem tocar na folha
real (tudo com employees.is_homologacao=true; a folha/eSocial/alertas já excluem).

Montado sob /portal (aggregator) → prefixo final /people-management/portal/homologacao/*,
que é ISENTO do gate de módulo DP (audience própria). O autocadastro é PÚBLICO
(pré-login, protegido por token); o painel exige login.
"""

import os
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_active_user
from core.auth.security import hash_password
from core.database.session import get_sync_db_dependency
from core.models import User

router = APIRouter(prefix="/homologacao", tags=["Homologação (base de teste)"])

# Token do link de autocadastro (pré-login). Override por env; default para o link funcionar.
_TOKEN = os.getenv("HOMOLOG_AUTOCADASTRO_TOKEN", "conecta-homolog-2026")

# Escalas de homologação — distribuídas em round-robin p/ cobrir todos os casos de
# fechamento (noturno c/ adicional, diurno, comercial 44h).
_ESCALAS = [
    {"cargo": "AGENTE DE PORTARIA", "escala": "12x36", "turno": "noturno",
     "inicio": "19:00", "fim": "07:00", "horas": 12.0},
    {"cargo": "AGENTE DE PORTARIA", "escala": "12x36", "turno": "diurno",
     "inicio": "07:00", "fim": "19:00", "horas": 12.0},
    {"cargo": "AUXILIAR ADMINISTRATIVO", "escala": "44h", "turno": "comercial",
     "inicio": "08:00", "fim": "17:00", "horas": 8.0},
]

# Campos obrigatórios com rigor eSocial (espelham o onboarding de produção).
_OBRIGATORIOS = {
    "nome": "Nome completo", "email": "E-mail", "cpf": "CPF",
    "data_nascimento": "Data de nascimento", "telefone": "Telefone",
    "cep": "CEP", "logradouro": "Logradouro", "bairro": "Bairro", "cidade": "Cidade",
    "nome_mae": "Nome da mãe", "naturalidade": "Naturalidade",
    "nacionalidade": "Nacionalidade", "rg": "RG", "estado_civil": "Estado civil",
    "pis": "PIS/PASEP",
}


class AutocadastroBody(BaseModel):
    token: str
    nome: str = Field(..., min_length=3)
    email: str
    senha: str | None = None  # ignorada — a senha é o CPF (dígitos)
    cpf: str
    data_nascimento: str
    telefone: str
    cep: str
    logradouro: str
    numero: str | None = None
    complemento: str | None = None
    bairro: str
    cidade: str
    uf: str | None = None
    nome_mae: str
    naturalidade: str
    nacionalidade: str
    rg: str
    estado_civil: str
    pis: str


def _homolog_ids(db: Session) -> tuple[str, str, str]:
    """(cliente_id, posto_id, posto_nome) da base de homologação — seedados fora daqui."""
    row = db.execute(
        text(
            "SELECT c.id::text, p.id::text, p.name "
            "FROM posts p JOIN clients c ON c.id = p.client_id WHERE p.code = 'CONECTA-BASE'"
        )
    ).fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="Base de homologação não inicializada (posto Conecta Base ausente).")
    return row[0], row[1], row[2]


def _gerar_turnos(db: Session, employee_id: str, post_id: str, escala: dict, dias: int = 14) -> int:
    """Gera os turnos (shifts) do testador para os próximos `dias`, conforme a escala.

    12x36 = dias alternados; 44h/comercial = seg-sex. Alimenta espelho/fechamento.
    """
    scale_id = db.execute(text("SELECT id::text FROM scales WHERE post_id=:p ORDER BY year DESC, month DESC LIMIT 1"),
                          {"p": post_id}).scalar()
    hoje = date.today()
    criados = 0
    for i in range(dias):
        d = hoje + timedelta(days=i)
        if escala["escala"] == "12x36":
            trabalha = (i % 2 == 0)  # dia sim, dia não
        else:
            trabalha = d.weekday() < 5  # seg-sex
        if not trabalha:
            continue
        db.execute(
            text(
                "INSERT INTO shifts (id, scale_id, post_id, employee_id, shift_date, "
                " planned_start_time, planned_end_time, planned_hours, status, is_active, created_at) "
                "VALUES (gen_random_uuid(), :sc, :p, :e, :d, :ini, :fim, :h, 'scheduled', true, now())"
            ),
            {"sc": scale_id, "p": post_id, "e": employee_id, "d": d,
             "ini": escala["inicio"], "fim": escala["fim"], "h": escala["horas"]},
        )
        criados += 1
    return criados


@router.post("/autocadastro", status_code=201)
def autocadastro(body: AutocadastroBody, db: Session = Depends(get_sync_db_dependency)) -> dict[str, Any]:
    """Autocadastro público (token) de um testador de homologação.

    Valida rigor eSocial, cria employee (is_homologacao) + user (login) + turnos, e
    atribui a escala automaticamente. NÃO toca na folha/eSocial reais.
    """
    if body.token != _TOKEN:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Link de homologação inválido ou expirado.")

    # rigor eSocial: todos os obrigatórios preenchidos
    faltando = [lbl for campo, lbl in _OBRIGATORIOS.items()
                if not str(getattr(body, campo, "") or "").strip()]
    if faltando:
        raise HTTPException(status_code=422, detail=f"Campos obrigatórios faltando: {', '.join(faltando)}")

    email = body.email.strip().lower()
    if db.execute(text("SELECT 1 FROM users WHERE lower(email)=:e"), {"e": email}).fetchone():
        raise HTTPException(status_code=409, detail="Já existe um cadastro com este e-mail.")

    cliente_id, posto_id, posto_nome = _homolog_ids(db)

    # escala round-robin pela contagem de testadores já cadastrados
    n = db.execute(text("SELECT count(*) FROM employees WHERE is_homologacao = true")).scalar() or 0
    esc = _ESCALAS[n % len(_ESCALAS)]
    matricula = f"HOMOLOG-{n + 1:02d}"

    # 1) employee na base de homologação
    employee_id = db.execute(
        text(
            "INSERT INTO employees (id, nome, email, cpf, data_nascimento, telefone, cep, "
            " logradouro, numero, complemento, bairro, cidade, uf, nome_mae, naturalidade, "
            " nacionalidade, rg, estado_civil, pis, cargo, escala_padrao, turno_padrao, "
            " matricula, status, is_homologacao, biometria_facial, cliente_id, cliente_nome, "
            " posto_atual_id, posto_atual_nome, data_inicio_posto, created_at) "
            "VALUES (gen_random_uuid(), :nome, :email, :cpf, :nasc, :tel, :cep, :log, :num, :comp, "
            " :bairro, :cidade, :uf, :mae, :natu, :naci, :rg, :ec, :pis, :cargo, :escala, :turno, "
            " :mat, 'ativo', true, false, :cli, :cli_nome, :posto, :posto_nome, :hoje, now()) "
            "RETURNING id::text"
        ),
        {
            "nome": body.nome.strip(), "email": email, "cpf": body.cpf, "nasc": body.data_nascimento,
            "tel": body.telefone, "cep": body.cep, "log": body.logradouro, "num": body.numero,
            "comp": body.complemento, "bairro": body.bairro, "cidade": body.cidade, "uf": body.uf,
            "mae": body.nome_mae, "natu": body.naturalidade, "naci": body.nacionalidade,
            "rg": body.rg, "ec": body.estado_civil, "pis": body.pis, "cargo": esc["cargo"],
            "escala": esc["escala"], "turno": esc["turno"], "mat": matricula,
            "cli": cliente_id, "cli_nome": "HOMOLOGAÇÃO", "posto": posto_id, "posto_nome": posto_nome,
            "hoje": date.today(),
        },
    ).scalar()

    # 2) login vinculado — SENHA = CPF (dígitos), decisão do Jordan (ninguém esquece).
    import re as _re

    from core.auth.jwt import create_access_token

    cpf_digits = _re.sub(r"\D", "", body.cpf or "")
    user_id = db.execute(
        text(
            "INSERT INTO users (id, email, password_hash, name, role, is_active, employee_id, created_at) "
            "VALUES (gen_random_uuid(), :email, :ph, :name, 'funcionario', true, :eid, now()) "
            "RETURNING id::text"
        ),
        {"email": email, "ph": hash_password(cpf_digits), "name": body.nome.strip(), "eid": employee_id},
    ).scalar()

    # 3) turnos dos próximos dias
    turnos = _gerar_turnos(db, employee_id, posto_id, esc)
    db.commit()

    # auto-login: token p/ o frontend cadastrar o rosto NA MESMA TELA (sem passar por login)
    token = create_access_token(subject=str(user_id))

    return {
        "success": True,
        "employee_id": employee_id,
        "matricula": matricula,
        "cargo": esc["cargo"],
        "escala": esc["escala"],
        "turno": esc["turno"],
        "horario": f'{esc["inicio"]}–{esc["fim"]}',
        "posto": posto_nome,
        "login_email": email,
        "senha_dica": "sua senha é o seu CPF (só números)",
        "access_token": token,
        "turnos_gerados": turnos,
        "proximo_passo": "Cadastre seu rosto agora e comece a bater o ponto.",
        "message": "Cadastro de homologação criado. Bem-vindo(a) à Conecta Base!",
    }


@router.get("/painel")
def painel_homologacao(
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Checklist de homologação por testador: dados, facial, ponto, espelho."""
    rows = db.execute(
        text(
            """
            SELECT e.id::text, e.nome, e.matricula, e.cargo, e.escala_padrao, e.turno_padrao,
                   coalesce(e.biometria_facial, false) AS facial,
                   (SELECT count(*) FROM gp_clock_punches cp WHERE cp.employee_id = e.id) AS batidas,
                   (SELECT count(*) FROM shifts sh WHERE sh.employee_id = e.id AND sh.is_active) AS turnos,
                   -- dados eSocial preenchidos (dos obrigatórios)
                   (CASE WHEN nullif(trim(coalesce(e.telefone,'')),'') IS NOT NULL THEN 1 ELSE 0 END
                  + CASE WHEN nullif(trim(coalesce(e.cep,'')),'') IS NOT NULL THEN 1 ELSE 0 END
                  + CASE WHEN nullif(trim(coalesce(e.nome_mae,'')),'') IS NOT NULL THEN 1 ELSE 0 END
                  + CASE WHEN nullif(trim(coalesce(e.rg,'')),'') IS NOT NULL THEN 1 ELSE 0 END
                  + CASE WHEN nullif(trim(coalesce(e.pis,'')),'') IS NOT NULL THEN 1 ELSE 0 END
                  + CASE WHEN nullif(trim(coalesce(e.naturalidade,'')),'') IS NOT NULL THEN 1 ELSE 0 END
                  + CASE WHEN nullif(trim(coalesce(e.nacionalidade,'')),'') IS NOT NULL THEN 1 ELSE 0 END) AS dados_ok
            FROM employees e
            WHERE e.is_homologacao = true
            ORDER BY e.matricula
            """
        )
    ).fetchall()
    testadores = [
        {
            "employee_id": r[0], "nome": r[1], "matricula": r[2], "cargo": r[3],
            "escala": r[4], "turno": r[5],
            "facial_cadastrada": bool(r[6]), "batidas": int(r[7] or 0),
            "turnos": int(r[8] or 0), "dados_ok": int(r[9] or 0), "dados_total": 7,
            "bateu_ponto": int(r[7] or 0) > 0,
        }
        for r in rows
    ]
    return {
        "total_testadores": len(testadores),
        "com_facial": sum(1 for t in testadores if t["facial_cadastrada"]),
        "bateram_ponto": sum(1 for t in testadores if t["bateu_ponto"]),
        "testadores": testadores,
    }
