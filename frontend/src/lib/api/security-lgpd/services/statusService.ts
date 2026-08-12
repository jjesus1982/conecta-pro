/**
 * Service Layer - LGPD Module Status
 *
 * Status e health check do módulo:
 * - Status de componentes
 * - Health check
 * - Informações de compliance
 *
 * @module security-lgpd/services/statusService
 */

import axios from 'axios';
import type { StandardResponse } from '@/types/generated/security-lgpd/conectaPROLGPDSecurityAPI.schemas';

const BASE_PATH = '/lgpd';

export interface LGPDStatus {
  module: string;
  version: string;
  status: 'operational' | 'degraded' | 'down';
  components: {
    encryption: 'active' | 'inactive';
    masking: 'active' | 'inactive';
    consent_management: 'active' | 'inactive';
    data_erasure: 'active' | 'inactive';
    pia_dpia: 'active' | 'inactive';
    audit_logging: 'active' | 'inactive';
  };
  compliance: {
    lgpd: string;
    articles: string[];
  };
  encryption_algorithms: string[];
  timestamp: string;
}

export interface HealthCheck {
  status: 'healthy' | 'unhealthy';
  module: string;
  timestamp: string;
}

/**
 * Obtém status completo do módulo LGPD
 */
export const getLGPDStatus = async (): Promise<LGPDStatus> => {
  const response = await axios.get<StandardResponse>(`${BASE_PATH}/status`);

  if (!response.data.success) {
    throw new Error(response.data.message || 'Erro ao obter status LGPD');
  }

  return response.data.data as unknown as LGPDStatus;
};

/**
 * Realiza health check do módulo
 */
export const healthCheck = async (): Promise<HealthCheck> => {
  const response = await axios.get<HealthCheck>(`${BASE_PATH}/health`);
  return response.data;
};

/**
 * Verifica se módulo está operacional
 */
export const isModuleOperational = async (): Promise<boolean> => {
  try {
    const status = await getLGPDStatus();
    return status.status === 'operational';
  } catch {
    return false;
  }
};

/**
 * Verifica se todos os componentes estão ativos
 */
export const areAllComponentsActive = (status: LGPDStatus): boolean => {
  return Object.values(status.components).every((comp) => comp === 'active');
};

/**
 * Lista componentes inativos
 */
export const getInactiveComponents = (status: LGPDStatus): string[] => {
  return Object.entries(status.components)
    .filter(([_, state]) => state === 'inactive')
    .map(([name, _]) => name);
};

/**
 * Obtém versão do módulo
 */
export const getModuleVersion = async (): Promise<string> => {
  const status = await getLGPDStatus();
  return status.version;
};

/**
 * Verifica conformidade com artigos LGPD
 */
export const checkCompliance = async (): Promise<{
  compliant: boolean;
  articles: string[];
}> => {
  const status = await getLGPDStatus();
  return {
    compliant: areAllComponentsActive(status),
    articles: status.compliance.articles,
  };
};

const statusServiceApi = {
  getLGPDStatus,
  healthCheck,
  isModuleOperational,
  areAllComponentsActive,
  getInactiveComponents,
  getModuleVersion,
  checkCompliance,
};

export default statusServiceApi;
