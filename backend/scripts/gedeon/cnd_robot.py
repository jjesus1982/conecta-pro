"""GEDEON — Robô de emissão de CND (Playwright, HOST). Unifica os portais:
navega → preenche CNPJ → resolve reCAPTCHA (2captcha, injeta token) → emite →
captura a certidão como PDF (page.pdf) → classifica negativa/positiva.

Roda no HOST (Playwright passa o WAF Azion da Caixa e os fluxos JS naturalmente).
Uso: python cnd_robot.py <portal> <cnpj>   (portal: sefaz_am | federal | prefeitura | caixa | cndt)
Saída: /opt/conecta-pro/uploads/cnds/<portal>_<cnpj>.pdf + imprime JSON do resultado.
"""

import base64
import json
import os
import re
import sys
import time

import httpx
from playwright.sync_api import sync_playwright

DEST = "/opt/conecta-pro/uploads/cnds"
os.makedirs(DEST, exist_ok=True)


def _key():
    # lê TWOCAPTCHA_API_KEY do ambiente ou do .env
    k = os.getenv("TWOCAPTCHA_API_KEY", "").strip()
    if not k:
        for l in open("/opt/conecta-pro/.env"):
            if l.startswith("TWOCAPTCHA_API_KEY="):
                k = l.strip().split("=", 1)[1]
    return k


def solve_recaptcha(sitekey, pageurl, invisible=False, timeout_s=180, tentativas=4):
    """Resolve reCAPTCHA via 2captcha, com retry em ERROR_CAPTCHA_UNSOLVABLE (intermitente)."""
    key = _key()
    if not key:
        raise RuntimeError("TWOCAPTCHA_API_KEY ausente")
    data = {"key": key, "method": "userrecaptcha", "googlekey": sitekey, "pageurl": pageurl, "json": 1}
    if invisible:
        data["invisible"] = 1
    last = ""
    for _ in range(tentativas):
        with httpx.Client(timeout=30) as cli:
            d = cli.post("https://2captcha.com/in.php", data=data).json()
            if d.get("status") != 1:
                raise RuntimeError("2captcha in: " + str(d.get("request")))
            cid = d["request"]
            time.sleep(15)
            end = time.time() + timeout_s
            resolved = None
            while time.time() < end:
                dd = cli.get(
                    "https://2captcha.com/res.php", params={"key": key, "action": "get", "id": cid, "json": 1}
                ).json()
                if dd.get("status") == 1:
                    resolved = dd["request"]
                    break
                req = dd.get("request")
                if req != "CAPCHA_NOT_READY":
                    last = str(req)
                    break  # ex.: ERROR_CAPTCHA_UNSOLVABLE → tenta de novo
                time.sleep(5)
            if resolved:
                return resolved
    raise RuntimeError("2captcha falhou após retries: " + last)


def solve_image_captcha(b64, tentativas=3, timeout_s=120):
    """Resolve captcha de IMAGEM (texto na imagem) via 2captcha base64. Retorna o texto."""
    key = _key()
    if not key:
        raise RuntimeError("TWOCAPTCHA_API_KEY ausente")
    body = b64.split("base64,")[-1].strip()
    last = ""
    for _ in range(tentativas):
        with httpx.Client(timeout=30) as cli:
            d = cli.post(
                "https://2captcha.com/in.php", data={"key": key, "method": "base64", "body": body, "json": 1}
            ).json()
            if d.get("status") != 1:
                raise RuntimeError("2captcha img in: " + str(d.get("request")))
            cid = d["request"]
            time.sleep(8)
            end = time.time() + timeout_s
            while time.time() < end:
                dd = cli.get(
                    "https://2captcha.com/res.php", params={"key": key, "action": "get", "id": cid, "json": 1}
                ).json()
                if dd.get("status") == 1:
                    return dd["request"]
                if dd.get("request") != "CAPCHA_NOT_READY":
                    last = str(dd.get("request"))
                    break
                time.sleep(4)
    raise RuntimeError("2captcha img falhou: " + last)


def solve_hcaptcha(sitekey, pageurl, tentativas=3, timeout_s=180):
    """Resolve hCaptcha via 2captcha. Retorna o token."""
    key = _key()
    if not key:
        raise RuntimeError("TWOCAPTCHA_API_KEY ausente")
    last = ""
    for _ in range(tentativas):
        with httpx.Client(timeout=30) as cli:
            d = cli.post(
                "https://2captcha.com/in.php",
                data={"key": key, "method": "hcaptcha", "sitekey": sitekey, "pageurl": pageurl, "json": 1},
            ).json()
            if d.get("status") != 1:
                raise RuntimeError("2captcha hcap in: " + str(d.get("request")))
            cid = d["request"]
            time.sleep(15)
            end = time.time() + timeout_s
            while time.time() < end:
                dd = cli.get(
                    "https://2captcha.com/res.php", params={"key": key, "action": "get", "id": cid, "json": 1}
                ).json()
                if dd.get("status") == 1:
                    return dd["request"]
                if dd.get("request") != "CAPCHA_NOT_READY":
                    last = str(dd.get("request"))
                    break
                time.sleep(5)
    raise RuntimeError("2captcha hcaptcha falhou: " + last)


