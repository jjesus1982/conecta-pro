'use client';

import {
  Receipt, Search, RefreshCw, Plus, MoreHorizontal, Eye, Edit, Trash2,
  ArrowLeft, DollarSign, Clock, CheckCircle, AlertCircle, Calendar,
  BarChart2, Calculator, List, Zap, TrendingUp, TrendingDown,
} from 'lucide-react';
import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { ConfirmModal } from '@/components/ui/modal';
import { BillingRuleFormModal } from '@/components/financeiro/billing-rule-form-modal';
import {
  useBillingRules,
  useCreateBillingRule,
  useUpdateBillingRule,
  useDeleteBillingRule,
  useActivateBillingRule,
  usePauseBillingRule,
} from '@/hooks/financial/useFinancial';
import type { BillingRuleResponse } from '@/types/generated/financial/models/billingRuleResponse';
import type { BillingRuleCreate } from '@/types/generated/financial/models/billingRuleCreate';
import { bankingApi } from '@/services/banking/bankingService';
import { useCondominio } from '@/contexts/CondominioContext';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';

// ─── helpers ──────────────────────────────────────────────────────────────────

const formatCurrency = (value: number | undefined | null) => {
  if (value == null) return 'R$ 0,00';
  return value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
};

const getTypeColor = (type: string) => {
  switch (type) {
    case 'fixed':      return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
    case 'variable':   return 'bg-orange-500/10 text-orange-500 border-orange-500/20';
    case 'percentage': return 'bg-purple-500/10 text-purple-500 border-purple-500/20';
    default:           return 'bg-gray-500/10 text-gray-500 border-gray-500/20';
  }
};

const TYPE_LABELS: Record<string, string> = { fixed: 'Fixo', variable: 'Variavel', percentage: 'Percentual' };
const FREQUENCY_LABELS: Record<string, string> = { monthly: 'Mensal', quarterly: 'Trimestral', annual: 'Anual' };

const TIPO_OPTIONS = [
  { value: 'portaria', label: 'Portaria / Vigilância' },
  { value: 'limpeza', label: 'Limpeza e Conservação' },
  { value: 'jardinagem', label: 'Jardinagem' },
  { value: 'seguranca_eletronica', label: 'Segurança Eletrônica' },
  { value: 'portaria_remota', label: 'Portaria Remota' },
];

const CHART_COLORS: Record<string, string> = {
  pago: '#10b981',
  pendente: '#f59e0b',
  vencido: '#ef4444',
  faturado: '#3b82f6',
};

const toYYYYMM = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;

// ─── types ────────────────────────────────────────────────────────────────────

interface BillingSummary {
  mes: string;
  total_faturado: number;
  total_pendente: number;
  total_vencido: number;
  total_pago: number;
  qtd_faturas: number;
  qtd_clientes: number;
  ticket_medio: number;
}

interface ContractItem {
  customer_id: string | null;
  customer_name: string;
  valor_total: number;
  qtd_titulos: number;
  vencimento_medio: string | null;
  status: string;
}

interface MedicaoResult {
  tipo: string;
  tipo_label: string;
  contrato_descricao: string;
  periodo_dias: number;
  valor_base: number;
  adicional_he: number;
  adicional_noturno: number;
  deducoes: number;
  valor_total: number;
  detalhamento: {
    custo_diario: number;
    he_percentual: number;
    noturno_percentual: number;
  };
}

interface BillingPreview {
  contratos_a_faturar: ContractItem[];
  valor_estimado: number;
  qtd_contratos: number;
  observacoes: string[];
}

// ─── Tab component ────────────────────────────────────────────────────────────

