/**
 * Service Layer - SST (Saude e Seguranca do Trabalho)
 * Afastamentos, CAT, Estabilidade, Ajuda Medicamento
 *
 * @module services/sst
 * @author Conecta PRO Team
 * @date 2026-03-16
 */

import api from '@/lib/api';

// =============================================================================
// TIPOS - AFASTAMENTOS
// =============================================================================

export interface Afastamento {
  id: string;
  employee_id: string;
  employee_nome: string;
  employee_cargo: string;
  tipo: string;
  motivo: string | null;
  data_inicio: string;
  data_fim_prevista: string | null;
  data_retorno: string | null;
  dias_previstos: number | null;
  atestado: boolean;
  cid: string | null;
  status: string;
  ajuda_medicamento_ativa: boolean;
  ajuda_medicamento_valor: number | null;
  gera_estabilidade: boolean;
  estabilidade_ate: string | null;
}

export interface AfastamentoList {
  total: number;
  afastamentos: Afastamento[];
}

export interface AfastamentoCreate {
  employee_id: string;
  tipo: string;
  motivo?: string;
  data_inicio: string;
  data_fim_prevista?: string;
  dias_previstos?: number;
  atestado?: boolean;
  cid?: string;
}

// =============================================================================
// TIPOS - DASHBOARD
// =============================================================================

export interface SSTDashboard {
  total_colaboradores: number;
  afastados_ativos: number;
  taxa_afastamento: string;
  risco_nr1: string;
  asos_vencendo_30d: number;
  cats_abertas: number;
  colaboradores_estabilidade: number;
  pcmso_vigente: boolean;
  ppra_vigente: boolean;
  ajuda_medicamento_ativa: number;
  custo_afastamentos_mes: number;
}

// =============================================================================
// TIPOS - CAT
// =============================================================================

export type ESocialStatus =
  | 'nao_transmitida'
  | 'transmitida'
  | 'aceita'
  | 'rejeitada'
  | 'erro';

export interface CATItem {
  cat_id: string;
  employee_id: string;
  tipo: string;
  data: string;
  local: string;
  gravidade: string;
  status: string;
  esocial_status: ESocialStatus;
  recibo_esocial: string | null;
  esocial_protocolo: string | null;
  esocial_transmitida_em: string | null;
  deadline_transmissao: string | null;
}

export interface CATList {
  total: number;
  cats: CATItem[];
}

export interface CATCreate {
  employee_id: string;
  tipo_acidente: string;
  data_acidente: string;
  local: string;
  descricao: string;
  gravidade: string;
  testemunhas?: string[];
}

export interface TaxaAcidente {
  total_colaboradores: number;
  total_cats: number;
  taxa_acidente_percentual: number;
}

export interface CATTransmitirResponse {
  cat_id: string;
  esocial_status: ESocialStatus;
  esocial: {
    transmissao_enfileirada: boolean;
    task_id?: string;
    motivo?: string;
    erro?: string;
  };
}

// =============================================================================
// TIPOS - ASO (eSocial S-2220)
// =============================================================================

export interface ASOItem {
  aso_id: string;
  employee_id?: string;
  employee_nome?: string;
  tipo: string;
  status: string;
  esocial_status: ESocialStatus;
  recibo_s2220: string | null;
  esocial_protocolo: string | null;
}

export interface ASOList {
  total?: number;
  asos?: ASOItem[];
  items?: ASOItem[];
}

// =============================================================================
// TIPOS - FICHAS DE EPI
// =============================================================================

export type FichaEPIStatus = 'pendente_assinatura' | 'assinada';

export interface FichaEPIItemEntrega {
  epi_nome: string;
  ca: string | null;
  quantidade: number;
  data_entrega: string | null;
  data_validade: string | null;
}

