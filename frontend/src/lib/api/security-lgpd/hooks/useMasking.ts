/**
 * React Query Hooks - Data Masking
 *
 * @module security-lgpd/hooks/useMasking
 */

import { useMutation, useQuery } from '@tanstack/react-query';
import type { MaskCategory, MaskLevel } from '../services/maskingService';
import * as maskingService from '../services/maskingService';

export const maskingKeys = {
  all: ['lgpd', 'masking'] as const,
  formats: () => [...maskingKeys.all, 'formats'] as const,
};

export const useMaskingFormats = () => {
  return useQuery({
    queryKey: maskingKeys.formats(),
    queryFn: maskingService.listMaskingFormats,
    staleTime: 60 * 60 * 1000, // 1 hora
  });
};

export const useMaskData = () => {
  return useMutation({
    mutationFn: ({
      data,
      category,
      level,
    }: {
      data: string;
      category: MaskCategory;
      level?: MaskLevel;
    }) => maskingService.maskData(data, category, level),
  });
};

export const useMaskCPF = () => {
  return useMutation({
    mutationFn: (cpf: string) => maskingService.maskCPF(cpf),
  });
};

export const useMaskEmail = () => {
  return useMutation({
    mutationFn: (email: string) => maskingService.maskEmail(email),
  });
};

export const useMaskPhone = () => {
  return useMutation({
    mutationFn: (phone: string) => maskingService.maskPhone(phone),
  });
};

export const useAutoMask = () => {
  return useMutation({
    mutationFn: (data: string) => maskingService.autoMask(data),
  });
};

const maskingHooks = {
  useMaskingFormats,
  useMaskData,
  useMaskCPF,
  useMaskEmail,
  useMaskPhone,
  useAutoMask,
};

export default maskingHooks;
