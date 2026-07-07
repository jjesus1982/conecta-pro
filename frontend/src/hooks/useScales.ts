'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { customInstance } from '@/lib/api-client';
import type { Scale, ScaleFilter, ScaleGenerateRequest, ScaleStats, PaginatedResponse } from '@/types/operacional';

const BASE_URL = '/api/v1/operacional/scales';

export interface ScaleOperationError {
  status?: number;
  message: string;
}

/**
 * Extrai status HTTP e mensagem legível de um erro (AxiosError ou Error).
 * Prioridade da mensagem: detail do backend > message do Error > fallback.
 */
function extractOperationError(err: unknown, fallback: string): ScaleOperationError {
  const axiosLike = err as { response?: { status?: number; data?: { detail?: unknown } } };
  const detail = axiosLike?.response?.data?.detail;
  const message =
    typeof detail === 'string' && detail
      ? detail
      : err instanceof Error && err.message
        ? err.message
        : fallback;
  return { status: axiosLike?.response?.status, message };
}

function buildParams(page: number, pageSize: number, filters?: ScaleFilter | Record<string, unknown>): string {
  const params = new URLSearchParams();
  params.append('page', String(page));
  params.append('page_size', String(pageSize));
  if (filters) {
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        params.append(key, String(value));
      }
    });
  }
  return params.toString();
}

export function useScales(
  initialPage: number = 1,
  initialPageSize: number = 20,
  initialFilters?: ScaleFilter
) {
  const [scales, setScales] = useState<Scale[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(initialPage);
  const [pageSize, setPageSize] = useState(initialPageSize);
  const [totalPages, setTotalPages] = useState(0);
  const [filters, setFilters] = useState<ScaleFilter | undefined>(initialFilters);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchScales = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await customInstance<PaginatedResponse<Scale>>({
        url: `${BASE_URL}/?${buildParams(page, pageSize, filters)}`,
        method: 'GET',
      });
      setScales(response.items);
      setTotal(response.total);
      setTotalPages(response.total_pages);
    } catch (err) {
      setError('Erro ao carregar escalas');
      setScales([]);
    } finally {
      setIsLoading(false);
    }
  }, [page, pageSize, filters]);

  useEffect(() => {
    fetchScales();
  }, [fetchScales]);

  const refresh = useCallback(() => {
    fetchScales();
  }, [fetchScales]);

  const updateFilters = useCallback((newFilters: ScaleFilter | undefined) => {
    setFilters(newFilters);
    setPage(1);
  }, []);

  return {
    scales,
    total,
    page,
    pageSize,
    totalPages,
    filters,
    isLoading,
    error,
    setPage,
    setPageSize,
    setFilters: updateFilters,
    refresh,
  };
}

export function useScale(id: string | null) {
  const [scale, setScale] = useState<Scale | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchScale = useCallback(async () => {
    if (!id) {
      setScale(null);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const data = await customInstance<Scale>({
        url: `${BASE_URL}/${id}`,
        method: 'GET',
      });
      setScale(data);
    } catch (err) {
      setError('Erro ao carregar escala');
      setScale(null);
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchScale();
  }, [fetchScale]);

  return {
    scale,
    isLoading,
    error,
    refresh: fetchScale,
  };
}

export function useScaleOperations() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Último erro com status HTTP, legível de forma síncrona pelas páginas
  // logo após uma operação retornar null (o state `error` não estaria fresco no closure).
  const lastErrorRef = useRef<ScaleOperationError | null>(null);

  const getLastError = useCallback((): ScaleOperationError | null => lastErrorRef.current, []);

  const generateScale = useCallback(async (data: ScaleGenerateRequest): Promise<Scale | null> => {
    setIsLoading(true);
    setError(null);
    try {
      const scale = await customInstance<Scale>({
        url: `${BASE_URL}/generate`,
        method: 'POST',
        data,
      });
      return scale;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Erro ao gerar escala';
      setError(message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const submitForApproval = useCallback(async (id: string): Promise<Scale | null> => {
    setIsLoading(true);
    setError(null);
    lastErrorRef.current = null;
    try {
      const scale = await customInstance<Scale>({
        url: `${BASE_URL}/${id}/submit`,
        method: 'POST',
      });
      return scale;
    } catch (err: unknown) {
      const opError = extractOperationError(err, 'Erro ao enviar para aprovação');
      lastErrorRef.current = opError;
      setError(opError.message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const approveScale = useCallback(async (id: string, notes?: string): Promise<Scale | null> => {
    setIsLoading(true);
    setError(null);
    lastErrorRef.current = null;
    try {
      const scale = await customInstance<Scale>({
        url: `${BASE_URL}/${id}/approve`,
        method: 'POST',
        data: { notes },
      });
      return scale;
    } catch (err: unknown) {
      const opError = extractOperationError(err, 'Erro ao aprovar escala');
      lastErrorRef.current = opError;
      setError(opError.message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const publishScale = useCallback(async (
    id: string,
    notifyEmployees: boolean = true
  ): Promise<Scale | null> => {
    setIsLoading(true);
    setError(null);
    lastErrorRef.current = null;
    try {
      const scale = await customInstance<Scale>({
        url: `${BASE_URL}/${id}/publish`,
        method: 'POST',
        data: { notify_employees: notifyEmployees },
      });
      return scale;
    } catch (err: unknown) {
      const opError = extractOperationError(err, 'Erro ao publicar escala');
      lastErrorRef.current = opError;
      setError(opError.message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const deleteScale = useCallback(async (id: string): Promise<boolean> => {
    setIsLoading(true);
    setError(null);
    try {
      await customInstance<void>({
        url: `${BASE_URL}/${id}`,
        method: 'DELETE',
      });
      return true;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Erro ao deletar escala';
      setError(message);
      return false;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return {
    isLoading,
    error,
    getLastError,
    generateScale,
    submitForApproval,
    approveScale,
    publishScale,
    deleteScale,
  };
}

export function useCurrentMonthScales() {
  const [scales, setScales] = useState<Scale[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchScales = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await customInstance<PaginatedResponse<Scale>>({
        url: `${BASE_URL}/?${buildParams(1, 100, { is_current_month: true })}`,
        method: 'GET',
      });
      setScales(response.items);
    } catch (err) {
      setError('Erro ao carregar escalas');
      setScales([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchScales();
  }, [fetchScales]);

  return {
    scales,
    isLoading,
    error,
    refresh: fetchScales,
  };
}

export function useScaleStats() {
  const [stats, setStats] = useState<ScaleStats | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await customInstance<ScaleStats>({
        url: `${BASE_URL}/stats`,
        method: 'GET',
      });
      setStats(data);
    } catch (err) {
      setError('Erro ao carregar estatísticas');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  return {
    stats,
    isLoading,
    error,
    refresh: fetchStats,
  };
}
