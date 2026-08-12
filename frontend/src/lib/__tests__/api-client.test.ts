import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';

// Mock do api.ts
const mockRequest = vi.fn();

vi.mock('../api', () => ({
  api: {
    request: (...args: any[]) => mockRequest(...args),
  },
}));

describe('customInstance', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('deve fazer requisição e retornar dados', async () => {
    const { customInstance } = await import('../api-client');
    
    mockRequest.mockResolvedValueOnce({ data: { id: 1, name: 'Test' } });
    
    const result = await customInstance({ url: '/api/test', method: 'GET' });
    
    expect(result).toEqual({ id: 1, name: 'Test' });
    expect(mockRequest).toHaveBeenCalledWith(expect.objectContaining({
      url: '/api/test',
      method: 'GET',
    }));
  });

  it('deve remover barra final da URL', async () => {
    const { customInstance } = await import('../api-client');
    
    mockRequest.mockResolvedValueOnce({ data: {} });
    
    await customInstance({ url: '/api/test/', method: 'GET' });
    
    expect(mockRequest).toHaveBeenCalledWith(expect.objectContaining({
      url: '/api/test',
    }));
  });

  it('deve preservar URL que termina com protocolo://', async () => {
    const { customInstance } = await import('../api-client');
    
    mockRequest.mockResolvedValueOnce({ data: {} });
    
    // URL com barra final mas que termina com :// não deve ser modificada
    // porque isso provavelmente é um protocolo como http://
    await customInstance({ url: 'http://example.com/api/', method: 'GET' });
    
    expect(mockRequest).toHaveBeenCalledWith(expect.objectContaining({
      url: 'http://example.com/api',
    }));
  });

  it('deve remover duplicações de path', async () => {
    const { customInstance } = await import('../api-client');
    
    mockRequest.mockResolvedValueOnce({ data: {} });
    
    await customInstance({ url: '/api/suppliers/suppliers/', method: 'GET' });
    
    expect(mockRequest).toHaveBeenCalledWith(expect.objectContaining({
      url: '/api/suppliers',
    }));
  });

  it('deve remover duplicações de path sem barra final', async () => {
    const { customInstance } = await import('../api-client');
    
    mockRequest.mockResolvedValueOnce({ data: {} });
    
    await customInstance({ url: '/api/users/users', method: 'GET' });
    
    expect(mockRequest).toHaveBeenCalledWith(expect.objectContaining({
      url: '/api/users',
    }));
  });

  it('deve adicionar condominio_id para endpoints financial sem params', async () => {
    const { customInstance } = await import('../api-client');
    
    mockRequest.mockResolvedValueOnce({ data: {} });
    
    await customInstance({ url: '/api/financial/budgets', method: 'GET' });
    
    expect(mockRequest).toHaveBeenCalledWith(expect.objectContaining({
      url: '/api/financial/budgets',
      params: expect.objectContaining({
        condominio_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      }),
    }));
  });

  it('deve adicionar condominio_id para endpoints financial com params existente', async () => {
    const { customInstance } = await import('../api-client');
    
    mockRequest.mockResolvedValueOnce({ data: {} });
    
    await customInstance({ 
      url: '/api/financial/invoices', 
      method: 'GET',
      params: { status: 'paid' },
    });
    
    expect(mockRequest).toHaveBeenCalledWith(expect.objectContaining({
      url: '/api/financial/invoices',
      params: expect.objectContaining({
        status: 'paid',
        condominio_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      }),
    }));
  });

  it('deve preservar condominio_id existente', async () => {
    const { customInstance } = await import('../api-client');
    
    mockRequest.mockResolvedValueOnce({ data: {} });
    
    await customInstance({ 
      url: '/api/financial/reports', 
      method: 'GET',
      params: { condominio_id: 'existing-id' },
    });
    
    expect(mockRequest).toHaveBeenCalledWith(expect.objectContaining({
      url: '/api/financial/reports',
      params: expect.objectContaining({
        condominio_id: 'existing-id',
      }),
    }));
  });

  it('deve NÃO adicionar condominio_id para endpoints não-financial', async () => {
    const { customInstance } = await import('../api-client');
    
    mockRequest.mockResolvedValueOnce({ data: {} });
    
    await customInstance({ url: '/api/users', method: 'GET' });
    
    const callArg = mockRequest.mock.calls[0]![0];
    expect(callArg.url).toBe('/api/users');
    expect(callArg.params).toBeUndefined();
  });

  it('deve propagar erro do Axios', async () => {
    const { customInstance } = await import('../api-client');
    
    const axiosError = new Error('Network Error') as any;
    axiosError.isAxiosError = true;
    mockRequest.mockRejectedValueOnce(axiosError);
    
    await expect(customInstance({ url: '/api/test', method: 'GET' }))
      .rejects.toBe(axiosError);
  });

  it('deve propagar erro genérico', async () => {
    const { customInstance } = await import('../api-client');
    
    const error = new Error('Generic Error');
    mockRequest.mockRejectedValueOnce(error);
    
    await expect(customInstance({ url: '/api/test', method: 'GET' }))
      .rejects.toBe(error);
  });

  it('deve lidar com URL undefined', async () => {
    const { customInstance } = await import('../api-client');
    
    mockRequest.mockResolvedValueOnce({ data: {} });
    
    await customInstance({ method: 'GET' });
    
    expect(mockRequest).toHaveBeenCalledWith(expect.objectContaining({
      method: 'GET',
    }));
  });
});
