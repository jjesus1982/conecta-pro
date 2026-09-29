/**
 * Testes E2E - Multi-Empresa (Multi-CNPJ)
 *
 * Validações:
 * - Backend API: listar empresas, sugerir empresa por serviço, simular regime
 * - Backend API: endpoints fiscais (Simples Nacional, Lucro Real, Comparativo, Retenções)
 * - Frontend UI: páginas /empresas, /empresas/liminares, /empresas/rentabilidade
 */

import { test, expect } from './fixtures';
import { corpoLoginUrlEncoded } from './_credenciais';

const API_URL = 'http://localhost:8080';

// ─── Helper: obtém token via OAuth2 form ─────────────────────────────────────

async function getToken(request: any): Promise<string> {
  const resp = await request.post(`${API_URL}/api/v1/auth/login`, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    data: corpoLoginUrlEncoded(),
  });
  const data = await resp.json();
  expect(data.access_token, 'Deve retornar access_token no login').toBeTruthy();
  return data.access_token;
}

// ─────────────────────────────────────────────────────────────────────────────
// BLOCO 1 — API: Empresas
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Multi-Empresa — API: Empresas', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    token = await getToken(request);
  });

  test('GET /api/v1/empresas — retorna lista com 2 empresas', async ({ request }) => {
    const resp = await request.get(`${API_URL}/api/v1/empresas/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(Array.isArray(data)).toBe(true);
    expect(data.length).toBeGreaterThanOrEqual(2);
  });

  test('GET /api/v1/empresas — Eletrônica tem slug e regime lucro_real', async ({ request }) => {
    const resp = await request.get(`${API_URL}/api/v1/empresas/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await resp.json();
    const eletronica = data.find((e: any) => e.slug === 'conecta_eletronica');
    expect(eletronica, 'Eletrônica deve estar na lista').toBeDefined();
    expect(eletronica.regime_tributario).toBe('lucro_real');
    expect(eletronica.is_principal).toBe(true);
  });

  test('GET /api/v1/empresas — Patrimonial tem regime simples_nacional e status em_abertura', async ({ request }) => {
    const resp = await request.get(`${API_URL}/api/v1/empresas/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await resp.json();
    const patrimonial = data.find((e: any) => e.slug === 'conecta_patrimonial');
    expect(patrimonial, 'Patrimonial deve estar na lista').toBeDefined();
    expect(patrimonial.regime_tributario).toBe('simples_nacional');
    expect(patrimonial.status).toBe('em_abertura');
  });

  test('GET /api/v1/empresas sem autenticação — retorna 403', async ({ request }) => {
    const resp = await request.get(`${API_URL}/api/v1/empresas/`);
    // Backend retorna 403 para requests sem token (sem header Authorization)
    expect(resp.status()).toBe(403);
  });

  test('GET /api/v1/empresas/sugerir/vigilancia — sugere Patrimonial', async ({ request }) => {
    const resp = await request.get(`${API_URL}/api/v1/empresas/sugerir/vigilancia`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.slug).toBe('conecta_patrimonial');
    expect(data.motivo).toBeTruthy();
    expect(typeof data.carga_tributaria_estimada).toBe('number');
  });

  test('GET /api/v1/empresas/sugerir/portaria_remota — sugere Eletrônica', async ({ request }) => {
    const resp = await request.get(`${API_URL}/api/v1/empresas/sugerir/portaria_remota`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.slug).toBe('conecta_eletronica');
  });

  test('POST /api/v1/empresas/{id}/simular-regime — calcula economia para Simples', async ({ request }) => {
    // Obter ID da Eletrônica
    const listaResp = await request.get(`${API_URL}/api/v1/empresas/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const lista = await listaResp.json();
    const eletronica = lista.find((e: any) => e.slug === 'conecta_eletronica');

    const resp = await request.post(
      `${API_URL}/api/v1/empresas/${eletronica.id}/simular-regime`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        data: { novo_regime: 'simples_nacional', faturamento_anual: 1200000 },
      }
    );
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.economia_anual).toBeGreaterThan(0);
    expect(data.regime_atual).toBe('lucro_real');
    expect(data.regime_simulado).toBe('simples_nacional');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// BLOCO 2 — API: Fiscal — Simples Nacional
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Multi-Empresa — API: Fiscal Simples Nacional', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    token = await getToken(request);
  });

  test('POST /fiscal/calcular/simples — retorna DAS e aliquota_efetiva', async ({ request }) => {
    const resp = await request.post(
      `${API_URL}/api/v1/financial/fiscal/calcular/simples`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        data: { receita_mes: 50000, rbt12: 500000, liminares: [] },
      }
    );
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.valor_das).toBeGreaterThan(0);
    expect(data.aliquota_efetiva).toBeTruthy();
    expect(data.carga_tributaria).toBeTruthy();
    expect(data.regime).toBe('simples_nacional');
    expect(Array.isArray(data.liminares_aplicadas)).toBe(true);
  });

  test('POST /fiscal/calcular/simples com liminar pis_cofins_zero — DAS menor e economia > 0', async ({ request }) => {
    const headers = {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    };

    const semResp = await request.post(
      `${API_URL}/api/v1/financial/fiscal/calcular/simples`,
      { headers, data: { receita_mes: 50000, rbt12: 500000, liminares: [] } }
    );
    const semData = await semResp.json();

    const comResp = await request.post(
      `${API_URL}/api/v1/financial/fiscal/calcular/simples`,
      { headers, data: { receita_mes: 50000, rbt12: 500000, liminares: ['pis_cofins_zero'] } }
    );
    const comData = await comResp.json();

    expect(comData.valor_das).toBeLessThan(semData.valor_das);
    expect(comData.economia_liminares).toBeGreaterThan(0);
    expect(comData.liminares_aplicadas).toContain('pis_cofins_zero');
  });

  test('POST /fiscal/calcular/verificar-limite-simples — status ok para RBT12 normal', async ({ request }) => {
    const resp = await request.post(
      `${API_URL}/api/v1/financial/fiscal/calcular/verificar-limite-simples`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        data: { rbt12: 600000 },
      }
    );
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.status).toBe('ok');
    expect(data.percentual_limite_nacional).toBeGreaterThan(0);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// BLOCO 3 — API: Fiscal — Lucro Real e Comparativo
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Multi-Empresa — API: Fiscal Lucro Real e Comparativo', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    token = await getToken(request);
  });

  test('POST /fiscal/calcular/lucro-real — retorna todos os impostos', async ({ request }) => {
    const resp = await request.post(
      `${API_URL}/api/v1/financial/fiscal/calcular/lucro-real`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        data: { receita_mes: 100000, receita_trimestre: 300000 },
      }
    );
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.irpj).toBeGreaterThan(0);
    expect(data.csll).toBeGreaterThan(0);
    expect(data.pis).toBeGreaterThan(0);
    expect(data.cofins).toBeGreaterThan(0);
    expect(data.iss).toBeGreaterThan(0);
    expect(data.total_impostos_mes).toBeGreaterThan(0);
    expect(data.regime).toBe('lucro_real');
  });

  test('POST /fiscal/calcular/comparativo-regimes — Simples < Lucro Real e tem recomendacao', async ({ request }) => {
    const resp = await request.post(
      `${API_URL}/api/v1/financial/fiscal/calcular/comparativo-regimes`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        data: { receita_anual: 1200000 },
      }
    );
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.simples_nacional.total_anual).toBeLessThan(data.lucro_real.total_anual);
    expect(data.economia_simples_anual).toBeGreaterThan(0);
    expect(data.recomendacao).toBeTruthy();
  });

  test('POST /fiscal/calcular/retencoes-nfse com liminares inss+pis_cofins — INSS e PIS/COFINS zerados', async ({ request }) => {
    const resp = await request.post(
      `${API_URL}/api/v1/financial/fiscal/calcular/retencoes-nfse`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        data: {
          valor_servico: 50000,
          regime_empresa: 'simples_nacional',
          liminares: ['inss_nao_retido', 'pis_cofins_zero'],
        },
      }
    );
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.retencoes.inss_11pct).toBe(0);
    expect(data.retencoes.pis_0_65pct).toBe(0);
    expect(data.retencoes.cofins_3pct).toBe(0);
    expect(data.liminares_aplicadas.length).toBeGreaterThan(0);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// BLOCO 4 — Frontend UI
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Multi-Empresa — Frontend UI', () => {
  test('Página /modulos/empresas carrega com título Gestão Multi-Empresa', async ({ page }) => {
    await page.goto('/modulos/empresas', { waitUntil: 'load' });
    await expect(page.locator('h1')).toContainText('Multi-Empresa', { timeout: 10000 });
  });

  test('Cards das duas empresas aparecem na página principal', async ({ page }) => {
    await page.goto('/modulos/empresas', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });
    // Nomes das empresas
    await expect(page.locator('text=Conecta Mais Eletrônica').first()).toBeVisible();
    await expect(page.locator('text=Conecta Mais Patrimonial').first()).toBeVisible();
  });

  test('Badges de regime tributário visíveis nos cards', async ({ page }) => {
    await page.goto('/modulos/empresas', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });
    // Lucro Real e Simples Nacional aparecem como badges
    await expect(page.locator('text=Lucro Real').first()).toBeVisible();
    await expect(page.locator('text=Simples Nacional').first()).toBeVisible();
  });

  test('Quick nav links estão visíveis: Liminares Judiciais e Rentabilidade', async ({ page }) => {
    await page.goto('/modulos/empresas', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Liminares Judiciais').first()).toBeVisible();
    await expect(page.locator('text=Rentabilidade').first()).toBeVisible();
  });

  test('Calculadora — aba Simples Nacional visível por padrão', async ({ page }) => {
    await page.goto('/modulos/empresas', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });
    // Tabs da calculadora
    await expect(page.locator('button', { hasText: 'Simples Nacional' }).first()).toBeVisible();
    await expect(page.locator('button', { hasText: 'Lucro Real' }).first()).toBeVisible();
    await expect(page.locator('button', { hasText: 'Comparativo' }).first()).toBeVisible();
  });

  test('Calculadora — preencher e calcular DAS Simples Nacional', async ({ page }) => {
    await page.goto('/modulos/empresas', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });

    // Inputs do Simples Nacional (são os primeiros inputs do form)
    const inputs = page.locator('input[type="number"]');
    await inputs.nth(0).fill('50000');   // Receita do Mês
    await inputs.nth(1).fill('500000');  // RBT12

    // Clicar em Calcular DAS
    await page.locator('button', { hasText: 'Calcular DAS' }).click();
    await page.waitForTimeout(300);

    // Resultado deve aparecer: Alíquota Efetiva e DAS a Recolher
    await expect(page.locator('text=Alíquota Efetiva').first()).toBeVisible({ timeout: 5000 });
    await expect(page.locator('text=DAS a Recolher').first()).toBeVisible();
  });

  test('Calculadora — navegar para aba Lucro Real', async ({ page }) => {
    await page.goto('/modulos/empresas', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });

    await page.locator('button', { hasText: 'Lucro Real' }).click();
    await page.waitForTimeout(300);

    // Input específico do Lucro Real: Receita do Trimestre
    await expect(page.locator('text=Receita do Trimestre').first()).toBeVisible({ timeout: 5000 });
    await expect(page.locator('button', { hasText: 'Calcular Impostos' }).first()).toBeVisible();
  });

  test('Calculadora — navegar para aba Comparativo', async ({ page }) => {
    await page.goto('/modulos/empresas', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });

    await page.locator('button', { hasText: 'Comparativo' }).click();
    await page.waitForTimeout(300);

    await expect(page.locator('text=Receita Anual').first()).toBeVisible({ timeout: 5000 });
    await expect(page.locator('button', { hasText: 'Comparar Regimes' }).first()).toBeVisible();
  });

  test('Seção Sugerir Empresa para Faturar está visível', async ({ page }) => {
    await page.goto('/modulos/empresas', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Sugerir Empresa para Faturar').first()).toBeVisible();
    // Select com opções de serviço
    await expect(page.locator('select').last()).toBeVisible();
  });

  test('Sugestão de empresa — selecionar Vigilância e ver resultado', async ({ page }) => {
    await page.goto('/modulos/empresas', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });

    // Selecionar serviço no dropdown
    const select = page.locator('select').last();
    await select.selectOption('vigilancia');
    await page.waitForTimeout(200);

    // Clicar em Sugerir Empresa
    await page.locator('button', { hasText: 'Sugerir Empresa' }).click();
    await page.waitForTimeout(300);

    // Resultado: nome da empresa sugerida
    await expect(page.locator('text=Conecta Mais Patrimonial').first()).toBeVisible({ timeout: 5000 });
  });

  test('Página /modulos/empresas/liminares carrega com título correto', async ({ page }) => {
    await page.goto('/modulos/empresas/liminares', { waitUntil: 'load' });
    await expect(page.locator('h1')).toContainText('Liminares', { timeout: 10000 });
  });

  test('Página Liminares — exibe 2 liminares iniciais na tabela', async ({ page }) => {
    await page.goto('/modulos/empresas/liminares', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });
    // Tipos de liminar pré-cadastrados
    await expect(page.locator('text=PIS/COFINS = 0').first()).toBeVisible();
    await expect(page.locator('text=INSS Não Retido').first()).toBeVisible();
  });

  test('Página Liminares — botão Nova Liminar abre modal', async ({ page }) => {
    await page.goto('/modulos/empresas/liminares', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });

    await page.locator('button', { hasText: 'Nova Liminar' }).click();
    await page.waitForTimeout(300);

    // Modal deve aparecer
    await expect(page.locator('text=Nova Liminar').last()).toBeVisible({ timeout: 5000 });
    // Botão Cancelar dentro do modal
    await expect(page.locator('button', { hasText: 'Cancelar' }).first()).toBeVisible();
  });

  test('Página Liminares — KPIs de contagem visíveis', async ({ page }) => {
    await page.goto('/modulos/empresas/liminares', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Total').first()).toBeVisible();
    await expect(page.locator('text=A Solicitar').first()).toBeVisible();
    await expect(page.locator('text=Concedidas').first()).toBeVisible();
  });

  test('Página /modulos/empresas/rentabilidade carrega com título correto', async ({ page }) => {
    await page.goto('/modulos/empresas/rentabilidade', { waitUntil: 'load' });
    await expect(page.locator('h1')).toContainText('Rentabilidade', { timeout: 10000 });
  });

  test('Página Rentabilidade — formulário com campos de entrada visíveis', async ({ page }) => {
    await page.goto('/modulos/empresas/rentabilidade', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Receita Bruta Mensal').first()).toBeVisible();
    await expect(page.locator('text=Custo Direto').first()).toBeVisible();
    await expect(page.locator('button', { hasText: 'Calcular' }).first()).toBeVisible();
  });

  test('Página Rentabilidade — calcular margem para Eletrônica', async ({ page }) => {
    await page.goto('/modulos/empresas/rentabilidade', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });

    // Preencher receita
    const inputs = page.locator('input[type="number"]');
    await inputs.nth(0).fill('100000');  // Receita Bruta Mensal
    await inputs.nth(1).fill('60000');   // Custo Direto
    await inputs.nth(2).fill('10000');   // Custo Indireto

    // Selecionar empresa Eletrônica
    const selects = page.locator('select');
    await selects.last().selectOption('eletronica');

    // Calcular
    await page.locator('button', { hasText: 'Calcular' }).first().click();
    await page.waitForTimeout(400);

    // Resultado deve mostrar Margem Líquida
    await expect(page.locator('text=Margem Líquida').first()).toBeVisible({ timeout: 5000 });
  });

  test('Página Rentabilidade — botão Comparar gera comparativo entre empresas', async ({ page }) => {
    await page.goto('/modulos/empresas/rentabilidade', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });

    // Preencher apenas receita (mínimo para habilitar Comparar)
    const inputs = page.locator('input[type="number"]');
    await inputs.nth(0).fill('80000');

    await page.locator('button', { hasText: 'Comparar' }).click();
    await page.waitForTimeout(400);

    // Deve mostrar as duas empresas no comparativo
    await expect(page.locator('text=Comparativo entre Empresas').first()).toBeVisible({ timeout: 5000 });
  });

  test('Link Voltar para Multi-Empresa funciona em Liminares', async ({ page }) => {
    await page.goto('/modulos/empresas/liminares', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });

    await page.locator('text=Voltar para Multi-Empresa').click();
    await page.waitForURL('**/empresas', { timeout: 10000 });
    await expect(page.locator('h1')).toContainText('Multi-Empresa', { timeout: 8000 });
  });
});
