/**
 * Testes E2E — Relatório Executivo IA (Phase 5)
 *
 * Validações:
 * - Endpoint backend GET /api/v1/financial/ai/advisor/relatorio retorna dados válidos
 * - Página de Relatórios carrega com a nova tab "Relatório Executivo IA"
 * - Geração do relatório funciona após seleção de período
 * - KPIs, destaques, pontos de atenção e recomendações são exibidos
 */

import { test, expect } from '@playwright/test';
import { corpoLoginUrlEncoded } from './_credenciais';

test.describe('Backend — Relatório Executivo IA', () => {
  test.use({ storageState: 'e2e/.auth/user.json' });

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

  test('GET /ai/advisor/relatorio retorna estrutura completa', async ({ request }) => {
    const resp = await request.get('http://localhost:8080/api/v1/financial/ai/advisor/relatorio', {
      headers: { Authorization: `Bearer ${sharedToken}` },
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();

    // Estrutura raiz
    expect(data).toHaveProperty('periodo');
    expect(data).toHaveProperty('titulo');
    expect(data).toHaveProperty('gerado_em');
    expect(data).toHaveProperty('sumario_executivo');
    expect(data).toHaveProperty('score_saude');
    expect(data).toHaveProperty('classificacao');
    expect(data).toHaveProperty('kpis');
    expect(data).toHaveProperty('comparativo');
    expect(data).toHaveProperty('destaques');
    expect(data).toHaveProperty('pontos_atencao');
    expect(data).toHaveProperty('recomendacoes_prioritarias');

    // KPIs obrigatórios
    expect(data.kpis).toHaveProperty('receita_realizada');
    expect(data.kpis).toHaveProperty('despesas');
    expect(data.kpis).toHaveProperty('saldo_liquido');
    expect(data.kpis).toHaveProperty('margem_pct');
    expect(data.kpis).toHaveProperty('inadimplencia_pct');
    expect(data.kpis).toHaveProperty('qtd_inadimplentes');

    // Comparativo
    expect(data.comparativo).toHaveProperty('receita_anterior');
    expect(data.comparativo).toHaveProperty('variacao_receita_pct');
    expect(data.comparativo).toHaveProperty('variacao_margem_pct');

    // Tipos
    expect(typeof data.score_saude).toBe('number');
    expect(data.score_saude).toBeGreaterThanOrEqual(0);
    expect(data.score_saude).toBeLessThanOrEqual(100);
    expect(typeof data.sumario_executivo).toBe('string');
    expect(data.sumario_executivo.length).toBeGreaterThan(10);
    expect(Array.isArray(data.destaques)).toBeTruthy();
    expect(Array.isArray(data.pontos_atencao)).toBeTruthy();
    expect(Array.isArray(data.recomendacoes_prioritarias)).toBeTruthy();
  });

  test('GET /ai/advisor/relatorio aceita query param periodo', async ({ request }) => {
    const resp = await request.get(
      'http://localhost:8080/api/v1/financial/ai/advisor/relatorio?periodo=2026-01',
      { headers: { Authorization: `Bearer ${sharedToken}` } }
    );
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.periodo).toBe('2026-01');
    expect(data.titulo).toContain('2026');
  });

  test('GET /ai/advisor/relatorio retorna pontos_atencao com estrutura correta', async ({ request }) => {
    const resp = await request.get('http://localhost:8080/api/v1/financial/ai/advisor/relatorio', {
      headers: { Authorization: `Bearer ${sharedToken}` },
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();

    // Pontos de atenção têm estrutura com icone, nivel, titulo, descricao, acao
    if (data.pontos_atencao.length > 0) {
      const ponto = data.pontos_atencao[0];
      expect(ponto).toHaveProperty('icone');
      expect(ponto).toHaveProperty('nivel');
      expect(ponto).toHaveProperty('titulo');
      expect(ponto).toHaveProperty('descricao');
      expect(ponto).toHaveProperty('acao');
    }
  });

  test('GET /ai/advisor/relatorio recomendacoes_prioritarias têm estrutura correta', async ({ request }) => {
    const resp = await request.get('http://localhost:8080/api/v1/financial/ai/advisor/relatorio', {
      headers: { Authorization: `Bearer ${sharedToken}` },
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();

    if (data.recomendacoes_prioritarias.length > 0) {
      const rec = data.recomendacoes_prioritarias[0];
      expect(rec).toHaveProperty('prioridade');
      expect(rec).toHaveProperty('titulo');
      expect(rec).toHaveProperty('descricao');
      expect(rec).toHaveProperty('acao');
    }
  });
});

test.describe('Frontend — Página de Relatórios com Aba Executivo IA', () => {
  test.use({ storageState: 'e2e/.auth/user.json' });

  test('página de relatórios carrega com a aba Relatório Executivo IA', async ({ page }) => {
    await page.goto('/modulos/financeiro/relatorios', { waitUntil: 'load' });
    await expect(page.getByRole('tab', { name: /relatório executivo ia/i })).toBeVisible({ timeout: 8000 });
  });

  test('aba Relatório Executivo IA exibe botão de geração e seletor de período', async ({ page }) => {
    await page.goto('/modulos/financeiro/relatorios', { waitUntil: 'load' });
    await page.getByRole('tab', { name: /relatório executivo ia/i }).click();

    await expect(page.getByRole('button', { name: /gerar relatório/i })).toBeVisible({ timeout: 5000 });
    await expect(page.locator('input[type="month"]')).toBeVisible();
  });

  test('gerar relatório exibe KPIs e sumário executivo', async ({ page }) => {
    await page.goto('/modulos/financeiro/relatorios', { waitUntil: 'load' });
    await page.getByRole('tab', { name: /relatório executivo ia/i }).click();

    // Clica no botão de gerar
    await page.getByRole('button', { name: /gerar relatório/i }).click();

    // Aguarda o relatório carregar (pode demorar por chamada à API)
    await expect(page.getByText(/relatório executivo financeiro/i)).toBeVisible({ timeout: 15000 });

    // Verifica que o score de saúde aparece (badge com score/100)
    await expect(page.locator('text=/\\d+\\/100/').first()).toBeVisible({ timeout: 5000 });
  });

  test('relatório gerado exibe seção de pontos de atenção', async ({ page }) => {
    await page.goto('/modulos/financeiro/relatorios', { waitUntil: 'load' });
    await page.getByRole('tab', { name: /relatório executivo ia/i }).click();

    await page.getByRole('button', { name: /gerar relatório/i }).click();
    await page.waitForTimeout(5000);

    // Pontos de atenção devem estar visíveis
    await expect(page.getByText(/pontos de atenção/i)).toBeVisible({ timeout: 10000 });
  });

  test('relatório gerado exibe recomendações prioritárias', async ({ page }) => {
    await page.goto('/modulos/financeiro/relatorios', { waitUntil: 'load' });
    await page.getByRole('tab', { name: /relatório executivo ia/i }).click();

    await page.getByRole('button', { name: /gerar relatório/i }).click();
    await page.waitForTimeout(5000);

    // Recomendações devem aparecer
    await expect(page.getByText(/recomendações prioritárias/i)).toBeVisible({ timeout: 10000 });
  });
});
