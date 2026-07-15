/**
 * Custom Hooks - Documents Metadata
 * Hooks React Query para metadata, estatísticas e validações
 */

import { useMutation, useQuery } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';
import { toast } from 'sonner';
import * as metadataService from '@/services/documents/metadata';

// ==================== Query Keys ====================

export const metadataKeys = {
  all: ['documents', 'metadata'] as const,
  types: () => [...metadataKeys.all, 'types'] as const,
  providers: () => [...metadataKeys.all, 'providers'] as const,
  stats: (tenantId: string) =>
    [...metadataKeys.all, 'stats', tenantId] as const,
  validations: () => [...metadataKeys.all, 'validations'] as const,
};

// ==================== Queries ====================

/**
 * Hook para listar tipos de documentos
 */
export const useDocumentTypes = () => {
  return useQuery({
    queryKey: metadataKeys.types(),
    queryFn: () => metadataService.listDocumentTypes(),
    staleTime: 1000 * 60 * 60, // Cache por 1 hora (lista estática)
  });
};

/**
 * Hook para listar providers OCR
 */
export const useOCRProviders = () => {
  return useQuery({
    queryKey: metadataKeys.providers(),
    queryFn: () => metadataService.listOCRProviders(),
    staleTime: 1000 * 60 * 60, // Cache por 1 hora (lista estática)
  });
};

/**
 * Hook para obter estatísticas de armazenamento
 */
export const useStorageStats = (tenantId: string, enabled: boolean = true) => {
  return useQuery({
    queryKey: metadataKeys.stats(tenantId),
    queryFn: () => metadataService.getStorageStats(tenantId),
    enabled: enabled && !!tenantId,
    staleTime: 1000 * 60 * 5, // Cache por 5 minutos
  });
};

// ==================== Mutations ====================

/**
 * Hook para validar CPF
 */
export const useValidateCPF = () => {
  return useMutation({
    mutationFn: (cpf: string) => metadataService.validateCPF(cpf),
    onSuccess: (data) => {
      if (data.valid) {
        toast.success('CPF válido');
      } else {
        toast.error('CPF inválido');
      }
    },
    onError: (error: any) => {
      const message =
        error?.response?.data?.detail?.[0]?.msg ||
        error?.response?.msgFromDetail(data?.detail) ||
        'Erro ao validar CPF';
      toast.error(message);
    },
  });
};

/**
 * Hook para validar CNPJ
 */
export const useValidateCNPJ = () => {
  return useMutation({
    mutationFn: (cnpj: string) => metadataService.validateCNPJ(cnpj),
    onSuccess: (data) => {
      if (data.valid) {
        toast.success('CNPJ válido');
      } else {
        toast.error('CNPJ inválido');
      }
    },
    onError: (error: any) => {
      const message =
        error?.response?.data?.detail?.[0]?.msg ||
        error?.response?.msgFromDetail(data?.detail) ||
        'Erro ao validar CNPJ';
      toast.error(message);
    },
  });
};

/**
 * Hook para validar CPF sem toast (uso silencioso)
 */
export const useValidateCPFSilent = () => {
  return useMutation({
    mutationFn: (cpf: string) => metadataService.validateCPF(cpf),
  });
};

/**
 * Hook para validar CNPJ sem toast (uso silencioso)
 */
export const useValidateCNPJSilent = () => {
  return useMutation({
    mutationFn: (cnpj: string) => metadataService.validateCNPJ(cnpj),
  });
};
