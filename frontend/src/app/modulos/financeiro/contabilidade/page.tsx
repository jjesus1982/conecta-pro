'use client';

import { Calculator, Search, RefreshCw, Plus, MoreHorizontal, Eye, AlertCircle, BookOpen, ArrowLeft, ListTree, Target, FileSpreadsheet } from 'lucide-react';
import { useState } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import {
  useAccountingAccounts,
  useCostCenters,
  useJournalEntries,
  useTrialBalance,
  useCreateJournalEntry,
} from '@/hooks/financial/useFinancial';
import { useListChartsApiV1FinancialAccountingAccountingChartsGet as useAccountingCharts } from '@/types/generated/financial/financial-accounting/financial-accounting';
import type { AccountingAccountListResponse } from '@/types/generated/financial/models/accountingAccountListResponse';
import type { JournalEntryListResponse } from '@/types/generated/financial/models/journalEntryListResponse';
import type { JournalEntryCreate } from '@/types/generated/financial/models/journalEntryCreate';
import { JournalEntryFormModal } from '@/components/financeiro/journal-entry-form-modal';

type TabType = 'accounts' | 'cost-centers' | 'entries' | 'balance';

const formatCurrency = (value: number | undefined | null) => {
  if (value == null) return 'R$ 0,00';
  return value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
};

const formatDate = (date: string | undefined | null) => {
  if (!date) return '-';
  return new Date(date).toLocaleDateString('pt-BR');
};

const getAccountTypeColor = (type: string) => {
  switch ((type || '').toUpperCase()) {
    case 'ASSET':
      return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
    case 'LIABILITY':
      return 'bg-red-500/10 text-red-500 border-red-500/20';
    case 'REVENUE':
      return 'bg-green-500/10 text-green-500 border-green-500/20';
    case 'EXPENSE':
    case 'COST':
      return 'bg-orange-500/10 text-orange-500 border-orange-500/20';
    case 'EQUITY':
      return 'bg-purple-500/10 text-purple-500 border-purple-500/20';
    default:
      return 'bg-gray-500/10 text-gray-500 border-gray-500/20';
  }
};

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  asset: 'Ativo', ASSET: 'Ativo',
  liability: 'Passivo', LIABILITY: 'Passivo',
  revenue: 'Receita', REVENUE: 'Receita',
  expense: 'Despesa', EXPENSE: 'Despesa', COST: 'Custo',
  equity: 'Patrimônio Líquido', EQUITY: 'Patrimônio Líquido',
};

const NATURE_LABELS: Record<string, string> = {
  debit: 'Devedora',
  credit: 'Credora',
};

