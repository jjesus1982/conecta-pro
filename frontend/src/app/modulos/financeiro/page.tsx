'use client';

import { DollarSign, TrendingUp, TrendingDown, Activity, ArrowRight, CreditCard, CheckCircle2, Users, Calculator, Receipt, Wallet, Building2, RefreshCw, Wifi, WifiOff, BarChart2, AlertTriangle, CheckCircle, Barcode, Brain, Shield, Zap, Eye, MessageCircle, Send, Lightbulb, Tag } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { useRouter } from 'next/navigation';
import { useCondominio } from '@/contexts/CondominioContext';
import { useFinancialOverview, usePayableDashboard, useReceivableDashboard, useCashflowDashboard } from '@/hooks/financial/useFinancial';
import type { IFinancialOverview } from '@/types/financial';
import { useState, useEffect, useCallback } from 'react';
import { fetchBankBalances, fetchBankStatus, bankingApi } from '@/services/banking/bankingService';
import type { BankBalance, BankConnectionStatus } from '@/services/banking/bankingService';
import { api } from '@/lib/api';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  Legend,
} from 'recharts';

const formatCurrency = (value: number | undefined | null) => {
  if (value == null) return 'R$ 0,00';
  return value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
};

// Demo data fallbacks
const MARGIN_DEMO = [
  { tipo: 'Portaria', label: 'Portaria', margem: 22, cor: '#3b82f6' },
  { tipo: 'Limpeza', label: 'Limpeza', margem: 18, cor: '#10b981' },
  { tipo: 'Jardinagem', label: 'Jardinagem', margem: 25, cor: '#22c55e' },
  { tipo: 'Seg. Eletrônica', label: 'Seg. Eletrônica', margem: 35, cor: '#8b5cf6' },
  { tipo: 'Portaria Remota', label: 'Portaria Remota', margem: 40, cor: '#f97316' },
];

const CASHFLOW_DEMO = Array.from({ length: 30 }, (_, i) => {
  const day = i + 1;
  const base = 150000 + Math.sin(i / 3) * 20000;
  return {
    dia: `${day < 10 ? '0' : ''}${day}/03`,
    esperado: Math.round(base),
    otimista: Math.round(base * 1.12),
    pessimista: Math.round(base * 0.88),
  };
});

const navigationCards = [
  {
    title: 'Contas a Pagar',
    description: 'Gerencie pagamentos, vencimentos e fornecedores',
    href: '/modulos/financeiro/contas-pagar',
    icon: TrendingDown,
  },
  {
    title: 'Contas a Receber',
    description: 'Controle cobranças, boletos e recebimentos',
    href: '/modulos/financeiro/contas-receber',
    icon: TrendingUp,
  },
  {
    title: 'Fluxo de Caixa',
    description: 'Acompanhe entradas, saídas e projeções',
    href: '/modulos/financeiro/fluxo-caixa',
    icon: Activity,
  },
  {
    title: 'Conciliação',
    description: 'Concilie extratos bancários e lançamentos',
    href: '/modulos/financeiro/conciliacao',
    icon: CheckCircle2,
  },
  {
    title: 'Fornecedores',
    description: 'Cadastro e gestão de fornecedores',
    href: '/modulos/financeiro/fornecedores',
    icon: Users,
  },
  {
    title: 'Contabilidade',
    description: 'Plano de contas, lançamentos e balancetes',
    href: '/modulos/financeiro/contabilidade',
    icon: Calculator,
  },
  {
    title: 'Faturamento',
    description: 'Emissão de faturas e controle de billing',
    href: '/modulos/financeiro/faturamento',
    icon: Receipt,
  },
  {
    title: 'Custeio ABC',
    description: 'Análise de custos por atividade',
    href: '/modulos/financeiro/custeio',
    icon: Wallet,
  },
  {
    title: 'Relatórios',
    description: 'DRE, Balanço Patrimonial e demonstrativos',
    href: '/modulos/financeiro/relatorios',
    icon: BarChart2,
  },
  {
    title: 'Cobranças',
    description: 'Emita boletos e cobranças via Banco Inter',
    href: '/modulos/financeiro/cobrancas',
    icon: Barcode,
  },
  {
    title: 'Banco Inter',
    description: 'Saldo, extrato, boletos, PIX e pagamentos bancários',
    href: '/modulos/financeiro/banking',
    icon: Building2,
  },
  {
    title: 'Inter — D6',
    description: 'Extrato, conciliação folha, cobranças e PIX recebidos (D6)',
    href: '/modulos/financeiro/inter',
    icon: Building2,
  },
  {
    title: 'Pagamentos & Transferências',
    description: 'Envie PIX, DARF, GPS, boletos e TED pelo Banco Inter (com OTP)',
    href: '/modulos/financeiro/inter/pagamentos',
    icon: Send,
  },
  {
    title: 'Precificação',
    description: 'Calcule preços ideais para novos contratos com IA',
    href: '/modulos/crm/precificacao',
    icon: Calculator,
  },
];

