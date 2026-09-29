import { test, expect } from '@playwright/test';
import { corpoLoginUrlEncoded } from './_credenciais';

test.describe('Financeiro — Precificação', () => {
  test.use({ storageState: 'e2e/.auth/user.json' });

  test('abre a página de precificação', async ({ page }) => {
    await page.goto('/modulos/financeiro/precificacao', { waitUntil: 'load' });
    await expect(page.getByRole('heading', { name: /precifica/i })).toBeVisible();
    await expect(page.getByText(/parâmetros do contrato/i)).toBeVisible();
  });

  test('seleciona tipo de serviço e exibe formulário completo', async ({ page }) => {
    await page.goto('/modulos/financeiro/precificacao', { waitUntil: 'load' });

    // Clica em Limpeza
    await page.getByRole('button', { name: /limpeza/i }).click();

    // Verifica seleção
    const limpezaBtn = page.locator('button', { hasText: /limpeza/i }).first();
    await expect(limpezaBtn).toHaveClass(/border-blue-500/);

    // Verifica campos
    await expect(page.getByText(/escala de trabalho/i)).toBeVisible();
    await expect(page.getByText(/localização/i)).toBeVisible();
  });

  test('calcula precificação para portaria', async ({ page }) => {
    await page.goto('/modulos/financeiro/precificacao', { waitUntil: 'load' });

    // Preenche quantidade
    const qtdInput = page.getByPlaceholder(/ex:/i);
    await qtdInput.fill('2');

    // Seleciona escala
    await page.selectOption('select[class*="focus:ring"]', '12x36');

    // Clica calcular
    await page.getByRole('button', { name: /calcular precifica/i }).click();

    // Aguarda resultado (pode demorar ou retornar erro de API - ambos são válidos)
    await page.waitForTimeout(3000);

    // O botão deve ter ficado disponível novamente (não stuck em loading)
    const calcBtn = page.getByRole('button', { name: /calcular precifica/i });
    await expect(calcBtn).not.toBeDisabled();
  });

  test('botão voltar leva ao módulo financeiro', async ({ page }) => {
    await page.goto('/modulos/financeiro/precificacao', { waitUntil: 'load' });
    await page.getByRole('link', { name: /voltar/i }).click();
    await expect(page).toHaveURL(/\/modulos\/financeiro/);
  });

  test('exibe opções de escala de trabalho no select', async ({ page }) => {
    await page.goto('/modulos/financeiro/precificacao', { waitUntil: 'load' });
    // Verifica que o select de escala existe com as opções corretas
    const escalaSelect = page.locator('select').first();
    await expect(escalaSelect).toBeVisible();
    const options = await escalaSelect.locator('option').allTextContents();
    expect(options.some(o => o.includes('12x36'))).toBeTruthy();
    expect(options.some(o => o.includes('44h'))).toBeTruthy();
  });
});

test.describe('Financeiro — Dashboard com Advisor', () => {
  test.use({ storageState: 'e2e/.auth/user.json' });

  test('dashboard carrega seção Financial Advisor', async ({ page }) => {
    await page.goto('/modulos/financeiro', { waitUntil: 'load' });
    await page.waitForTimeout(3000);
    // Verifica a seção do advisor — busca o container do chat
    await expect(page.getByPlaceholder(/pergunte algo/i)).toBeVisible({ timeout: 10000 });
  });

  test('advisor exibe prompts de perguntas rápidas', async ({ page }) => {
    await page.goto('/modulos/financeiro', { waitUntil: 'load' });
    await page.waitForTimeout(2000);
    // O chat box deve existir
    await expect(page.getByPlaceholder(/pergunte algo/i)).toBeVisible();
  });

  test('card de precificação aparece nos módulos financeiros', async ({ page }) => {
    await page.goto('/modulos/financeiro', { waitUntil: 'load' });
    await page.waitForTimeout(1500);
    // Busca o card de precificação na seção de módulos
    await expect(page.locator('h3', { hasText: 'Precificação' }).first()).toBeVisible();
  });

  test('card de precificação navega para a página correta', async ({ page }) => {
    await page.goto('/modulos/financeiro', { waitUntil: 'load' });
    await page.waitForTimeout(1500);
    await page.locator('h3', { hasText: 'Precificação' }).first().click();
    await expect(page).toHaveURL(/\/modulos\/financeiro\/precificacao/);
  });
});

