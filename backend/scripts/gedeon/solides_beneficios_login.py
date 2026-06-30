"""Robô login Sólides Benefícios (MFA — caixas em shadow DOM fechado, preenche por COORDENADA).
Fluxo: login -> email -> Solicitar PIN -> ESPERA PIN em /tmp/benef_pin.txt ->
clica cada caixa (centro) e digita -> clica Validar PIN -> salva sessão (storage_state).
COORDS provadas (viewport 1280x720): caixas x=[316,445,575,704,834,963] y=415; Validar=(898,483)."""

import os
import time

from playwright.sync_api import sync_playwright

env = {}
for l in open("/opt/conecta-pro/credentials/solides_web.env"):
    if "=" in l and not l.startswith("#"):
        k, v = l.strip().split("=", 1)
        env[k] = v

PINFILE = "/tmp/benef_pin.txt"
STATUS = "/tmp/benef_status.txt"
SESS = "/opt/conecta-pro/credentials/benef_session.json"

BOXES = [316, 445, 575, 704, 834, 963]
BY = 415
VALIDAR = (898, 483)


def log(m):
    open(STATUS, "a").write(str(m) + "\n")
    print(m, flush=True)


open(STATUS, "w").write("")
if os.path.exists(PINFILE):
    os.remove(PINFILE)

with sync_playwright() as b0:
    b = b0.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1280, "height": 720})
    pg = ctx.new_page()
    pg.goto("https://portal-beneficios.solides.com.br/login", wait_until="networkidle", timeout=45000)
    pg.wait_for_timeout(8000)
    pg.keyboard.press("Tab")
    pg.wait_for_timeout(400)
    pg.keyboard.type(env["PYETRA_USER"], delay=20)
    pg.wait_for_timeout(700)
    pg.keyboard.press("Enter")  # Solicitar PIN
    pg.wait_for_timeout(7000)
    pg.screenshot(path="/tmp/benef_pinscreen.png")
    log("PIN SOLICITADO. Aguardando PIN em " + PINFILE + " (ate 240s)")

    pin = None
    for _ in range(240):
        if os.path.exists(PINFILE):
            pin = open(PINFILE).read().strip()
            if pin:
                break
        time.sleep(1)
    if not pin:
        log("TIMEOUT sem PIN")
        pg.screenshot(path="/tmp/benef_final.png")
        raise SystemExit
    digs = [d for d in pin if d.isdigit()][:6]
    log("inserindo PIN: " + "".join(digs))

    for x, d in zip(BOXES, digs, strict=False):
        pg.mouse.click(x, BY)
        pg.wait_for_timeout(120)
        pg.keyboard.type(d, delay=50)
        pg.wait_for_timeout(120)
    pg.wait_for_timeout(300)
    pg.screenshot(path="/tmp/benef_afterpin.png")

    # SUBMETE o PIN: Enter (foco na ultima caixa) submete de forma confiavel; clica Validar tb
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(1200)
    pg.mouse.click(*VALIDAR)
    pg.wait_for_timeout(4500)
    pg.screenshot(path="/tmp/benef_pwstep.png")
    log("PIN submetido. url=" + pg.url)

    # ETAPA SENHA: senha do Benefícios (PYETRA_BENEFICIOS_PASS)
    senha = env.get("PYETRA_BENEFICIOS_PASS", "")
    PW_FIELD = (550, 357)
    ENTRAR = (640, 398)
    metodo = None
    try:
        loc = pg.locator("input[type=password]")
        if loc.count() > 0:
            loc.first.click()
            pg.wait_for_timeout(200)
            loc.first.fill(senha)
            metodo = "locator(%d)" % loc.count()
    except Exception as exc:
        log("locator senha falhou: %s" % exc)
    if metodo is None:  # fallback coordenada
        pg.mouse.click(*PW_FIELD)
        pg.wait_for_timeout(250)
        pg.keyboard.type(senha, delay=40)
        metodo = "coord"
    log("senha preenchida (metodo=%s)" % metodo)
    pg.wait_for_timeout(400)
    pg.screenshot(path="/tmp/benef_pwfilled.png")

    # Entrar: Enter (foco no campo senha) + clique no botao
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(1500)
    pg.mouse.click(*ENTRAR)
    pg.wait_for_timeout(8000)
    log("url final: " + pg.url)
    pg.screenshot(path="/tmp/benef_final.png")
    if "login" not in pg.url:
        ctx.storage_state(path=SESS)
        log("OK LOGADO + sessao salva em " + SESS)
    else:
        log("AINDA EM LOGIN (verificar senha/etapa)")
    # mantem o browser aberto +20s p/ inspecao final
    pg.wait_for_timeout(20000)
    pg.screenshot(path="/tmp/benef_final2.png")
    b.close()