def _classificar(texto):
    t = (texto or "").upper()
    if "EFEITO DE NEGATIVA" in t or "POSITIVA COM EFEITO" in t:
        return True, "positiva_com_efeito_negativa"
    if "NEGATIVA" in t and "POSITIVA" not in t:
        return True, "negativa"
    if "POSITIVA" in t:
        return False, "positiva"
    return None, "indeterminado"


# ── SEFAZ-AM (estadual, não-contribuinte) ──────────────────────────────────────
def sefaz_am(pg, cnpj):
    URL = "https://sistemas.sefaz.am.gov.br/GAE/mnt/dividaAtiva/certidaoNegativa/emitirCertidaoNegativaNaoContPortal.do"
    SITEKEY = "6Ld0oc4rAAAAAC_WFwEcD5Fx2sWOnwYg2wRIcYpc"  # pragma: allowlist secret
    CAP_PAGE = "https://sistemas.sefaz.am.gov.br/GAE/html/recaptcha-script.html"
    pg.goto(URL, wait_until="networkidle", timeout=45000)
    pg.click("#nrDocumento")
    pg.type("#nrDocumento", cnpj, delay=70)  # digita p/ a máscara jQuery formatar
    try:
        pg.check("#csCompleto")
    except Exception:
        pass
    token = solve_recaptcha(SITEKEY, CAP_PAGE, invisible=True)
    # injeta o token, remove a máscara (como o onclick faz) e submete
    pg.evaluate(
        """(t)=>{const e=document.getElementById('g-recaptcha-response'); if(e){e.value=t;}
        try{ if(typeof removerMascara==='function') removerMascara(); }catch(_){}
        const b=document.getElementById('botaoEmitir'); if(b){b.click();}}""",
        token,
    )
    pg.wait_for_timeout(6000)
    return pg.inner_text("body"), None  # (texto, pdf_path) — None = main faz page.pdf()


# ── CNDT / TST (trabalhista, captcha de IMAGEM) ────────────────────────────────
def cndt(pg, cnpj):
    pg.goto("https://cndt-certidao.tst.jus.br/inicio.faces", wait_until="networkidle", timeout=45000)
    pg.get_by_text("Emitir Certidão", exact=False).first.click(timeout=10000)
    pg.wait_for_timeout(3000)
    pg.fill('[id="gerarCertidaoForm:cpfCnpj"]', cnpj)
    b64 = pg.get_attribute("#idImgBase64", "src")
    resposta = solve_image_captcha(b64)
    pg.fill("#idCampoResposta", resposta)
    path = f"{DEST}/cndt_{cnpj}.pdf"
    try:
        with pg.expect_download(timeout=25000) as di:
            pg.click('[id="gerarCertidaoForm:btnEmitirCertidao"]')
        di.value.save_as(path)
        import fitz

        txt = "\n".join(p.get_text() for p in fitz.open(path))
        return txt, path
    except Exception:
        pg.wait_for_timeout(4000)
        return pg.inner_text("body"), None


