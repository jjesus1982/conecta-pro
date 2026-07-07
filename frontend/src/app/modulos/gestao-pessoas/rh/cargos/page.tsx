'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { ArrowLeft, Search, Briefcase, Loader2 } from 'lucide-react';
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

interface Cargo {
  id: string;
  cargo_nome?: string;
  nome?: string;
  name?: string;
  piso_salarial?: number;
  salario_base?: number;
  adicional_insalubridade_percentual?: number;
  adicional_periculosidade_percentual?: number;
  adicional_noturno_percentual?: number;
  jornada_semanal_horas?: number;
  horas_extras_percentual?: number;
}

export default function PageCargos() {
  const [cargos, setCargos] = useState<Cargo[]>([]);
  const [loading, setLoading] = useState(true);
  const [busca, setBusca] = useState('');

  useEffect(() => {
    fetch(`${API_BASE}/cct/cargos`, { headers: getAuthHeaders() })
      .then((r) => r.json())
      .then((d) => {
        const lista = Array.isArray(d) ? d : (d.cargos ?? d.data ?? []);
        setCargos(lista);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const fmt = (v?: number) =>
    v != null
      ? v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
      : 'R$ —';

  const filtrados = cargos.filter((c) =>
    (c.cargo_nome ?? c.nome ?? c.name ?? '')
      .toLowerCase()
      .includes(busca.toLowerCase())
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-[#F97316]" />
        <span className="ml-3 text-gray-500">Carregando cargos...</span>
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
        <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">
          Cargos CCT — SINDECOMPRESTS 2026
        </h1>
        <span className="ml-auto px-3 py-1 rounded-full text-sm font-medium bg-orange-100 text-orange-700 border border-orange-200">
          {cargos.length} cargos
        </span>
      </div>

      {/* Busca */}
      <Card className="border border-gray-100 mb-4">
        <CardContent className="p-4">
          <div className="relative max-w-md">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Buscar por nome do cargo..."
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-[#F97316]"
            />
          </div>
        </CardContent>
      </Card>

      {/* Grid de cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtrados.map((c, i) => (
          <Card
            key={c.id ?? i}
            className="border border-gray-100 hover:border-[#F97316] hover:shadow-md transition-all"
          >
            <CardContent className="p-5">
              <div className="flex items-start gap-3 mb-3">
                <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center shrink-0">
                  <Briefcase className="w-5 h-5 text-[#1E3A5F]" />
                </div>
                <div>
                  <p className="font-semibold text-gray-900 leading-tight">
                    {c.cargo_nome ?? c.nome ?? c.name ?? '—'}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">CCT SINDECOMPRESTS</p>
                </div>
              </div>

              <div className="mt-3 pt-3 border-t border-gray-50">
                <p className="text-xs text-gray-500 mb-1">Piso salarial</p>
                <p className="text-xl font-bold text-[#1E3A5F]">
                  {fmt(c.piso_salarial ?? c.salario_base)}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-2 mt-3">
                {c.adicional_insalubridade_percentual != null && (
                  <div className="bg-yellow-50 rounded px-2 py-1.5">
                    <p className="text-xs text-gray-500">Insalubridade</p>
                    <p className="text-sm font-semibold text-yellow-700">
                      {c.adicional_insalubridade_percentual}%
                    </p>
                  </div>
                )}
                {c.adicional_periculosidade_percentual != null && (
                  <div className="bg-red-50 rounded px-2 py-1.5">
                    <p className="text-xs text-gray-500">Periculosidade</p>
                    <p className="text-sm font-semibold text-red-600">
                      {c.adicional_periculosidade_percentual}%
                    </p>
                  </div>
                )}
                {c.jornada_semanal_horas != null && (
                  <div className="bg-gray-50 rounded px-2 py-1.5">
                    <p className="text-xs text-gray-500">Jornada</p>
                    <p className="text-sm font-semibold text-gray-700">
                      {c.jornada_semanal_horas}h/sem
                    </p>
                  </div>
                )}
                {(c.adicional_noturno_percentual ?? c.horas_extras_percentual) != null && (
                  <div className="bg-blue-50 rounded px-2 py-1.5">
                    <p className="text-xs text-gray-500">Noturno</p>
                    <p className="text-sm font-semibold text-blue-700">
                      {c.adicional_noturno_percentual ?? c.horas_extras_percentual}%
                    </p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
        {filtrados.length === 0 && (
          <div className="col-span-3 text-center py-12 text-gray-400">
            Nenhum cargo encontrado para &quot;{busca}&quot;
          </div>
        )}
      </div>
    </div>
  );
}
