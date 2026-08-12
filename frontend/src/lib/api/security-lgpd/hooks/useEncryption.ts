/**
 * React Query Hooks - Encryption
 *
 * @module security-lgpd/hooks/useEncryption
 */

import { useMutation, useQuery } from '@tanstack/react-query';
import type { EncryptionAlgorithm } from '../services/encryptionService';
import * as encryptionService from '../services/encryptionService';

export const encryptionKeys = {
  all: ['lgpd', 'encryption'] as const,
  algorithms: () => [...encryptionKeys.all, 'algorithms'] as const,
};

export const useEncryptionAlgorithms = () => {
  return useQuery({
    queryKey: encryptionKeys.algorithms(),
    queryFn: encryptionService.listAlgorithms,
    staleTime: 60 * 60 * 1000, // 1 hora
  });
};

export const useEncryptData = () => {
  return useMutation({
    mutationFn: ({
      data,
      algorithm,
      keyId,
    }: {
      data: string;
      algorithm?: EncryptionAlgorithm;
      keyId?: string;
    }) => encryptionService.encryptData(data, algorithm, keyId),
  });
};

export const useDecryptData = () => {
  return useMutation({
    mutationFn: ({ encryptedData, keyId }: { encryptedData: string; keyId?: string }) =>
      encryptionService.decryptData(encryptedData, keyId),
  });
};

const encryptionHooks = {
  useEncryptionAlgorithms,
  useEncryptData,
  useDecryptData,
};

export default encryptionHooks;
