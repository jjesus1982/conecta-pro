#!/usr/bin/env python3
"""Varredura de TELA do redesign — abre cada item de menu de cada módulo e registra o que
aconteceu. NÃO submete nada: só navega e observa.

Por que existe: ~120 telas foram ligadas e verificadas com `build()` real contra o banco,
mas "monta no builder" não é "pinta no navegador" — a distinção que já pegou defeito real
aqui (o painel de resultado do fiscal). Isto fecha essa lacuna sem clicar em nada que grave.

SEGURANÇA
  · só clica em item de MENU lateral; nunca em botão de formulário, ação ou documento
  · headless, contexto próprio, fecha o navegador no fim (não mata chromium de ninguém)
  · qualquer falha numa tela é registrada e a varredura segue

Uso:  python3 scripts/varredura_telas_redesign.py [modulo ...]
Saída: auditoria/qa/varredura_telas_<AAAAMMDD>.md  (escrita incremental — dá para ler
       antes de terminar)
"""
from __future__ import annotations

import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://erp.conectamais.pro"
RAIZ = Path("/opt/conecta-pro")
MODULOS = [
    "crm", "financeiro", "operacional", "rh", "documentos", "area-do-cliente",
    "licitacoes", "integracoes", "seguranca", "empresas", "assistente",
    "gestao-de-pessoas", "portal-do-funcionario", "saude-ocupacional", "relatorios",
    "juridico", "fiscal", "departamento-pessoal", "marketing", "aprovacoes",
]
# Ruído conhecido do app, não é defeito da tela.
IGNORAR_ERRO = re.compile(r"(favicon|apple-mobile-web-app|ERR_NETWORK_CHANGED|net::ERR_ABORTED)", re.I)


def cred() -> tuple[str, str]:
    env = (RAIZ / ".env").read_text()
    return (re.search(r"^ERP_USER=(.*)$", env, re.M).group(1).strip(),
            re.search(r"^ERP_PASS=(.*)$", env, re.M).group(1).strip())


LE_CONTEUDO = """() => {
  const ms = [...document.querySelectorAll('main')];
  const m = ms[ms.length - 1];
  if (!m) return { vazio: true, titulo: '', chars: 0 };
  const txt = m.innerText.trim();
  return {
    titulo: txt.split('\\n')[0] || '',
    chars: txt.length,
    // "vazio" = renderizou a casca e nada dentro. Form legítimo tem campos; tabela sem
    // linha é honesta e traz cabeçalho — por isso o corte é baixo.
    vazio: txt.length < 25,
    campos: m.querySelectorAll('input,textarea,select').length,
    linhas: m.querySelectorAll('.rd-tbl-row, [class*="tbl-row"]').length,
  };
}"""


def main() -> int:
    alvos = sys.argv[1:] or MODULOS
    u, p = cred()
    saida = RAIZ / "auditoria" / "qa" / f"varredura_telas_{datetime.now():%Y%m%d}.md"
    saida.parent.mkdir(parents=True, exist_ok=True)
    linhas: list[str] = [
        f"# Varredura de tela do redesign — {datetime.now():%d/%m/%Y %H:%M}",
        "",
        "Abre cada item de menu de cada módulo e registra o que aconteceu. **Nada foi",
        "submetido** — a varredura só navega. Erro de console filtrado do ruído conhecido",
        "(favicon, meta deprecada, rede).",
        "",
    ]
    saida.write_text("\n".join(linhas))
    tot = {"telas": 0, "vazias": 0, "erro": 0, "falha": 0}

    with sync_playwright() as pw:
        nav = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = nav.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        erros: list[str] = []
        pg.on("console", lambda m: erros.append(m.text[:160]) if m.type == "error" else None)

        pg.goto(f"{BASE}/login", wait_until="commit", timeout=60000)
        pg.wait_for_timeout(6000)
        pg.fill('input[placeholder="seu@email.com"]', u)
        pg.fill('input[placeholder="••••••••"]', p)
        pg.click('button:has-text("Entrar")')
        pg.wait_for_url("**/redesign**", timeout=60000)

        for mod in alvos:
            t0 = time.time()
            try:
                pg.goto(f"{BASE}/redesign/{mod}?_cb=sweep", wait_until="commit", timeout=60000)
                pg.wait_for_timeout(6000)
                pg.wait_for_selector("nav button", timeout=45000)
                itens = pg.eval_on_selector_all(
                    "nav button", "els => els.map(e => (e.title || e.textContent).trim())")
            except Exception as exc:  # noqa: BLE001
                linhas += [f"## {mod}", "", f"⚠️ **não abriu**: {type(exc).__name__}", ""]
                saida.write_text("\n".join(linhas))
                tot["falha"] += 1
                continue

            achados: list[str] = []
            for item in itens:
                erros.clear()
                tot["telas"] += 1
                try:
                    pg.click(f'nav button:has-text("{item}")', timeout=15000)
                    pg.wait_for_timeout(1400)
                    info = pg.evaluate(LE_CONTEUDO)
                except Exception as exc:  # noqa: BLE001
                    tot["falha"] += 1
                    achados.append(f"| {item} | — | ❌ falhou: {type(exc).__name__} |")
                    continue
                reais = [e for e in erros if not IGNORAR_ERRO.search(e)]
                marca = []
                if info["vazio"]:
                    marca.append("⚠️ vazia")
                    tot["vazias"] += 1
                if reais:
                    marca.append(f"❌ {len(reais)} erro(s): {reais[0][:70]}")
                    tot["erro"] += 1
                if marca:
                    detalhe = f"{info['campos']} campos · {info['linhas']} linhas"
                    achados.append(f"| {item} | {detalhe} | {' · '.join(marca)} |")

            dur = time.time() - t0
            linhas += [f"## {mod} — {len(itens)} telas em {dur:.0f}s", ""]
            if achados:
                linhas += ["| Tela | Conteúdo | Achado |", "|---|---|---|", *achados, ""]
            else:
                linhas += ["✅ todas abriram com conteúdo e sem erro de console.", ""]
            saida.write_text("\n".join(linhas))

        ctx.close()
        nav.close()

    linhas += [
        "## Resumo",
        "",
        f"- telas abertas: **{tot['telas']}**",
        f"- vazias (casca sem conteúdo): **{tot['vazias']}**",
        f"- com erro de console: **{tot['erro']}**",
        f"- não abriram: **{tot['falha']}**",
        "",
        "⚠️ Isto prova que a tela RENDERIZA. Não prova que o submit funciona — nenhum",
        "formulário foi enviado, porque os de escrita gravariam de verdade.",
    ]
    saida.write_text("\n".join(linhas))
    print(f"varredura concluída → {saida}")
    print(f"telas={tot['telas']} vazias={tot['vazias']} erro={tot['erro']} falha={tot['falha']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
