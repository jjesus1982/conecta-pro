import { useMutation } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';

const API_BASE = '/api/v1/people-management/hr';

function getAuthHeaders() {
  const token =
    typeof window !== 'undefined'
      ? localStorage.getItem('access_token') || localStorage.getItem('token')
      : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export interface ContratoGeradoResponse {
  template_slug: string;
  employee_id: string;
  employee_name: string;
  file_path: string;
  file_url: string;
  generated_at: string;
  formato: 'pdf' | 'html';
}

export function useGerarContratoTrabalho() {
  return useMutation<ContratoGeradoResponse, Error, { employee_id: string }>({
    mutationFn: async ({ employee_id }) => {
      const res = await fetch(
        `${API_BASE}/contracts/employee/${employee_id}/gerar-contrato-html`,
        { method: 'POST', headers: getAuthHeaders() }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(msgFromDetail(err?.detail) || `Erro ${res.status}`);
      }
      return res.json();
    },
  });
}
