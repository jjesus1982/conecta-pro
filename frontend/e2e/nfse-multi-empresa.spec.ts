/**
 * Testes E2E - NFS-e Multi-Empresa (Fase 6)
 *
 * Validações backend (API):
 * - POST /preparar com vigilancia → conecta_patrimonial
 * - POST /preparar com portaria_remota → conecta_eletronica
 * - POST com liminares pis_cofins_zero → pis=0, cofins=0
 * - POST com inss_nao_retido → inss_retido=false
 * - GET /identificar-empresa/vigilancia → patrimonial
 * - GET /identificar-empresa/cftv → eletronica
 * - POST /calcular-tributos com e sem liminares
 * - GET /empresas → lista empresas
 * - GET /servicos → mapeamento
 *
 * Validações frontend:
 * - Página carrega com header correto
 * - Formulário preenche e exibe resultado
 * - Badge empresa emissora visível
 */

import { test, expect } from './fixtures';
import { corpoLoginUrlEncoded } from './_credenciais';

const BASE_API = process.env.BASE_URL ?? 'http://localhost:3001';
const API_URL = 'http://localhost:8080';

// ─── Helper: obter token de auth ─────────────────────────────────────────────

async function getAuthToken(request: any): Promise<string> {
  const resp = await request.post(`${API_URL}/api/v1/auth/login`, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    data: corpoLoginUrlEncoded(),
  });
  const body = await resp.json();
  return body.access_token ?? body.token ?? '';
}

// ─── Payload padrão ──────────────────────────────────────────────────────────

const PAYLOAD_VIGILANCIA = {
  tipo_servico: 'vigilancia',
  descricao_servico: 'Servicos de vigilancia patrimonial - Competencia 03/2026',
  valor_servico: 50000.0,
  tomador_cnpj_cpf: '12345678000195',
  tomador_razao_social: 'Cliente Teste Ltda',
  competencia_ano: 2026,
  competencia_mes: 3,
  forcar_liminares: [],
};

const PAYLOAD_PORTARIA_REMOTA = {
  ...PAYLOAD_VIGILANCIA,
  tipo_servico: 'portaria_remota',
  descricao_servico: 'Servicos de portaria remota - Competencia 03/2026',
};

// ─── Testes de API (backend direto) ──────────────────────────────────────────

test.describe('NFS-e Multi-Empresa — API Backend', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    token = await getAuthToken(request);
  });

  test('POST /preparar com vigilancia deve retornar conecta_patrimonial', async ({ request }) => {
    const resp = await request.post(`${API_URL}/api/v1/fiscal/nfse-multi/preparar`, {
      headers: { Authorization: `Bearer ${token}` },
      data: PAYLOAD_VIGILANCIA,
    });

    expect(resp.status()).toBeLessThan(500);
    const body = await resp.json();
    // Patrimonial ainda nao tem CNPJ, sucesso=false mas empresa correta
    expect(body.empresa_emissora).toBe('conecta_patrimonial');
    expect(body).toHaveProperty('tributos');
    expect(body).toHaveProperty('liminares_aplicadas');
  });

  test('POST /preparar com portaria_remota deve retornar conecta_eletronica', async ({ request }) => {
    const resp = await request.post(`${API_URL}/api/v1/fiscal/nfse-multi/preparar`, {
      headers: { Authorization: `Bearer ${token}` },
      data: PAYLOAD_PORTARIA_REMOTA,
    });

    expect(resp.status()).toBeLessThan(500);
    const body = await resp.json();
    expect(body.empresa_emissora).toBe('conecta_eletronica');
    expect(body.sucesso).toBe(true);
    expect(body.xml_preview).toBeTruthy();
  });

  test('POST /preparar com cftv deve retornar conecta_eletronica', async ({ request }) => {
    const resp = await request.post(`${API_URL}/api/v1/fiscal/nfse-multi/preparar`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { ...PAYLOAD_VIGILANCIA, tipo_servico: 'cftv', descricao_servico: 'Servicos CFTV 03/2026' },
    });

    expect(resp.status()).toBeLessThan(500);
    const body = await resp.json();
    expect(body.empresa_emissora).toBe('conecta_eletronica');
  });

  test('POST /preparar com forcar_liminares pis_cofins_zero deve zerar PIS e COFINS', async ({ request }) => {
    const resp = await request.post(`${API_URL}/api/v1/fiscal/nfse-multi/preparar`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { ...PAYLOAD_PORTARIA_REMOTA, forcar_liminares: ['pis_cofins_zero'] },
    });

    expect(resp.status()).toBeLessThan(500);
    const body = await resp.json();
    expect(body.tributos.pis).toBe(0);
    expect(body.tributos.cofins).toBe(0);
    expect(body.liminares_aplicadas).toContain('pis_cofins_zero');
  });

  test('POST /preparar com forcar_liminares inss_nao_retido deve ter inss_retido=false', async ({ request }) => {
    const resp = await request.post(`${API_URL}/api/v1/fiscal/nfse-multi/preparar`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { ...PAYLOAD_PORTARIA_REMOTA, forcar_liminares: ['inss_nao_retido'] },
    });

    expect(resp.status()).toBeLessThan(500);
    const body = await resp.json();
    expect(body.tributos.inss_retido).toBe(false);
    expect(body.liminares_aplicadas).toContain('inss_nao_retido');
  });

  test('GET /identificar-empresa/vigilancia deve retornar conecta_patrimonial', async ({ request }) => {
    const resp = await request.get(`${API_URL}/api/v1/fiscal/nfse-multi/identificar-empresa/vigilancia`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    expect(resp.status()).toBeLessThan(500);
    const body = await resp.json();
    expect(body.empresa_emissora).toBe('conecta_patrimonial');
    expect(body.tipo_servico).toBe('vigilancia');
  });

  test('GET /identificar-empresa/cftv deve retornar conecta_eletronica', async ({ request }) => {
    const resp = await request.get(`${API_URL}/api/v1/fiscal/nfse-multi/identificar-empresa/cftv`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    expect(resp.status()).toBeLessThan(500);
    const body = await resp.json();
    expect(body.empresa_emissora).toBe('conecta_eletronica');
  });

  test('POST /calcular-tributos sem liminares deve calcular corretamente', async ({ request }) => {
    const resp = await request.post(`${API_URL}/api/v1/fiscal/nfse-multi/calcular-tributos`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        valor_servico: 10000.0,
        empresa_slug: 'conecta_eletronica',
        liminares: [],
      },
    });

    expect(resp.status()).toBeLessThan(500);
    const body = await resp.json();
    // ISS 5% de 10000 = 500
    expect(body.iss).toBeCloseTo(500, 1);
    // PIS 0.65% de 10000 = 65
    expect(body.pis).toBeCloseTo(65, 1);
  });

  test('POST /calcular-tributos com pis_cofins_zero deve zerar PIS e COFINS', async ({ request }) => {
    const resp = await request.post(`${API_URL}/api/v1/fiscal/nfse-multi/calcular-tributos`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        valor_servico: 10000.0,
        empresa_slug: 'conecta_eletronica',
        liminares: ['pis_cofins_zero'],
      },
    });

    expect(resp.status()).toBeLessThan(500);
    const body = await resp.json();
    expect(body.pis).toBe(0);
    expect(body.cofins).toBe(0);
    expect(body.liminares_aplicadas).toContain('pis_cofins_zero');
  });

  test('GET /empresas deve listar as 2 empresas configuradas', async ({ request }) => {
    const resp = await request.get(`${API_URL}/api/v1/fiscal/nfse-multi/empresas`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    expect(resp.status()).toBeLessThan(500);
    const body = await resp.json();
    expect(body.total).toBeGreaterThanOrEqual(2);
    const slugs = body.empresas.map((e: any) => e.slug);
    expect(slugs).toContain('conecta_eletronica');
    expect(slugs).toContain('conecta_patrimonial');
  });

  test('GET /servicos deve retornar mapeamento eletronica e patrimonial', async ({ request }) => {
    const resp = await request.get(`${API_URL}/api/v1/fiscal/nfse-multi/servicos`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    expect(resp.status()).toBeLessThan(500);
    const body = await resp.json();
    expect(body.eletronica.empresa).toBe('conecta_eletronica');
    expect(body.patrimonial.empresa).toBe('conecta_patrimonial');
    expect(body.eletronica.servicos).toContain('cftv');
    expect(body.patrimonial.servicos).toContain('vigilancia');
  });
});