export interface FichaEPI {
  ficha_id: string;
  employee_id: string;
  employee_nome: string;
  itens: FichaEPIItemEntrega[];
  status: FichaEPIStatus;
  assinatura_hash: string | null;
  assinado_em: string | null;
  created_at: string | null;
}

export interface FichaEPIList {
  total: number;
  pendentes_assinatura: number;
  assinadas: number;
  fichas: FichaEPI[];
}

export interface FichaEPIGerarPayload {
  employee_id: string;
  delivery_ids?: string[];
}

// =============================================================================
// TIPOS - COMPLIANCE NR-1
// =============================================================================

export interface NR1CheckASO {
  ok: boolean;
  situacao: string;
  data_validade: string | null;
}

export interface NR1CheckEPI {
  ok: boolean;
  situacao: string;
  entregas: number;
  com_ficha_assinada: number;
}

export interface NR1CheckRiscos {
  ok: boolean;
  situacao: string;
  fonte: string;
}

export interface NR1CheckTreinamentos {
  ok: boolean | null;
  situacao: string;
  nota?: string;
}

export interface NR1Funcionario {
  employee_id: string;
  nome: string;
  cargo: string;
  score: number;
  calcado: boolean;
  checks: {
    aso: NR1CheckASO;
    epi: NR1CheckEPI;
    riscos: NR1CheckRiscos;
    treinamentos: NR1CheckTreinamentos;
  };
}

export interface NR1Compliance {
  resumo: {
    total_funcionarios_ativos: number;
    calcados: number;
    descalcados: number;
    asos_vencidos_registros: number;
    funcionarios_aso_vencido: number;
    fichas_epi_pendentes_assinatura: number;
    entregas_epi_sem_ficha: number;
    riscos_mapeados_vigentes: number;
    treinamentos_fonte: string;
  };
  funcionarios: NR1Funcionario[];
}

// =============================================================================
// TIPOS - ESTABILIDADE
// =============================================================================

export interface EstabilidadeItem {
  employee_id: string;
  nome: string;
  cargo: string;
  tipo_afastamento: string;
  data_retorno: string | null;
  estabilidade_ate: string;
  dias_restantes: number;
  clausula_cct: string;
}

export interface EstabilidadeList {
  total: number;
  colaboradores: EstabilidadeItem[];
}

// =============================================================================
// TIPOS - AJUDA MEDICAMENTO
// =============================================================================

export interface AjudaMedicamentoItem {
  employee_id: string;
  nome: string;
  cargo: string;
  data_inicio_afastamento: string;
  valor_mensal: number;
  clausula_cct: string;
}

export interface AjudaMedicamentoList {
  total: number;
  valor_unitario: number;
  custo_mensal_total: number;
  colaboradores: AjudaMedicamentoItem[];
}

// =============================================================================
// TIPOS - LTCAT
// =============================================================================

export interface LTCATFatorRisco {
  agente: string;
  tipo: string;
  nivel: string | null;
}

export type LTCATStatusValor =
  | 'pendente_elaboracao'
  | 'em_elaboracao'
  | 'vigente'
  | 'vencido';

export interface LTCATStatus {
  ltcat_id: string | null;
  documento: string;
  base_legal: string;
  empresa: string;
  cnpj: string;
  vigencia: string;
  responsavel_tecnico: string;
  registro_conselho: string | null;
  observacoes: string | null;
  fonte_fatores_risco: string | null;
  postos_avaliados: number;
  status: LTCATStatusValor | string;
  fatores_risco: LTCATFatorRisco[];
  proxima_acao: string;
}

export interface LTCATUpdatePayload {
  status?: LTCATStatusValor;
  responsavel_tecnico?: string;
  registro_conselho?: string;
  validade_inicio?: string;
  validade_fim?: string;
  observacoes?: string;
}

// =============================================================================
// LABELS
// =============================================================================

export const AFASTAMENTO_STATUS_LABELS: Record<string, string> = {
  ativo: 'Ativo',
  encerrado: 'Encerrado',
  prorrogado: 'Prorrogado',
};

