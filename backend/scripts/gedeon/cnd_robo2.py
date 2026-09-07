#!/usr/bin/env python3
"""GEDEON — Robô de CND, portais que só saem por OUTRO IP (TST e Caixa), pelo nó de saída.

Nasceu em 07/09/2026, no dia em que o túnel do PC do Jordan ficou de pé (`docs/no_saida_cnd`).
Mesmo contrato de saída do `cnd_robot.py` (JSON em stdout; PDF em uploads/cnds), mesmo solver
(2captcha) e mesmo classificador — importados de lá, não copiados. Arquivo separado porque o
`cnd_robot.py` é WIP de outra sessão e porque estes dois portais mudaram de cara:

  • TST (CNDT): a tela nova é /gerarCertidao com `#cpfCnpj`, `#captcha-imagem` (base64),
    `#captcha-resposta` e `#botao-emitir` — os ids `gerarCertidaoForm:*` do robô antigo não
    existem mais (medido 07/09/2026 pelo túnel).
  • Caixa (CRF/FGTS): antes do formulário há um muro Radware/ShieldSquare com hCaptcha
    (sitekey ae73173b-…, callback `hSolvedRad`). Deste IP da VPS é 403 direto; pelo nó de saída
    o muro aparece e é resolvível.

Uso: CND_PROXY=socks5://127.0.0.1:1080 python3 cnd_robo2.py <cndt|caixa> <cnpj> [--radiografia]
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cnd_robot import DEST, _classificar, solve_hcaptcha, solve_image_captcha  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0 Safari/537.36")


def _pdf_text(path):
    import fitz
    return "\n".join(p.get_text() for p in fitz.open(path))


def cndt(pg, cnpj):
    pg.goto("https://cndt-certidao.tst.jus.br/inicio.faces", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(3000)
    pg.get_by_text("Emitir Certidão", exact=False).first.click(timeout=15000)
    pg.wait_for_selector("#cpfCnpj", timeout=30000)
    pg.fill("#cpfCnpj", cnpj)
    # a imagem do captcha chega por JS depois do form: sem esperar, o src vem vazio e o
    # 2captcha devolve ERROR_UPLOAD (medido 07/09/2026)
    pg.wait_for_function("() => (document.querySelector('#captcha-imagem')||{}).src && document.querySelector('#captcha-imagem').src.length > 200", timeout=30000)
    b64 = pg.get_attribute("#captcha-imagem", "src") or ""
    if not b64.startswith("data:"):
        b64 = "data:image/jpeg;base64," + b64
    pg.fill("#captcha-resposta", solve_image_captcha(b64))
    path = f"{DEST}/cndt_{cnpj}.pdf"
    try:
        with pg.expect_download(timeout=40000) as di:
            pg.click("#botao-emitir")
        di.value.save_as(path)
        return _pdf_text(path), path
    except Exception:
        pg.wait_for_timeout(4000)
        return pg.inner_text("body"), None


def _passar_muro_caixa(pg):
    """Muro Radware (validate.perfdrive.com) com hCaptcha: resolve, injeta o token e chama o
    callback do próprio muro. Devolve True se o formulário real apareceu."""
    html = pg.content()
    m = re.search(r'data-sitekey="([0-9a-f-]{36})"', html)
    if not m:
        return True  # sem muro
    token = solve_hcaptcha(m.group(1), pg.url)
    # o callback do muro (hSolvedRad) lê hcaptcha.getResponse()/getRespKey() do widget, não a
    # textarea — então o widget precisa "achar" que resolveu: sobrescrevemos os getters.
    pg.evaluate("""(t) => {
        for (const el of document.querySelectorAll('textarea[name="h-captcha-response"],textarea[name="g-recaptcha-response"]')) el.value = t;
        if (window.hcaptcha) { window.hcaptcha.getResponse = () => t; window.hcaptcha.getRespKey = () => 'E0_' + t.slice(-40); }
        if (typeof hSolvedRad === 'function') hSolvedRad(t);
        else { const f = document.querySelector('form'); if (f) f.submit(); }
    }""", token)
    try:
        pg.wait_for_url(re.compile(r"consulta-crf\.caixa\.gov\.br"), timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(5000)
    return "perfdrive" not in pg.url and 'data-sitekey="ae73173b' not in pg.content()


def _radiografia(pg):
    return pg.evaluate("""() => [...document.querySelectorAll('input,select,button,img,a')].map(e=>({tag:e.tagName,type:e.type||'',id:e.id||'',name:e.name||'',src:(e.src||'').slice(-60),value:(e.value||'').slice(0,25),text:(e.innerText||'').trim().slice(0,35),opts:e.tagName==='SELECT'?[...e.options].slice(0,6).map(o=>o.value):undefined})).filter(x=>x.id||x.name||x.src||x.text).slice(0,45)""")


def caixa(pg, cnpj):
    pg.goto("https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf",
            wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(4000)
    if not _passar_muro_caixa(pg):
        return "CAIXA_MURO: o muro anti-robô não liberou o formulário", None
    if "--radiografia" in sys.argv:
        return "CAIXA_RADIOGRAFIA: " + json.dumps(_radiografia(pg), ensure_ascii=False) + " URL=" + pg.url, None
    # formulário real: preenchido a partir da radiografia de 07/09 (ver abaixo, ajustar se mudar)
    pg.fill('input[id$="txtInscricao"], input[name$="txtInscricao"]', cnpj)
    return pg.inner_text("body"), None


PORTAIS = {"cndt": cndt, "caixa": caixa}


def main():
    portal, cnpj = sys.argv[1], re.sub(r"\D", "", sys.argv[2])
    out = {"portal": portal, "cnpj": cnpj, "ok": False, "regular": None, "situacao": None, "pdf": None, "mensagem": None}
    fn = PORTAIS.get(portal)
    if not fn:
        out["mensagem"] = "portal não implementado: " + portal
        print(json.dumps(out)); return
    proxy = None
    pxy = os.getenv("CND_PROXY", "").strip()
    if pxy:
        proxy = {"server": pxy}
    with sync_playwright() as b0:
        b = b0.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        ctx = b.new_context(viewport={"width": 1280, "height": 1400}, ignore_https_errors=True, user_agent=UA, proxy=proxy)
        pg = ctx.new_page()
        try:
            texto, pdf_path = fn(pg, cnpj)
            if texto and texto.strip().startswith(("CAIXA_MURO:", "CAIXA_RADIOGRAFIA:")):
                out.update(ok=False, situacao="diagnostico", mensagem=texto.strip()[:3000])
                print(json.dumps(out, ensure_ascii=False)); b.close(); return
            regular, situacao = _classificar(texto)
            mv = re.search(r"(?:V[áa]lid[ao]\s+at[ée]|validade)[:\s]*?(\d{2}/\d{2}/\d{4})", texto, re.I)
            mn = re.search(r"Certid[ãa]o\s*N[ºo°]?[:\s]*(\d[0-9./\-]{3,})", texto, re.I)  # exige dígitos: "Certidão NEGATIVA" virava número "EGATIVA"
            ok = situacao in ("negativa", "positiva", "positiva_com_efeito_negativa")
            if ok and not pdf_path:
                pdf_path = f"{DEST}/{portal}_{cnpj}.pdf"
                pg.pdf(path=pdf_path, format="A4", print_background=True)
            out.update(ok=ok, regular=regular, situacao=situacao, pdf=pdf_path if ok else None,
                       validade=(mv.group(1) if mv else None), numero=(mn.group(1) if mn else None),
                       mensagem=(f"emitido ({situacao})" if ok else f"não emitida: {texto[:120]}"))
        except Exception as exc:
            out["mensagem"] = f"erro: {exc}"[:400]
            try: pg.screenshot(path=f"/tmp/cnd2_{portal}_err.png")
            except Exception: pass
        b.close()
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
