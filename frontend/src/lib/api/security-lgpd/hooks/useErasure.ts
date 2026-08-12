/**
 * React Query Hooks - Data Erasure
 *
 * @module security-lgpd/hooks/useErasure
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ErasureScope } from '../services/erasureService';
import * as erasureService from '../services/erasureService';

export const erasureKeys = {
  all: ['lgpd', 'erasure'] as const,
  status: (requestId: string) => [...erasureKeys.all, 'status', requestId] as const,
};

export const useErasureStatus = (requestId: string, enabled = true) => {
  return useQuery({
    queryKey: erasureKeys.status(requestId),
    queryFn: () => erasureService.getErasureStatus(requestId),
    enabled: enabled && !!requestId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      // Refetch a cada 10s se estiver processando
      return status === 'processing' || status === 'pending' ? 10000 : false;
    },
  });
};

export const useRequestErasure = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      titularId,
      titularEmail,
      reason,
      scope,
    }: {
      titularId: string;
      titularEmail: string;
      reason: string;
      scope?: ErasureScope;
    }) => erasureService.requestDataErasure(titularId, titularEmail, reason, scope),
    onSuccess: (data) => {
      // Atualizar cache com o novo request
      queryClient.setQueryData(erasureKeys.status(data.request_id), data);
    },
  });
};

const erasureHooks = {
  useErasureStatus,
  useRequestErasure,
};

export default erasureHooks;
