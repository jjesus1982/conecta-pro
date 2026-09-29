/**
 * Os filtros que a PYETRA pediu no ponto: por colaborador, por período, e os outros.
 *
 * Pedido do Jordan em 29/09/2026: «em /redesign/gestao-de-pessoas?t=ponto a pyetra precisa
 * selecionar o período por data, por funcionário e outros filtros necessários».
 *
 * São DUAS telas de propósito, e o teste cobre as duas porque a divisão é a parte que pode
 * confundir:
 *   · `ponto`          — filtros de VALOR, resolvidos no cliente sobre as 200 batidas carregadas
 *   · `ponto-periodo`  — o PERÍODO, que precisa ir ao servidor (200 linhas não cobrem 4 dias)
 *
 * ⚠️ Armadilhas já pagas e evitadas aqui: a tela vem por `?t=<id>` (URL própria dá 404); `input`
 * genérico pega a caixa «Buscar…» do cabeçalho; e há dois botões com o nome do CTA — por isso
 * tudo é escopado no `<main>` interno.
 */
import { test, expect } from '@playwright/test';

test.describe('Ponto — filtros e período', () => {
  test.slow();

  test('a tela `ponto` oferece os seis filtros', async ({ page }) => {
    await page.goto(`/redesign/gestao-de-pessoas?t=ponto&_cb=${Date.now()}`);
    await page.waitForLoadState('networkidle');
    const main = page.locator('main').last();

    // Um <select> por filtro declarado. Menos que isso é filtro que não chegou à tela.
    await expect(main.locator('select')).toHaveCount(6, { timeout: 60_000 });

    // ⚠️ MAIÚSCULAS: `innerText` devolve o texto RENDERIZADO, e o cabeçalho da grade tem
    // `text-transform: uppercase` — comparar «Colaborador» com «COLABORADOR» reprova uma tela
    // que funciona. Foi assim que este teste acusou a tela do período de não renderizar colunas
    // que estavam lá, em letra grande.
    const texto = (await main.innerText()).toUpperCase();
    for (const rotulo of ['Colaborador', 'Posto', 'Tipo', 'Status', 'No posto', 'Origem']) {
      expect(texto, `o filtro «${rotulo}» não apareceu na tela`).toContain(rotulo.toUpperCase());
    }
    await page.screenshot({ path: 'e2e/.out/ponto-filtros.png', fullPage: true });
  });

  test('`ponto-periodo` consulta o servidor e devolve a tabela do intervalo', async ({ page }) => {
    await page.goto(`/redesign/gestao-de-pessoas?t=ponto-periodo&_cb=${Date.now()}`);
    await page.waitForLoadState('networkidle');
    const main = page.locator('main').last();

    // As duas datas vêm preenchidas (mês corrente até hoje) — ela não começa do zero.
    const datas = main.locator('input[type="date"]');
    await expect(datas).toHaveCount(2, { timeout: 60_000 });
    expect(await datas.nth(0).inputValue()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(await datas.nth(1).inputValue()).toMatch(/^\d{4}-\d{2}-\d{2}$/);

    // Colaborador + posto + tipo + status + no posto = cinco seletores.
    await expect(main.locator('select')).toHaveCount(6); // +1: o «Período rápido»

    // Um intervalo estreito de propósito: o teste não é de carga.
    await datas.nth(0).fill('2026-09-28');
    await datas.nth(1).fill('2026-09-28');
    await main.getByRole('button', { name: /^Buscar$/ }).click();

    // O que prova a entrega: a tabela do PERÍODO, com as colunas e a contagem.
    await expect(main.getByText(/28\/09\/2026 a 28\/09\/2026/)).toBeVisible({ timeout: 120_000 });
    await expect(main.getByText(/batida\(s\) no período/)).toBeVisible();
    // Mesmo cuidado com maiúsculas do teste acima.
    const corpo = (await main.innerText()).toUpperCase();
    for (const col of ['Colaborador', 'Data/hora', 'Tipo', 'No posto', 'Origem', 'Status']) {
      expect(corpo, `a coluna «${col}» não renderizou`).toContain(col.toUpperCase());
    }

    // ⭐ A tabela é LARGA de propósito e ROLA na horizontal — medido: 912 px de conteúdo em
    // 660 px de contêiner, com `overflow-x: auto` no pai. Não é corte, é o comportamento
    // padrão da casa para tabela larga (a tela `ponto` tem sete colunas e faz o mesmo).
    const rola = await page.evaluate(() => {
      const el = document.querySelector('.rd-tbl-inner') as HTMLElement | null;
      const p = el?.parentElement as HTMLElement | undefined;
      return !!p && p.scrollWidth > p.clientWidth && getComputedStyle(p).overflowX === 'auto';
    });
    expect(rola, 'a tabela larga precisa ROLAR, não ser cortada').toBe(true);
    await page.screenshot({ path: 'e2e/.out/ponto-periodo.png', fullPage: true });
    console.log('RESULTADO DO PERÍODO:\n' + corpo.slice(0, 900));
  });

  test('o botão da tela `ponto` leva ao período, e o atalho «Este mês» funciona', async ({ page }) => {
    // 🔴 O Jordan testou e perguntou: «selecionei um funcionário, quero selecionar o período, o
    // mês, o dia — a data ainda não consigo puxar, por quê?». A explicação técnica estava certa
    // e não adiantou: ele procurou a data onde estavam os outros filtros. Este teste trava o
    // CAMINHO, não a explicação.
    await page.goto(`/redesign/gestao-de-pessoas?t=ponto&_cb=${Date.now()}`);
    await page.waitForLoadState('networkidle');

    // ⚠️ O CTA mora no CABEÇALHO, fora do <main> interno — por isso aqui o escopo é a página.
    const botao = page.getByRole('button', { name: /Buscar por data \/ período/i });
    await expect(botao).toBeVisible({ timeout: 60_000 });
    await botao.click();

    const main = page.locator('main').last();
    await expect(main.getByText(/Ponto por período/i).first()).toBeVisible({ timeout: 60_000 });

    // ⚠️ Escolher o select pela POSIÇÃO falhou («did not find some options»): a ordem
    // renderizada não é a de declaração. O ancoradouro certo é o próprio conteúdo — o único
    // select que tem a opção `mes` é o do atalho.
    const rapido = main.locator('select').filter({ has: page.locator('option[value="mes"]') });
    await rapido.selectOption('mes');
    await main.getByRole('button', { name: /^Buscar$/ }).click();

    await expect(main.getByText(/batida\(s\) no período/)).toBeVisible({ timeout: 120_000 });
    const msg = await main.innerText();
    expect(msg, 'o atalho «Este mês» tem de abrir no dia 1').toMatch(/01\/\d{2}\/\d{4} a /);
    await page.screenshot({ path: 'e2e/.out/ponto-periodo-mes.png', fullPage: true });
  });
});
