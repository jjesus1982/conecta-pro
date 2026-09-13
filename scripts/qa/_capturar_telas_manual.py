#!/usr/bin/env python3
"""Captura as telas do redesign para o MANUAL do sistema (13/09/2026).

Faz login de verdade, espera a tela parar de dizer "carregando…" e salva o PNG em
uploads/manual_prints/ — que é `/app/uploads/manual_prints` dentro do backend, o caminho que
`gerar_apresentacao` lê no bloco {"tipo":"imagem"}.

Uso: python3 scripts/qa/_capturar_telas_manual.py [modulo ...]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.getenv("MANUAL_BASE", "https://erp.conectamais.pro")
USER = os.getenv("MANUAL_USER", "jjesus@conectamais.pro")
PWD = os.getenv("MANUAL_PWD", "")
OUT = Path("/opt/conecta-pro/uploads/manual_prints")

#: Telas cujo filtro abre no PRIMEIRO item e mostram pouca coisa: escolhe a opção que
#: representa melhor a tela no manual (não é maquiagem — é a mesma tela, outro filtro).
ESCOLHER: dict[str, str] = {
    "op-mapa-de-ponto": "Residencial Laranjeiras Village",
}

#: (arquivo, módulo, aba). Aba vazia = tela inicial do módulo.
TELAS: list[tuple[str, str, str]] = [
    ("op-visao-geral", "operacional", ""),
    ("op-grid-real-contratual", "operacional", "grid-real-contratual"),
    ("op-mapa-de-ponto", "operacional", "mapa-de-ponto"),
    ("dp-visao-geral", "departamento-pessoal", ""),
    ("dp-mapa-ferias", "departamento-pessoal", "mapa-ferias"),
    ("dp-beneficio-conferencia", "departamento-pessoal", "beneficio-conferencia"),
    ("gp-visao-geral", "gestao-de-pessoas", ""),
    ("gp-vigilante-aptidao", "gestao-de-pessoas", "vigilante-aptidao"),
    ("gp-uniforme-grade", "gestao-de-pessoas", "uniforme-grade"),
    ("fin-visao-geral", "financeiro", ""),
    ("crm-dashboard", "crm", ""),
    ("crm-calculado-vs-faturado", "crm", "calculado-vs-faturado"),
    ("eq-visao-geral", "equipamentos", ""),
    ("eq-frota-painel", "equipamentos", "frota-painel"),
    ("eq-avaliacao-dashboard", "equipamentos", "avaliacao-dashboard"),
]


def main() -> int:
    if not PWD:
        print("defina MANUAL_PWD"); return 2
    OUT.mkdir(parents=True, exist_ok=True)
    alvo = sys.argv[1:] or None
    with sync_playwright() as pw:
        nav = pw.chromium.launch(args=["--no-sandbox"])
        ctx = nav.new_context(viewport={"width": 1600, "height": 900}, device_scale_factor=2)
        pg = ctx.new_page()
        pg.goto(f"{BASE}/login", wait_until="domcontentloaded", timeout=90_000)
        pg.fill("input[type=email], input[name=email], input[name=username]", USER)
        pg.fill("input[type=password]", PWD)
        pg.click("button[type=submit]")
        pg.wait_for_timeout(9_000)
        print("login:", pg.url)
        for nome, mod, aba in TELAS:
            if alvo and mod not in alvo:
                continue
            url = f"{BASE}/redesign/{mod}" + (f"?t={aba}" if aba else "")
            try:
                pg.goto(url, wait_until="domcontentloaded", timeout=90_000)
                # a tela do redesign monta em duas fases: espera sumir o "carregando…"
                for _ in range(40):
                    if "carregando…" not in (pg.inner_text("body") or ""):
                        break
                    pg.wait_for_timeout(1_200)
                if (op := ESCOLHER.get(nome)):
                    for sel in pg.query_selector_all("select"):
                        if any(op in (o.inner_text() or "") for o in sel.query_selector_all("option")):
                            sel.select_option(label=op)
                            pg.wait_for_timeout(2_500)
                            break
                pg.wait_for_timeout(2_500)
                dest = OUT / f"{nome}.png"
                pg.screenshot(path=str(dest))
                print(f"  ok {nome}.png  ({dest.stat().st_size // 1024} KB)")
            except Exception as e:  # noqa: BLE001 — uma tela ruim não derruba as outras
                print(f"  x  {nome}: {e}")
        nav.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
