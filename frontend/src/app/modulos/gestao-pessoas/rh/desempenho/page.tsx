'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  ArrowLeft, Star, TrendingUp, Users, Award, Loader2,
  Network, Clock, ShieldAlert, GraduationCap, Info,
} from 'lucide-react';
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

interface Componente {
  disponivel: boolean;
  score: number | null;
  valor_bruto: unknown;
  fonte: string;
  peso: number;
  obs: string | null;
}

interface FuncionarioIntegrado {
  employee_id: string;
  nome: string;
  cargo?: string;
  posto?: string;
  score_composto: number | null;
  score_obs?: string | null;
  peso_coberto: number;
  componentes: Record<string, Componente>;
  componentes_indisponiveis: string[];
  indicadores: {
    tempo_casa_meses?: number | null;
    batidas_30d?: number;
    dias_com_batida_30d?: number;
    afastamentos?: { total?: number; ativos?: number; indisponivel?: boolean };
    atrasos?: { disponivel: boolean; motivo?: string };
  };
}

interface VisaoIntegrada {
  gerado_em?: string;
  metodo_score?: string;
  avisos?: string[];
  fontes?: Record<string, string>;
  total_funcionarios?: number;
  funcionarios?: FuncionarioIntegrado[];
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

function ScoreCell({ comp }: { comp?: Componente }) {
  if (!comp || !comp.disponivel || comp.score == null) {
    return (
      <span className="text-gray-400 text-xs" title={comp?.obs ?? 'indisponível'}>
        aguardando
      </span>
    );
  }
  const cor =
    comp.score >= 7.5 ? 'text-green-600' : comp.score >= 6 ? 'text-yellow-600' : 'text-red-600';
  return (
    <span className={`font-data font-semibold tabular-nums ${cor}`} title={comp.fonte}>
      {comp.score.toFixed(1)}
    </span>
  );
}

function CompostoBadge({ f }: { f: FuncionarioIntegrado }) {
  if (f.score_composto == null) {
    return (
      <span className="text-gray-400 text-xs" title={f.score_obs ?? 'sem dado real suficiente'}>
        sem dado suficiente
      </span>
    );
  }
  const cor =
    f.score_composto >= 7.5
      ? 'bg-green-100 text-green-700 border-green-200'
      : f.score_composto >= 6
        ? 'bg-yellow-100 text-yellow-700 border-yellow-200'
        : 'bg-red-100 text-red-700 border-red-200';
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-data font-semibold tabular-nums ${cor}`}
      title={`Cobre ${Math.round(f.peso_coberto * 100)}% dos pesos declarados; componentes sem dado real ficam fora do cálculo`}
    >
      {f.score_composto.toFixed(1)}
      <span className="font-normal opacity-70">({Math.round(f.peso_coberto * 100)}%)</span>
    </span>
  );
}

export default function PageDesempenho() {
  const [avaliacoes, setAvaliacoes] = useState<Avaliacao[]>([]);
  const [visao, setVisao] = useState<VisaoIntegrada | null>(null);
  const [loading, setLoading] = useState(true);
  const [filtroStatus, setFiltroStatus] = useState('');

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/reviews`, { headers: getAuthHeaders() })
        .then((r) => r.json())
        .catch(() => null),
      fetch(`${API_BASE}/visao-integrada`, { headers: getAuthHeaders() })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
    ])
      .then(([d, vi]) => {
        if (d) {
          const lista = Array.isArray(d)
            ? d
            : (d.items ?? d.reviews ?? d.avaliacoes ?? d.data ?? []);
          setAvaliacoes(lista);
        }
        if (vi) setVisao(vi);
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

      {/* Visão Integrada de Desempenho */}
      {visao?.funcionarios && visao.funcionarios.length > 0 && (
        <Card className="border border-gray-100 mb-6">
          <CardHeader>
            <div className="flex items-center justify-between flex-wrap gap-2">
              <CardTitle className="text-lg text-[#1E3A5F] flex items-center gap-2">
                <Network className="w-5 h-5 text-[#F97316]" />
                Visão Integrada de Desempenho — {visao.total_funcionarios} funcionários ativos
              </CardTitle>
              <span className="text-xs text-gray-400 flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" /> ponto 30d · ocorrências 90d
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-1 flex items-start gap-1.5">
              <Info className="w-3.5 h-3.5 mt-0.5 shrink-0 text-gray-400" />
              Score composto = média ponderada apenas dos componentes com dado real
              (avaliação 30% · 360 15% · líder 15% · ponto 15% · ocorrências 15% · treinamentos 10%).
              Componentes sem dado aparecem como &quot;aguardando&quot; e ficam fora do cálculo — nada é fabricado.
            </p>
            {(visao.avisos ?? []).length > 0 && (
              <div className="mt-2 space-y-1">
                {visao.avisos!.map((a, i) => (
                  <p key={i} className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1 flex items-start gap-1.5">
                    <ShieldAlert className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {a}
                  </p>
                ))}
              </div>
            )}
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100">
                    <th className="text-left py-3 px-3 text-gray-500 font-medium">Funcionário</th>
                    <th className="text-left py-3 px-3 text-gray-500 font-medium">Tempo de casa</th>
                    <th className="text-center py-3 px-3 text-gray-500 font-medium">Avaliação</th>
                    <th className="text-center py-3 px-3 text-gray-500 font-medium">360</th>
                    <th className="text-center py-3 px-3 text-gray-500 font-medium">Líder</th>
                    <th className="text-center py-3 px-3 text-gray-500 font-medium">Ponto 30d</th>
                    <th className="text-center py-3 px-3 text-gray-500 font-medium">Ocorrências</th>
                    <th className="text-center py-3 px-3 text-gray-500 font-medium">
                      <span className="inline-flex items-center gap-1"><GraduationCap className="w-3.5 h-3.5" />Trein.</span>
                    </th>
                    <th className="text-center py-3 px-3 text-gray-500 font-medium">Score composto</th>
                  </tr>
                </thead>
                <tbody>
                  {visao.funcionarios.map((f) => {
                    const meses = f.indicadores?.tempo_casa_meses;
                    const tempoCasa =
                      meses == null
                        ? '—'
                        : meses >= 12
                          ? `${Math.floor(meses / 12)}a ${meses % 12}m`
                          : `${meses}m`;
                    const afast = f.indicadores?.afastamentos;
                    return (
                      <tr key={f.employee_id} className="border-b border-gray-50 hover:bg-gray-50">
                        <td className="py-2.5 px-3">
                          <p className="font-medium text-gray-900">{f.nome}</p>
                          <p className="text-xs text-gray-400">
                            {f.cargo ?? '—'}
                            {f.posto ? ` · ${f.posto}` : ''}
                            {afast && (afast.ativos ?? 0) > 0 ? ' · afastado' : ''}
                          </p>
                        </td>
                        <td className="py-2.5 px-3 text-gray-600 font-data tabular-nums text-xs">{tempoCasa}</td>
                        <td className="py-2.5 px-3 text-center"><ScoreCell comp={f.componentes?.avaliacao_desempenho} /></td>
                        <td className="py-2.5 px-3 text-center"><ScoreCell comp={f.componentes?.avaliacao_360} /></td>
                        <td className="py-2.5 px-3 text-center"><ScoreCell comp={f.componentes?.avaliacao_lider} /></td>
                        <td className="py-2.5 px-3 text-center">
                          <ScoreCell comp={f.componentes?.conformidade_ponto} />
                          <p className="text-[10px] text-gray-400 font-data tabular-nums">
                            {f.indicadores?.batidas_30d ?? 0} batidas · {f.indicadores?.dias_com_batida_30d ?? 0} dias
                          </p>
                        </td>
                        <td className="py-2.5 px-3 text-center"><ScoreCell comp={f.componentes?.ocorrencias} /></td>
                        <td className="py-2.5 px-3 text-center"><ScoreCell comp={f.componentes?.treinamentos} /></td>
                        <td className="py-2.5 px-3 text-center"><CompostoBadge f={f} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

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
