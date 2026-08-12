/**
 * React Query Hooks - Audit Trail
 *
 * @module security-lgpd/hooks/useAudit
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { AuditFilters, SeverityLevel } from '../services/auditService';
import * as auditService from '../services/auditService';

export const auditKeys = {
  all: ['lgpd', 'audit'] as const,
  lists: () => [...auditKeys.all, 'list'] as const,
  list: (filters?: AuditFilters) => [...auditKeys.lists(), filters] as const,
  actions: () => [...auditKeys.all, 'actions'] as const,
  resourceTypes: () => [...auditKeys.all, 'resource-types'] as const,
};

export const useAuditLogs = (filters?: AuditFilters) => {
  return useQuery({
    queryKey: auditKeys.list(filters),
    queryFn: () => auditService.listAuditLogs(filters),
    staleTime: 2 * 60 * 1000, // 2 minutos
  });
};

export const useAuditActions = () => {
  return useQuery({
    queryKey: auditKeys.actions(),
    queryFn: auditService.listActions,
    staleTime: 30 * 60 * 1000, // 30 minutos
  });
};

export const useAuditResourceTypes = () => {
  return useQuery({
    queryKey: auditKeys.resourceTypes(),
    queryFn: auditService.listResourceTypes,
    staleTime: 30 * 60 * 1000, // 30 minutos
  });
};

export const useLogAuditEvent = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      action,
      resourceType,
      resourceId,
      userId,
      details,
      severity,
    }: {
      action: string;
      resourceType: string;
      resourceId: string;
      userId: string;
      details?: Record<string, any>;
      severity?: SeverityLevel;
    }) =>
      auditService.logAuditEvent(action, resourceType, resourceId, userId, details, severity),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: auditKeys.lists() });
    },
  });
};

export const useAuditLogsByUser = (userId: string) => {
  return useQuery({
    queryKey: [...auditKeys.lists(), 'user', userId],
    queryFn: () => auditService.getLogsByUser(userId),
    enabled: !!userId,
  });
};

export const useAuditLogsByResourceType = (resourceType: string) => {
  return useQuery({
    queryKey: [...auditKeys.lists(), 'resource-type', resourceType],
    queryFn: () => auditService.getLogsByResourceType(resourceType),
    enabled: !!resourceType,
  });
};

const auditHooks = {
  useAuditLogs,
  useAuditActions,
  useAuditResourceTypes,
  useLogAuditEvent,
  useAuditLogsByUser,
  useAuditLogsByResourceType,
};

export default auditHooks;
