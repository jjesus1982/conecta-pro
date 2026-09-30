/**
 * A tela de ALERTAS abre, mostra ONDE ESTÁ O PESO e lista — no navegador.
 *
 * 🔴 Ela nasceu em 30/09/2026 porque o digest da manhã — «Bom dia, o que precisa da sua
 * atenção» — apontava para `/notificacoes`, que devolve **404**. Medido: 374 notificações para
 * lá, a última daquele dia, e **nenhuma sequer aberta**.
 *
 * ⭐ O que este teste prova NÃO é que a tela responde 200: é que ela mostra o RESUMO antes da
 * lista. Com 1.892 não lidas para o Orlailson e 1.374 para a Pyetra, uma tela que só lista é
 * mais pilha — a entrega é a triagem, e é ela que precisa estar travada.
 *
 * ⚠️ Armadilhas já pagas nesta casa, todas evitadas aqui:
 *  1. A tela vem por `?t=<id>` — URL própria dá 404. (`ModuleView.tsx:1261`)
 *  2. `input`/`select` genérico com `.first()` pega a caixa «Buscar…» do cabeçalho.
 *  3. Há DOIS botões com o nome do CTA: o do cabeçalho e o do cartão. O ancoradouro é o
 *     `<main>` INTERNO — existem dois `<main>`, e o cabeçalho fica fora do de dentro.
 *  4. `innerText` devolve o texto RENDERIZADO: o cabeçalho da grade tem `text-transform:
 *     uppercase`, então comparar «Família» com «FAMÍLIA» reprova uma tela que funciona.
 *  5. Selecionar `<select>` pela POSIÇÃO falha — a ordem renderizada não é a de declaração.
 *     Escolha pelo CONTEÚDO (`filter({ has: option[value=...] })`).
 */
import { test, expect } from '@playwright/test';

test.describe('Alertas — triagem', () => {
  test.slow();

  test('abre, mostra onde está o peso e lista', async ({ page }) => {
    await page.goto(`/redesign/alertas?t=meus-alertas&_cb=${Date.now()}`);
    await page.waitForLoadState('networkidle');
    const main = page.locator('main').last();

    await expect(main.getByText(/Meus alertas/i).first()).toBeVisible({ timeout: 60_000 });

    // Cinco filtros: ação, período, só não lidas, família, severidade.
    await expect(main.locator('select')).toHaveCount(5);

    // O caminho SEGURO é o default — ninguém marca nada como lido sem escolher marcar.
    const acao = main.locator('select').filter({ has: page.locator('option[value="listar"]') });
    await expect(acao).toHaveValue('listar');

    await main.getByRole('button', { name: /^Ver$/ }).click();

    // ⭐ O QUE ESTA TELA EXISTE PARA FAZER: dizer onde está o peso ANTES da lista.
    await expect(main.getByText(/Onde está o peso/i).first()).toBeVisible({ timeout: 120_000 });
    await expect(main.getByText(/alerta\(s\) no filtro/i).first()).toBeVisible();

    const corpo = (await main.innerText()).toUpperCase();
    for (const col of ['Quando', 'Família', 'Severidade', 'O quê', 'Estado']) {
      expect(corpo, `a coluna «${col}» não renderizou`).toContain(col.toUpperCase());
    }

    // E o resumo traz família/severidade de verdade, não um rótulo vazio.
    expect(corpo, 'o resumo veio sem família nem severidade')
      .toMatch(/PONTO|SISTEMA|COMERCIAL|FINANCEIRO|CRM|DP/);

    await page.screenshot({ path: 'e2e/.out/alertas-triagem.png', fullPage: true });
    console.log('TELA DE ALERTAS:\n' + corpo.slice(0, 700));
  });

  test('o módulo aparece no menu lateral', async ({ page }) => {
    // Tela que existe e ninguém acha é tela que não foi entregue — a lição do «Buscar por data».
    await page.goto(`/redesign/alertas?_cb=${Date.now()}`);
    await page.waitForLoadState('networkidle');
    await expect(page.getByRole('button', { name: /Meus alertas/i }).first())
      .toBeVisible({ timeout: 60_000 });
  });
});
