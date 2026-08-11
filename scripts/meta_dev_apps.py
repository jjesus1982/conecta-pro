#!/usr/bin/env python3
"""Reconhecimento em developers.facebook.com — o que já existe antes de criar nada.

Por que existe: o `Conversions API Application` (991735013894149) NÃO pode ser
reivindicado — a Meta responde "ID inválido: só é possível solicitar acesso a um
app de outra empresa ou de sua propriedade". Ele é interno, provisionado pela
própria Meta no fluxo do CAPI. Logo, o token de Ads exige um app PRÓPRIO.

Antes de brigar com a verificação por SMS (que nunca chega), este script só OLHA:
já existe algum app na conta de desenvolvedor? Se existir, o caminho é reusar.

  C_USER=... XS=... DATR=... SB=... python3 scripts/meta_dev_apps.py
"""

import asyncio
import os
import pathlib
import sys

SH = pathlib.Path("/opt/conecta-pro/det-robot/state/meta")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


async def main() -> int:
    ck = {k: os.getenv(k, "").strip() for k in ("C_USER", "XS", "DATR", "SB")}
    if not (ck["C_USER"] and ck["XS"]):
        print("C_USER e XS obrigatórios.")
        return 2
    from playwright.async_api import async_playwright

    SH.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        nav = await pw.chromium.launch(
            headless=True,
            ignore_default_args=["--enable-automation"],
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
        )
        ctx = await nav.new_context(user_agent=UA, locale="pt-BR",
                                    timezone_id="America/Manaus",
                                    viewport={"width": 1600, "height": 1000})
        # developers.facebook.com é outro domínio: o cookie precisa valer para
        # .facebook.com inteiro, senão a sessão não atravessa.
        await ctx.add_cookies([
            {"name": n.lower(), "value": v, "domain": ".facebook.com", "path": "/", "secure": True}
            for n, v in ck.items() if v
        ])
        pg = await ctx.new_page()

        # Aquecer a sessão no facebook.com antes de saltar de subdomínio: indo
        # direto para developers.facebook.com/apps/ a Meta redireciona para a home
        # deslogada (topo mostra "Começar", não o avatar).
        await pg.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(6000)
        await pg.screenshot(path=str(SH / "dev_00_aquecimento.png"), full_page=False)
        print(f"aquecimento · url={pg.url[:90]}")

        for nome, url in (("apps", "https://developers.facebook.com/apps/"),
                          ("dev_home", "https://developers.facebook.com/")):
            await pg.goto(url, wait_until="domcontentloaded", timeout=60000)
            await pg.wait_for_timeout(7000)
            await pg.screenshot(path=str(SH / f"dev_{nome}.png"), full_page=True)
            corpo = (await pg.inner_text("body"))[:900]
            print(f"\n=== {nome} · url={pg.url[:90]}")
            print(corpo)

        await ctx.close()
        await nav.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
