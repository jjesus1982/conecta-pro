/**
 * Clicar numa notificação do SINO registra `clicked_at` — o campo que nunca foi escrito.
 *
 * 🔴 MEDIDO EM 30/09/2026: `clicked_at` estava vazio nas **11.029 notificações** da tabela
 * inteira. A coluna existia desde sempre e ninguém nunca escreveu nela.
 *
 * ⭐ E o custo não foi só a métrica faltando: eu li «zero cliques em 348 notificações» e afirmei
 * ao dono que **ninguém age sobre os alertas**. Era falso — o que havia era campo morto. Tive de
 * retirar a conclusão na frente dele. **Campo que ninguém escreve não é medida de comportamento.**
 *
 * O que este teste prova é o CAMINHO INTEIRO, e não que a rota responde 204: que abrir uma
 * notificação do sino, como uma pessoa faria, chega ao banco.
 *
 * ⚠️ A verificação no banco NÃO cabe aqui (o Playwright não fala com o Postgres). Ele deixa a
 * prova a meio caminho de propósito: imprime o título clicado, e quem roda confere a contagem de
 * `clicked_at` antes e depois. Teste que afirma o que não consegue medir é pior que teste nenhum.
 */
import { test, expect } from '@playwright/test';

test.describe('Sino — registrar o clique', () => {
  test.slow();

  test('abrir uma notificação do sino navega e registra', async ({ page }) => {
    await page.goto(`/redesign/alertas?_cb=${Date.now()}`);
    await page.waitForLoadState('networkidle');

    // ⚠️ `.rd-icon-btn` com `.first()` pega o botão «Recolher menu» da barra lateral, não o
    // sino — sexta vez que a posição me engana neste projeto. O ancoradouro é o NOME.
    const sino = page.getByRole('button', { name: /Notificaç/i }).first();
    await expect(sino).toBeVisible({ timeout: 60_000 });
    await sino.click();

    // O painel do sino põe `role="button"` só nos itens que TÊM destino. Pegamos o primeiro
    // que não seja o próprio sino (que também é button e já está no cabeçalho).
    const item = page.locator('[role="button"]').filter({ hasNotText: /Notificaç/i }).first();
    await expect(item).toBeVisible({ timeout: 30_000 });
    const titulo = (await item.innerText()).split('\n')[0]?.slice(0, 60);
    console.log('CLICANDO NA NOTIFICAÇÃO: ' + titulo);

    await item.click();

    // Navegou para algum lugar REAL — e não para um 404, que era o defeito de origem.
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/redesign\//, { timeout: 30_000 });
    const corpo = (await page.locator('body').innerText()).toUpperCase();
    expect(corpo, 'caiu numa página de erro — o destino da notificação não existe')
      .not.toContain('PÁGINA NÃO ENCONTRADA');
    expect(corpo).not.toContain('404');

    await page.screenshot({ path: 'e2e/.out/sino-clique.png', fullPage: true });
    console.log('DESTINO: ' + page.url());
  });
});
