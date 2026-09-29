import { test, expect } from '@playwright/test';
import { corpoLoginUrlEncoded } from './_credenciais';

const BASE = process.env.BASE_URL || 'http://localhost:3001';
const API = 'http://localhost:8080';

// ─── Backend API Tests — token compartilhado via beforeAll ──────────────────

test.describe('Obrigações Multi-Empresa — API Backend', () => {
  let token: string = '';

  test.beforeAll(async ({ request }) => {
    const res = await request.post(`${API}/api/v1/auth/login`, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      data: corpoLoginUrlEncoded(),
    });
    const data = await res.json();
    token = data.access_token as string;
  });

  test('GET /calendario/grupo — retorna resumo + por_empresa com eletronica e patrimonial', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/empresas/obrigacoes/calendario/grupo`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(200);
    const data = await res.json();
    expect(data).toHaveProperty('resumo');
    expect(data).toHaveProperty('por_empresa');
    expect(data.por_empresa).toHaveProperty('conecta_eletronica');
    expect(data.por_empresa).toHaveProperty('conecta_patrimonial');
  });

  test('GET /calendario/grupo — resumo tem campos total, criticas, atrasadas, pendentes', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/empresas/obrigacoes/calendario/grupo`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    expect(data.resumo).toHaveProperty('total');
    expect(data.resumo).toHaveProperty('criticas');
    expect(data.resumo).toHaveProperty('atrasadas');
    expect(data.resumo).toHaveProperty('pendentes');
    expect(typeof data.resumo.total).toBe('number');
    expect(data.resumo.total).toBeGreaterThan(0);
  });

  test('GET /calendario/grupo — eletronica tem obrigacoes de Lucro Real (EFD_ICMS_IPI, DCTF)', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/empresas/obrigacoes/calendario/grupo`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    const eletronica: { tipo: string }[] = data.por_empresa.conecta_eletronica;
    const tipos = eletronica.map((o) => o.tipo);
    expect(tipos).toContain('EFD_ICMS_IPI');
    expect(tipos).toContain('DCTF');
    expect(tipos).toContain('EFD_CONTRIBUICOES');
  });

  test('GET /calendario/grupo — patrimonial tem obrigacoes do Simples Nacional (PGDAS_D, DAS)', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/empresas/obrigacoes/calendario/grupo`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    const patrimonial: { tipo: string }[] = data.por_empresa.conecta_patrimonial;
    const tipos = patrimonial.map((o) => o.tipo);
    expect(tipos).toContain('PGDAS_D');
    expect(tipos).toContain('DAS');
  });

  test('GET /calendario/grupo — patrimonial NAO tem EFD_ICMS_IPI nem EFD_CONTRIBUICOES (dispensada)', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/empresas/obrigacoes/calendario/grupo`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    const patrimonial: { tipo: string }[] = data.por_empresa.conecta_patrimonial;
    const tipos = patrimonial.map((o) => o.tipo);
    expect(tipos).not.toContain('EFD_ICMS_IPI');
    expect(tipos).not.toContain('EFD_CONTRIBUICOES');
    expect(tipos).not.toContain('DCTF');
  });

  test('GET /calendario/conecta_eletronica — retorna obrigacoes mensais Lucro Real', async ({ request }) => {
    const res = await request.get(
      `${API}/api/v1/empresas/obrigacoes/calendario/conecta_eletronica`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    expect(res.status()).toBe(200);
    const data = await res.json();
    expect(data).toHaveProperty('empresa_slug', 'conecta_eletronica');
    expect(data).toHaveProperty('regime', 'lucro_real');
    expect(data.obrigacoes.length).toBeGreaterThan(0);
    const tipos = data.obrigacoes.map((o: { tipo: string }) => o.tipo);
    expect(tipos).toContain('EFD_ICMS_IPI');
  });

  test('GET /calendario/conecta_patrimonial — retorna obrigacoes mensais Simples Nacional', async ({ request }) => {
    const res = await request.get(
      `${API}/api/v1/empresas/obrigacoes/calendario/conecta_patrimonial`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    expect(res.status()).toBe(200);
    const data = await res.json();
    expect(data).toHaveProperty('empresa_slug', 'conecta_patrimonial');
    expect(data).toHaveProperty('regime', 'simples_nacional');
    expect(data.obrigacoes.length).toBeGreaterThan(0);
  });

  test('GET /alertas — retorna lista de alertas e dias_antecedencia', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/empresas/obrigacoes/alertas`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(200);
    const data = await res.json();
    expect(data).toHaveProperty('alertas');
    expect(data).toHaveProperty('dias_antecedencia');
    expect(Array.isArray(data.alertas)).toBe(true);
  });

  test('GET /dispensadas-simples — retorna lista de obrigacoes dispensadas', async ({ request }) => {
    const res = await request.get(
      `${API}/api/v1/empresas/obrigacoes/dispensadas-simples`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    expect(res.status()).toBe(200);
    const data = await res.json();
    expect(data).toHaveProperty('dispensadas');
    expect(Array.isArray(data.dispensadas)).toBe(true);
    expect(data.dispensadas.length).toBeGreaterThan(0);
    // Deve conter EFD na lista
    const hasEfd = data.dispensadas.some((d: string) => d.includes('EFD'));
    expect(hasEfd).toBe(true);
  });
});

// ─── Frontend UI Tests ─────────────────────────────────────────────────────

test.describe('Obrigações Multi-Empresa — Frontend UI', () => {
  test('Frontend — página de obrigações carrega', async ({ page }) => {
    // Injetar token fake antes de qualquer script da página
    await page.addInitScript(() => {
      localStorage.setItem('access_token', 'fake-test-token-admin');
      localStorage.setItem('refresh_token', 'fake-refresh-token');
    });
    // Mock /auth/me para evitar redirect para login
    await page.route('**/api/v1/auth/me', (route) => {
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
    // Mock da API de obrigações para não precisar de token real
    await page.route('**/api/v1/empresas/obrigacoes/**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          resumo: { total: 14, criticas: 2, atrasadas: 5, pendentes: 9, concluidas: 0 },
          por_empresa: {
            conecta_eletronica: [],
            conecta_patrimonial: [],
          },
        }),
      });
    });

    await page.goto(`${BASE}/modulos/empresas/obrigacoes`, { waitUntil: 'load' });
    await page.waitForTimeout(2000);
    await expect(page.locator('h1,h2').filter({ hasText: /Obriga/i }).first()).toBeVisible({ timeout: 10000 });
  });

  test('Frontend — KPI cards são visíveis na página de obrigações', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('access_token', 'fake-test-token-admin');
      localStorage.setItem('refresh_token', 'fake-refresh-token');
    });
    await page.route('**/api/v1/auth/me', (route) => {
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
    await page.route('**/api/v1/empresas/obrigacoes/**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          resumo: { total: 14, criticas: 2, atrasadas: 5, pendentes: 9, concluidas: 0 },
          por_empresa: {
            conecta_eletronica: [],
            conecta_patrimonial: [],
          },
        }),
      });
    });

    await page.goto(`${BASE}/modulos/empresas/obrigacoes`, { waitUntil: 'load' });
    await page.waitForTimeout(2000);

    await expect(page.locator('text=Total').first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Críticas').or(page.locator('text=Criticas')).first()).toBeVisible();
  });
});
