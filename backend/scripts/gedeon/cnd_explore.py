"""Explorador de portal de CND (Playwright HOST). Abre URL, opcionalmente clica um
texto, e dumpa o form real (inputs, selects, iframes, sitekey reCAPTCHA) + screenshot.
Uso: python cnd_explore.py <url> [texto_para_clicar]"""

import sys

from playwright.sync_api import sync_playwright

url = sys.argv[1]
clicar = sys.argv[2] if len(sys.argv) > 2 else None

DUMP = """()=>{
  const inputs=[...document.querySelectorAll('input,select,textarea')].map(e=>({
    tag:e.tagName.toLowerCase(),type:e.type||'',name:e.name||'',id:e.id||'',
    ph:e.placeholder||'',vis:e.offsetParent!==null}));
  const sitekeys=[...document.querySelectorAll('[data-sitekey]')].map(e=>e.getAttribute('data-sitekey'));
  const forms=[...document.querySelectorAll('form')].map(f=>({action:f.action,method:f.method}));
  const iframes=[...document.querySelectorAll('iframe')].map(f=>f.src);
  const btns=[...document.querySelectorAll('button,input[type=submit],a')].map(b=>(b.innerText||b.value||'').trim()).filter(Boolean).slice(0,40);
  return {inputs,sitekeys,forms,iframes,btns,url:location.href};
}"""

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_context(
        ignore_https_errors=True, viewport={"width": 1280, "height": 1000}, user_agent="Mozilla/5.0"
    ).new_page()
    pg.goto(url, wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(3000)
    if clicar:
        try:
            pg.get_by_text(clicar, exact=False).first.click(timeout=8000)
            pg.wait_for_timeout(5000)
        except Exception as e:
            print("clique falhou:", str(e)[:100])
    import json

    print("URL FINAL:", pg.url)
    d = pg.evaluate(DUMP)
    print("SITEKEYS:", d["sitekeys"])
    print("FORMS:", json.dumps(d["forms"], ensure_ascii=False)[:400])
    print("IFRAMES:", [i for i in d["iframes"] if i][:6])
    print("INPUTS visíveis:")
    for i in d["inputs"]:
        if i["vis"] and i["type"] not in ("hidden",):
            print("  ", json.dumps(i, ensure_ascii=False))
    print("BOTÕES/LINKS:", [x[:30] for x in d["btns"]][:30])
    pg.screenshot(path="/tmp/explore.png", full_page=True)
    print("screenshot: /tmp/explore.png")
    b.close()
