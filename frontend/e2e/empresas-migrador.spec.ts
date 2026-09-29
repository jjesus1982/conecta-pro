/**
 * Testes E2E - Migrador de Contratos (Fase 3 Multi-Empresa)
 *
 * Validações:
 * - API: analisar, simular, executar, aditivo, analisar-lote, sugerir
 * - Frontend UI: página /modulos/empresas/migrador carrega corretamente
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
// BLOCO 1 — API: Analisar Contrato
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Migrador — API: Analisar Contrato', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    token = await getToken(request);
  });

  test('POST /migrador/analisar — vigilancia → patrimonial deve_migrar=true', async ({ request }) => {
    const resp = await request.post(`${API_URL}/api/v1/empresas/migrador/analisar`, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      data: {
        contrato_id: 1,
        tipo_servico: 'vigilancia',
        empresa_atual_slug: 'conecta_eletronica',
        receita_bruta_mes: 80000,
        custo_direto_mes: 50000,
        liminares_patrimonial: [],
      },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.deve_migrar).toBe(true);
    expect(data.empresa_destino).toBe('conecta_patrimonial');
    expect(data.motivo).toBeTruthy();
    expect(data.impacto_financeiro).toBeDefined();
    expect(typeof data.impacto_financeiro.economia_mensal).toBe('number');
    expect(typeof data.impacto_financeiro.economia_anual).toBe('number');
    expect(Array.isArray(data.pendencias)).toBe(true);
    expect(typeof data.pode_migrar_imediatamente).toBe('boolean');
  });

  test('POST /migrador/analisar — portaria_remota → eletronica deve_migrar=false quando já na eletrônica', async ({ request }) => {
    const resp = await request.post(`${API_URL}/api/v1/empresas/migrador/analisar`, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      data: {
        contrato_id: 2,
        tipo_servico: 'portaria_remota',
        empresa_atual_slug: 'conecta_eletronica',
        receita_bruta_mes: 45000,
        custo_direto_mes: 20000,
        liminares_patrimonial: [],
      },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.empresa_destino).toBe('conecta_eletronica');
    expect(data.deve_migrar).toBe(false);
  });

  test('POST /migrador/analisar — vigilancia com liminares — tem pendencias menores', async ({ request }) => {
    const resp = await request.post(`${API_URL}/api/v1/empresas/migrador/analisar`, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      data: {
        contrato_id: 3,
        tipo_servico: 'vigilancia',
        empresa_atual_slug: 'conecta_eletronica',
        receita_bruta_mes: 50000,
        liminares_patrimonial: ['pis_cofins_zero', 'inss_nao_retido'],
      },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.empresa_destino).toBe('conecta_patrimonial');
    // Com as 2 liminares concedidas, menos pendências de liminar
    const temLiminarPis = data.pendencias.some((p: string) => p.includes('PIS/COFINS'));
    const temLiminarInss = data.pendencias.some((p: string) => p.includes('INSS'));
    expect(temLiminarPis).toBe(false);
    expect(temLiminarInss).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// BLOCO 2 — API: Simular Migração
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Migrador — API: Simular Migração', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    token = await getToken(request);
  });

  test('POST /migrador/simular — retorna vale_migrar e margens', async ({ request }) => {
    const resp = await request.post(`${API_URL}/api/v1/empresas/migrador/simular`, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      data: {
        contrato_id: 1,
        tipo_servico: 'vigilancia',
        empresa_atual_slug: 'conecta_eletronica',
        empresa_destino_slug: 'conecta_patrimonial',
        receita_bruta_mes: 80000,
        custo_direto_mes: 50000,
        custo_indireto_mes: 5000,
        rbt12: 600000,
        liminares: [],
      },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(typeof data.vale_migrar).toBe('boolean');
    expect(data.margem).toBeDefined();
    expect(typeof data.margem.origem_pct).toBe('number');
    expect(typeof data.margem.destino_pct).toBe('number');
    expect(typeof data.margem.ganho_pct).toBe('number');
    expect(data.impostos).toBeDefined();
    expect(typeof data.impostos.economia_anual).toBe('number');
    expect(data.recomendacao).toBeTruthy();
  });

  test('POST /migrador/simular — retorna liminares_aplicadas', async ({ request }) => {
    const resp = await request.post(`${API_URL}/api/v1/empresas/migrador/simular`, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      data: {
        contrato_id: 5,
        tipo_servico: 'vigilancia',
        empresa_atual_slug: 'conecta_eletronica',
        empresa_destino_slug: 'conecta_patrimonial',
        receita_bruta_mes: 60000,
        custo_direto_mes: 40000,
        liminares: ['pis_cofins_zero'],
      },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(Array.isArray(data.liminares_aplicadas)).toBe(true);
    expect(data.liminares_aplicadas).toContain('pis_cofins_zero');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// BLOCO 3 — API: Executar e Aditivo
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Migrador — API: Executar e Aditivo', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    token = await getToken(request);
  });

  test('POST /migrador/executar — retorna sucesso e aditivo_gerado', async ({ request }) => {
    const resp = await request.post(`${API_URL}/api/v1/empresas/migrador/executar`, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      data: {
        contrato_id: 42,
        empresa_origem_slug: 'conecta_eletronica',
        empresa_destino_slug: 'conecta_patrimonial',
        gerar_aditivo: true,
      },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.sucesso).toBe(true);
    expect(data.mensagem).toContain('42');
    expect(data.aditivo_gerado).toBe(true);
    expect(data.data_migracao).toBeTruthy();
  });

  test('POST /migrador/executar — sem aditivo — aditivo_gerado=false', async ({ request }) => {
    const resp = await request.post(`${API_URL}/api/v1/empresas/migrador/executar`, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      data: {
        contrato_id: 10,
        empresa_origem_slug: 'conecta_eletronica',
        empresa_destino_slug: 'conecta_patrimonial',
        gerar_aditivo: false,
      },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.sucesso).toBe(true);
    expect(data.aditivo_gerado).toBe(false);
  });

  test('POST /migrador/aditivo — retorna texto com campos do contrato', async ({ request }) => {
    const resp = await request.post(`${API_URL}/api/v1/empresas/migrador/aditivo`, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      data: {
        contrato_id: 99,
        empresa_origem: 'conecta_eletronica',
        empresa_destino: 'conecta_patrimonial',
        cnpj_destino: '12.345.678/0001-99',
      },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.aditivo_texto).toBeTruthy();
    expect(data.aditivo_texto).toContain('99');
    expect(data.aditivo_texto).toContain('12.345.678/0001-99');
    expect(data.aditivo_texto).toContain('ADITIVO DE TRANSFERÊNCIA CONTRATUAL');
    expect(data.formato).toBe('texto_simples');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// BLOCO 4 — API: Analisar Lote e Sugerir
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Migrador — API: Lote e Sugerir', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    token = await getToken(request);
  });

  test('POST /migrador/analisar-lote — retorna humanizados e eletronicos', async ({ request }) => {
    const resp = await request.post(`${API_URL}/api/v1/empresas/migrador/analisar-lote`, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      data: {
        contratos: [
          { contrato_id: 1, tipo_servico: 'vigilancia', receita_mes: 80000 },
          { contrato_id: 2, tipo_servico: 'portaria_remota', receita_mes: 45000 },
          { contrato_id: 3, tipo_servico: 'limpeza', receita_mes: 30000 },
          { contrato_id: 4, tipo_servico: 'cftv', receita_mes: 25000 },
        ],
        empresa_atual_slug: 'conecta_eletronica',
        liminares_patrimonial: [],
      },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.total_contratos).toBe(4);
    expect(data.humanizados).toBe(2);
    expect(data.eletronicos).toBe(2);
    expect(typeof data.economia_anual_total).toBe('number');
    expect(Array.isArray(data.detalhes_humanizados)).toBe(true);
    expect(Array.isArray(data.detalhes_eletronicos)).toBe(true);
    expect(data.detalhes_humanizados.length).toBe(2);
  });

  test('POST /migrador/analisar-lote — sem liminares economia menor que com liminares', async ({ request }) => {
    const headers = {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    };
    const contratos = [
      { contrato_id: 1, tipo_servico: 'vigilancia', receita_mes: 80000 },
    ];

    const semLimResp = await request.post(`${API_URL}/api/v1/empresas/migrador/analisar-lote`, {
      headers,
      data: { contratos, empresa_atual_slug: 'conecta_eletronica', liminares_patrimonial: [] },
    });
    const semLim = await semLimResp.json();

    const comLimResp = await request.post(`${API_URL}/api/v1/empresas/migrador/analisar-lote`, {
      headers,
      data: { contratos, empresa_atual_slug: 'conecta_eletronica', liminares_patrimonial: ['pis_cofins_zero'] },
    });
    const comLim = await comLimResp.json();

    // Com liminar PIS/COFINS, a economia deve ser ainda maior (menos impostos na patrimonial)
    expect(comLim.economia_anual_total).toBeGreaterThanOrEqual(semLim.economia_anual_total);
  });

  test('GET /migrador/sugerir/vigilancia — retorna patrimonial', async ({ request }) => {
    const resp = await request.get(`${API_URL}/api/v1/empresas/migrador/sugerir/vigilancia`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.empresa_destino).toBe('conecta_patrimonial');
    expect(data.categoria).toBe('humanizado');
    expect(data.motivo).toBeTruthy();
  });

  test('GET /migrador/sugerir/portaria_remota — retorna eletronica', async ({ request }) => {
    const resp = await request.get(`${API_URL}/api/v1/empresas/migrador/sugerir/portaria_remota`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.empresa_destino).toBe('conecta_eletronica');
    expect(data.categoria).toBe('eletronico');
  });

  test('GET /migrador/sugerir/monitoramento_24h — retorna eletronica', async ({ request }) => {
    const resp = await request.get(`${API_URL}/api/v1/empresas/migrador/sugerir/monitoramento_24h`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.empresa_destino).toBe('conecta_eletronica');
  });

  test('GET /migrador/sugerir sem autenticação — retorna 403', async ({ request }) => {
    const resp = await request.get(`${API_URL}/api/v1/empresas/migrador/sugerir/vigilancia`);
    expect(resp.status()).toBe(403);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// BLOCO 5 — Frontend UI
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Migrador — Frontend UI', () => {
  test('Página /modulos/empresas/migrador carrega com título Migrador', async ({ page }) => {
    await page.goto('/modulos/empresas/migrador', { waitUntil: 'load' });
    await expect(page.locator('h1')).toContainText('Migrador', { timeout: 10000 });
  });

  test('Regras visuais (Humanizados → Patrimonial, Eletrônicos → Eletrônica) visíveis', async ({ page }) => {
    await page.goto('/modulos/empresas/migrador', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Humanizados').first()).toBeVisible();
    await expect(page.locator('text=Eletrônicos').first()).toBeVisible();
  });

  test('Seção Analisar Contrato Individual visível com botão Analisar', async ({ page }) => {
    await page.goto('/modulos/empresas/migrador', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Analisar Contrato Individual').first()).toBeVisible();
    await expect(page.locator('button', { hasText: 'Analisar' }).first()).toBeVisible();
  });

  test('Seção Analisar em Lote visível com botão Analisar Lote', async ({ page }) => {
    await page.goto('/modulos/empresas/migrador', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Analisar em Lote').first()).toBeVisible();
    await expect(page.locator('button', { hasText: 'Analisar Lote' }).first()).toBeVisible();
  });

  test('Seção Guia de Migração visível com etapas', async ({ page }) => {
    await page.goto('/modulos/empresas/migrador', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Guia de Migração').first()).toBeVisible();
    await expect(page.locator('text=Classificar Serviço').first()).toBeVisible();
    await expect(page.locator('text=Gerar Aditivo').first()).toBeVisible();
  });

  test('Link Voltar para Multi-Empresa funciona', async ({ page }) => {
    await page.goto('/modulos/empresas/migrador', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });
    await page.locator('text=Voltar para Multi-Empresa').click();
    await page.waitForURL('**/empresas', { timeout: 10000 });
  });

  test('Analisar contrato individual — resultado com badge deve_migrar', async ({ page }) => {
    // Mock da API para retornar resultado sem precisar de auth real
    await page.route('**/api/v1/empresas/migrador/analisar', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          contrato_id: 1,
          tipo_servico: 'vigilancia',
          empresa_atual: 'conecta_eletronica',
          empresa_destino: 'conecta_patrimonial',
          deve_migrar: true,
          motivo: 'Serviço humanizado deve migrar para Patrimonial (Simples Nacional)',
          economia_anual_estimada: 15000,
          pendencias: [],
          impacto_financeiro: {
            imposto_atual_mes: 8000,
            imposto_destino_mes: 5000,
            economia_mensal: 3000,
            economia_anual: 36000,
          },
        }),
      });
    });

    await page.goto('/modulos/empresas/migrador', { waitUntil: 'load' });
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });

    // Selecionar tipo de serviço vigilância (já vem selecionado por padrão)
    await page.locator('button', { hasText: 'Analisar' }).first().click();
    await page.waitForTimeout(1500);

    // Deve mostrar resultado com empresa destino
    await expect(
      page.locator('text=Recomendado Migrar').or(page.locator('text=Sem migração necessária'))
    ).toBeVisible({ timeout: 8000 });
  });
});
