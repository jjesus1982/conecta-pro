/**
 * Portal do Cliente — cliente HTTP compartilhado.
 * Centraliza base URL, token (localStorage), e tratamento de 401 (desloga + redireciona).
 * Substitui os ~8 getPortalHeaders/fetch copiados pelas páginas.
 */
const API_BASE = (process.env.NEXT_PUBLIC_API_URL || '') + '/api/v1/portal';

export function getPortalToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('portal_token');
}

export class PortalAuthError extends Error {}

export async function portalFetch<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getPortalToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers || {}),
    },
  });
  if (res.status === 401) {
    // sessão expirada/invalidada → limpa e manda pro login
    if (typeof window !== 'undefined') {
      localStorage.removeItem('portal_token');
      localStorage.removeItem('portal_client_name');
      localStorage.removeItem('portal_client_id');
      window.location.href = '/area-cliente/login';
    }
    throw new PortalAuthError('Sessão expirada');
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

// ── Raio-X da Operação ────────────────────────────────────────────────────────
export interface OperacaoResumo {
  condominio: string; equipe_total: number; asos_vencidos: number; turnover_pct: number;
  assiduidade_local_pct: number; admissoes_12m: number; demissoes_12m: number;
}
export interface Funcionario { id: string; nome: string; funcao: string; cargo: string; admissao: string | null; tempo_casa_meses: number | null; status: string }
export interface RankingItem { posicao: number; nome: string; score: number; dias_presentes: number; pct_no_local: number; pct_facial_ok: number }
export interface Aso { funcionario: string; tipo: string; status: string; realizado: string | null; validade: string | null; apto: boolean; vencido: boolean }
export interface Movimentacao { nome: string; cargo: string; admissao: string | null; demissao: string | null; status: string }

export const operacao = {
  resumo: () => portalFetch<OperacaoResumo>('/operacao/resumo'),
  equipe: () => portalFetch<{ condominio: string; total: number; equipe: Funcionario[] }>('/operacao/equipe'),
  ranking: () => portalFetch<{ condominio: string; ranking: RankingItem[]; criterio: string }>('/operacao/ranking'),
  assiduidade: () => portalFetch<{ resumo: Record<string, number>; funcionarios: RankingItem[] }>('/operacao/assiduidade'),
  atestados: () => portalFetch<{ asos: Aso[]; resumo: { total: number; vencidos: number } }>('/operacao/atestados'),
  turnover: () => portalFetch<{ resumo: Record<string, number>; movimentacoes: Movimentacao[] }>('/operacao/turnover'),
  advertencias: () => portalFetch<{ advertencias: unknown[]; total: number }>('/operacao/advertencias'),
  escalas: () => portalFetch<{ tem_escala: boolean; turnos: unknown[]; padrao: unknown[] }>('/operacao/escalas'),
};
