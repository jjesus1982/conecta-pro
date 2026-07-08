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
  medico?: string | null;
  crm?: string | null;
  status: string;
  ajuda_medicamento_ativa: boolean;
  ajuda_medicamento_valor: number | null;
  gera_estabilidade: boolean;
  estabilidade_ate: string | null;
  // eSocial S-2230 — opcionais (expostos pelo backend após o bake)
  esocial_status?: string;
  recibo_s2230?: string | null;
  esocial_protocolo?: string | null;
}

export interface AfastamentoList {
  total: number;
  afastamentos: Afastamento[];
}

/** Tipos aceitos pelo backend (Tabela 18 eSocial: os 4 primeiros auto-transmitem S-2230) */
export const AFASTAMENTO_TIPOS: { value: string; label: string; autoS2230: boolean }[] = [
  { value: 'doenca', label: 'Doença (atestado)', autoS2230: true },
  { value: 'acidente_trabalho', label: 'Acidente de trabalho', autoS2230: true },
  { value: 'acidente_trajeto', label: 'Acidente de trajeto', autoS2230: true },
  { value: 'licenca_maternidade', label: 'Licença-maternidade', autoS2230: true },
  { value: 'licenca_paternidade', label: 'Licença-paternidade', autoS2230: false },
  { value: 'outro', label: 'Outro', autoS2230: false },
];

export interface AfastamentoCreate {
  employee_id: string;
  employee_nome?: string;
  employee_cargo?: string;
  tipo: string;
  motivo?: string;
  data_inicio: string;
  data_fim_prevista?: string;
  dias_previstos?: number;
  atestado?: boolean;
  cid?: string;
  medico?: string;
  crm?: string;
}

/** Resposta honesta do enfileiramento eSocial (recibo real vem depois, via pull) */
export interface ESocialEnfileiramento {
  evento?: string;
  transmissao_enfileirada: boolean;
  task_id?: string;
  nota?: string;
  motivo?: string;
  erro?: string;
}

export interface AfastamentoCreateResponse extends Afastamento {
  esocial?: ESocialEnfileiramento;
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
  recibo_esocial?: string | null;
  esocial: ESocialEnfileiramento;
}

/** Resposta do POST /sst/cat — DESTAQUE: deadline_transmissao (1º dia útil, Lei 8.213/91) */
export interface CATCreateResponse {
  cat_id: string;
  employee_id: string;
  tipo: string;
  data: string;
  local: string;
  gravidade: string;
  status: string;
  esocial_status: ESocialStatus;
  deadline_transmissao: string | null;
  prazo_legal: string;
  esocial: ESocialEnfileiramento;
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
  /** Nome original do ASO digitalizado anexado (null = sem anexo) */
  arquivo_nome?: string | null;
  /** true = carga retroativa (exame em papel, pré-sistema) */
  retroativo?: boolean;
}

export interface ASOList {
  total?: number;
  asos?: ASOItem[];
  items?: ASOItem[];
}

/** PUT /sst/aso/{id}/resultado — gatilho eSocial S-2220 */
export interface ASOResultadoPayload {
  apto: boolean;
  restricoes?: string[];
  medico?: string;
  crm?: string;
  observacoes?: string;
}

export interface ASOResultadoResponse {
  aso_id: string;
  status: string;
  apto: boolean;
  esocial: ESocialEnfileiramento;
}

/** POST /sst/aso/{id}/anexo — upload do ASO digitalizado */
export interface ASOAnexoResponse {
  aso_id: string;
  arquivo_nome: string;
  arquivo_path: string;
  tamanho_bytes: number;
}

/** POST /sst/aso/retroativo — carga retroativa (anexo OBRIGATÓRIO) */
export interface ASORetroativoPayload {
  employee_id: string;
  tipo: string;
  data_realizacao: string;
  clinica?: string;
  medico?: string;
  crm?: string;
  apto?: boolean;
}

export interface ASORetroativoResponse {
  aso_id: string;
  employee_id: string;
  employee_nome: string;
  tipo: string;
  status: string;
  retroativo: boolean;
  data_realizacao: string;
  data_validade: string | null;
  arquivo_nome: string;
  esocial: ESocialEnfileiramento;
}

