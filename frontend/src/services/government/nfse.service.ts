/**
 * Service Layer - NFS-e
 *
 * Endpoints: Emissão, Consulta e Cancelamento de NFS-e
 * Suporta: NFS-e Padrão Nacional e NFS-e Manaus
 */

import api from '@/lib/api';
import type { StandardResponse } from '@/types/generated/government';

// Tipos locais para a camada de serviço
export interface EmissaoNFSeParams {
  tomador: {
    cpf_cnpj: string;
    razao_social: string;
    email?: string;
  };
  servico: {
    codigo: string;
    descricao: string;
    valor: number;
    aliquota_iss?: number;
  };
  rps?: {
    numero: number;
    serie: string;
  };
}

export interface CancelamentoNFSeParams {
  numero_nota: string;
  codigo_cancelamento: string;
  motivo: string;
}

export interface ConsultaNFSeParams {
  numero_nota?: string;
  numero_rps?: string;
  serie_rps?: string;
  data_emissao_inicial?: string;
  data_emissao_final?: string;
}

/**
 * Emite NFS-e Padrão Nacional
 */
export async function emitirNFSeNacional(
  params: EmissaoNFSeParams
): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/nfse-nacional/emitir',
    {
      tomador: params.tomador,
      servico: params.servico,
      prestador: (params as any).prestador,
      numero: (params as any).numero,
      rps: params.rps,
    }
  );
  return data;
}

/**
 * Emite NFS-e Manaus
 */
export async function emitirNFSeManaus(
  params: EmissaoNFSeParams
): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/nfse-manaus/emitir',
    {
      tomador: params.tomador,
      servico: params.servico,
      rps: params.rps,
    }
  );
  return data;
}

/**
 * Cancela NFS-e Padrão Nacional
 */
export async function cancelarNFSeNacional(
  params: CancelamentoNFSeParams
): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/nfse-nacional/cancelar',
    {
      numero_nota: params.numero_nota,
      codigo_cancelamento: params.codigo_cancelamento,
      motivo: params.motivo,
    }
  );
  return data;
}

/**
 * Cancela NFS-e Manaus
 */
export async function cancelarNFSeManaus(
  params: CancelamentoNFSeParams
): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/nfse-manaus/cancelar',
    {
      numero_nota: params.numero_nota,
      codigo_cancelamento: params.codigo_cancelamento,
      motivo: params.motivo,
    }
  );
  return data;
}

/**
 * Consulta NFS-e por RPS (Manaus)
 */
export async function consultarNFSePorRPS(params: {
  numero_rps: string;
  serie_rps: string;
}): Promise<StandardResponse> {
  const { data } = await api.get<StandardResponse>(
    `/api/v1/government/nfse-manaus/consultar/rps/${params.numero_rps}`,
    { params: { serie: params.serie_rps } }
  );
  return data;
}

/**
 * Consulta lote de NFS-e
 */
export async function consultarLoteNFSe(params: {
  numero_lote: string;
}): Promise<StandardResponse> {
  const { data } = await api.get<StandardResponse>(
    `/api/v1/government/nfse-nacional/consultar-lote/${params.numero_lote}`
  );
  return data;
}

/**
 * Lista NFS-e emitidas com filtros
 * Endpoint real: GET /api/v1/financial/nfse
 * Normaliza campos do backend financeiro para o contrato esperado pelo frontend
 */
export async function listarNFSe(
  params: ConsultaNFSeParams
): Promise<StandardResponse> {
  const { data } = await api.get<{ total: number; items: any[] }>(
    '/api/v1/financial/nfse',
    { params }
  );
  const items = (data.items || []).map((n: any) => ({
    ...n,
    numero: n.numero_nfse ?? n.numero,
    tomador_nome: n.tomador_razao_social ?? n.tomador_nome,
    tomador_cnpj: n.tomador_cpf_cnpj ?? n.tomador_cnpj,
    valor_servico: n.valor_servicos ?? n.valor_servico,
    status: n.status === 'autorizada' ? 'emitida' : n.status,
  }));
  return { items, total: data.total } as unknown as StandardResponse;
}

/**
 * Consulta NFS-e Manaus por número
 */
export async function consultarNFSeManausPorNumero(params: {
  numero_nfse: string;
}): Promise<StandardResponse> {
  const { data } = await api.get<StandardResponse>(
    `/api/v1/government/nfse-manaus/consultar/numero/${params.numero_nfse}`
  );
  return data;
}

/**
 * Verifica status da conexão NFS-e Manaus
 */
export async function validarConexaoNFSe(): Promise<StandardResponse> {
  const { data } = await api.get<StandardResponse>(
    '/api/v1/government/nfse-manaus/status'
  );
  return data;
}

/**
 * Lista códigos de serviço NFS-e Manaus
 */
export async function listarCodigosServico(): Promise<StandardResponse> {
  const { data } = await api.get<StandardResponse>(
    '/api/v1/government/nfse-manaus/codigos-servico'
  );
  return data;
}

const nfseService = {
  emitirNFSeNacional,
  emitirNFSeManaus,
  cancelarNFSeNacional,
  cancelarNFSeManaus,
  consultarNFSePorRPS,
  consultarLoteNFSe,
  listarNFSe,
  consultarNFSeManausPorNumero,
  validarConexaoNFSe,
  listarCodigosServico,
};

export default nfseService;

export async function listarTomadoresNFSe(): Promise<any[]> {
  const { data } = await api.get<any>('/api/v1/government/nfse-nacional/tomadores');
  return data?.data?.tomadores || [];
}
