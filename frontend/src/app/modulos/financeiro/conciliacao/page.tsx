'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import Link from 'next/link';
import {
  CheckCircle2,
  Search,
  RefreshCw,
  Plus,
  Landmark,
  Upload,
  Eye,
  MoreHorizontal,
  AlertCircle,
  ArrowLeft,
  ArrowUpCircle,
  ArrowDownCircle,
  Activity,
  TrendingUp,
  TrendingDown,
  Building2,
  GitMerge,
  Wifi,
  WifiOff,
  FileText,
  X,
  Check,
  MinusCircle,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  useBankAccounts,
  useCreateBankAccount,
  useBankTransactions,
  useImportOFX,
} from '@/hooks/financial/useFinancial';
import { useCondominio } from '@/contexts/CondominioContext';
import type { BankAccountResponse } from '@/types/generated/financial/models/bankAccountResponse';
import type { BankTransactionResponse } from '@/types/generated/financial/models/bankTransactionResponse';
import type { BankAccountCreate } from '@/types/generated/financial/models/bankAccountCreate';
import { BankAccountFormModal } from '@/components/financeiro/bank-account-form-modal';
import { BankTransactionDetailModal } from '@/components/financeiro/bank-transaction-detail-modal';
import { cn, formatCurrency, formatDate } from '@/lib/utils';
import {
  fetchBankStatementFull,
  fetchBankBalances,
} from '@/services/banking/bankingService';
import type {
  BankTransactionFull,
  BankStatementFullResponse,
  BankingBalancesResponse,
} from '@/services/banking/bankingService';

type TabType = 'statement' | 'accounts' | 'reconciliation' | 'import-ofx';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getPaymentTypeBadge(txType: string) {
  const t = (txType || '').toUpperCase();
  if (t.includes('PIX'))
    return 'bg-emerald-500/15 text-emerald-600 border-emerald-500/30';
  if (t.includes('TED'))
    return 'bg-blue-500/15 text-blue-600 border-blue-500/30';
  if (t.includes('BOLETO') || t.includes('BILLET'))
    return 'bg-orange-500/15 text-orange-600 border-orange-500/30';
  if (t.includes('TARIFA') || t.includes('FEE') || t.includes('IOF'))
    return 'bg-slate-500/15 text-slate-500 border-slate-500/30';
  if (t.includes('DOC'))
    return 'bg-indigo-500/15 text-indigo-600 border-indigo-500/30';
  if (t.includes('CHEQUE'))
    return 'bg-purple-500/15 text-purple-600 border-purple-500/30';
  return 'bg-gray-400/15 text-gray-500 border-gray-400/30';
}

function getPaymentTypeLabel(txType: string) {
  const t = (txType || '').toUpperCase();
  if (t.includes('PIX')) return 'PIX';
  if (t.includes('TED')) return 'TED';
  if (t.includes('BOLETO') || t.includes('BILLET')) return 'Boleto';
  if (t.includes('TARIFA') || t.includes('FEE') || t.includes('IOF')) return 'Tarifa';
  if (t.includes('DOC')) return 'DOC';
  if (t.includes('CHEQUE')) return 'Cheque';
  return txType || 'Outros';
}

function getBankBadge(bankCode: string) {
  if (bankCode === '077') return { label: 'Inter', color: '#00a859' };
  return { label: bankCode || 'Banco', color: '#6b7280' };
}

function getMatchStatusStyle(status: string) {
  switch (status) {
    case 'matched':
      return { badge: 'bg-green-500/15 text-green-600 border-green-500/30', label: 'Conciliado' };
    case 'divergent':
      return { badge: 'bg-red-500/15 text-red-600 border-red-500/30', label: 'Divergente' };
    default:
      return { badge: 'bg-amber-500/15 text-amber-600 border-amber-500/30', label: 'Pendente' };
  }
}

