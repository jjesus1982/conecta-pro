'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  ClipboardList,
  AlertTriangle,
  Clock,
  CheckCircle2,
  Building2,
  Bell,
  ExternalLink,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  ShieldOff,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

// ─── Types ─────────────────────────────────────────────────────────────────

interface Obrigacao {
  tipo: string;
  descricao: string;
  periodo: string;
  vencimento: string;
  status: string;
  urgencia: string;
  regime?: string;
  link?: string | null;
  empresa?: string;
  empresa_slug?: string;
}

interface Resumo {
  total: number;
  criticas: number;
  atrasadas: number;
  pendentes: number;
  concluidas: number;
}

interface CalendarioGrupo {
  mes: number;
  ano: number;
  resumo: Resumo;
  por_empresa: Record<string, Obrigacao[]>;
  consolidado: Obrigacao[];
}

// ─── Helpers ────────────────────────────────────────────────────────────────

const MESES = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
];

function urgenciaBadge(urgencia: string) {
  if (urgencia === 'critica')
    return (
      <span className="inline-flex items-center gap-1 text-xs font-bold bg-red-100 text-red-700 px-2 py-0.5 rounded-full animate-pulse">
        <AlertTriangle className="h-3 w-3" /> Crítica
      </span>
    );
  if (urgencia === 'alta')
    return (
      <span className="inline-flex items-center gap-1 text-xs font-semibold bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full">
        <Clock className="h-3 w-3" /> Alta
      </span>
    );
  if (urgencia === 'atrasada')
    return (
      <span className="inline-flex items-center gap-1 text-xs font-bold bg-red-200 text-red-800 px-2 py-0.5 rounded-full animate-pulse">
        <AlertTriangle className="h-3 w-3" /> Atrasada
      </span>
    );
  return (
    <span className="text-xs font-medium bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">Normal</span>
  );
}

function statusBadge(status: string) {
  if (status === 'atrasada')
    return (
      <span className="text-xs font-bold bg-red-100 text-red-700 px-2 py-0.5 rounded-full animate-pulse">
        Atrasada
      </span>
    );
  if (status === 'concluida')
    return (
      <span className="inline-flex items-center gap-1 text-xs font-semibold bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
        <CheckCircle2 className="h-3 w-3" /> Concluída
      </span>
    );
  if (status === 'em_andamento')
    return (
      <span className="text-xs font-semibold bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">
        Em Andamento
      </span>
    );
  return (
    <span className="text-xs font-semibold bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded-full">
      Pendente
    </span>
  );
}

function empresaBadge(slug?: string) {
  if (slug === 'conecta_eletronica')
    return (
      <span className="text-xs font-semibold bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full border border-blue-200">
        Eletrônica
      </span>
    );
  if (slug === 'conecta_patrimonial')
    return (
      <span className="text-xs font-semibold bg-orange-100 text-orange-800 px-2 py-0.5 rounded-full border border-orange-200">
        Patrimonial
      </span>
    );
  return null;
}

function formatDate(iso: string) {
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}

// ─── Tabela de Obrigações ───────────────────────────────────────────────────

