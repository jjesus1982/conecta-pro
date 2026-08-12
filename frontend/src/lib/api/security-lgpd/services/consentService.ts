/**
 * Service Layer - Consent Management (LGPD Art. 7, 8, 9)
 *
 * Gestão de consentimentos LGPD:
 * - Registro de consentimentos
 * - Consulta de consentimentos por titular
 * - Revogação de consentimentos
 * - Listagem de finalidades e bases legais
 *
 * @module security-lgpd/services/consentService
 */

import {
  registerConsent as registerConsentApi,
  getConsents as getConsentsApi,
  revokeConsent as revokeConsentApi,
  listPurposes as listPurposesApi,
  listLegalBases as listLegalBasesApi,
} from '@/types/generated/security-lgpd/lgpd-consentimento/lgpd-consentimento';
import type {
  ConsentRequest,
  StandardResponse,
} from '@/types/generated/security-lgpd/conectaPROLGPDSecurityAPI.schemas';

/**
 * Interface para resposta de consentimentos
 */
export interface ConsentData {
  consent_id: string;
  titular_id: string;
  titular_email: string;
  purpose: string;
  legal_basis: string;
  description?: string;
  granted_at: string;
  expires_at?: string;
  status: 'active' | 'revoked' | 'expired';
  revocation_date?: string;
  revocation_reason?: string;
}

/**
 * Interface para listagem de consentimentos
 */
export interface ConsentsListResponse {
  consents: ConsentData[];
  total: number;
  titular_id: string;
}

/**
 * Interface para finalidades
 */
export interface Purpose {
  code: string;
  name: string;
  description: string;
}

/**
 * Interface para bases legais
 */
export interface LegalBasis {
  code: string;
  name: string;
  article: string;
  description: string;
}

/**
 * Registra novo consentimento LGPD
 */
export const registerConsent = async (
  data: ConsentRequest
): Promise<ConsentData> => {
  const response = await registerConsentApi(data) as StandardResponse;

  if (!response.success) {
    throw new Error(response.message || 'Erro ao registrar consentimento');
  }

  return response.data as unknown as ConsentData;
};

/**
 * Consulta consentimentos de um titular
 */
export const getConsentsByTitular = async (
  titularId: string
): Promise<ConsentsListResponse> => {
  const response = await getConsentsApi(titularId) as StandardResponse;

  if (!response.success) {
    throw new Error(response.message || 'Erro ao consultar consentimentos');
  }

  return response.data as unknown as ConsentsListResponse;
};

/**
 * Revoga um consentimento
 */
export const revokeConsent = async (
  consentId: string,
  reason: string
): Promise<void> => {
  const response = await revokeConsentApi(
    consentId,
    { reason }
  ) as StandardResponse;

  if (!response.success) {
    throw new Error(response.message || 'Erro ao revogar consentimento');
  }
};

/**
 * Lista finalidades de consentimento disponíveis
 */
export const listConsentPurposes = async (): Promise<Purpose[]> => {
  const response = await listPurposesApi() as StandardResponse;

  if (!response.success) {
    throw new Error(response.message || 'Erro ao listar finalidades');
  }

  return (response.data as unknown as { purposes: Purpose[] }).purposes;
};

/**
 * Lista bases legais LGPD disponíveis
 */
export const listLegalBases = async (): Promise<LegalBasis[]> => {
  const response = await listLegalBasesApi() as StandardResponse;

  if (!response.success) {
    throw new Error(response.message || 'Erro ao listar bases legais');
  }

  return (response.data as unknown as { legal_bases: LegalBasis[] }).legal_bases;
};

/**
 * Verifica se um consentimento está ativo
 */
export const isConsentActive = (consent: ConsentData): boolean => {
  if (consent.status !== 'active') {
    return false;
  }

  if (consent.expires_at) {
    const expirationDate = new Date(consent.expires_at);
    return expirationDate > new Date();
  }

  return true;
};

/**
 * Filtra consentimentos ativos
 */
export const getActiveConsents = (consents: ConsentData[]): ConsentData[] => {
  return consents.filter(isConsentActive);
};

/**
 * Agrupa consentimentos por finalidade
 */
export const groupConsentsByPurpose = (
  consents: ConsentData[]
): Record<string, ConsentData[]> => {
  return consents.reduce<Record<string, ConsentData[]>>((acc, consent) => {
    return {
      ...acc,
      [consent.purpose]: [...(acc[consent.purpose] || []), consent],
    };
  }, {});
};

const consentServiceApi = {
  registerConsent,
  getConsentsByTitular,
  revokeConsent,
  listConsentPurposes,
  listLegalBases,
  isConsentActive,
  getActiveConsents,
  groupConsentsByPurpose,
};

export default consentServiceApi;
