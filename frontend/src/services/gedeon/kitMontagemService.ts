/**
 * GEDEON — Montagem de kits (orquestrador) via API.
 * POST dispara a montagem (assíncrona) | GET acompanha o status | GET painel de completude.
 */
import { api } from '@/lib/api';

export interface MontagemStatus {
  task_id: string;
  state: 'PENDING' | 'STARTED' | 'SUCCESS' | 'FAILURE' | string;
  etapas_esperadas: string[];
  competencia?: string;
  resumo?: { etapas_ok: number; etapas_falha: number };
  etapas?: Record<string, { ok: boolean; erro?: string | null }>;
  ponto?: { state: string; competencia?: string; arquivados?: string };
  erro?: string;
}

export interface PainelKit {
  condominio: string;
  total: number;
  subpastas: { nome: string; docs: number }[];
  drive_link: string | null;
}

export interface PainelResponse {
  competencia: string;
  mes_kit: string;
  condominios: PainelKit[];
}

export interface CronogramaEtapa {
  titulo: string;
  data: string | null;
  prazo: string | null;
  blocos: string[];
  obs: string | null;
  vencido: boolean;
}
export interface CronogramaResponse {
  competencia: string;
  mes_entrega: string;
  hoje: string;
  etapas: CronogramaEtapa[];
}

export async function dispararMontagem(
  competencia?: string,
  blocos?: string[] | null,
  condominios?: string[] | null,
): Promise<{ task_id: string; competencia: string; blocos: string[] | string; status: string }> {
  const { data } = await api.post('/api/v1/gedeon/kits/montagem', {
    competencia: competencia || null,
    blocos: blocos && blocos.length ? blocos : null,
    condominios: condominios && condominios.length ? condominios : null,
  });
  return data;
}

export async function cronogramaKits(competencia?: string): Promise<CronogramaResponse> {
  const { data } = await api.get('/api/v1/gedeon/kits/cronograma', {
    params: competencia ? { competencia } : {},
  });
  return data;
}

/** Rótulos dos blocos da montagem incremental. */
export const BLOCO_LABEL: Record<string, string> = {
  folha: 'Folha e contracheques',
  guias: 'Guias e impostos',
  pagamentos: 'Salários (Inter)',
  vavt: 'VT / VR',
  cnds: 'Certidões (CNDs)',
  nfse: 'Notas fiscais',
  ponto: 'Assinados — ponto/VT/VR (Sólides)',
};

export async function statusMontagem(taskId: string): Promise<MontagemStatus> {
  const { data } = await api.get(`/api/v1/gedeon/kits/montagem/${taskId}`);
  return data;
}

export async function painelKits(competencia: string): Promise<PainelResponse> {
  const { data } = await api.get('/api/v1/gedeon/kits/painel', { params: { competencia } });
  return data;
}

/** Rótulos amigáveis das etapas do orquestrador. */
export const ETAPA_LABEL: Record<string, string> = {
  onvio_sessao: 'Conectar ao Onvio',
  onvio_sync: 'Sincronizar documentos (Onvio)',
  onvio_folha_contracheques: 'Folha e contracheques',
  onvio_guias: 'Guias (FGTS, DCTFWeb, INSS)',
  inter: 'Salários e boletos (Banco Inter)',
  inss_tributario: 'Comprovante de INSS',
  va_vt: 'Vale transporte e alimentação',
  cnds: 'Certidões (CNDs)',
  nfse_danfse: 'Notas fiscais (NFS-e)',
};

/** Etapas do orquestrador acionadas por cada bloco (p/ desenhar o progresso). */
export const BLOCOS_ETAPAS: Record<string, string[]> = {
  folha: ['onvio_sessao', 'onvio_sync', 'onvio_folha_contracheques'],
  guias: ['onvio_sessao', 'onvio_sync', 'onvio_guias'],
  pagamentos: ['inter', 'inss_tributario'],
  vavt: ['inter', 'va_vt'],
  cnds: ['cnds'],
  nfse: ['nfse_danfse'],
  ponto: [],
};
