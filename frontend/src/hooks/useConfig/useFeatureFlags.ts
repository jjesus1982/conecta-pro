/**
 * Custom Hooks - Feature Flags
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import * as featureFlagsService from '@/services/config/feature-flags';
import type {
  FeatureFlagCreate,
  FeatureFlagUpdate,
  FeatureFlagGradualRollout,
  FeatureFlagTenantToggle,
  FeatureFlagEvaluate,
} from '@/types/generated/config/conectaPROCONFIGModuleAPI.schemas';

export const featureFlagsKeys = {
  all: ['feature-flags'] as const,
  lists: () => [...featureFlagsKeys.all, 'list'] as const,
  list: (filters: any) => [...featureFlagsKeys.lists(), filters] as const,
  details: () => [...featureFlagsKeys.all, 'detail'] as const,
  detail: (id: string) => [...featureFlagsKeys.details(), id] as const,
  evaluations: () => [...featureFlagsKeys.all, 'evaluation'] as const,
  evaluation: (key: string, context: any) => [...featureFlagsKeys.evaluations(), key, context] as const,
};

export const useFeatureFlags = (params?: featureFlagsService.ListFeatureFlagsParams) => {
  return useQuery({
    queryKey: featureFlagsKeys.list(params),
    queryFn: () => featureFlagsService.listFeatureFlags(params),
  });
};

export const useFeatureFlag = (flagId: string, enabled: boolean = true) => {
  return useQuery({
    queryKey: featureFlagsKeys.detail(flagId),
    queryFn: () => featureFlagsService.getFeatureFlag(flagId),
    enabled: enabled && !!flagId,
  });
};

export const useEvaluateFeatureFlag = (evaluation: FeatureFlagEvaluate, enabled: boolean = true) => {
  return useQuery({
    queryKey: featureFlagsKeys.evaluation(evaluation.tenant_id || 'default', evaluation),
    queryFn: () => featureFlagsService.evaluateFeatureFlag(evaluation),
    enabled: enabled && (!!evaluation.tenant_id || !!evaluation.user_id),
  });
};

export const useCreateFeatureFlag = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: FeatureFlagCreate) => featureFlagsService.createFeatureFlag(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: featureFlagsKeys.lists() });
      toast.success('Feature flag criada!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao criar');
    },
  });
};

export const useUpdateFeatureFlag = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: FeatureFlagUpdate }) =>
      featureFlagsService.updateFeatureFlag(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: featureFlagsKeys.detail(variables.id) });
      queryClient.invalidateQueries({ queryKey: featureFlagsKeys.lists() });
      toast.success('Feature flag atualizada!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao atualizar');
    },
  });
};

export const useEnableFeatureFlag = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => featureFlagsService.enableFeatureFlag(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: featureFlagsKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: featureFlagsKeys.lists() });
      toast.success('Feature flag habilitada!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao habilitar');
    },
  });
};

export const useDisableFeatureFlag = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => featureFlagsService.disableFeatureFlag(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: featureFlagsKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: featureFlagsKeys.lists() });
      toast.success('Feature flag desabilitada!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao desabilitar');
    },
  });
};

export const useSetFeatureFlagPercentage = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, percentage }: { id: string; percentage: number }) =>
      featureFlagsService.setFeatureFlagPercentage(id, percentage),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: featureFlagsKeys.detail(variables.id) });
      toast.success('Percentual atualizado!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao atualizar percentual');
    },
  });
};

export const useSetGradualRollout = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, rollout }: { id: string; rollout: FeatureFlagGradualRollout }) =>
      featureFlagsService.setGradualRollout(id, rollout),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: featureFlagsKeys.detail(variables.id) });
      toast.success('Rollout configurado!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao configurar rollout');
    },
  });
};

export const useToggleFeatureFlagForTenant = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, toggle }: { id: string; toggle: FeatureFlagTenantToggle }) =>
      featureFlagsService.toggleFeatureFlagForTenant(id, toggle),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: featureFlagsKeys.detail(variables.id) });
      toast.success('Feature flag atualizada para tenant!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao atualizar');
    },
  });
};

export const useDeleteFeatureFlag = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => featureFlagsService.deleteFeatureFlag(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: featureFlagsKeys.lists() });
      toast.success('Feature flag deletada!');
    },
    onError: (error: any) => {
      toast.error(msgFromDetail(error?.response?.data?.detail) || 'Erro ao deletar');
    },
  });
};
