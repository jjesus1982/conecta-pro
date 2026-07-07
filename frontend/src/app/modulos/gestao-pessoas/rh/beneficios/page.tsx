'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { ArrowLeft, Gift, AlertCircle, Loader2 } from 'lucide-react';
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

interface Beneficio {
  id: string;
  type?: string;
  tipo?: string;
  provider?: string;
  plan_name?: string;
  employee_contribution?: number;
  company_contribution?: number;
  start_date?: string;
  end_date?: string;
  status?: string;
  employee_id?: string;
  employee_name?: string;
}

const BADGE_TIPO: Record<string, string> = {
  VT: 'bg-blue-100 text-blue-700 border-blue-200',
  VA: 'bg-green-100 text-green-700 border-green-200',
  VR: 'bg-purple-100 text-purple-700 border-purple-200',
  'Plano Saude': 'bg-pink-100 text-pink-700 border-pink-200',
  'Plano Saúde': 'bg-pink-100 text-pink-700 border-pink-200',
  'Plano Odontológico': 'bg-teal-100 text-teal-700 border-teal-200',
  'Seguro Vida': 'bg-indigo-100 text-indigo-700 border-indigo-200',
  'Empréstimo Consignado': 'bg-yellow-100 text-yellow-700 border-yellow-200',
};

export default function PageBeneficios() {
  const [beneficios, setBeneficios] = useState<Beneficio[]>([]);
  const [loading, setLoading] = useState(true);
  const [filtroTipo, setFiltroTipo] = useState('');
  const [pagina, setPagina] = useState(1);

  useEffect(() => {
    fetch(`${API_BASE}/benefits?page_size=100`, { headers: getAuthHeaders() })
      .then((r) => r.json())
      .then((d) => {
        const lista = Array.isArray(d)
          ? d
          : (d.items ?? d.benefits ?? d.data ?? []);
        setBeneficios(lista);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const fmt = (v?: number) =>
    v != null
      ? v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
      : '—';

  const normTipo = (b: Beneficio) => b.type ?? b.tipo ?? 'outro';

  const tipos = [...new Set(beneficios.map(normTipo))].sort();

  const filtrados = filtroTipo
    ? beneficios.filter((b) => normTipo(b) === filtroTipo)
    : beneficios;

  const porTipo = tipos.map((t) => {
    const grupo = beneficios.filter((b) => normTipo(b) === t);
    return {
      tipo: t,
      qtd: grupo.length,
      custo: grupo.reduce((s, b) => s + (b.company_contribution ?? 0), 0),
      semValor: grupo.filter(
        (b) => b.employee_contribution == null || b.employee_contribution === 0
      ).length,
    };
  });

  const POR_PAG = 30;
  const totalPag = Math.ceil(filtrados.length / POR_PAG);
  const pagAtual = filtrados.slice((pagina - 1) * POR_PAG, pagina * POR_PAG);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-[#F97316]" />
        <span className="ml-3 text-gray-500">Carregando benefícios...</span>
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
          Benefícios
        </h1>
        <span className="ml-auto px-3 py-1 rounded-full text-sm font-medium bg-orange-100 text-orange-700 border border-orange-200">
          {beneficios.length} registros
        </span>
      </div>

      {/* Cards por tipo (filtros clicáveis) */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-6">
        {porTipo.map((t) => (
          <Card
            key={t.tipo}
            onClick={() => {
              setFiltroTipo(filtroTipo === t.tipo ? '' : t.tipo);
              setPagina(1);
            }}
            className={`border cursor-pointer transition-all hover:shadow-md ${
              filtroTipo === t.tipo
                ? 'border-[#F97316] ring-2 ring-orange-100'
                : 'border-gray-100 hover:border-[#F97316]'
            }`}
          >
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-2">
                <span
                  className={`px-2 py-0.5 rounded-full text-xs font-medium border ${
                    BADGE_TIPO[t.tipo] ?? 'bg-gray-100 text-gray-700 border-gray-200'
                  }`}
                >
                  {t.tipo}
                </span>
                {t.semValor > 0 && (
                  <AlertCircle className="w-4 h-4 text-yellow-500" aria-label="Sem desconto cadastrado" />
                )}
              </div>
              <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{t.qtd}</p>
              <p className="text-xs text-gray-400">beneficiários</p>
              {t.custo > 0 && (
                <p className="text-sm font-semibold text-gray-600 mt-1">
                  {fmt(t.custo)}/mês
                </p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Tabela */}
      <Card className="border border-gray-100">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg text-[#1E3A5F]">
              {filtroTipo ? `${filtroTipo} — ${filtrados.length} registros` : `Todos — ${filtrados.length} registros`}
            </CardTitle>
            {filtroTipo && (
              <button
                onClick={() => { setFiltroTipo(''); setPagina(1); }}
                className="text-sm text-[#F97316] hover:underline"
              >
                Limpar filtro
              </button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left py-3 px-4 text-gray-500 font-medium">Tipo</th>
                  <th className="text-left py-3 px-4 text-gray-500 font-medium">Fornecedor / Plano</th>
                  <th className="text-right py-3 px-4 text-gray-500 font-medium">Custo empresa</th>
                  <th className="text-right py-3 px-4 text-gray-500 font-medium">Desconto func.</th>
                  <th className="text-center py-3 px-4 text-gray-500 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {pagAtual.map((b, i) => (
                  <tr
                    key={b.id ?? i}
                    className="border-b border-gray-50 hover:bg-gray-50"
                  >
                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs font-medium border ${
                          BADGE_TIPO[normTipo(b)] ??
                          'bg-gray-100 text-gray-700 border-gray-200'
                        }`}
                      >
                        {normTipo(b)}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-gray-700">
                      {b.provider ?? b.plan_name ?? '—'}
                    </td>
                    <td className="py-3 px-4 text-right font-medium text-gray-900">
                      {fmt(b.company_contribution)}
                    </td>
                    <td className="py-3 px-4 text-right">
                      {b.employee_contribution != null &&
                      b.employee_contribution > 0 ? (
                        <span className="text-gray-700">
                          {fmt(b.employee_contribution)}
                        </span>
                      ) : (
                        <span className="text-yellow-500 text-xs flex items-center justify-end gap-1">
                          <AlertCircle className="w-3 h-3" /> pendente
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                          b.status === 'active' || b.status === 'ativo'
                            ? 'bg-green-100 text-green-700'
                            : 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        {b.status ?? 'ativo'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Paginação */}
          {totalPag > 1 && (
            <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-100">
              <p className="text-sm text-gray-400">
                Página {pagina} de {totalPag} · {filtrados.length} registros
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPagina((p) => Math.max(1, p - 1))}
                  disabled={pagina === 1}
                  className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg disabled:opacity-40 hover:border-[#F97316] transition-colors"
                >
                  ← Anterior
                </button>
                <button
                  onClick={() => setPagina((p) => Math.min(totalPag, p + 1))}
                  disabled={pagina === totalPag}
                  className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg disabled:opacity-40 hover:border-[#F97316] transition-colors"
                >
                  Próxima →
                </button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
