"""QA E2E do módulo Fiscal/Contábil — browser real (Playwright), domínio público.

Login por token no localStorage (padrão provado). Para cada tela: navega, espera o
React Query, coleta erros de console + requests falhas (4xx/5xx) + o texto renderizado,
e checa asserts de DADO REAL. Screenshots em /state/qa_fiscal/. Saída JSON no stdout.
"""
import json
import sys
import time

import httpx
from playwright.sync_api import sync_playwright

BASE = "https://erp.conectamais.pro"
USER = "mcp-service@conectamais.pro"
PWD = "67142814d66bdb5aa96b97e902e98cc486ae"
SHOTS = "/state/qa_fiscal"

# tela → (rota, [asserts de texto que PROVAM dado real])
TELAS = [
    ("hub",        "/modulos/fiscal",            ["e-CAC", "Fiscal"]),
    ("ecac",       "/modulos/fiscal/ecac",       ["e-CAC", "50.749", "SISPAR 009523101", "CONECTAMAIS", "Com pendências"]),
    ("guias",      "/modulos/fiscal/guias",      ["Guias", "Parcelament"]),
    ("dctfweb",    "/modulos/fiscal/dctfweb",    ["DCTFWeb"]),
    ("painel",     "/modulos/fiscal/painel",     ["Fiscal"]),
    ("certidoes",  "/modulos/fiscal/certidoes",  ["Certid"]),
    ("nfse",       "/modulos/fiscal/nfse",       ["NFS"]),
    ("esocial",    "/modulos/fiscal/esocial",    ["eSocial"]),
    ("reinf",      "/modulos/fiscal/reinf",      ["Reinf"]),
    ("sped",       "/modulos/fiscal/sped",       ["SPED"]),
    ("nfe",        "/modulos/financeiro/fiscal", ["NF"]),
]


def token():
    r = httpx.post(f"{BASE}/api/v1/auth/login",
                   data={"username": USER, "password": PWD},
                   headers={"Content-Type": "application/x-www-form-urlencoded"},
                   verify=False, timeout=30)
    return r.json()["access_token"]


def run():
    import os
    os.makedirs(SHOTS, exist_ok=True)
    tok = token()
    rel = {"telas": [], "resumo": {}}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 900})
        # cookie auth_token = guard do middleware Next (senão redireciona /login)
        ctx.add_cookies([{"name": "auth_token", "value": tok, "domain": "erp.conectamais.pro", "path": "/"}])
        # init script: seta o token no localStorage ANTES de qualquer JS do app, TODA navegação
        ctx.add_init_script("try{localStorage.setItem('access_token'," + json.dumps(tok) +
                            ");localStorage.setItem('token'," + json.dumps(tok) + ");}catch(e){}")
        page = ctx.new_page()

        for nome, rota, asserts in TELAS:
            res = {"tela": nome, "rota": rota, "console_errors": [], "req_falhas": [], "asserts_ok": [], "asserts_faltando": []}
            errs, fails = [], []
            page.on("console", lambda m: errs.append(m.text[:160]) if m.type == "error" else None)
            page.on("response", lambda r: fails.append(f"{r.status} {r.url.split('/api/v1')[-1][:70]}")
                    if (r.status >= 400 and "/api/v1" in r.url) else None)
            try:
                page.goto(BASE + rota, wait_until="domcontentloaded", timeout=45000)
                # espera o React Query popular (até 18s procurando o 1º assert)
                alvo = asserts[0]
                dl = time.time() + 18
                body = ""
                while time.time() < dl:
                    try:
                        body = page.inner_text("body")
                    except Exception:
                        body = ""
                    if alvo in body:
                        break
                    page.wait_for_timeout(1500)
                page.wait_for_timeout(2500)
                body = page.inner_text("body")
                for a in asserts:
                    (res["asserts_ok"] if a in body else res["asserts_faltando"]).append(a)
                res["url_final"] = page.url
                res["logado"] = "/login" not in page.url
                page.screenshot(path=f"{SHOTS}/{nome}.png", full_page=True)
            except Exception as e:
                res["erro"] = str(e)[:120]
            res["console_errors"] = list(dict.fromkeys(errs))[:6]
            res["req_falhas"] = list(dict.fromkeys(fails))[:8]
            res["PASS"] = bool(res.get("logado") and not res["asserts_faltando"] and not res["req_falhas"])
            rel["telas"].append(res)
            errs.clear(); fails.clear()
        b.close()
    ok = sum(1 for t in rel["telas"] if t["PASS"])
    rel["resumo"] = {"total": len(rel["telas"]), "PASS": ok, "FAIL": len(rel["telas"]) - ok}
    print(">>>JSON<<<" + json.dumps(rel, ensure_ascii=False))


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(">>>JSON<<<" + json.dumps({"erro_fatal": str(e)[:200]}))
        sys.exit(1)
