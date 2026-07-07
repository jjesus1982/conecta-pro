'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  ArrowLeft, Users, UserCheck, UserX, TrendingUp,
  BarChart3, Download, Loader2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const API_BASE = '/api/v1/people-management/hr';

function getAuthHeaders() {
  let token: string | null = null;
  if (typeof window !== 'undefined') {
    try {
      token = localStorage.getItem('access_token') || localStorage.getItem('token');
    } catch {
      token = null;
    }
  }
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

interface HeadcountResumo {
  total_geral: number;
  total_ativos: number;
  total_inativos: number;
  indice_atividade: number;
}

interface PorStatus {
  status: string;
  total: number;
}

interface PorCargo {
  cargo: string;
  total: number;
  ativos: number;
}

interface HeadcountData {
  resumo: HeadcountResumo;
  por_status: PorStatus[];
  por_cargo: PorCargo[];
}

export default function PageRelatorios() {
  const [data, setData] = useState<HeadcountData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/reports/headcount`, { headers: getAuthHeaders() })
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const r = data?.resumo;
  const porCargo = data?.por_cargo ?? [];
  const porStatus = data?.por_status ?? [];

  const metricas = [
    {
      label: 'Total Funcionários',
      valor: r?.total_geral ?? '—',
      icon: Users,
      bg: 'bg-blue-50',
      iconCor: 'text-blue-600',
      cor: 'text-[#1E3A5F]',
    },
    {
      label: 'Ativos',
      valor: r?.total_ativos ?? '—',
      icon: UserCheck,
      bg: 'bg-green-50',
      iconCor: 'text-green-600',
      cor: 'text-green-600',
    },
    {
      label: 'Inativos',
      valor: r?.total_inativos ?? '—',
      icon: UserX,
      bg: 'bg-red-50',
      iconCor: 'text-red-500',
      cor: 'text-red-600',
    },
    {
      label: 'Índice de Atividade',
      valor: r?.indice_atividade != null ? `${r.indice_atividade}%` : '—',
      icon: TrendingUp,
      bg: 'bg-orange-50',
      iconCor: 'text-[#F97316]',
      cor: 'text-[#F97316]',
    },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-[#F97316]" />
        <span className="ml-3 text-gray-500">Carregando relatório...</span>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F8F9FB] p-6">
      <div className="flex items-center gap-3 mb-6">
        <Link
          href="/modulos/gestao-pessoas/rh"
          className="flex items-center gap-1 text-gray-400 hover:text-[#1E3A5F] transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Voltar
        </Link>
        <span className="text-gray-300">|</span>
        <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Relatórios RH</h1>
        <button
          className="ml-auto flex items-center gap-2 px-4 py-2 bg-[#1E3A5F] text-white text-sm font-medium rounded-lg hover:bg-[#16305a] transition-colors"
          onClick={() => {
            const rows: (string | number)[][] = [['Cargo', 'Total', 'Ativos', 'Inativos', '% Atividade']];
            (data?.por_cargo || []).forEach((c) => {
              const inativos = c.total - c.ativos;
              const pct = c.total > 0 ? Math.round((c.ativos / c.total) * 100) : 0;
              rows.push([c.cargo, c.total, c.ativos, inativos, `${pct}%`]);
            });
            const csv = rows.map((r) => r.join(';')).join('\n');
            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `headcount_rh_${new Date().toISOString().slice(0, 10)}.csv`;
            a.click();
            URL.revokeObjectURL(url);
          }}
        >
          <Download className="w-4 h-4" /> Exportar
        </button>
      </div>

      {/* Seção: Headcount */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-4">
          <BarChart3 className="w-5 h-5 text-[#1E3A5F]" />
          <h2 className="text-lg font-semibold text-[#1E3A5F]">Headcount Geral</h2>
        </div>

        {/* KPIs */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          {metricas.map((m) => {
            const Icon = m.icon;
            return (
              <Card key={m.label} className="border border-gray-100">
                <CardContent className="p-5">
                  <div
                    className={`w-10 h-10 ${m.bg} rounded-lg flex items-center justify-center mb-3`}
                  >
                    <Icon className={`w-5 h-5 ${m.iconCor}`} />
                  </div>
                  <p className="text-sm text-gray-500">{m.label}</p>
                  <p className={`font-data text-2xl font-semibold tabular-nums mt-1 ${m.cor}`}>{m.valor}</p>
                </CardContent>
              </Card>
            );
          })}
        </div>

        {/* Por cargo + Por status */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Por cargo — barra horizontal */}
          <div className="lg:col-span-2">
            <Card className="border border-gray-100">
              <CardHeader className="pb-2">
                <CardTitle className="text-base text-[#1E3A5F]">
                  Headcount por Cargo
                </CardTitle>
              </CardHeader>
              <CardContent>
                {porCargo.length > 0 ? (
                  <div className="space-y-4">
                    {porCargo.map((c) => {
                      const pct =
                        c.total > 0 ? Math.round((c.ativos / c.total) * 100) : 0;
                      return (
                        <div key={c.cargo}>
                          <div className="flex justify-between text-sm mb-1.5">
                            <span className="text-gray-700 font-medium truncate max-w-[55%]">
                              {c.cargo}
                            </span>
                            <span className="text-gray-500 text-xs shrink-0">
                              {c.ativos} ativos / {c.total} total · {pct}%
                            </span>
                          </div>
                          <div className="relative w-full bg-gray-100 rounded-full h-2.5">
                            <div
                              className="absolute inset-y-0 left-0 bg-gray-200 rounded-full"
                              style={{ width: '100%' }}
                            />
                            <div
                              className={`absolute inset-y-0 left-0 rounded-full transition-all ${
                                pct >= 80
                                  ? 'bg-green-500'
                                  : pct >= 60
                                    ? 'bg-[#F97316]'
                                    : 'bg-red-400'
                              }`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-gray-400 text-sm py-4 text-center">
                    Sem dados de cargo disponíveis
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Por status — pizza simplificada */}
          <div>
            <Card className="border border-gray-100">
              <CardHeader className="pb-2">
                <CardTitle className="text-base text-[#1E3A5F]">
                  Por Status
                </CardTitle>
              </CardHeader>
              <CardContent>
                {porStatus.length > 0 ? (
                  <div className="space-y-3">
                    {porStatus.map((s) => {
                      const total = r?.total_geral ?? 1;
                      const pct = Math.round((s.total / total) * 100);
                      const cor =
                        s.status === 'ativo'
                          ? 'bg-green-500'
                          : s.status === 'inativo'
                            ? 'bg-red-400'
                            : 'bg-gray-400';
                      return (
                        <div key={s.status} className="flex items-center gap-3">
                          <div className={`w-3 h-3 rounded-full ${cor} shrink-0`} />
                          <div className="flex-1 min-w-0">
                            <div className="flex justify-between text-sm mb-1">
                              <span className="text-gray-700 capitalize">{s.status}</span>
                              <span className="text-gray-500 font-semibold">
                                {s.total} ({pct}%)
                              </span>
                            </div>
                            <div className="w-full bg-gray-100 rounded-full h-1.5">
                              <div
                                className={`h-1.5 rounded-full ${cor}`}
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-gray-400 text-sm py-4 text-center">
                    Sem dados de status
                  </p>
                )}

                {r && (
                  <div className="mt-4 pt-4 border-t border-gray-100">
                    <p className="text-xs text-gray-400 mb-1">Índice de atividade</p>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-gray-100 rounded-full h-2">
                        <div
                          className="h-2 rounded-full bg-[#F97316]"
                          style={{ width: `${r.indice_atividade}%` }}
                        />
                      </div>
                      <span className="text-sm font-bold text-[#F97316]">
                        {r.indice_atividade}%
                      </span>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      {/* Tabela detalhada por cargo */}
      {porCargo.length > 0 && (
        <Card className="border border-gray-100">
          <CardHeader>
            <CardTitle className="text-base text-[#1E3A5F]">
              Detalhe por Cargo — {porCargo.length} cargos
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100">
                    <th className="text-left py-3 px-4 text-gray-500 font-medium">Cargo</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium">Total</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium">Ativos</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium">Inativos</th>
                    <th className="text-right py-3 px-4 text-gray-500 font-medium">% Atividade</th>
                  </tr>
                </thead>
                <tbody>
                  {porCargo.map((c) => {
                    const inativos = c.total - c.ativos;
                    const pct =
                      c.total > 0 ? Math.round((c.ativos / c.total) * 100) : 0;
                    return (
                      <tr key={c.cargo} className="border-b border-gray-50 hover:bg-gray-50">
                        <td className="py-3 px-4 font-medium text-gray-900">{c.cargo}</td>
                        <td className="py-3 px-4 text-right text-gray-700">{c.total}</td>
                        <td className="py-3 px-4 text-right text-green-600 font-medium">
                          {c.ativos}
                        </td>
                        <td className="py-3 px-4 text-right text-red-500">{inativos}</td>
                        <td className="py-3 px-4 text-right">
                          <span
                            className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                              pct >= 80
                                ? 'bg-green-100 text-green-700'
                                : pct >= 60
                                  ? 'bg-orange-100 text-orange-700'
                                  : 'bg-red-100 text-red-600'
                            }`}
                          >
                            {pct}%
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr className="border-t border-gray-200 bg-gray-50">
                    <td className="py-3 px-4 font-semibold text-gray-900">Total</td>
                    <td className="py-3 px-4 text-right font-bold text-[#1E3A5F]">
                      {r?.total_geral ?? '—'}
                    </td>
                    <td className="py-3 px-4 text-right font-bold text-green-600">
                      {r?.total_ativos ?? '—'}
                    </td>
                    <td className="py-3 px-4 text-right font-bold text-red-500">
                      {r?.total_inativos ?? '—'}
                    </td>
                    <td className="py-3 px-4 text-right font-bold text-[#F97316]">
                      {r?.indice_atividade != null ? `${r.indice_atividade}%` : '—'}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
