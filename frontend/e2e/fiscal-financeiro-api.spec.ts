import { test, expect } from '@playwright/test';
import { SENHA, USUARIO } from './_credenciais';

/**
 * E2E Tests — API Fiscal + Financeiro (Task 1.2 + 2.2)
 *
 * Valida os endpoints que foram modificados para usar dados reais:
 *
 * FISCAL (Multi-Empresa Dashboard):
 *  1. GET /api/v1/empresas/dashboard/fiscal/grupo
 *  2. GET /api/v1/empresas/dashboard/rentabilidade/grupo
 *  3. GET /api/v1/empresas/dashboard/contabil/grupo
 *  4. GET /api/v1/empresas/ (listar empresas)
 *  5. GET /api/v1/empresas/sugerir/{tipo}
 *
 * FINANCEIRO (Custos com dados reais):
 *  6. GET /api/v1/financial/ai/costing/summary
 *  7. GET /api/v1/financial/ai/costing/by-type
 *  8. GET /api/v1/financial/ai/costing/margin-by-type
 *  9. POST /api/v1/financial/ai/costing/registrar
 *
 * FISCAL (Calculadoras):
 * 10. POST /api/v1/financial/fiscal/calcular/simples
 * 11. POST /api/v1/financial/fiscal/calcular/lucro-real
 * 12. POST /api/v1/financial/fiscal/calcular/comparativo-regimes
 */

const API = 'http://localhost:8080';

let token: string;

test.beforeAll(async ({ request }) => {
  const loginRes = await request.post(`${API}/api/v1/auth/login`, {
    form: {
      username: USUARIO,
      password: SENHA,
    },
  });
  expect(loginRes.ok()).toBeTruthy();
  const body = await loginRes.json();
  token = body.access_token;
  expect(token).toBeTruthy();
});

function headers() {
  return { Authorization: `Bearer ${token}` };
}

// ─────────────────────────────────────────────────────────────
// FISCAL — Dashboard Multi-Empresa (dados reais)
// ─────────────────────────────────────────────────────────────

