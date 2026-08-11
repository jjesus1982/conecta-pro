#!/usr/bin/env python3
"""Atribui o app ao usuário do sistema CPROSYNC e gera o token de ads — TUDO numa sessão.

Por que numa sessão só: em 2026-08-10 o cookie da sessão do Jordan funcionou por
exatamente UMA carga de página; entre uma execução e outra a Meta invalidava (ela
amarra a sessão ao IP). Abrir um navegador por comando garantia a morte. Aqui o
navegador abre uma vez e faz o caminho inteiro antes que dê tempo de cair.

Fluxo, com screenshot em cada etapa (state/meta/passo_*.png):
  1. importa cookies    2. abre Usuários do sistema    3. seleciona CPROSYNC
  4. Adicionar ativos → Apps → Conversions API Application → salvar
  5. Gerar token → ads_read + business_management → captura o token

Cookies via env (nunca em argumento — ficariam no `ps` e no histórico):
  C_USER, XS, DATR, SB   →  o DATR é o cookie de dispositivo confiável; sem ele
  a Meta dispara checkpoint mesmo com sessão válida.

  C_USER=... XS=... DATR=... SB=... python3 scripts/meta_gerar_token_ads.py
"""

import asyncio
import os
import pathlib
import sys

BID = "959107583761655"
SYS_USER = "CPROSYNC"
APP = "Conversions API Application"
APP_ID = "991735013894149"
CONTA = "Conecta Mais - Anúncios"
SH = pathlib.Path("/opt/conecta-pro/det-robot/state/meta")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


async def main() -> int:
    ck = {k: os.getenv(k, "").strip() for k in ("C_USER", "XS", "DATR", "SB")}
    if not (ck["C_USER"] and ck["XS"]):
        print("C_USER e XS obrigatórios (DATR e SB ajudam a evitar checkpoint).")
        return 2
    from playwright.async_api import async_playwright

    SH.mkdir(parents=True, exist_ok=True)
    passo = [0]

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
        await ctx.add_cookies([
            {"name": n.lower(), "value": v, "domain": ".facebook.com", "path": "/", "secure": True}
            for n, v in ck.items() if v
        ])
        pg = await ctx.new_page()

        async def foto(nome: str) -> None:
            passo[0] += 1
            await pg.screenshot(path=str(SH / f"passo_{passo[0]}_{nome}.png"), full_page=True)
            print(f"    [shot] passo_{passo[0]}_{nome}.png")

        async def clicar(texto: str, timeout: int = 12000) -> bool:
            """Clica no primeiro elemento visível com esse texto. Devolve se conseguiu."""
            for loc in (pg.get_by_role("button", name=texto, exact=False),
                        pg.get_by_text(texto, exact=False)):
                try:
                    if await loc.count():
                        await loc.first.click(timeout=timeout)
                        await pg.wait_for_timeout(3500)
                        return True
                except Exception:  # noqa: BLE001
                    continue
            return False

        # 1 ─ entrar direto na tela dos usuários do sistema
        print("1) abrindo Usuários do sistema")
        await pg.goto(f"https://business.facebook.com/latest/settings/system_users?business_id={BID}",
                      wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(8000)
        if "login" in pg.url.lower():
            await foto("deslogado")
            print("   SESSÃO RECUSADA — cookies mortos ou IP bloqueado. Pegue cookies novos.")
            await ctx.close()
            await nav.close()
            return 1
        await foto("system_users")

        # 2 ─ selecionar o CPROSYNC
        print(f"2) selecionando {SYS_USER}")
        if not await clicar(SYS_USER):
            print(f"   não achei {SYS_USER} na lista")
        await foto("cprosync")

        # DESCARTADOS, com prova em screenshot — não refazer:
        #  · botão azul "Adicionar" do topo → cria USUÁRIO DO SISTEMA novo, não ativo;
        #  · "···" achado por aria-label → é o menu de PERFIL (com "Sair"), quase deslogou;
        #  · "··· → Atribuir ativos" → só oferece Contas de anúncios, Pixels, Conj. de
        #    eventos offline e Conj. de dados. NÃO existe "Apps" ali. Caminho morto.

        # 3 ─ CAUSA RAIZ: a página Apps do portfólio está VAZIA ("Nenhum aplicativo
        # adicionado"). O Conversions API Application existe, mas nasceu preso ao
        # fluxo do Events Manager, FORA do portfólio — e é exatamente isso que o
        # tooltip do botão cinza dizia: "um app deve fazer parte desse portfólio".
        # Não precisa criar app novo (nem o SMS que nunca chega): basta CONECTAR
        # o ID do app que já existe.
        print(f"3b) Apps → Conectar ID do app {APP_ID}")
        await pg.goto(f"https://business.facebook.com/latest/settings/apps?business_id={BID}",
                      wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(7000)
        await foto("lista_apps")
        await clicar("Adicionar")
        await foto("menu_adicionar_app")
        for rot in ("Conectar um ID do app", "Conectar um ID do aplicativo", "Conectar"):
            if await clicar(rot):
                break
        await foto("campo_id_app")
        # Escopar no DIÁLOGO: `input[type=text]` solto pegou a caixa de BUSCA do
        # topo da página e o campo "ID do aplicativo" ficou vazio.
        campo = pg.locator('div[role="dialog"] input').first
        await campo.fill(APP_ID, timeout=10000)
        await pg.wait_for_timeout(1200)
        await foto("id_preenchido")
        for rot in ("Adicionar app", "Adicionar aplicativo", "Conectar", "Adicionar"):
            if await clicar(rot):
                break
        await foto("app_conectado")

        # 3c ─ voltar para o usuário do sistema
        await pg.goto(f"https://business.facebook.com/latest/settings/system_users?business_id={BID}",
                      wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(7000)
        await clicar(SYS_USER)
        await foto("de_volta_no_usuario")

        # 4 ─ Gerar token
        print("4) Gerar token")
        await clicar("Gerar token") or await clicar("Gerar novo token")
        await pg.wait_for_timeout(3500)
        await foto("dialogo_token")
        await clicar(APP)
        for perm in ("ads_read", "business_management"):
            await clicar(perm)
        await foto("permissoes")
        await clicar("Gerar token")
        await pg.wait_for_timeout(6000)
        await foto("token")

        # 5 ─ tenta capturar o token da tela
        corpo = await pg.inner_text("body")
        import re
        m = re.search(r"\bEAA[A-Za-z0-9]{80,}", corpo)
        print(f"\n   TOKEN: {m.group(0) if m else 'não apareceu no texto — veja passo_*_token.png'}")
        await ctx.close()
        await nav.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
