import { test, expect } from '@playwright/test';
import { corpoLoginUrlEncoded } from './_credenciais';

test.describe('Financeiro — Faturamento AI (Phase 4)', () => {
  test.use({ storageState: 'e2e/.auth/user.json' });

  test('pagina de faturamento carrega com tabs', async ({ page }) => {
    await page.goto('/modulos/financeiro/faturamento', { waitUntil: 'load' });
    await expect(page.getByRole('heading', { name: /faturamento/i })).toBeVisible();
    // Verifica que as 4 tabs estão presentes
    await expect(page.getByText(/visao geral/i)).toBeVisible();
    await expect(page.getByText(/contratos a faturar/i)).toBeVisible();
    await expect(page.getByText(/calculadora de medicao/i)).toBeVisible();
    await expect(page.getByText(/historico/i)).toBeVisible();
  });

  test('tab Visao Geral exibe KPI cards', async ({ page }) => {
    await page.goto('/modulos/financeiro/faturamento', { waitUntil: 'load' });
    // Primeiro tab ativo por padrão
    await expect(page.getByText(/total faturado/i)).toBeVisible();
    await expect(page.getByText(/pago no mes/i)).toBeVisible();
    await expect(page.getByText(/pendente/i).first()).toBeVisible();
    await expect(page.getByText(/vencido/i)).toBeVisible();
  });

  test('tab Calculadora de Medicao é visível e tem formulário', async ({ page }) => {
    await page.goto('/modulos/financeiro/faturamento', { waitUntil: 'load' });
    // Clica na tab Calculadora
    await page.getByText(/calculadora de medicao/i).click();
    // Verifica formulário
    await expect(page.getByText(/tipo de servico/i)).toBeVisible();
    await expect(page.getByText(/descricao do contrato/i)).toBeVisible();
    await expect(page.getByText(/periodo \(dias\)/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /calcular medicao/i })).toBeVisible();
  });

  test('tab Contratos a Faturar é visível e tem seletor de mês', async ({ page }) => {
    await page.goto('/modulos/financeiro/faturamento', { waitUntil: 'load' });
    await page.getByText(/contratos a faturar/i).click();
    // Verifica input de mês
    await expect(page.locator('input[type="month"]')).toBeVisible();
    // Verifica botão de preview
    await expect(page.getByRole('button', { name: /preview faturamento/i })).toBeVisible();
  });

  test('tab Historico exibe tabela de regras', async ({ page }) => {
    await page.goto('/modulos/financeiro/faturamento', { waitUntil: 'load' });
    await page.getByText(/historico/i).click();
    // Aguarda carregar
    await page.waitForTimeout(2000);
    // Verifica que as colunas da tabela estão presentes
    await expect(page.getByText(/total regras/i)).toBeVisible();
    await expect(page.getByText(/ativas/i).first()).toBeVisible();
  });
});

test.describe('Backend — Billing Automator endpoints (Phase 4)', () => {
  test.use({ storageState: 'e2e/.auth/user.json' });

  // Token compartilhado entre todos os testes deste describe
  let sharedToken = '';

  test.beforeAll(async ({ request }) => {
    const fs = await import('fs');
    const storageState = JSON.parse(fs.readFileSync('e2e/.auth/user.json', 'utf-8'));
    const localStorage = storageState.origins?.[0]?.localStorage ?? [];
    const tokenEntry = localStorage.find((e: any) => e.name === 'access_token');
    if (tokenEntry?.value) {
      sharedToken = tokenEntry.value;
    } else {
      const resp = await request.post('http://localhost:8080/api/v1/auth/login', {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        data: corpoLoginUrlEncoded(),
      });
      const data = await resp.json();
      sharedToken = data.access_token ?? '';
    }
  });

  test('GET /ai/billing/summary retorna dados do resumo', async ({ request }) => {
    const resp = await request.get('http://localhost:8080/api/v1/financial/ai/billing/summary', {
      headers: { Authorization: `Bearer ${sharedToken}` },
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data).toHaveProperty('mes');
    expect(data).toHaveProperty('total_faturado');
    expect(data).toHaveProperty('total_pendente');
    expect(data).toHaveProperty('total_vencido');
    expect(data).toHaveProperty('total_pago');
    expect(data).toHaveProperty('qtd_faturas');
    expect(data).toHaveProperty('qtd_clientes');
    expect(data).toHaveProperty('ticket_medio');
  });

  test('GET /ai/billing/summary com mês especifico', async ({ request }) => {
    const resp = await request.get('http://localhost:8080/api/v1/financial/ai/billing/summary?mes=2026-03', {
      headers: { Authorization: `Bearer ${sharedToken}` },
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.mes).toBe('2026-03');
    expect(typeof data.total_faturado).toBe('number');
  });

  test('POST /ai/billing/medicao retorna cálculo de portaria', async ({ request }) => {
    const resp = await request.post('http://localhost:8080/api/v1/financial/ai/billing/medicao', {
      headers: { Authorization: `Bearer ${sharedToken}`, 'Content-Type': 'application/json' },
      data: JSON.stringify({
        tipo: 'portaria',
        descricao: 'Contrato teste — 2 postos',
        periodo_dias: 30,
      }),
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data).toHaveProperty('tipo');
    expect(data).toHaveProperty('valor_base');
    expect(data).toHaveProperty('adicional_he');
    expect(data).toHaveProperty('adicional_noturno');
    expect(data).toHaveProperty('deducoes');
    expect(data).toHaveProperty('valor_total');
    expect(data).toHaveProperty('detalhamento');
    expect(data.valor_total).toBeGreaterThan(0);
    expect(data.tipo).toBe('portaria');
  });

  test('POST /ai/billing/medicao retorna cálculo de limpeza', async ({ request }) => {
    const resp = await request.post('http://localhost:8080/api/v1/financial/ai/billing/medicao', {
      headers: { Authorization: `Bearer ${sharedToken}`, 'Content-Type': 'application/json' },
      data: JSON.stringify({
        tipo: 'limpeza',
        descricao: 'Limpeza mensal condominio',
        periodo_dias: 30,
      }),
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.tipo).toBe('limpeza');
    expect(data.valor_total).toBeGreaterThan(0);
  });

  test('GET /ai/billing/contracts retorna lista', async ({ request }) => {
    const resp = await request.get('http://localhost:8080/api/v1/financial/ai/billing/contracts?mes=2026-03', {
      headers: { Authorization: `Bearer ${sharedToken}` },
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(Array.isArray(data)).toBeTruthy();
    // Se houver dados, verificar estrutura
    if (data.length > 0) {
      expect(data[0]).toHaveProperty('valor_total');
      expect(data[0]).toHaveProperty('qtd_titulos');
      expect(data[0]).toHaveProperty('status');
    }
  });

  test('GET /ai/billing/preview retorna preview de faturamento', async ({ request }) => {
    const resp = await request.get('http://localhost:8080/api/v1/financial/ai/billing/preview?mes=2026-03', {
      headers: { Authorization: `Bearer ${sharedToken}` },
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data).toHaveProperty('contratos_a_faturar');
    expect(data).toHaveProperty('valor_estimado');
    expect(data).toHaveProperty('qtd_contratos');
    expect(data).toHaveProperty('observacoes');
    expect(Array.isArray(data.contratos_a_faturar)).toBeTruthy();
    expect(Array.isArray(data.observacoes)).toBeTruthy();
    expect(typeof data.valor_estimado).toBe('number');
  });
});
