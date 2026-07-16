/**
 * Custom Hooks - System Config
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import * as systemConfigService from '@/services/config/system-config';
import type {
  SystemConfigCreate,
  SystemConfigUpdate,
} from '@/types/generated/config/conectaPROCONFIGModuleAPI.schemas';

export const systemConfigKeys = {
  all: ['system-config'] as const,
  lists: () => [...systemConfigKeys.all, 'list'] as const,
  list: (filters: any) => [...systemConfigKeys.lists(), filters] as const,
  details: () => [...systemConfigKeys.all, 'detail'] as const,
  detail: (id: string) => [...systemConfigKeys.details(), id] as const,
};

export const useSystemConfigs = (params?: systemConfigService.ListSystemConfigParams) => {
  return useQuery({
    queryKey: systemConfigKeys.list(params),
    queryFn: () => systemConfigService.listSystemConfigs(params),
  });
};

export const useSystemConfig = (configId: string, enabled: boolean = true) => {
  return useQuery({
    queryKey: systemConfigKeys.detail(configId),
    queryFn: () => systemConfigService.getSystemConfig(configId),
    enabled: enabled && !!configId,
  });
};

export const useCreateSystemConfig = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: SystemConfigCreate) => systemConfigService.createSystemConfig(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: systemConfigKeys.lists() });
      toast.success('Configuração criada!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao criar');
    },
  });
};

export const useUpdateSystemConfig = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: SystemConfigUpdate }) =>
      systemConfigService.updateSystemConfig(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: systemConfigKeys.detail(variables.id) });
      queryClient.invalidateQueries({ queryKey: systemConfigKeys.lists() });
      toast.success('Configuração atualizada!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao atualizar');
    },
  });
};

export const useDeleteSystemConfig = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => systemConfigService.deleteSystemConfig(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: systemConfigKeys.lists() });
      toast.success('Configuração deletada!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao deletar');
    },
  });
};
