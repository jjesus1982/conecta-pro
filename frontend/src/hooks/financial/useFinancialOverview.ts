import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { IFinancialOverview } from '@/types/financial';

/**
 * KPIs do financeiro a partir do endpoint REAL /financial/dashboard.
 * O endpoint devolve estrutura aninhada (100% real: bank_transactions/accounts/
 * receivables); aqui mapeamos pro shape flat IFinancialOverview que as telas usam.
 * (Antes vinha aliasado do bi_dashboard/stats — meta-contagem de dashboards, sem
 * esses campos → KPIs renderizavam undefined.)
 */
export function useFinancialOverview(params?: { condominio_id?: string }) {
  return useQuery({
    queryKey: ['financial-overview', params?.condominio_id ?? null],
    queryFn: async (): Promise<IFinancialOverview> => {
      const { data } = await api.get('/api/v1/financial/dashboard', { params });
      return {
        receita_total: Number(data?.mes_atual?.entradas ?? 0),
        despesa_total: Number(data?.mes_atual?.saidas ?? 0),
        saldo: Number(data?.saldo?.atual ?? 0),
        inadimplencia: Number(data?.contas_receber?.vencido ?? 0),
      };
    },
    staleTime: 60_000,
  });
}
