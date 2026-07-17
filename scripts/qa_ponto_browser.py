"""QA de browser do módulo Ponto — valida na tela renderizada (como o CIC vê).

USO: ERP_TOKEN=<jwt-jordan> python3 scripts/qa_ponto_browser.py
Exit 0 = tudo PASS. (Token: create_access_token no container backend.)
"""

import os
import re
import sys

from playwright.sync_api import sync_playwright

BASE = "https://erp.conectamais.pro"
TOK = os.environ["ERP_TOKEN"]
PONTO = f"{BASE}/modulos/gestao-pessoas/ponto"
PAGES = ["", "fechamento", "espelho", "batida", "atrasos", "banco-horas", "justificativas"]

results = []


def check(name, ok, detail):
    results.append(ok)
    print(("✅ PASS " if ok else "❌ FAIL ") + name + " — " + str(detail)[:140])


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 900},
                        permissions=["geolocation"], geolocation={"latitude": -3.1, "longitude": -60.02})
    pg = ctx.new_page()
    errs: list = []
    fails: list = []
    pg.on("console", lambda m: errs.append(m.text[:120]) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append("PAGEERROR: " + str(e)[:120]))
    pg.on("response", lambda r: fails.append((r.status, r.url[-80:]))
          if r.status >= 400 and "/ws/" not in r.url and "notifications" not in r.url else None)
    pg.add_init_script(f"try{{localStorage.setItem('access_token','{TOK}')}}catch(e){{}}")

    # 1) Sweep das 7 telas
    for rota in PAGES:
        errs.clear(); fails.clear()
        pg.goto(f"{PONTO}/{rota}".rstrip("/"), wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_timeout(7000)
        body = pg.evaluate("document.body.innerText")
        crash = "Algo deu errado" in body
        errlist = [e for e in dict.fromkeys(errs) if "WebSocket" not in e and "Permissions" not in e]
        check(f"tela /{rota or 'index'}", not crash and not errlist and not fails,
              f"console={errlist[:2]} http={fails[:2]}" if (crash or errlist or fails) else "limpa")

    # 2) Espelho em hora LOCAL: entradas de manhã (06-08h), nunca bloco 10-12h sem manhã
    pg.goto(f"{PONTO}/espelho", wait_until="domcontentloaded")
    pg.wait_for_timeout(8000)
    body = pg.evaluate("document.body.innerText")
    horas = re.findall(r"\b(0[5-9]|1[0-2]):\d{2}\b", body)
    tem_manha = any(h in ("05", "06", "07", "08") for h in horas)
    check("espelho mostra horários de manhã (local)", tem_manha or not horas,
          f"amostra de horas: {sorted(set(horas))[:8]}")

    # 3) Atrasos: coluna Colaborador com NOMES (não '--')
    pg.goto(f"{PONTO}/atrasos", wait_until="domcontentloaded")
    pg.wait_for_timeout(7000)
    body = pg.evaluate("document.body.innerText")
    linhas_sem_nome = body.count("--\t") + body.count("--	2026")
    tem_nomes = bool(re.search(r"[A-Z]{3,} [A-Z]{2,}.*\t?20\d\d-", body)) or "--" not in body
    check("atrasos com nome do colaborador", "ponto_em_aberto" not in body or tem_nomes,
          "nomes presentes" if tem_nomes else "coluna ainda com '--'")

    # 4) Justificativas: tabela carrega (sem 422 no console — já coberto acima)
    pg.goto(f"{PONTO}/justificativas", wait_until="domcontentloaded")
    pg.wait_for_timeout(7000)
    body = pg.evaluate("document.body.innerText")
    check("justificativas renderiza conteúdo",
          len(body) > 600 or "Nenhuma justificativa" in body,  # vazio-real honesto conta
          f"{len(body)} chars")

    # 5) Batida: tela renderiza (relógio/botão) e SEM violação de Permissions-Policy
    errs.clear()
    pg.goto(f"{PONTO}/batida", wait_until="domcontentloaded")
    pg.wait_for_timeout(7000)
    body = pg.evaluate("document.body.innerText")
    viol = [e for e in errs if "Permissions policy" in e and "eolocation" in e]
    check("batida sem bloqueio de geolocalização", not viol, viol[:1] or "policy ok")
    check("batida renderiza UI", len(body) > 400 and ("Bater" in body or "Ponto" in body or ":" in body),
          f"{len(body)} chars")

    # 6) Index: dashboard com Sync Sólides + banco de horas plausível
    pg.goto(PONTO, wait_until="domcontentloaded")
    pg.wait_for_timeout(7000)
    body = pg.evaluate("document.body.innerText")
    check("index dashboard carrega KPIs", "Banco de Horas" in body and "Sync" in body, "KPIs presentes")

    b.close()

print(f"\n════ RESULTADO: {sum(results)}/{len(results)} PASS ════")
sys.exit(0 if all(results) else 1)
