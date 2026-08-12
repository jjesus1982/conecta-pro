/**
 * Service Layer - Encryption (LGPD Compliance)
 *
 * Criptografia de dados sensíveis com algoritmos suportados:
 * - AES-256-GCM (recomendado)
 * - AES-256-CBC
 * - Fernet
 * - ChaCha20-Poly1305
 * - RSA-OAEP
 *
 * @module security-lgpd/services/encryptionService
 */

import axios from 'axios';
import type {
  EncryptDataRequest,
  DecryptDataRequest,
  StandardResponse,
} from '@/types/generated/security-lgpd/conectaPROLGPDSecurityAPI.schemas';

const BASE_PATH = '/lgpd/encryption';

export type EncryptionAlgorithm =
  | 'AES-256-GCM'
  | 'AES-256-CBC'
  | 'Fernet'
  | 'ChaCha20-Poly1305'
  | 'RSA-OAEP';

export interface EncryptedData {
  encrypted_data: string;
  algorithm: EncryptionAlgorithm;
  key_id?: string;
  iv?: string;
  tag?: string;
  timestamp: string;
}

export interface AlgorithmInfo {
  name: EncryptionAlgorithm;
  description: string;
  key_size: number;
  recommended: boolean;
}

/**
 * Criptografa dados sensíveis
 */
export const encryptData = async (
  data: string,
  algorithm: EncryptionAlgorithm = 'AES-256-GCM',
  keyId?: string
): Promise<EncryptedData> => {
  const payload: EncryptDataRequest = {
    data,
    algorithm,
    key_id: keyId,
  };

  const response = await axios.post<StandardResponse>(`${BASE_PATH}/encrypt`, payload);

  if (!response.data.success) {
    throw new Error(response.data.message || 'Erro ao criptografar dados');
  }

  return response.data.data as unknown as EncryptedData;
};

/**
 * Descriptografa dados
 */
export const decryptData = async (
  encryptedData: string,
  keyId?: string
): Promise<string> => {
  const payload: DecryptDataRequest = {
    encrypted_data: encryptedData,
    key_id: keyId,
  };

  const response = await axios.post<StandardResponse>(`${BASE_PATH}/decrypt`, payload);

  if (!response.data.success) {
    throw new Error(response.data.message || 'Erro ao descriptografar dados');
  }

  return (response.data.data as unknown as { decrypted_data: string }).decrypted_data;
};

/**
 * Lista algoritmos de criptografia disponíveis
 */
export const listAlgorithms = async (): Promise<AlgorithmInfo[]> => {
  const response = await axios.get<StandardResponse>(`${BASE_PATH}/algorithms`);

  if (!response.data.success) {
    throw new Error(response.data.message || 'Erro ao listar algoritmos');
  }

  return (response.data.data as unknown as { algorithms: AlgorithmInfo[] }).algorithms;
};

/**
 * Criptografa múltiplos campos de um objeto
 */
export const encryptFields = async <T extends Record<string, any>>(
  obj: T,
  fields: (keyof T)[],
  algorithm?: EncryptionAlgorithm
): Promise<Record<string, EncryptedData>> => {
  const results: Record<string, EncryptedData> = {};

  for (const field of fields) {
    const value = obj[field];
    if (value !== undefined && value !== null) {
      results[field as string] = await encryptData(String(value), algorithm);
    }
  }

  return results;
};

/**
 * Valida se dados estão criptografados
 */
export const isEncrypted = (data: string): boolean => {
  // Verifica se é base64 válido e tem tamanho mínimo
  try {
    return /^[A-Za-z0-9+/]+=*$/.test(data) && data.length > 20;
  } catch {
    return false;
  }
};

const encryptionServiceApi = {
  encryptData,
  decryptData,
  listAlgorithms,
  encryptFields,
  isEncrypted,
};

export default encryptionServiceApi;
