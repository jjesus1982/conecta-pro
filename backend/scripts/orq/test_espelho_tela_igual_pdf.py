#!/usr/bin/env python3
"""A tela de conferência e o PDF assinado têm de dizer o MESMO número.

Origem: 15/09/2026. O Jordan pediu para ver a folha de ponto individual «para depois mandar
pra ele assinar e a empresa também». Fui conferir e os dois lados discordavam. Mesmo
colaborador (ADAILSON SERRA ALVES), mesma competência 09/2026:

                          tela        PDF (o documento assinado)
    dias trabalhados      12          6
    horas trabalhadas     60:53       54:58
    horas previstas       90:00       88:00
    saldo                 -29:07      -33:02

Eram dois motores. O PDF lê `time_sheets`, gravado por `espelho_service.calcular_espelho`,
que junta o turno noturno: 19:01 → 07:02, intervalo 00:59, 11:01 — Portaria 671 correta. A
tela recalculava por conta própria em `PunchService.get_espelho_mensal` e PARTIA o turno na
meia-noite, virando dois «dias» de ~6h. Medido em setembro: 115 pares de batidas cruzando a
meia-noite, em 21 pessoas — a portaria noturna inteira.

O risco não é cosmético. Quem confere na tela e manda assinar está aprovando um documento que
diz outra coisa, e o que vale juridicamente é o PDF.

## A regra afirmada

Para todo colaborador com espelho calculado no mês, o que a rota da tela devolve tem de bater
com `time_sheets` — a fonte do PDF — em horas trabalhadas, horas previstas, saldo e dias.
Não é «os dois estão certos»: é «os dois são o mesmo número». Se o motor mudar, muda para os
dois de uma vez, porque passa a existir um só.

    QA_SENHA=... python3 backend/scripts/orq/test_espelho_tela_igual_pdf.py

Linha canônica: `TOTAL: <n> divergência(s) entre tela e PDF`. Exit 1 quando há achado.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

API = os.environ.get("QA_API", "http://127.0.0.1:8080")
USUARIO = os.environ.get("QA_USER", "jjesus@conectamais.pro")
SENHA = os.environ.get("QA_SENHA", "JsJ618908@#%")
MES = int(os.environ.get("QA_MES", "9"))
ANO = int(os.environ.get("QA_ANO", "2026"))

#: Quantos colaboradores conferir. Divergência de motor é sistêmica, não amostral — uma dúzia
#: já denuncia. Conferir os 51 a cada rodada custaria minutos sem dizer nada a mais.
QUANTOS = int(os.environ.get("QA_QUANTOS", "12"))

PG = os.environ.get("QA_PG_CONTAINER", "conecta-pro-postgres")
DOCKER = os.environ.get("QA_DOCKER", "/usr/bin/docker")


def _sql(q: str) -> list[list[str]]:
    r = subprocess.run(  # noqa: S603
        [DOCKER, "exec", PG, "psql", "-U", "postgres", "-d", "conecta_pro", "-t", "-A", "-F|", "-c", q],
        capture_output=True,
        timeout=120,
        check=False,
    )
    return [ln.split("|") for ln in r.stdout.decode("utf8", "ignore").strip().splitlines() if ln.strip()]


def _token() -> str | None:
    dados = urllib.parse.urlencode({"username": USUARIO, "password": SENHA}).encode()
    req = urllib.request.Request(
        f"{API}/api/v1/auth/login",
        data=dados,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310  # nosec B310 - QA_API local
            return json.load(r).get("access_token")
    except Exception as e:  # noqa: BLE001
        print(f"   login falhou: {e}")
        return None


def _min(hhmm: str | None) -> int | None:
    """'11:01' -> 661. Aceita negativo ('-29:07'). None quando não dá para ler."""
    if not hhmm or ":" not in str(hhmm):
        return None
    s = str(hhmm).strip()
    neg = s.startswith("-")
    try:
        h, m = (s.lstrip("-")).split(":")[:2]
        v = int(h) * 60 + int(m)
    except ValueError:
        return None
    return -v if neg else v


sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from _fixtures import exige_host  # noqa: E402


def main() -> int:
    exige_host("compara a tela com o PDF por docker")
    tok = _token()
    if not tok:
        return 2

    linhas = _sql(
        "SELECT CAST(employee_id AS TEXT), coalesce(employee_name,'—'), "
        "coalesce(hours_worked_minutes,0), coalesce(hours_expected_minutes,0), "
        "coalesce(hours_balance_minutes,0), coalesce(work_days_worked,0) "
        f"FROM time_sheets WHERE reference_month={MES} AND reference_year={ANO} "
        "AND coalesce(is_deleted,false)=false ORDER BY employee_name "
        f"LIMIT {QUANTOS};"
    )
    if len(linhas) < 3:
        print(f"RECUSO: só {len(linhas)} espelho(s) calculado(s) em {MES:02d}/{ANO} — nada a comparar")
        return 2

    achados = 0
    for eid, nome, trab, prev, saldo, dias in linhas:
        req = urllib.request.Request(
            f"{API}/api/v1/people-management/ponto/espelho/{eid}?month={MES}&year={ANO}",
            headers={"Authorization": f"Bearer {tok}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310  # nosec B310 - QA_API local
                tela = json.load(r)
        except Exception as e:  # noqa: BLE001
            print(f"   {nome}: a tela não respondeu ({e})")
            achados += 1
            continue

        # PDF/time_sheets em minutos; a tela devolve HH:MM.
        pares = [
            ("horas trabalhadas", _min(tela.get("total_trabalhado")), int(trab or 0)),
            ("horas previstas", _min(tela.get("horas_esperadas")), int(prev or 0)),
            ("saldo", _min(tela.get("saldo")), int(saldo or 0)),
            ("dias", tela.get("total_dias"), int(dias or 0)),
        ]
        ruins = [(o, t, p) for o, t, p in pares if t is not None and int(t) != int(p)]
        if ruins:
            achados += 1
            print(f"   {nome}:")
            for o, t, p in ruins:
                print(f"       {o:20s} tela={t!s:>8}  PDF={p!s:>8}")

    print(f"\n   {len(linhas)} colaborador(es) conferido(s) em {MES:02d}/{ANO}")
    print(f"\nTOTAL: {achados} divergência(s) entre tela e PDF")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
