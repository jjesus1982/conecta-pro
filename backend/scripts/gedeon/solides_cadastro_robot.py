"""Robô Sólides — extrai o "Relatório de Colaboradores" (app.tangerino.com.br) e
backfilla campos VAZIOS do onboarding em employees (nunca sobrescreve o curado).

Vence o reCAPTCHA v2 do login via 2captcha (TWOCAPTCHA_API_KEY). Cobertura do
relatório: telefone, RG, estado_civil, nacionalidade (via 'Estrangeiro'), sexo,
nascimento, escolaridade. NÃO tem endereço/nome_mãe/naturalidade (ficam na ficha
individual — Sólides muitas vezes vazio). Roda no HOST.

Uso:
  PYETRA_USER=... PYETRA_SOLIDES_PASS=... TWOCAPTCHA_API_KEY=... \
  DATABASE_URL=... python3 solides_cadastro_robot.py [--dry-run]
"""
import os, re, sys, time, json, httpx
from playwright.sync_api import sync_playwright

LOGIN = "https://app.tangerino.com.br/Tangerino/pages/LoginPage"
COLAB = "https://app.tangerino.com.br/Tangerino/pages/colaboradores?funcionalidade=3"
U, P = os.environ["PYETRA_USER"], os.environ["PYETRA_SOLIDES_PASS"]
KEY = os.environ["TWOCAPTCHA_API_KEY"]
DRY = "--dry-run" in sys.argv


def _sitekey(pg):
    hit = [None]
    pg.on("request", lambda r: hit.__setitem__(0, (re.search(r"[?&]k=([\w-]{30,})", r.url) or [None, hit[0]])[1]) if "recaptcha/api2" in r.url else None)
    pg.goto(LOGIN, wait_until="networkidle", timeout=45000)
    pg.wait_for_timeout(4000)
    return hit[0]


def _solve(sitekey):
    with httpx.Client(timeout=30) as c:
        cid = c.post("https://2captcha.com/in.php", data={"key": KEY, "method": "userrecaptcha", "googlekey": sitekey, "pageurl": LOGIN, "json": 1}).json()["request"]
        for _ in range(40):
            time.sleep(6)
            d = c.get("https://2captcha.com/res.php", params={"key": KEY, "action": "get", "id": cid, "json": 1}).json()
            if d.get("status") == 1:
                return d["request"]
    raise SystemExit("2captcha timeout")


def extrair() -> list[dict]:
    import xlrd
    dest = "/tmp/tang_colab.xls"
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        pg = ctx.new_page()
        token = _solve(_sitekey(pg))
        pg.fill("input[name=login]", U); pg.fill("input[name=password]", P)
        pg.evaluate("(t)=>{let ta=document.getElementById('g-recaptcha-response')||(()=>{let x=document.createElement('textarea');x.id='g-recaptcha-response';x.name='g-recaptcha-response';document.body.appendChild(x);return x;})();ta.value=t;}", token)
        pg.click("input[name=btnLogin]"); pg.wait_for_timeout(11000)
        if "LoginPage" in pg.url:
            raise SystemExit("login falhou (captcha/senha)")
        pg.goto(COLAB, wait_until="domcontentloaded", timeout=35000); pg.wait_for_timeout(7000)
        with pg.expect_download(timeout=40000) as di:
            pg.click("text=Exportar Excel")
        di.value.save_as(dest)
        b.close()
    wb = xlrd.open_workbook(dest); sh = wb.sheet_by_index(0)
    hdr_r = next(r for r in range(10) if "Colaborador" in str(sh.cell_value(r, 0)))
    dig = lambda s: re.sub(r"\D", "", str(s or ""))
    out = []
    for r in range(hdr_r + 1, sh.nrows):
        cpf = dig(sh.cell_value(r, 7))
        if len(cpf) != 11:
            continue
        estr = str(sh.cell_value(r, 24)).strip().lower()
        out.append({
            "cpf": cpf,
            "telefone": str(sh.cell_value(r, 13)).strip(),
            "rg": dig(sh.cell_value(r, 8)),
            "estado_civil": str(sh.cell_value(r, 38)).strip(),
            "nacionalidade": "Brasileira" if estr in ("não", "nao", "n", "false", "") else "",
        })
    return out


def backfill(regs: list[dict]) -> None:
    from sqlalchemy import create_engine, text
    eng = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
    with eng.begin() as c:
        n = 0
        for r in regs:
            n += c.execute(text("""
                UPDATE employees SET
                  telefone = CASE WHEN coalesce(telefone,'')='' AND :tel<>'' THEN :tel ELSE telefone END,
                  rg = CASE WHEN coalesce(rg,'')='' AND :rg<>'' THEN :rg ELSE rg END,
                  estado_civil = CASE WHEN coalesce(estado_civil,'')='' AND :ec<>'' THEN :ec ELSE estado_civil END,
                  nacionalidade = CASE WHEN coalesce(nacionalidade,'')='' AND :nac<>'' THEN :nac ELSE nacionalidade END
                WHERE status='ativo' AND regexp_replace(coalesce(cpf,''),'[^0-9]','','g') = :cpf
            """), {"tel": r["telefone"], "rg": r["rg"], "ec": r["estado_civil"], "nac": r["nacionalidade"], "cpf": r["cpf"]}).rowcount
    print(f"backfill: {n} linhas atualizadas (só campos vazios)")


if __name__ == "__main__":
    regs = extrair()
    print(f"extraídos {len(regs)} colaboradores do relatório Sólides")
    if DRY:
        print(json.dumps(regs[:2], ensure_ascii=False, indent=1))
    else:
        backfill(regs)
