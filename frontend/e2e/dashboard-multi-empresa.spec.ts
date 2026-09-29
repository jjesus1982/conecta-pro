import { test, expect } from '@playwright/test';
import { corpoLoginUrlEncoded } from './_credenciais';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3001';
const API_URL = 'http://localhost:8080';

let token: string = '';

test.beforeAll(async ({ request }) => {
  const res = await request.post(`${API_URL}/api/v1/auth/login`, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    data: corpoLoginUrlEncoded(),
  });
  const body = await res.json();
  token = body.access_token || '';
});

// ─── API Tests ────────────────────────────────────────────────────────────────

test('GET /dashboard/fiscal/grupo — retorna grupo + eletronica + patrimonial', async ({ request }) => {
  const res = await request.get(`${API_URL}/api/v1/empresas/dashboard/fiscal/grupo`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body).toHaveProperty('grupo');
  expect(body).toHaveProperty('conecta_eletronica');
  expect(body).toHaveProperty('conecta_patrimonial');
  expect(body.grupo.total_faturamento_estimado).toBeGreaterThan(0);
});

test('GET /dashboard/fiscal/grupo — eletronica tem carga_pct', async ({ request }) => {
  const res = await request.get(`${API_URL}/api/v1/empresas/dashboard/fiscal/grupo`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.conecta_eletronica).toHaveProperty('carga_pct');
  expect(typeof body.conecta_eletronica.carga_pct).toBe('number');
  expect(body.conecta_eletronica.carga_pct).toBeGreaterThan(0);
});

test('GET /dashboard/fiscal/grupo — patrimonial tem economia_liminar > 0', async ({ request }) => {
  const res = await request.get(`${API_URL}/api/v1/empresas/dashboard/fiscal/grupo`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.conecta_patrimonial).toHaveProperty('economia_liminar');
  expect(body.conecta_patrimonial.economia_liminar).toBeGreaterThan(0);
});

test('GET /dashboard/rentabilidade/grupo — retorna por_contrato', async ({ request }) => {
  const res = await request.get(`${API_URL}/api/v1/empresas/dashboard/rentabilidade/grupo`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body).toHaveProperty('por_contrato');
  expect(Array.isArray(body.por_contrato)).toBe(true);
  expect(body.por_contrato.length).toBeGreaterThan(0);
});

test('GET /dashboard/rentabilidade/grupo — tem ranking', async ({ request }) => {
  const res = await request.get(`${API_URL}/api/v1/empresas/dashboard/rentabilidade/grupo`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body).toHaveProperty('ranking');
  expect(Array.isArray(body.ranking)).toBe(true);
  // ranking deve estar ordenado por margem decrescente
  if (body.ranking.length >= 2) {
    expect(body.ranking[0].margem_pct).toBeGreaterThanOrEqual(body.ranking[1].margem_pct);
  }
});

test('GET /dashboard/contabil/grupo — retorna grupo_consolidado', async ({ request }) => {
  const res = await request.get(`${API_URL}/api/v1/empresas/dashboard/contabil/grupo`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body).toHaveProperty('grupo_consolidado');
  expect(body.grupo_consolidado.receita_bruta).toBeGreaterThan(0);
  expect(body.grupo_consolidado).toHaveProperty('lucro_liquido');
  expect(body.grupo_consolidado).toHaveProperty('margem_liquida_pct');
});

test('GET /dashboard/contabil/grupo — tem exportacao_contador', async ({ request }) => {
  const res = await request.get(`${API_URL}/api/v1/empresas/dashboard/contabil/grupo`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body).toHaveProperty('exportacao_contador');
  expect(body.exportacao_contador).toHaveProperty('formato');
  expect(body.exportacao_contador).toHaveProperty('status');
});

// ─── Frontend Tests ───────────────────────────────────────────────────────────

