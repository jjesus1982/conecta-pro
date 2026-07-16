/**
 * Custom Hooks - Tenants
 * Hooks React Query de alto nível para gestão de tenants
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import * as tenantsService from '@/services/config/tenants';
import type {
  TenantCreate,
  TenantUpdate,
  TenantPlanUpdate,
  TenantAddressUpdate,
} from '@/types/generated/config/conectaPROCONFIGModuleAPI.schemas';

// ==================== Query Keys ====================

export const tenantsKeys = {
  all: ['tenants'] as const,
  lists: () => [...tenantsKeys.all, 'list'] as const,
  list: (filters: any) => [...tenantsKeys.lists(), filters] as const,
  details: () => [...tenantsKeys.all, 'detail'] as const,
  detail: (id: string) => [...tenantsKeys.details(), id] as const,
  stats: () => [...tenantsKeys.all, 'stats'] as const,
};

// ==================== Queries ====================

/**
 * Hook para listar tenants
 */
export const useTenants = (params?: tenantsService.ListTenantsParams) => {
  return useQuery({
    queryKey: tenantsKeys.list(params),
    queryFn: () => tenantsService.listTenants(params),
  });
};

/**
 * Hook para obter tenant específico
 */
export const useTenant = (tenantId: string, enabled: boolean = true) => {
  return useQuery({
    queryKey: tenantsKeys.detail(tenantId),
    queryFn: () => tenantsService.getTenant(tenantId),
    enabled: enabled && !!tenantId,
  });
};

/**
 * Hook para calcular estatísticas de tenants
 */
export const useTenantsStats = () => {
  const { data: tenants } = useTenants();

  return useQuery({
    queryKey: tenantsKeys.stats(),
    queryFn: () => {
      if (!tenants?.items) return null;
      return tenantsService.calculateTenantStats(tenants.items);
    },
    enabled: !!tenants?.items,
  });
};

// ==================== Mutations ====================

/**
 * Hook para criar tenant
 */
export const useCreateTenant = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: TenantCreate) => tenantsService.createTenant(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: tenantsKeys.lists() });
      toast.success('Tenant criado com sucesso!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao criar tenant');
    },
  });
};

/**
 * Hook para atualizar tenant
 */
export const useUpdateTenant = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: TenantUpdate }) =>
      tenantsService.updateTenant(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: tenantsKeys.detail(variables.id) });
      queryClient.invalidateQueries({ queryKey: tenantsKeys.lists() });
      toast.success('Tenant atualizado com sucesso!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao atualizar tenant');
    },
  });
};

/**
 * Hook para deletar tenant
 */
export const useDeleteTenant = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => tenantsService.deleteTenant(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: tenantsKeys.lists() });
      toast.success('Tenant deletado com sucesso!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao deletar tenant');
    },
  });
};

// ==================== Plano ====================

/**
 * Hook para atualizar plano do tenant
 */
export const useUpdateTenantPlan = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, plan }: { id: string; plan: TenantPlanUpdate }) =>
      tenantsService.updateTenantPlan(id, plan),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: tenantsKeys.detail(variables.id) });
      queryClient.invalidateQueries({ queryKey: tenantsKeys.lists() });
      toast.success('Plano atualizado com sucesso!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao atualizar plano');
    },
  });
};

// ==================== Endereço ====================

/**
 * Hook para atualizar endereço do tenant
 */
export const useUpdateTenantAddress = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, address }: { id: string; address: TenantAddressUpdate }) =>
      tenantsService.updateTenantAddress(id, address),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: tenantsKeys.detail(variables.id) });
      toast.success('Endereço atualizado com sucesso!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao atualizar endereço');
    },
  });
};

// ==================== Status ====================

/**
 * Hook para ativar tenant
 */
export const useActivateTenant = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => tenantsService.activateTenant(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: tenantsKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: tenantsKeys.lists() });
      toast.success('Tenant ativado com sucesso!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao ativar tenant');
    },
  });
};

/**
 * Hook para suspender tenant
 */
export const useSuspendTenant = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => tenantsService.suspendTenant(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: tenantsKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: tenantsKeys.lists() });
      toast.success('Tenant suspenso com sucesso!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao suspender tenant');
    },
  });
};

/**
 * Hook para cancelar tenant
 */
export const useCancelTenant = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => tenantsService.cancelTenant(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: tenantsKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: tenantsKeys.lists() });
      toast.success('Tenant cancelado com sucesso!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao cancelar tenant');
    },
  });
};

/**
 * Hook para converter trial
 */
export const useConvertTrialTenant = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => tenantsService.convertTrialTenant(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: tenantsKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: tenantsKeys.lists() });
      toast.success('Trial convertido com sucesso!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao converter trial');
    },
  });
};

// ==================== Features ====================

/**
 * Hook para habilitar feature
 */
export const useEnableTenantFeature = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, feature }: { id: string; feature: string }) =>
      tenantsService.enableTenantFeature(id, feature),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: tenantsKeys.detail(variables.id) });
      toast.success('Feature habilitada com sucesso!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao habilitar feature');
    },
  });
};

/**
 * Hook para desabilitar feature
 */
export const useDisableTenantFeature = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, feature }: { id: string; feature: string }) =>
      tenantsService.disableTenantFeature(id, feature),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: tenantsKeys.detail(variables.id) });
      toast.success('Feature desabilitada com sucesso!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao desabilitar feature');
    },
  });
};
