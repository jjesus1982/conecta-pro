'use client';

import { useState, useEffect, useCallback } from 'react';
import { customInstance } from '@/lib/api-client';

// A rota montada e /operacional/scales/templates/. O valor anterior
// (/operacional/templates-escalas) nunca existiu — templates de escala estavam
// quebrados desde sempre por nome errado.
const BASE = '/api/v1/operacional/scales/templates';

const scaleTemplatesService = {
  list: (page: number, pageSize: number, filters?: Record<string, unknown>) =>
    customInstance({ url: `${BASE}/`, method: 'GET', params: { page, page_size: pageSize, ...filters } }),
  getById: (id: string) =>
    customInstance({ url: `${BASE}/${id}`, method: 'GET' }),
  create: (data: unknown) =>
    customInstance({ url: `${BASE}/`, method: 'POST', data }),
  update: (id: string, data: unknown) =>
    customInstance({ url: `${BASE}/${id}`, method: 'PATCH', data }),
  delete: (id: string) =>
    customInstance({ url: `${BASE}/${id}`, method: 'DELETE' }),
  apply: (id: string, data: unknown) =>
    customInstance({ url: `${BASE}/${id}/apply`, method: 'POST', data }),
  // sem preview: o backend nunca expos dry-run de template (so /apply, que cria a
  // escala de verdade). Manter o botao seria prometer uma previa que da 404.
};
import { useToast } from '@/components/ui/use-toast';
import type {
  ScaleTemplate,
  ScaleTemplateCreate,
  ScaleTemplateUpdate,
  ScaleTemplateApply,
  ScaleTemplateFilter,
  Scale,
  PaginatedResponse,
} from '@/types/operacional';

/**
 * Hook para listar templates com paginação e filtros
 */
export function useTemplates(
  initialPage: number = 1,
  initialPageSize: number = 50,
  initialFilters?: ScaleTemplateFilter
) {
  const [templates, setTemplates] = useState<ScaleTemplate[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(initialPage);
  const [pageSize, setPageSize] = useState(initialPageSize);
  const [totalPages, setTotalPages] = useState(0);
  const [filters, setFilters] = useState<ScaleTemplateFilter | undefined>(initialFilters);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTemplates = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await scaleTemplatesService.list(page, pageSize, filters as Record<string, unknown> | undefined) as PaginatedResponse<ScaleTemplate>;
      setTemplates(response.items);
      setTotal(response.total);
      setTotalPages(response.total_pages);
    } catch (err) {

      setError('Erro ao carregar templates');
      setTemplates([]);
    } finally {
      setIsLoading(false);
    }
  }, [page, pageSize, filters]);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  const refresh = useCallback(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  const updateFilters = useCallback((newFilters: ScaleTemplateFilter | undefined) => {
    setFilters(newFilters);
    setPage(1);
  }, []);

  return {
    templates,
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

/**
 * Hook para buscar template individual
 */
export function useTemplate(id: string | null) {
  const [template, setTemplate] = useState<ScaleTemplate | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTemplate = useCallback(async () => {
    if (!id) {
      setTemplate(null);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const data = await scaleTemplatesService.getById(id) as ScaleTemplate;
      setTemplate(data);
    } catch (err) {

      setError('Erro ao carregar template');
      setTemplate(null);
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchTemplate();
  }, [fetchTemplate]);

  return {
    template,
    isLoading,
    error,
    refresh: fetchTemplate,
  };
}

/**
 * Hook para operações de template (mutations)
 */
export function useTemplateOperations() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();

  const createTemplate = useCallback(async (data: ScaleTemplateCreate): Promise<ScaleTemplate | null> => {
    setIsLoading(true);
    setError(null);
    try {
      const template = await scaleTemplatesService.create(data) as ScaleTemplate;
      toast({
        title: 'Template criado!',
        description: `Template "${data.name}" foi criado com sucesso.`,
      });
      return template;
    } catch (err: unknown) {

      const message = err instanceof Error ? err.message : 'Erro ao criar template';
      setError(message);
      toast({
        title: 'Erro ao criar template',
        description: message,
        variant: 'destructive',
      });
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  const updateTemplate = useCallback(async (
    id: string,
    data: ScaleTemplateUpdate
  ): Promise<ScaleTemplate | null> => {
    setIsLoading(true);
    setError(null);
    try {
      const template = await scaleTemplatesService.update(id, data) as ScaleTemplate;
      toast({
        title: 'Template atualizado!',
        description: 'As alterações foram salvas com sucesso.',
      });
      return template;
    } catch (err: unknown) {

      const message = err instanceof Error ? err.message : 'Erro ao atualizar template';
      setError(message);
      toast({
        title: 'Erro ao atualizar template',
        description: message,
        variant: 'destructive',
      });
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  const deleteTemplate = useCallback(async (id: string): Promise<boolean> => {
    setIsLoading(true);
    setError(null);
    try {
      await scaleTemplatesService.delete(id);
      toast({
        title: 'Template excluído!',
        description: 'O template foi removido com sucesso.',
      });
      return true;
    } catch (err: unknown) {

      const message = err instanceof Error ? err.message : 'Erro ao deletar template';
      setError(message);
      toast({
        title: 'Erro ao excluir template',
        description: message,
        variant: 'destructive',
      });
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  const applyTemplate = useCallback(async (
    id: string,
    data: ScaleTemplateApply
  ): Promise<Scale | null> => {
    setIsLoading(true);
    setError(null);
    try {
      const scale = await scaleTemplatesService.apply(id, data) as Scale;
      toast({
        title: 'Escala criada!',
        description: 'A escala foi gerada a partir do template com sucesso.',
      });
      return scale;
    } catch (err: unknown) {

      const message = err instanceof Error ? err.message : 'Erro ao aplicar template';
      setError(message);
      toast({
        title: 'Erro ao aplicar template',
        description: message,
        variant: 'destructive',
      });
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  return {
    isLoading,
    error,
    createTemplate,
    updateTemplate,
    deleteTemplate,
    applyTemplate,
  };
}
