/**
 * Service Layer - PIA/DPIA (LGPD Art. 38)
 *
 * Privacy Impact Assessment / Data Protection Impact Assessment:
 * - Criação de avaliações de impacto
 * - Consulta de avaliações
 * - Categorias de risco
 *
 * @module security-lgpd/services/piaService
 */

import axios from 'axios';
import type {
  PIARequest,
  StandardResponse,
} from '@/types/generated/security-lgpd/conectaPROLGPDSecurityAPI.schemas';

const BASE_PATH = '/lgpd/pia';

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export interface PIAAssessment {
  assessment_id: string;
  project_name: string;
  description: string;
  data_categories: string[];
  processing_purposes: string[];
  data_subjects: string[];
  risk_factors: string[];
  risk_level: RiskLevel;
  risk_score: number;
  recommendations: string[];
  created_at: string;
  created_by?: string;
}

export interface RiskCategory {
  code: string;
  name: string;
  description: string;
  weight: number;
}

/**
 * Cria avaliação de impacto de privacidade
 */
export const createPIA = async (
  projectName: string,
  description: string,
  dataCategories: string[],
  processingPurposes?: string[],
  dataSubjects?: string[],
  riskFactors?: string[]
): Promise<PIAAssessment> => {
  const payload: PIARequest = {
    project_name: projectName,
    description,
    data_categories: dataCategories,
    processing_purposes: processingPurposes,
    data_subjects: dataSubjects,
    risk_factors: riskFactors,
  };

  const response = await axios.post<StandardResponse>(`${BASE_PATH}/create`, payload);

  if (!response.data.success) {
    throw new Error(response.data.message || 'Erro ao criar avaliação de impacto');
  }

  return response.data.data as unknown as PIAAssessment;
};

/**
 * Consulta avaliação PIA/DPIA por ID
 */
export const getPIA = async (assessmentId: string): Promise<PIAAssessment> => {
  const response = await axios.get<StandardResponse>(`${BASE_PATH}/${assessmentId}`);

  if (!response.data.success) {
    throw new Error(response.data.message || 'Erro ao consultar avaliação');
  }

  return response.data.data as unknown as PIAAssessment;
};

/**
 * Lista categorias de risco disponíveis
 */
export const listRiskCategories = async (): Promise<RiskCategory[]> => {
  const response = await axios.get<StandardResponse>(`${BASE_PATH}/risk-categories/list`);

  if (!response.data.success) {
    throw new Error(response.data.message || 'Erro ao listar categorias de risco');
  }

  return (response.data.data as unknown as { risk_categories: RiskCategory[] }).risk_categories;
};

/**
 * Determina se PIA é obrigatório baseado no nível de risco
 */
export const isPIAMandatory = (riskLevel: RiskLevel): boolean => {
  return riskLevel === 'high' || riskLevel === 'critical';
};

/**
 * Calcula score de risco baseado em fatores
 */
export const calculateRiskScore = (riskFactors: string[]): number => {
  // Cada fator de risco adiciona 10 pontos
  return Math.min(riskFactors.length * 10, 100);
};

/**
 * Determina nível de risco baseado no score
 */
export const determineRiskLevel = (score: number): RiskLevel => {
  if (score >= 75) return 'critical';
  if (score >= 50) return 'high';
  if (score >= 25) return 'medium';
  return 'low';
};

const piaServiceApi = {
  createPIA,
  getPIA,
  listRiskCategories,
  isPIAMandatory,
  calculateRiskScore,
  determineRiskLevel,
};

export default piaServiceApi;
