'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  Users, UserCheck, UserX, FileText, TrendingUp,
  Briefcase, Gift, GraduationCap, Star, Wind, BarChart3,
  AlertTriangle, CheckCircle, CheckCircle2, ArrowRight, Loader2,
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

interface CargoItem {
  cargo: string;
  total: number;
  ativos: number;
}

interface CCTResumo {
  sindicato?: string;
  nome?: string;
  vigencia?: string;
  vigencia_inicio?: string;
  vigencia_fim?: string;
  total_cargos?: number;
  vinculados_cct?: number;
  conformidade_pct?: number;
  status?: string;
}

export default function DashboardRH() {
  const [resumo, setResumo] = useState<HeadcountResumo | null>(null);
  const [cargos, setCargos] = useState<CargoItem[]>([]);
  const [cct, setCCT] = useState<CCTResumo | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/reports/headcount`, { headers: getAuthHeaders() })
        .then((r) => r.json()),
      fetch(`${API_BASE}/cct/resumo`, { headers: getAuthHeaders() })
        .then((r) => r.json()),
    ])
      .then(([hc, cctData]) => {
        setResumo(hc.resumo ?? hc);
        setCargos(hc.por_cargo ?? []);
        setCCT(cctData);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const submodulos = [
    { label: 'CCT', href: 'rh/cct', icon: FileText, desc: '52 cargos' },
    { label: 'Cargos', href: 'rh/cargos', icon: Briefcase, desc: 'SINDECOMPRESTS' },
    { label: 'Benefícios', href: 'rh/beneficios', icon: Gift, desc: '157 registros' },
    { label: 'Treinamentos', href: 'rh/treinamentos', icon: GraduationCap, desc: '8 cursos' },
    { label: 'Desempenho', href: 'rh/desempenho', icon: Star, desc: '15 avaliações' },
    { label: 'Clima', href: 'rh/clima', icon: Wind, desc: '3 pesquisas' },
    { label: 'Relatórios', href: 'rh/relatorios', icon: BarChart3, desc: 'Headcount' },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-[#F97316]" />
        <span className="ml-3 text-gray-500">Carregando RH...</span>
      </div>
    );
  }

  const r = resumo;
  const metricas = [
    {
      label: 'Total Funcionários',
      valor: r?.total_geral ?? 52,
      icon: Users,
      cor: 'text-[#1E3A5F]',
      bg: 'bg-blue-50',
      iconCor: 'text-blue-600',
    },
    {
      label: 'Ativos',
      valor: r?.total_ativos ?? 41,
      icon: UserCheck,
      cor: 'text-green-600',
      bg: 'bg-green-50',
      iconCor: 'text-green-600',
    },
    {
      label: 'Inativos',
      valor: r?.total_inativos ?? 11,
      icon: UserX,
      cor: 'text-red-600',
      bg: 'bg-red-50',
      iconCor: 'text-red-500',
    },
    {
      label: 'Índice de Atividade',
      valor: `${r?.indice_atividade ?? 78.8}%`,
      icon: TrendingUp,
      cor: 'text-orange-600',
      bg: 'bg-orange-50',
      iconCor: 'text-[#F97316]',
    },
  ];

  return (
    <div className="min-h-screen bg-[#F8F9FB] p-6 overflow-x-hidden">
      {/* Cabeçalho */}
      <div className="mb-8">
        <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Recursos Humanos</h1>
        <p className="text-gray-500 mt-1">
          Gestão de pessoas, CCT, benefícios e desenvolvimento
        </p>
      </div>

      {/* Cards métricas */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {metricas.map((m) => {
          const Icon = m.icon;
          return (
            <Card key={m.label} className="border border-gray-100">
              <CardContent className="p-6">
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

      {/* CCT + Headcount por cargo */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Card CCT */}
        <Card className="border border-gray-100">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg text-[#1E3A5F]">
                Convenção Coletiva
              </CardTitle>
              <span className="px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700 border border-green-200 flex items-center gap-1">
                <CheckCircle className="w-3 h-3" /> Vigente
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div>
                <p className="text-sm text-gray-500">Sindicato</p>
                <p className="font-semibold text-gray-900">
                  {cct?.sindicato ?? cct?.nome ?? 'SINDECOMPRESTS'}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-gray-500">Início</p>
                  <p className="font-medium text-gray-800">
                    {cct?.vigencia_inicio
                      ? new Date(cct.vigencia_inicio).toLocaleDateString('pt-BR')
                      : cct?.vigencia ? `01/01/${cct.vigencia}` : '01/01/2026'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Fim</p>
                  <p className="font-medium text-gray-800">
                    {cct?.vigencia_fim
                      ? new Date(cct.vigencia_fim).toLocaleDateString('pt-BR')
                      : cct?.vigencia ? `31/12/${cct.vigencia}` : '31/12/2026'}
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-gray-500">Cargos cadastrados</p>
                  <p className="font-semibold text-gray-900">
                    {cct?.total_cargos ?? 52}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Conformidade</p>
                  <p className="font-semibold text-green-600 inline-flex items-center gap-1">
                    {cct?.conformidade_pct ?? 100}% <CheckCircle2 className="w-4 h-4" />
                  </p>
                </div>
              </div>
              <Link
                href="/modulos/gestao-pessoas/rh/cct"
                className="flex items-center justify-center gap-2 mt-2 py-2 rounded-lg border border-[#1E3A5F] text-[#1E3A5F] text-sm font-medium hover:bg-blue-50 transition-colors"
              >
                Ver detalhes da CCT <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </CardContent>
        </Card>

        {/* Headcount por cargo */}
        <Card className="border border-gray-100">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg text-[#1E3A5F]">
              Headcount por Cargo
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {cargos.slice(0, 5).map((c) => {
                const pct =
                  c.total > 0 ? Math.round((c.ativos / c.total) * 100) : 0;
                return (
                  <div key={c.cargo}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-gray-700 font-medium truncate max-w-[60%]">
                        {c.cargo}
                      </span>
                      <span className="text-gray-500 shrink-0">
                        {c.ativos}/{c.total} ({pct}%)
                      </span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-2">
                      <div
                        className={`h-2 rounded-full transition-all ${
                          pct >= 80
                            ? 'bg-green-500'
                            : pct >= 60
                              ? 'bg-orange-400'
                              : 'bg-red-400'
                        }`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
            <Link
              href="/modulos/gestao-pessoas/rh/relatorios"
              className="flex items-center justify-center gap-2 mt-4 py-2 rounded-lg border border-[#F97316] text-[#F97316] text-sm font-medium hover:bg-orange-50 transition-colors"
            >
              Ver relatório completo <ArrowRight className="w-4 h-4" />
            </Link>
          </CardContent>
        </Card>
      </div>

      {/* Alertas */}
      <div className="space-y-3 mb-8">
        {(r?.total_inativos ?? 11) > 0 && (
          <div className="bg-orange-50 border border-orange-200 rounded-lg p-4 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-orange-500 shrink-0 mt-0.5" />
            <div>
              <p className="font-medium text-orange-800">
                {r?.total_inativos ?? 11} funcionários inativos
              </p>
              <p className="text-sm text-orange-600 mt-0.5">
                Verifique a situação e atualize o status de cada funcionário.
              </p>
            </div>
          </div>
        )}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-center gap-3">
          <CheckCircle className="w-5 h-5 text-blue-500 shrink-0" />
          <p className="text-blue-800 text-sm">
            CCT {cct?.sindicato || 'SINDECOMPRESTS'} {cct?.vigencia || '2026'} vigente até{' '}
            {cct?.vigencia ? `31/12/${cct.vigencia}` : '31/12/2026'} — conformidade{' '}
            {cct?.conformidade_pct ?? 100}%
          </p>
        </div>
      </div>

      {/* Navegação rápida */}
      <div>
        <h2 className="text-lg font-semibold text-[#1E3A5F] mb-4">
          Submódulos
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          {submodulos.map((s) => {
            const Icon = s.icon;
            return (
              <Link
                key={s.href}
                href={`/modulos/gestao-pessoas/${s.href}`}
                className="bg-white rounded-xl border border-gray-100 p-4 flex flex-col items-center gap-2 hover:border-[#F97316] hover:shadow-md transition-all text-center group min-h-0"
              >
                <div className="w-10 h-10 bg-gray-50 group-hover:bg-orange-50 rounded-lg flex items-center justify-center transition-colors">
                  <Icon className="w-5 h-5 text-gray-500 group-hover:text-[#F97316] transition-colors" />
                </div>
                <span className="text-xs font-medium text-gray-700">
                  {s.label}
                </span>
                <span className="text-xs text-gray-400">{s.desc}</span>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