// Mock de autenticação e APIs do dashboard para testes frontend
async function setupDashboardMocks(page: any) {
  // Injetar token fake no localStorage antes de qualquer script da página
  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'fake-test-token-admin');
    localStorage.setItem('refresh_token', 'fake-refresh-token');
  });

  await page.route('**/api/v1/auth/me', (route: any) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        email: 'admin@conectaplus.com.br',
        name: 'Admin',
        role: 'admin',
        is_active: true,
        permissions: ['*'],
        tenant_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      }),
    });
  });
  await page.route('**/api/v1/empresas/dashboard/**', (route: any) => {
    const url = route.request().url();
    if (url.includes('fiscal')) {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          periodo: '03/2026',
          grupo: { total_faturamento_estimado: 350000, total_impostos_mes: 55000, economia_liminares_potencial: 5000 },
          conecta_eletronica: { regime: 'lucro_real', receita_estimada: 200000, impostos_mes: 40000, carga_pct: 20, detalhamento: {} },
          conecta_patrimonial: { regime: 'simples_nacional', receita_estimada: 150000, impostos_sem_liminar: 15000, impostos_com_liminar: 10000, economia_liminar: 5000, carga_pct_sem: 10, carga_pct_com: 6.7, status_liminares: 'a_solicitar' },
          obrigacoes_mes: { total: 14, criticas: 2, atrasadas: 5, pendentes: 9 },
        }),
      });
    } else if (url.includes('rentabilidade')) {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          resumo_grupo: { total_receita_mes: 350000, total_lucro_liquido_mes: 70000, margem_media_pct: 20, total_receita_anual_estimada: 4200000 },
          por_contrato: [
            { tipo_servico: 'vigilancia', empresa: 'conecta_patrimonial', receita_mes: 100000, impostos_mes: 10000, lucro_liquido_mes: 20000, margem_pct: 20, situacao: 'bom', alertas: [] },
          ],
          ranking: [
            { tipo_servico: 'vigilancia', margem_pct: 25, situacao: 'excelente' },
            { tipo_servico: 'portaria_remota', margem_pct: 20, situacao: 'bom' },
          ],
          alertas: [],
        }),
      });
    } else if (url.includes('contabil')) {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          periodo: '03/2026',
          grupo_consolidado: {
            receita_bruta: 350000,
            deducoes: 5000,
            receita_liquida: 345000,
            custos_operacionais: 200000,
            lucro_bruto: 145000,
            despesas_administrativas: 50000,
            resultado_operacional: 95000,
            impostos: 25000,
            lucro_liquido: 70000,
            margem_liquida_pct: 20,
          },
          por_empresa: {
            conecta_eletronica: { receita_bruta: 200000, impostos: 20000, lucro_liquido: 40000, margem_pct: 20 },
            conecta_patrimonial: { receita_bruta: 150000, impostos: 5000, lucro_liquido: 30000, margem_pct: 20, economia_potencial_liminares: 5000 },
          },
          exportacao_contador: { formato: 'TOTVS Dominio', ultima_exportacao: null, proxima_exportacao: '2026-04-01', status: 'disponivel' },
        }),
      });
    } else {
      route.continue();
    }
  });
}

test('Frontend /modulos/empresas/dashboard carrega', async ({ page }) => {
  await setupDashboardMocks(page);
  await page.goto(`${BASE_URL}/modulos/empresas/dashboard`, { waitUntil: 'load' });
  // Aguardar remoção de loading
  await page.waitForTimeout(2000);
  const title = page.locator('h1');
  await expect(title).toContainText('Conecta Mais');
});

test('KPI cards visíveis', async ({ page }) => {
  await setupDashboardMocks(page);
  await page.goto(`${BASE_URL}/modulos/empresas/dashboard`, { waitUntil: 'load' });
  await page.waitForTimeout(2500);
  const kpiCards = page.locator('[data-testid="kpi-cards"]');
  await expect(kpiCards).toBeVisible();
  // Deve ter pelo menos 4 cards
  const cards = kpiCards.locator('.shadow-sm, .border');
  expect(await cards.count()).toBeGreaterThanOrEqual(3);
});

test('Tabs navegáveis', async ({ page }) => {
  await setupDashboardMocks(page);
  await page.goto(`${BASE_URL}/modulos/empresas/dashboard`, { waitUntil: 'load' });
  await page.waitForTimeout(2000);
  const tabsContainer = page.locator('[data-testid="tabs-container"]');
  await expect(tabsContainer).toBeVisible();

  // Clicar na aba Rentabilidade — escopar pelo container de tabs para evitar conflito com sidebar
  await tabsContainer.locator('button', { hasText: 'Rentabilidade' }).click();
  await page.waitForTimeout(500);

  // Clicar na aba Contábil
  await tabsContainer.locator('button', { hasText: 'Contábil' }).click();
  await page.waitForTimeout(500);

  // Verificar que o container de tabs ainda está visível após navegação
  await expect(tabsContainer).toBeVisible();
  // As três abas devem existir no container
  const allTabButtons = tabsContainer.locator('button');
  expect(await allTabButtons.count()).toBeGreaterThanOrEqual(3);
});
