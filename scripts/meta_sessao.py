#!/usr/bin/env python3
"""Sessão de navegador na Meta (Business Manager) — mesmo padrão do det-robot.

Serve para colher o que a integração precisa e a UI da Meta só entrega logada:
token de System User com `ads_read`, id da conta de anúncios, e o token da
Conversions API no Events Manager.

Reusa o que já funciona contra portal do governo neste repo (`det-robot/robot.py`):
  • PERFIL PERSISTENTE — cookies + "confiança" do navegador ficam no disco. O
    1º login é o caro (checkpoint/2FA); depois disso o perfil carrega a sessão
    e os passos seguintes rodam direto.
  • `--disable-blink-features=AutomationControlled` + `ignore_default_args`
    `--enable-automation`: sem isso o `navigator.webdriver` entrega o robô.
  • User-Agent real de Chrome/Windows, viewport de gente.

Credenciais NUNCA em argumento de linha de comando (ficariam no `ps` e no
histórico) — só via env:
    META_LOGIN_EMAIL, META_LOGIN_PASS

Passos (cada um deixa screenshot em state/meta/):
    python3 scripts/meta_sessao.py login          # loga; para em 2FA se houver
    python3 scripts/meta_sessao.py codigo 123456  # entrega o código do 2FA
    python3 scripts/meta_sessao.py ver <url>      # navega logado e fotografa
    python3 scripts/meta_sessao.py estado         # a sessão está viva?
"""

import asyncio
import os
import pathlib
import sys

PERFIL = os.getenv("META_PROFILE", "/opt/conecta-pro/det-robot/state/meta_profile")
SHOTS = pathlib.Path(os.getenv("META_SHOTS", "/opt/conecta-pro/det-robot/state/meta"))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _ctx(pw, headless: bool = True):
    """Contexto persistente, com as mesmas defesas do det-robot."""
    pathlib.Path(PERFIL).mkdir(parents=True, exist_ok=True)
    return pw.chromium.launch_persistent_context(
        PERFIL,
        headless=headless,
        ignore_default_args=["--enable-automation"],
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1440,900",
        ],
        user_agent=UA,
        locale="pt-BR",
        timezone_id="America/Manaus",
        viewport={"width": 1440, "height": 900},
    )


async def _foto(pg, nome: str) -> str:
    SHOTS.mkdir(parents=True, exist_ok=True)
    caminho = SHOTS / f"{nome}.png"
    await pg.screenshot(path=str(caminho), full_page=True)
    return str(caminho)


async def _diagnostico(pg) -> str:
    """Diz em UMA linha onde a sessão parou — é o que importa entre um passo e outro."""
    url = pg.url
    corpo = (await pg.inner_text("body"))[:400].lower()
    if "business.facebook.com" in url and "login" not in url:
        return "LOGADO no Business Manager"
    if any(w in corpo for w in ("código de login", "codigo de login", "autenticação de dois",
                                "two-factor", "insira o código", "confirme que é você",
                                "confirme que e voce")):
        return "PAROU EM 2FA/CHECKPOINT — rode: meta_sessao.py codigo <codigo>"
    if "senha incorreta" in corpo or "não corresponde" in corpo:
        return "CREDENCIAL RECUSADA pela Meta"
    if "login" in url or "entrar" in corpo[:120]:
        return "AINDA NA TELA DE LOGIN"
    return f"estado desconhecido — url={url[:80]}"