/** GET /sst/asos/sem-aso — funcionários ativos sem NENHUM ASO digitalizado */
export interface SemASOItem {
  employee_id: string;
  nome: string;
  cargo: string | null;
}

export interface SemASOList {
  total: number;
  colaboradores: SemASOItem[];
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
// TIPOS - ENTREGAS DE EPI
// =============================================================================

/** POST /sst/epi — registra a entrega e gera a ficha (pendente de assinatura) */
export interface EPIEntregaCreate {
  employee_id: string;
  epi_nome: string;
  quantidade: number;
  epi_ca?: string;
}

export interface EPIEntregaResponse {
  delivery_id: string;
  employee_id: string;
  epi: string;
  quantidade: number;
  data_entrega: string | null;
  status: string;
  ficha_epi: {
    ficha_id: string | null;
    status: string;
    pdf?: string;
    erro?: string;
  };
}

export interface EPIEntregaItem {
  delivery_id: string;
  employee_id: string;
  epi: string;
  quantidade: number;
  ca: string | null;
  /** Campo "status" do backend carrega a NR da entrega (drift histórico) */
  status: string | null;
  ficha_epi_id: string | null;
  ficha_status: 'pendente_assinatura' | 'assinada' | 'sem_ficha' | string;
}

export interface EPIEntregaList {
  total: number;
  epis: EPIEntregaItem[];
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
  /** Vencimento do treinamento NR-1 mais recente (fonte: sst_treinamentos) */
  nr1_vencimento?: string | null;
  registros?: number;
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
// TIPOS - PRONTUÁRIO SST 360 (dossiê completo por funcionário)
// =============================================================================

/** Todo bloco do prontuário carrega a fonte real; se o domínio falhou, vem `erro` */
export interface ProntuarioBlocoBase {
  fonte: string;
  erro?: string;
}

export interface ProntuarioIdentificacao {
  fonte: string;
  employee_id: string;
  nome: string;
  cpf: string | null;
  matricula: string | null;
  cargo: string | null;
  data_admissao: string | null;
  data_demissao: string | null;
  status: string;
  posto_atual: { posto_id: string; nome: string } | null;
  posto_atual_erro?: string;
}

export interface ProntuarioCompliance extends ProntuarioBlocoBase {
  score?: number | null;
  calcado?: boolean | null;
  checks?: NR1Funcionario['checks'] | null;
  nota?: string;
}

export interface ProntuarioASOItem {
  aso_id: string;
  tipo: string | null;
  status: string | null;
  data_agendamento: string | null;
  data_realizacao: string | null;
  data_validade: string | null;
  vencido: boolean;
  clinica: string | null;
  medico: string | null;
  crm: string | null;
  apto: boolean | null;
  exames: { dt_exame?: string; cod_procedimento?: string; nome?: string }[] | null;
  esocial_status: string | null;
  recibo_s2220: string | null;
}

export interface ProntuarioASOs extends ProntuarioBlocoBase {
  total?: number;
  proximo_vencimento?: string | null;
  vencido?: boolean;
  historico?: ProntuarioASOItem[];
}

export interface ProntuarioEPIEntrega {
  delivery_id: string;
  epi_nome: string;
  ca: string | null;
  quantidade: number;
  nr: string | null;
  data_entrega: string | null;
  data_validade: string | null;
  data_devolucao: string | null;
  ficha_epi_id: string | null;
  ficha_status: string | null;
}

export interface ProntuarioFichaEPI {
  ficha_id: string;
  status: FichaEPIStatus | string;
  itens: FichaEPIItemEntrega[];
  assinatura_hash: string | null;
  assinado_em: string | null;
  created_at: string | null;
}

export interface ProntuarioEPIs extends ProntuarioBlocoBase {
  total_entregas?: number;
  entregas?: ProntuarioEPIEntrega[];
  total_fichas?: number;
  fichas_assinadas?: number;
  fichas?: ProntuarioFichaEPI[];
}

export interface ProntuarioRisco {
  risk_id: string;
  categoria: string;
  descricao: string;
  nivel: string;
  fonte_geradora: string | null;
  medidas_controle: string[];
  epi_recomendado: string[];
  cod_agente_nocivo: string | null;
  utiliz_epc: string | null;
  utiliz_epi: string | null;
  medicao: string | null;
  status: string;
}

export interface ProntuarioRiscosFuncao extends ProntuarioBlocoBase {
  cargo?: string | null;
  funcao_token?: string | null;
  total?: number;
  riscos?: ProntuarioRisco[];
  nota?: string;
}

export interface ProntuarioTreinamento {
  id: string;
  norma: string;
  descricao: string | null;
  data_realizacao: string;
  validade_meses: number;
  vencimento: string;
  situacao: TreinamentoSituacao | string;
  certificado_path: string | null;
  created_by: string | null;
}

export interface ProntuarioTreinamentos extends ProntuarioBlocoBase {
  total?: number;
  treinamentos?: ProntuarioTreinamento[];
}

export interface ProntuarioAfastamento {
  id: string;
  tipo: string;
  motivo: string | null;
  data_inicio: string;
  data_fim_prevista: string | null;
  data_retorno: string | null;
  dias_previstos: number | null;
  cid: string | null;
  medico: string | null;
  crm: string | null;
  status: string;
  gera_estabilidade: boolean;
  estabilidade_ate: string | null;
  ajuda_medicamento_ativa: boolean;
  esocial_status: string | null;
  recibo_s2230: string | null;
  esocial_protocolo: string | null;
}

export interface ProntuarioAfastamentos extends ProntuarioBlocoBase {
  total?: number;
  estabilidade_vigente_ate?: string | null;
  afastamentos?: ProntuarioAfastamento[];
}

export interface ProntuarioCAT {
  cat_id: string;
  tipo_acidente: string;
  data_acidente: string;
  hora_acidente: string | null;
  local: string;
  descricao: string;
  gravidade: string;
  parte_corpo: string | null;
  agente_causador: string | null;
  afastamento_dias: number | null;
  numero_cat_inss: string | null;
  status: string;
  esocial_status: string | null;
  recibo_esocial: string | null;
  esocial_protocolo: string | null;
  esocial_transmitida_em: string | null;
}

export interface ProntuarioCATs extends ProntuarioBlocoBase {
  total?: number;
  cats?: ProntuarioCAT[];
}

export interface ProntuarioSST {
  gerado_em: string;
  identificacao: ProntuarioIdentificacao;
  compliance: ProntuarioCompliance;
  asos: ProntuarioASOs;
  epis: ProntuarioEPIs;
  riscos_funcao: ProntuarioRiscosFuncao;
  treinamentos: ProntuarioTreinamentos;
  afastamentos: ProntuarioAfastamentos;
  cats: ProntuarioCATs;
}

// =============================================================================
// TIPOS - TREINAMENTOS NR (4º pilar do compliance NR-1)
// =============================================================================

export type TreinamentoSituacao = 'em_dia' | 'vencendo' | 'vencido';

export const TREINAMENTO_NORMAS: { value: string; label: string }[] = [
  { value: 'NR-1', label: 'NR-1 (Disposições Gerais / GRO)' },
  { value: 'NR-6', label: 'NR-6 (EPI)' },
  { value: 'brigada', label: 'Brigada de Incêndio' },
  { value: 'primeiros_socorros', label: 'Primeiros Socorros' },
  { value: 'outro', label: 'Outro' },
];

export interface TreinamentoNR {
  id: string;
  employee_id: string;
  employee_nome: string | null;
  norma: string;
  descricao: string | null;
  data_realizacao: string;
  validade_meses: number;
  vencimento: string;
  situacao: TreinamentoSituacao;
  certificado_path: string | null;
  created_by: string | null;
}

export interface TreinamentoNRList {
  total: number;
  em_dia: number;
  vencendo_30d: number;
  vencidos: number;
  treinamentos: TreinamentoNR[];
}

export interface TreinamentoNRCreate {
  employee_id: string;
  norma: string;
  descricao?: string;
  data_realizacao: string;
  validade_meses: number;
  certificado_path?: string;
}

// =============================================================================
// TIPOS - REGULARIZAÇÃO DE ASOs VENCIDAS
// =============================================================================

export interface ASORegularizacaoItem {
  employee_id: string;
  nome: string;
  cargo: string | null;
  aso_id: string;
  tipo_ultimo_aso: string;
  data_validade: string;
  dias_vencido: number;
  posto_id: string | null;
  posto_nome: string;
  ja_agendado: boolean;
  proxima_data_agendada: string | null;
}

export interface ASORegularizacaoPostoResumo {
  posto_nome: string;
  posto_id: string | null;
  pendentes: number;
  mais_vencido_dias: number;
}

export interface ASORegularizacao {
  gerado_em: string;
  registros_aso_vencidos_total: number;
  funcionarios_pendentes: number;
  ja_agendados: number;
  nota: string;
  resumo_por_posto: ASORegularizacaoPostoResumo[];
  pendentes: ASORegularizacaoItem[];
}

export interface ASOAgendarLoteItem {
  employee_id: string;
  data_agendamento: string;
  clinica?: string;
  tipo: string;
}

export interface ASOAgendarLoteResponse {
  total_recebidos: number;
  total_agendados: number;
  total_erros: number;
  agendados: {
    aso_id: string;
    employee_id: string;
    employee_nome: string;
    tipo: string;
    data_agendamento: string;
    clinica: string | null;
    status: string;
  }[];
  erros: { employee_id: string; erro: string }[];
  nota: string;
}

// =============================================================================
// TIPOS - ESTEIRA PCMSO PREVENTIVA (projeção 12m — nada é gravado)
// =============================================================================

export interface EsteiraPCMSODoc {
  pcmso_id: string;
  medico_coordenador: string;
  crm: string;
  uf: string;
  elaborador: string | null;
  vigencia_inicio: string;
  vigencia_fim: string;
  vigente_hoje: boolean;
  dias_para_vencer_pcmso: number;
  grupos_funcao: string[];
}

export interface EsteiraExamePrevisto {
  nome: string;
  cod_tabela27: string | null;
}

export type EsteiraSituacao = 'pendente_imediato' | 'vencido' | 'previsto';

export interface EsteiraAgendaItem {
  employee_id: string;
  nome: string;
  cargo: string | null;
  posto_id: string | null;
  posto_nome: string;
  situacao: EsteiraSituacao;
  data_prevista: string;
  mes: string; // YYYY-MM
  vencimento_base: string | null;
  dias_para_vencer: number | null;
  dias_vencido: number | null;
  base: { tipo: string; data_realizacao: string } | null;
  grupo_pcmso: string | null;
  exames_definidos: boolean;
  exames_previstos: EsteiraExamePrevisto[];
  nota_exames: string | null;
  ja_agendado: boolean;
  proxima_data_agendada: string | null;
}

export interface EsteiraMesResumo {
  mes: string;
  label: string;
  total: number;
  pendente_imediato: number;
  vencidos: number;
  previstos: number;
  agendados: number;
}

export interface EsteiraPostoResumo {
  posto_nome: string;
  posto_id: string | null;
  total: number;
  acao_imediata: number;
}

export interface EsteiraPCMSO {
  gerado_em: string;
  horizonte_meses: number;
  pcmso: EsteiraPCMSODoc | null;
  total_funcionarios_ativos: number;
  totais: {
    pendente_imediato: number;
    vencidos: number;
    previstos: number;
    ja_agendados: number;
    sem_mapa_exames: number;
    alem_do_horizonte: number;
  };
  resumo_por_mes: EsteiraMesResumo[];
  resumo_por_posto: EsteiraPostoResumo[];
  agenda: EsteiraAgendaItem[];
  nota: string;
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

// Riscos Ocupacionais (PPRA/PGR — tabela gp_risks)
export interface RiscoOcupacional {
  risk_id: string;
  posto_id: string;
  /** Nome legível do posto (join posts/condominios); null = posto não vinculado */
  posto_nome: string | null;
  categoria: string;
  descricao: string;
  nivel: string;
  status: string;
  fonte_geradora: string | null;
  medidas_controle: string[];
  epi_recomendado: string[];
}

export interface RiscoList {
  total: number;
  riscos: RiscoOcupacional[];
}

export interface RiscoCreate {
  posto_id: string;
  categoria: string;
  descricao: string;
  nivel: string;
  fonte_geradora?: string;
  medidas_controle?: string[];
  epi_recomendado?: string[];
}

export interface PostoOption {
  id: string;
  name: string;
  code?: string | null;
  status?: string | null;
}

// =============================================================================
// TIPOS - CALENDARIO LEGAL SST
// =============================================================================

export type CalendarioLegalCriticidade = 'vencido' | 'atencao' | 'ok' | 'sem_data';

export interface CalendarioLegalItem {
  titulo: string;
  categoria: string;
  vencimento: string | null;
  dias_restantes: number | null;
  criticidade: CalendarioLegalCriticidade;
  acao_sugerida: string;
  fonte: string;
}

export interface CalendarioLegal {
  gerado_em: string;
  total: number;
  resumo: Record<CalendarioLegalCriticidade, number>;
  itens: CalendarioLegalItem[];
}

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
// HELPERS
// =============================================================================

/** Extrai o `detail` honesto de um erro da API (string ou lista Pydantic 422). */
export function apiErrorDetail(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data
    ?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) =>
        d && typeof d === 'object' && 'msg' in d
          ? `${Array.isArray((d as { loc?: unknown[] }).loc) ? (d as { loc: unknown[] }).loc.join('.') + ': ' : ''}${String((d as { msg: unknown }).msg)}`
          : String(d)
      )
      .filter(Boolean);
    if (msgs.length > 0) return msgs.join('; ');
  }
  return fallback;
}

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
    api
      .post<AfastamentoCreateResponse>(`${BASE}/afastamentos`, data)
      .then((r) => r.data),

  registrarRetorno: (id: string, data_retorno: string) =>
    api
      .put<AfastamentoCreateResponse>(`${BASE}/afastamentos/${id}/retorno`, { data_retorno })
      .then((r) => r.data),

  // CAT
  listCATs: (employee_id?: string) =>
    api
      .get<CATList>(`${BASE}/cat`, {
        params: employee_id ? { employee_id } : {},
      })
      .then((r) => r.data),

  createCAT: (data: CATCreate) =>
    api.post<CATCreateResponse>(`${BASE}/cat`, data).then((r) => r.data),

  transmitirCAT: (catId: string) =>
    api
      .post<CATTransmitirResponse>(`${BASE}/cat/${catId}/transmitir`)
      .then((r) => r.data),

  getTaxaAcidente: () =>
    api.get<TaxaAcidente>(`${BASE}/cat/taxa-acidente`).then((r) => r.data),

  // ASO (eSocial S-2220)
  listASOs: () => api.get<ASOList>(`${BASE}/aso`).then((r) => r.data),

  // Anexo do ASO (documento digitalizado — PDF/JPG/PNG, max 10MB)
  uploadASOAnexo: (asoId: string, file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return api
      .post<ASOAnexoResponse>(`${BASE}/aso/${asoId}/anexo`, fd)
      .then((r) => r.data);
  },

  downloadASOAnexo: (asoId: string) =>
    api
      .get(`${BASE}/aso/${asoId}/anexo`, { responseType: 'blob' })
      .then((r) => r.data as Blob),

  // Carga retroativa (exame em papel pré-sistema — anexo OBRIGATÓRIO)
  criarASORetroativo: (payload: ASORetroativoPayload, file: File) => {
    const fd = new FormData();
    fd.append('employee_id', payload.employee_id);
    fd.append('tipo', payload.tipo);
    fd.append('data_realizacao', payload.data_realizacao);
    if (payload.clinica) fd.append('clinica', payload.clinica);
    if (payload.medico) fd.append('medico', payload.medico);
    if (payload.crm) fd.append('crm', payload.crm);
    fd.append('apto', String(payload.apto ?? true));
    fd.append('file', file);
    return api
      .post<ASORetroativoResponse>(`${BASE}/aso/retroativo`, fd)
      .then((r) => r.data);
  },

  // Funcionários ativos sem nenhum ASO digitalizado (contador da carga retroativa)
  listSemASO: () => api.get<SemASOList>(`${BASE}/asos/sem-aso`).then((r) => r.data),

  // Regularização de ASOs vencidas
  getASOsRegularizacao: () =>
    api.get<ASORegularizacao>(`${BASE}/asos/regularizacao`).then((r) => r.data),

  agendarASOsLote: (itens: ASOAgendarLoteItem[]) =>
    api
      .post<ASOAgendarLoteResponse>(`${BASE}/asos/agendar-lote`, itens)
      .then((r) => r.data),

  // Esteira PCMSO Preventiva (projeção ao vivo — nada é gravado)
  getEsteiraPCMSO: (horizonteMeses = 12) =>
    api
      .get<EsteiraPCMSO>(`${BASE}/pcmso/esteira`, {
        params: { horizonte_meses: horizonteMeses },
      })
      .then((r) => r.data),

  // Treinamentos NR (sst_treinamentos)
  listTreinamentos: (filters?: {
    employee_id?: string;
    norma?: string;
    vencendo_em_dias?: number;
  }) =>
    api
      .get<TreinamentoNRList>(`${BASE}/treinamentos`, { params: filters ?? {} })
      .then((r) => r.data),

  criarTreinamento: (data: TreinamentoNRCreate) =>
    api.post<TreinamentoNR>(`${BASE}/treinamentos`, data).then((r) => r.data),

  excluirTreinamento: (id: string) =>
    api.delete(`${BASE}/treinamentos/${id}`).then((r) => r.data),

  registrarResultadoASO: (asoId: string, data: ASOResultadoPayload) =>
    api
      .put<ASOResultadoResponse>(`${BASE}/aso/${asoId}/resultado`, data)
      .then((r) => r.data),

  // Entregas de EPI
  listEntregasEPI: (employee_id?: string) =>
    api
      .get<EPIEntregaList>(`${BASE}/epi`, {
        params: employee_id ? { employee_id } : {},
      })
      .then((r) => r.data),

  registrarEntregaEPI: (data: EPIEntregaCreate) =>
    api.post<EPIEntregaResponse>(`${BASE}/epi`, data).then((r) => r.data),

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

  // Prontuário SST 360 (dossiê completo por funcionário)
  getProntuario: (employeeId: string) =>
    api
      .get<ProntuarioSST>(`${BASE}/prontuario/${employeeId}`)
      .then((r) => r.data),

  // Compliance NR-1
  getNR1Compliance: () =>
    api.get<NR1Compliance>(`${BASE}/nr1/compliance`).then((r) => r.data),

  /** Relatório de Compliance NR-1 em PDF padrão-ouro (p/ auditor fiscal) */
  downloadNR1CompliancePdf: () =>
    api
      .get(`${BASE}/nr1/compliance/pdf`, { responseType: 'blob' })
      .then((r) => r.data as Blob),

  /** PPP (Perfil Profissiográfico Previdenciário) em PDF padrão-ouro */
  downloadPPPPdf: (employeeId: string) =>
    api
      .get(`${BASE}/ppp/${employeeId}/pdf`, { responseType: 'blob' })
      .then((r) => r.data as Blob),

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

  // Riscos Ocupacionais (gp_risks — fonte real)
  listRiscos: (filters?: { posto_id?: string; nivel?: string; categoria?: string }) =>
    api
      .get<RiscoList>(`${BASE}/riscos`, { params: filters ?? {} })
      .then((r) => r.data),

  createRisco: (data: RiscoCreate) =>
    api.post(`${BASE}/risco`, data).then((r) => r.data),

  // Postos (para o seletor por nome no Novo Mapeamento)
  listPostos: () =>
    api
      .get<{ items: PostoOption[]; total: number }>(
        '/api/v1/operacional/posts/',
        { params: { page: 1, page_size: 100 } },
      )
      .then((r) => r.data),

  // LTCAT
  getLTCATStatus: () =>
    api.get<LTCATStatus>(`${BASE}/ltcat/status`).then((r) => r.data),

  updateLTCAT: (data: LTCATUpdatePayload) =>
    api.put(`${BASE}/ltcat`, data).then((r) => r.data),

  // Calendario Legal SST (radar unico de vencimentos legais)
  getCalendarioLegal: () =>
    api.get<CalendarioLegal>(`${BASE}/calendario-legal`).then((r) => r.data),
};

export default sstService;