export default function ContabilidadePage() {
  const [activeTab, setActiveTab] = useState<TabType>('accounts');
  const [searchTerm, setSearchTerm] = useState('');
  const [showFormModal, setShowFormModal] = useState(false);

  const { data: chartsData } = useAccountingCharts({});
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const activeChartId: string = (Array.isArray(chartsData) && chartsData.length > 0) ? (chartsData as any[])[0]?.id ?? '' : '';

  const { data: accountsRaw, isLoading: loadingAccounts, refetch: refetchAccounts } = useAccountingAccounts({ chart_id: activeChartId }, { query: { enabled: !!activeChartId } });
  const { data: costCentersRaw, isLoading: loadingCostCenters, refetch: refetchCostCenters } = useCostCenters();
  const { data: entriesRaw, isLoading: loadingEntries, refetch: refetchEntries } = useJournalEntries(undefined);
  const { data: trialBalanceRaw, isLoading: loadingBalance, refetch: refetchBalance } = useTrialBalance('');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const accounts: any[] = Array.isArray(accountsRaw) ? (accountsRaw as any[]) : ((accountsRaw as any)?.items ?? []);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const costCenters: any[] = (costCentersRaw as any)?.items ?? [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const entries: any[] = (entriesRaw as any)?.items ?? [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const trialBalance: any[] = Array.isArray(trialBalanceRaw) ? trialBalanceRaw : ((trialBalanceRaw as any)?.items ?? []);
  const createEntry = useCreateJournalEntry();

  const isLoading =
    activeTab === 'accounts' ? loadingAccounts :
    activeTab === 'cost-centers' ? loadingCostCenters :
    activeTab === 'entries' ? loadingEntries :
    loadingBalance;

  const handleRefresh = () => {
    if (activeTab === 'accounts') refetchAccounts();
    else if (activeTab === 'cost-centers') refetchCostCenters();
    else if (activeTab === 'entries') refetchEntries();
    else refetchBalance();
  };

  const handleFormSubmit = async (data: JournalEntryCreate) => {
    try {
      await createEntry.mutateAsync({ data });
      setShowFormModal(false);
      // refetch() removido - mutation já invalida queries automaticamente
    } catch (error) {
      void error;
    }
  };

  // Filter functions
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const filteredAccounts = accounts.filter((acc: any) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      acc.code?.toLowerCase().includes(term) ||
      acc.name?.toLowerCase().includes(term)
    );
  });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const filteredCostCenters = costCenters.filter((cc: any) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      cc.code?.toLowerCase().includes(term) ||
      cc.name?.toLowerCase().includes(term) ||
      cc.responsible?.toLowerCase().includes(term)
    );
  });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const filteredEntries = entries.filter((entry: any) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      entry.description?.toLowerCase().includes(term) ||
      entry.debit_account?.toLowerCase().includes(term) ||
      entry.credit_account?.toLowerCase().includes(term)
    );
  });

  const balanceData = trialBalance;

  // A API do lançamento traz total_debit/total_credit (string) + lines[] com account_id e
  // debit_amount/credit_amount — a tela lia entry.debit_account/amount (inexistentes) → tudo "-"/R$0.
  const accMap: Record<string, string> = {};
  for (const a of (accounts as any[])) accMap[a.id] = a.code ? `${a.code} — ${a.name ?? ''}`.trim() : (a.name ?? '');
  const contasDe = (entry: any, tipo: 'debit' | 'credit'): string => {
    const key = tipo === 'debit' ? 'debit_amount' : 'credit_amount';
    const codes = (entry?.lines ?? [])
      .filter((l: any) => Number(l[key] ?? 0) > 0)
      .map((l: any) => accMap[l.account_id] ?? l.account_code ?? l.account_id ?? '—');
    return codes.length ? Array.from(new Set(codes)).join(', ') : '—';
  };
  const valorEntry = (entry: any): number => Number(entry?.total_debit ?? entry?.total_credit ?? entry?.amount ?? 0);

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
                <div className="w-10 h-10 rounded-lg bg-teal-500/10 flex items-center justify-center">
                  <Calculator className="w-5 h-5 text-teal-500" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                    Contabilidade
                  </h1>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    Plano de contas, lancamentos e balancetes
                  </p>
                </div>
              </div>
            </div>
            {activeTab === 'entries' && (
              <Button variant="primary" size="sm" onClick={() => setShowFormModal(true)}>
                <Plus className="w-4 h-4 mr-2" />
                Novo Lancamento
              </Button>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Tabs */}
        <div className="flex items-center gap-1 mb-6 bg-[hsl(var(--muted))] rounded-lg p-1 w-fit">
          <button
            onClick={() => setActiveTab('accounts')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'accounts'
                ? 'bg-[hsl(var(--card))] text-[hsl(var(--foreground))] shadow-sm'
                : 'text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
            }`}
          >
            Plano de Contas
          </button>
          <button
            onClick={() => setActiveTab('cost-centers')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'cost-centers'
                ? 'bg-[hsl(var(--card))] text-[hsl(var(--foreground))] shadow-sm'
                : 'text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
            }`}
          >
            Centros de Custo
          </button>
          <button
            onClick={() => setActiveTab('entries')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'entries'
                ? 'bg-[hsl(var(--card))] text-[hsl(var(--foreground))] shadow-sm'
                : 'text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
            }`}
          >
            Lancamentos
          </button>
          <button
            onClick={() => setActiveTab('balance')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'balance'
                ? 'bg-[hsl(var(--card))] text-[hsl(var(--foreground))] shadow-sm'
                : 'text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
            }`}
          >
            Balancete
          </button>
        </div>

        {/* Search and Filters */}
        <div className="flex flex-col sm:flex-row gap-4 mb-6">
          <div className="flex-1">
            <Input
              type="search"
              placeholder="Buscar..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              icon={<Search className="w-4 h-4" />}
            />
          </div>
          <Button variant="outline" onClick={handleRefresh} disabled={isLoading}>
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
        </div>

        {/* Loading state */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-pulse-slow text-[hsl(var(--primary))]">
              <Calculator className="w-8 h-8" />
            </div>
          </div>
        )}

        {/* Accounts Table */}
        {!isLoading && activeTab === 'accounts' && (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Codigo</TableHead>
                  <TableHead>Nome</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Natureza</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                {filteredAccounts.map((acc: any) => (
                  <TableRow key={acc.id}>
                    <TableCell className="font-mono font-medium">{acc.code || '-'}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <ListTree className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                        {acc.name || '-'}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge className={getAccountTypeColor(acc.type || acc.account_type)}>
                        {ACCOUNT_TYPE_LABELS[acc.type || acc.account_type] || acc.type || '-'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-[hsl(var(--foreground))]">
                        {NATURE_LABELS[acc.nature] || acc.nature || '-'}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">
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
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {filteredAccounts.length === 0 && (
              <div className="text-center py-12">
                <ListTree className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhuma conta encontrada
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1">
                  {searchTerm ? 'Tente ajustar os filtros de busca' : 'Nenhuma conta cadastrada no plano de contas'}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Cost Centers Table */}
        {!isLoading && activeTab === 'cost-centers' && (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Codigo</TableHead>
                  <TableHead>Nome</TableHead>
                  <TableHead>Responsavel</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                {filteredCostCenters.map((cc: any) => (
                  <TableRow key={cc.id}>
                    <TableCell className="font-mono font-medium">{cc.code || '-'}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Target className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                        {cc.name || '-'}
                      </div>
                    </TableCell>
                    <TableCell>{cc.responsible || '-'}</TableCell>
                    <TableCell>
                      <Badge className={
                        cc.status === 'active' || cc.is_active
                          ? 'bg-green-500/10 text-green-500 border-green-500/20'
                          : 'bg-gray-500/10 text-gray-500 border-gray-500/20'
                      }>
                        {cc.status === 'active' || cc.is_active ? 'Ativo' : 'Inativo'}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {filteredCostCenters.length === 0 && (
              <div className="text-center py-12">
                <Target className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhum centro de custo encontrado
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1">
                  {searchTerm ? 'Tente ajustar os filtros de busca' : 'Nenhum centro de custo cadastrado'}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Journal Entries Table */}
        {!isLoading && activeTab === 'entries' && (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Data</TableHead>
                  <TableHead>Descricao</TableHead>
                  <TableHead>Debito</TableHead>
                  <TableHead>Credito</TableHead>
                  <TableHead>Valor</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                {filteredEntries.map((entry: any) => (
                  <TableRow key={entry.id}>
                    <TableCell>{formatDate(entry.date || entry.created_at)}</TableCell>
                    <TableCell className="max-w-[200px] truncate">{entry.description || '-'}</TableCell>
                    <TableCell className="font-mono text-sm">{contasDe(entry, 'debit')}</TableCell>
                    <TableCell className="font-mono text-sm">{contasDe(entry, 'credit')}</TableCell>
                    <TableCell className="font-medium">{formatCurrency(valorEntry(entry))}</TableCell>
                    <TableCell className="text-right">
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
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {filteredEntries.length === 0 && (
              <div className="text-center py-12">
                <BookOpen className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhum lancamento encontrado
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1 mb-4">
                  {searchTerm ? 'Tente ajustar os filtros de busca' : 'Registre o primeiro lancamento contabil'}
                </p>
                {!searchTerm && (
                  <Button variant="primary" onClick={() => setShowFormModal(true)}>
                    <Plus className="w-4 h-4 mr-2" />
                    Novo Lancamento
                  </Button>
                )}
              </div>
            )}
          </div>
        )}

        {/* Trial Balance Table */}
        {!isLoading && activeTab === 'balance' && (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Conta</TableHead>
                  <TableHead className="text-right">Saldo Anterior</TableHead>
                  <TableHead className="text-right">Debitos</TableHead>
                  <TableHead className="text-right">Creditos</TableHead>
                  <TableHead className="text-right">Saldo Atual</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                {balanceData.map((item: any, index: number) => (
                  <TableRow key={item.id || index}>
                    <TableCell>
                      <div>
                        <p className="font-medium text-[hsl(var(--foreground))]">
                          {item.account_name || item.name || '-'}
                        </p>
                        <p className="text-xs font-mono text-[hsl(var(--muted-foreground))]">
                          {item.account_code || item.code || ''}
                        </p>
                      </div>
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {formatCurrency(item.previous_balance)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-blue-500">
                      {formatCurrency(item.total_debits || item.debits)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-red-500">
                      {formatCurrency(item.total_credits || item.credits)}
                    </TableCell>
                    <TableCell className="text-right font-mono font-bold">
                      <span className={
                        (item.current_balance || item.balance || 0) >= 0
                          ? 'text-green-500'
                          : 'text-red-500'
                      }>
                        {formatCurrency(item.current_balance || item.balance)}
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {balanceData.length === 0 && (
              <div className="text-center py-12">
                <FileSpreadsheet className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Balancete vazio
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1">
                  Registre lancamentos contabeis para gerar o balancete
                </p>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Modals */}
      <JournalEntryFormModal
        isOpen={showFormModal}
        onClose={() => setShowFormModal(false)}
        onSubmit={handleFormSubmit}
        isLoading={createEntry.isPending}
      />
    </div>
  );
}
