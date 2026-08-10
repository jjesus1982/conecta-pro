#!/usr/bin/env python3
"""QA E2E no NAVEGADOR — prova visual do que foi entregue nesta frente.

Playwright de verdade (chromium headless), login real, navegação real. Não é
curl com HTML: renderiza React, espera hidratação e lê o que o humano veria.

O que cobre, e por quê:
  1. login              — sem isso nada abaixo vale
  2. CRM / funil        — Anderson e Juan Torres viraram oportunidade (Task 6/backfill)
  3. sino               — alerta "conversas esfriaram" chegou (Task 5, watchdog fora do Telegram)
  4. precificação       — a tabela mostra os preços corrigidos (ronda 15%, intrajornada)

Screenshots em /tmp/qa_e2e/*.png — prova, não afirmação.

  docker exec -e PYTHONPATH=/app -w /app conecta-pro-backend python3 scripts/qa_e2e_navegador.py
  (ou no host: python3 backend/scripts/qa_e2e_navegador.py)
"""

import asyncio
import os
import pathlib
import sys

BASE = os.getenv("QA_BASE_URL", "http://127.0.0.1:3001")
USER = os.getenv("QA_USER", "jjesus@conectamais.pro")
PWD = os.getenv("QA_PASS", "")
SHOTS = pathlib.Path(os.getenv("QA_SHOTS", "/tmp/qa_e2e"))


async def main() -> int:
    from playwright.async_api import async_playwright

    if not PWD:
        print("QA_PASS não definida — abortando (não vou adivinhar credencial).")
        return 2
    SHOTS.mkdir(parents=True, exist_ok=True)
    falhas: list[str] = []

    async with async_playwright() as pw:
        nav = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = await nav.new_context(viewport={"width": 1440, "height": 900}, locale="pt-BR")
        pg = await ctx.new_page()
        erros_js: list[str] = []
        pg.on("pageerror", lambda e: erros_js.append(str(e)[:160]))

        async def tiro(nome: str) -> str:
            caminho = SHOTS / f"{nome}.png"
            await pg.screenshot(path=str(caminho), full_page=True)
            return str(caminho)

        # ── 1. LOGIN ─────────────────────────────────────────────────────────
        print("1) login")
        await pg.goto(f"{BASE}/login", wait_until="domcontentloaded", timeout=60000)
        # React hidrata depois do DOM: espera o campo existir, não a rede silenciar.
        await pg.wait_for_selector('input[type="email"], input[name="email"], input#email', timeout=45000)
        await pg.fill('input[type="email"], input[name="email"], input#email', USER)
        await pg.fill('input[type="password"], input[name="password"], input#password', PWD)
        await pg.click('button[type="submit"]')
        try:
            await pg.wait_for_url(lambda u: "/login" not in u, timeout=45000)
        except Exception:
            falhas.append("login: não saiu de /login")
        await pg.wait_for_timeout(2500)
        print(f"   url={pg.url}  shot={await tiro('01_login')}")

        # ── 2. CRM: dashboard + os dois leads recuperados ────────────────────
        # O /redesign/crm abre num DASHBOARD; os nomes vivem nas sub-abas do menu
        # lateral. Clicar no menu é o caminho do humano — e testa o roteador junto.
        print("2) CRM / dashboard")
        await pg.goto(f"{BASE}/redesign/crm", wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(4500)
        dash = await pg.inner_text("body")
        if "Qualified" not in dash:
            falhas.append("CRM dashboard: não mostra 'Leads por status'")
        print(f"   dashboard ok  shot={await tiro('02_crm_dashboard')}")

        async def abrir_aba(rotulo: str, nome_shot: str) -> str:
            alvo = pg.locator(f'nav >> text="{rotulo}"').first
            if not await alvo.count():
                alvo = pg.get_by_text(rotulo, exact=True).first
            await alvo.click()
            await pg.wait_for_timeout(4500)
            await tiro(nome_shot)
            return await pg.inner_text("body")

        print("2b) CRM / oportunidades")
        try:
            corpo = (await abrir_aba("Oportunidades", "02b_oportunidades")).lower()
        except Exception as e:  # noqa: BLE001
            falhas.append(f"CRM: não abriu Oportunidades ({str(e)[:60]})")
            corpo = ""
        for quem in ("anderson", "juan"):
            if quem not in corpo:
                falhas.append(f"Oportunidades: '{quem}' não aparece")
        print(f"   Anderson={'anderson' in corpo}  Juan={'juan' in corpo}")

        # ── 3. SINO: o alerta do watchdog ────────────────────────────────────
        print("3) sino / notificações")
        alvo = None
        for sel in ('[data-testid="sino"]', 'button[aria-label*="otific"]', 'button:has(svg[class*="bell"])',
                    'header button:has(svg)'):
            if await pg.locator(sel).count():
                alvo = sel
                break
        if alvo:
            try:
                await pg.locator(alvo).first.click()
                await pg.wait_for_timeout(2500)
            except Exception as e:  # noqa: BLE001
                falhas.append(f"sino: clique falhou ({str(e)[:60]})")
        corpo_sino = (await pg.inner_text("body")).lower()
        tem_alerta = "esfriaram" in corpo_sino or "esfriou" in corpo_sino
        if not tem_alerta:
            falhas.append("sino: alerta 'conversas esfriaram' não visível na UI")
        print(f"   seletor={alvo}  alerta_visivel={tem_alerta}  shot={await tiro('03_sino')}")

        # ── 4. PRECIFICAÇÃO: os preços corrigidos ────────────────────────────
        # Fica no menu do CRM (não no financeiro) e usa o MESMO calcular_funcao do
        # agente — é a prova de que a correção de parâmetros chegou na tela.
        print("4) precificação")
        await pg.goto(f"{BASE}/redesign/crm", wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(3000)
        try:
            txt = await abrir_aba("Precificação", "04_precificacao")
        except Exception as e:  # noqa: BLE001
            falhas.append(f"precificação: não abriu a aba ({str(e)[:60]})")
            txt = ""
        plano = txt.replace(".", "").replace(",", "")
        # AGP Rondante Noturno 7.481,27 e AGP P1 Diurno 5.590,22 (com intrajornada)
        achou = [v for v in ("748127", "559022", "688278", "618871") if v in plano]
        if not achou:
            falhas.append("precificação: nenhum dos preços novos apareceu na tela")
        print(f"   precos_novos_na_tela={achou}")

        if erros_js:
            falhas.append(f"erros de JS no console: {erros_js[:3]}")
        await ctx.close()
        await nav.close()

    print("\n" + "=" * 70)
    if falhas:
        print("QA E2E FALHOU:")
        for f in falhas:
            print("  -", f)
        print(f"\nscreenshots em {SHOTS}")
        return 1
    print(f"QA E2E OK — 4 telas provadas no navegador. screenshots em {SHOTS}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
