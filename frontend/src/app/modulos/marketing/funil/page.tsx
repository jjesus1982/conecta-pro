'use client';
import { useQuery } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';
import { Filter, ArrowRight } from 'lucide-react';

const STAGE_COLORS = ['bg-blue-200', 'bg-cyan-200', 'bg-teal-300', 'bg-green-400'];

export default function FunilPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['marketing-funil-real'],
    queryFn: () => customInstance({ url: '/api/v1/marketing/funil', method: 'GET' }),
    staleTime: 30_000,
  });

  const d = data as any;
  const stages = (d?.funil || []) as { stage: string; value: number }[];
  const origens = (d?.por_origem || []) as any[];
  const totais = d?.totais || {};
  const fmtBRL = (v: number) => 'R$ ' + (v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 });

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><Filter className="h-6 w-6" />Funil de Vendas</h1>
        <p className="text-gray-500">Pipeline com dados reais: leads → qualificados → clientes</p>
      </div>

      {isLoading && <p className="text-sm text-gray-400">Carregando dados reais...</p>}

      {/* Funil */}
      <div className="flex items-center justify-center gap-2 py-6 flex-wrap">
        {stages.map((s, i) => (
          <div key={i} className="flex items-center gap-2">
            <div className={`${STAGE_COLORS[i] || 'bg-gray-200'} rounded-xl p-6 text-center min-w-[150px]`}>
              <p className="text-3xl font-bold">{s.value}</p>
              <p className="text-sm font-medium mt-1">{s.stage}</p>
            </div>
            {i < stages.length - 1 && <ArrowRight className="h-5 w-5 text-gray-400" />}
          </div>
        ))}
      </div>

      {/* Indicadores */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-500">MRR Total</p>
          <p className="text-2xl font-bold text-green-600">{fmtBRL(totais.mrr_total)}</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-500">Taxa Lead → Qualificado</p>
          <p className="text-2xl font-bold">{totais.taxa_lead_qualificado ?? 0}%</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-500">Taxa Lead → Cliente</p>
          <p className="text-2xl font-bold">{totais.taxa_lead_cliente ?? 0}%</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-500">Clientes ativos</p>
          <p className="text-2xl font-bold">{totais.clientes_ativos ?? 0}</p>
        </div>
      </div>

      {/* Por origem */}
      <div className="bg-white rounded-xl border p-4">
        <h2 className="font-semibold mb-3">Desempenho por Origem</h2>
        {origens.length === 0 ? (
          <p className="text-sm text-gray-400">Sem dados ainda.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left p-2">Origem</th>
                <th className="text-right p-2">Leads</th>
                <th className="text-right p-2">Qualificados</th>
                <th className="text-right p-2">Clientes</th>
                <th className="text-right p-2">Conversão</th>
                <th className="text-right p-2">MRR</th>
              </tr>
            </thead>
            <tbody>
              {origens.map((o, i) => (
                <tr key={i} className="border-t">
                  <td className="p-2 font-medium capitalize">{o.origem}</td>
                  <td className="p-2 text-right">{o.leads}</td>
                  <td className="p-2 text-right">{o.qualificados}</td>
                  <td className="p-2 text-right">{o.clientes}</td>
                  <td className="p-2 text-right">{o.conversao}%</td>
                  <td className="p-2 text-right text-green-600">{fmtBRL(o.mrr)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="text-xs text-gray-400 mt-3">
          "Direto" = clientes da base sem lead de origem vinculado. Conforme o marketing rodar (UTM/anúncios),
          as origens pagas passam a aparecer aqui com CAC e ROI.
        </p>
      </div>
    </div>
  );
}
