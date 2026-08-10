#!/usr/bin/env python3
"""Importa a sessão da Meta a partir de COOKIES exportados do navegador do Jordan.

Por que este caminho existe: login automatizado no Instagram a partir deste
servidor recebe HTTP 429 (IP limitado) e a mensagem de erro é IDÊNTICA para
senha certa e errada — ou seja, a Meta recusa avaliar, não recusa a senha.
Insistir só aumenta o risco de travar a conta.

Cookie de sessão pula tudo: já foi validado no navegador dele (com 2FA, com
checkpoint, com IP residencial). Aqui ele só é reutilizado.

COMO EXPORTAR (no navegador onde você já está logado):
  F12 → Application → Cookies → https://business.facebook.com
  Copie os valores de `c_user` e `xs` (são esses dois que sustentam a sessão).

USO:
  C_USER=... XS=... python3 scripts/meta_cookies.py importar
  python3 scripts/meta_cookies.py verificar
"""
import asyncio
import os
import pathlib
import sys

PERFIL = "/opt/conecta-pro/det-robot/state/meta_profile"
SH = pathlib.Path("/opt/conecta-pro/det-robot/state/meta")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _ctx(pw):
    return pw.chromium.launch_persistent_context(
        PERFIL, headless=True, ignore_default_args=["--enable-automation"],
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        user_agent=UA, locale="pt-BR", timezone_id="America/Manaus",
        viewport={"width": 1440, "height": 900})


async def importar():
    c_user, xs = os.getenv("C_USER", "").strip(), os.getenv("XS", "").strip()
    if not (c_user and xs):
        print("C_USER e XS não definidos — veja o cabeçalho do arquivo.")
        return 2
    from playwright.async_api import async_playwright
    biscoitos = [
        {"name": n, "value": v, "domain": d, "path": "/", "httpOnly": True, "secure": True}
        for n, v in (("c_user", c_user), ("xs", xs))
        for d in (".facebook.com", ".instagram.com")
    ]
    async with async_playwright() as pw:
        ctx = await _ctx(pw)
        await ctx.add_cookies(biscoitos)
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await pg.goto("https://business.facebook.com/", wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(7000)
        SH.mkdir(parents=True, exist_ok=True)
        await pg.screenshot(path=str(SH / "cookie_importado.png"), full_page=True)
        logado = "login" not in pg.url
        print(f"  {'SESSÃO ATIVA' if logado else 'ainda deslogado'} · url={pg.url[:80]}")
        print(f"  shot: {SH / 'cookie_importado.png'}")
        await ctx.close()
    return 0 if logado else 1


async def verificar():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        ctx = await _ctx(pw)
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await pg.goto("https://business.facebook.com/", wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(6000)
        SH.mkdir(parents=True, exist_ok=True)
        await pg.screenshot(path=str(SH / "cookie_verifica.png"), full_page=True)
        print(f"  url={pg.url[:90]}  logado={'login' not in pg.url}")
        await ctx.close()
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verificar"
    sys.exit(asyncio.run(importar() if cmd == "importar" else verificar()))
