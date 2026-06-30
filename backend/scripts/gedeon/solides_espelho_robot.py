"""GEDEON — Robô do espelho de ponto assinado (Sólides/Tangerino via Playwright).
Roda no HOST (Playwright+Chromium). Loga como Pyetra, filtra competência, baixa
cada folha de ponto ASSINADA (link S3 presigned) → uploads/solides_espelhos/ + manifesto."""

import json
import re
import sys
import unicodedata

import httpx
from playwright.sync_api import sync_playwright

DEST = "/opt/conecta-pro/uploads/solides_espelhos"


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def creds():
    e = {}
    for l in open("/opt/conecta-pro/credentials/solides_web.env"):
        if "=" in l and not l.startswith("#"):
            k, v = l.strip().split("=", 1)
            e[k] = v
    return e


def baixar_assinados(dt_ini="20/04/2026", dt_fim="31/05/2026"):
    e = creds()
    import os

    os.makedirs(DEST, exist_ok=True)
    with sync_playwright() as b0:
        b = b0.chromium.launch(headless=True)
        pg = b.new_context().new_page()
        pg.goto("https://app.tangerino.com.br/Tangerino/pages/LoginPage", wait_until="domcontentloaded", timeout=30000)
        pg.wait_for_timeout(2500)
        pg.fill("input[name=login]", e["PYETRA_USER"])
        pg.fill("input[name=password]", e["PYETRA_SOLIDES_PASS"])
        pg.click("input[name=btnLogin]")
        pg.wait_for_timeout(8000)
        if "LoginPage" in pg.url:
            raise SystemExit("login falhou")
        pg.goto(
            "https://app.tangerino.com.br/Tangerino/pages/assinatura-eletronica?funcionalidade=85",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        pg.wait_for_timeout(4000)
        pg.get_by_text("Status de Assinaturas Individuais", exact=True).first.click(timeout=5000)
        pg.wait_for_timeout(4000)
        js = """(a)=>{const[n,l]=a;const s=document.querySelector(`select[name='${n}']`);if(!s)return;const o=[...s.options].find(o=>o.text.trim()===l);if(o){s.value=o.value;s.dispatchEvent(new Event('change',{bubbles:true}));}}"""
        pg.evaluate(js, ["statusAssinaturaDigital", "Assinado"])
        pg.wait_for_timeout(800)
        for nm, val in [("dataInicioContainer:dataInicio", dt_ini), ("dataFimContainer:dataFim", dt_fim)]:
            pg.fill(f"input[name='{nm}']", val)
            pg.dispatch_event(f"input[name='{nm}']", "change")
        pg.click("#idf3")
        pg.wait_for_timeout(9000)
        # cells: 1=Colaborador, 2=Período Folha, 5=Doc.Assinado (link S3)
        EXTRACT = """()=>{const t=[...document.querySelectorAll('table')].find(x=>[...x.querySelectorAll('th')].some(h=>/Colaborador/i.test(h.innerText)));if(!t)return[];return [...t.querySelectorAll('tbody tr')].filter(r=>r.cells.length>5).map(r=>{const a=r.cells[5].querySelector('a[href*=s3]');return a?{nome:r.cells[1].innerText.trim(),periodo:r.cells[2].innerText.trim(),href:a.href}:null;}).filter(Boolean);}"""
        # percorre TODAS as páginas via o link ">" (próxima); ">>" é última página (NÃO usar).
        todas = []
        pagina = 0
        for pagina in range(40):
            atual = pg.evaluate(EXTRACT)
            todas.extend(atual)
            antes = atual[0]["nome"] if atual else None
            nxt = pg.locator("a.simbolos").filter(has_text=re.compile(r"^>$"))
            if nxt.count() == 0:
                break
            try:
                nxt.first.click(timeout=4000)
                pg.wait_for_timeout(3500)
            except Exception:
                break
            depois = pg.evaluate(EXTRACT)
            if not depois or depois[0]["nome"] == antes:
                break  # não avançou = última página

        # dedup por funcionário, mantendo o ESPELHO de período mais recente (folha de maio > abril)
        def _keyp(per):
            ds = re.findall(r"(\d{2})/(\d{2})/(\d{4})", per or "")
            if not ds:
                return ""
            d, m, y = ds[-1]
            return y + m + d  # última data do período (sortable AAAAMMDD)

        best = {}
        for x in todas:
            nm = x["nome"].strip().upper()
            if not nm:
                continue
            k = _keyp(x.get("periodo"))
            if nm not in best or k > best[nm][0]:
                best[nm] = (k, x)
        pares = [v[1] for v in best.values()]
        print(
            f"paginas percorridas: {pagina + 1} | linhas: {len(todas)} | funcionarios distintos: {len(pares)}",
            file=sys.stderr,
        )
        b.close()
    manifesto = []
    for p in pares:
        try:
            r = httpx.get(p["href"], timeout=60)
            r.raise_for_status()
            fn = f"{slug(p['nome'])}.pdf"
            open(f"{DEST}/{fn}", "wb").write(r.content)
            manifesto.append({"nome": p["nome"], "arquivo": fn, "bytes": len(r.content)})
        except Exception as ex:
            print("falha", p["nome"], str(ex)[:50])
    json.dump(manifesto, open(f"{DEST}/manifesto.json", "w"), ensure_ascii=False, indent=2)
    return manifesto


if __name__ == "__main__":
    di = sys.argv[1] if len(sys.argv) > 1 else "20/04/2026"
    df = sys.argv[2] if len(sys.argv) > 2 else "31/05/2026"
    m = baixar_assinados(di, df)
    print(f"baixados {len(m)} espelhos assinados (janela {di}-{df}):")
    for x in m:
        print(f"  {x['nome'][:32]:32s} {x['bytes']} bytes")
