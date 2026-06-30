"""DIAGNÓSTICO do modal MFA do Sólides Benefícios (HOST, headless).
Abre login -> email -> Solicitar PIN -> introspecta DOM (shadow+iframes) p/ achar
as 6 caixas de PIN e o botão Validar -> tenta preencher com PIN FALSO 123456 por
vários métodos -> screenshots em cada passo. NÃO valida login real (PIN é falso)."""

import json

from playwright.sync_api import sync_playwright

env = {}
for l in open("/opt/conecta-pro/credentials/solides_web.env"):
    if "=" in l and not l.startswith("#"):
        k, v = l.strip().split("=", 1)
        env[k] = v

LOG = "/tmp/benef_diag.log"
open(LOG, "w").write("")


def log(m):
    open(LOG, "a").write(str(m) + "\n")
    print(m, flush=True)


# JS que varre document + todos os shadow roots e devolve inputs com geometria
INTROSPECT = r"""
() => {
  const out = [];
  function walk(root, path) {
    const els = root.querySelectorAll('*');
    for (const e of els) {
      const tag = e.tagName.toLowerCase();
      if (tag === 'input' || (e.getAttribute && e.getAttribute('contenteditable') === 'true')) {
        const r = e.getBoundingClientRect();
        out.push({
          path, tag,
          type: e.type || '',
          maxlength: e.getAttribute && e.getAttribute('maxlength'),
          inputmode: e.getAttribute && e.getAttribute('inputmode'),
          name: e.name || '', id: e.id || '',
          ph: e.placeholder || '',
          x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height),
          vis: r.width > 0 && r.height > 0,
        });
      }
      if (e.shadowRoot) walk(e.shadowRoot, path + '>' + tag + '#sr');
    }
  }
  walk(document, 'doc');
  // botoes com texto Validar
  const btns = [];
  function walkb(root, path) {
    for (const e of root.querySelectorAll('button, [role=button], a')) {
      const t = (e.innerText || e.textContent || '').trim();
      if (/validar/i.test(t)) {
        const r = e.getBoundingClientRect();
        btns.push({ path, text: t.slice(0,30), x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2) });
      }
      if (e.shadowRoot) walkb(e.shadowRoot, path + '#sr');
    }
  }
  walkb(document, 'doc');
  return { inputs: out, validar: btns };
}
"""

with sync_playwright() as b0:
    b = b0.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1280, "height": 720})
    pg = ctx.new_page()
    pg.goto("https://portal-beneficios.solides.com.br/login", wait_until="networkidle", timeout=45000)
    pg.wait_for_timeout(8000)
    # email
    pg.keyboard.press("Tab")
    pg.wait_for_timeout(400)
    pg.keyboard.type(env["PYETRA_USER"], delay=20)
    pg.wait_for_timeout(700)
    pg.keyboard.press("Enter")  # Solicitar PIN
    pg.wait_for_timeout(7000)
    pg.screenshot(path="/tmp/benef_diag_modal.png")

    # 1) Introspecção no documento principal + shadow roots
    data = pg.evaluate(INTROSPECT)
    log("=== MAIN FRAME inputs (shadow incluso) ===")
    log(json.dumps(data["inputs"], ensure_ascii=False, indent=1))
    log("=== botoes Validar (main) ===")
    log(json.dumps(data["validar"], ensure_ascii=False))

    # 2) Iframes
    log("=== FRAMES ===")
    for fr in pg.frames:
        log("frame url=" + (fr.url or "")[:80])
        try:
            fd = fr.evaluate(INTROSPECT)
            if fd["inputs"]:
                log("  inputs no frame:")
                log("  " + json.dumps(fd["inputs"], ensure_ascii=False))
            if fd["validar"]:
                log("  validar no frame: " + json.dumps(fd["validar"], ensure_ascii=False))
        except Exception as exc:
            log("  (erro introspectando frame: %s)" % exc)

    # 3) Tenta preencher com PIN FALSO 123456 — método A: locator nos inputs visiveis
    fake = "123456"
    filled_method = None
    try:
        # acha inputs visiveis com maxlength 1 ou pequenos (caixas de PIN)
        candidatos = [i for i in data["inputs"] if i["vis"] and i["w"] < 80 and i["h"] < 80]
        log("candidatos a caixa de PIN (main): %d" % len(candidatos))
        if len(candidatos) >= 6:
            cs = sorted(candidatos, key=lambda i: i["x"])[:6]
            for c, d in zip(cs, fake, strict=False):
                pg.mouse.click(c["x"] + c["w"] // 2, c["y"] + c["h"] // 2)
                pg.wait_for_timeout(80)
                pg.keyboard.type(d, delay=40)
                pg.wait_for_timeout(80)
            filled_method = "coord-por-caixa"
    except Exception as exc:
        log("metodo A erro: %s" % exc)

    pg.wait_for_timeout(500)
    pg.screenshot(path="/tmp/benef_diag_fill.png")
    after = pg.evaluate(INTROSPECT)
    cheias = [i for i in after["inputs"] if i.get("vis")]
    log("metodo usado: %s" % filled_method)
    log("screenshot de preenchimento: /tmp/benef_diag_fill.png")
    log("FIM diagnostico")
    b.close()