function TabelaObrigacoes({
  obrigacoes,
  showEmpresa = false,
}: {
  obrigacoes: Obrigacao[];
  showEmpresa?: boolean;
}) {
  if (obrigacoes.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400">
        <ClipboardList className="h-10 w-10 mx-auto mb-3 opacity-40" />
        <p>Nenhuma obrigação encontrada para este período.</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs font-semibold text-gray-500 uppercase border-b border-gray-100">
            {showEmpresa && <th className="py-3 px-4">Empresa</th>}
            <th className="py-3 px-4">Tipo</th>
            <th className="py-3 px-4 hidden md:table-cell">Descrição</th>
            <th className="py-3 px-4 hidden sm:table-cell">Período</th>
            <th className="py-3 px-4">Vencimento</th>
            <th className="py-3 px-4">Urgência</th>
            <th className="py-3 px-4">Status</th>
            <th className="py-3 px-4">Link</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {obrigacoes.map((o, i) => (
            <tr
              key={i}
              className={cn(
                'hover:bg-gray-50 transition-colors',
                o.status === 'atrasada' && 'bg-red-50/50',
                o.urgencia === 'critica' && 'bg-orange-50/50',
              )}
            >
              {showEmpresa && (
                <td className="py-3 px-4">{empresaBadge(o.empresa_slug)}</td>
              )}
              <td className="py-3 px-4">
                <span className="font-mono text-xs font-bold text-[#111b57] bg-blue-50 px-1.5 py-0.5 rounded">
                  {o.tipo}
                </span>
              </td>
              <td className="py-3 px-4 hidden md:table-cell text-gray-600 max-w-xs truncate">
                {o.descricao}
              </td>
              <td className="py-3 px-4 hidden sm:table-cell text-gray-500 text-xs">{o.periodo}</td>
              <td className="py-3 px-4 font-semibold text-gray-800 whitespace-nowrap">
                {formatDate(o.vencimento)}
              </td>
              <td className="py-3 px-4">{urgenciaBadge(o.urgencia)}</td>
              <td className="py-3 px-4">{statusBadge(o.status)}</td>
              <td className="py-3 px-4">
                {o.link ? (
                  <a
                    href={o.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 text-xs font-medium"
                  >
                    Acessar <ExternalLink className="h-3 w-3" />
                  </a>
                ) : (
                  <span className="text-gray-300 text-xs">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Componente Principal ──────────────────────────────────────────────────

type Tab = 'grupo' | 'eletronica' | 'patrimonial';

export default function ObrigacoesPage() {
  const today = new Date();
  const [mes, setMes] = useState(today.getMonth() + 1);
  const [ano, setAno] = useState(today.getFullYear());
  const [tab, setTab] = useState<Tab>('grupo');
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<CalendarioGrupo | null>(null);
  const [dispensadas, setDispensadas] = useState<string[]>([]);
  const [error, setError] = useState('');

  const fetchCalendario = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch(
        `/api/v1/empresas/obrigacoes/calendario/grupo?mes=${mes}&ano=${ano}`,
        { headers }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Erro ao carregar calendário');
    } finally {
      setLoading(false);
    }
  }, [mes, ano]);

  const fetchDispensadas = useCallback(async () => {
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
      const headers: Record<string, string> = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const res = await fetch('/api/v1/empresas/obrigacoes/dispensadas-simples', { headers });
      if (res.ok) {
        const json = await res.json();
        setDispensadas(json.dispensadas || []);
      }
    } catch {
      // silently ignore
    }
  }, []);

  useEffect(() => {
    fetchCalendario();
    fetchDispensadas();
  }, [fetchCalendario, fetchDispensadas]);

  const prevMes = () => {
    if (mes === 1) { setMes(12); setAno(a => a - 1); }
    else setMes(m => m - 1);
  };
  const nextMes = () => {
    if (mes === 12) { setMes(1); setAno(a => a + 1); }
    else setMes(m => m + 1);
  };

  const resumo = data?.resumo;
  const consolidado = data?.consolidado ?? [];
  const eletronica = data?.por_empresa?.conecta_eletronica ?? [];
  const patrimonial = data?.por_empresa?.conecta_patrimonial ?? [];

  const tabObrigacoes: Record<Tab, Obrigacao[]> = {
    grupo: consolidado,
    eletronica,
    patrimonial,
  };

  const TABS: { key: Tab; label: string; icon: React.ReactNode; count: number }[] = [
    {
      key: 'grupo',
      label: 'Grupo Consolidado',
      icon: <Building2 className="h-4 w-4" />,
      count: consolidado.length,
    },
    {
      key: 'eletronica',
      label: 'Eletrônica',
      icon: <Building2 className="h-4 w-4 text-blue-600" />,
      count: eletronica.length,
    },
    {
      key: 'patrimonial',
      label: 'Patrimonial',
      icon: <Building2 className="h-4 w-4 text-orange-500" />,
      count: patrimonial.length,
    },
  ];

  return (
    <div className="min-h-screen bg-gray-50 p-4 md:p-8">
      {/* Header */}
      <div className="mb-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl md:text-3xl font-bold text-[hsl(var(--foreground))] flex items-center gap-3">
            <ClipboardList className="h-8 w-8 text-[#f97707]" />
            Obrigações Fiscais Multi-Empresa
          </h1>
          <p className="text-gray-500 mt-1 text-sm">
            Calendário consolidado de obrigações fiscais e contábeis do grupo
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={fetchCalendario}
            disabled={loading}
            className="flex items-center gap-2 border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
            Atualizar
          </button>
          <button type="button" className="flex items-center gap-2 bg-[#111b57] hover:bg-[#1a47f5] text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors">
            <Bell className="h-4 w-4" />
            Configurar Alertas
          </button>
        </div>
      </div>

      {/* Seletor Mês/Ano */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={prevMes}
          className="p-2 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 transition-colors"
        >
          <ChevronLeft className="h-4 w-4 text-gray-600" />
        </button>
        <div className="text-center min-w-[160px]">
          <p className="font-bold text-[#111b57] text-lg">
            {MESES[mes - 1]} {ano}
          </p>
        </div>
        <button
          onClick={nextMes}
          className="p-2 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 transition-colors"
        >
          <ChevronRight className="h-4 w-4 text-gray-600" />
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
        {[
          {
            label: 'Total',
            value: resumo?.total ?? 0,
            icon: <ClipboardList className="h-5 w-5" />,
            color: 'bg-blue-50 text-blue-700 border-blue-100',
            valueColor: 'text-blue-800',
          },
          {
            label: 'Críticas',
            value: resumo?.criticas ?? 0,
            icon: <AlertTriangle className="h-5 w-5" />,
            color: 'bg-red-50 text-red-700 border-red-100',
            valueColor: 'text-red-700',
          },
          {
            label: 'Atrasadas',
            value: resumo?.atrasadas ?? 0,
            icon: <Clock className="h-5 w-5" />,
            color: 'bg-orange-50 text-orange-700 border-orange-100',
            valueColor: 'text-orange-700',
          },
          {
            label: 'Pendentes',
            value: resumo?.pendentes ?? 0,
            icon: <Clock className="h-5 w-5" />,
            color: 'bg-yellow-50 text-yellow-700 border-yellow-100',
            valueColor: 'text-yellow-700',
          },
        ].map((kpi) => (
          <Card key={kpi.label} className={cn('border', kpi.color)}>
            <CardContent className="p-4">
              <div className={cn('mb-2', kpi.color.split(' ')[1])}>{kpi.icon}</div>
              <p className={cn('font-data text-3xl font-semibold tabular-nums', kpi.valueColor)}>{kpi.value}</p>
              <p className="text-xs font-medium mt-1 text-gray-500">{kpi.label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 rounded-xl p-1 mb-6 max-w-xl">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              'flex-1 flex items-center justify-center gap-1.5 text-xs font-semibold py-2 px-3 rounded-lg transition-all',
              tab === t.key
                ? 'bg-white text-[#111b57] shadow-sm'
                : 'text-gray-500 hover:text-gray-700',
            )}
          >
            {t.icon}
            {t.label}
            <span
              className={cn(
                'rounded-full text-xs px-1.5 py-0.5',
                tab === t.key ? 'bg-blue-100 text-blue-700' : 'bg-gray-200 text-gray-600',
              )}
            >
              {t.count}
            </span>
          </button>
        ))}
      </div>

      {/* Tabela */}
      <Card className="border border-gray-200 shadow-sm mb-8">
        <CardContent className="p-0">
          {loading ? (
            <div className="py-16 text-center text-gray-400">
              <RefreshCw className="h-8 w-8 mx-auto animate-spin mb-3 opacity-40" />
              <p>Carregando calendário...</p>
            </div>
          ) : (
            <TabelaObrigacoes
              obrigacoes={tabObrigacoes[tab]}
              showEmpresa={tab === 'grupo'}
            />
          )}
        </CardContent>
      </Card>

      {/* Seção Dispensadas - Simples Nacional */}
      {dispensadas.length > 0 && (
        <div>
          <h2 className="text-lg font-bold text-[#111b57] flex items-center gap-2 mb-4">
            <ShieldOff className="h-5 w-5 text-blue-500" />
            Dispensadas — Simples Nacional (Patrimonial)
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            {dispensadas.map((d) => (
              <div
                key={d}
                className="bg-blue-50 border border-blue-100 rounded-xl p-4 flex items-start gap-3"
              >
                <CheckCircle2 className="h-4 w-4 text-blue-500 mt-0.5 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-blue-800">{d}</p>
                  <p className="text-xs text-blue-500 mt-0.5">Dispensada — LC 123/2006</p>
                </div>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-400 mt-3">
            Empresas optantes pelo Simples Nacional são dispensadas dessas obrigações conforme a Lei Complementar 123/2006.
          </p>
        </div>
      )}
    </div>
  );
}
