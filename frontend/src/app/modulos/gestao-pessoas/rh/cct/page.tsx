'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  ArrowLeft, CheckCircle, CheckCircle2, Search, FileText, TrendingUp,
  Users, Calendar, Loader2,
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

interface CCTResumo {
  sindicato?: string;
  nome?: string;
  vigencia?: string;
  vigencia_inicio?: string;
  vigencia_fim?: string;
  total_cargos?: number;
  vinculados_cct?: number;
  sem_vinculo?: number;
  conformidade_pct?: number;
  status?: string;
}

interface CCTCargo {
  id: string;
  cargo_nome?: string;
  nome?: string;
  name?: string;
  piso_salarial?: number;
  salario_base?: number;
  adicional_insalubridade_percentual?: number;
  adicional_periculosidade_percentual?: number;
  jornada_semanal_horas?: number;
}

export default function PageCCT() {
  const [cct, setCCT] = useState<CCTResumo | null>(null);
  const [cargos, setCargos] = useState<CCTCargo[]>([]);
  const [loading, setLoading] = useState(true);
  const [busca, setBusca] = useState('');

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/cct/resumo`, { headers: getAuthHeaders() }).then((r) =>
        r.json()
      ),
      fetch(`${API_BASE}/cct/cargos`, { headers: getAuthHeaders() }).then((r) =>
        r.json()
      ),
    ])
      .then(([resumo, cargosData]) => {
        setCCT(resumo);
        const lista = Array.isArray(cargosData)
          ? cargosData
          : (cargosData.cargos ?? cargosData.data ?? []);
        setCargos(lista);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const fmt = (v?: number) =>
    v != null
      ? v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
      : 'R$ —';

  const cargosFiltrados = cargos.filter((c) =>
    (c.cargo_nome ?? c.nome ?? c.name ?? '')
      .toLowerCase()
      .includes(busca.toLowerCase())
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-[#F97316]" />
        <span className="ml-3 text-gray-500">Carregando CCT...</span>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F8F9FB] p-6">
      {/* Cabeçalho */}
      <div className="flex items-center gap-3 mb-6">
        <Link
          href="/modulos/gestao-pessoas/rh"
          className="flex items-center gap-1 text-gray-400 hover:text-[#1E3A5F] transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Voltar
        </Link>
        <span className="text-gray-300">|</span>
        <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">
          Convenção Coletiva de Trabalho
        </h1>
      </div>

      {/* Card principal CCT */}
      <Card className="border border-gray-100 mb-6">
        <CardContent className="p-6">
          <div className="flex items-start justify-between mb-6">
            <div>
              <p className="text-sm text-gray-500 mb-1">Sindicato</p>
              <h2 className="text-xl font-bold text-[#1E3A5F]">
                {cct?.sindicato ?? cct?.nome ?? 'SINDECOMPRESTS'}
              </h2>
              <p className="text-sm text-gray-400 mt-1">
                Vigência {cct?.vigencia ?? '2026'}
              </p>
            </div>
            <span className="px-3 py-1.5 rounded-full text-sm font-medium bg-green-100 text-green-700 border border-green-200 flex items-center gap-1.5">
              <CheckCircle className="w-4 h-4" /> Vigente
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div className="bg-blue-50 rounded-lg p-4">
              <Calendar className="w-5 h-5 text-blue-600 mb-2" />
              <p className="text-xs text-gray-500">Início da vigência</p>
              <p className="font-semibold text-gray-900 mt-1">
                {cct?.vigencia_inicio
                  ? new Date(cct.vigencia_inicio).toLocaleDateString('pt-BR')
                  : '01/01/2026'}
              </p>
            </div>
            <div className="bg-orange-50 rounded-lg p-4">
              <Calendar className="w-5 h-5 text-orange-500 mb-2" />
              <p className="text-xs text-gray-500">Fim da vigência</p>
              <p className="font-semibold text-gray-900 mt-1">
                {cct?.vigencia_fim
                  ? new Date(cct.vigencia_fim).toLocaleDateString('pt-BR')
                  : '31/12/2026'}
              </p>
            </div>
            <div className="bg-purple-50 rounded-lg p-4">
              <FileText className="w-5 h-5 text-purple-600 mb-2" />
              <p className="text-xs text-gray-500">Cargos cadastrados</p>
              <p className="font-semibold text-gray-900 mt-1">
                {cct?.total_cargos ?? cargosFiltrados.length} cargos
              </p>
            </div>
            <div className="bg-green-50 rounded-lg p-4">
              <TrendingUp className="w-5 h-5 text-green-600 mb-2" />
              <p className="text-xs text-gray-500">Conformidade salarial</p>
              <p className="font-semibold text-green-600 mt-1 inline-flex items-center gap-1">
                {cct?.conformidade_pct ?? 100}% <CheckCircle2 className="w-4 h-4" />
              </p>
            </div>
          </div>

          {(cct?.vinculados_cct != null || cct?.sem_vinculo != null) && (
            <div className="mt-4 pt-4 border-t border-gray-100 grid grid-cols-2 gap-4">
              <div className="flex items-center gap-3">
                <Users className="w-4 h-4 text-gray-400" />
                <div>
                  <p className="text-xs text-gray-500">Vinculados à CCT</p>
                  <p className="font-semibold text-gray-900">
                    {cct.vinculados_cct ?? '—'}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Users className="w-4 h-4 text-gray-400" />
                <div>
                  <p className="text-xs text-gray-500">Sem vínculo</p>
                  <p className="font-semibold text-gray-900">
                    {cct.sem_vinculo ?? 0}
                  </p>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Tabela de cargos */}
      <Card className="border border-gray-100">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg text-[#1E3A5F]">
              Cargos da CCT ({cargosFiltrados.length})
            </CardTitle>
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                placeholder="Buscar cargo..."
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                className="pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm w-52 focus:outline-none focus:border-[#F97316]"
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left py-3 px-4 text-gray-500 font-medium">
                    Cargo
                  </th>
                  <th className="text-right py-3 px-4 text-gray-500 font-medium">
                    Piso Salarial
                  </th>
                  <th className="text-right py-3 px-4 text-gray-500 font-medium">
                    Insalubridade
                  </th>
                  <th className="text-right py-3 px-4 text-gray-500 font-medium">
                    Periculosidade
                  </th>
                  <th className="text-right py-3 px-4 text-gray-500 font-medium">
                    Jornada
                  </th>
                </tr>
              </thead>
              <tbody>
                {cargosFiltrados.map((c, i) => (
                  <tr
                    key={c.id ?? i}
                    className="border-b border-gray-50 hover:bg-gray-50"
                  >
                    <td className="py-3 px-4 font-medium text-gray-900">
                      {c.cargo_nome ?? c.nome ?? c.name ?? '—'}
                    </td>
                    <td className="py-3 px-4 text-right font-semibold text-[#1E3A5F]">
                      {fmt(c.piso_salarial ?? c.salario_base)}
                    </td>
                    <td className="py-3 px-4 text-right text-gray-600">
                      {c.adicional_insalubridade_percentual != null
                        ? `${c.adicional_insalubridade_percentual}%`
                        : '—'}
                    </td>
                    <td className="py-3 px-4 text-right text-gray-600">
                      {c.adicional_periculosidade_percentual != null
                        ? `${c.adicional_periculosidade_percentual}%`
                        : '—'}
                    </td>
                    <td className="py-3 px-4 text-right text-gray-600">
                      {c.jornada_semanal_horas != null
                        ? `${c.jornada_semanal_horas}h/sem`
                        : '—'}
                    </td>
                  </tr>
                ))}
                {cargosFiltrados.length === 0 && (
                  <tr>
                    <td
                      colSpan={5}
                      className="py-8 text-center text-gray-400"
                    >
                      Nenhum cargo encontrado
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
