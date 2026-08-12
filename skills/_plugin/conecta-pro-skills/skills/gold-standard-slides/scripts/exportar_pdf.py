"""Exporta deck HTML → PDF (1 página por slide, 1920×1080 nítido).
Uso: python3 exportar_pdf.py <deck.html> [saida.pdf]
Requer: playwright (instalado no host) + pillow.
"""
import io, sys, os
from playwright.sync_api import sync_playwright
from PIL import Image

deck = os.path.abspath(sys.argv[1])
out = sys.argv[2] if len(sys.argv) > 2 else deck.rsplit(".", 1)[0] + ".pdf"
imgs = []

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1920, "height": 1080})
    pg.goto(f"file://{deck}", wait_until="domcontentloaded")
    pg.wait_for_timeout(2500)
    n = pg.evaluate("document.querySelectorAll('.slide').length")
    for i in range(n):
        pg.wait_for_timeout(1200)  # deixa o reveal terminar
        imgs.append(Image.open(io.BytesIO(pg.screenshot())).convert("RGB"))
        pg.keyboard.press("ArrowRight")
    b.close()

imgs[0].save(out, save_all=True, append_images=imgs[1:], quality=92)
print(f"PDF: {out} ({n} slides, {os.path.getsize(out)//1024}KB)")
