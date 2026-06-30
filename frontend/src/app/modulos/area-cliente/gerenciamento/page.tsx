'use client';

import { useState, useMemo, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Key, RefreshCw, Copy, Check, Power, FileText, Search,
  Shield, AlertTriangle, Clock, Eye, X, Loader2, Users,
  ExternalLink, ChevronLeft, ChevronRight, Filter,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const API = '/api/v1/portal/access-management';

function getHeaders(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

// ─── Types ──────────────────────────────────────────────────────────────────

interface ClientAccess {
  client_id: string;
  nome: string;
  cnpj: string;
  email: string;
  portal_ativo: boolean;
  portal_username: string;
  ultimo_acesso: string | null;
  data_criacao: string | null;
}

interface LogEntry {
  id: string;
  acao: string;
  detalhes: string;
  ip: string | null;
  dispositivo: string | null;
  data: string | null;
}

interface ProvisionResult {
  client_id: string;
  nome: string;
  cnpj: string;
  portal_username: string;
  senha_temporaria: string;
  portal_url: string;
  primeiro_acesso: boolean;
  instrucoes: string;
}

interface ToggleResult {
  client_id: string;
  nome: string;
  portal_ativo: boolean;
  acao: string;
}

interface LogsResult {
  client_id: string;
  total: number;
  logs: LogEntry[];
}

interface PreviewResult {
  client_id: string;
  nome: string;
  preview_url: string;
  expira_em: string;
  aviso: string;
}

type StatusFilter = 'all' | 'active' | 'inactive' | 'pending';

// ─── API functions ──────────────────────────────────────────────────────────

async function fetchClients(): Promise<ClientAccess[]> {
  const res = await fetch(API, { headers: getHeaders() });
  if (!res.ok) throw new Error('Erro ao carregar clientes');
  return res.json();
}

async function provisionAccess(clientId: string): Promise<ProvisionResult> {
  const res = await fetch(`${API}/${clientId}/provision`, { method: 'POST', headers: getHeaders() });
  if (!res.ok) throw new Error('Erro ao provisionar acesso');
  return res.json();
}

async function toggleAccess(clientId: string): Promise<ToggleResult> {
  const res = await fetch(`${API}/${clientId}/toggle`, { method: 'POST', headers: getHeaders() });
  if (!res.ok) throw new Error('Erro ao alterar acesso');
  return res.json();
}

async function fetchLogs(clientId: string): Promise<LogsResult> {
  const res = await fetch(`${API}/${clientId}/logs`, { headers: getHeaders() });
  if (!res.ok) throw new Error('Erro ao carregar logs');
  return res.json();
}

async function generatePreviewToken(clientId: string): Promise<PreviewResult> {
  const res = await fetch(`${API}/${clientId}/preview-token`, { method: 'POST', headers: getHeaders() });
  if (!res.ok) throw new Error('Erro ao gerar preview');
  return res.json();
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function fmtDate(iso: string | null): string {
  if (!iso) return '\u2014';
  const d = new Date(iso);
  return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

function getClientStatus(client: ClientAccess): StatusFilter {
  if (!client.portal_ativo) return 'inactive';
  if (!client.ultimo_acesso) return 'pending';
  return 'active';
}

function StatusBadge({ client }: { client: ClientAccess }) {
  const status = getClientStatus(client);
  if (status === 'inactive') {
    return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400">Inativo</span>;
  }
  if (status === 'pending') {
    return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400">Aguardando</span>;
  }
  return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">Ativo</span>;
}

function SkeletonRow() {
  return (
    <tr className="border-b animate-pulse">
      <td className="p-3"><div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-48" /><div className="h-3 bg-gray-100 dark:bg-gray-800 rounded w-32 mt-1" /></td>
      <td className="p-3"><div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-36" /></td>
      <td className="p-3"><div className="h-5 bg-gray-200 dark:bg-gray-700 rounded-full w-20" /></td>
      <td className="p-3"><div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-28" /></td>
      <td className="p-3"><div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-24 ml-auto" /></td>
    </tr>
  );
}

const PAGE_SIZE = 15;

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'Todos' },
  { value: 'active', label: 'Ativos' },
  { value: 'inactive', label: 'Inativos' },
  { value: 'pending', label: 'Aguardando' },
];

// ─── Toast component ────────────────────────────────────────────────────────

interface ToastState {
  message: string;
  type: 'success' | 'error' | 'info';
}

function Toast({ toast, onClose }: { toast: ToastState; onClose: () => void }) {
  const bgColor = toast.type === 'error'
    ? 'bg-red-600'
    : toast.type === 'success'
      ? 'bg-green-600'
      : 'bg-gray-900';

  return (
    <div className={`fixed bottom-8 right-4 ${bgColor} text-white px-4 py-3 rounded-lg text-sm shadow-lg z-50 animate-in fade-in slide-in-from-bottom-2 flex items-center gap-3 max-w-sm`}>
      <span className="flex-1">{toast.message}</span>
      <button type="button" onClick={onClose} className="text-white/70 hover:text-white">
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

// ─── Page ───────────────────────────────────────────────────────────────────

export default function GerenciamentoAcessosPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [page, setPage] = useState(1);
  const [provisionModal, setProvisionModal] = useState<ProvisionResult | null>(null);
  const [logsModal, setLogsModal] = useState<{ clientId: string; nome: string; logs: LogEntry[] } | null>(null);
  const [previewModal, setPreviewModal] = useState<PreviewResult | null>(null);
  const [copied, setCopied] = useState(false);
  const [toast, setToast] = useState<ToastState | null>(null);

  // ─── Queries ──────────────────────────────────────────────────────────────

  const {
    data: clients = [],
    isLoading,
    isRefetching,
    refetch,
  } = useQuery<ClientAccess[]>({
    queryKey: ['access-management', 'clients'],
    queryFn: fetchClients,
    staleTime: 60_000,
  });

  // ─── Mutations ────────────────────────────────────────────────────────────

  const provisionMutation = useMutation({
    mutationFn: provisionAccess,
    onSuccess: (data) => {
      setProvisionModal(data);
      queryClient.invalidateQueries({ queryKey: ['access-management', 'clients'] });
      showToast('Acesso provisionado com sucesso', 'success');
    },
    onError: () => showToast('Erro ao provisionar acesso', 'error'),
  });

  const toggleMutation = useMutation({
    mutationFn: toggleAccess,
    onSuccess: (data) => {
      showToast(`Acesso ${data.acao} para ${data.nome}`, 'success');
      queryClient.invalidateQueries({ queryKey: ['access-management', 'clients'] });
    },
    onError: () => showToast('Erro ao alterar acesso', 'error'),
  });

  const logsMutation = useMutation({
    mutationFn: fetchLogs,
    onSuccess: (data) => {
      const client = clients.find(c => c.client_id === data.client_id);
      setLogsModal({ clientId: data.client_id, nome: client?.nome ?? '', logs: data.logs });
    },
    onError: () => showToast('Erro ao carregar logs', 'error'),
  });

  const previewMutation = useMutation({
    mutationFn: generatePreviewToken,
    onSuccess: (data) => {
      setPreviewModal(data);
      // abre o portal direto em nova aba, logado como o condomínio (modo admin)
      if (typeof window !== 'undefined' && data.preview_url) window.open(data.preview_url, '_blank');
    },
    onError: () => showToast('Erro ao gerar preview', 'error'),
  });

  // ─── Derived state ───────────────────────────────────────────────────────

  const filtered = useMemo(() => {
    let result = clients;

    // Status filter
    if (statusFilter !== 'all') {
      result = result.filter(c => getClientStatus(c) === statusFilter);
    }

    // Search filter
    if (search) {
      const s = search.toLowerCase();
      result = result.filter(c =>
        c.nome.toLowerCase().includes(s) ||
        c.cnpj.toLowerCase().includes(s) ||
        c.email.toLowerCase().includes(s),
      );
    }

    return result;
  }, [clients, search, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const paginatedClients = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  const activeCount = clients.filter(c => c.portal_ativo).length;
  const pendingCount = clients.filter(c => c.portal_ativo && !c.ultimo_acesso).length;

  const busyId = provisionMutation.isPending
    ? (provisionMutation.variables ?? null)
    : toggleMutation.isPending
      ? (toggleMutation.variables ?? null)
      : logsMutation.isPending
        ? (logsMutation.variables ?? null)
        : previewMutation.isPending
          ? (previewMutation.variables ?? null)
          : null;

  // ─── Handlers ─────────────────────────────────────────────────────────────

  const showToast = useCallback((message: string, type: 'success' | 'error' | 'info' = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 5000);
  }, []);

  function handleToggle(clientId: string, nome: string, ativo: boolean) {
    if (ativo && !confirm(`Desativar acesso de "${nome}" ao portal?`)) return;
    toggleMutation.mutate(clientId);
  }

  async function handleCopy() {
    if (!provisionModal) return;
    const text = [
      'Portal do Cliente \u2014 Conecta PRO',
      `Login: ${provisionModal.portal_username}`,
      `Senha: ${provisionModal.senha_temporaria}`,
      `URL: ${provisionModal.portal_url}`,
    ].join('\n');
    await navigator.clipboard.writeText(text);
    setCopied(true);
    showToast('Credenciais copiadas para a area de transferencia', 'success');
    setTimeout(() => setCopied(false), 2000);
  }

  function closeProvisionModal() {
    setProvisionModal(null);
    setCopied(false);
  }

  // Reset page when filters change
  function handleSearchChange(value: string) {
    setSearch(value);
    setPage(1);
  }

  function handleStatusFilterChange(value: StatusFilter) {
    setStatusFilter(value);
    setPage(1);
  }

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Shield className="h-6 w-6 text-indigo-600" />
            Gerenciamento de Acessos
          </h1>
          <p className="text-sm text-muted-foreground mt-1">Portal do Cliente \u2014 provisionar, ativar e auditar</p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <span className="px-3 py-1 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400">
            <Users className="w-3 h-3 inline mr-1" />{activeCount}/{clients.length} ativos
          </span>
          {pendingCount > 0 && (
            <span className="px-3 py-1 rounded-full text-xs font-semibold bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400">
              {pendingCount} aguardando 1o acesso
            </span>
          )}
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isLoading || isRefetching}>
            <RefreshCw className={`h-4 w-4 mr-1 ${isRefetching ? 'animate-spin' : ''}`} /> Atualizar
          </Button>
        </div>
      </div>

      {/* Search + Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Buscar por nome, CNPJ ou email..."
            value={search}
            onChange={e => handleSearchChange(e.target.value)}
            className="pl-10"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          {STATUS_OPTIONS.map(opt => (
            <Button
              key={opt.value}
              variant={statusFilter === opt.value ? 'default' : 'outline'}
              size="sm"
              onClick={() => handleStatusFilterChange(opt.value)}
              className="text-xs"
            >
              {opt.label}
            </Button>
          ))}
        </div>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="text-left p-3 font-medium">Cliente</th>
                  <th className="text-left p-3 font-medium">CNPJ</th>
                  <th className="text-left p-3 font-medium">Status Portal</th>
                  <th className="text-left p-3 font-medium">Ultimo Acesso</th>
                  <th className="text-right p-3 font-medium">Ações</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <>
                    <SkeletonRow />
                    <SkeletonRow />
                    <SkeletonRow />
                    <SkeletonRow />
                    <SkeletonRow />
                  </>
                ) : paginatedClients.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="p-12 text-center">
                      <Users className="h-10 w-10 text-muted-foreground/40 mx-auto mb-3" />
                      <p className="text-muted-foreground font-medium">
                        {search || statusFilter !== 'all'
                          ? 'Nenhum cliente encontrado para os filtros aplicados'
                          : 'Nenhum cliente cadastrado'}
                      </p>
                      {(search || statusFilter !== 'all') && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="mt-2"
                          onClick={() => { setSearch(''); setStatusFilter('all'); setPage(1); }}
                        >
                          Limpar filtros
                        </Button>
                      )}
                    </td>
                  </tr>
                ) : paginatedClients.map(c => (
                  <tr key={c.client_id} className="border-b hover:bg-muted/30 transition-colors">
                    <td className="p-3">
                      <div className="font-medium">{c.nome}</div>
                      <div className="text-xs text-muted-foreground">{c.email}</div>
                    </td>
                    <td className="p-3 font-mono text-xs">{c.cnpj}</td>
                    <td className="p-3"><StatusBadge client={c} /></td>
                    <td className="p-3 text-muted-foreground text-xs">{fmtDate(c.ultimo_acesso)}</td>
                    <td className="p-3">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost" size="sm"
                          onClick={() => provisionMutation.mutate(c.client_id)}
                          disabled={busyId === c.client_id}
                          title="Provisionar ou resetar senha"
                        >
                          {busyId === c.client_id && provisionMutation.isPending
                            ? <Loader2 className="h-4 w-4 animate-spin" />
                            : <Key className="h-4 w-4" />}
                        </Button>
                        <Button
                          variant="ghost" size="sm"
                          onClick={() => handleToggle(c.client_id, c.nome, c.portal_ativo)}
                          disabled={busyId === c.client_id}
                          title={c.portal_ativo ? 'Desativar acesso' : 'Ativar acesso'}
                        >
                          <Power className={`h-4 w-4 ${c.portal_ativo ? 'text-green-600' : 'text-gray-400'}`} />
                        </Button>
                        <Button
                          variant="ghost" size="sm"
                          onClick={() => logsMutation.mutate(c.client_id)}
                          disabled={busyId === c.client_id}
                          title="Ver logs de acesso"
                        >
                          <FileText className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost" size="sm"
                          onClick={() => previewMutation.mutate(c.client_id)}
                          disabled={busyId === c.client_id || !c.portal_ativo}
                          title="Visualizar como cliente"
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {!isLoading && filtered.length > PAGE_SIZE && (
            <div className="flex items-center justify-between px-4 py-3 border-t">
              <p className="text-xs text-muted-foreground">
                Mostrando {((safePage - 1) * PAGE_SIZE) + 1}\u2013{Math.min(safePage * PAGE_SIZE, filtered.length)} de {filtered.length} clientes
              </p>
              <div className="flex items-center gap-1">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={safePage <= 1}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                {Array.from({ length: totalPages }, (_, i) => i + 1)
                  .filter(p => p === 1 || p === totalPages || Math.abs(p - safePage) <= 1)
                  .map((p, idx, arr) => {
                    const prev = arr[idx - 1];
                    const showEllipsis = prev !== undefined && p - prev > 1;
                    return (
                      <span key={p} className="flex items-center">
                        {showEllipsis && <span className="px-1 text-muted-foreground text-xs">...</span>}
                        <Button
                          variant={p === safePage ? 'default' : 'outline'}
                          size="sm"
                          className="min-w-[32px]"
                          onClick={() => setPage(p)}
                        >
                          {p}
                        </Button>
                      </span>
                    );
                  })}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={safePage >= totalPages}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Modal Provisionar */}
      {provisionModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={closeProvisionModal}>
          <div className="bg-white dark:bg-gray-900 rounded-xl max-w-md w-full p-6 space-y-4 shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <Key className="h-5 w-5 text-indigo-600" /> Acesso Provisionado
              </h3>
              <button type="button" onClick={closeProvisionModal} className="text-gray-400 hover:text-gray-600">
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3 text-sm text-amber-800 dark:text-amber-300 flex gap-2">
              <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
              <span>Esta senha sera exibida apenas uma vez. Copie antes de fechar.</span>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-xs text-muted-foreground">Cliente</label>
                <p className="font-medium">{provisionModal.nome}</p>
              </div>
              <div>
                <label className="text-xs text-muted-foreground">CNPJ</label>
                <p className="font-mono">{provisionModal.cnpj}</p>
              </div>
              <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 space-y-2">
                <div>
                  <label className="text-xs text-muted-foreground">Login (CNPJ ou usuario)</label>
                  <p className="font-mono font-bold text-lg">{provisionModal.portal_username}</p>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Senha temporaria</label>
                  <p className="font-mono font-bold text-lg text-indigo-600">{provisionModal.senha_temporaria}</p>
                </div>
              </div>
              <div>
                <label className="text-xs text-muted-foreground">URL do portal</label>
                <p className="text-sm text-blue-600">{provisionModal.portal_url}</p>
              </div>
            </div>

            <Button onClick={handleCopy} className="w-full" variant={copied ? 'default' : 'outline'}>
              {copied ? <><Check className="h-4 w-4 mr-1" /> Copiado!</> : <><Copy className="h-4 w-4 mr-1" /> Copiar credenciais</>}
            </Button>
          </div>
        </div>
      )}

      {/* Modal Logs */}
      {logsModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setLogsModal(null)}>
          <div className="bg-white dark:bg-gray-900 rounded-xl max-w-2xl w-full p-6 max-h-[80vh] overflow-y-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <Clock className="h-5 w-5" /> Logs \u2014 {logsModal.nome}
              </h3>
              <button type="button" onClick={() => setLogsModal(null)} className="text-gray-400 hover:text-gray-600">
                <X className="h-5 w-5" />
              </button>
            </div>
            {logsModal.logs.length === 0 ? (
              <div className="text-center py-12">
                <FileText className="h-10 w-10 text-muted-foreground/40 mx-auto mb-3" />
                <p className="text-muted-foreground font-medium">Nenhum log registrado</p>
                <p className="text-xs text-muted-foreground mt-1">Os logs aparecerao quando o cliente acessar o portal.</p>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2">Data/Hora</th>
                    <th className="pb-2">Acao</th>
                    <th className="pb-2">IP</th>
                    <th className="pb-2">Detalhes</th>
                  </tr>
                </thead>
                <tbody>
                  {logsModal.logs.map(l => (
                    <tr key={l.id} className="border-b">
                      <td className="py-2 text-xs text-muted-foreground whitespace-nowrap">{fmtDate(l.data)}</td>
                      <td className="py-2 font-medium">{l.acao}</td>
                      <td className="py-2 font-mono text-xs">{l.ip || '\u2014'}</td>
                      <td className="py-2 text-xs text-muted-foreground max-w-[200px] truncate">{l.detalhes || '\u2014'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* Modal Preview */}
      {previewModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setPreviewModal(null)}>
          <div className="bg-white dark:bg-gray-900 rounded-xl max-w-md w-full p-6 space-y-4 shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <Eye className="h-5 w-5 text-blue-600" /> Preview do Portal
              </h3>
              <button type="button" onClick={() => setPreviewModal(null)} className="text-gray-400 hover:text-gray-600">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3 text-sm text-blue-800 dark:text-blue-300 flex gap-2">
              <Eye className="h-4 w-4 flex-shrink-0 mt-0.5" />
              <span>{previewModal.aviso}</span>
            </div>
            <div className="space-y-2">
              <div>
                <label className="text-xs text-muted-foreground">Cliente</label>
                <p className="font-medium">{previewModal.nome}</p>
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Expira em</label>
                <p className="text-sm font-medium text-amber-600">{previewModal.expira_em}</p>
              </div>
            </div>
            <a href={previewModal.preview_url} target="_blank" rel="noopener noreferrer" className="w-full">
              <Button className="w-full">
                <ExternalLink className="h-4 w-4 mr-2" /> Abrir Portal como Cliente
              </Button>
            </a>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && <Toast toast={toast} onClose={() => setToast(null)} />}
    </div>
  );
}
