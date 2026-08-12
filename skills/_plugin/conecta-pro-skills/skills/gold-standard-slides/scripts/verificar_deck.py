"""Verificação obrigatória de deck: screenshot de cada slide + checagem de overflow.
Uso: python3 verificar_deck.py <deck.html> <prefixo_saida>
Sai com código 1 se detectar overflow de conteúdo em algum slide.
"""
import sys
from playwright.sync_api import sync_playwright

deck, prefix = sys.argv[1], sys.argv[2]
problemas = []

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1280, "height": 720})
    pg.goto(f"file://{deck}", wait_until="domcontentloaded")
    pg.wait_for_timeout(2500)
    n = pg.evaluate("document.querySelectorAll('.slide').length")
    for i in range(n):
        pg.wait_for_timeout(1100)
        pg.screenshot(path=f"{prefix}_slide{i+1}.png")
        # overflow: conteúdo maior que o palco 1920×1080
        ov = pg.evaluate("""() => {
            const s = document.querySelectorAll('.slide')[%d];
            const out = [];
            if (s.scrollHeight > 1082 || s.scrollWidth > 1922)
                out.push(`slide estoura palco (${s.scrollWidth}x${s.scrollHeight})`);
            for (const el of s.querySelectorAll('*')) {
                const r = el.getBoundingClientRect ? null : null;
                if (el.scrollHeight > el.clientHeight + 4 && getComputedStyle(el).overflow !== 'hidden')
                    out.push(`texto cortado em <${el.tagName.toLowerCase()} class="${el.className}">`);
            }
            return out.slice(0, 3);
        }""" % i)
        if ov:
            problemas.append((i + 1, ov))
        pg.keyboard.press("ArrowRight")
    b.close()

print(f"{n} slides capturados: {prefix}_slide*.png")
for num, ov in problemas:
    print(f"PROBLEMA slide {num}: {'; '.join(ov)}")
sys.exit(1 if problemas else 0)
