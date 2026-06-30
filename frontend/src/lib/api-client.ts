/**
 * Custom Axios instance for Orval-generated API clients
 * Reutiliza a instância configurada do api.ts com interceptors
 */

import { api } from './api';
import type { AxiosRequestConfig, AxiosResponse, AxiosError } from 'axios';

// Condominio ID padrão para desenvolvimento
// TODO: Obter dinamicamente do contexto do usuário em produção
const DEFAULT_CONDOMINIO_ID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';

export const customInstance = async <T>(
  configOrUrl: AxiosRequestConfig | string,
  options?: RequestInit | AxiosRequestConfig,
): Promise<T> => {
  // Support both (config) and (url, options) calling conventions from orval
  let config: AxiosRequestConfig;
  if (typeof configOrUrl === 'string') {
    config = { url: configOrUrl, ...(options as AxiosRequestConfig) };
  } else {
    config = configOrUrl;
  }

  try {
    if (config.url) {
      if (config.url.includes('/api/v1/financial/')) {
        // O client orval do financeiro gera prefixo DOBRADO (/financial/X/X/...),
        // mas o backend serve SINGLE e sem barra final (redirect_slashes=False).
        // Mapeamento confirmado empiricamente endpoint-a-endpoint:
        let u = config.url;
        // 1) casos plural (não são duplicação exata)
        u = u.replace('/financial/purchase/purchases', '/financial/purchases');
        u = u.replace('/financial/bank-reconciliation/bank-reconciliations', '/financial/bank-reconciliations');
        // 2) colapsa segmento imediatamente duplicado: /financial/X/X -> /financial/X (inclui cashflow)
        u = u.replace(/\/financial\/([^/]+)\/\1(?=\/|$|\?)/, '/financial/$1');
        // 3) remove barra final (rota de listagem) — backend não aceita trailing slash
        u = u.replace(/\/(?=\?|$)/, '');
        config.url = u;

        // condominio_id default p/ endpoints multi-tenant do Financial
        if (!config.params) {
          config.params = {};
        }
        if (!config.params.condominio_id) {
          config.params.condominio_id = DEFAULT_CONDOMINIO_ID;
        }
      } else if (config.url.includes('/lgpd/') && !config.url.includes('/security/lgpd/')) {
        // Client LGPD gera /lgpd/...; backend monta sob /security (real: /security/lgpd/...)
        config.url = config.url.replace('/lgpd/', '/security/lgpd/');
      } else if (config.url.includes('/campo/guardian/')) {
        // Resíduo do módulo Guardian (removido na reorg): /campo/guardian/campo/campo/* -> /campo/*
        config.url = config.url
          .replace('/campo/guardian/campo/campo', '/campo')
          .replace('/campo/guardian/cyber', '/campo/cyber')
          .replace('/campo/guardian/', '/campo/');
      } else {
        // Demais módulos (inclui integrações: colapsa /integrations/integrations/connectors -> single)
        config.url = config.url.replace(/\/([^\/]+)\/\1(?=\/|$|\?)/, '/$1');
      }
    }

    const response: AxiosResponse<T> = await api.request<T>(config);
    return response.data;
  } catch (error) {
    // Propagar erro do Axios para tratamento do React Query
    throw error as AxiosError;
  }
};

export default customInstance;
