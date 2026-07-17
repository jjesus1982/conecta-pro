"""
Coletor e-CAC standalone — contexto FRESCO (não-persistente) + certificado A1.

Roda como processo isolado (subprocess) — NÃO usa o perfil persistente do DET (o
certificado é a própria autenticação). Isso contorna o bug do Playwright client-cert em
launch_persistent_context (mTLS trava/reseta). Contexto fresco = mTLS funciona.

Fluxo: authorize gov.br DIRETO (pula o hCaptcha do e-CAC) → "Seu certificado digital"
(mTLS, sem captcha) → e-CAC logado → Situação Fiscal / Pendências / Parcelamentos.

Saída: JSON no stdout (linha única marcada por >>>JSON<<<) para o chamador consumir.
Screenshots em /state/ecac_std/ para diagnóstico.
"""
import json
import os
import sys
import time

from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, pkcs12,
)
from playwright.sync_api import sync_playwright

PFX = os.environ.get("DET_PFX_PATH", "/cert/certificado.pfx")
PFX_PASS = os.environ.get("CERTIFICATE_PASSWORD", "Conecta123")
SHOTS = "/state/ecac_std"
AUTHZ = ("https://sso.acesso.gov.br/authorize?response_type=code"
         "&client_id=cav.receita.fazenda.gov.br"
         "&scope=openid+govbr_recupera_certificadox509+govbr_confiabilidades"
         "&redirect_uri=https://cav.receita.fazenda.gov.br/autenticacao/login/govbrsso"
         "&nonce=conecta&state=conecta")

log = []


def _l(m):
    log.append(m)
    sys.stderr.write(f"[ecac] {m}\n")
    sys.stderr.flush()


def _pem():
    os.makedirs("/dev/shm/ecacstd", exist_ok=True)
    cp, kp = "/dev/shm/ecacstd/c.pem", "/dev/shm/ecacstd/k.pem"
    key, cert, extra = pkcs12.load_key_and_certificates(open(PFX, "rb").read(), PFX_PASS.encode())
    pem = cert.public_bytes(Encoding.PEM)
    for c in (extra or []):
        pem += c.public_bytes(Encoding.PEM)
    open(cp, "wb").write(pem)
    open(kp, "wb").write(key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()))
    return cp, kp


def _shot(page, nome):
    try:
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=f"{SHOTS}/{nome}.png", full_page=True)
    except Exception:
        pass


def _logado(page):
    u = page.url.lower()
    return ("cav.receita.fazenda.gov.br" in u
            and "/autenticacao/login" not in u
            and "sso.acesso.gov.br" not in u)


def run():
    cp, kp = _pem()
    res = {"ok": False, "log": log, "url": "", "situacao_fiscal_texto": "", "links": []}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = b.new_context(
            client_certificates=[
                {"origin": "https://certificado.sso.acesso.gov.br", "certPath": cp, "keyPath": kp},
                {"origin": "https://sso.acesso.gov.br", "certPath": cp, "keyPath": kp},
                {"origin": "https://cav.receita.fazenda.gov.br", "certPath": cp, "keyPath": kp},
            ],
            ignore_https_errors=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        )
        page = ctx.new_page()
        reqs = []
        page.on("framenavigated", lambda f: reqs.append(f"NAV {f.url[:120]}") if f == page.main_frame else None)
        page.on("request", lambda r: reqs.append(f"{r.method} {r.url[:120]}") if (
            "gov.br" in r.url and r.resource_type in ("document", "xhr", "fetch")) else None)
        page.on("requestfailed", lambda r: reqs.append(f"FAILED {r.url[:100]}"))
        res["reqs"] = reqs
        try:
            _l("authorize direto")
            page.goto(AUTHZ, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)
            _shot(page, "01_authz")
            _l("url: " + page.url[:70])

            if not _logado(page) and "sso.acesso.gov.br" in page.url.lower():
                # inspeciona o botão do certificado (tag/id/onclick/href)
                try:
                    res["cert_btn"] = page.evaluate(
                        """()=>{const els=[...document.querySelectorAll('a,button,div,span,li')];
                          const b=els.find(e=>/seu certificado digital\\s*$/i.test((e.innerText||'').trim()));
                          if(!b) return null;
                          const clk=b.closest('a,button')||b;
                          return {tag:clk.tagName,id:clk.id,href:clk.getAttribute('href'),
                                  onclick:(clk.getAttribute('onclick')||'').slice(0,120),
                                  html:clk.outerHTML.slice(0,300)};}"""
                    )
                except Exception:
                    res["cert_btn"] = None
                # o botão #login-certificate é type=submit com formaction → certificado.sso
                # (mTLS). Clicar o texto NÃO submete; navegamos TOP-LEVEL pro formaction, que
                # o mTLS aceita (o client-cert reseta em XHR mas funciona em navegação direta).
                formaction = None
                try:
                    formaction = page.get_attribute("#login-certificate", "formaction")
                except Exception:
                    pass
                _l("formaction: " + str(formaction)[:90])
                # SUBMIT NATIVO do botão #login-certificate (type=submit → POST top-level ao
                # formaction, com operation=login-certificate). GET no formaction só re-renderiza.
                try:
                    with page.expect_navigation(timeout=50000, wait_until="domcontentloaded"):
                        page.locator("#login-certificate").click(timeout=8000, force=True)
                    _l("pós-submit: " + page.url[:70])
                except Exception as e:
                    _l("submit nav: " + str(e)[:60] + " | url=" + page.url[:60])
                page.wait_for_timeout(5000)
                # aguarda a apresentação do cert + redirect ao e-CAC (até 70s)
                dl = time.time() + 70
                while time.time() < dl and not _logado(page):
                    time.sleep(3)
                _shot(page, "02_postcert")
                _l("pós-cert: " + page.url[:70])

            res["url"] = page.url
            if not _logado(page):
                res["erro"] = "não autenticou no e-CAC"
                try:
                    res["texto_login"] = page.locator("body").inner_text()[:1500]
                except Exception:
                    pass
                return res

            _l("✅ e-CAC autenticado")
            _shot(page, "03_dashboard")
            try:
                res["dashboard_texto"] = page.locator("body").inner_text()[:2000]
            except Exception:
                pass
            res["links"] = page.evaluate(
                """()=>Array.from(document.querySelectorAll('a,button')).map(e=>({
                     t:(e.innerText||'').trim().slice(0,60),
                     h:(e.getAttribute('href')||'').slice(0,120)})).filter(x=>x.t).slice(0,120)"""
            )

            # Situação Fiscal / Consulta Pendências
            clicou = None
            for termo in ("Situação Fiscal", "Consulta Pendências", "Certidões e Situação",
                          "Diagnóstico Fiscal", "Regularidade Fiscal", "Situacao Fiscal"):
                try:
                    el = page.get_by_text(termo, exact=False)
                    if el.count():
                        el.first.click(timeout=6000)
                        page.wait_for_timeout(5000)
                        clicou = termo
                        break
                except Exception:
                    continue
            _l("situação fiscal: " + str(clicou))
            _shot(page, "04_sitfis")
            res["url"] = page.url
            try:
                res["situacao_fiscal_texto"] = page.locator("body").inner_text()[:9000]
            except Exception:
                pass
            res["ok"] = True
        except Exception as e:
            res["erro"] = str(e)[:150]
            _l("ERRO: " + str(e)[:120])
        finally:
            b.close()
    return res


if __name__ == "__main__":
    out = run()
    print(">>>JSON<<<" + json.dumps(out, ensure_ascii=False))
