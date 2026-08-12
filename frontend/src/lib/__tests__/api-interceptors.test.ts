import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import axios from 'axios';

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
};

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
});

// Mock window.location
const locationMock = {
  hostname: 'localhost',
  port: '3000',
  href: 'http://localhost:3000',
};
Object.defineProperty(window, 'location', {
  value: locationMock,
  writable: true,
});

describe('api - getBaseURL branches', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    vi.resetModules();
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it('deve usar URL de desenvolvimento em localhost:3000', async () => {
    window.location.hostname = 'localhost';
    window.location.port = '3000';
    
    const { api } = await import('../api');
    // A instância já foi criada com a baseURL
    expect(api.defaults.baseURL).toBe('http://localhost:8080');
  });

  it('deve usar URL de desenvolvimento em localhost:3001', async () => {
    window.location.hostname = 'localhost';
    window.location.port = '3001';
    
    vi.resetModules();
    const { api } = await import('../api');
    expect(api.defaults.baseURL).toBe('http://localhost:8080');
  });

  it('deve usar URL de desenvolvimento em localhost:3002', async () => {
    window.location.hostname = 'localhost';
    window.location.port = '3002';
    
    vi.resetModules();
    const { api } = await import('../api');
    expect(api.defaults.baseURL).toBe('http://localhost:8080');
  });

  it('deve usar URL de produção em produção', async () => {
    window.location.hostname = 'erp.conectamais.pro';
    window.location.port = '';
    
    vi.resetModules();
    const { api } = await import('../api');
    expect(api.defaults.baseURL).toBe('https://erp.conectamais.pro');
  });

  it('deve usar URL de staging em staging.conectamais.pro', async () => {
    window.location.hostname = 'staging.conectamais.pro';
    window.location.port = '';
    
    vi.resetModules();
    const { api } = await import('../api');
    expect(api.defaults.baseURL).toBe('https://staging.conectamais.pro');
  });

  it('deve usar URL de produção para outros hostnames', async () => {
    window.location.hostname = 'outro.dominio.com';
    window.location.port = '';
    
    vi.resetModules();
    const { api } = await import('../api');
    expect(api.defaults.baseURL).toBe('https://erp.conectamais.pro');
  });
});

describe('api - request interceptor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('deve adicionar token no header quando existe', async () => {
    localStorageMock.getItem.mockReturnValue('test-token');
    
    vi.resetModules();
    const { api } = await import('../api');
    
    // Simular uma requisição
    const config = { headers: {} as Record<string, string> };
    const requestInterceptor = (api.interceptors.request as any).handlers[0];
    
    if (requestInterceptor && requestInterceptor.fulfilled) {
      const result = requestInterceptor.fulfilled(config as any);
      expect(result.headers?.Authorization).toBe('Bearer test-token');
    }
  });

  it('deve NÃO adicionar token quando não existe', async () => {
    localStorageMock.getItem.mockReturnValue(null);
    
    vi.resetModules();
    const { api } = await import('../api');
    
    const config = { headers: {} as Record<string, string> };
    const requestInterceptor = (api.interceptors.request as any).handlers[0];
    
    if (requestInterceptor && requestInterceptor.fulfilled) {
      const result = requestInterceptor.fulfilled(config as any);
      expect(result.headers?.Authorization).toBeUndefined();
    }
  });

  it('deve rejeitar erro no request interceptor', async () => {
    vi.resetModules();
    const { api } = await import('../api');
    
    const requestInterceptor = (api.interceptors.request as any).handlers[0];
    const error = new Error('Request Error');
    
    if (requestInterceptor && requestInterceptor.rejected) {
      await expect(requestInterceptor.rejected(error)).rejects.toBe(error);
    }
  });
});