// Custom Tooltip for Cashflow AreaChart
function CashflowTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg p-3 shadow-lg text-xs">
      <p className="font-semibold text-[hsl(var(--foreground))] mb-1">{label}</p>
      {payload.map((entry: any) => (
        <p key={entry.dataKey} style={{ color: entry.color }}>
          {entry.name}: {formatCurrency(entry.value)}
        </p>
      ))}
    </div>
  );
}

// Custom Tooltip for Margin BarChart
function MarginTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg p-3 shadow-lg text-xs">
      <p className="font-semibold text-[hsl(var(--foreground))] mb-1">{label}</p>
      <p style={{ color: payload[0]?.fill ?? '#3b82f6' }}>Margem: {payload[0]?.value}%</p>
    </div>
  );
}

export default function FinanceiroPage() {
  const router = useRouter();
  const { condominioId } = useCondominio();
  const { data: overview, isLoading } = useFinancialOverview({ condominio_id: condominioId }) as {
    data: IFinancialOverview | undefined;
    isLoading: boolean;
  };

  const { data: payableData } = usePayableDashboard({ condominio_id: condominioId });
  const { data: receivableData } = useReceivableDashboard({ condominio_id: condominioId });
  const { data: cashflowData } = useCashflowDashboard({ condominio_id: condominioId });

  const payableStats = payableData as any;
  const receivableStats = receivableData as any;
  const cashflowStats = cashflowData as any;

  // Conta bancária integrada (Banco Inter)
  const [bankBalances, setBankBalances] = useState<BankBalance[]>([]);
  const [bankStatus, setBankStatus] = useState<BankConnectionStatus[]>([]);
  const [bankLoading, setBankLoading] = useState(true);
  const [lastBankSync, setLastBankSync] = useState<string | null>(null);

  // AI Command Center
  const [aiInsights, setAiInsights] = useState<any[]>([]);
  const [aiAlerts, setAiAlerts] = useState<any[]>([]);
  const [aiHealth, setAiHealth] = useState<any | null>(null);
  const [aiLoading, setAiLoading] = useState(true);
  const [cashflowPoints, setCashflowPoints] = useState<any[]>([]);
  const [cashflowGaps, setCashflowGaps] = useState<any[]>([]);

  // Margin by service type
  const [marginData, setMarginData] = useState<typeof MARGIN_DEMO>(MARGIN_DEMO);
  const [marginLoading, setMarginLoading] = useState(true);

  // Pending payables (actions)
  const [pendingPayables, setPendingPayables] = useState<any[]>([]);
  const [pendingLoading, setPendingLoading] = useState(true);

  // Financial Advisor chat
  const [advisorRecommendations, setAdvisorRecommendations] = useState<any[]>([]);
  const [advisorLoading, setAdvisorLoading] = useState(false);
  const [advisorRecsLoaded, setAdvisorRecsLoaded] = useState(false);
  const [chatMessages, setChatMessages] = useState<{role: 'user'|'advisor'; text: string}[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);

  const loadBankData = useCallback(async () => {
    setBankLoading(true);
    try {
      const [balancesResp, statusResp] = await Promise.all([
        fetchBankBalances(),
        fetchBankStatus(),
      ]);
      setBankBalances(balancesResp.balances);
      setBankStatus(statusResp);
      setLastBankSync(new Date().toLocaleTimeString('pt-BR'));
    } catch {
      // silently ignore
    } finally {
      setBankLoading(false);
    }
  }, []);

  const loadAIInsights = useCallback(async () => {
    setAiLoading(true);
    try {
      const { data } = await bankingApi.get('/api/v1/financial/ai/command-center');
      setAiInsights(data.insights ?? []);
      setAiAlerts(data.alerts ?? []);
      setAiHealth(data.health ?? null);
      // Cashflow from command-center
      const points: any[] = data.cashflow?.points ?? [];
      const gaps: any[] = data.cashflow?.gaps ?? [];
      if (points.length > 0) {
        setCashflowPoints(points.map((p: any) => ({
          dia: p.date ?? p.dia ?? '',
          esperado: p.expected ?? p.esperado ?? 0,
          otimista: p.optimistic ?? p.otimista ?? 0,
          pessimista: p.pessimistic ?? p.pessimista ?? 0,
        })));
      } else {
        setCashflowPoints(CASHFLOW_DEMO);
      }
      setCashflowGaps(gaps);
    } catch {
      setCashflowPoints(CASHFLOW_DEMO);
    } finally {
      setAiLoading(false);
    }
  }, []);

  const loadMarginData = useCallback(async () => {
    setMarginLoading(true);
    try {
      const { data } = await api.get('/api/v1/financial/ai/costing/margin-by-type');
      const items: any[] = Array.isArray(data) ? data : (data?.items ?? []);
      if (items.length > 0) {
        const COLOR_MAP: Record<string, string> = {
          portaria: '#3b82f6',
          limpeza: '#10b981',
          jardinagem: '#22c55e',
          seguranca_eletronica: '#8b5cf6',
          portaria_remota: '#f97316',
        };
        setMarginData(items.map((item: any) => ({
          tipo: item.tipo ?? item.type ?? item.label ?? '',
          label: item.label ?? item.tipo ?? item.type ?? '',
          margem: item.margem ?? item.margin ?? 0,
          cor: COLOR_MAP[item.tipo?.toLowerCase()?.replace(/\s/g, '_') ?? ''] ?? '#3b82f6',
        })));
      }
      // else keep MARGIN_DEMO
    } catch {
      // keep MARGIN_DEMO
    } finally {
      setMarginLoading(false);
    }
  }, []);

  const loadAdvisorRecommendations = useCallback(async () => {
    if (advisorRecsLoaded) return;
    setAdvisorLoading(true);
    try {
      const { data } = await bankingApi.get('/api/v1/financial/ai/advisor/recommendations');
      const recs: any[] = Array.isArray(data) ? data : (data?.items ?? []);
      setAdvisorRecommendations(recs.slice(0, 4));
      setAdvisorRecsLoaded(true);
    } catch {
      setAdvisorRecommendations([]);
    } finally {
      setAdvisorLoading(false);
    }
  }, [advisorRecsLoaded]);

  const sendAdvisorMessage = async () => {
    const q = chatInput.trim();
    if (!q || chatLoading) return;
    setChatMessages(prev => [...prev, { role: 'user', text: q }]);
    setChatInput('');
    setChatLoading(true);
    try {
      const { data } = await bankingApi.post('/api/v1/financial/ai/advisor/chat', { pergunta: q });
      const answer = data.resposta ?? data.answer ?? 'Sem resposta disponível.';
      setChatMessages(prev => [...prev, { role: 'advisor', text: answer }]);
    } catch {
      setChatMessages(prev => [...prev, { role: 'advisor', text: 'Erro ao conectar com o Advisor. Tente novamente.' }]);
    } finally {
      setChatLoading(false);
    }
  };

  const loadPendingPayables = useCallback(async () => {
    setPendingLoading(true);
    try {
      const { data } = await api.get('/api/v1/financial/payables', {
        params: { status: 'pendente', limit: 5 },
      });
      const items: any[] = Array.isArray(data) ? data : (data?.items ?? []);
      setPendingPayables(items.slice(0, 5));
    } catch {
      setPendingPayables([]);
    } finally {
      setPendingLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBankData();
    loadAIInsights();
    loadMarginData();
    loadPendingPayables();
  }, [loadBankData, loadAIInsights, loadMarginData, loadPendingPayables]);

  const getBankStatusInfo = (bankCode: string) =>
    bankStatus.find((s) => s.bank_code === bankCode);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <DollarSign className="w-12 h-12" />
        </div>
      </div>
    );
  }

  const displayCashflow = cashflowPoints.length > 0 ? cashflowPoints : CASHFLOW_DEMO;

  return (
    <div className="min-h-screen bg-grid">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[hsl(var(--background))]/80 backdrop-blur-xl border-b border-[hsl(var(--border))]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-4 h-16">
            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
              <DollarSign className="w-5 h-5 text-emerald-500" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                Financeiro
              </h1>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                Gestão financeira completa
              </p>
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* ── KPI Cards ── */}
        <div className="mb-8">
          <h2 className="text-lg font-semibold text-[hsl(var(--foreground))] mb-4">
            Indicadores
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Receita */}
            <Card>
              <CardContent className="pt-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                    <TrendingUp className="w-5 h-5 text-green-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Receita</p>
                    <p className="font-data text-xl font-semibold tabular-nums text-green-500 truncate">
                      {formatCurrency(overview?.receita_total)}
                    </p>
                    {receivableStats?.total_count != null && (
                      <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">
                        {receivableStats.total_count} recebimento{receivableStats.total_count !== 1 ? 's' : ''} no período
                      </p>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Despesa */}
            <Card>
              <CardContent className="pt-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
                    <TrendingDown className="w-5 h-5 text-red-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Despesa</p>
                    <p className="font-data text-xl font-semibold tabular-nums text-red-500 truncate">
                      {formatCurrency(overview?.despesa_total)}
                    </p>
                    {payableStats?.total_count != null && (
                      <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">
                        {payableStats.total_count} pagamento{payableStats.total_count !== 1 ? 's' : ''} no período
                      </p>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Saldo */}
            <Card>
              <CardContent className="pt-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                    <Activity className="w-5 h-5 text-blue-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Saldo</p>
                    <p className="font-data text-xl font-semibold tabular-nums text-blue-500 truncate">
                      {formatCurrency(overview?.saldo)}
                    </p>
                    {cashflowStats?.projected_balance != null && (
                      <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">
                        Projetado: {formatCurrency(cashflowStats.projected_balance)}
                      </p>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Inadimplência */}
            <Card>
              <CardContent className="pt-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-yellow-500/10 flex items-center justify-center">
                    <CreditCard className="w-5 h-5 text-yellow-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Inadimplência</p>
                    <p className="font-data text-xl font-semibold tabular-nums text-yellow-500 truncate">
                      {formatCurrency(overview?.inadimplencia)}
                    </p>
                    {receivableStats?.overdue_count != null && (
                      <p className="text-xs text-red-400 mt-0.5">
                        {receivableStats.overdue_count} em atraso
                      </p>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* ── AI Command Center ── */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-purple-500/10 flex items-center justify-center">
                <Brain className="w-4 h-4 text-purple-500" />
              </div>
              <h2 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                AI Command Center
              </h2>
            </div>
            {aiHealth && (
              <div className={cn(
                'flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold',
                aiHealth.classification === 'excelente' ? 'bg-green-500/10 text-green-600' :
                aiHealth.classification === 'bom' ? 'bg-blue-500/10 text-blue-600' :
                aiHealth.classification === 'atencao' ? 'bg-yellow-500/10 text-yellow-600' :
                'bg-red-500/10 text-red-600'
              )}>
                <Shield className="w-3 h-3" />
                Score {aiHealth.score}/100 — {aiHealth.classification}
              </div>
            )}
          </div>

          {aiLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {[...Array(2)].map((_, i) => (
                <Card key={i}><CardContent className="pt-4"><div className="h-12 bg-[hsl(var(--muted))] rounded animate-pulse" /></CardContent></Card>
              ))}
            </div>
          ) : aiAlerts.length === 0 && aiInsights.length === 0 ? (
            <div className="flex items-center gap-3 p-4 rounded-xl bg-green-500/10 border border-green-500/20">
              <CheckCircle className="w-5 h-5 text-green-500 shrink-0" />
              <div>
                <p className="text-sm font-semibold text-green-600 dark:text-green-400">Saúde financeira em dia</p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Nenhum alerta ou risco identificado pelos agentes de IA</p>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {aiAlerts.slice(0, 3).map((alert: any, idx: number) => (
                <div key={idx} className={cn(
                  'flex items-start gap-3 p-4 rounded-xl border',
                  alert.level === 'vermelho' ? 'bg-red-500/10 border-red-500/20' :
                  alert.level === 'laranja' ? 'bg-orange-500/10 border-orange-500/20' :
                  'bg-yellow-500/10 border-yellow-500/20'
                )}>
                  <AlertTriangle className={cn('w-4 h-4 shrink-0 mt-0.5',
                    alert.level === 'vermelho' ? 'text-red-500' :
                    alert.level === 'laranja' ? 'text-orange-500' : 'text-yellow-500'
                  )} />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-[hsl(var(--foreground))]">{alert.title}</p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">{alert.action}</p>
                  </div>
                </div>
              ))}
              {aiInsights.slice(0, 2).map((insight: any, idx: number) => (
                <div key={idx} className="flex items-start gap-3 p-4 rounded-xl bg-blue-500/10 border border-blue-500/20">
                  <Zap className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-[hsl(var(--foreground))]">{insight.title}</p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">{insight.description}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Fluxo de Caixa 30d  |  Margem por Tipo ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">

          {/* Fluxo de Caixa 30 Dias */}
          <Card>
            <CardContent className="pt-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-semibold text-[hsl(var(--foreground))]">Fluxo de Caixa — 30 Dias</h3>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Projeção com cenários otimista e pessimista</p>
                </div>
                <button
                  onClick={() => router.push('/modulos/financeiro/fluxo-caixa')}
                  className="text-xs text-[hsl(var(--primary))] hover:underline flex items-center gap-1 shrink-0"
                >
                  Ver projeção completa
                  <ArrowRight className="w-3 h-3" />
                </button>
              </div>

              {/* Gap alert */}
              {cashflowGaps.length > 0 && (
                <div className="flex items-center gap-2 mb-3 px-3 py-2 rounded-lg bg-orange-500/10 border border-orange-500/20">
                  <AlertTriangle className="w-4 h-4 text-orange-500 shrink-0" />
                  <p className="text-xs text-orange-600 dark:text-orange-400 font-medium">
                    Gap previsto em {cashflowGaps[0]?.date ?? cashflowGaps[0]?.data ?? 'breve'} — revise sua projeção
                  </p>
                </div>
              )}

              {aiLoading ? (
                <div className="h-[200px] bg-[hsl(var(--muted))] rounded-lg animate-pulse" />
              ) : (
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={displayCashflow} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="cfExpected" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.25} />
                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="cfOptimistic" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#22c55e" stopOpacity={0.2} />
                        <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="cfPessimistic" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#ef4444" stopOpacity={0.2} />
                        <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" strokeOpacity={0.5} />
                    <XAxis
                      dataKey="dia"
                      tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                      tickLine={false}
                      axisLine={false}
                      interval={4}
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                    />
                    <Tooltip content={<CashflowTooltip />} />
                    <Legend
                      iconType="circle"
                      iconSize={8}
                      wrapperStyle={{ fontSize: 11 }}
                    />
                    <Area
                      type="monotone"
                      dataKey="pessimista"
                      name="Pessimista"
                      stroke="#ef4444"
                      strokeWidth={1.5}
                      strokeDasharray="4 4"
                      fill="url(#cfPessimistic)"
                      dot={false}
                    />
                    <Area
                      type="monotone"
                      dataKey="esperado"
                      name="Esperado"
                      stroke="#3b82f6"
                      strokeWidth={2}
                      fill="url(#cfExpected)"
                      dot={false}
                    />
                    <Area
                      type="monotone"
                      dataKey="otimista"
                      name="Otimista"
                      stroke="#22c55e"
                      strokeWidth={1.5}
                      strokeDasharray="4 4"
                      fill="url(#cfOptimistic)"
                      dot={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Margem por Tipo de Serviço */}
          <Card>
            <CardContent className="pt-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-semibold text-[hsl(var(--foreground))]">Margem por Tipo de Serviço</h3>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Margem líquida por categoria de contrato</p>
                </div>
                <button
                  onClick={() => router.push('/modulos/financeiro/custeio')}
                  className="text-xs text-[hsl(var(--primary))] hover:underline flex items-center gap-1 shrink-0"
                >
                  Ver custeio
                  <ArrowRight className="w-3 h-3" />
                </button>
              </div>

              {marginLoading ? (
                <div className="h-[200px] bg-[hsl(var(--muted))] rounded-lg animate-pulse" />
              ) : (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart
                    layout="vertical"
                    data={marginData}
                    margin={{ top: 0, right: 30, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="hsl(var(--border))" strokeOpacity={0.5} />
                    <XAxis
                      type="number"
                      tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(v) => `${v}%`}
                      domain={[0, 50]}
                    />
                    <YAxis
                      type="category"
                      dataKey="label"
                      tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                      tickLine={false}
                      axisLine={false}
                      width={90}
                    />
                    <Tooltip content={<MarginTooltip />} />
                    <Bar dataKey="margem" radius={[0, 4, 4, 0]} barSize={18}>
                      {marginData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.cor} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </div>

        {/* ── Alertas de Risco  |  Ações Pendentes ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">

          {/* Alertas de Risco */}
          <div>
            <h2 className="text-lg font-semibold text-[hsl(var(--foreground))] mb-4">
              Alertas &amp; Pendências
            </h2>
            {(() => {
              const overduePayables = payableStats?.overdue_count ?? 0;
              const overdueReceivables = receivableStats?.overdue_count ?? 0;
              const weekPayables = payableStats?.due_this_week ?? payableStats?.pending_count ?? 0;
              const hasAlerts = overduePayables > 0 || overdueReceivables > 0;

              if (!hasAlerts) {
                return (
                  <div className="flex items-center gap-3 p-4 rounded-xl bg-green-500/10 border border-green-500/20">
                    <CheckCircle className="w-5 h-5 text-green-500 shrink-0" />
                    <div>
                      <p className="text-sm font-semibold text-green-600 dark:text-green-400">Tudo em dia</p>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">Nenhuma pendência financeira no momento</p>
                    </div>
                  </div>
                );
              }

              return (
                <div className="flex flex-col gap-3">
                  {overduePayables > 0 && (
                    <button
                      onClick={() => router.push('/modulos/financeiro/contas-pagar')}
                      className="flex items-center gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/20 hover:bg-red-500/15 transition-colors text-left"
                    >
                      <AlertTriangle className="w-5 h-5 text-red-500 shrink-0" />
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-red-500">{overduePayables} conta{overduePayables !== 1 ? 's' : ''} vencida{overduePayables !== 1 ? 's' : ''}</p>
                        <p className="text-xs text-[hsl(var(--muted-foreground))] truncate">Contas a pagar em atraso</p>
                      </div>
                    </button>
                  )}
                  {overdueReceivables > 0 && (
                    <button
                      onClick={() => router.push('/modulos/financeiro/contas-receber')}
                      className="flex items-center gap-3 p-4 rounded-xl bg-yellow-500/10 border border-yellow-500/20 hover:bg-yellow-500/15 transition-colors text-left"
                    >
                      <AlertTriangle className="w-5 h-5 text-yellow-500 shrink-0" />
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-yellow-600 dark:text-yellow-400">{overdueReceivables} recebimento{overdueReceivables !== 1 ? 's' : ''} em atraso</p>
                        <p className="text-xs text-[hsl(var(--muted-foreground))] truncate">Contas a receber vencidas</p>
                      </div>
                    </button>
                  )}
                  {weekPayables > 0 && (
                    <button
                      onClick={() => router.push('/modulos/financeiro/contas-pagar')}
                      className="flex items-center gap-3 p-4 rounded-xl bg-blue-500/10 border border-blue-500/20 hover:bg-blue-500/15 transition-colors text-left"
                    >
                      <CreditCard className="w-5 h-5 text-blue-500 shrink-0" />
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-blue-500">{weekPayables} pagamento{weekPayables !== 1 ? 's' : ''} esta semana</p>
                        <p className="text-xs text-[hsl(var(--muted-foreground))] truncate">Vencimentos nos próximos 7 dias</p>
                      </div>
                    </button>
                  )}
                </div>
              );
            })()}
          </div>

          {/* Ações Pendentes */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                Ações Pendentes
              </h2>
              <button
                onClick={() => router.push('/modulos/financeiro/contas-pagar')}
                className="text-xs text-[hsl(var(--primary))] hover:underline flex items-center gap-1"
              >
                Ver todas as ações
                <ArrowRight className="w-3 h-3" />
              </button>
            </div>

            {pendingLoading ? (
              <div className="flex flex-col gap-2">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="h-14 bg-[hsl(var(--muted))] rounded-xl animate-pulse" />
                ))}
              </div>
            ) : pendingPayables.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 rounded-xl border border-dashed border-[hsl(var(--border))] bg-[hsl(var(--muted))]/30">
                <CheckCircle className="w-8 h-8 text-green-500 mb-2" />
                <p className="text-sm font-medium text-[hsl(var(--foreground))]">Nenhuma ação pendente</p>
                <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">Todas as contas estão em dia</p>
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                {pendingPayables.map((item: any, idx: number) => (
                  <div
                    key={item.id ?? idx}
                    className="flex items-center gap-3 p-3 rounded-xl bg-[hsl(var(--card))] border border-[hsl(var(--border))] hover:border-[hsl(var(--primary))]/30 transition-colors"
                  >
                    <div className="w-8 h-8 rounded-lg bg-orange-500/10 flex items-center justify-center shrink-0">
                      <Receipt className="w-4 h-4 text-orange-500" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-[hsl(var(--foreground))] truncate">
                        {item.description ?? item.descricao ?? item.nome ?? `Conta #${item.id}`}
                      </p>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">
                        Vence: {item.due_date ?? item.vencimento ?? '—'}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-sm font-semibold text-[hsl(var(--foreground))]">
                        {formatCurrency(item.amount ?? item.valor ?? 0)}
                      </span>
                      <button
                        onClick={() => router.push(`/modulos/financeiro/contas-pagar`)}
                        className="flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-md bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))] hover:bg-[hsl(var(--primary))]/20 transition-colors"
                      >
                        <Eye className="w-3 h-3" />
                        Ver
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── Contas Bancárias Integradas ── */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-[hsl(var(--foreground))]">
              Contas Bancárias
            </h2>
            <div className="flex items-center gap-2">
              {lastBankSync && (
                <span className="text-xs text-[hsl(var(--muted-foreground))]">
                  Atualizado às {lastBankSync}
                </span>
              )}
              <button
                onClick={loadBankData}
                disabled={bankLoading}
                className="p-1.5 rounded-md hover:bg-[hsl(var(--muted))] transition-colors"
              >
                <RefreshCw className={`w-4 h-4 text-[hsl(var(--muted-foreground))] ${bankLoading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {bankLoading ? (
              <>
                <Card><CardContent className="pt-4"><div className="h-16 bg-[hsl(var(--muted))] rounded animate-pulse" /></CardContent></Card>
                <Card><CardContent className="pt-4"><div className="h-16 bg-[hsl(var(--muted))] rounded animate-pulse" /></CardContent></Card>
              </>
            ) : bankBalances.length > 0 ? bankBalances.map((bank) => {
              const status = getBankStatusInfo(bank.bank_code);
              const isConnected = status?.connected ?? false;
              return (
                <Card key={bank.bank_code} className="border-l-4" style={{ borderLeftColor: '#00a859' }}>
                  <CardContent className="pt-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
                        style={{ backgroundColor: '#00a85915' }}>
                        <Building2 className="w-5 h-5" style={{ color: '#00a859' }} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 mb-0.5">
                          <span className="text-sm font-semibold text-[hsl(var(--foreground))]">{bank.bank_name}</span>
                          {isConnected ? (
                            <Wifi className="w-3 h-3 text-green-500" />
                          ) : (
                            <WifiOff className="w-3 h-3 text-red-400" />
                          )}
                        </div>
                        <p className="text-xs text-[hsl(var(--muted-foreground))] mb-2">
                          Conta: {bank.account}
                        </p>
                        <p className="font-data text-2xl font-semibold tabular-nums" style={{ color: '#00a859' }}>
                          {formatCurrency(bank.available_balance)}
                        </p>
                        {bank.blocked_balance > 0 && (
                          <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">
                            Bloqueado: {formatCurrency(bank.blocked_balance)}
                          </p>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            }) : (
              <div className="col-span-2 p-4 rounded-xl bg-[hsl(var(--muted))]/50 border border-[hsl(var(--border))] flex items-center gap-3">
                <WifiOff className="w-5 h-5 text-[hsl(var(--muted-foreground))] shrink-0" />
                <div>
                  <p className="text-sm font-medium text-[hsl(var(--foreground))]">Contas bancárias não conectadas</p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Configure a integração com o Banco Inter em Configurações &gt; Integrações</p>
                </div>
              </div>
            )}
          </div>
          {bankBalances.length > 1 && (
            <div className="mt-3 p-3 rounded-lg bg-[hsl(var(--muted))]/50 flex items-center justify-between">
              <span className="text-sm text-[hsl(var(--muted-foreground))]">Saldo total consolidado</span>
              <span className="text-lg font-bold text-[hsl(var(--foreground))]">
                {formatCurrency(bankBalances.reduce((sum, b) => sum + b.available_balance, 0))}
              </span>
            </div>
          )}
        </div>

        {/* ── Financial Advisor ── */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center">
                <MessageCircle className="w-4 h-4 text-indigo-500" />
              </div>
              <h2 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                Financial Advisor
              </h2>
            </div>
            {!advisorRecsLoaded && (
              <button
                onClick={loadAdvisorRecommendations}
                disabled={advisorLoading}
                className="text-xs text-indigo-500 hover:underline flex items-center gap-1"
              >
                {advisorLoading ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Lightbulb className="w-3 h-3" />}
                Carregar recomendações
              </button>
            )}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Recomendações */}
            <div>
              <p className="text-xs text-[hsl(var(--muted-foreground))] mb-2">Recomendações prioritárias</p>
              {advisorLoading ? (
                <div className="space-y-2">
                  {[1,2,3].map(i => <div key={i} className="h-14 bg-[hsl(var(--muted))] rounded-xl animate-pulse" />)}
                </div>
              ) : advisorRecommendations.length > 0 ? (
                <div className="space-y-2">
                  {advisorRecommendations.map((rec: any, idx: number) => (
                    <div key={idx} className={`flex items-start gap-3 p-3 rounded-xl border ${
                      rec.prioridade === 1 ? 'bg-red-500/5 border-red-200' :
                      rec.prioridade === 2 ? 'bg-yellow-500/5 border-yellow-200' :
                      'bg-blue-500/5 border-blue-100'
                    }`}>
                      <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0 mt-0.5 ${
                        rec.prioridade === 1 ? 'bg-red-100 text-red-600' :
                        rec.prioridade === 2 ? 'bg-yellow-100 text-yellow-600' :
                        'bg-blue-100 text-blue-600'
                      }`}>{rec.prioridade}</div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-[hsl(var(--foreground))] leading-tight">{rec.titulo}</p>
                        <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5 line-clamp-2">{rec.descricao}</p>
                        {rec.prazo_sugerido && (
                          <span className="text-xs text-indigo-500 mt-1 inline-block">{rec.prazo_sugerido}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-4 rounded-xl bg-[hsl(var(--muted))]/30 border border-dashed border-[hsl(var(--border))] text-center">
                  <Lightbulb className="w-6 h-6 text-[hsl(var(--muted-foreground))] mx-auto mb-2" />
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Clique em "Carregar recomendações" para ver sugestões da IA</p>
                </div>
              )}
            </div>

            {/* Chat */}
            <div>
              <p className="text-xs text-[hsl(var(--muted-foreground))] mb-2">Pergunte ao Financial Advisor</p>
              <div className="border border-[hsl(var(--border))] rounded-xl overflow-hidden bg-[hsl(var(--card))]">
                {/* Mensagens */}
                <div className="h-44 overflow-y-auto p-3 space-y-2">
                  {chatMessages.length === 0 && (
                    <div className="text-center py-4">
                      <Brain className="w-6 h-6 text-[hsl(var(--muted-foreground))] mx-auto mb-1" />
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">Faça uma pergunta financeira</p>
                      <div className="flex flex-wrap gap-1 justify-center mt-2">
                        {['Qual minha margem atual?','Tenho inadimplência?','Como melhorar o fluxo?'].map(q => (
                          <button type="button" key={q} onClick={() => setChatInput(q)} className="text-xs px-2 py-1 rounded-full bg-indigo-50 text-indigo-600 hover:bg-indigo-100 border border-indigo-200">{q}</button>
                        ))}
                      </div>
                    </div>
                  )}
                  {chatMessages.map((msg, i) => (
                    <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[85%] px-3 py-2 rounded-xl text-xs leading-relaxed ${
                        msg.role === 'user'
                          ? 'bg-indigo-600 text-white rounded-br-sm'
                          : 'bg-[hsl(var(--muted))] text-[hsl(var(--foreground))] rounded-bl-sm'
                      }`}>
                        {msg.text}
                      </div>
                    </div>
                  ))}
                  {chatLoading && (
                    <div className="flex justify-start">
                      <div className="bg-[hsl(var(--muted))] px-3 py-2 rounded-xl rounded-bl-sm text-xs text-[hsl(var(--muted-foreground))]">
                        <RefreshCw className="w-3 h-3 animate-spin inline mr-1" />Analisando...
                      </div>
                    </div>
                  )}
                </div>
                {/* Input */}
                <div className="border-t border-[hsl(var(--border))] p-2 flex gap-2">
                  <input
                    type="text"
                    value={chatInput}
                    onChange={e => setChatInput(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && sendAdvisorMessage()}
                    placeholder="Pergunte algo sobre suas finanças..."
                    className="flex-1 text-xs px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] focus:ring-1 focus:ring-indigo-400 focus:outline-none"
                  />
                  <button
                    onClick={sendAdvisorMessage}
                    disabled={chatLoading || !chatInput.trim()}
                    className="p-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 transition-colors"
                  >
                    <Send className="w-3 h-3" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ── Navigation Cards ── */}
        <div>
          <h2 className="text-lg font-semibold text-[hsl(var(--foreground))] mb-4">
            Módulos Financeiros
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {navigationCards.map((card) => {
              const Icon = card.icon;
              return (
                <Card
                  key={card.href}
                  variant="interactive"
                  className="group"
                  onClick={() => router.push(card.href)}
                >
                  <CardContent className="pt-4">
                    <div className="flex flex-col gap-3">
                      <div className="flex items-center justify-between">
                        <div className="w-10 h-10 rounded-lg bg-[hsl(var(--primary))]/10 flex items-center justify-center">
                          <Icon className="w-5 h-5 text-[hsl(var(--primary))]" />
                        </div>
                        <ArrowRight className="w-4 h-4 text-[hsl(var(--muted-foreground))] transition-transform group-hover:translate-x-1" />
                      </div>
                      <div>
                        <h3 className="text-sm font-semibold text-[hsl(var(--foreground))]">
                          {card.title}
                        </h3>
                        <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1 line-clamp-2">
                          {card.description}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      </main>
    </div>
  );
}
