#!/usr/bin/env python3
"""Tela do /redesign que demora mais que o teto — a que o supervisor abandona.

Risco 4 do pré-mortem da frente 4 (12/09/2026): *"vai ficar pesado e ninguém vai abrir"*.
Matriz cliente × dia × posto recalculada a cada abertura é consulta lenta, e `consultar_kits`
já deu **ReadTimeout** na primeira batida de 11/09. Tela que demora é tela que não é usada —
e o custo não aparece em nenhum log, porque o HTTP responde 200.

Mede o que o navegador espera: `GET /api/v1/redesign/data/<slug>` com token real, uma vez por
módulo, e compara com o teto. Mede DUAS vezes e vale a SEGUNDA: a primeira abertura do
processo paga import de módulo e conexão de pool, que o usuário paga uma vez por deploy e não
por tela — na medição de 12/09 a diferença foi de 78 s (primeira) para 0,6 s (segunda), e
reportar os 78 s como "a tela" seria tão falso quanto ignorá-los.

    python3 backend/scripts/qa/checar_tela_lenta.py                     # staging (8081)
    QA_BASE=http://127.0.0.1:8204 python3 backend/scripts/qa/checar_tela_lenta.py
    QA_TETO_S=3 QA_SLUGS=operacional,financeiro python3 backend/scripts/qa/checar_tela_lenta.py

LIMITES:
- Mede a API, não o navegador: render do React e rede do cliente ficam de fora.
- Sem base de pé, RECUSA (exit 2) em vez de sair verde — fila vazia não é resultado.
- Slug que devolve 403 para o usuário do teste é PULADO e dito em voz alta (não é lentidão).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.getenv("QA_BASE", "http://127.0.0.1:8081")
TETO_S = float(os.getenv("QA_TETO_S", "3"))
USER = os.getenv("QA_USER", "jjesus@conectamais.pro")
SENHA = os.getenv("QA_SENHA", "JsJ618908@#%")
TIMEOUT = float(os.getenv("QA_TIMEOUT_S", "120"))

#: Os módulos que carregam grade/tabela grande. `operacional` é o da frente 4 (mês inteiro).
SLUGS = [s for s in os.getenv(
    "QA_SLUGS",
    "operacional,departamento-pessoal,financeiro,rh,crm,gestao-de-pessoas").split(",") if s]


def _token() -> str:
    dados = urllib.parse.urlencode({"username": USER, "password": SENHA}).encode()
    req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=dados,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310
        return json.load(r)["access_token"]


def _medir(slug: str, tok: str) -> tuple[float, int, int]:
    """(segundos, http, telas). Erro de rede vira (-1, 0, 0) — não é lentidão, é queda."""
    req = urllib.request.Request(f"{BASE}/api/v1/redesign/data/{slug}",
                                 headers={"Authorization": f"Bearer {tok}"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310
            corpo = json.load(r)
            return time.monotonic() - t0, r.status, len(corpo.get("wired") or [])
    except urllib.error.HTTPError as e:
        return time.monotonic() - t0, e.code, 0
    except Exception:  # noqa: BLE001
        return -1.0, 0, 0


def main() -> int:
    try:
        tok = _token()
    except Exception as exc:  # noqa: BLE001
        print(f"RECUSO: {BASE} não autenticou ({exc}) — sem base de pé este check não mede nada, "
              f"e sair verde por isso seria pior que não rodar.")
        return 2

    lentas = 0
    for slug in SLUGS:
        _frio, http, _ = _medir(slug, tok)      # descarta: import/pool do processo
        seg, http, telas = _medir(slug, tok)
        if http == 403:
            print(f"  {slug}: 403 para {USER} — pulado (permissão, não lentidão)")
            continue
        if seg < 0 or http != 200:
            print(f"  {slug}: NÃO RESPONDEU (http {http}) — isso não é lentidão, é queda")
            lentas += 1
            continue
        marca = "LENTA" if seg > TETO_S else "ok"
        print(f"  {slug}: {seg:.2f}s ({telas} telas) · frio {_frio:.2f}s · teto {TETO_S:.0f}s · {marca}")
        lentas += seg > TETO_S
    print(f"TOTAL telas lentas: {lentas}")
    return 1 if lentas else 0


if __name__ == "__main__":
    sys.exit(main())
