'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';
import { Trophy, TrendingUp, TrendingDown } from 'lucide-react';

interface Tender {
  id: string;
  numero_edital?: string;
  orgao?: string;
  objeto?: string;
  valor_estimado?: number;
  status: string;
  data_abertura?: string;
  updated_at?: string;
}

export default function ResultadosLicitacoesPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['bidding-tenders-results'],
    queryFn: () => customInstance({ url: '/api/v1/bidding/tenders', method: 'GET' }),
    staleTime: 30_000,
  });

  const resultados = useMemo(() => {
    const items: Tender[] = (data as any)?.items || (data as any)?.tenders || [];
    return items.filter((t) => t.status === 'won' || t.status === 'lost' || t.status === 'vencida' || t.status === 'perdida');
  }, [data]);

  const totalVencidas = resultados.filter((r) => r.status === 'won' || r.status === 'vencida').length;
  const totalPerdidas = resultados.filter((r) => r.status === 'lost' || r.status === 'perdida').length;
  const valorVencidas = resultados
    .filter((r) => r.status === 'won' || r.status === 'vencida')
    .reduce((acc, r) => acc + (r.valor_estimado || 0), 0);

  if (isLoading) return <div className="p-8 text-center text-gray-500">Carregando resultados...</div>;
  if (error) return <div className="p-8 text-center text-red-500">Erro ao carregar resultados</div>;

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center gap-3">
        <Trophy className="h-7 w-7 text-yellow-500" />
        <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Resultados de Licitacoes</h1>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border p-4">
          <div className="flex items-center gap-2 text-gray-500 text-sm mb-1">
            <TrendingUp className="h-4 w-4 text-green-500" /> Vencidas
          </div>
          <p className="font-data text-2xl font-semibold tabular-nums text-green-600">{totalVencidas}</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <div className="flex items-center gap-2 text-gray-500 text-sm mb-1">
            <TrendingDown className="h-4 w-4 text-red-500" /> Perdidas
          </div>
          <p className="font-data text-2xl font-semibold tabular-nums text-red-600">{totalPerdidas}</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <div className="flex items-center gap-2 text-gray-500 text-sm mb-1">
            <Trophy className="h-4 w-4 text-yellow-500" /> Valor Total Vencidas
          </div>
          <p className="font-data text-2xl font-semibold tabular-nums text-green-600">
            R$ {valorVencidas.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
          </p>
        </div>
      </div>

      {/* Tabela */}
      <div className="bg-white rounded-xl border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="text-left p-3 font-semibold text-gray-600">Edital</th>
              <th className="text-left p-3 font-semibold text-gray-600">Orgao</th>
              <th className="text-right p-3 font-semibold text-gray-600">Valor</th>
              <th className="text-center p-3 font-semibold text-gray-600">Resultado</th>
              <th className="text-center p-3 font-semibold text-gray-600">Data</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {resultados.length === 0 ? (
              <tr>
                <td colSpan={5} className="p-6 text-center text-gray-400">
                  Nenhum resultado registrado ainda
                </td>
              </tr>
            ) : (
              resultados.map((r) => {
                const isWon = r.status === 'won' || r.status === 'vencida';
                return (
                  <tr key={r.id} className="hover:bg-gray-50">
                    <td className="p-3 font-medium">{r.numero_edital || '-'}</td>
                    <td className="p-3">{r.orgao || '-'}</td>
                    <td className="p-3 text-right">
                      {r.valor_estimado
                        ? `R$ ${r.valor_estimado.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`
                        : '-'}
                    </td>
                    <td className="p-3 text-center">
                      <span
                        className={`px-2 py-1 rounded-full text-xs font-medium ${
                          isWon ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                        }`}
                      >
                        {isWon ? 'Vencida' : 'Perdida'}
                      </span>
                    </td>
                    <td className="p-3 text-center text-gray-500">
                      {r.updated_at ? r.updated_at.split('T')[0] : r.data_abertura?.split('T')[0] || '-'}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
