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

// ── Avisos (notificações proativas) ──────────────────────────────────────────
export interface Aviso { id: string; tipo: string; titulo: string; mensagem: string; link: string | null; lida: boolean; criado_em: string | null }

export const avisos = {
  listar: (apenasNaoLidas = false) => portalFetch<{ avisos: Aviso[] }>(`/avisos${apenasNaoLidas ? '?apenas_nao_lidas=true' : ''}`),
  naoLidas: () => portalFetch<{ nao_lidas: number }>('/avisos/nao-lidas'),
  marcarLida: (id: string) => portalFetch(`/avisos/${id}/lida`, { method: 'POST' }),
};

// ── Financeiro ────────────────────────────────────────────────────────────────
export interface NotaFiscal { numero: string; emissao: string | null; competencia: string | null; valor: number; status: string; link: string | null; descricao: string }
export interface Contrato { numero: string; status: string; valor_mensal: number; valor_total: number | null; assinado: boolean; renovacao_meses: number | null }
export interface Boleto { numero: string; valor: number; vencimento: string | null; status: string }

export const financeiro = {
  resumo: () => portalFetch<{ notas_total: number; faturado_total: number; contrato_mensal: number; contrato_ativo: boolean }>('/financeiro/resumo'),
  notas: () => portalFetch<{ notas: NotaFiscal[]; total: number; valor_total: number }>('/financeiro/notas'),
  contrato: () => portalFetch<{ contrato: Contrato | null }>('/financeiro/contrato'),
  boletos: () => portalFetch<{ boletos: Boleto[]; total: number }>('/financeiro/boletos'),
};

// ── Visitas da gestão (rondas de supervisão) ─────────────────────────────────
export interface VisitaAtividade { tipo: string; tipo_label: string; hora: string | null }
export interface VisitaFoto { checkpoint_id: string; arquivo: string; url: string }
export interface Visita {
  round_id: string;
  status: string;
  responsavel: string;
  duracao_minutos: number | null;
  checkin: string | null;
  checkout: string | null;
  data: string;
  inicio: string | null;
  atividades: VisitaAtividade[];
  fotos: VisitaFoto[];
}

export interface OcorrenciaPortal {
  code: string;
  tipo: string;
  severidade: string;
  status: string;
  posto: string;
  data: string | null;
  resolvida_em: string | null;
}

export const operacao = {
  resumo: () => portalFetch<OperacaoResumo>('/operacao/resumo'),
  equipe: () => portalFetch<{ condominio: string; total: number; equipe: Funcionario[] }>('/operacao/equipe'),
  ranking: () => portalFetch<{ condominio: string; ranking: RankingItem[]; criterio: string }>('/operacao/ranking'),
  assiduidade: () => portalFetch<{ resumo: Record<string, number>; funcionarios: RankingItem[] }>('/operacao/assiduidade'),
  atestados: () => portalFetch<{ asos: Aso[]; resumo: { total: number; vencidos: number } }>('/operacao/atestados'),
  turnover: () => portalFetch<{ resumo: Record<string, number>; movimentacoes: Movimentacao[] }>('/operacao/turnover'),
  advertencias: () => portalFetch<{ advertencias: unknown[]; total: number }>('/operacao/advertencias'),
  escalas: () => portalFetch<{ tem_escala: boolean; turnos: unknown[]; padrao: unknown[] }>('/operacao/escalas'),
  ocorrencias: () =>
    portalFetch<{ condominio: string; total: number; ocorrencias: OcorrenciaPortal[] }>('/operacao/ocorrencias'),
  visitas: (limite = 10) =>
    portalFetch<{ condominio: string; total_visitas: number; visitas: Visita[] }>(`/operacao/visitas?limite=${limite}`),
};
