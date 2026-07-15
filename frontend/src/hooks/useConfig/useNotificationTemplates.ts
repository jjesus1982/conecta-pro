/**
 * Custom Hooks - Notification Templates
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import * as templatesService from '@/services/config/notification-templates';
import type {
  NotificationTemplateCreate,
  NotificationTemplateUpdate,
  NotificationTemplateRender,
} from '@/types/generated/config/conectaPROCONFIGModuleAPI.schemas';

export const notificationTemplatesKeys = {
  all: ['notification-templates'] as const,
  lists: () => [...notificationTemplatesKeys.all, 'list'] as const,
  list: (filters: any) => [...notificationTemplatesKeys.lists(), filters] as const,
  details: () => [...notificationTemplatesKeys.all, 'detail'] as const,
  detail: (id: string) => [...notificationTemplatesKeys.details(), id] as const,
};

export const useNotificationTemplates = (
  params?: templatesService.ListNotificationTemplatesParams
) => {
  return useQuery({
    queryKey: notificationTemplatesKeys.list(params),
    queryFn: () => templatesService.listNotificationTemplates(params),
  });
};

export const useNotificationTemplate = (templateId: string, enabled: boolean = true) => {
  return useQuery({
    queryKey: notificationTemplatesKeys.detail(templateId),
    queryFn: () => templatesService.getNotificationTemplate(templateId),
    enabled: enabled && !!templateId,
  });
};

export const useCreateNotificationTemplate = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: NotificationTemplateCreate) =>
      templatesService.createNotificationTemplate(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationTemplatesKeys.lists() });
      toast.success('Template criado!');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao criar');
    },
  });
};

export const useUpdateNotificationTemplate = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: NotificationTemplateUpdate }) =>
      templatesService.updateNotificationTemplate(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: notificationTemplatesKeys.detail(variables.id),
      });
      queryClient.invalidateQueries({ queryKey: notificationTemplatesKeys.lists() });
      toast.success('Template atualizado!');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao atualizar');
    },
  });
};

export const useActivateNotificationTemplate = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => templatesService.activateNotificationTemplate(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: notificationTemplatesKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: notificationTemplatesKeys.lists() });
      toast.success('Template ativado!');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao ativar');
    },
  });
};

export const useDeactivateNotificationTemplate = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => templatesService.deactivateNotificationTemplate(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: notificationTemplatesKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: notificationTemplatesKeys.lists() });
      toast.success('Template desativado!');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao desativar');
    },
  });
};

export const useRenderNotificationTemplate = () => {
  return useMutation({
    mutationFn: ({ id, render }: { id: string; render: NotificationTemplateRender }) =>
      templatesService.renderNotificationTemplate(id, render),
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao renderizar');
    },
  });
};

export const useCloneNotificationTemplate = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => templatesService.cloneNotificationTemplate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationTemplatesKeys.lists() });
      toast.success('Template clonado!');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao clonar');
    },
  });
};

export const useDeleteNotificationTemplate = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => templatesService.deleteNotificationTemplate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationTemplatesKeys.lists() });
      toast.success('Template deletado!');
    },
    onError: (error: any) => {
      toast.error(error?.response?.msgFromDetail(data?.detail) || 'Erro ao deletar');
    },
  });
};
