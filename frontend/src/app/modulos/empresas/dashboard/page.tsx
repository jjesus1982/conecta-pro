'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Building2,
  DollarSign,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  CheckCircle2,
  Clock,
  LayoutDashboard,
  Download,
  RefreshCw,
  ChevronRight,
  AlertCircle,
  Star,
  ArrowRight,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import Link from 'next/link';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { api } from '@/lib/api';

// ─── Formatters ──────────────────────────────────────────────────────────────
const fmt = (v: number | null | undefined) => {
  if (v == null) return 'R$ 0';
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
};
const fmtPct = (v: number | null | undefined) => `${(v ?? 0).toFixed(1)}%`;

// ─── Types ────────────────────────────────────────────────────────────────────
interface FiscalData {
  periodo: string;
  grupo: {
    total_faturamento_estimado: number;
    total_impostos_mes: number;
    economia_liminares_potencial: number;
  };
  conecta_eletronica: {
    regime: string;
    receita_estimada: number;
    impostos_mes: number;
    carga_pct: number;
    detalhamento: Record<string, number>;
  };
  conecta_patrimonial: {
    regime: string;
    receita_estimada: number;
    impostos_sem_liminar: number;
    impostos_com_liminar: number;
    economia_liminar: number;
    carga_pct_sem: number;
    carga_pct_com: number;
    status_liminares: string;
  };
  obrigacoes_mes: {
    total: number;
    criticas: number;
    atrasadas: number;
    pendentes: number;
  };
}

interface RentabilidadeData {
  resumo_grupo: {
    total_receita_mes: number;
    total_lucro_liquido_mes: number;
    margem_media_pct: number;
    total_receita_anual_estimada: number;
  };
  por_contrato: Array<{
    tipo_servico: string;
    empresa: string;
    receita_mes: number;
    impostos_mes: number;
    lucro_liquido_mes: number;
    margem_pct: number;
    situacao: string;
    alertas: string[];
  }>;
  ranking: Array<{
    tipo_servico: string;
    margem_pct: number;
    situacao: string;
  }>;
  alertas: string[];
}

interface ContabilData {
  periodo: string;
  grupo_consolidado: {
    receita_bruta: number;
    deducoes: number;
    receita_liquida: number;
    custos_operacionais: number;
    lucro_bruto: number;
    despesas_administrativas: number;
    resultado_operacional: number;
    impostos: number;
    lucro_liquido: number;
    margem_liquida_pct: number;
  };
  por_empresa: {
    conecta_eletronica: { receita_bruta: number; impostos: number; lucro_liquido: number; margem_pct: number };
    conecta_patrimonial: { receita_bruta: number; impostos: number; lucro_liquido: number; margem_pct: number; economia_potencial_liminares: number };
  };
  exportacao_contador: {
    formato: string;
    ultima_exportacao: string | null;
    proxima_exportacao: string;
    status: string;
  };
}

// ─── Dados de gráfico fiscal (estáticos para o chart) ─────────────────────────
const CHART_FISCAL_DATA = [
  { name: 'IRPJ/CSLL', eletronica: 19200, patrimonial: 0 },
  { name: 'PIS/COFINS', eletronica: 16500, patrimonial: 3882 },
  { name: 'ISS', eletronica: 10000, patrimonial: 7500 },
  { name: 'DAS/GPS', eletronica: 0, patrimonial: 8538 },
];

const SITUACAO_LABEL: Record<string, string> = {
  excelente: 'Excelente',
  bom: 'Bom',
  aceitavel: 'Aceitável',
  atencao: 'Atenção',
  deficitario: 'Deficitário',
};

const SITUACAO_COLOR: Record<string, string> = {
  excelente: 'text-green-600 bg-green-50 border-green-200',
  bom: 'text-blue-600 bg-blue-50 border-blue-200',
  aceitavel: 'text-yellow-600 bg-yellow-50 border-yellow-200',
  atencao: 'text-orange-600 bg-orange-50 border-orange-200',
  deficitario: 'text-red-600 bg-red-50 border-red-200',
};

const PIE_COLORS = ['#1a47f5', '#f97707', '#10b981', '#8b5cf6'];