test.describe('Fiscal — Dashboard Multi-Empresa', () => {
  test('GET /dashboard/fiscal/grupo deve retornar dados reais ou sem_receita', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/empresas/dashboard/fiscal/grupo`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('periodo');
    expect(data).toHaveProperty('grupo');
    expect(data).toHaveProperty('empresas');
    // Status deve ser "com_dados", "sem_receita" ou "sem_dados" — NUNCA hardcoded
    expect(['com_dados', 'sem_receita', 'sem_dados']).toContain(data.status);
    // Deve ter as 2 empresas reais
    if (data.empresas) {
      expect(data.empresas).toHaveProperty('conecta_eletronica');
      expect(data.empresas).toHaveProperty('conecta_patrimonial');
    }
  });

  test('GET /dashboard/fiscal/grupo com mes/ano custom', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/empresas/dashboard/fiscal/grupo?mes=1&ano=2026`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data.periodo).toBe('01/2026');
  });

  test('GET /dashboard/rentabilidade/grupo deve retornar dados ou sem_dados', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/empresas/dashboard/rentabilidade/grupo`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(['com_dados', 'sem_dados']).toContain(data.status);
    if (data.status === 'sem_dados') {
      expect(data).toHaveProperty('mensagem');
      expect(data.resumo_grupo.total_receita_mes).toBe(0);
    }
  });

  test('GET /dashboard/contabil/grupo deve retornar dados ou sem_dados', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/empresas/dashboard/contabil/grupo`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('periodo');
    expect(['com_dados', 'sem_dados']).toContain(data.status);
    expect(data).toHaveProperty('grupo_consolidado');
    expect(data).toHaveProperty('por_empresa');
    expect(data).toHaveProperty('exportacao_contador');
    // Exportação para Domínio deve estar presente
    expect(data.exportacao_contador.formato).toContain('Dominio');
  });

  test('GET /dashboard/contabil/grupo por_empresa deve listar empresas reais', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/empresas/dashboard/contabil/grupo`, {
      headers: headers(),
    });
    const data = await res.json();
    if (data.por_empresa) {
      const slugs = Object.keys(data.por_empresa);
      expect(slugs).toContain('conecta_eletronica');
      expect(data.por_empresa.conecta_eletronica.regime).toBe('lucro_real');
    }
  });
});

// ─────────────────────────────────────────────────────────────
// FISCAL — Empresas CRUD
// ─────────────────────────────────────────────────────────────

test.describe('Fiscal — Empresas API', () => {
  test('GET /empresas/ deve listar as 2 empresas', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/empresas/`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(Array.isArray(data)).toBeTruthy();
    expect(data.length).toBe(2);

    const slugs = data.map((e: any) => e.slug);
    expect(slugs).toContain('conecta_eletronica');
    expect(slugs).toContain('conecta_patrimonial');
  });

  test('GET /empresas/ conecta_eletronica deve ser Lucro Real', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/empresas/`, { headers: headers() });
    const data = await res.json();
    const eletronica = data.find((e: any) => e.slug === 'conecta_eletronica');
    expect(eletronica.regime_tributario).toBe('lucro_real');
    expect(eletronica.status).toBe('ativa');
    expect(eletronica.is_principal).toBe(true);
  });

  test('GET /empresas/ conecta_patrimonial deve ser Simples Nacional', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/empresas/`, { headers: headers() });
    const data = await res.json();
    const patrimonial = data.find((e: any) => e.slug === 'conecta_patrimonial');
    expect(patrimonial.regime_tributario).toBe('simples_nacional');
    expect(patrimonial.status).toBe('em_abertura');
  });

  test('GET /empresas/sugerir/vigilancia deve sugerir patrimonial', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/empresas/sugerir/vigilancia`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data.slug).toBe('conecta_patrimonial');
  });

  test('GET /empresas/sugerir/portaria_remota deve sugerir eletronica', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/empresas/sugerir/portaria_remota`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data.slug).toBe('conecta_eletronica');
  });
});

// ─────────────────────────────────────────────────────────────
// FISCAL — Obrigações
// ─────────────────────────────────────────────────────────────

test.describe('Fiscal — Obrigações', () => {
  test('GET /obrigacoes/calendario/grupo deve retornar calendário', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/empresas/obrigacoes/calendario/grupo`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('resumo');
    expect(data.resumo).toHaveProperty('total');
  });

  test('GET /obrigacoes/alertas deve retornar alertas', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/empresas/obrigacoes/alertas`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
  });
});

// ─────────────────────────────────────────────────────────────
// FINANCEIRO — Custos (dados reais, sem benchmark fake)
// ─────────────────────────────────────────────────────────────

