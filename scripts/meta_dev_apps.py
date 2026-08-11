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
    ck = {k: os.getenv(k, "").strip() for k in ("C_USER", "XS", "DATR", "SB", "FR")}
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

        if "telefone" in sys.argv:
            # Sem número no argumento: só abre o diálogo e fotografa (não dispara
            # SMS nenhum). Com número: troca e manda reenviar.
            i = sys.argv.index("telefone")
            novo = sys.argv[i + 1] if len(sys.argv) > i + 1 else ""
            await pg.goto("https://developers.facebook.com/", wait_until="domcontentloaded", timeout=60000)
            await pg.wait_for_timeout(6000)
            await pg.get_by_text("Começar", exact=False).first.click(timeout=15000)
            await pg.wait_for_timeout(7000)
            await pg.get_by_role("button", name="Atualizar número de celular").first.click(timeout=15000)
            await pg.wait_for_timeout(5000)
            await pg.screenshot(path=str(SH / "dev_tel_0_dialogo.png"), full_page=True)
            print(f"\n--- diálogo de telefone · url={pg.url[:90]}\n{(await pg.inner_text('body'))[:700]}")
            if novo:
                # Ancorar no PLACEHOLDER: `input[type=text]` solto pega o campo do
                # CÓDIGO que fica atrás do diálogo (vem antes no DOM), e o telefone
                # continua vazio — o SMS nunca troca de número.
                campo = pg.get_by_placeholder("Insira seu telefone").first
                await campo.fill(novo, timeout=15000)
                await pg.wait_for_timeout(1500)
                await pg.screenshot(path=str(SH / "dev_tel_1_preenchido.png"), full_page=True)
                # O botão fica cinza durante o cooldown de reenvio ("Aguarde 19
                # segundos"). Clicar na hora não faz nada — tem que esperar liberar.
                enviar = pg.get_by_role("button", name="Enviar SMS para verificação")
                for _ in range(24):  # até ~60s
                    if await enviar.first.is_enabled():
                        break
                    await pg.wait_for_timeout(2500)
                if await enviar.first.is_enabled():
                    await enviar.first.click(timeout=12000)
                    await pg.wait_for_timeout(8000)
                else:
                    print("   botão 'Enviar SMS' seguiu desabilitado após 60s")
                await pg.screenshot(path=str(SH / "dev_tel_2_enviado.png"), full_page=True)
                print(f"\n--- pós-envio\n{(await pg.inner_text('body'))[:700]}")
            await ctx.close()
            await nav.close()
            return 0

        if "codigo" in sys.argv:
            # Reabre o diálogo de cadastro (ele retoma no passo pendente, sem
            # reenviar SMS) e entrega o código de 6 dígitos.
            codigo = sys.argv[sys.argv.index("codigo") + 1]
            await pg.goto("https://developers.facebook.com/", wait_until="domcontentloaded", timeout=60000)
            await pg.wait_for_timeout(6000)
            await pg.get_by_text("Começar", exact=False).first.click(timeout=15000)
            await pg.wait_for_timeout(7000)
            await pg.screenshot(path=str(SH / "dev_cod_0_antes.png"), full_page=True)
            campo = pg.locator('input[type="text"], input[type="tel"]').first
            await campo.fill(codigo, timeout=15000)
            await pg.wait_for_timeout(1500)
            await pg.screenshot(path=str(SH / "dev_cod_1_preenchido.png"), full_page=True)
            for i in range(1, 7):
                avancou = False
                for rot in ("Continuar", "Avançar", "Concluir", "Enviar"):
                    alvo = pg.get_by_role("button", name=rot, exact=False)
                    # aria-disabled fica ativo enquanto o campo não valida — não
                    # adianta clicar num botão cinza, só estoura timeout.
                    if await alvo.count() and await alvo.first.is_enabled():
                        await alvo.first.click(timeout=12000)
                        await pg.wait_for_timeout(7000)
                        avancou = True
                        break
                await pg.screenshot(path=str(SH / f"dev_cod_{i + 1}.png"), full_page=True)
                print(f"\n--- pós-código {i} · url={pg.url[:90]}\n{(await pg.inner_text('body'))[:700]}")
                if not avancou:
                    print("   (nenhum botão habilitado — parei aqui)")
                    break
            await ctx.close()
            await nav.close()
            return 0

        if "registrar" in sys.argv:
            # /apps/ redirecionar para a home de marketing COM o facebook.com logado
            # não é sessão morta: é conta sem cadastro de desenvolvedor. O "Começar"
            # abre esse cadastro. Avanço passo a passo, fotografando, e paro onde
            # pedir algo que só o Jordan pode dar (SMS, aceite).
            await pg.goto("https://developers.facebook.com/", wait_until="domcontentloaded", timeout=60000)
            await pg.wait_for_timeout(6000)
            await pg.get_by_text("Começar", exact=False).first.click(timeout=15000)
            await pg.wait_for_timeout(6000)
            for i in range(1, 7):
                await pg.screenshot(path=str(SH / f"dev_reg_{i}.png"), full_page=True)
                corpo = (await pg.inner_text("body"))[:700]
                print(f"\n--- passo {i} · url={pg.url[:90]}\n{corpo}")
                avancou = False
                for rot in ("Avançar", "Continuar", "Próxima", "Próximo", "Concluir"):
                    alvo = pg.get_by_role("button", name=rot, exact=False)
                    if await alvo.count():
                        await alvo.first.click(timeout=12000)
                        await pg.wait_for_timeout(6000)
                        avancou = True
                        break
                if not avancou:
                    print("   (sem botão de avançar — fim do caminho automático)")
                    break
            await ctx.close()
            await nav.close()
            return 0

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
