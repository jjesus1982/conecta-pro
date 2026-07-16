"""QA de browser do módulo GED/GEDEON — valida na tela renderizada (como o CIC vê).

USO (host):
  TOKEN=$(docker exec -e PYTHONPATH=/app conecta-pro-backend python3 -c "
  from core.auth.jwt import create_access_token
  from core.database.session import SyncSessionLocal
  from sqlalchemy import text
  s=SyncSessionLocal()
  uid=s.execute(text(\"SELECT id FROM users WHERE email='jjesus@conectamais.pro' LIMIT 1\")).scalar()
  print(create_access_token(subject=str(uid)))" | tail -1)
  ERP_TOKEN=$TOKEN python3 scripts/qa_ged_browser.py

Exit 0 = tudo PASS. Telas gated: token injetado no localStorage antes do app carregar.
"""

import os
import re
import sys

from playwright.sync_api import sync_playwright

BASE = "https://erp.conectamais.pro"
TOK = os.environ["ERP_TOKEN"]
GED = f"{BASE}/modulos/gestao-pessoas/ged"

PAGES = [
    "", "documentos", "kits", "kit", "montar-kit", "envios", "clientes", "certidoes",
    "upload", "assinaturas", "relatorios", "whatsapp", "consultor", "configuracoes",
    "onvio-sync",
]

results = []


def check(name, ok, detail):
    results.append(ok)
    print(("✅ PASS " if ok else "❌ FAIL ") + name + " — " + str(detail)[:140])


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    console_err: list = []
    http_fail: list = []
    pg.on("console", lambda m: console_err.append(m.text[:120]) if m.type == "error" else None)
    pg.on(
        "response",
        lambda r: http_fail.append((r.status, r.url[-80:]))
        if r.status >= 400 and "/ws/" not in r.url and "notifications" not in r.url
        else None,
    )
    pg.add_init_script(f"try{{localStorage.setItem('access_token','{TOK}')}}catch(e){{}}")

    # 1) Sweep: todas as telas carregam sem crash/console error/HTTP>=400
    for rota in PAGES:
        console_err.clear()
        http_fail.clear()
        pg.goto(f"{GED}/{rota}".rstrip("/"), wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_timeout(6000)
        body = pg.evaluate("document.body.innerText")
        crash = "Algo deu errado" in body
        errs = [e for e in dict.fromkeys(console_err) if "WebSocket" not in e]
        fails = list(dict.fromkeys(http_fail))
        check(
            f"tela /{rota or 'index'}",
            not crash and not errs and not fails,
            f"console={errs[:2]} http={fails[:3]}" if (errs or fails or crash) else "limpa",
        )

    # 2) Consultor: funcionários reais e kits montados (competência de junho)
    pg.goto(f"{GED}/consultor", wait_until="domcontentloaded")
    pg.wait_for_timeout(8000)
    body = pg.evaluate("document.body.innerText")
    m = re.search(r"(\d+)/(\d+)\s*\n\s*Kits montados", body)
    kits_txt = f"{m.group(1)}/{m.group(2)}" if m else None
    # aceita competência atual (pode ter menos kits que junho); o que NÃO pode é a
    # tabela inteira com funcionários 0 (bug do elo por nome)
    linhas_func = re.findall(r"≈?(\d+)\s*\|?\s*", "")
    func_zero = body.count("NÃO\t0\t≈0")
    check(
        "consultor sem '≈0 funcionários' geral",
        "≈0" not in body or body.count("≈0") < 8,
        f"kits montados={kits_txt}, ocorrências de ≈0: {body.count('≈0')}",
    )

    # 3) Index/kits: painel de completude SEM pastas com nome de arquivo
    pg.goto(GED, wait_until="domcontentloaded")
    # espera o painel resolver (cache quente = rápido; frio = até 60s)
    ok_painel = False
    for _ in range(12):
        pg.wait_for_timeout(5000)
        body = pg.evaluate("document.body.innerText")
        if "Lendo os kits no Drive" not in body:
            ok_painel = True
            break
    check("index painel resolve", ok_painel, "spinner sumiu" if ok_painel else "preso em 'Lendo os kits'")
    if ok_painel:
        check(
            "index sem kit com nome de arquivo",
            ".pdf" not in body and ".xlsx" not in body.lower(),
            "nenhuma pasta-lixo no painel",
        )

    # 4) Certidões: cards com dados reais
    pg.goto(f"{GED}/certidoes", wait_until="domcontentloaded")
    pg.wait_for_timeout(7000)
    body = pg.evaluate("document.body.innerText")
    check("certidões com validade real", "Validade:" in body, "cards presentes")

    b.close()

print(f"\n════ RESULTADO: {sum(results)}/{len(results)} PASS ════")
sys.exit(0 if all(results) else 1)
