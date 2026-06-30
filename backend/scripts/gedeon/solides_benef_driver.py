"""Robô INTERATIVO Sólides Benefícios. Pede PIN, preenche, e fica VIVO aceitando
comandos em /tmp/benef_cmd.txt (1 por vez, apagado apos ler). Screenshot ao vivo
em /tmp/benef_live.png apos cada comando. Tudo na MESMA sessao (1 PIN só).

Comandos: v=ValidarPIN | e=Enter | t=Tab | pw=preenche senha(coord) |
  pwl=preenche senha(locator) | ent=Entrar(coord) | i=introspect DOM |
  s=salva sessao se logado | shot=so screenshot | c X,Y=clica coord |
  k TEXTO=digita texto | q=quit. Tambem tenta submit automatico proven (v+e) 1x."""

import os
import time

from playwright.sync_api import sync_playwright

env = {}
for l in open("/opt/conecta-pro/credentials/solides_web.env"):
    if "=" in l and not l.startswith("#"):
        k, v = l.strip().split("=", 1)
        env[k] = v

PINFILE = "/tmp/benef_pin.txt"
CMD = "/tmp/benef_cmd.txt"
STATUS = "/tmp/benef_status.txt"
SESS = "/opt/conecta-pro/credentials/benef_session.json"
BOXES = [316, 445, 575, 704, 834, 963]
BY = 415
VALIDAR = (898, 483)
PW_FIELD = (550, 357)
ENTRAR = (640, 398)

INTRO = r"""()=>{const o=[];function w(r,p){for(const e of r.querySelectorAll('*')){
const t=e.tagName.toLowerCase();if(t==='input'){const c=e.getBoundingClientRect();
o.push({t,type:e.type||'',ml:e.getAttribute&&e.getAttribute('maxlength'),x:Math.round(c.x),y:Math.round(c.y),w:Math.round(c.width),vis:c.width>0});}
if(e.shadowRoot)w(e.shadowRoot,p+'#sr');}}w(document,'d');return o;}"""


def log(m):
    open(STATUS, "a").write(str(m) + "\n")
    print(m, flush=True)


open(STATUS, "w").write("")
for f in (PINFILE, CMD):
    if os.path.exists(f):
        os.remove(f)

with sync_playwright() as b0:
    b = b0.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1280, "height": 720})
    pg = ctx.new_page()

    def shot():
        pg.screenshot(path="/tmp/benef_live.png")

    pg.goto("https://portal-beneficios.solides.com.br/login", wait_until="networkidle", timeout=45000)
    pg.wait_for_timeout(8000)
    pg.keyboard.press("Tab")
    pg.wait_for_timeout(400)
    pg.keyboard.type(env["PYETRA_USER"], delay=20)
    pg.wait_for_timeout(700)
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(7000)
    shot()
    log("PIN SOLICITADO. Aguardando PIN em " + PINFILE)

    pin = None
    for _ in range(240):
        if os.path.exists(PINFILE):
            pin = open(PINFILE).read().strip()
            if pin:
                break
        time.sleep(1)
    if not pin:
        log("TIMEOUT sem PIN")
        b.close()
        raise SystemExit
    digs = [d for d in pin if d.isdigit()][:6]
    log("preenchendo PIN " + "".join(digs))
    for x, d in zip(BOXES, digs, strict=False):
        pg.mouse.click(x, BY)
        pg.wait_for_timeout(120)
        pg.keyboard.type(d, delay=50)
        pg.wait_for_timeout(120)
    pg.wait_for_timeout(300)
    shot()

    senha = env.get("PYETRA_BENEFICIOS_PASS", "")

    def do(cmd):
        cmd = cmd.strip()
        if cmd == "v":
            pg.mouse.click(*VALIDAR)
        elif cmd == "e":
            pg.keyboard.press("Enter")
        elif cmd == "t":
            pg.keyboard.press("Tab")
        elif cmd == "pw":
            pg.mouse.click(*PW_FIELD)
            pg.wait_for_timeout(250)
            pg.keyboard.type(senha, delay=40)
        elif cmd == "pwl":
            loc = pg.locator("input[type=password]")
            log("password inputs=%d" % loc.count())
            if loc.count() > 0:
                loc.first.click()
                pg.wait_for_timeout(150)
                loc.first.fill(senha)
        elif cmd == "ent":
            pg.mouse.click(*ENTRAR)
        elif cmd == "i":
            log("INTROSPECT: " + str(pg.evaluate(INTRO)))
        elif cmd == "s":
            if "login" not in pg.url:
                ctx.storage_state(path=SESS)
                log("SESSAO SALVA " + SESS)
            else:
                log("nao logado, nao salvo")
        elif cmd.startswith("c "):
            x, y = cmd[2:].split(",")
            pg.mouse.click(int(x), int(y))
        elif cmd.startswith("k "):
            pg.keyboard.type(cmd[2:], delay=40)
        elif cmd == "shot":
            pass
        pg.wait_for_timeout(1500)
        shot()
        log("apos '%s' url=%s" % (cmd, pg.url))

    # tentativa automatica: SO clicar Validar (1 submit, sem Enter — evita double-submit)
    log("auto-submit: so v (clique unico em Validar)")
    do("v")
    # se avancou (sumiu o PIN), tenta senha
    if "login" not in pg.url:
        do("pwl")
        do("ent")
    if "login" not in pg.url:
        ctx.storage_state(path=SESS)
        log("AUTO OK LOGADO + sessao salva")

    # loop interativo (ate 200s) — eu dirijo via /tmp/benef_cmd.txt
    log("MODO INTERATIVO. comandos em " + CMD)
    for _ in range(200):
        if os.path.exists(CMD):
            c = open(CMD).read().strip()
            os.remove(CMD)
            if c == "q":
                break
            if c:
                try:
                    do(c)
                except Exception as exc:
                    log("erro cmd '%s': %s" % (c, exc))
        time.sleep(1)
    if "login" not in pg.url:
        ctx.storage_state(path=SESS)
        log("FIM LOGADO + sessao salva")
    shot()
    log("encerrando. url=" + pg.url)
    b.close()
