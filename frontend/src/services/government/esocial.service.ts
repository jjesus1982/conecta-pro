/**
 * Service Layer - eSocial
 *
 * Endpoints: Eventos eSocial, Folha de Pagamento, Validações
 */

import api from '@/lib/api';
import type {
  EventoResponse,
  StandardResponse,
} from '@/types/generated/government';

// Tipos locais para a camada de serviço (payloads flexíveis)
export interface EventoESocialParams {
  tipo_evento: string;
  dados_evento: Record<string, unknown>;
  validar_apenas?: boolean;
}

export interface ConfiguracaoEmpresaParams {
  cnpj: string;
  razao_social: string;
  natureza_juridica: string;
  regime_tributario: string;
}

export interface CalculoFolhaParams {
  mes_referencia: string;
  ano_referencia: number;
  colaboradores: Array<{
    cpf: string;
    salario_base: number;
    eventos_adicionais?: Array<{ codigo: string; valor: number }>;
  }>;
}

/**
 * Envia evento para eSocial
 */
export async function enviarEvento(
  params: EventoESocialParams
): Promise<EventoResponse> {
  const { data } = await api.post<EventoResponse>(
    '/api/v1/government/esocial/evento',
    {
      tipo_evento: params.tipo_evento,
      dados: params.dados_evento,
      validar_apenas: params.validar_apenas,
    }
  );
  return data;
}

/**
 * Consulta status de evento eSocial
 */
export async function consultarEvento(params: {
  evento_id: string;
}): Promise<EventoResponse> {
  const { data } = await api.get<EventoResponse>(
    `/api/v1/government/esocial/consultar/${params.evento_id}`
  );
  return data;
}

/**
 * Lista eventos eSocial com filtros
 */
export async function listarEventos(params?: {
  tipo_evento?: string;
  data_inicial?: string;
  data_final?: string;
  status?: string;
}): Promise<EventoResponse[]> {
  const { data } = await api.get<any>(
    '/api/v1/government/esocial/eventos',
    { params }
  );
  // Backend devolve envelope {success,message,data:{items,total}}; desempacota p/ {items,total}
  return (data as any)?.data ?? data;
}

/**
 * Configura empresa no eSocial (S-1000)
 */
export async function configurarEmpresa(
  params: ConfiguracaoEmpresaParams
): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/esocial/configurar-empresa',
    {
      cnpj: params.cnpj,
      razao_social: params.razao_social,
      natureza_juridica: params.natureza_juridica,
      regime_tributario: params.regime_tributario,
    }
  );
  return data;
}

/**
 * Calcula folha de pagamento
 */
export async function calcularFolha(
  params: CalculoFolhaParams
): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/esocial/calcular-folha',
    {
      mes_referencia: params.mes_referencia,
      ano_referencia: params.ano_referencia,
      colaboradores: params.colaboradores,
    }
  );
  return data;
}

/**
 * Valida evento eSocial antes de enviar
 */
export async function validarEvento(params: {
  tipo_evento: string;
  dados_evento: Record<string, unknown>;
}): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/esocial/validar-evento',
    {
      tipo_evento: params.tipo_evento,
      dados_evento: params.dados_evento,
    }
  );
  return data;
}

/**
 * Consulta tabela de eventos eSocial
 */
export async function consultarTabelaEventos(): Promise<StandardResponse> {
  const { data } = await api.get<StandardResponse>(
    '/api/v1/government/esocial/eventos-suportados'
  );
  return data;
}

/**
 * Gera lote de eventos para envio
 */
export async function gerarLoteEventos(params: {
  eventos: EventoESocialParams[];
}): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/esocial/gerar-lote',
    { eventos: params.eventos }
  );
  return data;
}

const esocialService = {
  enviarEvento,
  consultarEvento,
  listarEventos,
  configurarEmpresa,
  calcularFolha,
  validarEvento,
  consultarTabelaEventos,
  gerarLoteEventos,
};

export default esocialService;
