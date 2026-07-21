"""
ORÁCULO DE FIDELIDADE (Fase 2) — compara Clássico × Redesign por tela.

Uso:
  python3 oraculo_fidelidade.py <classic_path> <redesign_path> <label> [out_dir]
Ex:
  python3 oraculo_fidelidade.py /modulos/fiscal/certidoes "/redesign/fiscal?t=certidoes" fiscal-certidoes

Faz: login (token compartilhado clássico/redesign), captura SCREENSHOT dos dois lados +
extrai o texto visível (tabelas/KPIs/títulos), e imprime um DIFF de fidelidade — o que o
clássico mostra e o redesign NÃO (e vice-versa). Salva os 2 PNGs lado a lado p/ o verificador
olhar. Regra (ruling do Jordan): a INFORMAÇÃO do clássico é a fonte da verdade.

NÃO é automático 100% (mapeamento de tela é humano) — é a ferramenta que torna "fiel"
objetivo em vez de opinião. Rodar ANTES de declarar uma tela fiel.
"""
import sys

from playwright.sync_api import sync_playwright

BASE = "https://erp.conectamais.pro"
USER = "mcp-service@conectamais.pro"
PWD = "67142814d66bdb5aa96b97e902e98cc486ae"

_EXTRACT = r"""() => {
  const seen = new Set(), out = [];
  const sel = 'table tbody tr, [class*=row], [class*=kpi], [class*=card] h3, h1, h2, .rd-badge';
  document.querySelectorAll(sel).forEach(e => {
    let t = (e.innerText || '').trim().replace(/\s+/g, ' ');
    if (t && t.length > 1 && t.length < 200 && !seen.has(t)) { seen.add(t); out.push(t); }
  });
  return out.slice(0, 150);
}"""


def run(classic_path, redesign_path, label, out_dir):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 1000})
        pg = ctx.new_page()
        pg.goto(f"{BASE}/redesign/login", wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_timeout(1400)
        pg.fill("input[type=email]", USER)
        pg.fill("input[type=password]", PWD)
        pg.click("button[type=submit]")
        try:
            pg.wait_for_url("**/redesign", timeout=20000)
        except Exception:
            pass
        data = {}
        for path, tag in [(classic_path, "classico"), (redesign_path, "redesign")]:
            try:
                pg.goto(f"{BASE}{path}", wait_until="domcontentloaded", timeout=45000)
                pg.wait_for_timeout(3200)
                pg.screenshot(path=f"{out_dir}/oraculo_{label}_{tag}.png", full_page=True)
                data[tag] = pg.evaluate(_EXTRACT)
            except Exception as e:
                data[tag] = [f"__ERRO__ {str(e)[:80]}"]
        ctx.close()
        b.close()
    c, r = set(data.get("classico", [])), set(data.get("redesign", []))
    print(f"=== ORÁCULO: {label} ===")
    print(f"clássico: {len(c)} elementos | redesign: {len(r)} elementos")
    so_classico = [x for x in data.get("classico", []) if x not in r][:25]
    so_redesign = [x for x in data.get("redesign", []) if x not in c][:25]
    print(f"\n[!] SÓ no CLÁSSICO (fidelidade pede trazer p/ o redesign) — {len(so_classico)}:")
    for x in so_classico:
        print(f"   - {x[:110]}")
    print(f"\n[?] SÓ no REDESIGN (verificar se é real ou divergência do design) — {len(so_redesign)}:")
    for x in so_redesign:
        print(f"   - {x[:110]}")
    print(f"\nscreenshots: oraculo_{label}_classico.png / oraculo_{label}_redesign.png")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("uso: oraculo_fidelidade.py <classic_path> <redesign_path> <label> [out_dir]")
        sys.exit(1)
    run(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else ".")
