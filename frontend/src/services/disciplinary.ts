/**
 * Service Layer - Disciplinary Actions (Medidas Administrativas)
 *
 * Gerencia medidas disciplinares (CRUD, aprovacao, assinatura, IA)
 *
 * As rotas vivem sob people-management/hr/discipline e usam verbos em portugues
 * (submeter/aprovar/rejeitar/assinar/recusar-assinatura). Este arquivo apontava
 * para /api/v1/operacional/disciplinary com verbos em ingles — prefixo e verbos
 * que nunca existiram, entao nenhuma acao disciplinar saia da tela.
 */

import { apiClient } from '@/lib/api/client';
import type {
  DisciplinaryAction,
  DisciplinaryActionCreate,
  DisciplinaryActionUpdate,
} from '@/types/disciplinary';

const BASE_URL = '/api/v1/people-management/hr/discipline/medidas-administrativas';

/**
 * Conta advertencias e suspensoes anteriores do funcionario.
 *
 * A IA de conformidade/proporcionalidade pesa antecedentes: mandar 0 fixo mudaria
 * o parecer. Entao conta no historico real, excluindo a propria medida e as que
 * nunca chegaram a valer (rascunho, rejeitada, cancelada).
 */
async function antecedentes(action: DisciplinaryAction) {
  const { data } = await apiClient.get<DisciplinaryAction[]>(
    `${BASE_URL}/funcionario/${action.employee_id}`
  );
  const valeu = data.filter(
    (a) =>
      a.id !== action.id &&
      !['rascunho', 'rejeitada', 'cancelada'].includes(a.status)
  );
  return {
    previous_warnings: valeu.filter((a) => a.action_type.startsWith('advertencia')).length,
    previous_suspensions: valeu.filter((a) => a.action_type === 'suspensao').length,
  };
}

export const disciplinaryService = {
  /**
   * Cria nova medida disciplinar
   */
  async create(data: DisciplinaryActionCreate): Promise<DisciplinaryAction> {
    const response = await apiClient.post<DisciplinaryAction>(BASE_URL, data);
    return response.data;
  },

  /**
   * Atualiza medida disciplinar (apenas rascunho) — o backend expoe PATCH, nao PUT
   */
  async update(actionId: string, data: DisciplinaryActionUpdate): Promise<DisciplinaryAction> {
    const response = await apiClient.patch<DisciplinaryAction>(`${BASE_URL}/${actionId}`, data);
    return response.data;
  },

  /**
   * Historico disciplinar do funcionario
   */
  async history(employeeId: string): Promise<DisciplinaryAction[]> {
    const response = await apiClient.get<DisciplinaryAction[]>(
      `${BASE_URL}/funcionario/${employeeId}`
    );
    return response.data;
  },

  /**
   * Submete para aprovacao
   */
  async submit(actionId: string, notes?: string): Promise<DisciplinaryAction> {
    const response = await apiClient.post<DisciplinaryAction>(
      `${BASE_URL}/${actionId}/submeter`,
      { notes: notes ?? null }
    );
    return response.data;
  },

  /**
   * Aprova medida disciplinar
   */
  async approve(actionId: string, notes?: string): Promise<DisciplinaryAction> {
    const response = await apiClient.post<DisciplinaryAction>(
      `${BASE_URL}/${actionId}/aprovar`,
      { notes: notes ?? null }
    );
    return response.data;
  },

  /**
   * Rejeita medida disciplinar
   */
  async reject(actionId: string, reason: string): Promise<DisciplinaryAction> {
    const response = await apiClient.post<DisciplinaryAction>(
      `${BASE_URL}/${actionId}/rejeitar`,
      { reason }
    );
    return response.data;
  },

  /**
   * Assina documento digitalmente
   */
  async sign(
    actionId: string,
    data: {
      signature_data: string;
      signer_type: string;
      latitude?: number;
      longitude?: number;
    }
  ): Promise<DisciplinaryAction> {
    const response = await apiClient.post<DisciplinaryAction>(
      `${BASE_URL}/${actionId}/assinar`,
      data
    );
    return response.data;
  },

  /**
   * Registra recusa de assinatura com testemunhas
   */
  async refuseSignature(
    actionId: string,
    data: {
      witness_1_name: string;
      witness_1_cpf: string;
      witness_2_name: string;
      witness_2_cpf: string;
    }
  ): Promise<DisciplinaryAction> {
    const response = await apiClient.post<DisciplinaryAction>(
      `${BASE_URL}/${actionId}/recusar-assinatura`,
      data
    );
    return response.data;
  },

  /**
   * Valida conformidade CLT via IA.
   *
   * A rota nao e por id: recebe o retrato da medida. Por isso toma a medida
   * inteira, nao so o actionId.
   */
  async validateCompliance(action: DisciplinaryAction): Promise<{
    compliant: boolean;
    issues: string[];
    suggestions: string[];
  }> {
    const response = await apiClient.post<{
      compliant: boolean;
      issues: string[];
      suggestions: string[];
    }>(`${BASE_URL}/ia/validar-conformidade`, {
      action_type: action.action_type,
      reason_category: action.reason_category,
      reason_description: action.reason_description,
      incident_date: action.incident_date,
      application_date: action.application_date ?? action.incident_date,
      suspension_days: action.suspension_days ?? null,
      ...(await antecedentes(action)),
    });
    return response.data;
  },

  /**
   * Verifica proporcionalidade da medida via IA
   */
  async checkProportionality(action: DisciplinaryAction): Promise<{
    proportional: boolean;
    analysis: string;
  }> {
    const admissao = action.employee_admission_date;
    const response = await apiClient.post<{
      proportional: boolean;
      analysis: string;
    }>(`${BASE_URL}/ia/verificar-proporcionalidade`, {
      action_type: action.action_type,
      reason_category: action.reason_category,
      employee_tenure_days: admissao
        ? Math.max(0, Math.floor((Date.now() - new Date(admissao).getTime()) / 86_400_000))
        : 0,
      ...(await antecedentes(action)),
    });
    return response.data;
  },
};

export default disciplinaryService;