export const GRAVIDADE_LABELS: Record<string, string> = {
  leve: 'Leve',
  medio: 'Medio',
  grave: 'Grave',
  critico: 'Critico',
};

// =============================================================================
// SERVICE - SST
// =============================================================================

const BASE = '/api/v1/people-management/sst';

export const sstService = {
  // Dashboard
  getDashboard: () =>
    api.get<SSTDashboard>(`${BASE}/dashboard`).then((r) => r.data),

  // Afastamentos
  listAfastamentos: (status?: string) =>
    api
      .get<AfastamentoList>(`${BASE}/afastamentos`, {
        params: status ? { status } : {},
      })
      .then((r) => r.data),

  getAfastamento: (id: string) =>
    api.get<Afastamento>(`${BASE}/afastamentos/${id}`).then((r) => r.data),

  createAfastamento: (data: AfastamentoCreate) =>
    api.post(`${BASE}/afastamentos`, data).then((r) => r.data),

  registrarRetorno: (id: string, data_retorno: string) =>
    api
      .put(`${BASE}/afastamentos/${id}/retorno`, { data_retorno })
      .then((r) => r.data),

  // CAT
  listCATs: (employee_id?: string) =>
    api
      .get<CATList>(`${BASE}/cat`, {
        params: employee_id ? { employee_id } : {},
      })
      .then((r) => r.data),

  createCAT: (data: CATCreate) =>
    api.post(`${BASE}/cat`, data).then((r) => r.data),

  transmitirCAT: (catId: string) =>
    api
      .post<CATTransmitirResponse>(`${BASE}/cat/${catId}/transmitir`)
      .then((r) => r.data),

  getTaxaAcidente: () =>
    api.get<TaxaAcidente>(`${BASE}/cat/taxa-acidente`).then((r) => r.data),

  // ASO (eSocial S-2220)
  listASOs: () => api.get<ASOList>(`${BASE}/aso`).then((r) => r.data),

  // Fichas de EPI
  listFichasEPI: (status?: FichaEPIStatus) =>
    api
      .get<FichaEPIList>(`${BASE}/epi/fichas`, {
        params: status ? { status } : {},
      })
      .then((r) => r.data),

  gerarFichaEPI: (data: FichaEPIGerarPayload) =>
    api.post(`${BASE}/epi/fichas/gerar`, data).then((r) => r.data),

  downloadFichaEPIPdf: (fichaId: string) =>
    api
      .get(`${BASE}/epi/fichas/${fichaId}/pdf`, { responseType: 'blob' })
      .then((r) => r.data as Blob),

  // Compliance NR-1
  getNR1Compliance: () =>
    api.get<NR1Compliance>(`${BASE}/nr1/compliance`).then((r) => r.data),

  // Estabilidade
  listEstabilidade: () =>
    api
      .get<EstabilidadeList>(`${BASE}/estabilidade/ativos`)
      .then((r) => r.data),

  // Ajuda Medicamento
  listAjudaMedicamento: () =>
    api
      .get<AjudaMedicamentoList>(`${BASE}/ajuda-medicamento/ativos`)
      .then((r) => r.data),

  // NR1 / PCMSO / PPRA
  getNR1Dashboard: () =>
    api.get(`${BASE}/nr1/dashboard`).then((r) => r.data),

  getPCMSOStatus: () =>
    api.get(`${BASE}/pcmso/status`).then((r) => r.data),

  getPPRAStatus: () =>
    api.get(`${BASE}/ppra/status`).then((r) => r.data),

  // LTCAT
  getLTCATStatus: () =>
    api.get<LTCATStatus>(`${BASE}/ltcat/status`).then((r) => r.data),

  updateLTCAT: (data: LTCATUpdatePayload) =>
    api.put(`${BASE}/ltcat`, data).then((r) => r.data),
};

export default sstService;
