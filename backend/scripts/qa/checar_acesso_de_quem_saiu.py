#!/usr/bin/env python3
"""Quem não trabalha mais aqui não entra no sistema.

Origem: 17/09/2026. O Jordan, sobre o app do Antônio logado na conta da Graciene: «cada deve
ter acesso apenas ao que é seu». Puxando o fio, a conta trocada era o menor dos problemas —
havia **13 contas ativas** de gente que não trabalha mais na empresa: 5 demitidos (Keyson,
Lorinaldo, Marcelino, Marta, Thaís), 6 inativos e 1 suspenso. Quatro deles com e-mail
@conectamais.pro, que o dono acreditava existir só para ele e para a Pyetra.

Desativar não apaga nada: ponto, documentos e histórico continuam. Só o login fecha.

    python3 backend/scripts/qa/checar_acesso_de_quem_saiu.py

Linha canônica: `TOTAL: <n> conta(s) ativa(s) de quem saiu`. Exit 1 quando há achado.
"""

from __future__ import annotations

import os
import subprocess
import sys

PG = os.environ.get("QA_PG", "conecta-pro-postgres")
DOCKER = "/usr/bin/docker"  # nosec B607 - absoluto por causa do ruff S607

#: Situações em que a pessoa não deve mais entrar. 'afastado_inss' NÃO entra: quem está
#: afastado segue sendo funcionário, precisa ver holerite e assinar documento.
_FORA = ("demitido", "inativo", "suspenso", "desligado", "rescindido")

_SQL = (
    "SELECT u.email || ' | ' || e.nome || ' | ' || coalesce(e.status,'-') "
    "FROM users u JOIN employees e ON e.id = u.employee_id "
    "WHERE u.is_active = true AND lower(coalesce(e.status,'')) IN ("
    + ", ".join(f"'{s}'" for s in _FORA)
    + ") ORDER BY e.status, e.nome"
)


def main() -> int:
    saida = subprocess.run(  # noqa: S603  # nosec B603 - argv fixo, sem shell
        [DOCKER, "exec", PG, "psql", "-U", "postgres", "-d", "conecta_pro", "-t", "-A", "-c", _SQL],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    ).stdout
    linhas = [ln.strip() for ln in saida.strip().splitlines() if ln.strip()]
    for ln in linhas:
        print(f"  ✗ {ln}")
    print(f"TOTAL: {len(linhas)} conta(s) ativa(s) de quem saiu")
    return 1 if linhas else 0


if __name__ == "__main__":
    sys.exit(main())
