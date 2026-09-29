import { test, expect } from '@playwright/test';
import { SENHA, USUARIO } from '../_credenciais';

/**
 * E2E Tests — 12 Agentes IA Operacional (API endpoints)
 *
 * Valida que todos os endpoints dos agentes de IA respondem corretamente,
 * mesmo quando o banco está vazio (sistema construído do zero).
 *
 * Endpoints testados:
 *  1. GET  /api/v1/operacional/ai/command-center
 *  2. GET  /api/v1/operacional/ai/coverage-prediction
 *  3. GET  /api/v1/operacional/ai/performance-overview
 *  4. GET  /api/v1/operacional/ai/absence-risks
 *  5. GET  /api/v1/operacional/ai/field-monitor
 *  6. POST /api/v1/operacional/ai/incident/classify
 *  7. GET  /api/v1/operacional/ai/cost/forecast
 *  8. POST /api/v1/operacional/ai/maintenance/expire-time-bank
 *  9. POST /api/v1/operacional/ai/scale/optimize
 * 10. POST /api/v1/operacional/ai/substitute/find
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
// 1. AI Command Center (Hub consolidado)
// ─────────────────────────────────────────────────────────────

test.describe('1. AI Command Center Hub', () => {
  test('GET /command-center deve retornar status e overview', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/operacional/ai/command-center`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('status');
    expect(data).toHaveProperty('overview');
  });

  test('deve responder mesmo sem autenticação (endpoints públicos)', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/operacional/ai/command-center`);
    // Os endpoints AI são acessíveis sem token (design decision)
    expect(res.ok()).toBeTruthy();
  });
});

// ─────────────────────────────────────────────────────────────
// 2. CoveragePredictorAgent
// ─────────────────────────────────────────────────────────────

test.describe('2. CoveragePredictorAgent', () => {
  test('GET /coverage-prediction deve retornar previsão', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/operacional/ai/coverage-prediction`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    // Deve ter estrutura de previsão (pode estar vazio se sem dados)
    expect(typeof data).toBe('object');
  });

  test('GET /coverage-prediction com target_date', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/operacional/ai/coverage-prediction?target_date=2026-03-15`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(typeof data).toBe('object');
  });
});

// ─────────────────────────────────────────────────────────────
// 3. PerformanceAnalyzerAgent
// ─────────────────────────────────────────────────────────────

test.describe('3. PerformanceAnalyzerAgent', () => {
  test('GET /performance-overview deve retornar scores', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/operacional/ai/performance-overview`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(typeof data).toBe('object');
  });

  test('GET /performance-overview com period_days=30', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/operacional/ai/performance-overview?period_days=30`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
  });
});

// ─────────────────────────────────────────────────────────────
// 4. AnomalyDetectorAgent
// ─────────────────────────────────────────────────────────────

test.describe('4. AnomalyDetectorAgent', () => {
  test('GET /absence-risks deve retornar riscos', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/operacional/ai/absence-risks`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(typeof data).toBe('object');
  });
});

// ─────────────────────────────────────────────────────────────
// 5. FieldMonitorAgent
// ─────────────────────────────────────────────────────────────

test.describe('5. FieldMonitorAgent', () => {
  test('GET /field-monitor deve retornar dashboard', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/operacional/ai/field-monitor`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(typeof data).toBe('object');
  });
});

// ─────────────────────────────────────────────────────────────
// 6. IncidentClassifierAgent
// ─────────────────────────────────────────────────────────────

test.describe('6. IncidentClassifierAgent', () => {
  test('POST /incident/classify deve classificar ocorrência', async ({ request }) => {
    const res = await request.post(`${API}/api/v1/operacional/ai/incident/classify`, {
      headers: headers(),
      data: {
        description: 'Vigilante abandonou posto às 23h sem aviso prévio',
      },
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('category');
    expect(data).toHaveProperty('severity');
    expect(data).toHaveProperty('confidence');
  });

  test('POST /incident/classify com descrição curta', async ({ request }) => {
    const res = await request.post(`${API}/api/v1/operacional/ai/incident/classify`, {
      headers: headers(),
      data: {
        description: 'furto no estacionamento',
      },
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('category');
  });

  test('POST /incident/classify com descrição de equipamento', async ({ request }) => {
    const res = await request.post(`${API}/api/v1/operacional/ai/incident/classify`, {
      headers: headers(),
      data: {
        description: 'Câmera do setor B parou de funcionar, sem imagem há 2 horas',
      },
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('category');
  });
});

// ─────────────────────────────────────────────────────────────
// 9. CostPredictorAgent
// ─────────────────────────────────────────────────────────────

test.describe('9. CostPredictorAgent', () => {
  test('GET /cost/forecast deve retornar previsão de custos', async ({ request }) => {
    const res = await request.get(`${API}/api/v1/operacional/ai/cost/forecast`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(typeof data).toBe('object');
  });
});

// ─────────────────────────────────────────────────────────────
// 10. Time Bank Maintenance
// ─────────────────────────────────────────────────────────────

test.describe('10. Time Bank Maintenance', () => {
  test('POST /maintenance/expire-time-bank deve processar', async ({ request }) => {
    const res = await request.post(`${API}/api/v1/operacional/ai/maintenance/expire-time-bank`, {
      headers: headers(),
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('expired_count');
    expect(data).toHaveProperty('processed_at');
  });
});

// ─────────────────────────────────────────────────────────────
// 11. ScaleOptimizerAgent
// ─────────────────────────────────────────────────────────────

test.describe('11. ScaleOptimizerAgent', () => {
  test('POST /scale/optimize deve otimizar escala', async ({ request }) => {
    const res = await request.post(`${API}/api/v1/operacional/ai/scale/optimize`, {
      headers: headers(),
      data: {
        slots_count: 5,
        employees_count: 8,
        max_consecutive_days: 6,
        max_weekly_hours: 44.0,
        balance_weekend_shifts: true,
      },
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('success');
    expect(data).toHaveProperty('coverage_percentage');
    expect(data).toHaveProperty('estimated_cost');
  });

  test('POST /scale/optimize com escala mínima', async ({ request }) => {
    const res = await request.post(`${API}/api/v1/operacional/ai/scale/optimize`, {
      headers: headers(),
      data: {
        slots_count: 1,
        employees_count: 2,
        max_consecutive_days: 6,
        max_weekly_hours: 44.0,
        balance_weekend_shifts: false,
      },
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data.success).toBe(true);
  });

  test('POST /scale/optimize com escala grande', async ({ request }) => {
    const res = await request.post(`${API}/api/v1/operacional/ai/scale/optimize`, {
      headers: headers(),
      data: {
        slots_count: 20,
        employees_count: 30,
        max_consecutive_days: 5,
        max_weekly_hours: 40.0,
        balance_weekend_shifts: true,
      },
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('success');
  });
});

// ─────────────────────────────────────────────────────────────
// 12. SubstitutionOptimizerAgent
// ─────────────────────────────────────────────────────────────

test.describe('12. SubstitutionOptimizerAgent', () => {
  test('POST /substitute/find deve buscar substitutos', async ({ request }) => {
    const res = await request.post(`${API}/api/v1/operacional/ai/substitute/find`, {
      headers: headers(),
      data: {
        shift_id: '00000000-0000-0000-0000-000000000001',
        post_lat: -3.1019,
        post_lon: -60.025,
        urgency: 'normal',
        max_results: 5,
      },
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('shift_id');
    expect(data).toHaveProperty('urgency');
    expect(data).toHaveProperty('suggestions');
    expect(Array.isArray(data.suggestions)).toBeTruthy();
  });

  test('POST /substitute/find com urgência alta', async ({ request }) => {
    const res = await request.post(`${API}/api/v1/operacional/ai/substitute/find`, {
      headers: headers(),
      data: {
        shift_id: '00000000-0000-0000-0000-000000000002',
        post_lat: -3.1190,
        post_lon: -60.0217,
        urgency: 'urgent',
        max_results: 3,
      },
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data.urgency).toBe('urgent');
  });
});

// ─────────────────────────────────────────────────────────────
// Cross-cutting: Todos os GET endpoints são acessíveis
// ─────────────────────────────────────────────────────────────

test.describe('Acessibilidade — Todos os GET endpoints respondem', () => {
  const endpoints = [
    '/api/v1/operacional/ai/command-center',
    '/api/v1/operacional/ai/coverage-prediction',
    '/api/v1/operacional/ai/performance-overview',
    '/api/v1/operacional/ai/absence-risks',
    '/api/v1/operacional/ai/field-monitor',
    '/api/v1/operacional/ai/cost/forecast',
  ];

  for (const path of endpoints) {
    test(`GET ${path} deve retornar 200`, async ({ request }) => {
      const res = await request.get(`${API}${path}`, { headers: headers() });
      expect(res.ok()).toBeTruthy();
      const data = await res.json();
      expect(typeof data).toBe('object');
    });
  }
});