async def cmd_login() -> int:
    email, senha = os.getenv("META_LOGIN_EMAIL", ""), os.getenv("META_LOGIN_PASS", "")
    if not (email and senha):
        print("META_LOGIN_EMAIL / META_LOGIN_PASS não definidas — não vou adivinhar.")
        return 2
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        ctx = await _ctx(pw)
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await pg.goto("https://business.facebook.com/", wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(3000)
        # Já logado pelo perfil? Então não toca em nada.
        if "login" not in pg.url and "business.facebook.com" in pg.url:
            print(f"  já logado pelo perfil persistente · {await _foto(pg, '00_ja_logado')}")
            await ctx.close()
            return 0
        # A entrada do Business é um SELETOR, não um formulário: "Continuar com o
        # Facebook" / "Continuar com o Instagram" / "Conta Meta gerenciada". Só depois
        # de escolher é que aparece usuário+senha. META_LOGIN_VIA decide o caminho.
        via = os.getenv("META_LOGIN_VIA", "instagram").lower()
        rotulo = "Instagram" if via.startswith("i") else "Facebook"
        try:
            botao = pg.get_by_text(f"Continuar com o {rotulo}", exact=False).first
            if await botao.count():
                # A Meta abre o login numa POPUP de OAuth; sem capturar, o clique
                # parece não fazer nada (a página de origem fica igual).
                try:
                    async with ctx.expect_page(timeout=15000) as pop:
                        await botao.click()
                    pg = await pop.value
                    await pg.wait_for_load_state("domcontentloaded")
                    print(f"  popup de login capturada · url={pg.url[:70]}")
                except Exception:  # noqa: BLE001 — sem popup: navegou na própria aba
                    await pg.wait_for_timeout(6000)
                    print(f"  sem popup; url={pg.url[:70]}")
                await pg.wait_for_timeout(4000)
        except Exception as e:  # noqa: BLE001
            print(f"  seletor de entrada: {str(e)[:90]}")

        # Campos variam por caminho (FB: email/pass · IG: username/password).
        campos_user = ('input[name="email"]', 'input#email', 'input[name="username"]',
                       'input[autocomplete="username"]', 'input[type="text"]')
        campos_pass = ('input[name="pass"]', 'input#pass', 'input[name="password"]',
                       'input[type="password"]')
        try:
            for sel in campos_user:
                if await pg.locator(sel).count():
                    await pg.fill(sel, email, timeout=15000)
                    break
            for sel in campos_pass:
                if await pg.locator(sel).count():
                    await pg.fill(sel, senha, timeout=15000)
                    break
            await pg.keyboard.press("Enter")
            await pg.wait_for_timeout(10000)
        except Exception as e:  # noqa: BLE001
            print(f"  falha ao preencher o formulário: {str(e)[:110]}")
        print(f"  {await _diagnostico(pg)}")
        print(f"  screenshot: {await _foto(pg, '01_pos_login')}")
        await ctx.close()
    return 0


async def cmd_login_fb() -> int:
    """Login direto em facebook.com/login.php — sem o seletor do Business.

    Por que existe: o caminho do Business ("Continuar com o Instagram") devolveu
    HTTP 429 e o `/accounts/login/` do Instagram renderiza ZERO inputs. O
    formulário clássico do facebook.com ainda é HTML de verdade.
    """
    email, senha = os.getenv("META_LOGIN_EMAIL", ""), os.getenv("META_LOGIN_PASS", "")
    if not (email and senha):
        print("META_LOGIN_EMAIL / META_LOGIN_PASS não definidas.")
        return 2
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        ctx = await _ctx(pw)
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await pg.goto("https://www.facebook.com/login.php", wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(4000)
        if not await pg.locator('input[name="email"]').count():
            print(f"  formulário não renderizou · {await _foto(pg, '10_sem_form')}")
            print(f"  {(await pg.inner_text('body'))[:300]}")
            await ctx.close()
            return 1
        await pg.fill('input[name="email"]', email)
        await pg.fill('input[name="pass"]', senha)
        await pg.keyboard.press("Enter")
        await pg.wait_for_timeout(12000)
        print(f"  url={pg.url[:110]}")
        print(f"  {await _diagnostico(pg)}")
        print(f"  screenshot: {await _foto(pg, '11_pos_login_fb')}")
        await ctx.close()
    return 0


async def cmd_codigo(codigo: str) -> int:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        ctx = await _ctx(pw)
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await pg.wait_for_timeout(2000)
        alvo = None
        for sel in ('input[name="approvals_code"]', 'input[autocomplete="one-time-code"]',
                    'input[type="text"][maxlength="6"]', 'input[type="tel"]'):
            if await pg.locator(sel).count():
                alvo = sel
                break
        if not alvo:
            print(f"  não achei campo de código nesta tela · {await _foto(pg, '02_sem_campo')}")
            print(f"  {await _diagnostico(pg)}")
            await ctx.close()
            return 1
        await pg.fill(alvo, codigo)
        await pg.keyboard.press("Enter")
        await pg.wait_for_timeout(9000)
        print(f"  {await _diagnostico(pg)}")
        print(f"  screenshot: {await _foto(pg, '02_pos_codigo')}")
        await ctx.close()
    return 0


async def cmd_ver(url: str) -> int:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        ctx = await _ctx(pw)
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(6000)
        nome = "pg_" + "".join(c if c.isalnum() else "_" for c in url)[-40:]
        print(f"  url={pg.url[:100]}")
        print(f"  {(await pg.inner_text('body'))[:500]}")
        print(f"  screenshot: {await _foto(pg, nome)}")
        await ctx.close()
    return 0


async def cmd_estado() -> int:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        ctx = await _ctx(pw)
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await pg.goto("https://business.facebook.com/", wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(4000)
        print(f"  {await _diagnostico(pg)}")
        print(f"  screenshot: {await _foto(pg, '03_estado')}")
        await ctx.close()
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "login":
        return asyncio.run(cmd_login())
    if cmd == "login_fb":
        return asyncio.run(cmd_login_fb())
    if cmd == "codigo":
        return asyncio.run(cmd_codigo(sys.argv[2]))
    if cmd == "ver":
        return asyncio.run(cmd_ver(sys.argv[2]))
    if cmd == "estado":
        return asyncio.run(cmd_estado())
    print(f"comando desconhecido: {cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
