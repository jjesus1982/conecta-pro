#!/usr/bin/env python3
"""Cada um só bate e só vê o PRÓPRIO ponto.

Origem: 17/09/2026. O Antônio Carlos Castro Gama mandou print do app dele mostrando «Olá,
GRACIENE» e bateu a entrada dela às 08:05 no Condomínio Prime Arena — ele é do Mirante das
Flores. O Jordan: «precisamos corrigir isso e verificar se outros não estão com o mesmo
problema, cada deve ter acesso apenas ao que é seu».

O vínculo no banco estava CERTO (o user dele aponta para o employee dele). O buraco era nas
rotas:

  · `POST /ponto/batida` recebia `employee_id` NO CORPO e gravava para quem viesse ali,
    sem conferir de quem era o token. Qualquer pessoa logada batia ponto por qualquer colega.
  · `GET /ponto/batidas/{employee_id}` devolvia a jornada de qualquer um para qualquer
    logado — bastava saber o UUID.
  · E nenhuma das 1.372 batidas dos 15 dias anteriores tinha `created_by`, `device_id`,
    `ip_address` ou `user_agent`: as quatro colunas existem e nada as preenchia. Não havia
    como sequer PERGUNTAR quem bateu por quem.

## As regras afirmadas

1. A rota de bater ponto exige usuário autenticado e tira o dono do TOKEN. Gestor pode bater
   por outro (correção de DP é trabalho real), e aí fica registrado em `created_by`.
2. A rota que lê o ponto de um id exige ser o dono ou gestor.
3. Batida nova nasce com `created_by` preenchido — sem autor, não há auditoria possível.

    python3 backend/scripts/orq/test_ponto_so_o_seu.py

Linha canônica: `TOTAL: <n> porta(s) aberta(s) no ponto`. Exit 1 quando há achado.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[3]
SVC = RAIZ / "backend/modules/people_management/ponto/services/punch_service.py"
DOCKER = "/usr/bin/docker"  # nosec B607 - absoluto por causa do ruff S607


def _corpo_da_rota(fonte: str, decorator: str) -> str:
    """Devolve o texto da função logo abaixo do decorator dado."""
    i = fonte.find(decorator)
    if i < 0:
        return ""
    j = fonte.find("\n@router.", i + 1)
    return fonte[i : j if j > 0 else len(fonte)]


#: Python executado DENTRO do container: gera um token de funcionário de homologação e
#: chama as rotas de verdade. Medir a SAÍDA e não o texto do arquivo é o ponto: a primeira
#: versão desta trava procurava as strings `current_user` e `_PODE_BATER_POR_OUTRO` no corpo
#: da função, e duas sabotagens passaram — as strings continuavam presentes noutro trecho.
_PROVA = r"""
import sys, json, urllib.request, urllib.error
sys.path.insert(0, '/app')
from core.auth.jwt import create_access_token
from sqlalchemy import create_engine, text
from core.config import settings

eng = create_engine(str(settings.database_url).replace('+asyncpg', ''))
with eng.connect() as c:
    linhas = c.execute(text(
        "SELECT u.id::text, e.id::text FROM users u JOIN employees e ON e.id=u.employee_id "
        "WHERE coalesce(e.is_homologacao,false)=true AND u.role='funcionario' "
        "ORDER BY u.email LIMIT 2")).fetchall()
if len(linhas) < 2:
    print('SEM_COORTE'); raise SystemExit
(uid_a, eid_a), (uid_b, eid_b) = linhas
tok = create_access_token(subject=uid_a)

BASE = 'http://127.0.0.1:8080/api/v1/people-management/ponto'

def chamar(metodo, url, corpo=None):
    req = urllib.request.Request(url, method=metodo,
        data=json.dumps(corpo).encode() if corpo else None,
        headers={'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0

# A tenta LER o ponto de B
print('LER_DE_OUTRO', chamar('GET', BASE + '/batidas/' + eid_b + '?data=2026-01-01'))
# A tenta BATER por B  (employee_id de B no corpo)
print('BATER_POR_OUTRO', chamar('POST', BASE + '/batida',
      {'employee_id': eid_b, 'punch_type': 'entrada'}))
# O funcionário NÃO usa /ponto/* — essas rotas são do módulo 'dp' e o guard de módulo já o
# barra, inclusive no próprio ponto. Ele bate e consulta pelo portal. Exigir 200 aqui seria
# cobrar algo que nunca existiu (a primeira versão desta trava cobrava, e acusou o certo).
# O que se mede é o gestor: ele PRECISA continuar passando, senão a trava quebrou o DP.
with eng.connect() as c:
    g = c.execute(text(
        # 'all' ou 'module:dp' — um admin com permissions vazio é barrado pelo guard de
        # módulo e daria falso positivo (aconteceu com admin@conectamais.pro).
        "SELECT u.id::text FROM users u WHERE u.is_active AND ("
        "  u.permissions::text ILIKE '%all%' OR u.permissions::text ILIKE '%module:dp%') "
        "ORDER BY u.email LIMIT 1")).fetchone()
if g:
    tok = create_access_token(subject=g[0])
    print('GESTOR_LE', chamar('GET', BASE + '/batidas/' + eid_b + '?data=2026-01-01'))
"""


sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from _fixtures import exige_host  # noqa: E402


def main() -> int:
    exige_host("lê o código-fonte do backend no repositório")
    achados: list[str] = []

    # ── A prova que vale: o que as rotas FAZEM, com um token real de funcionário ──
    try:
        saida = subprocess.run(  # noqa: S603  # nosec B603 - argv fixo, sem shell
            [DOCKER, "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend", "python3", "-c", _PROVA],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        ).stdout
        res = dict(linha.split(" ", 1) for linha in saida.strip().splitlines() if " " in linha)
        if "SEM_COORTE" in saida:
            print("  (sem coorte de homologação para testar — regras não conferidas)")
        else:
            if res.get("LER_DE_OUTRO") != "403":
                achados.append(
                    f"funcionário LEU o ponto de um colega e recebeu {res.get('LER_DE_OUTRO')}, "
                    "não 403 — bastava saber o UUID"
                )
            if res.get("BATER_POR_OUTRO") != "403":
                achados.append(
                    f"funcionário BATEU ponto por um colega e recebeu {res.get('BATER_POR_OUTRO')}, "
                    "não 403 — o employee_id do corpo voltou a mandar"
                )
            if res.get("GESTOR_LE") not in ("200", "201", None):
                achados.append(
                    f"GESTOR não consegue mais ler o ponto de um colaborador "
                    f"({res.get('GESTOR_LE')}) — a trava apertou demais e quebrou o DP"
                )
    except (OSError, subprocess.SubprocessError) as exc:
        achados.append(f"não deu para provar as rotas em produção: {exc}")

    # ── E o rastro: sem autor gravado, não há como auditar depois ────────────
    if "created_by=autor_user_id" not in SVC.read_text(encoding="utf8"):
        achados.append("punch_service não grava `created_by`: volta a ser impossível saber quem bateu o ponto de quem")

    for a in achados:
        print(f"  ✗ {a}")
    print(f"TOTAL: {len(achados)} porta(s) aberta(s) no ponto")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
