import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';

// Detectar ambiente via variáveis de ambiente
const getBaseURL = (): string => {
  // Sempre priorizar a variável de ambiente
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }

  // Fallback: produção
  return 'https://erp.conectamais.pro';
};

// Páginas PRÉ-LOGIN (públicas): um 401 de chamada de fundo aqui (ex.: token velho no
// storage) NÃO pode redirecionar o usuário pro /login — a página é usada sem sessão.
// Ex.: /homologacao (autocadastro) travava quem tinha sessão antiga de admin no celular.
const PRE_LOGIN_PATHS = [
  '/login', '/homologacao', '/cadastro', '/forgot-password',
  '/reset-password', '/portal-funcionario', '/area-cliente', '/offline',
];
function emPaginaPreLogin(): boolean {
  if (typeof window === 'undefined') return false;
  const p = window.location.pathname;
  return PRE_LOGIN_PATHS.some((r) => p === r || p.startsWith(r + '/'));
}

// Instância Axios configurada
export const api: AxiosInstance = axios.create({
  baseURL: getBaseURL(),
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
    'X-App-Version': process.env.NEXT_PUBLIC_APP_VERSION || '2.0.0',
  },
});

// Interceptor de request - adiciona token
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = typeof window !== 'undefined'
      ? localStorage.getItem('access_token')
      : null;

    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
  },
  (error) => Promise.reject(error)
);

// Interceptor de response - trata erros
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean; _retryCount?: number };

    // Backend startup retry — 502/503/504 ou network error
    const status = error.response?.status;
    if ((status === 502 || status === 503 || status === 504 || !error.response) && !originalRequest._retry) {
      const retryCount = originalRequest._retryCount || 0;
      if (retryCount < 2) {
        originalRequest._retryCount = retryCount + 1;
        await new Promise(resolve => setTimeout(resolve, 3000));
        return api(originalRequest);
      }
    }

    // Token expirado ou não autenticado - tentar refresh
    if ((error.response?.status === 401 || error.response?.status === 403) && !originalRequest._retry) {
      originalRequest._retry = true;

      // Nunca redirecionar a partir de páginas pré-login (login/homologação/cadastro…):
      // limpa tokens velhos e deixa a página pública funcionar sem bounce pro /login.
      if (emPaginaPreLogin()) {
        try {
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
        } catch { /* storage indisponível */ }
        return Promise.reject(error);
      }

      try {
        const refreshToken = localStorage.getItem('refresh_token');
        if (refreshToken) {
          const response = await axios.post(`${getBaseURL()}/api/v1/auth/refresh`, {
            refresh_token: refreshToken,
          });

          const { access_token, refresh_token: newRefreshToken } = response.data;

          localStorage.setItem('access_token', access_token);
          if (newRefreshToken) {
            localStorage.setItem('refresh_token', newRefreshToken);
          }
          // Atualizar cookie com o novo token
          if (typeof window !== 'undefined') {
            const isSecure = window.location.protocol === 'https:';
            document.cookie = `auth_token=${access_token}; path=/; max-age=${30 * 60}; SameSite=Lax${isSecure ? '; Secure' : ''}`;
          }

          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${access_token}`;
          }

          return api(originalRequest);
        } else {
          // Sem refresh token e com acesso autenticado — limpar e redirecionar
          const hasSession = typeof window !== 'undefined' && localStorage.getItem('access_token');
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          if (typeof window !== 'undefined' && hasSession) {
            document.cookie = 'auth_token=; path=/; max-age=0';
            window.location.href = '/login';
          }
        }
      } catch (refreshError) {
        // Refresh falhou - limpar tokens e redirecionar
        const hasSession = typeof window !== 'undefined' && localStorage.getItem('access_token');
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');

        if (typeof window !== 'undefined' && hasSession) {
          document.cookie = 'auth_token=; path=/; max-age=0';
          window.location.href = '/login';
        }
      }
    }

    return Promise.reject(error);
  }
);

// Tipos de erro padronizados
export interface ApiError {
  message: string;
  code: string;
  details?: Record<string, unknown>;
}

// Helper para extrair mensagem de erro
export const getErrorMessage = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as ApiError | undefined;
    return data?.message || error.message || 'Erro de conexão com o servidor';
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'Erro desconhecido';
};

// Export da instância para uso com Orval
export const axiosInstance = api;
export default api;
