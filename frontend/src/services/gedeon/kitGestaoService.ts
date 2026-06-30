/**
 * GEDEON — Gestão do kit: ATLAS (conferência), assinaturas, faturamento (NFS-e/boleto),
 * entrega, visão por funcionário e alinhamento DP. Tudo via /api/v1/gedeon/kits/*.
 */
import { api } from '@/lib/api';

const BASE = '/api/v1/gedeon/kits';

// ── ATLAS (conferência) ──────────────────────────────────────────────────────
export interface AtlasCheck { check: string; severidade: 'ok' | 'alerta' | 'erro'; mensagem: string; detalhe?: unknown }
export interface AtlasResult {
  competencia: string; condominio: string; selo: 'conferido' | 'reprovado';
  funcionarios_folha: number; funcionarios_ativos: number; completude: number;
  resumo: { ok: number; alertas: number; erros: number }; checks: AtlasCheck[];
}
export async function conferirKit(condominio: string, competencia?: string, refresh = false): Promise<AtlasResult> {
  const { data } = await api.get(`${BASE}/conferir`, { params: { condominio, competencia, refresh } });
  return data;
}

// ── Pendências de assinatura ─────────────────────────────────────────────────
export interface PendenciaCond {
  condominio: string; funcionarios_folha: number; assinados: number;
  pendentes: { funcionario: string; estado: string }[]; total_pendentes: number;
}
export interface AssinaturasResult {
  competencia: string; total_pendentes: number; tem_dados_aguardando: boolean;
  condominios: PendenciaCond[];
}
export async function pendenciasAssinatura(condominio?: string, competencia?: string): Promise<AssinaturasResult> {
  const { data } = await api.get(`${BASE}/assinaturas`, { params: { condominio, competencia } });
  return data;
}

// ── Faturamento (NFS-e + boleto) ─────────────────────────────────────────────
export interface FaturarPreview {
  emitido: boolean; condominio: string; competencia: string; mes_emissao?: string; valor?: number;
  nfse?: unknown; boleto?: unknown; aviso?: string;
}
export async function faturarKit(
  condominio: string, opts: { competencia?: string; tipo?: 'nfse' | 'boleto' | 'ambos'; confirmar?: boolean; optante_simples?: boolean } = {},
): Promise<FaturarPreview> {
  const { data } = await api.post(`${BASE}/faturar`, {
    condominio, competencia: opts.competencia, tipo: opts.tipo ?? 'ambos',
    confirmar: opts.confirmar ?? false, optante_simples: opts.optante_simples ?? false,
  });
  return data;
}

// ── Entrega ──────────────────────────────────────────────────────────────────
export interface EntregaStatus {
  competencia: string; condominio: string; estado: 'nao_preparado' | 'preparado' | 'entregue';
  indice_link?: string | null; drive_link?: string | null; selo_atlas?: string | null;
  preparado_em?: string; entregue_em?: string; canal?: string; historico?: unknown[];
}
export async function statusEntrega(condominio: string, competencia?: string): Promise<EntregaStatus> {
  const { data } = await api.get(`${BASE}/entrega/status`, { params: { condominio, competencia } });
  return data;
}
export async function prepararEntrega(condominio: string, competencia?: string): Promise<EntregaStatus> {
  const { data } = await api.post(`${BASE}/entrega/preparar`, null, { params: { condominio, competencia } });
  return data;
}
export async function marcarEntregue(condominio: string, opts: { competencia?: string; canal?: string; obs?: string } = {}): Promise<EntregaStatus> {
  const { data } = await api.post(`${BASE}/entrega/marcar`, {
    condominio, competencia: opts.competencia, canal: opts.canal ?? 'manual', obs: opts.obs ?? '',
  });
  return data;
}

// ── Visão por funcionário ────────────────────────────────────────────────────
export interface VisaoFuncionario {
  competencia: string; funcionario: string; condominio?: string | null; total_docs: number;
  kit: { subpasta: string; nome: string; link?: string | null; condominio: string }[];
  solides_assinados: { tipo: string; label: string; arquivo: string; created: string }[];
  onvio: { nome_arquivo: string }[];
}
export async function listarFuncionarios(condominio: string, competencia?: string): Promise<{ funcionarios: string[] }> {
  const { data } = await api.get(`${BASE}/funcionarios`, { params: { condominio, competencia } });
  return data;
}
export async function visaoFuncionario(funcionario: string, condominio?: string, competencia?: string): Promise<VisaoFuncionario> {
  const { data } = await api.get(`${BASE}/funcionario`, { params: { funcionario, condominio, competencia } });
  return data;
}

// ── Alinhamento DP ───────────────────────────────────────────────────────────
export interface DpAlinhamento {
  competencia: string; condominio: string; funcionarios_folha: number; com_espelho_dp: number;
  sem_espelho_dp: { folha: string; dp: string | null }[];
  afastamentos_mes: { funcionario: string; tipo: string; inicio: string; fim: string | null }[];
}
export async function alinhamentoDp(condominio: string, competencia?: string): Promise<DpAlinhamento> {
  const { data } = await api.get(`${BASE}/dp/alinhamento`, { params: { condominio, competencia } });
  return data;
}
