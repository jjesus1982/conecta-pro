'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  DollarSign, TrendingUp, Users, Receipt, FileText, Building2,
  RefreshCw, Calendar, ArrowUpRight, ArrowDownRight,
  Landmark, CheckCircle2, Clock, AlertTriangle,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend,
} from 'recharts';
import { api } from '@/lib/api';

// ─── Types ───────────────────────────────────────────────────────────────────

interface DashboardTotais {
  nfse_emitidas: number;
  clientes_ativos: number;
  faturamento_bruto: number;
  iss_total: number;
  ticket_medio: number;
}

interface DashboardMes {
  competencia: string;
  nfse_emitidas: number;
  faturamento_bruto: number;
  iss_total: number;
  faturamento_liquido: number;
}

interface DashboardCliente {
  cliente: string;
  cnpj: string;
  nfse_emitidas: number;
  total_bruto: number;
  total_iss: number;
}

interface DashboardServico {
  servico: string;
  quantidade: number;
  total: number;
}

interface NfseDashboardData {
  totais: DashboardTotais;
  por_mes: DashboardMes[];
  por_cliente: DashboardCliente[];
  por_servico: DashboardServico[];
}

interface DreDashboardData {
  dre: {
    receita_bruta: number;
    receita_liquida: number;
    resultado_liquido: number;
    total_despesas: number;
    despesa_folha: number;
  };
  contas_a_pagar: { total: number; valor: number; vencidas: number };
  contas_a_receber: { total: number; valor: number; vencidas: number };
  alertas: Array<{ tipo: string; mensagem: string; nivel: string }>;
}

interface NfseItem {
  id: string;
  numero_nfse: string;
  numero_rps: number;
  status: string;
  data_emissao: string;
  data_competencia: string;
  tomador_razao_social: string;
  tomador_cpf_cnpj: string;
  descricao_servico: string;
  valor_servicos: number;
  iss_aliquota: number;
  iss_valor: number;
  iss_retido: boolean;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const fmt = (v: number | undefined | null) => {
  if (v == null) return 'R$ 0,00';
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
};

const fmtCompact = (v: number) => {
  if (v >= 1000) return `R$ ${(v / 1000).toFixed(1)}k`;
  return fmt(v);
};

const fmtCnpj = (cnpj: string) => {
  const c = cnpj.replace(/\D/g, '').padStart(14, '0');
  return `${c.slice(0,2)}.${c.slice(2,5)}.${c.slice(5,8)}/${c.slice(8,12)}-${c.slice(12)}`;
};

const shortName = (name: string) =>
  name.replace(/^CONDOMINIO\s+(RESIDENCIAL\s+)?/i, '')
      .replace(/^RESIDENCIAL\s+/i, '')
      .replace(/^DO\s+EDIFICIO\s+/i, 'Ed. ');

const COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
  '#06b6d4', '#f97316', '#ec4899', '#14b8a6', '#6366f1', '#84cc16',
];

const PIE_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#f97316', '#ec4899'];

// ─── Custom Tooltips ─────────────────────────────────────────────────────────

function BarTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg p-3 shadow-lg text-xs">
      <p className="font-semibold text-[hsl(var(--foreground))] mb-1">{d.name}</p>
      <p className="text-emerald-400">Faturamento: {fmt(d.valor)}</p>
      <p className="text-slate-400">NFS-e: {d.nfse}</p>
    </div>
  );
}

function PieTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0];
  return (
    <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg p-3 shadow-lg text-xs">
      <p className="font-semibold text-[hsl(var(--foreground))] mb-1">{d.name}</p>
      <p className="text-emerald-400">{fmt(d.value)}</p>
      <p className="text-slate-400">{d.payload.pct}%</p>
    </div>
  );
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function DashboardFinanceiroPage() {
  const [data, setData] = useState<NfseDashboardData | null>(null);
  const [nfseList, setNfseList] = useState<NfseItem[]>([]);
  const [bankBalance, setBankBalance] = useState<{total: number; banks: Array<{name: string; balance: number}>}>({total: 0, banks: []});
  const [loading, setLoading] = useState(true);
  const [periodo, setPeriodo] = useState('todos');
  const [lastUpdate, setLastUpdate] = useState<string>('');
  const [extrato, setExtrato] = useState<Record<string, unknown>[]>([]);
  const [extratoLoading, setExtratoLoading] = useState(false);
  const [dreData, setDreData] = useState<DreDashboardData | null>(null);
  const [justifData, setJustifData] = useState<{ total: number; valor_total: number } | null>(null);
  const [mrrPreviewData, setMrrPreviewData] = useState<{ total_mrr: number; total_clientes: number } | null>(null);

  const loadExtrato = useCallback(async () => {
    setExtratoLoading(true);
    try {
      const r = await api.get('/api/v1/integrations/banking/statement/full');
      setExtrato((r.data.transactions || r.data.items || []).slice(0, 5));
    } catch { } finally {
      setExtratoLoading(false);
    }
  }, []);


  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const now = new Date();
      const mes = now.getMonth() + 1;
      const ano = now.getFullYear();
      const [dashRes, nfseRes, bankRes, dreRes, justifRes, mrrPreviewRes] = await Promise.all([
        api.get('/api/v1/financial/nfse/dashboard'),
        api.get('/api/v1/financial/nfse', { params: { page_size: 50 } }),
        api.get('/api/v1/integrations/banking/balances').catch(() => ({ data: { total_balance: 0, balances: [] } })),
        api.get('/api/v1/fiscal-dashboard/atual').catch(() => ({ data: {} })),
        api.get('/api/v1/justificativa/pendentes').catch(() => ({ data: { total: 0, valor_total: 0 } })),
        api.get(`/api/v1/financial/billing/cobrar-recorrente/${mes}/${ano}/preview`).catch(() => ({ data: {} })),
      ]);
      setData(dashRes.data);
      setNfseList(nfseRes.data.items ?? []);
      const balances = bankRes.data?.balances ?? [];
      setBankBalance({
        total: bankRes.data?.total_balance ?? 0,
        banks: balances.map((b: Record<string, unknown>) => ({ name: String(b.bank_name ?? ''), balance: Number(b.balance ?? 0) })),
      });
      if (dreRes.data?.dre) setDreData(dreRes.data);
      if (justifRes.data?.total !== undefined) setJustifData(justifRes.data);
      if (mrrPreviewRes.data?.total_mrr !== undefined) setMrrPreviewData(mrrPreviewRes.data);
      setLastUpdate(new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }));
    } catch (err) {
      console.error('Erro ao carregar dashboard financeiro:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); loadExtrato(); }, [loadData, loadExtrato]);

  if (loading || !data) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <RefreshCw className="h-8 w-8 animate-spin text-emerald-500" />
      </div>
    );
  }

  // ── Derived data ──

  const { totais, por_cliente, por_servico, por_mes } = data;

  // Faturamento recorrente mensal (média)
  const mrrTotal = por_mes.length > 0
    ? por_mes.reduce((s, m) => s + m.faturamento_bruto, 0) / por_mes.length
    : 0;

  // Filter by período
  const filteredMes = periodo === 'todos'
    ? por_mes
    : por_mes.filter(m => m.competencia === periodo);

  const filteredBruto = filteredMes.reduce((s, m) => s + m.faturamento_bruto, 0);
  const filteredIss = filteredMes.reduce((s, m) => s + m.iss_total, 0);
  const filteredLiquido = filteredMes.reduce((s, m) => s + m.faturamento_liquido, 0);
  const filteredNfse = filteredMes.reduce((s, m) => s + m.nfse_emitidas, 0);

  // Bar chart data (por cliente, sorted desc)
  const barData = [...por_cliente]
    .sort((a, b) => b.total_bruto - a.total_bruto)
    .map(c => ({
      name: shortName(c.cliente),
      fullName: c.cliente,
      valor: periodo === 'todos' ? c.total_bruto : c.total_bruto / (por_mes.length || 1),
      nfse: c.nfse_emitidas,
      cnpj: c.cnpj,
    }));

  // Pie chart data (por serviço)
  const totalServicos = por_servico.reduce((s, sv) => s + sv.total, 0);
  const pieData = por_servico
    .sort((a, b) => b.total - a.total)
    .map(sv => ({
      name: sv.servico.length > 30 ? sv.servico.slice(0, 28) + '...' : sv.servico,
      fullName: sv.servico,
      value: sv.total,
      pct: ((sv.total / totalServicos) * 100).toFixed(1),
      qtd: sv.quantidade,
    }));

  // NFS-e list filtered
  const filteredNfseList = periodo === 'todos'
    ? nfseList
    : nfseList.filter(n => n.data_competencia.startsWith(periodo));

  // Variação mês a mês
  const sortedMeses = [...por_mes].sort((a, b) => a.competencia.localeCompare(b.competencia));
  const mesAtual = sortedMeses.length >= 1 ? sortedMeses[sortedMeses.length - 1] : null;
  const mesAnterior = sortedMeses.length >= 2 ? sortedMeses[sortedMeses.length - 2] : null;
  const variacaoMes = mesAtual && mesAnterior && mesAnterior.faturamento_bruto > 0
    ? ((mesAtual.faturamento_bruto - mesAnterior.faturamento_bruto) / mesAnterior.faturamento_bruto) * 100
    : 0;

  return (
    <div className="space-y-6 p-1">
      {/* ── Header ── */}
      <PageHeader
        eyebrow="FINANCEIRO"
        title="Dashboard Financeiro"
        subtitle="Dados reais das NFS-e — CONECTAMAIS ELETRONICA LTDA"
        icon={<DollarSign className="w-5 h-5" />}
        actions={
          <>
            <Select value={periodo} onValueChange={setPeriodo} aria-label="Periodo">
              <SelectTrigger className="w-[180px]">
                <Calendar className="h-4 w-4 mr-2" />
                <SelectValue placeholder="Período" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os meses</SelectItem>
                {sortedMeses.map(m => (
                  <SelectItem key={m.competencia} value={m.competencia}>
                    {new Date(m.competencia + '-01').toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="outline" size="sm" onClick={loadData} disabled={loading}>
              <RefreshCw className={`h-4 w-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
              Atualizar
            </Button>
            {lastUpdate && (
              <span className="text-xs text-[hsl(var(--muted-foreground))]">
                {lastUpdate}
              </span>
            )}
          </>
        }
      />

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={<DollarSign className="w-4 h-4" />}
          color="#10b981"
          label="Faturamento Bruto"
          value={fmt(filteredBruto)}
          sub={`${filteredNfse} NFS-e emitidas`}
          change={variacaoMes !== 0 && periodo === 'todos' ? Number(variacaoMes.toFixed(1)) : undefined}
        />

        <StatCard
          icon={<TrendingUp className="w-4 h-4" />}
          color="#3b82f6"
          label="Faturamento Líquido"
          value={fmt(filteredLiquido)}
          sub="Após retenção ISS"
        />

        <StatCard
          icon={<Receipt className="w-4 h-4" />}
          color="#f59e0b"
          label="ISS Retido"
          value={fmt(filteredIss)}
          sub="Alíquota 5%"
        />

        <StatCard
          icon={<Users className="w-4 h-4" />}
          color="#8b5cf6"
          label="Ticket Médio"
          value={fmt(mrrTotal / (totais.clientes_ativos || 1))}
          sub={`${totais.clientes_ativos} clientes ativos`}
        />
      </div>

      {/* ── Alerta Lucro Real — Saídas sem justificativa ── */}
      {justifData && justifData.total > 0 && (
        <div className="bg-orange-50 dark:bg-orange-950/30 border border-orange-200 dark:border-orange-800 rounded-xl p-4 flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-orange-800 dark:text-orange-300 flex items-center gap-1.5">
              <AlertTriangle className="h-4 w-4 text-orange-600 dark:text-orange-400" />
              Saídas sem justificativa fiscal (Lucro Real)
            </p>
            <p className="font-data text-2xl font-semibold tabular-nums text-orange-600 dark:text-orange-400 mt-0.5">
              {justifData.total} transações pendentes
            </p>
            <p className="text-xs text-orange-600 dark:text-orange-400 mt-0.5">
              {fmt(justifData.valor_total)} sem documentação obrigatória
            </p>
          </div>
          <a
            href="/modulos/financeiro/conciliacao"
            className="text-sm text-orange-700 dark:text-orange-300 font-medium hover:underline whitespace-nowrap ml-4"
          >
            Resolver →
          </a>
        </div>
      )}

      {/* ── Saldo Bancario ── */}
      {bankBalance.total > 0 && (
        <Card className="bg-gradient-to-r from-blue-500/5 to-cyan-500/5 border-blue-500/20">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-[hsl(var(--muted-foreground))]">
                  Saldo Bancario Consolidado
                </p>
                <p className="font-data text-2xl font-semibold tabular-nums text-blue-500 mt-1">{fmt(bankBalance.total)}</p>
                <div className="flex gap-4 mt-1">
                  {bankBalance.banks.map((b) => (
                    <span key={b.name} className="text-xs text-[hsl(var(--muted-foreground))]">
                      {b.name}: {fmt(b.balance)}
                    </span>
                  ))}
                </div>
              </div>
              <div className="rounded-full bg-blue-500/10 p-3">
                <DollarSign className="h-6 w-6 text-blue-500" />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── DRE Real + Contas ── */}
      {dreData && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Card className="border-l-4 border-l-red-400">
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide">
                    Contas a Pagar
                  </p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-red-500 mt-1">{fmt(dreData.contas_a_pagar.valor)}</p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">
                    {dreData.contas_a_pagar.total} contas · {dreData.contas_a_pagar.vencidas} vencidas
                  </p>
                </div>
                <div className="rounded-full bg-red-500/10 p-3">
                  <ArrowDownRight className="h-6 w-6 text-red-500" />
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-emerald-400">
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide">
                    Contas a Receber
                  </p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-emerald-500 mt-1">{fmt(dreData.contas_a_receber.valor)}</p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">
                    {dreData.contas_a_receber.total} contas · {dreData.contas_a_receber.vencidas} vencidas
                  </p>
                </div>
                <div className="rounded-full bg-emerald-500/10 p-3">
                  <ArrowUpRight className="h-6 w-6 text-emerald-500" />
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className={`border-l-4 ${dreData.dre.resultado_liquido >= 0 ? 'border-l-blue-400' : 'border-l-red-400'}`}>
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide">
                    Resultado DRE (mês)
                  </p>
                  <p className={`font-data text-2xl font-semibold tabular-nums mt-1 ${dreData.dre.resultado_liquido >= 0 ? 'text-blue-500' : 'text-red-500'}`}>
                    {fmt(dreData.dre.resultado_liquido)}
                  </p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">
                    Despesas: {fmt(dreData.dre.total_despesas)}
                  </p>
                </div>
                <div className={`rounded-full p-3 ${dreData.dre.resultado_liquido >= 0 ? 'bg-blue-500/10' : 'bg-red-500/10'}`}>
                  <TrendingUp className={`h-6 w-6 ${dreData.dre.resultado_liquido >= 0 ? 'text-blue-500' : 'text-red-500'}`} />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── MRR Card ── */}
      <Card className="bg-gradient-to-r from-emerald-500/5 to-blue-500/5 border-emerald-500/20">
        <CardContent className="pt-4 pb-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-[hsl(var(--muted-foreground))]">
                Faturamento Mensal Recorrente (MRR)
              </p>
              <p className="font-data text-2xl font-semibold tabular-nums text-emerald-500 mt-1">
                {fmt(mrrPreviewData?.total_mrr ?? mrrTotal)}
              </p>
              <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
                {mrrPreviewData
                  ? `${mrrPreviewData.total_clientes} clientes ativos com contrato`
                  : `Baseado na média de ${por_mes.length} meses com NFS-e emitidas`}
              </p>
            </div>
            <div className="text-right">
              <p className="text-sm text-[hsl(var(--muted-foreground))]">Projeção Anual</p>
              <p className="text-xl font-bold text-[hsl(var(--foreground))]">
                {fmt((mrrPreviewData?.total_mrr ?? mrrTotal) * 12)}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Charts Row ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Bar Chart - Faturamento por Cliente */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Building2 className="h-4 w-4 text-blue-500" />
              Faturamento por Cliente
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[380px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={barData}
                  layout="vertical"
                  margin={{ top: 5, right: 30, left: 10, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                  <XAxis
                    type="number"
                    tickFormatter={fmtCompact}
                    tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={130}
                    tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                  />
                  <Tooltip content={<BarTooltip />} />
                  <Bar dataKey="valor" radius={[0, 4, 4, 0]} maxBarSize={24}>
                    {barData.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Pie Chart - Composição de Receita */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Receipt className="h-4 w-4 text-amber-500" />
              Receita por Serviço
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[380px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="45%"
                    innerRadius={55}
                    outerRadius={90}
                    paddingAngle={2}
                    dataKey="value"
                    nameKey="name"
                    label={({ percent }: any) => `${((percent ?? 0) * 100).toFixed(1)}%`}
                  >
                    {pieData.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip content={<PieTooltip />} />
                  <Legend
                    layout="vertical"
                    align="center"
                    verticalAlign="bottom"
                    wrapperStyle={{ fontSize: '10px', paddingTop: '8px' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Evolução Mensal ── */}
      {sortedMeses.length > 1 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-emerald-500" />
              Evolução Mensal
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {sortedMeses.map((m, i) => (
                <div key={m.competencia} className="rounded-lg border border-[hsl(var(--border))] p-4">
                  <p className="text-sm font-medium text-[hsl(var(--muted-foreground))] capitalize">
                    {new Date(m.competencia + '-01').toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })}
                  </p>
                  <p className="text-xl font-bold text-[hsl(var(--foreground))] mt-1">{fmt(m.faturamento_bruto)}</p>
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-xs text-[hsl(var(--muted-foreground))]">
                      {m.nfse_emitidas} NFS-e
                    </span>
                    <span className="text-xs text-amber-500">
                      ISS: {fmt(m.iss_total)}
                    </span>
                  </div>
                  <div className="mt-1">
                    <span className="text-xs text-blue-500">
                      Líquido: {fmt(m.faturamento_liquido)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Tabela de NFS-e ── */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <FileText className="h-4 w-4 text-blue-500" />
              Notas Fiscais de Serviço (NFS-e)
            </CardTitle>
            <Badge variant="outline" className="text-xs">
              {filteredNfseList.length} notas
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[60px]">RPS</TableHead>
                  <TableHead>Tomador</TableHead>
                  <TableHead className="w-[140px]">CNPJ</TableHead>
                  <TableHead className="w-[100px]">Competência</TableHead>
                  <TableHead className="text-right w-[120px]">Valor Bruto</TableHead>
                  <TableHead className="text-right w-[100px]">ISS (5%)</TableHead>
                  <TableHead className="text-right w-[120px]">Valor Líquido</TableHead>
                  <TableHead className="w-[90px]">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredNfseList
                  .sort((a, b) => b.valor_servicos - a.valor_servicos)
                  .map(nf => (
                  <TableRow key={nf.id}>
                    <TableCell className="font-mono text-xs">{nf.numero_rps}</TableCell>
                    <TableCell className="text-sm font-medium max-w-[200px] truncate" title={nf.tomador_razao_social}>
                      {shortName(nf.tomador_razao_social)}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{fmtCnpj(nf.tomador_cpf_cnpj)}</TableCell>
                    <TableCell className="text-xs">
                      {new Date(nf.data_competencia).toLocaleDateString('pt-BR', { month: 'short', year: 'numeric' })}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">{fmt(nf.valor_servicos)}</TableCell>
                    <TableCell className="text-right font-mono text-xs text-amber-500">{fmt(nf.iss_valor)}</TableCell>
                    <TableCell className="text-right font-mono text-sm text-emerald-500">
                      {fmt(nf.valor_servicos - nf.iss_valor)}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={nf.status === 'autorizada' ? 'default' : 'secondary'}
                        className={`text-[10px] ${nf.status === 'autorizada' ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/30' : ''}`}
                      >
                        {nf.status}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* ── Indicadores Fiscais ── */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Receipt className="h-4 w-4 text-amber-500" />
            Indicadores Fiscais
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="rounded-lg border border-[hsl(var(--border))] p-4 text-center">
              <p className="text-xs text-[hsl(var(--muted-foreground))] uppercase">ISS Total</p>
              <p className="text-xl font-bold text-amber-500 mt-1">{fmt(totais.iss_total)}</p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Alíquota 5%</p>
            </div>
            <div className="rounded-lg border border-[hsl(var(--border))] p-4 text-center">
              <p className="text-xs text-[hsl(var(--muted-foreground))] uppercase">PIS/COFINS</p>
              <p className="text-xl font-bold text-emerald-500 mt-1">R$ 0,00</p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Liminar ativa</p>
            </div>
            <div className="rounded-lg border border-[hsl(var(--border))] p-4 text-center">
              <p className="text-xs text-[hsl(var(--muted-foreground))] uppercase">INSS Retido</p>
              <p className="text-xl font-bold text-emerald-500 mt-1">R$ 0,00</p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Liminar pendente</p>
            </div>
            <div className="rounded-lg border border-[hsl(var(--border))] p-4 text-center">
              <p className="text-xs text-[hsl(var(--muted-foreground))] uppercase">Carga Tributária</p>
              <p className="text-xl font-bold text-blue-500 mt-1">
                {((totais.iss_total / totais.faturamento_bruto) * 100).toFixed(1)}%
              </p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Sobre faturamento</p>
            </div>
          </div>
        </CardContent>
      </Card>
      {/* Últimas transações Inter */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Landmark className="h-4 w-4 text-green-500" />
              Últimas transações — Banco Inter
            </span>
            <a
              href="/modulos/financeiro/banking"
              className="text-xs text-blue-500 hover:underline font-normal"
            >
              Ver extrato completo →
            </a>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {extratoLoading ? (
            <p className="text-xs text-[hsl(var(--muted-foreground))]">Carregando...</p>
          ) : extrato.length > 0 ? (
            <div className="space-y-2">
              {extrato.map((tx, i) => {
                const isCredit = ['credit', 'credito', 'CREDITO', 'PIX_RECEBIDO'].includes(
                  String(tx.transaction_type || ''))
                return (
                  <div key={i}
                    className="flex items-center justify-between py-1.5 border-b border-[hsl(var(--border))] last:border-0">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-[hsl(var(--foreground))] truncate">
                        {String(tx.description || '')}
                      </p>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">
                        {new Date(String(tx.transaction_date || '')).toLocaleDateString('pt-BR')}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 ml-2">
                      {tx.reconciliado ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                      ) : (
                        <Clock className="w-3.5 h-3.5 text-amber-500" />
                      )}
                      <span className={`text-sm font-medium ${
                        isCredit ? 'text-emerald-500' : 'text-red-500'}`}>
                        {isCredit ? '+' : '-'}
                        {Number(tx.amount || 0).toLocaleString('pt-BR', {
                          style: 'currency', currency: 'BRL'
                        })}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-xs text-[hsl(var(--muted-foreground))]">
              Nenhuma transação recente
            </p>
          )}
        </CardContent>
      </Card>

    </div>
  );
}
