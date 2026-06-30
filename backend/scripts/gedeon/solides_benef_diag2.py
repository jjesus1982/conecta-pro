"""TESTE de preenchimento (PIN FALSO 123456) — confirma coords das caixas.
Clica cada caixa pelo centro e digita o dígito. Screenshot pra verificar visual."""

from playwright.sync_api import sync_playwright

env = {}
for l in open("/opt/conecta-pro/credentials/solides_web.env"):
    if "=" in l and not l.startswith("#"):
        k, v = l.strip().split("=", 1)
        env[k] = v

BOXES = [316, 445, 575, 704, 834, 963]  # x dos centros
BY = 415  # y dos centros
VALIDAR = (898, 483)
LOG = "/tmp/benef_diag2.log"
open(LOG, "w").write("")


def log(m):
    open(LOG, "a").write(str(m) + "\n")
    print(m, flush=True)


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
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(7000)
    pg.screenshot(path="/tmp/benef_d2_modal.png")
    log("modal aberto")

    # MÉTODO 1: clica cada caixa e digita
    fake = "123456"
    for x, d in zip(BOXES, fake, strict=False):
        pg.mouse.click(x, BY)
        pg.wait_for_timeout(120)
        pg.keyboard.type(d, delay=50)
        pg.wait_for_timeout(120)
    pg.wait_for_timeout(400)
    pg.screenshot(path="/tmp/benef_d2_fill1.png")
    log("metodo1 (clica-cada-caixa+digita) -> /tmp/benef_d2_fill1.png")

    b.close()
