'use client';

import { AlertCircle, AlertTriangle, Award, CheckCircle, Clock, Eye, RefreshCw, Search, Shield, XCircle, type LucideIcon } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

// ─── Tipos ────────────────────────────────────────────────────────────────────

interface Certidao {
  id: string;
  name: string;
  document_type: string;
  issuing_body: string | null;
  issue_date: string | null;
  expiry_date: string | null;
  status: string;
  file_path: string | null;
  file_url: string | null;
  notes: string | null;
  alerta_ativo: boolean;
  created_at: string | null;
  updated_at: string | null;
}

interface ResumoApi {
  validas: number;
  vencidas: number;
  a_vencer_30d: number;
}

interface ApiResponse {
  certidoes: Certidao[];
  total: number;
  resumo: ResumoApi;
  gerado_em: string;
}

// ─── Constantes ───────────────────────────────────────────────────────────────

// syncKey = chave aceita pelo endpoint POST /sync/{param}
// documentType = document_type salvo no banco (usado para relacionar com a lista de certidões)
const TIPOS_PRINCIPAIS = [
  { syncKey: 'cnd_federal',      documentType: 'certidao_negativa_federal',      label: 'CND Federal',      orgao: 'RFB / PGFN',       icon: '🏛️' },
  { syncKey: 'cndt_trabalhista', documentType: 'certidao_negativa_trabalhista',  label: 'CNDT Trabalhista', orgao: 'TST',               icon: '⚖️' },
  { syncKey: 'crf_fgts',        documentType: 'certidao_negativa_fgts',         label: 'CRF FGTS',         orgao: 'Caixa Econômica',   icon: '🏦' },
  { syncKey: 'cnd_estadual',    documentType: 'certidao_negativa_estadual',     label: 'CND Estadual',     orgao: 'SEFAZ AM',          icon: '🗺️' },
  { syncKey: 'cnd_municipal',   documentType: 'certidao_negativa_municipal',    label: 'CND Municipal',    orgao: 'Prefeitura Manaus', icon: '🏙️' },
];

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; Icon: LucideIcon }> = {
  valida:         { label: 'Válida',     color: 'text-green-700',  bg: 'bg-green-100',  Icon: CheckCircle },
  a_vencer:       { label: 'Vencendo',   color: 'text-yellow-700', bg: 'bg-yellow-100', Icon: AlertTriangle },
  vencida:        { label: 'Vencida',    color: 'text-red-700',    bg: 'bg-red-100',    Icon: XCircle },
  sem_vencimento: { label: 'Sem Prazo',  color: 'text-blue-700',   bg: 'bg-blue-100',   Icon: Clock },
  pendente:       { label: 'Pendente',   color: 'text-gray-700',   bg: 'bg-gray-100',   Icon: Clock },
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function calcularStatus(certidao: Certidao): string {
  if (certidao.status) return certidao.status;
  if (!certidao.expiry_date) return 'sem_vencimento';
  const validade = new Date(certidao.expiry_date);
  const hoje = new Date();
  const diff = Math.ceil((validade.getTime() - hoje.getTime()) / (1000 * 60 * 60 * 24));
  if (diff < 0) return 'vencida';
  if (diff <= 30) return 'a_vencer';
  return 'valida';
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
  });
}

function getToken(): string {
  if (typeof window === 'undefined') return '';
  return (
    localStorage.getItem('auth_token') ||
    localStorage.getItem('access_token') ||
    localStorage.getItem('token') ||
    ''
  );
}

// ─── Componente StatusBadge ───────────────────────────────────────────────────

const STATUS_FALLBACK = { label: 'Pendente', color: 'text-gray-700', bg: 'bg-gray-100', Icon: Clock };

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_FALLBACK;
  const { Icon } = cfg;
  return (
    <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full', cfg.bg, cfg.color)}>
      <Icon className="w-3 h-3" />
      {cfg.label}
    </span>
  );
}

// ─── Componente CardTipo ──────────────────────────────────────────────────────

