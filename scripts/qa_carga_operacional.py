#!/usr/bin/env python3
"""Teste de CARGA do módulo Operacional — em produção, com trava de aborto.

Isto roda contra o sistema que as pessoas estão usando. O teste é desenhado para
PARAR antes de atrapalhar, não para achar o limite a qualquer custo:

  · SÓ LEITURA. Nenhum endpoint de escrita, nenhum de ponto, nada de dinheiro.
    Bater ponto é o que não pode falhar num fim de turno — fica fora.
  · RAMPA CURTA. 1 → 2 → 5 → 10 → 20 simultâneos, rajadas curtas, com pausa entre
    elas para o sistema respirar.
  · ABORTA SOZINHO em qualquer um destes:
      - um único 5xx
      - p95 acima de 4× a linha de base
      - memória do backend acima de 5,2 GiB (o teto do container é 6 GiB; estourar
        mataria produção, e às 18h de sexta tem gente batendo ponto)

O alvo é /redesign/data/operacional: é a leitura mais cara e mais realista do
módulo — monta ~100 telas numa requisição. Se ela aguenta, o resto aguenta.

    export QA_TOKEN=...
    python3 scripts/qa_carga_operacional.py
"""
from __future__ import annotations

import concurrent.futures as cf
import os
import statistics
import subprocess
import sys
import time
import urllib.request

BASE = "https://erp.conectamais.pro"
TOKEN = os.getenv("QA_TOKEN", "").strip()

ALVOS = [
    ("dispatcher operacional (~100 telas)", "/api/v1/redesign/data/operacional"),
    ("presença ao vivo", "/api/v1/operacional/presenca/hoje"),
    ("dashboard operacional", "/api/v1/operacional/dashboard/"),
]

DEGRAUS = [1, 2, 5, 10, 20]
POR_DEGRAU = 20          # requisições por degrau
PAUSA = 3                # segundos entre degraus, p/ o sistema respirar
TETO_MEM_GIB = 5.2       # container tem 6 GiB
FATOR_P95 = 4.0


def mem_backend_gib() -> float:
    try:
        r = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}",
                            "conecta-pro-backend"], capture_output=True, text=True, timeout=25)
        bruto = r.stdout.split("/")[0].strip()          # ex.: "3.948GiB"
        if bruto.endswith("GiB"):
            return float(bruto[:-3])
        if bruto.endswith("MiB"):
            return float(bruto[:-3]) / 1024
    except Exception:  # noqa: BLE001
        pass
    return -1.0


def uma(url: str) -> tuple[int, float]:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            r.read()
            return r.status, time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        return e.code, time.perf_counter() - t0
    except Exception:  # noqa: BLE001
        return 0, time.perf_counter() - t0


def rajada(url: str, n: int, simultaneos: int) -> tuple[list[float], list[int]]:
    lat: list[float] = []
    cods: list[int] = []
    with cf.ThreadPoolExecutor(max_workers=simultaneos) as ex:
        for cod, dt in ex.map(lambda _: uma(url), range(n)):
            cods.append(cod)
            lat.append(dt)
    return lat, cods


def pct(v: list[float], p: float) -> float:
    if not v:
        return 0.0
    s = sorted(v)
    return s[min(len(s) - 1, int(len(s) * p))]


def main() -> int:
    if not TOKEN:
        print("Defina QA_TOKEN.")
        return 2

    print(f"memória do backend antes: {mem_backend_gib():.2f} GiB (teto 6 GiB)\n")
    abortou = False

    for rotulo, caminho in ALVOS:
        url = BASE + caminho
        print(f"── {rotulo}")

        # linha de base: 3 sequenciais, o menor tempo manda (menos ruído)
        base_lat = [uma(url)[1] for _ in range(3)]
        base = min(base_lat)
        cod0, _ = uma(url)
        if cod0 != 200:
            print(f"   pulando: devolve HTTP {cod0}\n")
            continue
        print(f"   base (1 req): {base * 1000:.0f} ms")

        for sim in DEGRAUS:
            mem = mem_backend_gib()
            if mem > TETO_MEM_GIB:
                print(f"   ⛔ ABORTADO: backend em {mem:.2f} GiB (teto de segurança {TETO_MEM_GIB})")
                abortou = True
                break

            lat, cods = rajada(url, POR_DEGRAU, sim)
            erros = [c for c in cods if c >= 500 or c == 0]
            p50, p95 = pct(lat, 0.5), pct(lat, 0.95)
            vazao = POR_DEGRAU / sum(lat) * sim if sum(lat) else 0

            marca = ""
            if erros:
                marca = f"  ⛔ {len(erros)} erro(s) {sorted(set(erros))}"
            elif p95 > base * FATOR_P95:
                marca = f"  ⚠️ p95 {p95 / base:.1f}× a base"

            print(f"   {sim:2d} simultâneo(s): p50={p50 * 1000:6.0f} ms  p95={p95 * 1000:6.0f} ms  "
                  f"~{vazao:4.1f} req/s  mem={mem:.2f} GiB{marca}")

            if erros:
                print("   ⛔ ABORTADO: apareceu erro 5xx — não insisto em produção.")
                abortou = True
                break
            time.sleep(PAUSA)
        print()

    print(f"memória do backend depois: {mem_backend_gib():.2f} GiB")
    return 1 if abortou else 0


if __name__ == "__main__":
    raise SystemExit(main())
