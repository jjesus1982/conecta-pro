'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { ArrowLeft, Star, TrendingUp, Users, Award, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const API_BASE = '/api/v1/people-management/human-resources/performance';

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

interface Avaliacao {
  id: string;
  employee_id?: string;
  employee_name?: string;
  funcionario_nome?: string;
  review_date?: string;
  review_period_start?: string;
  review_period_end?: string;
  completed_at?: string;
  data_avaliacao?: string;
  reviewer_id?: string;
  reviewer_name?: string;
  avaliador_nome?: string;
  score?: number;
  overall_score?: number;
  nota?: number;
  type?: string;
  status?: string;
  period?: string;
  periodo?: string;
  scores_breakdown?: Record<string, number>;
}

const STATUS_BADGE: Record<string, string> = {
  completed: 'bg-green-100 text-green-700',
  concluida: 'bg-green-100 text-green-700',
  pending: 'bg-yellow-100 text-yellow-700',
  pendente: 'bg-yellow-100 text-yellow-700',
  in_progress: 'bg-blue-100 text-blue-700',
  em_andamento: 'bg-blue-100 text-blue-700',
  cancelled: 'bg-red-100 text-red-600',
  cancelada: 'bg-red-100 text-red-600',
};

function ScoreStars({ score }: { score: number }) {
  const stars = Math.round((score / 10) * 5);
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((s) => (
        <Star
          key={s}
          className={`w-3.5 h-3.5 ${s <= stars ? 'text-yellow-400 fill-yellow-400' : 'text-gray-200'}`}
        />
      ))}
      <span className="ml-1.5 text-sm font-semibold text-gray-700">{score.toFixed(1)}</span>
    </div>
  );
}

