import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { IFinancialOverview } from '@/types/financial';

/**
 * KPIs do financeiro (receita/despesa/saldo/inadimplencia).
 *
 * Bate no endpoint REAL que já serve a tela /modulos/financeiro:
 * GET /financial/bi-dashboard/bi/dashboards/stats — servido pelo shim
 * `modules/ged/controllers/financial_overview_controller.py`, que devolve
 * IFinancialOverview 100% do banco (nfse_emitidas/payables/bank_accounts/receivables).
 *
 * O nome do path é legado (o subsistema bi_dashboard foi removido — era casca dormente,
 * o shim já o sombreava e cobre o dado real). Mantido o path por ser o contrato vivo.
 * Antes vinha via hook Orval gerado (tipado como DashboardStats, desalinhado do runtime);
 * agora é explícito e não depende dos types gerados do subsistema deletado.
 */
export function useFinancialOverview(params?: { condominio_id?: string }) {
  return useQuery({
    queryKey: ['financial-overview', params?.condominio_id ?? null],
    queryFn: async (): Promise<IFinancialOverview> => {
      const { data } = await api.get('/api/v1/financial/bi-dashboard/bi/dashboards/stats', { params });
      return {
        receita_total: Number(data?.receita_total ?? 0),
        despesa_total: Number(data?.despesa_total ?? 0),
        saldo: Number(data?.saldo ?? 0),
        inadimplencia: Number(data?.inadimplencia ?? 0),
      };
    },
    staleTime: 60_000,
  });
}
