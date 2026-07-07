'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { ArrowLeft, Wind, BarChart3, Users, CheckCircle, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const API_BASE = '/api/v1/people-management/human-resources/climate';

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

interface Pesquisa {
  id: string;
  title?: string;
  titulo?: string;
  name?: string;
  description?: string;
  descricao?: string;
  status?: string;
  start_date?: string;
  end_date?: string;
  data_inicio?: string;
  data_fim?: string;
  taxa_resposta?: number;
  response_rate?: number;
  total_respondentes?: number;
  total_respondents?: number;
  total_convidados?: number;
  total_invited?: number;
  score_geral?: number;
  overall_score?: number;
  period?: string;
  periodo?: string;
}

const STATUS_BADGE: Record<string, string> = {
  active: 'bg-green-100 text-green-700 border-green-200',
  ativo: 'bg-green-100 text-green-700 border-green-200',
  completed: 'bg-blue-100 text-blue-700 border-blue-200',
  concluida: 'bg-blue-100 text-blue-700 border-blue-200',
  pending: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  pendente: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  draft: 'bg-gray-100 text-gray-600 border-gray-200',
  rascunho: 'bg-gray-100 text-gray-600 border-gray-200',
};

function ScoreBar({ value, max = 10 }: { value: number; max?: number }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 bg-gray-100 rounded-full h-2">
        <div
          className={`h-2 rounded-full transition-all ${
            pct >= 70 ? 'bg-green-500' : pct >= 50 ? 'bg-[#F97316]' : 'bg-red-400'
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-sm font-semibold text-gray-700 w-8 text-right">
        {value.toFixed(1)}
      </span>
    </div>
  );
}

export default function PageClima() {
  const [pesquisas, setPesquisas] = useState<Pesquisa[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/surveys`, { headers: getAuthHeaders() })
      .then((r) => r.json())
      .then((d) => {
        const lista = Array.isArray(d)
          ? d
          : (d.items ?? d.surveys ?? d.pesquisas ?? d.data ?? []);
        setPesquisas(lista);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const normTitle = (p: Pesquisa) => p.title ?? p.titulo ?? p.name ?? '—';
  const normTaxa = (p: Pesquisa) => p.taxa_resposta ?? p.response_rate ?? 0;
  const normScore = (p: Pesquisa) => p.score_geral ?? p.overall_score;
  const normStatus = (p: Pesquisa) => p.status ?? 'pendente';
  const normRespondentes = (p: Pesquisa) => p.total_respondentes ?? p.total_respondents ?? 0;
  const normConvidados = (p: Pesquisa) => p.total_convidados ?? p.total_invited;
  const normData = (d?: string) => {
    if (!d) return null;
    try {
      return new Date(d).toLocaleDateString('pt-BR');
    } catch {
      return d;
    }
  };

  const ativas = pesquisas.filter(
    (p) => normStatus(p) === 'active' || normStatus(p) === 'ativo'
  ).length;
  const mediaScore =
    pesquisas.filter((p) => normScore(p) != null).length > 0
      ? pesquisas
          .filter((p) => normScore(p) != null)
          .reduce((s, p) => s + (normScore(p) ?? 0), 0) /
        pesquisas.filter((p) => normScore(p) != null).length
      : 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-[#F97316]" />
        <span className="ml-3 text-gray-500">Carregando pesquisas de clima...</span>
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
        <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Clima Organizacional</h1>
        <span className="ml-auto px-3 py-1 rounded-full text-sm font-medium bg-orange-100 text-orange-700 border border-orange-200">
          {pesquisas.length} pesquisas
        </span>
      </div>

      {/* Métricas */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        <Card className="border border-gray-100">
          <CardContent className="p-5">
            <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center mb-3">
              <Wind className="w-5 h-5 text-blue-600" />
            </div>
            <p className="text-sm text-gray-500">Total de pesquisas</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">{pesquisas.length}</p>
          </CardContent>
        </Card>
        <Card className="border border-gray-100">
          <CardContent className="p-5">
            <div className="w-10 h-10 bg-green-50 rounded-lg flex items-center justify-center mb-3">
              <CheckCircle className="w-5 h-5 text-green-600" />
            </div>
            <p className="text-sm text-gray-500">Pesquisas ativas</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-green-600 mt-1">{ativas}</p>
          </CardContent>
        </Card>
        <Card className="border border-gray-100">
          <CardContent className="p-5">
            <div className="w-10 h-10 bg-orange-50 rounded-lg flex items-center justify-center mb-3">
              <BarChart3 className="w-5 h-5 text-[#F97316]" />
            </div>
            <p className="text-sm text-gray-500">Score médio</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-[#F97316] mt-1">
              {mediaScore > 0 ? mediaScore.toFixed(1) : '—'}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Cards das pesquisas */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {pesquisas.map((p, i) => {
          const taxa = normTaxa(p);
          const score = normScore(p);
          const status = normStatus(p);
          const respondentes = normRespondentes(p);
          const convidados = normConvidados(p);
          const dataInicio = normData(p.start_date ?? p.data_inicio);
          const dataFim = normData(p.end_date ?? p.data_fim);

          return (
            <Card
              key={p.id ?? i}
              className="border border-gray-100 hover:border-[#F97316] hover:shadow-md transition-all"
            >
              <CardContent className="p-5">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center shrink-0">
                      <Wind className="w-5 h-5 text-blue-600" />
                    </div>
                    <div className="min-w-0">
                      <p className="font-semibold text-gray-900 leading-tight line-clamp-2">
                        {normTitle(p)}
                      </p>
                      {(p.period ?? p.periodo) && (
                        <p className="text-xs text-gray-400 mt-0.5">{p.period ?? p.periodo}</p>
                      )}
                    </div>
                  </div>
                  <span
                    className={`ml-2 px-2 py-0.5 rounded-full text-xs font-medium border shrink-0 ${
                      STATUS_BADGE[status] ?? 'bg-gray-100 text-gray-600 border-gray-200'
                    }`}
                  >
                    {status}
                  </span>
                </div>

                {p.description || p.descricao ? (
                  <p className="text-sm text-gray-500 mb-3 line-clamp-2">
                    {p.description ?? p.descricao}
                  </p>
                ) : null}

                {/* Taxa de resposta */}
                {(taxa > 0 || respondentes > 0) && (
                  <div className="mb-3">
                    <div className="flex justify-between text-xs text-gray-500 mb-1.5">
                      <span>Taxa de resposta</span>
                      <span>
                        {respondentes > 0 && convidados != null
                          ? `${respondentes}/${convidados}`
                          : `${taxa}%`}
                      </span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-2">
                      <div
                        className={`h-2 rounded-full ${
                          taxa >= 70
                            ? 'bg-green-500'
                            : taxa >= 50
                              ? 'bg-[#F97316]'
                              : 'bg-red-400'
                        }`}
                        style={{ width: `${taxa}%` }}
                      />
                    </div>
                  </div>
                )}

                {/* Score geral */}
                {score != null && score > 0 && (
                  <div className="mb-3">
                    <p className="text-xs text-gray-500 mb-1.5">Score geral</p>
                    <ScoreBar value={score} />
                  </div>
                )}

                {/* Datas */}
                {(dataInicio || dataFim) && (
                  <div className="flex gap-4 pt-3 border-t border-gray-50 mt-3">
                    {dataInicio && (
                      <div>
                        <p className="text-xs text-gray-400">Início</p>
                        <p className="text-xs font-medium text-gray-700">{dataInicio}</p>
                      </div>
                    )}
                    {dataFim && (
                      <div>
                        <p className="text-xs text-gray-400">Fim</p>
                        <p className="text-xs font-medium text-gray-700">{dataFim}</p>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}

        {pesquisas.length === 0 && (
          <div className="col-span-3 text-center py-16 text-gray-400">
            <Wind className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p>Nenhuma pesquisa de clima cadastrada</p>
          </div>
        )}
      </div>
    </div>
  );
}