function CardTipo({
  tipo,
  certidoes,
  onSincronizarTipo,
  sincronizando,
}: {
  tipo: typeof TIPOS_PRINCIPAIS[number];
  certidoes: Certidao[];
  onSincronizarTipo: (syncKey: string) => Promise<void>;
  sincronizando: boolean;
}) {
  const cert = certidoes.find((c) => c.document_type === tipo.documentType);
  const status = cert ? calcularStatus(cert) : 'pendente';
  const cfg = STATUS_CONFIG[status] ?? STATUS_FALLBACK;

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-3 flex-1 min-w-0">
            <span className="text-2xl">{tipo.icon}</span>
            <div className="min-w-0">
              <p className="font-semibold text-sm text-[hsl(var(--foreground))] truncate">{tipo.label}</p>
              <p className="text-xs text-[hsl(var(--muted-foreground))] truncate">{tipo.orgao}</p>
              {cert ? (
                <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
                  Validade: {formatDate(cert.expiry_date)}
                </p>
              ) : (
                <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">Não consultada</p>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-2 shrink-0">
            <StatusBadge status={status} />
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onSincronizarTipo(tipo.syncKey)}
              disabled={sincronizando}
              className="text-xs h-7 px-2"
            >
              {sincronizando ? (
                <RefreshCw className="w-3 h-3 animate-spin" />
              ) : (
                'Buscar'
              )}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Página Principal ─────────────────────────────────────────────────────────

export default function CertidoesPage() {
  const [certidoes, setCertidoes] = useState<Certidao[]>([]);
  const [resumo, setResumo] = useState<ResumoApi>({ validas: 0, vencidas: 0, a_vencer_30d: 0 });
  const [isLoading, setIsLoading] = useState(true);
  const [isError, setIsError] = useState(false);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [sincronizandoTodas, setSincronizandoTodas] = useState(false);
  const [sincronizandoTipo, setSincronizandoTipo] = useState<string>('');
  const [toastMsg, setToastMsg] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);
  const [detalhe, setDetalhe] = useState<Certidao | null>(null);

  // ── Toast helper ──
  const showToast = useCallback((type: 'success' | 'error', msg: string) => {
    setToastMsg({ type, msg });
    setTimeout(() => setToastMsg(null), 4000);
  }, []);

  // ── Fetch certidões ──
  const fetchCertidoes = useCallback(async () => {
    setIsLoading(true);
    setIsError(false);
    try {
      const token = getToken();
      const res = await fetch('/api/v1/ged/certidoes', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ApiResponse = await res.json();
      setCertidoes(data.certidoes ?? []);
      setResumo(data.resumo ?? { validas: 0, vencidas: 0, a_vencer_30d: 0 });
    } catch {
      setIsError(true);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { fetchCertidoes(); }, [fetchCertidoes]);

  // ── Sincronizar todas ──
  const sincronizarTodas = useCallback(async () => {
    setSincronizandoTodas(true);
    try {
      const token = getToken();
      const res = await fetch('/api/v1/ged/certidoes/sync', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast('success', 'Sincronização concluída com sucesso!');
      await fetchCertidoes();
    } catch (e: unknown) {
      showToast('error', `Erro ao sincronizar: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSincronizandoTodas(false);
    }
  }, [fetchCertidoes, showToast]);

  // ── Sincronizar por tipo ──
  const sincronizarTipo = useCallback(async (tipoKey: string) => {
    setSincronizandoTipo(tipoKey);
    try {
      const token = getToken();
      const res = await fetch(`/api/v1/ged/certidoes/sync/${tipoKey}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      showToast('success', `${tipoKey}: ${data.status ?? 'OK'}`);
      await fetchCertidoes();
    } catch (e: unknown) {
      showToast('error', `Erro ao buscar ${tipoKey}: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSincronizandoTipo('');
    }
  }, [fetchCertidoes, showToast]);

  // ── Lista filtrada ──
  const enriched = certidoes.map((c) => ({ ...c, _status: calcularStatus(c) }));

  const filtrados = enriched.filter((c) => {
    const q = search.toLowerCase();
    const matchSearch = !search ||
      c.name.toLowerCase().includes(q) ||
      c.document_type.toLowerCase().includes(q) ||
      (c.issuing_body ?? '').toLowerCase().includes(q);
    const matchStatus = !statusFilter || c._status === statusFilter;
    return matchSearch && matchStatus;
  });

  const total = certidoes.length;

  return (
    <div className="space-y-6 animate-fade-in">

      {/* Toast */}
      {toastMsg && (
        <div className={cn(
          'fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-sm font-medium',
          toastMsg.type === 'success' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
        )}>
          {toastMsg.msg}
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[hsl(var(--foreground))]">Certidões</h1>
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            Gestão de certidões negativas e regularidade fiscal
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={fetchCertidoes}
            disabled={isLoading}
            title="Recarregar lista"
          >
            <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
          </Button>
          <Button
            size="sm"
            onClick={sincronizarTodas}
            disabled={sincronizandoTodas || isLoading}
          >
            {sincronizandoTodas ? (
              <><RefreshCw className="w-4 h-4 mr-2 animate-spin" />Sincronizando...</>
            ) : (
              <><RefreshCw className="w-4 h-4 mr-2" />Sincronizar Todas</>
            )}
          </Button>
          <Button
            size="sm"
            onClick={() => { window.location.href = '/modulos/fiscal/certidoes/emitir'; }}
            className="bg-emerald-600 hover:bg-emerald-700 text-white"
            title="Emitir e baixar as CNDs automaticamente pelo Conecta PRO"
          >
            <Shield className="w-4 h-4 mr-2" />Emitir CNDs
          </Button>
        </div>
      </div>

      {/* Cards de resumo */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Total</p>
                <p className="text-2xl font-bold">{isLoading ? '…' : total}</p>
              </div>
              <Award className="w-8 h-8 text-blue-500 opacity-80" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Válidas</p>
                <p className="text-2xl font-bold text-green-600">{isLoading ? '…' : resumo.validas}</p>
              </div>
              <CheckCircle className="w-8 h-8 text-green-500 opacity-80" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Vencendo 30d</p>
                <p className="text-2xl font-bold text-yellow-600">{isLoading ? '…' : resumo.a_vencer_30d}</p>
              </div>
              <AlertCircle className="w-8 h-8 text-yellow-500 opacity-80" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Vencidas</p>
                <p className="text-2xl font-bold text-red-600">{isLoading ? '…' : resumo.vencidas}</p>
              </div>
              <XCircle className="w-8 h-8 text-red-500 opacity-80" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Cards por tipo */}
      <div>
        <h2 className="text-sm font-semibold text-[hsl(var(--muted-foreground))] uppercase tracking-wide mb-3">
          Certidões Principais
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
          {TIPOS_PRINCIPAIS.map((tipo) => (
            <CardTipo
              key={tipo.syncKey}
              tipo={tipo}
              certidoes={certidoes}
              onSincronizarTipo={sincronizarTipo}
              sincronizando={sincronizandoTipo === tipo.syncKey}
            />
          ))}
        </div>
      </div>

      {/* Filtros */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[hsl(var(--muted-foreground))]" />
          <Input
            type="search"
            placeholder="Buscar por nome, tipo ou órgão..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="flex gap-2 flex-wrap">
          {[
            { value: '', label: 'Todos' },
            { value: 'valida', label: 'Válidas' },
            { value: 'a_vencer', label: 'Vencendo' },
            { value: 'vencida', label: 'Vencidas' },
            { value: 'sem_vencimento', label: 'Sem Prazo' },
          ].map(({ value, label }) => (
            <Button
              key={value}
              variant={statusFilter === value ? 'default' : 'secondary'}
              size="sm"
              onClick={() => setStatusFilter(value)}
            >
              {label}
            </Button>
          ))}
        </div>
      </div>

      {/* Erro */}
      {isError && (
        <div className="flex items-center gap-3 p-4 rounded-lg bg-red-50 border border-red-200">
          <AlertCircle className="w-5 h-5 text-red-500 shrink-0" />
          <div className="flex-1">
            <p className="font-medium text-red-700">Erro ao carregar certidões</p>
            <p className="text-sm text-red-600">Verifique a conexão e tente novamente.</p>
          </div>
          <Button variant="secondary" size="sm" onClick={fetchCertidoes}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Tabela */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="divide-y divide-[hsl(var(--border))]">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="p-4 flex items-center gap-4">
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-48 bg-[hsl(var(--secondary))] rounded animate-pulse" />
                    <div className="h-3 w-32 bg-[hsl(var(--secondary))] rounded animate-pulse" />
                  </div>
                  <div className="h-6 w-20 bg-[hsl(var(--secondary))] rounded animate-pulse" />
                </div>
              ))}
            </div>
          ) : filtrados.length === 0 ? (
            <div className="text-center py-16">
              <Shield className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                {search || statusFilter ? 'Nenhuma certidão encontrada' : 'Nenhuma certidão cadastrada'}
              </h3>
              <p className="text-[hsl(var(--muted-foreground))] mt-1 text-sm">
                {search || statusFilter
                  ? 'Tente ajustar os filtros de busca'
                  : 'Clique em "Sincronizar Todas" para buscar as certidões nos portais governamentais'}
              </p>
              {!search && !statusFilter && (
                <Button className="mt-4" size="sm" onClick={sincronizarTodas} disabled={sincronizandoTodas}>
                  {sincronizandoTodas ? 'Sincronizando...' : 'Sincronizar Todas'}
                </Button>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--secondary))]/30">
                    <th className="text-left p-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase tracking-wide">
                      Certidão
                    </th>
                    <th className="text-left p-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase tracking-wide hidden md:table-cell">
                      Órgão Emissor
                    </th>
                    <th className="text-left p-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase tracking-wide hidden lg:table-cell">
                      Emissão
                    </th>
                    <th className="text-left p-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase tracking-wide">
                      Validade
                    </th>
                    <th className="text-left p-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase tracking-wide">
                      Status
                    </th>
                    <th className="w-12 p-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase tracking-wide text-center">
                      Ver
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[hsl(var(--border))]">
                  {filtrados.map((cert) => (
                    <tr key={cert.id} className="hover:bg-[hsl(var(--secondary))]/40 transition-colors">
                      <td className="p-3">
                        <div className="flex items-center gap-1.5">
                          {cert.alerta_ativo && (
                            <AlertCircle className="w-3.5 h-3.5 text-red-500 shrink-0" title="Alerta ativo — renovação urgente" />
                          )}
                          <p className="font-medium text-sm text-[hsl(var(--foreground))]">{cert.name}</p>
                        </div>
                        <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">{cert.document_type}</p>
                      </td>
                      <td className="p-3 hidden md:table-cell">
                        <span className="text-sm text-[hsl(var(--foreground))]">{cert.issuing_body ?? '—'}</span>
                      </td>
                      <td className="p-3 hidden lg:table-cell">
                        <span className="text-sm text-[hsl(var(--muted-foreground))]">{formatDate(cert.issue_date)}</span>
                      </td>
                      <td className="p-3">
                        <span className="text-sm text-[hsl(var(--foreground))]">{formatDate(cert.expiry_date)}</span>
                      </td>
                      <td className="p-3">
                        <StatusBadge status={cert._status} />
                      </td>
                      <td className="p-3 text-center">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDetalhe(detalhe?.id === cert.id ? null : cert)}
                          title="Ver detalhes"
                          className="h-7 w-7 p-0"
                        >
                          <Eye className="w-4 h-4" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Rodapé com contagem */}
      {!isLoading && filtrados.length > 0 && (
        <p className="text-xs text-[hsl(var(--muted-foreground))] text-center">
          Exibindo {filtrados.length} de {total} certidão{total !== 1 ? 'ões' : ''}
        </p>
      )}

      {/* Painel de detalhe inline */}
      {detalhe && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">{detalhe.name}</CardTitle>
              <Button variant="ghost" size="sm" onClick={() => setDetalhe(null)}>✕</Button>
            </div>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
              {[
                { label: 'Tipo', value: detalhe.document_type },
                { label: 'Órgão', value: detalhe.issuing_body ?? '—' },
                { label: 'Status', value: <StatusBadge status={calcularStatus(detalhe)} /> },
                { label: 'Emissão', value: formatDate(detalhe.issue_date) },
                { label: 'Validade', value: formatDate(detalhe.expiry_date) },
                { label: 'ID', value: <span className="font-mono text-xs">{detalhe.id}</span> },
                { label: 'Atualizado', value: formatDate(detalhe.updated_at) },
                ...(detalhe.alerta_ativo ? [{ label: 'Alerta', value: <span className="text-red-600 font-semibold text-xs">⚠️ Renovação urgente</span> }] : []),
                ...(detalhe.notes ? [{ label: 'Observações', value: detalhe.notes }] : []),
              ].map(({ label, value }) => (
                <div key={label}>
                  <dt className="text-[hsl(var(--muted-foreground))] text-xs font-medium uppercase tracking-wide">{label}</dt>
                  <dd className="mt-1 text-[hsl(var(--foreground))]">{value}</dd>
                </div>
              ))}
            </dl>
            {detalhe.file_url && (
              <div className="mt-4">
                <a
                  href={detalhe.file_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-blue-600 hover:underline"
                >
                  Abrir documento PDF
                </a>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