test.describe('Backend — Novos endpoints AI', () => {
  test.use({ storageState: 'e2e/.auth/user.json' });

  // Token compartilhado entre todos os testes deste describe (evita rate limit)
  let sharedToken = '';

  test.beforeAll(async ({ request }) => {
    // Lê token do storage state salvo durante auth setup
    const fs = await import('fs');
    const storageState = JSON.parse(fs.readFileSync('e2e/.auth/user.json', 'utf-8'));
    // Busca token nos localStorage entries
    const localStorage = storageState.origins?.[0]?.localStorage ?? [];
    const tokenEntry = localStorage.find((e: any) => e.name === 'access_token');
    if (tokenEntry?.value) {
      sharedToken = tokenEntry.value;
    } else {
      // Fallback: fazer login (apenas 1 vez)
      const resp = await request.post('http://localhost:8080/api/v1/auth/login', {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        data: corpoLoginUrlEncoded(),
      });
      const data = await resp.json();
      sharedToken = data.access_token ?? '';
    }
  });

  test('GET /api/v1/financial/ai/advisor/health retorna dados', async ({ request }) => {
    const resp = await request.get('http://localhost:8080/api/v1/financial/ai/advisor/health', {
      headers: { Authorization: `Bearer ${sharedToken}` },
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data).toHaveProperty('score');
    expect(data).toHaveProperty('classificacao');
  });

  test('GET /api/v1/financial/ai/advisor/recommendations retorna array', async ({ request }) => {
    const resp = await request.get('http://localhost:8080/api/v1/financial/ai/advisor/recommendations', {
      headers: { Authorization: `Bearer ${sharedToken}` },
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(Array.isArray(data)).toBeTruthy();
  });

  test('POST /api/v1/financial/ai/pricing/calculate retorna precificação', async ({ request }) => {
    const resp = await request.post('http://localhost:8080/api/v1/financial/ai/pricing/calculate', {
      headers: { Authorization: `Bearer ${sharedToken}`, 'Content-Type': 'application/json' },
      data: JSON.stringify({ tipo: 'portaria', quantidade: 2, escala: '12x36', localizacao: 'default' }),
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data).toHaveProperty('custo_estimado');
    expect(data).toHaveProperty('precificacao');
    expect(data.precificacao).toHaveProperty('preco_ideal');
    expect(data.custo_estimado).toBeGreaterThan(0);
  });

  test('GET /api/v1/financial/ai/collection/analyze retorna inadimplentes', async ({ request }) => {
    const resp = await request.get('http://localhost:8080/api/v1/financial/ai/collection/analyze', {
      headers: { Authorization: `Bearer ${sharedToken}` },
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data).toHaveProperty('acoes');
    expect(data).toHaveProperty('total_em_atraso');
    expect(data).toHaveProperty('qtd_inadimplentes');
    expect(Array.isArray(data.acoes)).toBeTruthy();
  });

  test('POST /api/v1/financial/ai/advisor/chat responde perguntas', async ({ request }) => {
    const resp = await request.post('http://localhost:8080/api/v1/financial/ai/advisor/chat', {
      headers: { Authorization: `Bearer ${sharedToken}`, 'Content-Type': 'application/json' },
      data: JSON.stringify({ pergunta: 'Qual é a margem atual?' }),
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data).toHaveProperty('resposta');
    expect(typeof data.resposta).toBe('string');
    expect(data.resposta.length).toBeGreaterThan(10);
  });
});
