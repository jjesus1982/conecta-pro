/**
 * React Query Hooks - PIA/DPIA
 *
 * @module security-lgpd/hooks/usePIA
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as piaService from '../services/piaService';

export const piaKeys = {
  all: ['lgpd', 'pia'] as const,
  detail: (assessmentId: string) => [...piaKeys.all, 'detail', assessmentId] as const,
  riskCategories: () => [...piaKeys.all, 'risk-categories'] as const,
};

export const usePIA = (assessmentId: string, enabled = true) => {
  return useQuery({
    queryKey: piaKeys.detail(assessmentId),
    queryFn: () => piaService.getPIA(assessmentId),
    enabled: enabled && !!assessmentId,
    staleTime: 10 * 60 * 1000, // 10 minutos
  });
};

export const useRiskCategories = () => {
  return useQuery({
    queryKey: piaKeys.riskCategories(),
    queryFn: piaService.listRiskCategories,
    staleTime: 60 * 60 * 1000, // 1 hora
  });
};

export const useCreatePIA = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      projectName,
      description,
      dataCategories,
      processingPurposes,
      dataSubjects,
      riskFactors,
    }: {
      projectName: string;
      description: string;
      dataCategories: string[];
      processingPurposes?: string[];
      dataSubjects?: string[];
      riskFactors?: string[];
    }) =>
      piaService.createPIA(
        projectName,
        description,
        dataCategories,
        processingPurposes,
        dataSubjects,
        riskFactors
      ),
    onSuccess: (data) => {
      queryClient.setQueryData(piaKeys.detail(data.assessment_id), data);
    },
  });
};

const piaHooks = {
  usePIA,
  useRiskCategories,
  useCreatePIA,
};

export default piaHooks;
