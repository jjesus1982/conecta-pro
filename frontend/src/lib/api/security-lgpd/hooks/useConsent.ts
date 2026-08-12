/**
 * React Query Hooks - Consent Management
 *
 * Hooks customizados para gestão de consentimentos LGPD
 *
 * @module security-lgpd/hooks/useConsent
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ConsentRequest } from '@/types/generated/security-lgpd/conectaPROLGPDSecurityAPI.schemas';
import * as consentService from '../services/consentService';

// Query keys
export const consentKeys = {
  all: ['lgpd', 'consents'] as const,
  lists: () => [...consentKeys.all, 'list'] as const,
  list: (titularId: string) => [...consentKeys.lists(), titularId] as const,
  purposes: () => [...consentKeys.all, 'purposes'] as const,
  legalBases: () => [...consentKeys.all, 'legal-bases'] as const,
};

/**
 * Hook para consultar consentimentos de um titular
 */
export const useConsentsByTitular = (titularId: string, enabled = true) => {
  return useQuery({
    queryKey: consentKeys.list(titularId),
    queryFn: () => consentService.getConsentsByTitular(titularId),
    enabled: enabled && !!titularId,
    staleTime: 5 * 60 * 1000, // 5 minutos
  });
};

/**
 * Hook para consultar finalidades de consentimento
 */
export const useConsentPurposes = () => {
  return useQuery({
    queryKey: consentKeys.purposes(),
    queryFn: consentService.listConsentPurposes,
    staleTime: 30 * 60 * 1000, // 30 minutos - dados estáveis
  });
};

/**
 * Hook para consultar bases legais LGPD
 */
export const useLegalBases = () => {
  return useQuery({
    queryKey: consentKeys.legalBases(),
    queryFn: consentService.listLegalBases,
    staleTime: 30 * 60 * 1000, // 30 minutos - dados estáveis
  });
};

/**
 * Hook para registrar consentimento
 */
export const useRegisterConsent = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ConsentRequest) => consentService.registerConsent(data),
    onSuccess: (_, variables) => {
      // Invalidar lista de consentimentos do titular
      queryClient.invalidateQueries({
        queryKey: consentKeys.list(variables.titular_id),
      });
    },
  });
};

/**
 * Hook para revogar consentimento
 */
export const useRevokeConsent = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ consentId, reason }: { consentId: string; reason: string }) =>
      consentService.revokeConsent(consentId, reason),
    onSuccess: () => {
      // Invalidar todas as listas de consentimentos
      queryClient.invalidateQueries({
        queryKey: consentKeys.lists(),
      });
    },
  });
};

/**
 * Hook para verificar consentimentos ativos
 */
export const useActiveConsents = (titularId: string) => {
  const { data, ...rest } = useConsentsByTitular(titularId);

  const activeConsents = data?.consents
    ? consentService.getActiveConsents(data.consents)
    : [];

  return {
    activeConsents,
    total: activeConsents.length,
    ...rest,
  };
};

/**
 * Hook para agrupar consentimentos por finalidade
 */
export const useConsentsByPurpose = (titularId: string) => {
  const { data, ...rest } = useConsentsByTitular(titularId);

  const grouped = data?.consents
    ? consentService.groupConsentsByPurpose(data.consents)
    : {};

  return {
    grouped,
    purposes: Object.keys(grouped),
    ...rest,
  };
};

const consentHooks = {
  useConsentsByTitular,
  useConsentPurposes,
  useLegalBases,
  useRegisterConsent,
  useRevokeConsent,
  useActiveConsents,
  useConsentsByPurpose,
};

export default consentHooks;