function KpiCard({
  title,
  value,
  icon,
  color,
  loading,
}: {
  title: string;
  value: string;
  icon: React.ReactNode;
  color: string;
  loading?: boolean;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-xs text-[hsl(var(--muted-foreground))] mb-1 truncate">{title}</p>
            {loading ? (
              <div className="h-6 w-28 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
            ) : (
              <p className={cn('font-data text-xl font-semibold tabular-nums', color)}>{value}</p>
            )}
          </div>
          <div className={cn('w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0', color.replace('text-', 'bg-').replace('-600', '-500/10').replace('-500', '-500/10'))}>
            {icon}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function ConciliacaoPage() {
  const { condominioId } = useCondominio();
  const [activeTab, setActiveTab] = useState<TabType>('statement');
  const [search, setSearch] = useState('');
  const [showAccountModal, setShowAccountModal] = useState(false);
  const [selectedTransaction, setSelectedTransaction] = useState<BankTransactionResponse | null>(null);
  const [showTransactionDetail, setShowTransactionDetail] = useState(false);

  // ── Tab 1: Extrato Bancário ──────────────────────────────────────────────
  const [statementDays, setStatementDays] = useState(30);
  const [statementBankFilter, setStatementBankFilter] = useState<string>('all');
  const [statementTypeFilter, setStatementTypeFilter] = useState<string>('all');
  const [statementData, setStatementData] = useState<BankStatementFullResponse | null>(null);
  const [statementLoading, setStatementLoading] = useState(false);
  const [lastSync, setLastSync] = useState<string | null>(null);

  const syncStatement = useCallback(async () => {
    setStatementLoading(true);
    try {
      const bankCode = statementBankFilter !== 'all' ? statementBankFilter : undefined;
      const data = await fetchBankStatementFull(statementDays, bankCode);
      setStatementData(data);
      setLastSync(new Date().toLocaleTimeString('pt-BR'));
    } catch {
      // silenced
    } finally {
      setStatementLoading(false);
    }
  }, [statementDays, statementBankFilter]);

  useEffect(() => {
    if (activeTab === 'statement') {
      syncStatement();
    }
  }, [activeTab, syncStatement]);

  // Filtered statement transactions
  const statementTransactions: BankTransactionFull[] = (statementData?.transactions ?? []).filter((tx) => {
    const matchesType =
      statementTypeFilter === 'all' ||
      (statementTypeFilter === 'credit' && tx.type === 'credit') ||
      (statementTypeFilter === 'debit' && tx.type === 'debit');
    const matchesSearch =
      !search ||
      tx.description?.toLowerCase().includes(search.toLowerCase()) ||
      tx.counterpart_name?.toLowerCase().includes(search.toLowerCase());
    return matchesType && matchesSearch;
  });

  const statementCredits = statementTransactions
    .filter((t) => t.type === 'credit')
    .reduce((s, t) => s + t.amount, 0);
  const statementDebits = statementTransactions
    .filter((t) => t.type === 'debit')
    .reduce((s, t) => s + t.amount, 0);
  const statementBalance = statementCredits - statementDebits;

  // ── Tab 2: Contas Bancárias ──────────────────────────────────────────────
  const {
    data: accountsData,
    isLoading: loadingAccounts,
    isError: accountsError,
    error: accountsErr,
    refetch: refetchAccounts,
  } = useBankAccounts({ condominio_id: condominioId });

  const {
    data: transactionsData,
    isLoading: loadingTransactions,
    isError: transactionsError,
    error: transactionsErr,
    refetch: refetchTransactions,
  } = useBankTransactions({ bank_account_id: '' });

  const createBankAccount = useCreateBankAccount();
  const importOFX = useImportOFX();

  const accounts: BankAccountResponse[] = Array.isArray(accountsData) ? accountsData : [];
  const transactions: BankTransactionResponse[] = Array.isArray(transactionsData) ? transactionsData : [];

  const totalAccountsBalance = accounts.reduce(
    (s, a) => s + (a.current_balance ? parseFloat(a.current_balance) : 0),
    0
  );
  const pixEnabledCount = accounts.filter((a: any) => a.pix_enabled).length;

  const filteredAccounts = search
    ? accounts.filter(
        (acc) =>
          acc.name?.toLowerCase().includes(search.toLowerCase()) ||
          acc.bank_name?.toLowerCase().includes(search.toLowerCase())
      )
    : accounts;

  // ── Tab 3: Conciliação ───────────────────────────────────────────────────
  const filteredTransactions = search
    ? transactions.filter((tx) => tx.description?.toLowerCase().includes(search.toLowerCase()))
    : transactions;

  const matchedCount = filteredTransactions.filter(
    (tx) => tx.reconciliation_status === 'matched'
  ).length;
  const reconciliationProgress =
    filteredTransactions.length > 0
      ? Math.round((matchedCount / filteredTransactions.length) * 100)
      : 0;

  // ── Tab 4: Importar OFX ─────────────────────────────────────────────────
  const [isDragOver, setIsDragOver] = useState(false);
  const [ofxPreview, setOfxPreview] = useState<{ name: string; size: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Handlers ─────────────────────────────────────────────────────────────

  const handleCreateAccount = async (data: any) => {
    try {
      await createBankAccount.mutateAsync({ data: data as BankAccountCreate });
      setShowAccountModal(false);
    } catch (err) {
      throw err;
    }
  };

  const handleImportOFX = async (file?: File) => {
    const target = file ?? (() => {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = '.ofx,.OFX';
      return input;
    })();

    if (target instanceof HTMLInputElement) {
      target.onchange = async (e) => {
        const f = (e.target as HTMLInputElement).files?.[0];
        if (!f) return;
        setOfxPreview({ name: f.name, size: `${(f.size / 1024).toFixed(1)} KB` });
        try {
          await importOFX.mutateAsync({
            data: { file: f } as unknown as Parameters<typeof importOFX.mutateAsync>[0]['data'],
            params: { bank_account_id: '' },
          });
        } catch {
          // silenced
        }
      };
      target.click();
      return;
    }

    // file is a File object
    setOfxPreview({ name: file!.name, size: `${(file!.size / 1024).toFixed(1)} KB` });
    try {
      await importOFX.mutateAsync({
        data: { file: file! } as unknown as Parameters<typeof importOFX.mutateAsync>[0]['data'],
        params: { bank_account_id: '' },
      });
    } catch {
      // silenced
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file && (file.name.endsWith('.ofx') || file.name.endsWith('.OFX'))) {
      handleImportOFX(file);
    }
  };

  const handleViewTransaction = (transaction: BankTransactionResponse) => {
    setSelectedTransaction(transaction);
    setShowTransactionDetail(true);
  };

  const refetch = () => {
    refetchAccounts();
    refetchTransactions();
  };

  // ── Tabs config ──────────────────────────────────────────────────────────

  const tabs: { key: TabType; label: string; icon: React.ReactNode }[] = [
    { key: 'statement', label: 'Extrato Bancario', icon: <Activity className="w-3.5 h-3.5" /> },
    { key: 'accounts', label: 'Contas Bancarias', icon: <Building2 className="w-3.5 h-3.5" /> },
    { key: 'reconciliation', label: 'Conciliacao', icon: <GitMerge className="w-3.5 h-3.5" /> },
    { key: 'import-ofx', label: 'Importar OFX', icon: <Upload className="w-3.5 h-3.5" /> },
  ];

  const isLoading =
    activeTab === 'accounts' ? loadingAccounts : activeTab === 'reconciliation' ? loadingTransactions : false;
  const isError =
    activeTab === 'accounts' ? accountsError : activeTab === 'reconciliation' ? transactionsError : false;
  const error =
    activeTab === 'accounts' ? accountsErr : activeTab === 'reconciliation' ? transactionsErr : null;

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6 animate-fade-in">

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <Link href="/modulos/financeiro">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="w-4 h-4 mr-2" />
              Financeiro
            </Button>
          </Link>
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5 text-emerald-500" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                Conciliacao Bancaria
              </h1>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                {activeTab === 'statement'
                  ? lastSync
                    ? `Ultima sincronizacao: ${lastSync}`
                    : 'Aguardando sincronizacao...'
                  : 'Gerencie contas, extrato e conciliacao'}
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {activeTab === 'statement' && (
            <Button
              variant="outline"
              size="sm"
              onClick={syncStatement}
              disabled={statementLoading}
            >
              <RefreshCw className={cn('w-4 h-4 mr-2', statementLoading && 'animate-spin')} />
              Sincronizar com Bancos
            </Button>
          )}
          {activeTab === 'accounts' && (
            <>
              <Button variant="outline" size="sm" onClick={refetch} disabled={isLoading}>
                <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
              </Button>
              <Button variant="primary" size="sm" onClick={() => setShowAccountModal(true)}>
                <Plus className="w-4 h-4 mr-2" />
                Nova Conta
              </Button>
            </>
          )}
          {activeTab === 'reconciliation' && (
            <Button variant="outline" size="sm" onClick={refetch} disabled={isLoading}>
              <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
            </Button>
          )}
          {activeTab === 'import-ofx' && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => handleImportOFX()}
              disabled={importOFX.isPending}
            >
              <Upload className="w-4 h-4 mr-2" />
              Selecionar Arquivo
            </Button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2">
        {tabs.map((tab) => (
          <Button
            key={tab.key}
            variant="ghost"
            size="sm"
            className={cn(
              'rounded-lg px-4 py-2 flex items-center gap-1.5',
              activeTab === tab.key
                ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]'
                : 'bg-[hsl(var(--secondary))] text-[hsl(var(--secondary-foreground))]'
            )}
            onClick={() => { setActiveTab(tab.key); setSearch(''); }}
          >
            {tab.icon}
            {tab.label}
          </Button>
        ))}
      </div>

      {/* Search — show on tabs that use it */}
      {(activeTab === 'statement' || activeTab === 'accounts' || activeTab === 'reconciliation') && (
        <div className="flex-1">
          <Input
            type="search"
            placeholder={
              activeTab === 'statement'
                ? 'Buscar por descricao ou contraparte...'
                : activeTab === 'accounts'
                ? 'Buscar contas...'
                : 'Buscar transacoes...'
            }
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            icon={<Search className="w-4 h-4" />}
          />
        </div>
      )}

      {/* Error banner */}
      {isError && (
        <div className="flex items-center gap-3 p-4 rounded-lg bg-[hsl(var(--destructive))]/10 border border-[hsl(var(--destructive))]/30">
          <AlertCircle className="w-5 h-5 text-[hsl(var(--destructive))] flex-shrink-0" />
          <div>
            <p className="font-medium text-[hsl(var(--destructive))]">Erro ao carregar dados</p>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">
              {(error as Error)?.message || 'Tente novamente em alguns instantes'}
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={refetch} className="ml-auto">
            Tentar novamente
          </Button>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════
          TAB 1 — Extrato Bancário
      ══════════════════════════════════════════════════════════════════════ */}
      {activeTab === 'statement' && (
        <div className="space-y-5">

          {/* Filtros de período + banco + tipo */}
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={statementBankFilter}
              onChange={(e) => setStatementBankFilter(e.target.value)}
              className="h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm px-3 text-[hsl(var(--foreground))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--ring))]"
            >
              <option value="all">Todos os bancos</option>
              <option value="077">Inter</option>
            </select>

            <select
              value={statementTypeFilter}
              onChange={(e) => setStatementTypeFilter(e.target.value)}
              className="h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm px-3 text-[hsl(var(--foreground))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--ring))]"
            >
              <option value="all">Todos os tipos</option>
              <option value="credit">Credito</option>
              <option value="debit">Debito</option>
            </select>

            <select
              value={statementDays}
              onChange={(e) => setStatementDays(Number(e.target.value))}
              className="h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm px-3 text-[hsl(var(--foreground))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--ring))]"
            >
              <option value={7}>Ultimos 7 dias</option>
              <option value={15}>Ultimos 15 dias</option>
              <option value={30}>Ultimos 30 dias</option>
              <option value={60}>Ultimos 60 dias</option>
              <option value={90}>Ultimos 90 dias</option>
            </select>
          </div>

          {/* KPI Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <KpiCard
              title="Total Entradas"
              value={formatCurrency(statementCredits)}
              icon={<TrendingUp className="w-4 h-4 text-green-500" />}
              color="text-green-600"
              loading={statementLoading}
            />
            <KpiCard
              title="Total Saidas"
              value={formatCurrency(statementDebits)}
              icon={<TrendingDown className="w-4 h-4 text-red-500" />}
              color="text-red-600"
              loading={statementLoading}
            />
            <KpiCard
              title="Saldo do Periodo"
              value={formatCurrency(statementBalance)}
              icon={<Activity className="w-4 h-4 text-blue-500" />}
              color={statementBalance >= 0 ? 'text-blue-600' : 'text-red-600'}
              loading={statementLoading}
            />
            <KpiCard
              title="Transacoes"
              value={String(statementTransactions.length)}
              icon={<ArrowUpCircle className="w-4 h-4 text-purple-500" />}
              color="text-purple-600"
              loading={statementLoading}
            />
          </div>

          {/* Tabela de transações */}
          <Card>
            <CardContent className="p-0">
              {statementLoading ? (
                <div className="divide-y divide-[hsl(var(--border))]">
                  {[...Array(6)].map((_, i) => (
                    <div key={i} className="p-4 flex items-center gap-4">
                      <div className="flex-1 space-y-2">
                        <div className="h-4 w-48 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                        <div className="h-3 w-32 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                      </div>
                      <div className="h-4 w-24 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                    </div>
                  ))}
                </div>
              ) : statementTransactions.length === 0 ? (
                <div className="text-center py-16">
                  <Activity className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                    Nenhuma transacao encontrada
                  </h3>
                  <p className="text-[hsl(var(--muted-foreground))] mt-1 mb-4">
                    {search ? 'Tente ajustar a busca' : 'Sincronize com os bancos para ver o extrato'}
                  </p>
                  {!search && (
                    <Button onClick={syncStatement} disabled={statementLoading}>
                      <RefreshCw className="w-4 h-4 mr-2" />
                      Sincronizar Agora
                    </Button>
                  )}
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-[hsl(var(--border))]">
                        <th className="text-left p-4 text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide">
                          Data / Hora
                        </th>
                        <th className="text-left p-4 text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide">
                          Descricao
                        </th>
                        <th className="text-left p-4 text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide hidden md:table-cell">
                          Tipo
                        </th>
                        <th className="text-left p-4 text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide hidden lg:table-cell">
                          Banco
                        </th>
                        <th className="text-right p-4 text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide">
                          Valor
                        </th>
                        <th className="text-right p-4 text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide hidden xl:table-cell">
                          Saldo Apos
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[hsl(var(--border))]">
                      {statementTransactions.map((tx) => {
                        const bankBadge = getBankBadge(tx.bank_code);
                        const isCredit = tx.type === 'credit';
                        return (
                          <tr
                            key={tx.id}
                            className="hover:bg-[hsl(var(--secondary))]/40 transition-colors"
                          >
                            {/* Data */}
                            <td className="p-4 whitespace-nowrap">
                              <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                                {tx.date ? formatDate(tx.date) : '-'}
                              </p>
                              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                                {tx.date
                                  ? new Date(tx.date).toLocaleTimeString('pt-BR', {
                                      hour: '2-digit',
                                      minute: '2-digit',
                                    })
                                  : ''}
                              </p>
                            </td>

                            {/* Descricao */}
                            <td className="p-4 max-w-xs">
                              <p className="text-sm font-medium text-[hsl(var(--foreground))] truncate">
                                {tx.description || '-'}
                              </p>
                              {tx.counterpart_name && (
                                <p className="text-xs text-[hsl(var(--muted-foreground))] truncate">
                                  {tx.counterpart_name}
                                </p>
                              )}
                            </td>

                            {/* Tipo de pagamento */}
                            <td className="p-4 hidden md:table-cell">
                              <span
                                className={cn(
                                  'inline-flex px-2 py-0.5 text-xs font-medium rounded-full border',
                                  getPaymentTypeBadge(tx.transaction_type)
                                )}
                              >
                                {getPaymentTypeLabel(tx.transaction_type)}
                              </span>
                            </td>

                            {/* Banco */}
                            <td className="p-4 hidden lg:table-cell">
                              <span
                                className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-full border"
                                style={{
                                  color: bankBadge.color,
                                  backgroundColor: `${bankBadge.color}18`,
                                  borderColor: `${bankBadge.color}40`,
                                }}
                              >
                                <Landmark className="w-3 h-3" />
                                {bankBadge.label}
                              </span>
                            </td>

                            {/* Valor */}
                            <td className="p-4 text-right whitespace-nowrap">
                              <span
                                className={cn(
                                  'font-mono text-sm font-semibold',
                                  isCredit ? 'text-green-500' : 'text-red-500'
                                )}
                              >
                                {isCredit ? '+' : '-'}
                                {formatCurrency(Math.abs(tx.amount))}
                              </span>
                            </td>

                            {/* Saldo após */}
                            <td className="p-4 text-right hidden xl:table-cell">
                              {tx.balance_after != null ? (
                                <span className="font-mono text-xs text-[hsl(var(--muted-foreground))]">
                                  {formatCurrency(tx.balance_after)}
                                </span>
                              ) : (
                                <span className="text-xs text-[hsl(var(--muted-foreground))]">—</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════
          TAB 2 — Contas Bancárias
      ══════════════════════════════════════════════════════════════════════ */}
      {activeTab === 'accounts' && (
        <div className="space-y-5">

          {/* KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <KpiCard
              title="Total de Contas"
              value={String(accounts.length)}
              icon={<Building2 className="w-4 h-4 text-blue-500" />}
              color="text-blue-600"
              loading={loadingAccounts}
            />
            <KpiCard
              title="Saldo Total"
              value={formatCurrency(totalAccountsBalance)}
              icon={<TrendingUp className="w-4 h-4 text-emerald-500" />}
              color="text-emerald-600"
              loading={loadingAccounts}
            />
            <KpiCard
              title="Contas PIX Habilitadas"
              value={String(pixEnabledCount)}
              icon={<Wifi className="w-4 h-4 text-purple-500" />}
              color="text-purple-600"
              loading={loadingAccounts}
            />
          </div>

          {/* Tabela */}
          <Card>
            <CardContent className="p-0">
              {loadingAccounts ? (
                <div className="divide-y divide-[hsl(var(--border))]">
                  {[...Array(3)].map((_, i) => (
                    <div key={i} className="p-4 flex items-center gap-4">
                      <div className="flex-1 space-y-2">
                        <div className="h-4 w-48 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                        <div className="h-3 w-32 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-[hsl(var(--border))]">
                        <th className="text-left p-4 text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide">
                          Conta
                        </th>
                        <th className="text-left p-4 text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide hidden md:table-cell">
                          Banco
                        </th>
                        <th className="text-left p-4 text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide hidden lg:table-cell">
                          Agencia / Conta
                        </th>
                        <th className="text-left p-4 text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide hidden lg:table-cell">
                          Recursos
                        </th>
                        <th className="text-right p-4 text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide">
                          Saldo Atual
                        </th>
                        <th className="w-12 p-4"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[hsl(var(--border))]">
                      {filteredAccounts.map((account: BankAccountResponse) => (
                        <tr
                          key={account.id}
                          className="hover:bg-[hsl(var(--secondary))]/50 transition-colors"
                        >
                          <td className="p-4">
                            <div className="flex items-center gap-3">
                              <div className="w-9 h-9 rounded-lg bg-emerald-500/10 flex items-center justify-center flex-shrink-0">
                                <Landmark className="w-4 h-4 text-emerald-500" />
                              </div>
                              <div>
                                <p className="font-medium text-[hsl(var(--foreground))]">
                                  {account.name}
                                </p>
                                <p className="text-xs text-[hsl(var(--muted-foreground))] md:hidden">
                                  {account.bank_name}
                                </p>
                              </div>
                            </div>
                          </td>
                          <td className="p-4 hidden md:table-cell">
                            <span className="text-sm text-[hsl(var(--foreground))]">
                              {account.bank_name || '-'}
                            </span>
                          </td>
                          <td className="p-4 hidden lg:table-cell">
                            <p className="text-sm text-[hsl(var(--muted-foreground))]">
                              Ag. {account.agency || '—'}
                            </p>
                            <p className="text-xs text-[hsl(var(--muted-foreground))]">
                              Cc. {account.account_number || '—'}
                            </p>
                          </td>
                          <td className="p-4 hidden lg:table-cell">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              {(account as any).pix_enabled ? (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-purple-500/15 text-purple-600 border border-purple-500/30">
                                  <Wifi className="w-3 h-3" /> PIX
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-gray-400/15 text-gray-500 border border-gray-400/30">
                                  <WifiOff className="w-3 h-3" /> PIX
                                </span>
                              )}
                              {(account as any).boleto_enabled && (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-orange-500/15 text-orange-600 border border-orange-500/30">
                                  <FileText className="w-3 h-3" /> Boleto
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="p-4 text-right">
                            <span className="font-mono text-sm font-semibold text-[hsl(var(--foreground))]">
                              {formatCurrency(
                                account.current_balance ? parseFloat(account.current_balance) : 0
                              )}
                            </span>
                          </td>
                          <td className="p-4">
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button variant="ghost" size="sm">
                                  <MoreHorizontal className="w-4 h-4" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem>
                                  <Eye className="w-4 h-4 mr-2" />
                                  Visualizar
                                </DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {!loadingAccounts && filteredAccounts.length === 0 && (
                <div className="text-center py-14">
                  <Landmark className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                    Nenhuma conta bancaria encontrada
                  </h3>
                  <p className="text-[hsl(var(--muted-foreground))] mt-1">
                    {search ? 'Tente ajustar a busca' : 'Cadastre sua primeira conta bancaria'}
                  </p>
                  {!search && (
                    <Button className="mt-4" onClick={() => setShowAccountModal(true)}>
                      <Plus className="w-4 h-4 mr-2" />
                      Nova Conta
                    </Button>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════
          TAB 3 — Conciliação
      ══════════════════════════════════════════════════════════════════════ */}
      {activeTab === 'reconciliation' && (
        <div className="space-y-5">

          {/* Barra de progresso */}
          {filteredTransactions.length > 0 && (
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                      Progresso de Conciliacao
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">
                      {matchedCount} de {filteredTransactions.length} transacoes conciliadas
                    </p>
                  </div>
                  <span
                    className={cn(
                      'font-data text-2xl font-semibold tabular-nums',
                      reconciliationProgress === 100
                        ? 'text-green-500'
                        : reconciliationProgress > 50
                        ? 'text-amber-500'
                        : 'text-red-500'
                    )}
                  >
                    {reconciliationProgress}%
                  </span>
                </div>
                <div className="w-full bg-[hsl(var(--secondary))] rounded-full h-2.5">
                  <div
                    className={cn(
                      'h-2.5 rounded-full transition-all duration-500',
                      reconciliationProgress === 100
                        ? 'bg-green-500'
                        : reconciliationProgress > 50
                        ? 'bg-amber-500'
                        : 'bg-red-500'
                    )}
                    style={{ width: `${reconciliationProgress}%` }}
                  />
                </div>
              </CardContent>
            </Card>
          )}

          {/* Split view */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">

            {/* Lado esquerdo: Transações bancárias */}
            <Card>
              <CardContent className="p-0">
                <div className="p-4 border-b border-[hsl(var(--border))]">
                  <h2 className="font-semibold text-[hsl(var(--foreground))]">
                    Transacoes Bancarias
                  </h2>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    Transacoes nao conciliadas aparecem em destaque
                  </p>
                </div>

                {loadingTransactions ? (
                  <div className="divide-y divide-[hsl(var(--border))]">
                    {[...Array(4)].map((_, i) => (
                      <div key={i} className="p-4 space-y-2">
                        <div className="h-4 w-40 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                        <div className="h-3 w-24 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                      </div>
                    ))}
                  </div>
                ) : filteredTransactions.length === 0 ? (
                  <div className="text-center py-10">
                    <GitMerge className="w-10 h-10 text-[hsl(var(--muted-foreground))] mx-auto mb-3" />
                    <p className="text-[hsl(var(--muted-foreground))] text-sm">
                      Nenhuma transacao para conciliar
                    </p>
                  </div>
                ) : (
                  <div className="divide-y divide-[hsl(var(--border))]">
                    {filteredTransactions.map((tx: BankTransactionResponse) => {
                      const statusStyle = getMatchStatusStyle(tx.reconciliation_status || 'pending');
                      const isCredit = tx.transaction_type === 'credit';
                      const isPending = tx.reconciliation_status !== 'matched';
                      return (
                        <div
                          key={tx.id}
                          className={cn(
                            'p-4 transition-colors cursor-pointer',
                            isPending
                              ? (tx as any).requires_justification
                                ? 'hover:bg-orange-500/5 border-l-2 border-l-orange-500'
                                : 'hover:bg-amber-500/5 border-l-2 border-l-amber-500/50'
                              : 'hover:bg-[hsl(var(--secondary))]/40 border-l-2 border-l-green-500/50'
                          )}
                          onClick={() => handleViewTransaction(tx)}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <p className="text-sm font-medium text-[hsl(var(--foreground))] truncate">
                                  {tx.description || '-'}
                                </p>
                                {(tx as any).requires_justification && (
                                  <span className="flex-shrink-0 px-1.5 py-0.5 text-xs bg-orange-100 text-orange-700 rounded font-medium">
                                    <AlertCircle className="w-3 h-3 inline" /> Justificar
                                  </span>
                                )}
                              </div>
                              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                                {tx.transaction_date ? formatDate(tx.transaction_date) : '-'}
                              </p>
                            </div>
                            <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
                              <span
                                className={cn(
                                  'font-mono text-sm font-semibold',
                                  isCredit ? 'text-green-500' : 'text-red-500'
                                )}
                              >
                                {isCredit ? '+' : '-'}
                                {formatCurrency(Math.abs(parseFloat(tx.amount) || 0))}
                              </span>
                              <span
                                className={cn(
                                  'inline-flex px-2 py-0.5 text-xs font-medium rounded-full border',
                                  statusStyle.badge
                                )}
                              >
                                {statusStyle.label}
                              </span>
                            </div>
                          </div>

                          {isPending && (
                            <div
                              className="flex items-center gap-2 mt-3"
                              onClick={(e) => e.stopPropagation()}
                            >
                              {(tx as any).requires_justification ? (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  className="text-xs h-7 px-3 border-orange-500/40 text-orange-600 hover:bg-orange-500/10"
                                  onClick={() => handleViewTransaction(tx)}
                                >
                                  📝 Justificar
                                </Button>
                              ) : (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  className="text-xs h-7 px-3 border-green-500/40 text-green-600 hover:bg-green-500/10"
                                >
                                  <Check className="w-3 h-3 mr-1" />
                                  Conciliar
                                </Button>
                              )}
                              <Button
                                variant="outline"
                                size="sm"
                                className="text-xs h-7 px-3 text-blue-600 border-blue-500/40 hover:bg-blue-500/10"
                              >
                                <Plus className="w-3 h-3 mr-1" />
                                Criar Lancamento
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-xs h-7 px-3 text-[hsl(var(--muted-foreground))]"
                              >
                                <MinusCircle className="w-3 h-3 mr-1" />
                                Ignorar
                              </Button>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Lado direito: Lancamentos do sistema */}
            <Card>
              <CardContent className="p-0">
                <div className="p-4 border-b border-[hsl(var(--border))]">
                  <h2 className="font-semibold text-[hsl(var(--foreground))]">
                    Lancamentos do Sistema
                  </h2>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    Vincule os lancamentos financeiros as transacoes bancarias
                  </p>
                </div>

                <div className="p-6 text-center">
                  <GitMerge className="w-10 h-10 text-[hsl(var(--muted-foreground))] mx-auto mb-3" />
                  <p className="text-sm text-[hsl(var(--muted-foreground))]">
                    Selecione uma transacao bancaria ao lado para visualizar
                    sugestoes de lancamentos vinculados.
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════
          TAB 4 — Importar OFX
      ══════════════════════════════════════════════════════════════════════ */}
      {activeTab === 'import-ofx' && (
        <div className="space-y-5">
          <Card>
            <CardContent className="p-6 space-y-6">
              <div>
                <h2 className="text-base font-semibold text-[hsl(var(--foreground))]">
                  Importar Extrato OFX
                </h2>
                <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1">
                  Importe arquivos .OFX exportados do seu banco para sincronizar
                  transacoes manualmente.
                </p>
              </div>

              {/* Drag & Drop zone */}
              <div
                onDrop={handleDrop}
                onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
                onDragLeave={() => setIsDragOver(false)}
                className={cn(
                  'border-2 border-dashed rounded-xl p-10 text-center transition-colors cursor-pointer',
                  isDragOver
                    ? 'border-[hsl(var(--primary))] bg-[hsl(var(--primary))]/5'
                    : 'border-[hsl(var(--border))] hover:border-[hsl(var(--primary))]/50 hover:bg-[hsl(var(--secondary))]/50'
                )}
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload
                  className={cn(
                    'w-10 h-10 mx-auto mb-3 transition-colors',
                    isDragOver
                      ? 'text-[hsl(var(--primary))]'
                      : 'text-[hsl(var(--muted-foreground))]'
                  )}
                />
                <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                  Arraste e solte o arquivo OFX aqui
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
                  ou clique para selecionar — apenas .ofx
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".ofx,.OFX"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleImportOFX(file);
                  }}
                />
              </div>

              {/* Preview do arquivo selecionado */}
              {ofxPreview && (
                <div className="flex items-center gap-3 p-4 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--secondary))]/50">
                  <div className="w-9 h-9 rounded-lg bg-blue-500/10 flex items-center justify-center flex-shrink-0">
                    <FileText className="w-4 h-4 text-blue-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-[hsl(var(--foreground))] truncate">
                      {ofxPreview.name}
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">
                      {ofxPreview.size}
                    </p>
                  </div>
                  {importOFX.isPending ? (
                    <div className="flex items-center gap-1.5 text-xs text-[hsl(var(--muted-foreground))]">
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Importando...
                    </div>
                  ) : importOFX.isSuccess ? (
                    <span className="flex items-center gap-1.5 text-xs text-green-600">
                      <CheckCircle2 className="w-4 h-4" />
                      Importado
                    </span>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setOfxPreview(null)}
                    >
                      <X className="w-4 h-4" />
                    </Button>
                  )}
                </div>
              )}

              {/* Instrucoes */}
              <div className="rounded-lg border border-[hsl(var(--border))] p-4 space-y-3">
                <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                  Como exportar o arquivo OFX:
                </p>
                <ul className="space-y-2 text-sm text-[hsl(var(--muted-foreground))]">
                  <li className="flex items-start gap-2">
                    <span className="w-5 h-5 rounded-full bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))] text-xs flex items-center justify-center flex-shrink-0 mt-0.5 font-semibold">
                      1
                    </span>
                    Acesse o internet banking do Banco Inter
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="w-5 h-5 rounded-full bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))] text-xs flex items-center justify-center flex-shrink-0 mt-0.5 font-semibold">
                      2
                    </span>
                    Va em Extrato e selecione o periodo desejado
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="w-5 h-5 rounded-full bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))] text-xs flex items-center justify-center flex-shrink-0 mt-0.5 font-semibold">
                      3
                    </span>
                    Exporte ou baixe o arquivo no formato OFX
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="w-5 h-5 rounded-full bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))] text-xs flex items-center justify-center flex-shrink-0 mt-0.5 font-semibold">
                      4
                    </span>
                    Arraste o arquivo para a area acima ou clique para selecionar
                  </li>
                </ul>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── Modals ──────────────────────────────────────────────────────────── */}
      <BankAccountFormModal
        isOpen={showAccountModal}
        onClose={() => setShowAccountModal(false)}
        onSubmit={handleCreateAccount}
        isLoading={createBankAccount.isPending}
      />

      <BankTransactionDetailModal
        isOpen={showTransactionDetail}
        onClose={() => {
          setShowTransactionDetail(false);
          setSelectedTransaction(null);
        }}
        transaction={selectedTransaction}
        onSuccess={() => {
          setShowTransactionDetail(false);
          setSelectedTransaction(null);
          refetch();
        }}
      />
    </div>
  );
}
