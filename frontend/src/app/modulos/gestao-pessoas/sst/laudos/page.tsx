'use client';

import { useQuery } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';
import { FileText, Shield, AlertTriangle, CheckCircle, Clock, Building2, User, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import Link from 'next/link';

interface RiskFactor {
  agente: string;
  tipo: string;
  nr_referencia: string;
}

interface LTCATStatus {
  documento: string;
  base_legal: string;
  empresa: string;
  cnpj: string;
  vigencia: string;
  responsavel_tecnico: string;
  postos_avaliados: number;
  status: string;
  fatores_risco: RiskFactor[];
  proxima_acao: string;
}

const statusConfig: Record<string, { label: string; color: string; bg: string; icon: typeof CheckCircle }> = {
  vigente: { label: 'Vigente', color: 'text-green-700', bg: 'bg-green-50 border-green-200', icon: CheckCircle },
  pendente_elaboracao: { label: 'Pendente de Elaboracao', color: 'text-amber-700', bg: 'bg-amber-50 border-amber-200', icon: Clock },
  vencido: { label: 'Vencido', color: 'text-red-700', bg: 'bg-red-50 border-red-200', icon: AlertTriangle },
  em_revisao: { label: 'Em Revisao', color: 'text-blue-700', bg: 'bg-blue-50 border-blue-200', icon: Clock },
};

const tipoColors: Record<string, string> = {
  fisico: 'bg-blue-100 text-blue-800',
  quimico: 'bg-purple-100 text-purple-800',
  biologico: 'bg-green-100 text-green-800',
  ergonomico: 'bg-amber-100 text-amber-800',
  'ergonômico': 'bg-amber-100 text-amber-800',
  acidente: 'bg-red-100 text-red-800',
};

export default function LTCATPage() {
  const { data, isLoading, error } = useQuery<LTCATStatus>({
    queryKey: ['sst', 'ltcat', 'status'],
    queryFn: () => customInstance({ url: '/api/v1/people-management/sst/ltcat/status' }) as Promise<LTCATStatus>,
    staleTime: 60000,
    retry: 2,
  });

  if (isLoading) {
    return (
      <div className="p-6 space-y-6 animate-pulse">
        <div className="h-8 w-64 bg-gray-200 rounded" />
        <div className="grid grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => <div key={i} className="h-24 bg-gray-100 rounded-xl" />)}
        </div>
        <div className="h-64 bg-gray-100 rounded-xl" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <AlertTriangle className="w-10 h-10 text-red-400 mx-auto mb-3" />
          <p className="font-medium text-red-800">Erro ao carregar LTCAT</p>
          <p className="text-sm text-red-600 mt-1">Verifique a conexao com o servidor.</p>
        </div>
      </div>
    );
  }

  const st = statusConfig[data.status as keyof typeof statusConfig] ?? { icon: Clock, color: 'text-gray-500', bg: 'bg-gray-50', label: data.status };
  const StatusIcon = st.icon;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-50 rounded-lg">
            <FileText className="w-6 h-6 text-indigo-600" />
          </div>
          <div>
            <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">LTCAT</h1>
            <p className="text-gray-500 text-sm">Laudo Tecnico das Condicoes Ambientais de Trabalho</p>
          </div>
          <span className="ml-3 px-2.5 py-1 text-xs font-medium bg-indigo-100 text-indigo-700 rounded-full">
            NR-15 / Lei 8.213
          </span>
        </div>
        <div className="flex gap-2">
          <Link href="/modulos/gestao-pessoas/sst">
            <Button type="button" variant="outline" size="sm">Voltar ao SST</Button>
          </Link>
        </div>
      </div>

      {/* Status Banner */}
      <div className={`rounded-xl border p-4 ${st.bg}`}>
        <div className="flex items-center gap-3">
          <StatusIcon className={`w-5 h-5 ${st.color}`} />
          <div>
            <p className={`font-semibold ${st.color}`}>Status: {st.label}</p>
            <p className="text-sm text-gray-600 mt-0.5">{data.proxima_acao}</p>
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">Postos Avaliados</p>
                <p className="font-data text-2xl font-semibold tabular-nums mt-1">{data.postos_avaliados}</p>
              </div>
              <div className="p-2 bg-blue-50 rounded-lg">
                <Building2 className="w-5 h-5 text-blue-600" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">Agentes de Risco</p>
                <p className="font-data text-2xl font-semibold tabular-nums mt-1">{data.fatores_risco.length}</p>
              </div>
              <div className="p-2 bg-amber-50 rounded-lg">
                <AlertTriangle className="w-5 h-5 text-amber-600" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">Vigencia</p>
                <p className="text-lg font-bold mt-1">{data.vigencia.split(' a ')[0]}</p>
                <p className="text-xs text-gray-400">a {data.vigencia.split(' a ')[1]}</p>
              </div>
              <div className="p-2 bg-green-50 rounded-lg">
                <Shield className="w-5 h-5 text-green-600" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">Resp. Tecnico</p>
                <p className="text-sm font-bold mt-1">{data.responsavel_tecnico}</p>
              </div>
              <div className="p-2 bg-purple-50 rounded-lg">
                <User className="w-5 h-5 text-purple-600" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Company Info */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Dados da Empresa</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-gray-500">Razao Social:</span>
              <p className="font-medium">{data.empresa}</p>
            </div>
            <div>
              <span className="text-gray-500">CNPJ:</span>
              <p className="font-medium">{data.cnpj}</p>
            </div>
            <div>
              <span className="text-gray-500">Base Legal:</span>
              <p className="font-medium">{data.base_legal}</p>
            </div>
            <div>
              <span className="text-gray-500">Documento:</span>
              <p className="font-medium">{data.documento}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Risk Factors Table */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-600" />
            Fatores de Risco Identificados
          </CardTitle>
        </CardHeader>
        <CardContent>
          {data.fatores_risco.length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              <Shield className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="font-medium">Nenhum fator de risco cadastrado</p>
              <p className="text-sm mt-1">O LTCAT precisa ser elaborado por engenheiro de seguranca.</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b">
                  <th className="pb-3">Agente de Risco</th>
                  <th className="pb-3">Tipo</th>
                  <th className="pb-3">NR Referencia</th>
                </tr>
              </thead>
              <tbody>
                {data.fatores_risco.map((fr, i) => (
                  <tr key={i} className="border-t hover:bg-gray-50">
                    <td className="py-3 font-medium">{fr.agente}</td>
                    <td className="py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${tipoColors[fr.tipo] || 'bg-gray-100 text-gray-700'}`}>
                        {fr.tipo}
                      </span>
                    </td>
                    <td className="py-3 text-gray-500">{fr.nr_referencia}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
