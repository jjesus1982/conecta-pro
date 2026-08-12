/**
 * Service Layer - Data Masking (LGPD Compliance)
 *
 * Mascaramento de dados PII:
 * - CPF, CNPJ
 * - Email
 * - Telefone
 * - Nome, Endereço
 * - Cartão de crédito
 *
 * @module security-lgpd/services/maskingService
 */

import axios from 'axios';
import type {
  MaskDataRequest,
  StandardResponse,
} from '@/types/generated/security-lgpd/conectaPROLGPDSecurityAPI.schemas';

const BASE_PATH = '/lgpd/masking';

export type MaskCategory = 'cpf' | 'email' | 'phone' | 'name' | 'address' | 'credit_card';
export type MaskLevel = 'partial' | 'full' | 'custom';

export interface MaskedData {
  original_length: number;
  masked_value: string;
  category: MaskCategory;
  level: MaskLevel;
}

export interface MaskingFormat {
  categories: MaskCategory[];
  levels: MaskLevel[];
  patterns: Record<MaskCategory, string>;
}

/**
 * Mascara dados sensíveis
 */
export const maskData = async (
  data: string,
  category: MaskCategory,
  level: MaskLevel = 'partial'
): Promise<string> => {
  const payload: MaskDataRequest = {
    data,
    category,
    level,
  };

  const response = await axios.post<StandardResponse>(`${BASE_PATH}/mask`, payload);

  if (!response.data.success) {
    throw new Error(response.data.message || 'Erro ao mascarar dados');
  }

  return (response.data.data as unknown as MaskedData).masked_value;
};

/**
 * Lista formatos de mascaramento disponíveis
 */
export const listMaskingFormats = async (): Promise<MaskingFormat> => {
  const response = await axios.get<StandardResponse>(`${BASE_PATH}/formats`);

  if (!response.data.success) {
    throw new Error(response.data.message || 'Erro ao listar formatos');
  }

  return response.data.data as unknown as MaskingFormat;
};

/**
 * Mascara CPF (parcial: 123.456.***-**)
 */
export const maskCPF = async (cpf: string): Promise<string> => {
  return maskData(cpf, 'cpf', 'partial');
};

/**
 * Mascara email (parcial: joh****@example.com)
 */
export const maskEmail = async (email: string): Promise<string> => {
  return maskData(email, 'email', 'partial');
};

/**
 * Mascara telefone (parcial: (11) 9****-1234)
 */
export const maskPhone = async (phone: string): Promise<string> => {
  return maskData(phone, 'phone', 'partial');
};

/**
 * Mascara nome (parcial: João S****)
 */
export const maskName = async (name: string): Promise<string> => {
  return maskData(name, 'name', 'partial');
};

/**
 * Mascara cartão de crédito (parcial: **** **** **** 1234)
 */
export const maskCreditCard = async (card: string): Promise<string> => {
  return maskData(card, 'credit_card', 'partial');
};

/**
 * Mascara múltiplos campos de um objeto
 */
export const maskFields = async <T extends Record<string, any>>(
  obj: T,
  fieldsConfig: Array<{ field: keyof T; category: MaskCategory; level?: MaskLevel }>
): Promise<Partial<T>> => {
  const masked: Partial<T> = {};

  for (const config of fieldsConfig) {
    const value = obj[config.field];
    if (value !== undefined && value !== null) {
      masked[config.field] = (await maskData(
        String(value),
        config.category,
        config.level
      )) as any;
    }
  }

  return masked;
};

/**
 * Detecta tipo de dado e aplica mascaramento automático
 */
export const autoMask = async (data: string): Promise<string> => {
  // Detecta padrão e aplica mascaramento apropriado
  if (/^\d{3}\.\d{3}\.\d{3}-\d{2}$/.test(data)) {
    return maskCPF(data);
  }
  if (/^[\w.-]+@[\w.-]+\.\w+$/.test(data)) {
    return maskEmail(data);
  }
  if (/^\(\d{2}\)\s?\d{4,5}-?\d{4}$/.test(data)) {
    return maskPhone(data);
  }
  // Default: mascaramento parcial
  const len = data.length;
  return data.substring(0, Math.ceil(len * 0.3)) + '*'.repeat(Math.floor(len * 0.7));
};

const maskingServiceApi = {
  maskData,
  listMaskingFormats,
  maskCPF,
  maskEmail,
  maskPhone,
  maskName,
  maskCreditCard,
  maskFields,
  autoMask,
};

export default maskingServiceApi;