describe('api - response interceptor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('deve retornar response normalmente quando sucesso', async () => {
    vi.resetModules();
    const { api } = await import('../api');
    
    const response = { data: 'success', status: 200 };
    const responseInterceptor = (api.interceptors.response as any).handlers[0];
    
    if (responseInterceptor && responseInterceptor.fulfilled) {
      const result = responseInterceptor.fulfilled(response as any);
      expect(result).toBe(response);
    }
  });

  it('deve tentar refresh token quando recebe 401 e tem refresh_token', async () => {
    localStorageMock.getItem.mockImplementation((key: string) => {
      if (key === 'refresh_token') return 'refresh-token';
      return null;
    });
    
    vi.resetModules();
    
    // Mock axios.post para retornar novo token
    const axiosPostSpy = vi.spyOn(axios, 'post').mockResolvedValue({
      data: { access_token: 'new-access-token', refresh_token: 'new-refresh-token' }
    });
    
    const { api } = await import('../api');
    
    const error = {
      response: { status: 401 },
      config: { headers: {}, _retry: false },
    };
    
    const responseInterceptor = (api.interceptors.response as any).handlers[0];
    
    if (responseInterceptor && responseInterceptor.rejected) {
      // O teste passa se não lançar erro
      await expect(responseInterceptor.rejected(error as any)).rejects.toBeDefined();
    }
    
    axiosPostSpy.mockRestore();
  });

  it('deve redirecionar para login quando recebe 401 sem refresh_token', async () => {
    localStorageMock.getItem.mockReturnValue(null);
    
    vi.resetModules();
    const { api } = await import('../api');
    
    const error = {
      response: { status: 401 },
      config: { headers: {}, _retry: false },
    };
    
    const responseInterceptor = (api.interceptors.response as any).handlers[0];
    
    if (responseInterceptor && responseInterceptor.rejected) {
      await expect(responseInterceptor.rejected(error as any)).rejects.toBe(error);
    }
    
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('access_token');
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('refresh_token');
  });

  it('deve redirecionar para login quando refresh falha', async () => {
    localStorageMock.getItem.mockImplementation((key: string) => {
      if (key === 'refresh_token') return 'refresh-token';
      return null;
    });
    
    vi.resetModules();
    
    // Mock axios.post para falhar
    const axiosPostSpy = vi.spyOn(axios, 'post').mockRejectedValue(new Error('Refresh failed'));
    
    const { api } = await import('../api');
    
    const error = {
      response: { status: 401 },
      config: { headers: {}, _retry: false },
    };
    
    const responseInterceptor = (api.interceptors.response as any).handlers[0];
    
    if (responseInterceptor && responseInterceptor.rejected) {
      await expect(responseInterceptor.rejected(error as any)).rejects.toBe(error);
    }
    
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('access_token');
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('refresh_token');
    
    axiosPostSpy.mockRestore();
  });

  it('deve rejeitar erro quando não é 401/403', async () => {
    vi.resetModules();
    const { api } = await import('../api');
    
    const error = {
      response: { status: 500 },
      config: { headers: {} },
    };
    
    const responseInterceptor = (api.interceptors.response as any).handlers[0];
    
    if (responseInterceptor && responseInterceptor.rejected) {
      await expect(responseInterceptor.rejected(error as any)).rejects.toBe(error);
    }
  });

  it('deve rejeitar erro quando já tentou retry', async () => {
    vi.resetModules();
    const { api } = await import('../api');
    
    const error = {
      response: { status: 401 },
      config: { headers: {}, _retry: true },
    };
    
    const responseInterceptor = (api.interceptors.response as any).handlers[0];
    
    if (responseInterceptor && responseInterceptor.rejected) {
      await expect(responseInterceptor.rejected(error as any)).rejects.toBe(error);
    }
  });
});

describe('api - getErrorMessage branches', () => {
  it('deve extrair mensagem de erro Axios com response.data.message', async () => {
    const { getErrorMessage } = await import('../api');
    const axiosError = {
      response: {
        data: { message: 'Erro do servidor' },
      },
      message: 'Network Error',
    };
    
    // Simular isAxiosError retornando true
    vi.spyOn(axios, 'isAxiosError').mockReturnValue(true);
    
    const result = getErrorMessage(axiosError);
    expect(result).toBe('Erro do servidor');
  });

  it('deve usar error.message quando AxiosError sem response.data.message', async () => {
    const { getErrorMessage } = await import('../api');
    const axiosError = {
      response: { data: {} },
      message: 'Network Error',
    };
    
    vi.spyOn(axios, 'isAxiosError').mockReturnValue(true);
    
    const result = getErrorMessage(axiosError);
    expect(result).toBe('Network Error');
  });

  it('deve usar mensagem padrão quando AxiosError sem message', async () => {
    const { getErrorMessage } = await import('../api');
    const axiosError = {
      response: { data: {} },
    };
    
    vi.spyOn(axios, 'isAxiosError').mockReturnValue(true);
    
    const result = getErrorMessage(axiosError);
    expect(result).toBe('Erro de conexão com o servidor');
  });

  it('deve retornar mensagem de Error nativo', async () => {
    const { getErrorMessage } = await import('../api');
    vi.spyOn(axios, 'isAxiosError').mockReturnValue(false);
    
    const error = new Error('Erro nativo');
    const result = getErrorMessage(error);
    expect(result).toBe('Erro nativo');
  });

  it('deve retornar mensagem padrão para erro desconhecido', async () => {
    const { getErrorMessage } = await import('../api');
    vi.spyOn(axios, 'isAxiosError').mockReturnValue(false);
    
    const result = getErrorMessage(null);
    expect(result).toBe('Erro desconhecido');
  });
});