export default function PageDesempenho() {
  const [avaliacoes, setAvaliacoes] = useState<Avaliacao[]>([]);
  const [loading, setLoading] = useState(true);
  const [filtroStatus, setFiltroStatus] = useState('');

  useEffect(() => {
    fetch(`${API_BASE}/reviews`, { headers: getAuthHeaders() })
      .then((r) => r.json())
      .then((d) => {
        const lista = Array.isArray(d)
          ? d
          : (d.items ?? d.reviews ?? d.avaliacoes ?? d.data ?? []);
        setAvaliacoes(lista);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const normNome = (a: Avaliacao) =>
    a.employee_name ?? a.funcionario_nome ?? (a.employee_id ? `ID: ${a.employee_id.slice(0, 8)}` : '—');
  const normPeriodo = (a: Avaliacao) => {
    if (a.review_period_start && a.review_period_end) {
      try {
        const ini = new Date(a.review_period_start).toLocaleDateString('pt-BR');
        const fim = new Date(a.review_period_end).toLocaleDateString('pt-BR');
        return `${ini} – ${fim}`;
      } catch {
        return `${a.review_period_start} – ${a.review_period_end}`;
      }
    }
    const d = a.completed_at ?? a.review_date ?? a.data_avaliacao;
    if (!d) return '—';
    try {
      return new Date(d).toLocaleDateString('pt-BR');
    } catch {
      return d;
    }
  };
  const normAvaliador = (a: Avaliacao) =>
    a.reviewer_name ?? a.avaliador_nome ?? (a.reviewer_id ? `ID: ${a.reviewer_id.slice(0, 8)}` : '—');
  const normScore = (a: Avaliacao) => a.overall_score ?? a.score ?? a.nota ?? 0;
  const normStatus = (a: Avaliacao) => a.status ?? 'pendente';

  const filtradas = filtroStatus
    ? avaliacoes.filter((a) => normStatus(a) === filtroStatus)
    : avaliacoes;

  const concluidas = avaliacoes.filter(
    (a) => normStatus(a) === 'completed' || normStatus(a) === 'concluida'
  );
  const mediaScore =
    concluidas.length > 0
      ? concluidas.reduce((s, a) => s + normScore(a), 0) / concluidas.length
      : 0;

  const statusOptions = [...new Set(avaliacoes.map(normStatus))].sort();

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-[#F97316]" />
        <span className="ml-3 text-gray-500">Carregando avaliações...</span>
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
        <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Avaliações de Desempenho</h1>
        <span className="ml-auto px-3 py-1 rounded-full text-sm font-medium bg-orange-100 text-orange-700 border border-orange-200">
          {avaliacoes.length} avaliações
        </span>
      </div>

      {/* Métricas */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <Card className="border border-gray-100">
          <CardContent className="p-5">
            <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center mb-3">
              <Users className="w-5 h-5 text-blue-600" />
            </div>
            <p className="text-sm text-gray-500">Total avaliações</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">{avaliacoes.length}</p>
          </CardContent>
        </Card>
        <Card className="border border-gray-100">
          <CardContent className="p-5">
            <div className="w-10 h-10 bg-green-50 rounded-lg flex items-center justify-center mb-3">
              <Award className="w-5 h-5 text-green-600" />
            </div>
            <p className="text-sm text-gray-500">Concluídas</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-green-600 mt-1">{concluidas.length}</p>
          </CardContent>
        </Card>
        <Card className="border border-gray-100">
          <CardContent className="p-5">
            <div className="w-10 h-10 bg-yellow-50 rounded-lg flex items-center justify-center mb-3">
              <Star className="w-5 h-5 text-yellow-500" />
            </div>
            <p className="text-sm text-gray-500">Nota média</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-yellow-600 mt-1">
              {mediaScore > 0 ? mediaScore.toFixed(1) : '—'}
            </p>
          </CardContent>
        </Card>
        <Card className="border border-gray-100">
          <CardContent className="p-5">
            <div className="w-10 h-10 bg-orange-50 rounded-lg flex items-center justify-center mb-3">
              <TrendingUp className="w-5 h-5 text-[#F97316]" />
            </div>
            <p className="text-sm text-gray-500">Taxa conclusão</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-[#F97316] mt-1">
              {avaliacoes.length > 0
                ? Math.round((concluidas.length / avaliacoes.length) * 100)
                : 0}
              %
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Tabela */}
      <Card className="border border-gray-100">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg text-[#1E3A5F]">
              {filtroStatus
                ? `${filtroStatus} — ${filtradas.length} registros`
                : `Todas as avaliações — ${filtradas.length} registros`}
            </CardTitle>
            {statusOptions.length > 0 && (
              <div className="flex gap-2">
                {statusOptions.map((s) => (
                  <button
                    key={s}
                    onClick={() => setFiltroStatus(filtroStatus === s ? '' : s)}
                    className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                      filtroStatus === s
                        ? 'bg-[#1E3A5F] text-white border-[#1E3A5F]'
                        : 'border-gray-200 text-gray-600 hover:border-[#F97316]'
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left py-3 px-4 text-gray-500 font-medium">Funcionário</th>
                  <th className="text-left py-3 px-4 text-gray-500 font-medium">Período</th>
                  <th className="text-left py-3 px-4 text-gray-500 font-medium">Avaliador</th>
                  <th className="text-left py-3 px-4 text-gray-500 font-medium">Nota</th>
                  <th className="text-center py-3 px-4 text-gray-500 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {filtradas.map((a, i) => {
                  const score = normScore(a);
                  const status = normStatus(a);
                  return (
                    <tr
                      key={a.id ?? i}
                      className="border-b border-gray-50 hover:bg-gray-50"
                    >
                      <td className="py-3 px-4 font-medium text-gray-900">
                        {normNome(a)}
                      </td>
                      <td className="py-3 px-4 text-gray-600 text-xs">{normPeriodo(a)}</td>
                      <td className="py-3 px-4 text-gray-600">{normAvaliador(a)}</td>
                      <td className="py-3 px-4">
                        {score > 0 ? (
                          <ScoreStars score={score} />
                        ) : (
                          <span className="text-gray-400 text-xs">Pendente</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-center">
                        <span
                          className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                            STATUS_BADGE[status] ?? 'bg-gray-100 text-gray-600'
                          }`}
                        >
                          {status}
                        </span>
                      </td>
                    </tr>
                  );
                })}
                {filtradas.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-12 text-center text-gray-400">
                      Nenhuma avaliação encontrada
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
