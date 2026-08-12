/**
 * Instância customizada do Axios para Orval
 * Adiciona interceptors, tratamento de erros e headers padrão
 */

import axios, { AxiosError, AxiosRequestConfig, AxiosResponse } from 'axios';

// Base URL da API — usa detecção inteligente igual a api.ts
const getBaseURL = (): string => {
  return process.env.NEXT_PUBLIC_API_URL || 'https://erp.conectamais.pro';
};
const BASE_URL = getBaseURL();

// Criar instância do axios
export const axiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor - adicionar token de autenticação
axiosInstance.interceptors.request.use(
  (config) => {
    // Adicionar token do localStorage se existir
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('access_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor - tratamento de erros
axiosInstance.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    // Tratar erro 401 - redirecionar para login
    if (error.response?.status === 401) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('access_token');
        document.cookie = 'auth_token=; path=/; max-age=0';
        window.location.href = '/login';
      }
    }

    // Tratar erro 403 - sem permissão
    if (error.response?.status === 403) {
      void error;
    }

    // Tratar erro 500 - erro do servidor
    if (error.response?.status === 500) {
      void error;
    }

    return Promise.reject(error);
  }
);

/**
 * Função customizada para uso com Orval
 * Exporta uma função que o Orval pode usar como mutator
 */
const customInstanceBase = <T>(
  config: AxiosRequestConfig,
  options?: AxiosRequestConfig
): Promise<T> => {
  const source = axios.CancelToken.source();

  const promise = axiosInstance({
    ...config,
    ...options,
    cancelToken: source.token,
  }).then(({ data }: AxiosResponse<T>) => data);

  // @ts-ignore
  promise.cancel = () => {
    source.cancel('Query was cancelled');
  };

  return promise;
};

/**
 * CustomInstance com métodos HTTP helper
 */
export const customInstance = Object.assign(customInstanceBase, {
  get: <T>(url: string, config?: AxiosRequestConfig): Promise<T> => {
    return customInstanceBase<T>({ ...config, method: 'GET', url });
  },
  post: <T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> => {
    return customInstanceBase<T>({ ...config, method: 'POST', url, data });
  },
  put: <T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> => {
    return customInstanceBase<T>({ ...config, method: 'PUT', url, data });
  },
  patch: <T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> => {
    return customInstanceBase<T>({ ...config, method: 'PATCH', url, data });
  },
  delete: <T>(url: string, config?: AxiosRequestConfig): Promise<T> => {
    return customInstanceBase<T>({ ...config, method: 'DELETE', url });
  },
});

// Type para o customInstance
export type CustomInstance<T> = {
  (config: AxiosRequestConfig, options?: AxiosRequestConfig): Promise<T>;
  get: <T>(url: string, config?: AxiosRequestConfig) => Promise<T>;
  post: <T>(url: string, data?: any, config?: AxiosRequestConfig) => Promise<T>;
  put: <T>(url: string, data?: any, config?: AxiosRequestConfig) => Promise<T>;
  patch: <T>(url: string, data?: any, config?: AxiosRequestConfig) => Promise<T>;
  delete: <T>(url: string, config?: AxiosRequestConfig) => Promise<T>;
  cancel?: () => void;
};

export default customInstance;
