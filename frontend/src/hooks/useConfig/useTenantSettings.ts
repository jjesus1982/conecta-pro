/**
 * Custom Hooks - Tenant Settings
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import * as settingsService from '@/services/config/tenant-settings';
import type {
  TenantSettingsCreate,
  TenantSettingsUpdate,
  TenantSettingsValueUpdate,
} from '@/types/generated/config/conectaPROCONFIGModuleAPI.schemas';

export const tenantSettingsKeys = {
  all: ['tenant-settings'] as const,
  lists: () => [...tenantSettingsKeys.all, 'list'] as const,
  list: (tenantId: string, filters: any) => [...tenantSettingsKeys.lists(), tenantId, filters] as const,
  details: () => [...tenantSettingsKeys.all, 'detail'] as const,
  detail: (id: string) => [...tenantSettingsKeys.details(), id] as const,
};

export const useTenantSettings = (
  tenantId: string,
  params?: settingsService.ListTenantSettingsParams
) => {
  return useQuery({
    queryKey: tenantSettingsKeys.list(tenantId, params),
    queryFn: () => settingsService.listTenantSettings(tenantId, params),
    enabled: !!tenantId,
  });
};

export const useTenantSetting = (settingId: string, enabled: boolean = true) => {
  return useQuery({
    queryKey: tenantSettingsKeys.detail(settingId),
    queryFn: () => settingsService.getTenantSetting(settingId),
    enabled: enabled && !!settingId,
  });
};

export const useCreateTenantSetting = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ tenantId, data }: { tenantId: string; data: TenantSettingsCreate }) =>
      settingsService.createTenantSetting(tenantId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: tenantSettingsKeys.lists() });
      toast.success('Configuração criada!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao criar configuração');
    },
  });
};

export const useUpdateTenantSetting = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: TenantSettingsUpdate }) =>
      settingsService.updateTenantSetting(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: tenantSettingsKeys.detail(variables.id) });
      queryClient.invalidateQueries({ queryKey: tenantSettingsKeys.lists() });
      toast.success('Configuração atualizada!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao atualizar');
    },
  });
};

export const useUpdateTenantSettingValue = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, value }: { id: string; value: TenantSettingsValueUpdate }) =>
      settingsService.updateTenantSettingValue(id, value),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: tenantSettingsKeys.detail(variables.id) });
      toast.success('Valor atualizado!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao atualizar valor');
    },
  });
};

export const useResetTenantSetting = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => settingsService.resetTenantSetting(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: tenantSettingsKeys.detail(id) });
      toast.success('Configuração resetada!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao resetar');
    },
  });
};

export const useDeleteTenantSetting = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => settingsService.deleteTenantSetting(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: tenantSettingsKeys.lists() });
      toast.success('Configuração deletada!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao deletar');
    },
  });
};
