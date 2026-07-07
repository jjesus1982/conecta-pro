'use client';

import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ShieldCheck,
  Search,
  FileText,
  Filter,
  MinusCircle,
  ChevronDown,
  ChevronUp,
  Clock,
  CheckCircle,
  Radio,
  XCircle as XCircleSmall,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

const API_BASE = '/api/v1/ged/certidoes';
const COLETA_BASE = '/api/v1/ged/coleta-automatica';

// ── Helpers de UI ─────────────────────────────────────────────────────────────

function showToast(msg: string, type: 'success' | 'error' = 'success') {
  const el = document.createElement('div');
  el.className = `fixed top-4 right-4 z-[9999] px-4 py-3 rounded-lg shadow-lg text-sm font-medium text-white transition-opacity ${type === 'error' ? 'bg-red-500' : 'bg-emerald-500'}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 3000);
}

function getAuthHeaders() {
  let token: string | null = null;
  try { token = localStorage.getItem('access_token') || localStorage.getItem('token'); } catch { /* noop */ }
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

function relativeTime(dateStr: string | null): string {
  if (!dateStr) return '—';
  const ms = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return 'agora mesmo';
  if (mins < 60) return `${mins} min atrás`;
  const h = Math.floor(mins / 60);
  if (h < 24) return `${h}h atrás`;
  return `${Math.floor(h / 24)}d atrás`;
}

function formatDate(dateStr: string | null) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('pt-BR');
}

function daysUntilExpiry(expiry_date: string | null): number {
  if (!expiry_date) return 9999;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const expiry = new Date(expiry_date); expiry.setHours(0, 0, 0, 0);
  return Math.ceil((expiry.getTime() - today.getTime()) / 86400000);
}

// ── Tipos ─────────────────────────────────────────────────────────────────────

interface Certificate {
  id: string;
  name: string;
  document_type: string;
  issuing_body: string | null;
  issue_date: string | null;
  expiry_date: string | null;
  status: 'valida' | 'vencida' | 'a_vencer' | 'sem_vencimento';
  file_path: string | null;
  file_url: string | null;
  notes: string | null;
  alerta_ativo: boolean;
  created_at: string | null;
  updated_at: string | null;
}

interface ParsedNotes {
  regular: boolean | null | undefined;
  fonte: string;
  situacao: string;
  cnpj_ativo_rfb?: boolean | null;
  validade_dias?: number | null;
  consultado_em?: string;
  nota?: string | null;
  mensagem?: string | null;
}

interface CertType {
  key: string;
  document_type: string;
  name: string;
  issuing_body: string;
}

interface Resumo {
  validas: number;
  vencidas: number;
  a_vencer_30d: number;
}

interface HistoryEntry {
  id: string;
  run_at: string;
  run_type: string;
  status: string;
  duration_ms: number;
  sync_novos: number;
  kits_assembled: number;
  certidoes_atualizadas: number;
  alertas_disparados: number;
  triggered_by: string;
  erros: unknown[] | null;
}

// ── Query functions ────────────────────────────────────────────────────────────

async function fetchCertidoes(): Promise<{ certidoes: Certificate[]; resumo: Resumo }> {
  const res = await fetch(API_BASE, { headers: getAuthHeaders() });
  if (!res.ok) throw new Error('Falha ao carregar certidões');
  return res.json();
}

async function fetchTipos(): Promise<{ tipos: CertType[] }> {
  const res = await fetch(`${API_BASE}/tipos`, { headers: getAuthHeaders() });
  if (!res.ok) throw new Error('Falha ao carregar tipos');
  return res.json();
}

async function fetchHistory(): Promise<HistoryEntry[]> {
  const res = await fetch(`${COLETA_BASE}/history?limit=20`, { headers: getAuthHeaders() });
  if (!res.ok) throw new Error('Falha ao carregar histórico');
  const all: HistoryEntry[] = await res.json();
  return all.filter((h) => (h.certidoes_atualizadas ?? 0) > 0).slice(0, 5);
}

async function runCnds(): Promise<unknown> {
  const res = await fetch(`${COLETA_BASE}/cnds/run`, {
    method: 'POST',
    headers: getAuthHeaders(),
  });
  if (res.status === 409) throw new Error('Atualização já em andamento. Aguarde.');
  if (!res.ok) throw new Error('Erro ao disparar atualização.');
  return res.json();
}

// ── Lógica semáforo D5.4 ──────────────────────────────────────────────────────

const SKIP_AUTOMATION = new Set(['alvara_funcionamento', 'registro_cnpj']);

const DOCUMENT_TYPE_LABELS: Record<string, string> = {
  certidao_negativa_fgts: 'FGTS — Caixa',
  certidao_negativa_federal: 'Federal — RFB/PGFN',
  certidao_negativa_inss: 'INSS — Federal',
  certidao_negativa_trabalhista: 'Trabalhista — TST',
  certidao_negativa_estadual: 'Estadual — Sefaz AM',
  certidao_negativa_municipal: 'Municipal — SEMEF',
  alvara_funcionamento: 'Alvará de Funcionamento',
  registro_cnpj: 'Registro CNPJ — RFB',
};

function parseNotes(notes: string | null): ParsedNotes | null {
  if (!notes) return null;
  try { return JSON.parse(notes) as ParsedNotes; } catch { return null; }
}

type SemaforoColor = 'verde' | 'amarelo' | 'vermelho' | 'cinza';

function getColor(c: Certificate): SemaforoColor {
  if (SKIP_AUTOMATION.has(c.document_type)) return 'cinza';
  const parsed = parseNotes(c.notes);
  const dias = daysUntilExpiry(c.expiry_date);
  if (dias < 0) return 'vermelho';
  if (parsed?.regular === false) return 'vermelho';
  if (parsed?.regular === null) return 'amarelo';
  if (dias < 7) return 'vermelho';
  if (dias < 30) return 'amarelo';
  if (parsed?.regular === true) return 'verde';
  return 'cinza';
}

const COLOR_STYLES: Record<SemaforoColor, { border: string; bg: string; badge: string; label: string }> = {
  verde:    { border: 'border-l-emerald-500', bg: 'bg-emerald-500/10', badge: 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30', label: 'Regular' },
  amarelo:  { border: 'border-l-amber-400',   bg: 'bg-amber-500/10',   badge: 'bg-amber-500/10 text-amber-500 border border-amber-500/30',       label: 'Indeterminado' },
  vermelho: { border: 'border-l-red-500',     bg: 'bg-red-500/10',     badge: 'bg-red-500/10 text-red-500 border border-red-500/30',             label: 'Irregular/Vencido' },
  cinza:    { border: 'border-l-gray-500',    bg: 'bg-gray-500/10',    badge: 'bg-gray-500/10 text-[hsl(var(--muted-foreground))] border border-gray-500/30', label: 'Manual' },
};

const COLOR_ICONS: Record<SemaforoColor, React.FC<{ className?: string }>> = {
  verde:    ({ className }) => <CheckCircle2 className={className} />,
  amarelo:  ({ className }) => <AlertTriangle className={className} />,
  vermelho: ({ className }) => <XCircle className={className} />,
  cinza:    ({ className }) => <MinusCircle className={className} />,
};

const COLOR_TEXT: Record<SemaforoColor, string> = {
  verde:    'text-emerald-500',
  amarelo:  'text-amber-500',
  vermelho: 'text-red-500',
  cinza:    'text-[hsl(var(--muted-foreground))]',
};

// ── Componente principal ───────────────────────────────────────────────────────

export default function CertidoesPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [isPolling, setIsPolling] = useState(false);

  const {
    data: certsData,
    isLoading: certsLoading,
    isError: certsError,
    error: certsErrorMsg,
    refetch: refetchCerts,
  } = useQuery({
    queryKey: ['certidoes'],
    queryFn: fetchCertidoes,
    staleTime: 30000,
  });

  const { data: tiposData } = useQuery({
    queryKey: ['certidoes-tipos'],
    queryFn: fetchTipos,
    staleTime: 300000,
  });

  const { data: historyData } = useQuery({
    queryKey: ['certidoes-history'],
    queryFn: fetchHistory,
    staleTime: 30000,
  });

  const updateMutation = useMutation({
    mutationFn: runCnds,
    onSuccess: () => {
      showToast('Atualização iniciada! Dados serão recarregados em breve.');
      setIsPolling(true);
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ['certidoes'] });
        qc.invalidateQueries({ queryKey: ['certidoes-history'] });
        setIsPolling(false);
      }, 8000);
    },
    onError: (err: Error) => {
      showToast(err.message || 'Erro de conexão.', 'error');
    },
  });

  const isUpdating = updateMutation.isPending || isPolling;

  const certificates = certsData?.certidoes ?? [];
  const resumo = certsData?.resumo ?? { validas: 0, vencidas: 0, a_vencer_30d: 0 };
  const certTypes = tiposData?.tipos ?? [];
  const history = historyData ?? [];

  const lastUpdate = useMemo(() => {
    const dates = certificates.map((c) => c.updated_at).filter(Boolean) as string[];
    return dates.length ? (dates.sort().at(-1) ?? null) : null;
  }, [certificates]);

  // ── Contagens semáforo ─────────────────────────────────────────────────────
  const semaforoCount = certificates.reduce(
    (acc, c) => { const cor = getColor(c); acc[cor] = (acc[cor] ?? 0) + 1; return acc; },
    {} as Record<SemaforoColor, number>,
  );

  // ── Tabela filtrada ────────────────────────────────────────────────────────
  const urgentCount = certificates.filter((c) => { const d = daysUntilExpiry(c.expiry_date); return d > 0 && d <= 7; }).length;

  const filtered = certificates
    .filter((c) => {
      if (filterType !== 'all' && c.document_type !== filterType) return false;
      if (filterStatus === 'valida' && c.status !== 'valida') return false;
      if (filterStatus === 'vencendo' && c.status !== 'a_vencer') return false;
      if (filterStatus === 'vencida' && c.status !== 'vencida') return false;
      if (search) {
        const q = search.toLowerCase();
        return (c.name || '').toLowerCase().includes(q) || (c.document_type || '').toLowerCase().includes(q) || (c.issuing_body || '').toLowerCase().includes(q);
      }
      return true;
    })
    .sort((a, b) => daysUntilExpiry(a.expiry_date) - daysUntilExpiry(b.expiry_date));

  const toggleExpanded = (id: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(id)) { next.delete(id); } else { next.add(id); }
      return next;
    });
  };

  if (certsLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-4 w-48" />
          </div>
          <Skeleton className="h-10 w-36" />
        </div>
        <div className="flex gap-4">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-5 w-28" />)}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => <Skeleton key={i} className="h-28 w-full rounded-lg" />)}
        </div>
        <div className="grid gap-4 md:grid-cols-4">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-24 w-full rounded-lg" />)}
        </div>
      </div>
    );
  }

  if (certsError) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4">
        <XCircle className="h-12 w-12 text-red-500" />
        <div className="text-center">
          <p className="font-semibold text-red-500">Erro ao carregar certidões</p>
          <p className="text-sm text-muted-foreground mt-1">
            {certsErrorMsg instanceof Error ? certsErrorMsg.message : 'Verifique sua conexão e tente novamente.'}
          </p>
        </div>
        <Button variant="outline" onClick={() => refetchCerts()}>
          <RefreshCw className="h-4 w-4 mr-2" /> Tentar novamente
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2 text-[hsl(var(--foreground))]">
            <ShieldCheck className="h-6 w-6" />
            Certidões da Empresa
          </h1>
          <p className="text-sm text-muted-foreground flex items-center gap-1 mt-0.5">
            <Clock className="h-3.5 w-3.5" />
            Última atualização: {relativeTime(lastUpdate)}
          </p>
        </div>
        <Button
          onClick={() => updateMutation.mutate()}
          disabled={isUpdating}
          className="bg-[#FF6B35] hover:bg-[#e85d2a] text-white shadow-md"
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${isUpdating ? 'animate-spin' : ''}`} />
          {isUpdating ? 'Atualizando...' : 'Atualizar agora'}
        </Button>
      </div>

      {/* ── Resumo semáforo ─────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-4 text-sm font-medium">
        {(['verde', 'amarelo', 'vermelho', 'cinza'] as SemaforoColor[]).map((cor) => {
          const Icon = COLOR_ICONS[cor];
          const style = COLOR_STYLES[cor];
          return (
            <span key={cor} className={`flex items-center gap-1.5 ${COLOR_TEXT[cor]}`}>
              <Icon className="h-4 w-4" />
              {semaforoCount[cor] ?? 0} {style.label.toLowerCase()}
            </span>
          );
        })}
      </div>

      {/* ── 8 Cards semáforo ────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {certificates.map((c) => {
          const cor = getColor(c);
          const style = COLOR_STYLES[cor];
          const Icon = COLOR_ICONS[cor];
          const parsed = parseNotes(c.notes);
          const dias = daysUntilExpiry(c.expiry_date);
          const isOpen = expandedRows.has(c.id);
          const label = DOCUMENT_TYPE_LABELS[c.document_type] ?? c.name;
          const situacaoLabel = parsed?.situacao ?? (SKIP_AUTOMATION.has(c.document_type) ? 'não automatizado' : '—');

          return (
            <Card key={c.id} className={`border-l-4 ${style.border} transition-shadow hover:shadow-sm`}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-start gap-2 min-w-0">
                    <Icon className={`h-4 w-4 mt-0.5 flex-shrink-0 ${COLOR_TEXT[cor]}`} />
                    <div className="min-w-0">
                      <p className="font-semibold text-sm text-[hsl(var(--foreground))] truncate">{label}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Validade: {c.expiry_date ? `${formatDate(c.expiry_date)} (${dias > 0 ? `${dias}d` : 'vencida'})` : '—'}
                      </p>
                    </div>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${style.badge}`}>
                    {situacaoLabel}
                  </span>
                </div>

                {parsed?.fonte && (
                  <p className="text-xs text-muted-foreground mt-2 truncate flex items-center gap-1">
                    <Radio className="h-3 w-3 flex-shrink-0" /> {parsed.fonte}
                  </p>
                )}
                {parsed?.nota && (
                  <p className="text-xs italic text-muted-foreground mt-1 line-clamp-2">{parsed.nota}</p>
                )}

                <button
                  onClick={() => toggleExpanded(c.id)}
                  className="mt-2 flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 underline-offset-2 hover:underline"
                >
                  {isOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                  {isOpen ? 'Ocultar detalhes' : 'Ver detalhes'}
                </button>

                {isOpen && (
                  <div className="mt-2 rounded-md bg-[hsl(var(--secondary))] border border-[hsl(var(--border))] p-2 overflow-x-auto">
                    <pre className="text-[11px] text-[hsl(var(--muted-foreground))] leading-5 whitespace-pre-wrap">
                      {parsed
                        ? JSON.stringify(parsed, null, 2)
                        : (c.notes ?? 'sem dados')}
                    </pre>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* ── Alerta vencimento urgente ────────────────────────────────────── */}
      {(resumo.vencidas > 0 || urgentCount > 0) && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-medium text-red-500">Atenção — certidões precisam de ação</p>
            <p className="text-sm text-red-500 mt-0.5">
              {resumo.vencidas > 0 && `${resumo.vencidas} vencida(s). `}
              {urgentCount > 0 && `${urgentCount} vence(m) em menos de 7 dias.`}
            </p>
          </div>
        </div>
      )}

      {/* ── Stats de validade ────────────────────────────────────────────── */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card className="border-emerald-500/30">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Válidas</CardTitle>
            <CheckCircle className="h-4 w-4 text-emerald-500" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-emerald-500">{resumo.validas}</div>
          </CardContent>
        </Card>
        <Card className="border-amber-500/30">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Vencendo (30d)</CardTitle>
            <AlertTriangle className="h-4 w-4 text-amber-500" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-amber-500">{resumo.a_vencer_30d}</div>
          </CardContent>
        </Card>
        <Card className="border-red-500/30">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Vencidas</CardTitle>
            <XCircleSmall className="h-4 w-4 text-red-500" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-red-500">{resumo.vencidas}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">{certificates.length}</div>
          </CardContent>
        </Card>
      </div>

      {/* ── Filtros ─────────────────────────────────────────────────────── */}
      <Card>
        <CardContent className="pt-4 pb-3">
          <div className="flex flex-col md:flex-row gap-3">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar por nome, tipo ou órgão emissor..."
                className="pl-10"
              />
            </div>
            <Select value={filterType} onValueChange={setFilterType} aria-label="Tipo">
              <SelectTrigger className="w-[200px]">
                <SelectValue placeholder="Tipo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os tipos</SelectItem>
                {certTypes.map((t) => (
                  <SelectItem key={t.document_type} value={t.document_type}>{t.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={filterStatus} onValueChange={setFilterStatus} aria-label="Status">
              <SelectTrigger className="w-[160px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="valida">Válidas</SelectItem>
                <SelectItem value="vencendo">Vencendo</SelectItem>
                <SelectItem value="vencida">Vencidas</SelectItem>
              </SelectContent>
            </Select>
            {(filterType !== 'all' || filterStatus !== 'all' || search) && (
              <Button variant="ghost" size="sm" onClick={() => { setFilterType('all'); setFilterStatus('all'); setSearch(''); }}>
                <Filter className="h-4 w-4 mr-1" /> Limpar
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ── Tabela de certidões ─────────────────────────────────────────── */}
      <Card>
        <CardContent className="p-0">
          {filtered.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <ShieldCheck className="h-12 w-12 mx-auto mb-3 opacity-40" />
              <p className="font-medium">Nenhuma certidão encontrada</p>
              <p className="text-sm mt-1">Ajuste os filtros ou atualize as certidões</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left p-3 font-medium text-muted-foreground">Certidão</th>
                    <th className="text-left p-3 font-medium text-muted-foreground">Emissão</th>
                    <th className="text-left p-3 font-medium text-muted-foreground">Validade</th>
                    <th className="text-center p-3 font-medium text-muted-foreground">Dias</th>
                    <th className="text-left p-3 font-medium text-muted-foreground">Status</th>
                    <th className="text-left p-3 font-medium text-muted-foreground">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((cert) => {
                    const cor = getColor(cert);
                    const Icon = COLOR_ICONS[cor];
                    const style = COLOR_STYLES[cor];
                    const days = daysUntilExpiry(cert.expiry_date);
                    return (
                      <tr key={cert.id} className="border-b last:border-0 hover:bg-muted/50">
                        <td className="p-3">
                          <div className="flex items-center gap-2">
                            <Icon className={`h-3.5 w-3.5 flex-shrink-0 ${COLOR_TEXT[cor]}`} />
                            <div>
                              <p className="font-medium">{DOCUMENT_TYPE_LABELS[cert.document_type] ?? cert.name}</p>
                              <p className="text-xs text-muted-foreground">{cert.issuing_body}</p>
                            </div>
                          </div>
                        </td>
                        <td className="p-3 text-muted-foreground">{formatDate(cert.issue_date)}</td>
                        <td className="p-3 text-muted-foreground">{formatDate(cert.expiry_date)}</td>
                        <td className="p-3 text-center">
                          <span className={days <= 0 ? 'text-red-500 font-bold' : days <= 7 ? 'text-red-500 font-semibold' : days <= 30 ? 'text-amber-500 font-semibold' : 'text-emerald-500'}>
                            {days <= 0 ? 'Vencida' : `${days}d`}
                          </span>
                        </td>
                        <td className="p-3">
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${style.badge}`}>
                            {style.label}
                          </span>
                        </td>
                        <td className="p-3">
                          {cert.file_url && (
                            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => window.open(cert.file_url!, '_blank')}>
                              <FileText className="h-3.5 w-3.5" />
                            </Button>
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

      {/* ── Histórico CND ───────────────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            Histórico de atualizações (últimas 5 execuções com certidões)
          </CardTitle>
        </CardHeader>
        <CardContent>
          {history.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              Nenhuma execução registrada ainda. Clique em &quot;Atualizar agora&quot; ou aguarde a coleta automática.
            </p>
          ) : (
            <div className="space-y-2">
              {history.map((h) => (
                <div key={h.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5 border-b last:border-0 text-sm">
                  <Badge
                    variant={h.status === 'success' ? 'default' : 'outline'}
                    className={
                      h.status === 'success' ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30' :
                      h.status === 'partial' ? 'bg-amber-500/10 text-amber-500 border border-amber-500/30' :
                      'bg-red-500/10 text-red-500 border border-red-500/30'
                    }
                  >
                    {h.status}
                  </Badge>
                  <span className="text-muted-foreground">{new Date(h.run_at).toLocaleString('pt-BR')}</span>
                  <span className="text-xs bg-[hsl(var(--secondary))] text-[hsl(var(--muted-foreground))] px-1.5 py-0.5 rounded">{h.run_type}</span>
                  <span className="font-medium text-emerald-500 inline-flex items-center gap-1"><CheckCircle className="h-3 w-3" /> {h.certidoes_atualizadas} atualizadas</span>
                  {(h.alertas_disparados ?? 0) > 0 && (
                    <span className="font-medium text-amber-500 inline-flex items-center gap-1"><AlertTriangle className="h-3 w-3" /> {h.alertas_disparados} alertas</span>
                  )}
                  <span className="ml-auto text-muted-foreground text-xs">{((h.duration_ms ?? 0) / 1000).toFixed(1)}s</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

    </div>
  );
}