test.describe('Financeiro — Custos API (sem benchmark fake)', () => {
  test('GET /costing/summary deve retornar 5 tipos com fonte correta', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/financial/ai/costing/summary?mes=2026-03`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('resumo_por_tipo');
    expect(data.resumo_por_tipo.length).toBe(5);

    // Verificar que não há mais benchmarks fake — fonte deve ser "real" ou "sem_dados"
    for (const tipo of data.resumo_por_tipo) {
      expect(['real', 'sem_dados']).toContain(tipo.fonte);
      if (tipo.fonte === 'sem_dados') {
        expect(tipo.custo_total).toBe(0);
        expect(tipo.margem_pct).toBe(0);
      }
    }
  });

  test('GET /costing/by-type portaria deve retornar dados reais', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/financial/ai/costing/by-type?tipo=portaria&mes=2026-03`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data.tipo).toBe('portaria');
    expect(data.fonte).toBe('real');
    expect(data.custo_total).toBeGreaterThan(0);
    expect(data.breakdown).toBeTruthy();
    expect(Object.keys(data.breakdown).length).toBeGreaterThan(0);
  });

  test('GET /costing/by-type limpeza deve retornar sem_dados (sem fake)', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/financial/ai/costing/by-type?tipo=limpeza&mes=2026-03`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data.tipo).toBe('limpeza');
    expect(data.fonte).toBe('sem_dados');
    expect(data.custo_total).toBe(0);
    expect(data.margem_pct).toBe(0);
    // Deve ter referência de benchmark (informativa, não como dado real)
    expect(data).toHaveProperty('benchmark_referencia');
    expect(data.benchmark_referencia.custo_base).toBeGreaterThan(0);
  });

  test('GET /costing/by-type sem_dados deve ter aviso orientativo', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/financial/ai/costing/by-type?tipo=jardinagem&mes=2026-03`, {
      headers: headers(),
    });
    const data = await res.json();
    expect(data.fonte).toBe('sem_dados');
    expect(data.aviso).toContain('Registrar Custo');
  });

  test('GET /costing/margin-by-type deve retornar margens', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/financial/ai/costing/margin-by-type`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(Array.isArray(data)).toBeTruthy();
  });

  test('GET /costing/summary total_custo deve refletir dados reais', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/financial/ai/costing/summary?mes=2026-03`, {
      headers: headers(),
    });
    const data = await res.json();
    // total_custo deve ser soma dos custos reais (portaria = 9200, resto = 0)
    const portaria = data.resumo_por_tipo.find((t: any) => t.tipo === 'portaria');
    if (portaria && portaria.fonte === 'real') {
      expect(data.total_custo).toBe(portaria.custo_total);
    }
  });
});

// ─────────────────────────────────────────────────────────────
// FISCAL — Calculadoras de impostos
// ─────────────────────────────────────────────────────────────

test.describe('Fiscal — Calculadoras', () => {
  test('POST /calcular/simples deve calcular DAS', async ({ request }) => {
    const res = await request.post(`${API}/api/v1/financial/fiscal/calcular/simples`, {
      headers: headers(),
      data: {
        receita_mes: 150000,
        rbt12: 1800000,
        liminares: [],
      },
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('valor_das');
    expect(data.valor_das).toBeGreaterThan(0);
  });

  test('POST /calcular/lucro-real deve calcular IRPJ/CSLL/PIS/COFINS', async ({ request }) => {
    const res = await request.post(`${API}/api/v1/financial/fiscal/calcular/lucro-real`, {
      headers: headers(),
      data: {
        receita_mes: 200000,
        receita_trimestre: 600000,
      },
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('total_impostos_mes');
    expect(data.total_impostos_mes).toBeGreaterThan(0);
  });

  test('POST /calcular/comparativo-regimes deve comparar', async ({ request }) => {
    const res = await request.post(`${API}/api/v1/financial/fiscal/calcular/comparativo-regimes`, {
      headers: headers(),
      data: {
        receita_mes: 150000,
        rbt12: 1800000,
        receita_anual: 1800000,
      },
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('simples_nacional');
    expect(data).toHaveProperty('lucro_real');
    expect(data).toHaveProperty('economia_simples_anual');
  });

  test('POST /calcular/simples com liminares deve retornar DAS válido', async ({ request }) => {
    const com = await request.post(`${API}/api/v1/financial/fiscal/calcular/simples`, {
      headers: headers(),
      data: { receita_mes: 150000, rbt12: 1800000, liminares: ['pis_cofins'] },
    });
    expect(com.ok()).toBeTruthy();
    const dCom = await com.json();
    expect(dCom).toHaveProperty('valor_das');
    expect(dCom.valor_das).toBeGreaterThan(0);
  });
});

// ─────────────────────────────────────────────────────────────
// FINANCEIRO — Financial AI Command Center
// ─────────────────────────────────────────────────────────────

test.describe('Financeiro — AI Command Center', () => {
  test('GET /financial/ai/command-center deve retornar dashboard', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/financial/ai/command-center`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(typeof data).toBe('object');
  });

  test('GET /financial/ai/advisor/health deve retornar saúde financeira', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/financial/ai/advisor/health`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
  });
});