# ── FEDERAL / RFB-PGFN (SPA Angular + hCaptcha) ────────────────────────────────
def federal(pg, cnpj):
    URL = "https://servicos.receitafederal.gov.br/servico/certidoes"
    SITEKEY = "f214a120-a07a-4b28-907a-bfa6b96257ae"  # pragma: allowlist secret
    pg.goto(URL, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(8000)
    try:
        pg.get_by_text("Aceitar", exact=True).first.click(timeout=4000)
    except Exception:
        pass
    pg.get_by_text("Pessoa Jurídica", exact=False).first.click(timeout=10000)
    pg.wait_for_timeout(6000)
    pg.fill('input[placeholder="Informe o CNPJ"]', cnpj)
    path = f"{DEST}/federal_{cnpj}.pdf"
    # RFB retorna erro transitório "023 - tente novamente" com frequência → retry curto
    for tent in range(3):
        token = solve_hcaptcha(SITEKEY, URL)
        pg.evaluate(
            """(t)=>{
            document.querySelectorAll('[name="h-captcha-response"],[name="g-recaptcha-response"],textarea#h-captcha-response')
              .forEach(x=>{x.value=t; x.dispatchEvent(new Event('input',{bubbles:true}));
              x.dispatchEvent(new Event('change',{bubbles:true}));});
            // SPA lê hcaptcha.getResponse() no submit → faz devolver o token
            try{ if(window.hcaptcha){ window.hcaptcha.getResponse=function(){return t;}; } }catch(e){}
            // textareas dentro de iframes hcaptcha não são acessíveis; o getResponse cobre
        }""",
            token,
        )
        pg.wait_for_timeout(1500)
        try:
            with pg.expect_download(timeout=30000) as di:
                pg.get_by_text("Emitir Certidão", exact=False).first.click(timeout=10000)
            di.value.save_as(path)
            import fitz

            txt = "\n".join(p.get_text() for p in fitz.open(path))
            return txt, path
        except Exception:
            pg.wait_for_timeout(5000)
            corpo = pg.inner_text("body")
            if re.search(r"n[ãa]o foi poss[íi]vel concluir|tente novamente|023", corpo, re.I):
                # erro transitório da RFB → fecha o aviso e tenta de novo
                try:
                    pg.get_by_text("×", exact=False).first.click(timeout=2000)
                except Exception:
                    pass
                pg.wait_for_timeout(12000)
                continue
            return corpo, None  # outra resposta (certidão na tela?)
    return "RFB_TRANSITORIO: 023 - tente novamente em alguns minutos", None


# ── PREFEITURA MANAUS / SEMEF (municipal, iframe GeneXus + captcha de IMAGEM) ───
def prefeitura(pg, cnpj):
    pg.goto(
        "https://manausatende.manaus.am.gov.br/servicoJanela.php?servico=257",
        wait_until="domcontentloaded",
        timeout=45000,
    )
    pg.wait_for_timeout(8000)
    fr = None
    for f in pg.frames:
        if "hwtportalcontribuinte" in (f.url or ""):
            fr = f
    if not fr:
        raise RuntimeError("frame SEMEF não carregou")
    path = f"{DEST}/prefeitura_{cnpj}.pdf"
    # a certidão abre em POPUP; captcha errado reseta o form → retry
    for _ in range(3):
        fr.check("#vTIPOFILTRO3")  # CNPJ (value 4)
        fr.wait_for_timeout(1500)
        fr.click("#vNRFILTRO")
        fr.type("#vNRFILTRO", cnpj, delay=30)
        cap = fr.query_selector("img[src*='Captcha']")
        if not cap:
            raise RuntimeError("captcha SEMEF não encontrado")
        resposta = solve_image_captcha(base64.b64encode(cap.screenshot()).decode())
        fr.click("#_cfield")
        fr.type("#_cfield", resposta, delay=30)
        try:
            with pg.context.expect_page(timeout=18000) as pi:
                fr.click("input[name=BTNCONSULTAR]")
            popup = pi.value
            popup.wait_for_load_state("domcontentloaded", timeout=10000)
            popup.wait_for_timeout(2500)
            texto = popup.inner_text("body")
            popup.pdf(path=path, format="A4", print_background=True)
            return texto, path
        except Exception:
            pg.wait_for_timeout(3000)  # form resetou (captcha errado) → tenta de novo
            continue
    return "SEMEF: captcha não validado após retries", None


PORTAIS = {"sefaz_am": sefaz_am, "cndt": cndt, "federal": federal, "prefeitura": prefeitura}


def main():
    portal = sys.argv[1]
    cnpj = re.sub(r"\D", "", sys.argv[2])
    fn = PORTAIS.get(portal)
    out = {
        "portal": portal,
        "cnpj": cnpj,
        "ok": False,
        "regular": None,
        "situacao": None,
        "pdf": None,
        "mensagem": None,
    }
    if not fn:
        out["mensagem"] = "portal não implementado: " + portal
        print(json.dumps(out))
        return
    # proxy opcional (ex.: Caixa, bloqueada por WAF/IP). CND_PROXY=http://user:pass@host:port  # pragma: allowlist secret
    proxy = None
    pxy = os.getenv("CND_PROXY", "").strip()
    if pxy:
        m = re.match(r"(\w+)://(?:([^:@]+):([^@]+)@)?(.+)", pxy)
        if m:
            proxy = {"server": f"{m.group(1)}://{m.group(4)}"}
            if m.group(2):
                proxy["username"] = m.group(2)
                proxy["password"] = m.group(3)
    with sync_playwright() as b0:
        b = b0.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        ctx = b.new_context(
            viewport={"width": 1280, "height": 1400}, ignore_https_errors=True, user_agent="Mozilla/5.0", proxy=proxy
        )
        pg = ctx.new_page()
        try:
            texto, pdf_path = fn(pg, cnpj)
            regular, situacao = _classificar(texto)
            mv = re.search(r"(?:V[áa]lid[ao]\s+at[ée]|validade)[:\s]*?(\d{2}/\d{2}/\d{4})", texto, re.I)
            mn = re.search(r"Certid[ãa]o\s*N[ºo°]?[:\s]*([0-9A-Za-z./\-]+)", texto, re.I)
            ok = situacao in ("negativa", "positiva", "positiva_com_efeito_negativa")
            if ok and not pdf_path:  # portal renderiza na tela → captura via page.pdf()
                pdf_path = f"{DEST}/{portal}_{cnpj}.pdf"
                pg.pdf(path=pdf_path, format="A4", print_background=True)
            out.update(
                ok=ok,
                regular=regular,
                situacao=situacao,
                pdf=pdf_path if ok else None,
                validade=(mv.group(1) if mv else None),
                numero=(mn.group(1) if mn else None),
                mensagem=(f"emitido ({situacao})" if ok else f"não emitida: {texto[:90]}"),
            )
        except Exception as exc:
            out["mensagem"] = f"erro: {exc}"
            try:
                pg.screenshot(path=f"/tmp/cnd_{portal}_err.png")
            except Exception:
                pass
        b.close()
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