// ─── Fases de Transição ────────────────────────────────────────────────────────
const FASES_TRANSICAO = [
  { label: 'Fase 0: Multi-empresa configurado', done: true, pct: 100 },
  { label: 'Fase 1: Contratos humanizados migrados', done: false, pct: 0 },
  { label: 'Fase 2: Abertura CNPJ Patrimonial', done: false, pct: 0 },
  { label: 'Fase 3: Liminares concedidas', done: false, pct: 0 },
  { label: 'Fase 4: Eletrônica migrada para Simples', done: false, pct: 0 },
];

// ─── Componente Tab ───────────────────────────────────────────────────────────
function Tab({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'px-5 py-2.5 text-sm font-semibold rounded-t-lg border-b-2 transition-colors',
        active
          ? 'border-blue-600 text-blue-700 bg-white'
          : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
      )}
    >
      {children}
    </button>
  );
}

// ─── KPI Card ─────────────────────────────────────────────────────────────────
function KpiCard({
  title, value, sub, icon: Icon, color,
}: {
  title: string; value: string; sub?: string; icon: React.ElementType; color: string;
}) {
  return (
    <Card className="border border-gray-100 shadow-sm">
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{title}</p>
            <p className={cn('font-data text-2xl font-semibold tabular-nums mt-1', color)}>{value}</p>
            {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
          </div>
          <div className={cn('p-2.5 rounded-xl', color.includes('blue') ? 'bg-blue-50' : color.includes('red') ? 'bg-red-50' : color.includes('green') ? 'bg-green-50' : 'bg-orange-50')}>
            <Icon className={cn('w-5 h-5', color)} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function DashboardMultiEmpresaPage() {
  const hoje = new Date();
  const [mes, setMes] = useState(hoje.getMonth() + 1);
  const [ano, setAno] = useState(hoje.getFullYear());
  const [activeTab, setActiveTab] = useState<'fiscal' | 'rentabilidade' | 'contabil'>('fiscal');
  const [loading, setLoading] = useState(true);
  const [fiscal, setFiscal] = useState<FiscalData | null>(null);
  const [rentabilidade, setRentabilidade] = useState<RentabilidadeData | null>(null);
  const [contabil, setContabil] = useState<ContabilData | null>(null);

  const carregar = useCallback(async () => {
    setLoading(true);
    try {
      const [f, r, c] = await Promise.all([
        api.get(`/api/v1/empresas/dashboard/fiscal/grupo?mes=${mes}&ano=${ano}`),
        api.get('/api/v1/empresas/dashboard/rentabilidade/grupo'),
        api.get(`/api/v1/empresas/dashboard/contabil/grupo?mes=${mes}&ano=${ano}`),
      ]);
      setFiscal(f.data);
      setRentabilidade(r.data);
      setContabil(c.data);
    } catch (e) {
      void e;
    } finally {
      setLoading(false);
    }
  }, [mes, ano]);

  useEffect(() => { carregar(); }, [carregar]);

  const lucroLiquido = (rentabilidade?.resumo_grupo.total_lucro_liquido_mes ?? 0);
  const impostosMes = (fiscal?.grupo.total_impostos_mes ?? 0);
  const faturamento = (fiscal?.grupo.total_faturamento_estimado ?? 350000);
  const economiaLiminar = (fiscal?.grupo.economia_liminares_potencial ?? 0);

  // Dados para o gráfico pizza de rentabilidade
  const pieData = (rentabilidade?.por_contrato ?? []).map((c, i) => ({
    name: c.tipo_servico,
    value: Math.max(0, c.lucro_liquido_mes),
    color: PIE_COLORS[i % PIE_COLORS.length],
  }));

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-gradient-to-br from-[#111b57] to-[#1a47f5] px-6 py-8">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-white/10 rounded-xl">
                <LayoutDashboard className="w-7 h-7 text-white" />
              </div>
              <div>
                <h1 className="font-display text-2xl font-bold text-white">Conecta Mais — Visão do Grupo</h1>
                <p className="text-blue-200 text-sm mt-0.5">Dashboard Multi-Empresa consolidado</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <select
                value={mes}
                onChange={e => setMes(Number(e.target.value))}
                className="rounded-lg border border-white/20 bg-white/10 text-white text-sm px-3 py-2"
              >
                {['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'].map((m, i) => (
                  <option key={i} value={i + 1} className="text-gray-900 bg-white">{m}</option>
                ))}
              </select>
              <select
                value={ano}
                onChange={e => setAno(Number(e.target.value))}
                className="rounded-lg border border-white/20 bg-white/10 text-white text-sm px-3 py-2"
              >
                {[2024, 2025, 2026].map(a => (
                  <option key={a} value={a} className="text-gray-900 bg-white">{a}</option>
                ))}
              </select>
              <button
                onClick={carregar}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 bg-white/10 hover:bg-white/20 text-white text-sm rounded-lg transition-colors"
              >
                <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
                Atualizar
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">

        {/* KPIs do Grupo */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" data-testid="kpi-cards">
          <KpiCard
            title="Faturamento Total"
            value={fmt(faturamento)}
            sub="estimativa do mês"
            icon={DollarSign}
            color="text-blue-700"
          />
          <KpiCard
            title="Impostos do Mês"
            value={fmt(impostosMes)}
            sub={`${fmtPct(impostosMes / faturamento * 100)} da receita`}
            icon={TrendingDown}
            color="text-red-600"
          />
          <KpiCard
            title="Lucro Líquido"
            value={fmt(lucroLiquido)}
            sub={`Margem ${fmtPct(rentabilidade?.resumo_grupo.margem_media_pct)}`}
            icon={TrendingUp}
            color="text-green-600"
          />
          <KpiCard
            title="Economia c/ Liminares"
            value={fmt(economiaLiminar)}
            sub="potencial mensal"
            icon={Star}
            color="text-orange-500"
          />
        </div>

        {/* Tabs */}
        <Card className="shadow-sm">
          <div className="border-b border-gray-200 px-4 flex gap-1" data-testid="tabs-container">
            <Tab active={activeTab === 'fiscal'} onClick={() => setActiveTab('fiscal')}>Fiscal</Tab>
            <Tab active={activeTab === 'rentabilidade'} onClick={() => setActiveTab('rentabilidade')}>Rentabilidade</Tab>
            <Tab active={activeTab === 'contabil'} onClick={() => setActiveTab('contabil')}>Contábil</Tab>
          </div>

          <CardContent className="p-6">
            {/* ── TAB FISCAL ── */}
            {activeTab === 'fiscal' && (
              <div className="space-y-6">
                {loading ? (
                  <div className="h-48 flex items-center justify-center">
                    <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
                  </div>
                ) : (
                  <>
                    {/* 2 cards lado a lado */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {/* Eletrônica */}
                      <div className="border border-blue-100 rounded-xl p-5 bg-blue-50/30">
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-2">
                            <Building2 className="w-5 h-5 text-blue-700" />
                            <span className="font-semibold text-gray-800">Conecta Eletrônica</span>
                          </div>
                          <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-blue-100 text-blue-700">
                            {fiscal?.conecta_eletronica.regime}
                          </span>
                        </div>
                        <div className="space-y-2 text-sm">
                          <div className="flex justify-between">
                            <span className="text-gray-600">Receita estimada</span>
                            <span className="font-semibold">{fmt(fiscal?.conecta_eletronica.receita_estimada)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-600">Impostos totais</span>
                            <span className="font-semibold text-red-600">{fmt(fiscal?.conecta_eletronica.impostos_mes)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-600">Carga tributária</span>
                            <span className="font-semibold">{fmtPct(fiscal?.conecta_eletronica.carga_pct)}</span>
                          </div>
                          <div className="border-t border-blue-100 pt-2 mt-2">
                            <p className="text-xs text-gray-500 mb-1.5">Detalhamento:</p>
                            {Object.entries(fiscal?.conecta_eletronica.detalhamento ?? {}).map(([k, v]) => (
                              <div key={k} className="flex justify-between text-xs">
                                <span className="text-gray-500 uppercase">{k}</span>
                                <span className="font-medium">{fmt(v)}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>

                      {/* Patrimonial */}
                      <div className="border border-orange-100 rounded-xl p-5 bg-orange-50/30">
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-2">
                            <Building2 className="w-5 h-5 text-orange-600" />
                            <span className="font-semibold text-gray-800">Conecta Patrimonial</span>
                          </div>
                          <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-orange-100 text-orange-700">
                            {fiscal?.conecta_patrimonial.regime}
                          </span>
                        </div>
                        <div className="space-y-2 text-sm">
                          <div className="flex justify-between">
                            <span className="text-gray-600">Receita estimada</span>
                            <span className="font-semibold">{fmt(fiscal?.conecta_patrimonial.receita_estimada)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-600">DAS sem liminar</span>
                            <span className="font-semibold text-red-600">{fmt(fiscal?.conecta_patrimonial.impostos_sem_liminar)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-600">DAS com liminar</span>
                            <span className="font-semibold text-green-600">{fmt(fiscal?.conecta_patrimonial.impostos_com_liminar)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-600">Economia liminar</span>
                            <span className="font-semibold text-orange-600">{fmt(fiscal?.conecta_patrimonial.economia_liminar)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-600">Carga s/ liminar</span>
                            <span className="font-medium">{fmtPct(fiscal?.conecta_patrimonial.carga_pct_sem)}</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Gráfico comparativo */}
                    <div>
                      <h3 className="text-sm font-semibold text-gray-700 mb-3">Comparativo de Impostos por Categoria</h3>
                      <ResponsiveContainer width="100%" height={220}>
                        <BarChart data={CHART_FISCAL_DATA} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                          <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                          <YAxis tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11 }} />
                          <Tooltip formatter={(v: unknown) => fmt(v as number)} />
                          <Legend />
                          <Bar dataKey="eletronica" name="Eletrônica" fill="#1a47f5" radius={[4, 4, 0, 0]} />
                          <Bar dataKey="patrimonial" name="Patrimonial" fill="#f97707" radius={[4, 4, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>

                    {/* Banner liminares */}
                    <div className="flex items-start gap-3 p-4 bg-yellow-50 border border-yellow-200 rounded-xl">
                      <AlertTriangle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
                      <p className="text-sm text-yellow-800">
                        <strong>Com liminares PIS/COFINS + INSS,</strong> Patrimonial economizaria{' '}
                        <strong>{fmt(fiscal?.grupo.economia_liminares_potencial)}/mês</strong> ({fmt((fiscal?.grupo.economia_liminares_potencial ?? 0) * 12)}/ano).
                        Status atual: <span className="uppercase font-medium">{fiscal?.conecta_patrimonial.status_liminares?.replace('_', ' ')}</span>.
                      </p>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* ── TAB RENTABILIDADE ── */}
            {activeTab === 'rentabilidade' && (
              <div className="space-y-6">
                {loading ? (
                  <div className="h-48 flex items-center justify-center">
                    <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
                  </div>
                ) : (
                  <>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      {/* Resumo */}
                      <div className="md:col-span-2">
                        <h3 className="text-sm font-semibold text-gray-700 mb-3">Contratos por Margem</h3>
                        <div className="space-y-2">
                          {(rentabilidade?.ranking ?? []).map((c, i) => (
                            <div key={i} className="flex items-center gap-3 p-3 rounded-lg border border-gray-100 bg-white">
                              <span className="text-xs text-gray-400 w-4">{i + 1}</span>
                              <div className="flex-1">
                                <p className="text-sm font-medium text-gray-800 capitalize">{c.tipo_servico.replace('_', ' ')}</p>
                              </div>
                              <span className={cn(
                                'text-xs font-semibold px-2.5 py-1 rounded-full border',
                                c.margem_pct >= 20
                                  ? 'text-green-700 bg-green-50 border-green-200'
                                  : c.margem_pct >= 10
                                  ? 'text-yellow-700 bg-yellow-50 border-yellow-200'
                                  : 'text-red-700 bg-red-50 border-red-200'
                              )}>
                                {fmtPct(c.margem_pct)}
                              </span>
                              <span className={cn(
                                'text-xs font-medium px-2 py-0.5 rounded border',
                                SITUACAO_COLOR[c.situacao] ?? 'text-gray-600 bg-gray-50 border-gray-200'
                              )}>
                                {SITUACAO_LABEL[c.situacao] ?? c.situacao}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Pizza */}
                      <div>
                        <h3 className="text-sm font-semibold text-gray-700 mb-3">Lucro por Contrato</h3>
                        <ResponsiveContainer width="100%" height={200}>
                          <PieChart>
                            <Pie
                              data={pieData}
                              cx="50%"
                              cy="50%"
                              innerRadius={50}
                              outerRadius={80}
                              dataKey="value"
                              label={(props: any) => `${((props.percent ?? 0) * 100).toFixed(0)}%`}
                              labelLine={false}
                            >
                              {pieData.map((entry, i) => (
                                <Cell key={i} fill={entry.color} />
                              ))}
                            </Pie>
                            <Tooltip formatter={(v: unknown) => fmt(v as number)} />
                          </PieChart>
                        </ResponsiveContainer>
                        <div className="space-y-1 mt-2">
                          {pieData.map((d, i) => (
                            <div key={i} className="flex items-center gap-2 text-xs">
                              <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: d.color }} />
                              <span className="text-gray-600 capitalize">{d.name.replace('_', ' ')}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* Alertas */}
                    {(rentabilidade?.alertas ?? []).length > 0 && (
                      <div className="p-4 bg-orange-50 border border-orange-200 rounded-xl space-y-1">
                        <div className="flex items-center gap-2 mb-1">
                          <AlertCircle className="w-4 h-4 text-orange-600" />
                          <span className="text-sm font-semibold text-orange-800">Alertas de Rentabilidade</span>
                        </div>
                        {(rentabilidade?.alertas ?? []).map((a, i) => (
                          <p key={i} className="text-xs text-orange-700 pl-6">{a}</p>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            {/* ── TAB CONTÁBIL ── */}
            {activeTab === 'contabil' && (
              <div className="space-y-6">
                {loading ? (
                  <div className="h-48 flex items-center justify-center">
                    <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
                  </div>
                ) : (
                  <>
                    {/* DRE Consolidado */}
                    <div>
                      <h3 className="text-sm font-semibold text-gray-700 mb-3">DRE Simplificado — {contabil?.periodo}</h3>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b border-gray-200">
                              <th className="text-left py-2 text-gray-500 font-medium">Linha</th>
                              <th className="text-right py-2 text-blue-700 font-medium">Eletrônica</th>
                              <th className="text-right py-2 text-orange-600 font-medium">Patrimonial</th>
                              <th className="text-right py-2 text-gray-800 font-semibold">Consolidado</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-100">
                            {[
                              { label: 'Receita Bruta', eletKey: 'receita_bruta', patKey: 'receita_bruta', consKey: 'receita_bruta' },
                              { label: 'Impostos', eletKey: 'impostos', patKey: 'impostos', consKey: 'impostos', neg: true },
                              { label: 'Lucro Líquido', eletKey: 'lucro_liquido', patKey: 'lucro_liquido', consKey: 'lucro_liquido', bold: true },
                            ].map((row, i) => {
                              const elet = contabil?.por_empresa.conecta_eletronica as any;
                              const pat = contabil?.por_empresa.conecta_patrimonial as any;
                              const cons = contabil?.grupo_consolidado as any;
                              return (
                                <tr key={i} className={row.bold ? 'bg-gray-50' : ''}>
                                  <td className={cn('py-2.5 text-gray-600', row.bold && 'font-semibold text-gray-800')}>{row.label}</td>
                                  <td className={cn('py-2.5 text-right', row.neg ? 'text-red-600' : 'text-gray-800', row.bold && 'font-semibold')}>
                                    {fmt(elet?.[row.eletKey])}
                                  </td>
                                  <td className={cn('py-2.5 text-right', row.neg ? 'text-red-600' : 'text-gray-800', row.bold && 'font-semibold')}>
                                    {fmt(pat?.[row.patKey])}
                                  </td>
                                  <td className={cn('py-2.5 text-right font-semibold', row.neg ? 'text-red-600' : row.bold ? 'text-green-700' : 'text-gray-800')}>
                                    {fmt(cons?.[row.consKey])}
                                  </td>
                                </tr>
                              );
                            })}
                            <tr>
                              <td className="py-2.5 text-gray-600">Margem Líquida</td>
                              <td className="py-2.5 text-right">{fmtPct(contabil?.por_empresa.conecta_eletronica.margem_pct)}</td>
                              <td className="py-2.5 text-right">{fmtPct(contabil?.por_empresa.conecta_patrimonial.margem_pct)}</td>
                              <td className="py-2.5 text-right font-semibold">{fmtPct(contabil?.grupo_consolidado.margem_liquida_pct)}</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>

                    {/* Economia liminares Patrimonial */}
                    <div className="flex items-start gap-3 p-4 bg-green-50 border border-green-200 rounded-xl">
                      <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
                      <p className="text-sm text-green-800">
                        <strong>Patrimonial:</strong> com liminares ativas, economia potencial de{' '}
                        <strong>{fmt(contabil?.por_empresa.conecta_patrimonial.economia_potencial_liminares)}/mês</strong>{' '}
                        ({fmt((contabil?.por_empresa.conecta_patrimonial.economia_potencial_liminares ?? 0) * 12)}/ano).
                      </p>
                    </div>

                    {/* Exportação Domínio */}
                    <div className="border border-gray-200 rounded-xl p-5">
                      <div className="flex items-start justify-between">
                        <div>
                          <h3 className="font-semibold text-gray-800">Exportação para Contador</h3>
                          <p className="text-sm text-gray-500 mt-0.5">Formato: {contabil?.exportacao_contador.formato}</p>
                          <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                            <span>Última: {contabil?.exportacao_contador.ultima_exportacao ?? 'Nunca'}</span>
                            <span>Próxima: {contabil?.exportacao_contador.proxima_exportacao}</span>
                          </div>
                        </div>
                        <button type="button" className="flex items-center gap-2 px-4 py-2 bg-[#111b57] hover:bg-[#1a47f5] text-white text-sm rounded-lg transition-colors">
                          <Download className="w-4 h-4" />
                          Exportar Agora
                        </button>
                      </div>
                      <div className="mt-3">
                        <span className={cn(
                          'inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full',
                          contabil?.exportacao_contador.status === 'pendente'
                            ? 'bg-yellow-50 text-yellow-700 border border-yellow-200'
                            : 'bg-green-50 text-green-700 border border-green-200'
                        )}>
                          <Clock className="w-3 h-3" />
                          {contabil?.exportacao_contador.status === 'pendente' ? 'Exportação pendente' : 'Exportado'}
                        </span>
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Obrigações Críticas */}
        <Card className="shadow-sm">
          <CardContent className="p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-orange-500" />
                <h2 className="font-semibold text-gray-800">Obrigações do Mês</h2>
              </div>
              <Link
                href="/modulos/empresas/obrigacoes"
                className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 font-medium"
              >
                Ver Calendário Completo
                <ChevronRight className="w-4 h-4" />
              </Link>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: 'Total', value: fiscal?.obrigacoes_mes.total ?? 0, color: 'text-gray-700', bg: 'bg-gray-50' },
                { label: 'Críticas', value: fiscal?.obrigacoes_mes.criticas ?? 0, color: 'text-red-700', bg: 'bg-red-50' },
                { label: 'Atrasadas', value: fiscal?.obrigacoes_mes.atrasadas ?? 0, color: 'text-orange-700', bg: 'bg-orange-50' },
                { label: 'Pendentes', value: fiscal?.obrigacoes_mes.pendentes ?? 0, color: 'text-yellow-700', bg: 'bg-yellow-50' },
              ].map((item, i) => (
                <div key={i} className={cn('rounded-xl p-4 text-center', item.bg)}>
                  <p className={cn('font-data text-2xl font-semibold tabular-nums', item.color)}>{item.value}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{item.label}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Guia de Transição */}
        <Card className="shadow-sm">
          <CardContent className="p-5">
            <div className="flex items-center gap-2 mb-4">
              <ArrowRight className="w-5 h-5 text-blue-600" />
              <h2 className="font-semibold text-gray-800">Estratégia de Transição — Conecta Mais</h2>
            </div>
            <div className="space-y-3">
              {FASES_TRANSICAO.map((fase, i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className={cn(
                    'w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0',
                    fase.done ? 'bg-green-100' : 'bg-gray-100'
                  )}>
                    {fase.done
                      ? <CheckCircle2 className="w-4 h-4 text-green-600" />
                      : <Clock className="w-4 h-4 text-gray-400" />
                    }
                  </div>
                  <div className="flex-1">
                    <p className={cn('text-sm', fase.done ? 'text-gray-800 font-medium' : 'text-gray-500')}>{fase.label}</p>
                    <div className="w-full bg-gray-100 rounded-full h-1.5 mt-1">
                      <div
                        className={cn('h-1.5 rounded-full transition-all', fase.done ? 'bg-green-500' : 'bg-gray-300')}
                        style={{ width: `${fase.pct}%` }}
                      />
                    </div>
                  </div>
                  <span className="text-xs text-gray-400 w-8 text-right">{fase.pct}%</span>
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-400 mt-4 italic">
              Progresso geral: 20% (1 de 5 fases concluída). Economia anual estimada ao concluir: R$ 145.440.
            </p>
          </CardContent>
        </Card>

      </div>
    </div>
  );
}
