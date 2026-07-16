/**
 * Custom Hooks - Documents Templates
 * Hooks React Query para gestão de templates de extração
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import * as templatesService from '@/services/documents/templates';
import type { TemplateRequest } from '@/types/generated/documents';

// ==================== Query Keys ====================

export const templatesKeys = {
  all: ['documents', 'templates'] as const,
  lists: () => [...templatesKeys.all, 'list'] as const,
  list: (filters: any) => [...templatesKeys.lists(), filters] as const,
  details: () => [...templatesKeys.all, 'detail'] as const,
  detail: (id: string) => [...templatesKeys.details(), id] as const,
};

// ==================== Queries ====================

/**
 * Hook para listar templates de extração
 */
export const useTemplates = (params?: templatesService.ListTemplatesParams) => {
  return useQuery({
    queryKey: templatesKeys.list(params),
    queryFn: () => templatesService.listTemplates(params),
  });
};

/**
 * Hook para obter template específico
 */
export const useTemplate = (templateId: string, enabled: boolean = true) => {
  return useQuery({
    queryKey: templatesKeys.detail(templateId),
    queryFn: () => templatesService.getTemplate(templateId),
    enabled: enabled && !!templateId,
  });
};

// ==================== Mutations ====================

/**
 * Hook para criar template de documento
 */
export const useCreateDocumentTemplate = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: { tenant_id: string; template: TemplateRequest }) =>
      templatesService.createTemplate(params.tenant_id, params.template),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: templatesKeys.lists() });
      toast.success('Template criado com sucesso!');
    },
    onError: (error: any) => {
      const message =
        error?.response?.data?.detail?.[0]?.msg ||
        msgFromDetail(error?.response?.data?.detail) ||
        'Erro ao criar template';
      toast.error(message);
    },
  });
};

/**
 * Hook para deletar template
 */
export const useDeleteTemplate = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (templateId: string) =>
      templatesService.deleteTemplate(templateId),
    onSuccess: (_, templateId) => {
      queryClient.invalidateQueries({ queryKey: templatesKeys.lists() });
      queryClient.removeQueries({ queryKey: templatesKeys.detail(templateId) });
      toast.success('Template removido com sucesso!');
    },
    onError: (error: any) => {
      const message =
        error?.response?.data?.detail?.[0]?.msg ||
        msgFromDetail(error?.response?.data?.detail) ||
        'Erro ao remover template';
      toast.error(message);
    },
  });
};
