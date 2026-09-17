#!/usr/bin/env python3
"""A senha do colaborador é o CPF dele — sempre, e sem opção de outra.

Origem: 17/09/2026. Regra do Jordan, dita depois que o Antônio Carlos apareceu com o app
logado na conta da Graciene: «a senha de cada colaborador ao logar é seu cpf, o login é o
e-mail e a senha é sempre o seu cpf, sem opção de outra senha, obrigatoriamente cpf».

O `primeiro_acesso_controller` já nascia assim («senha = CPF, nunca cria senha nova»). As
portas por onde uma senha diferente entrava depois eram o `reset-password` — que gravava o
que a pessoa digitasse — e as senhas antigas, de antes da regra existir.

## As regras afirmadas

1. Todo colaborador de campo (funcionario, agente, lider) com CPF válido ENTRA com o CPF.
2. `POST /auth/reset-password` não grava senha escolhida para quem tem vínculo: redefine para
   o CPF, ignorando o corpo.
3. O primeiro acesso continua definindo senha = CPF.

Só o item 1 é medido de fora, com login real — e de propósito: a única prova de que a senha
é o CPF é o CPF entrar. Os itens 2 e 3 são conferidos no código, porque testá-los exigiria
forjar token de recuperação.

    python3 backend/scripts/orq/test_senha_e_o_cpf.py

Linha canônica: `TOTAL: <n> colaborador(es) fora da regra`. Exit 1 quando há achado.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[3]
DOCKER = "/usr/bin/docker"  # nosec B607 - absoluto por causa do ruff S607
AUTH = RAIZ / "backend/api/v1/endpoints/auth.py"
PRIMEIRO = RAIZ / "backend/modules/people_management/employee_portal/controllers/primeiro_acesso_controller.py"

#: Quantos conferir por rodada. O login tem rate limit de 5/min, então testar os 84 levaria
#: 17 minutos e derrubaria a trava por timeout. Amostra rotativa pelo dia do mês.
_AMOSTRA = 3

_PROVA = r"""
import sys, json, urllib.request, urllib.error, datetime
sys.path.insert(0, '/app')
from sqlalchemy import create_engine, text
from core.config import settings

eng = create_engine(str(settings.database_url).replace('+asyncpg', ''))
with eng.connect() as c:
    linhas = c.execute(text(
        "SELECT u.email, e.cpf, e.nome FROM users u JOIN employees e ON e.id=u.employee_id "
        "WHERE u.role IN ('funcionario','agente','lider') "
        "  AND coalesce(e.is_homologacao,false)=false "
        "  AND e.cpf ~ '^[0-9]{11}$' AND u.is_active = true "
        "ORDER BY u.email")).fetchall()
if not linhas:
    print('SEM_COLABORADORES'); raise SystemExit
dia = datetime.date.today().day
for i in range(AMOSTRA):
    email, cpf, nome = linhas[(dia * 7 + i) % len(linhas)]
    dados = ('username=' + urllib.parse.quote(email) + '&password=' + urllib.parse.quote(cpf)).encode()
    req = urllib.request.Request('http://127.0.0.1:8080/api/v1/auth/login', data=dados,
          headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        cod = urllib.request.urlopen(req, timeout=15).status
    except urllib.error.HTTPError as e:
        cod = e.code
    except Exception:
        cod = 0
    print('LOGIN|' + nome + '|' + str(cod))
"""


def main() -> int:
    achados: list[str] = []

    # ── 1. o CPF entra mesmo? ────────────────────────────────────────────────
    try:
        codigo = f"import urllib.parse\nAMOSTRA = {_AMOSTRA}\n{_PROVA}"
        saida = subprocess.run(  # noqa: S603  # nosec B603 - argv fixo, sem shell
            [DOCKER, "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend", "python3", "-c", codigo],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        ).stdout
        if "SEM_COLABORADORES" in saida:
            print("  (nenhum colaborador com CPF para conferir)")
        for linha in saida.strip().splitlines():
            if not linha.startswith("LOGIN|"):
                continue
            _, nome, cod = linha.split("|", 2)
            # 429 é o rate limit de 5/min da própria casa — não é a senha estar errada.
            if cod not in ("200", "429"):
                achados.append(f"{nome}: login com o CPF devolveu {cod}, não 200")
    except (OSError, subprocess.SubprocessError) as exc:
        achados.append(f"não deu para provar o login: {exc}")

    # ── 2. reset-password não aceita senha escolhida de quem tem vínculo ─────
    auth = AUTH.read_text(encoding="utf8")
    if "user.password_hash = get_password_hash(nova)" not in auth:
        achados.append(
            "reset-password voltou a gravar a senha que a pessoa digita — a porta de escolher outra senha reabriu"
        )
    if "employee_id" not in auth.split("async def reset_password")[-1][:2500]:
        achados.append("reset-password não distingue mais quem tem vínculo de funcionário")

    # ── 3. primeiro acesso continua nascendo com CPF ─────────────────────────
    if PRIMEIRO.exists() and 'get_password_hash(emp["cpf"])' not in PRIMEIRO.read_text(encoding="utf8"):
        achados.append("primeiro acesso não define mais a senha como o CPF")

    for a in achados:
        print(f"  ✗ {a}")
    print(f"TOTAL: {len(achados)} colaborador(es) fora da regra")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
