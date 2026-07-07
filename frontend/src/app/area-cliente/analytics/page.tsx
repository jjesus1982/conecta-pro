'use client';

import React, { useEffect, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AlertTriangle, BarChart2, CheckCircle, Clock, FileText, TrendingUp, XCircle } from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

function portalFetch(path: string) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('portal_token') : '';
  return fetch(`${API_BASE}/api/v1/portal${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface Overview {
  kits_total: number;
  kits_aprovados: number;
  kits_pendentes: number;
  chamados_abertos: number;
  chamados_resolvidos_30d: number;
  tempo_medio_resolucao_horas: number;
  documentos_total: number;
  health_score: number;
  proxima_geracao_kit: string | null;
}

interface KitHistory {
  month: string;
  status: string;
  documents: number;
  completion_pct: number;
}

interface TicketHistory {
  month: string;
  abertos: number;
  resolvidos: number;
  tempo_medio_h: number;
}

interface Conformidade {
  certidoes: { name: string; status: string; expires_at: string | null }[];
  compliance_score: number;
  documentos_em_dia: number;
  documentos_pendentes: number;
}

// ─── Sub-components ────────────────────────────────────────────────────────────

function MetricCard({
  label,
  value,
  sub,
  color,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  sub?: string;
  color: string;
  icon: React.ElementType;
}) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 flex items-center gap-4">
      <div className={`${color} p-3 rounded-xl`}>
        <Icon className="h-6 w-6 text-white" />
      </div>
      <div>
        <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{value}</p>
        <p className="text-sm font-medium text-gray-600">{label}</p>
        {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

function HealthGauge({ score }: { score: number }) {
  const color = score >= 80 ? '#10b981' : score >= 60 ? '#f59e0b' : '#ef4444';
  const data = [{ name: 'Score', value: score, fill: color }];

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
      <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">Health Score</h3>
      <div className="flex items-center gap-4">
        <ResponsiveContainer width={100} height={100}>
          <RadialBarChart
            cx="50%"
            cy="50%"
            innerRadius="60%"
            outerRadius="90%"
            barSize={12}
            data={data}
            startAngle={180}
            endAngle={0}
          >
            <RadialBar dataKey="value" background={{ fill: '#f3f4f6' }} />
          </RadialBarChart>
        </ResponsiveContainer>
        <div>
          <p className="text-4xl font-bold" style={{ color }}>{score}</p>
          <p className="text-sm text-gray-500">de 100</p>
          <p className="text-xs mt-1 font-medium" style={{ color }}>
            {score >= 80 ? 'Ótimo' : score >= 60 ? 'Atenção' : 'Crítico'}
          </p>
        </div>
      </div>
    </div>
  );
}

function CertidaoStatus({ status }: { status: string }) {
  if (status === 'ok') return <CheckCircle className="h-4 w-4 text-emerald-500" />;
  if (status === 'vencendo') return <AlertTriangle className="h-4 w-4 text-amber-500" />;
  return <XCircle className="h-4 w-4 text-red-500" />;
}

function Skeleton() {
  return <div className="animate-pulse bg-gray-200 rounded-lg h-32 w-full" />;
}

// ─── Main Page ─────────────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [kitsHistory, setKitsHistory] = useState<KitHistory[]>([]);
  const [ticketsHistory, setTicketsHistory] = useState<TicketHistory[]>([]);
  const [conformidade, setConformidade] = useState<Conformidade | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [ov, kh, th, cf] = await Promise.allSettled([
          portalFetch('/analytics/overview').then((r) => r.json()),
          portalFetch('/analytics/kits-history?months=6').then((r) => r.json()),
          portalFetch('/analytics/tickets-history?months=6').then((r) => r.json()),
          portalFetch('/analytics/conformidade').then((r) => r.json()),
        ]);

        if (ov.status === 'fulfilled') setOverview(ov.value);
        if (kh.status === 'fulfilled') setKitsHistory(Array.isArray(kh.value) ? kh.value : []);
        if (th.status === 'fulfilled') setTicketsHistory(Array.isArray(th.value) ? th.value : []);
        if (cf.status === 'fulfilled') setConformidade(cf.value);
      } catch (err) {
        console.error('Erro ao carregar analytics:', err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const STATUS_COLORS: Record<string, string> = {
    aprovado: '#10b981',
    enviado: '#4f46e5',
    completo: '#3b82f6',
    em_montagem: '#f59e0b',
    pendente: '#6b7280',
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="bg-indigo-600 p-2 rounded-lg">
          <BarChart2 className="h-6 w-6 text-white" />
        </div>
        <div>
          <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Relatórios e Analytics</h1>
          <p className="text-sm text-gray-500">Histórico e métricas do seu portal</p>
        </div>
      </div>

      {/* Metric Cards + Health Score */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(5)].map((_, i) => <Skeleton key={i} />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <HealthGauge score={overview?.health_score ?? 0} />
          <MetricCard
            label="Kits Aprovados"
            value={`${overview?.kits_aprovados ?? 0}/${overview?.kits_total ?? 0}`}
            sub="total do histórico"
            color="bg-emerald-500"
            icon={CheckCircle}
          />
          <MetricCard
            label="Chamados Abertos"
            value={overview?.chamados_abertos ?? 0}
            sub={`${overview?.chamados_resolvidos_30d ?? 0} resolvidos nos últimos 30d`}
            color="bg-indigo-500"
            icon={FileText}
          />
          <MetricCard
            label="Tempo Médio Resolução"
            value={`${Math.round(overview?.tempo_medio_resolucao_horas ?? 0)}h`}
            sub="por chamado"
            color="bg-amber-500"
            icon={Clock}
          />
        </div>
      )}

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Kits History */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-indigo-500" />
            Kits dos Últimos 6 Meses
          </h3>
          {loading ? (
            <Skeleton />
          ) : kitsHistory.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-8">Nenhum dado disponível</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={kitsHistory} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  formatter={(value: unknown, name: unknown): [string | number, string] =>
                    name === 'completion_pct'
                      ? [`${value as number}%`, 'Conclusão']
                      : [value as number, 'Documentos']
                  }
                />
                <Bar dataKey="documents" name="Documentos" radius={[4, 4, 0, 0]}>
                  {kitsHistory.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={STATUS_COLORS[entry.status] ?? '#6b7280'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Tickets History */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <FileText className="h-4 w-4 text-amber-500" />
            Chamados por Mês
          </h3>
          {loading ? (
            <Skeleton />
          ) : ticketsHistory.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-8">Nenhum dado disponível</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={ticketsHistory} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line
                  type="monotone"
                  dataKey="abertos"
                  stroke="#ef4444"
                  strokeWidth={2}
                  dot={{ r: 4 }}
                  name="Abertos"
                />
                <Line
                  type="monotone"
                  dataKey="resolvidos"
                  stroke="#10b981"
                  strokeWidth={2}
                  dot={{ r: 4 }}
                  name="Resolvidos"
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Conformidade */}
      {conformidade && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-700">Conformidade de Certidões</h3>
            <div className="flex items-center gap-2">
              <div className="w-32 bg-gray-100 rounded-full h-2">
                <div
                  className="h-2 rounded-full transition-all duration-700"
                  style={{
                    width: `${conformidade.compliance_score}%`,
                    backgroundColor:
                      conformidade.compliance_score >= 80
                        ? '#10b981'
                        : conformidade.compliance_score >= 60
                        ? '#f59e0b'
                        : '#ef4444',
                  }}
                />
              </div>
              <span className="text-sm font-bold text-gray-700">{conformidade.compliance_score}%</span>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {conformidade.certidoes.map((cert) => (
              <div
                key={cert.name}
                className="flex items-center justify-between p-3 rounded-lg bg-gray-50 border border-gray-100"
              >
                <div className="flex items-center gap-2">
                  <CertidaoStatus status={cert.status} />
                  <span className="text-sm text-gray-700">{cert.name}</span>
                </div>
                {cert.expires_at && (
                  <span className="text-xs text-gray-400">
                    {new Date(cert.expires_at).toLocaleDateString('pt-BR')}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Export */}
      <div className="flex justify-end">
        <button
          onClick={() => window.print()}
          className="flex items-center gap-2 px-4 py-2 text-sm bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition-colors"
        >
          <FileText className="h-4 w-4" />
          Exportar / Imprimir
        </button>
      </div>
    </div>
  );
}