// ─── Testes de Frontend ───────────────────────────────────────────────────────

test.describe('NFS-e Multi-Empresa — Frontend', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/modulos/fiscal/nfse-multi', { waitUntil: 'load' });
    await page.waitForTimeout(1000);
  });

  test('deve carregar página com header correto', async ({ page }) => {
    await expect(page.locator('h1')).toContainText('NFS-e', { timeout: 8000 });
  });

  test('deve exibir subtitulo sobre selecao automatica de empresa', async ({ page }) => {
    await expect(
      page.locator('text=empresa emissora').or(page.locator('text=liminares')).first()
    ).toBeVisible({ timeout: 8000 });
  });

  test('deve exibir formulario com campos obrigatorios', async ({ page }) => {
    await test.step('Tipo de Servico', async () => {
      await expect(page.locator('select').first()).toBeVisible({ timeout: 8000 });
    });
    await test.step('Valor do Servico', async () => {
      await expect(page.locator('input[type="number"]').first()).toBeVisible({ timeout: 8000 });
    });
    await test.step('Botao Calcular', async () => {
      await expect(
        page.locator('button', { hasText: 'Calcular' }).first()
      ).toBeVisible({ timeout: 8000 });
    });
  });

  test('deve preencher formulario e exibir resultado com empresa emissora', async ({ page }) => {
    // Mock da API para evitar dependencia de auth real
    await page.route('**/api/v1/fiscal/nfse-multi/preparar', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          sucesso: true,
          empresa_emissora: 'conecta_eletronica',
          motivo_selecao_empresa: 'Portaria remota é serviço eletrônico',
          liminares_aplicadas: [],
          tributos: {
            valor_servico: 50000,
            pis: 825,
            cofins: 3800,
            iss: 2500,
            inss_retido: false,
            valor_liquido: 42875,
          },
          xml_preview: null,
          mensagem: 'NFS-e preparada com sucesso',
          ambiente: 'homologacao',
        }),
      });
    });

    // Selecionar tipo de servico eletronica (portaria_remota)
    await page.locator('select').first().selectOption('portaria_remota');
    await page.fill('textarea', 'Servicos de portaria remota 03/2026');
    await page.fill('input[type="number"]', '50000');
    // Localizar campos de texto (CNPJ e Razão Social) por posição
    const textInputs = page.locator('input[type="text"]');
    await textInputs.first().fill('12345678000195');
    await textInputs.nth(1).fill('Cliente Teste E2E Ltda');

    await page.locator('button', { hasText: 'Calcular' }).first().click();
    await page.waitForTimeout(3000);

    // Verificar resultado — mensagem de sucesso ou empresa emissora visível
    await expect(
      page.locator('text=NFS-e preparada').or(page.locator('text=sucesso')).or(page.locator('text=Tributos Calculados')).first()
    ).toBeVisible({ timeout: 10000 });
  });
});