interface TabProps {
  id: string;
  label: string;
  icon: React.ReactNode;
  active: boolean;
  onClick: () => void;
}
const Tab = ({ label, icon, active, onClick }: TabProps) => (
  <button
    onClick={onClick}
    className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
      active
        ? 'border-blue-500 text-blue-500'
        : 'border-transparent text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
    }`}
  >
    {icon}
    {label}
  </button>
);

// ─── KPI Card ─────────────────────────────────────────────────────────────────

interface KPICardProps {
  label: string;
  value: string;
  icon: React.ReactNode;
  color: string;
}
const KPICard = ({ label, value, icon, color }: KPICardProps) => (
  <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
    <div className="flex items-center gap-3">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
        {icon}
      </div>
      <div>
        <p className="text-lg font-bold text-[hsl(var(--foreground))] truncate">{value}</p>
        <p className="text-xs text-[hsl(var(--muted-foreground))]">{label}</p>
      </div>
    </div>
  </div>
);

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function FaturamentoPage() {
  const { condominioId } = useCondominio();
  const [activeTab, setActiveTab] = useState<'visao-geral' | 'contratos' | 'medicao' | 'historico'>('visao-geral');

  // ── Tab 1 – Visão Geral state
  const [summary, setSummary] = useState<BillingSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  // ── Tab 2 – Contratos state
  const [mesSelecionado, setMesSelecionado] = useState(toYYYYMM(new Date()));
  const [contracts, setContracts] = useState<ContractItem[]>([]);
  const [contractsLoading, setContractsLoading] = useState(false);
  const [preview, setPreview] = useState<BillingPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // ── Tab 3 – Calculadora state
  const [medTipo, setMedTipo] = useState('portaria');
  const [medDescricao, setMedDescricao] = useState('');
  const [medPeriodo, setMedPeriodo] = useState(30);
  const [medResult, setMedResult] = useState<MedicaoResult | null>(null);
  const [medLoading, setMedLoading] = useState(false);
  const [medError, setMedError] = useState('');

  // ── Tab 4 – Histórico (existing billing rules)
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [showFormModal, setShowFormModal] = useState(false);
  const [selectedRule, setSelectedRule] = useState<BillingRuleResponse | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    title: string; message: string; action: () => Promise<void>; variant: 'danger' | 'warning' | 'info';
  } | null>(null);

  const { data: rulesData, isLoading: rulesLoading, error: rulesError, refetch } = useBillingRules({
    condominio_id: condominioId,
    status: statusFilter !== 'all' ? statusFilter : undefined,
    search: searchTerm || undefined,
  });
  const createMutation = useCreateBillingRule();
  const updateMutation = useUpdateBillingRule();
  const deleteMutation = useDeleteBillingRule();
  const activateMutation = useActivateBillingRule();
  const pauseMutation = usePauseBillingRule();

  const rules: any[] = Array.isArray(rulesData) ? (rulesData as any[]) : ((rulesData as any)?.items ?? []);

  // ── Load billing summary
  const loadSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const mes = toYYYYMM(new Date());
      const { data } = await bankingApi.get(`/api/v1/financial/ai/billing/summary?mes=${mes}`);
      setSummary(data);
    } catch {
      // leave null — show zeros
    } finally {
      setSummaryLoading(false);
    }
  }, []);

  // ── Load contracts for month
  const loadContracts = useCallback(async (mes: string) => {
    setContractsLoading(true);
    try {
      const { data } = await bankingApi.get(`/api/v1/financial/ai/billing/contracts?mes=${mes}`);
      setContracts(Array.isArray(data) ? data : []);
    } catch {
      setContracts([]);
    } finally {
      setContractsLoading(false);
    }
  }, []);

  // ── Load preview
  const loadPreview = useCallback(async () => {
    setPreviewLoading(true);
    try {
      const { data } = await bankingApi.get(`/api/v1/financial/ai/billing/preview?mes=${mesSelecionado}`);
      setPreview(data);
    } catch {
      setPreview(null);
    } finally {
      setPreviewLoading(false);
    }
  }, [mesSelecionado]);

  // ── Calculate medicao
  const calcularMedicao = async () => {
    setMedLoading(true);
    setMedError('');
    try {
      const { data } = await bankingApi.post('/api/v1/financial/ai/billing/medicao', {
        tipo: medTipo,
        descricao: medDescricao || 'Contrato de serviço',
        periodo_dias: medPeriodo,
      });
      setMedResult(data);
    } catch {
      setMedError('Erro ao calcular medição. Tente novamente.');
    } finally {
      setMedLoading(false);
    }
  };

  // ── Effects
  useEffect(() => {
    if (activeTab === 'visao-geral') loadSummary();
  }, [activeTab, loadSummary]);

  useEffect(() => {
    if (activeTab === 'contratos') loadContracts(mesSelecionado);
  }, [activeTab, mesSelecionado, loadContracts]);

  // ── Billing rule handlers
  const handleCreate = () => { setSelectedRule(null); setShowFormModal(true); };
  const handleEdit = (rule: any) => { setSelectedRule(rule); setShowFormModal(true); };
  const handleDelete = (rule: any) => {
    setConfirmAction({
      title: 'Excluir Regra', message: `Excluir "${rule.name}" permanentemente?`,
      action: async () => { await deleteMutation.mutateAsync({ ruleId: rule.id }); },
      variant: 'danger',
    });
    setConfirmOpen(true);
  };
  // O banco guarda status em PT ('ativa'/'inativa'); comparar com 'active' (EN) nunca casava.
  const isAtiva = (r: any) => ['ativa', 'active', 'ativo', 'ativado'].includes(String(r?.status ?? '').toLowerCase()) || r?.is_active === true;
  const handleToggleStatus = async (rule: any) => {
    if (isAtiva(rule)) {
      await pauseMutation.mutateAsync({ ruleId: rule.id });
    } else {
      await activateMutation.mutateAsync({ ruleId: rule.id });
    }
  };
  const handleFormSubmit = async (data: BillingRuleCreate) => {
    if (selectedRule) {
      await updateMutation.mutateAsync({ ruleId: selectedRule.id, data });
    } else {
      await createMutation.mutateAsync({ data });
    }
    setShowFormModal(false);
    setSelectedRule(null);
  };

  const filteredRules = rules.filter((rule: any) => {
    const matchesSearch =
      !searchTerm ||
      rule.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      rule.description?.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = statusFilter === 'all'
      || (statusFilter === 'active' ? isAtiva(rule) : !isAtiva(rule));
    return matchesSearch && matchesStatus;
  });

  // FIN-08: as regras têm value_type='fixo' (PT) e o valor está em base_value —
  // antes filtrava por 'fixed' (EN, não existia) e somava r.value/amount
  // (inexistentes) → Valor Fixo Total = R$0. Agora tolera fixo/fixed e lê base_value.
  const isFixa = (r: any) =>
    ['fixo', 'fixed'].includes(String(r.value_type ?? r.type ?? r.rule_type ?? '').toLowerCase());
  const valorRegra = (r: any) => Number(r.base_value ?? r.value ?? r.amount ?? 0);
  const activeRules = rules.filter((r: any) => isAtiva(r));
  const totalFixedValue = activeRules
    .filter(isFixa)
    .reduce((sum: number, r: any) => sum + valorRegra(r), 0);

  // ── Chart data for overview
  const chartData = summary ? [
    { name: 'Faturado', valor: summary.total_faturado, fill: CHART_COLORS.faturado },
    { name: 'Pago', valor: summary.total_pago, fill: CHART_COLORS.pago },
    { name: 'Pendente', valor: summary.total_pendente, fill: CHART_COLORS.pendente },
    { name: 'Vencido', valor: summary.total_vencido, fill: CHART_COLORS.vencido },
  ] : [];

  return (
    <div className="min-h-screen bg-grid">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[hsl(var(--background))]/80 backdrop-blur-xl border-b border-[hsl(var(--border))]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <Link href="/modulos/financeiro">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Financeiro
                </Button>
              </Link>
              <div className="flex items-center gap-2">
                <div className="w-10 h-10 rounded-lg bg-amber-500/10 flex items-center justify-center">
                  <Receipt className="w-5 h-5 text-amber-500" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">Faturamento</h1>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">Automação e controle do ciclo de faturamento</p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => { loadSummary(); refetch(); }}>
                <RefreshCw className="w-4 h-4" />
              </Button>
              {activeTab === 'historico' && (
                <Button variant="primary" size="sm" onClick={handleCreate}>
                  <Plus className="w-4 h-4 mr-2" />
                  Nova Regra
                </Button>
              )}
            </div>
          </div>

          {/* Tab bar */}
          <div className="flex gap-0 overflow-x-auto border-t border-[hsl(var(--border))]">
            <Tab id="visao-geral" label="Visao Geral" icon={<BarChart2 className="w-4 h-4" />}
              active={activeTab === 'visao-geral'} onClick={() => setActiveTab('visao-geral')} />
            <Tab id="contratos" label="Contratos a Faturar" icon={<List className="w-4 h-4" />}
              active={activeTab === 'contratos'} onClick={() => setActiveTab('contratos')} />
            <Tab id="medicao" label="Calculadora de Medicao" icon={<Calculator className="w-4 h-4" />}
              active={activeTab === 'medicao'} onClick={() => setActiveTab('medicao')} />
            <Tab id="historico" label="Historico" icon={<Clock className="w-4 h-4" />}
              active={activeTab === 'historico'} onClick={() => setActiveTab('historico')} />
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">

        {/* ── TAB 1: VISÃO GERAL ───────────────────────────────────── */}
        {activeTab === 'visao-geral' && (
          <div className="space-y-6">
            {/* KPI Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <KPICard
                label="Total Faturado"
                value={summaryLoading ? '...' : formatCurrency(summary?.total_faturado)}
                icon={<Receipt className="w-5 h-5 text-blue-500" />}
                color="bg-blue-500/10"
              />
              <KPICard
                label="Pago no Mes"
                value={summaryLoading ? '...' : formatCurrency(summary?.total_pago)}
                icon={<CheckCircle className="w-5 h-5 text-green-500" />}
                color="bg-green-500/10"
              />
              <KPICard
                label="Pendente"
                value={summaryLoading ? '...' : formatCurrency(summary?.total_pendente)}
                icon={<Clock className="w-5 h-5 text-amber-500" />}
                color="bg-amber-500/10"
              />
              <KPICard
                label="Vencido"
                value={summaryLoading ? '...' : formatCurrency(summary?.total_vencido)}
                icon={<AlertCircle className="w-5 h-5 text-red-500" />}
                color="bg-red-500/10"
              />
            </div>

            {/* Secondary stats */}
            <div className="grid grid-cols-3 gap-4">
              <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 text-center">
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {summaryLoading ? '...' : summary?.qtd_faturas ?? 0}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">Faturas no Mes</p>
              </div>
              <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 text-center">
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {summaryLoading ? '...' : summary?.qtd_clientes ?? 0}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">Clientes</p>
              </div>
              <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 text-center">
                <p className="text-lg font-bold text-[hsl(var(--foreground))] truncate">
                  {summaryLoading ? '...' : formatCurrency(summary?.ticket_medio)}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">Ticket Medio</p>
              </div>
            </div>

            {/* Bar chart */}
            {chartData.length > 0 && (
              <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-6">
                <h3 className="text-sm font-semibold text-[hsl(var(--foreground))] mb-4">
                  Faturamento por Status — {summary?.mes}
                </h3>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                    <YAxis
                      tickFormatter={(v) => `R$${(v / 1000).toFixed(0)}k`}
                      tick={{ fontSize: 11 }}
                    />
                    <Tooltip
                      formatter={(v: unknown) => [formatCurrency(v as number)] as any}
                      contentStyle={{
                        background: 'hsl(var(--card))',
                        border: '1px solid hsl(var(--border))',
                        borderRadius: '8px',
                      }}
                    />
                    <Bar dataKey="valor" radius={[6, 6, 0, 0]}>
                      {chartData.map((entry, idx) => (
                        <Cell key={idx} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {summaryLoading && (
              <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
              </div>
            )}
          </div>
        )}

        {/* ── TAB 2: CONTRATOS A FATURAR ───────────────────────────── */}
        {activeTab === 'contratos' && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                <label className="text-sm text-[hsl(var(--muted-foreground))]">Mes de referencia:</label>
                <input
                  type="month"
                  value={mesSelecionado}
                  onChange={(e) => setMesSelecionado(e.target.value)}
                  className="border border-[hsl(var(--border))] rounded-lg px-3 py-1.5 text-sm bg-[hsl(var(--background))] text-[hsl(var(--foreground))] focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={loadPreview}
                disabled={previewLoading}
              >
                {previewLoading ? (
                  <RefreshCw className="w-4 h-4 animate-spin mr-2" />
                ) : (
                  <Zap className="w-4 h-4 mr-2" />
                )}
                Preview Faturamento
              </Button>
            </div>

            {/* Preview box */}
            {preview && (
              <div className="bg-blue-500/5 border border-blue-500/20 rounded-xl p-5 space-y-3">
                <div className="flex items-center gap-2">
                  <Zap className="w-5 h-5 text-blue-500" />
                  <h3 className="font-semibold text-[hsl(var(--foreground))]">
                    Preview Faturamento — {mesSelecionado}
                  </h3>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Contratos identificados</p>
                    <p className="font-data text-xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{preview.qtd_contratos}</p>
                  </div>
                  <div>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Valor estimado</p>
                    <p className="font-data text-xl font-semibold tabular-nums text-blue-500">{formatCurrency(preview.valor_estimado)}</p>
                  </div>
                </div>
                {preview.observacoes.map((obs, i) => (
                  <p key={i} className="text-sm text-[hsl(var(--muted-foreground))]">• {obs}</p>
                ))}
              </div>
            )}

            {/* Contracts table */}
            <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
              {contractsLoading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                </div>
              ) : contracts.length === 0 ? (
                <div className="text-center py-12">
                  <List className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                  <p className="text-[hsl(var(--muted-foreground))]">
                    Nenhum contrato pendente de faturamento em {mesSelecionado}
                  </p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Cliente</TableHead>
                      <TableHead className="text-right">Valor Total</TableHead>
                      <TableHead className="text-center">Titulos</TableHead>
                      <TableHead>Vencimento Medio</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {contracts.map((c, idx) => (
                      <TableRow key={c.customer_id ?? idx}>
                        <TableCell>
                          <p className="font-medium text-[hsl(var(--foreground))]">{c.customer_name}</p>
                          {c.customer_id && (
                            <p className="text-xs text-[hsl(var(--muted-foreground))]">#{c.customer_id.slice(0, 8)}</p>
                          )}
                        </TableCell>
                        <TableCell className="text-right font-semibold text-[hsl(var(--foreground))]">
                          {formatCurrency(c.valor_total)}
                        </TableCell>
                        <TableCell className="text-center">
                          <Badge className="bg-blue-500/10 text-blue-500 border-blue-500/20">
                            {c.qtd_titulos}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm text-[hsl(var(--muted-foreground))]">
                          {c.vencimento_medio
                            ? new Date(c.vencimento_medio + 'T00:00:00').toLocaleDateString('pt-BR')
                            : '—'}
                        </TableCell>
                        <TableCell>
                          <Badge className={
                            c.status === 'vencida'
                              ? 'bg-red-500/10 text-red-500 border-red-500/20'
                              : c.status === 'pendente'
                              ? 'bg-amber-500/10 text-amber-500 border-amber-500/20'
                              : 'bg-gray-500/10 text-gray-500 border-gray-500/20'
                          }>
                            {c.status}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
          </div>
        )}

        {/* ── TAB 3: CALCULADORA DE MEDIÇÃO ────────────────────────── */}
        {activeTab === 'medicao' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Form */}
              <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-6 space-y-5">
                <h3 className="font-semibold text-[hsl(var(--foreground))] flex items-center gap-2">
                  <Calculator className="w-5 h-5 text-amber-500" />
                  Parametros do Contrato
                </h3>

                {/* Tipo */}
                <div className="space-y-2">
                  <label className="text-sm font-medium text-[hsl(var(--foreground))]">Tipo de Servico</label>
                  <select
                    value={medTipo}
                    onChange={(e) => setMedTipo(e.target.value)}
                    className="w-full border border-[hsl(var(--border))] rounded-lg px-3 py-2 text-sm bg-[hsl(var(--background))] text-[hsl(var(--foreground))] focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    {TIPO_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>

                {/* Descricao */}
                <div className="space-y-2">
                  <label className="text-sm font-medium text-[hsl(var(--foreground))]">Descricao do Contrato</label>
                  <Input
                    placeholder="Ex: Contrato Condominio XYZ — 2 postos"
                    value={medDescricao}
                    onChange={(e) => setMedDescricao(e.target.value)}
                  />
                </div>

                {/* Periodo */}
                <div className="space-y-2">
                  <label className="text-sm font-medium text-[hsl(var(--foreground))]">
                    Periodo (dias): <span className="text-blue-500 font-bold">{medPeriodo}</span>
                  </label>
                  <input
                    type="range"
                    min={1}
                    max={365}
                    value={medPeriodo}
                    onChange={(e) => setMedPeriodo(Number(e.target.value))}
                    className="w-full accent-blue-500"
                  />
                  <div className="flex justify-between text-xs text-[hsl(var(--muted-foreground))]">
                    <span>1 dia</span>
                    <span>30 dias</span>
                    <span>90 dias</span>
                    <span>365 dias</span>
                  </div>
                </div>

                {medError && (
                  <p className="text-sm text-red-500">{medError}</p>
                )}

                <Button
                  variant="primary"
                  className="w-full"
                  onClick={calcularMedicao}
                  disabled={medLoading}
                >
                  {medLoading ? (
                    <RefreshCw className="w-4 h-4 animate-spin mr-2" />
                  ) : (
                    <Calculator className="w-4 h-4 mr-2" />
                  )}
                  Calcular Medicao
                </Button>
              </div>

              {/* Result */}
              <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-6">
                {!medResult ? (
                  <div className="flex flex-col items-center justify-center h-full py-12 text-center">
                    <Calculator className="w-12 h-12 text-[hsl(var(--muted-foreground))] mb-4" />
                    <p className="text-[hsl(var(--muted-foreground))] text-sm">
                      Preencha os parametros e clique em Calcular Medicao
                    </p>
                  </div>
                ) : (
                  <div className="space-y-5">
                    <h3 className="font-semibold text-[hsl(var(--foreground))]">
                      Resultado — {medResult.tipo_label}
                    </h3>
                    {medResult.contrato_descricao && (
                      <p className="text-sm text-[hsl(var(--muted-foreground))]">{medResult.contrato_descricao}</p>
                    )}

                    {/* Breakdown rows */}
                    {[
                      { label: 'Valor Base', value: medResult.valor_base, icon: <DollarSign className="w-4 h-4" />, color: 'text-[hsl(var(--foreground))]' },
                      { label: 'Adicional HE', value: medResult.adicional_he, icon: <TrendingUp className="w-4 h-4" />, color: 'text-amber-500' },
                      { label: 'Adicional Noturno', value: medResult.adicional_noturno, icon: <TrendingUp className="w-4 h-4" />, color: 'text-blue-500' },
                      { label: 'Deduções', value: -medResult.deducoes, icon: <TrendingDown className="w-4 h-4" />, color: 'text-green-500' },
                    ].map(({ label, value, icon, color }) => (
                      <div key={label} className="flex items-center justify-between py-2 border-b border-[hsl(var(--border))]">
                        <div className="flex items-center gap-2 text-sm text-[hsl(var(--muted-foreground))]">
                          {icon}
                          {label}
                        </div>
                        <span className={`font-medium text-sm ${color}`}>{formatCurrency(Math.abs(value))}</span>
                      </div>
                    ))}

                    <div className="flex items-center justify-between pt-2">
                      <span className="font-bold text-[hsl(var(--foreground))]">TOTAL</span>
                      <span className="font-data text-2xl font-semibold tabular-nums text-green-500">{formatCurrency(medResult.valor_total)}</span>
                    </div>

                    <div className="bg-[hsl(var(--muted))]/30 rounded-lg p-3 space-y-1">
                      <p className="text-xs font-medium text-[hsl(var(--muted-foreground))]">Detalhamento</p>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">
                        Custo diario: {formatCurrency(medResult.detalhamento.custo_diario)} ×{' '}
                        {medResult.periodo_dias} dias
                      </p>
                      {medResult.detalhamento.he_percentual > 0 && (
                        <p className="text-xs text-[hsl(var(--muted-foreground))]">
                          HE: {medResult.detalhamento.he_percentual}% sobre valor base
                        </p>
                      )}
                      {medResult.detalhamento.noturno_percentual > 0 && (
                        <p className="text-xs text-[hsl(var(--muted-foreground))]">
                          Noturno: {medResult.detalhamento.noturno_percentual}% sobre valor base
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── TAB 4: HISTÓRICO (Regras de Faturamento) ─────────────── */}
        {activeTab === 'historico' && (
          <div className="space-y-6">
            {/* Stats */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <KPICard label="Total Regras" value={rulesLoading ? '...' : String(rules.length)}
                icon={<Receipt className="w-5 h-5 text-amber-500" />} color="bg-amber-500/10" />
              <KPICard label="Ativas" value={rulesLoading ? '...' : String(activeRules.length)}
                icon={<CheckCircle className="w-5 h-5 text-green-500" />} color="bg-green-500/10" />
              <KPICard label="Valor Fixo Total" value={rulesLoading ? '...' : formatCurrency(totalFixedValue)}
                icon={<DollarSign className="w-5 h-5 text-blue-500" />} color="bg-blue-500/10" />
              <KPICard label="Inativas" value={rulesLoading ? '...' : String(rules.filter((r: any) => !isAtiva(r)).length)}
                icon={<Clock className="w-5 h-5 text-gray-500" />} color="bg-gray-500/10" />
            </div>

            {/* Filters */}
            <div className="flex flex-col sm:flex-row gap-4">
              <div className="flex-1">
                <Input
                  type="search"
                  placeholder="Buscar por nome ou descricao..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  icon={<Search className="w-4 h-4" />}
                />
              </div>
              <Select value={statusFilter} onValueChange={setStatusFilter} aria-label="Status Filter">
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="active">Ativo</SelectItem>
                  <SelectItem value="inactive">Inativo</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {rulesError && (
              <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
                <Receipt className="h-5 w-5 text-destructive" />
                <p className="text-sm text-destructive flex-1">Erro ao carregar regras de faturamento</p>
                <Button variant="outline" size="sm" onClick={() => refetch()}>Tentar novamente</Button>
              </div>
            )}

            <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
              {rulesLoading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                </div>
              ) : (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Nome</TableHead>
                        <TableHead>Tipo</TableHead>
                        <TableHead>Valor / Percentual</TableHead>
                        <TableHead>Periodicidade</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="text-right">Ações</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredRules.map((rule: any) => (
                        <TableRow key={rule.id}>
                          <TableCell>
                            <div>
                              <p className="font-medium text-[hsl(var(--foreground))]">{rule.name}</p>
                              {rule.description && (
                                <p className="text-xs text-[hsl(var(--muted-foreground))] truncate max-w-[200px]">
                                  {rule.description}
                                </p>
                              )}
                            </div>
                          </TableCell>
                          <TableCell>
                            <Badge className={getTypeColor(rule.type || rule.rule_type)}>
                              {TYPE_LABELS[rule.type || rule.rule_type] || rule.type || rule.rule_type}
                            </Badge>
                          </TableCell>
                          <TableCell className="font-medium">
                            {['percentual', 'percentage'].includes(String(rule.value_type ?? rule.type ?? rule.rule_type ?? '').toLowerCase())
                              ? `${valorRegra(rule)}%`
                              : formatCurrency(valorRegra(rule))}
                          </TableCell>
                          <TableCell>
                            <span className="text-sm text-[hsl(var(--foreground))]">
                              {FREQUENCY_LABELS[rule.frequency || rule.recurrence] || rule.frequency || rule.recurrence || '-'}
                            </span>
                          </TableCell>
                          <TableCell>
                            <Badge
                              className={
                                isAtiva(rule)
                                  ? 'bg-green-500/10 text-green-500 border-green-500/20 cursor-pointer'
                                  : 'bg-gray-500/10 text-gray-500 border-gray-500/20 cursor-pointer'
                              }
                              onClick={() => handleToggleStatus(rule)}
                            >
                              {isAtiva(rule) ? 'Ativo' : 'Inativo'}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right">
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button variant="ghost" size="sm">
                                  <MoreHorizontal className="w-4 h-4" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem onClick={() => handleEdit(rule)}>
                                  <Edit className="w-4 h-4 mr-2" />Editar
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => handleToggleStatus(rule)}>
                                  <Eye className="w-4 h-4 mr-2" />
                                  {rule.status === 'active' ? 'Desativar' : 'Ativar'}
                                </DropdownMenuItem>
                                <DropdownMenuItem
                                  onClick={() => handleDelete(rule)}
                                  className="text-red-500 focus:text-red-500"
                                >
                                  <Trash2 className="w-4 h-4 mr-2" />Excluir
                                </DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>

                  {filteredRules.length === 0 && (
                    <div className="text-center py-12">
                      <Receipt className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                      <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                        Nenhuma regra de faturamento encontrada
                      </h3>
                      <p className="text-[hsl(var(--muted-foreground))] mt-1 mb-4">
                        {searchTerm ? 'Tente ajustar os filtros de busca' : 'Crie a primeira regra de faturamento'}
                      </p>
                      {!searchTerm && (
                        <Button variant="primary" onClick={handleCreate}>
                          <Plus className="w-4 h-4 mr-2" />Nova Regra
                        </Button>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </main>

      {/* Modals */}
      <BillingRuleFormModal
        isOpen={showFormModal}
        onClose={() => { setShowFormModal(false); setSelectedRule(null); }}
        onSubmit={handleFormSubmit}
        rule={selectedRule}
      />

      {confirmAction && (
        <ConfirmModal
          isOpen={confirmOpen}
          onClose={() => setConfirmOpen(false)}
          onConfirm={async () => { await confirmAction.action(); setConfirmOpen(false); }}
          title={confirmAction.title}
          message={confirmAction.message}
          variant={confirmAction.variant}
          isLoading={deleteMutation.isPending}
        />
      )}
    </div>
  );
}
