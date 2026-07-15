import { useMutation } from '@tanstack/react-query';
import { msgFromDetail } from '@/lib/string';

const API_BASE = '/api/v1/people-management/hr';

function getAuthHeaders(): HeadersInit {
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
  formato: 'html' | 'pdf';
}

export interface GerarAvisoPrevioFeriasParams {
  employee_id: string;
  data_inicio_ferias: string;
  dias?: number;
}

export function useGerarAvisoPrevioFerias() {
  return useMutation<ContratoGeradoResponse, Error, GerarAvisoPrevioFeriasParams>({
    mutationFn: async ({ employee_id, data_inicio_ferias, dias = 30 }) => {
      const params = new URLSearchParams({
        data_inicio_ferias,
        dias: String(dias),
      });
      const res = await fetch(
        `${API_BASE}/contracts/employee/${employee_id}/gerar-aviso-previo-ferias-html?${params}`,
        { method: 'POST', headers: getAuthHeaders() },
      );
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(msgFromDetail(err?.detail) || `Erro ${res.status}`);
      }
      return res.json();
    },
  });
}
