'use client';

import { AlertCircle, AlertTriangle, Award, CheckCircle, Clock, Eye, RefreshCw, Search, Shield, XCircle, type LucideIcon } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';
import { cn } from '@/lib/utils';
import { emitirCnd, statusCnd, type PortalManual } from '@/services/gedeon/cndService';

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

// ─── Modelo GEDEON: o mesmo robô de CND usado no GED ──────────────────────────
// syncKey (UI do Fiscal) → portal do robô GEDEON. Os 3 automáticos rodam pelo
// robô (ponte Redis → Playwright host + 2captcha); Federal/FGTS são
// manual-assistidos (emite no portal oficial + sobe o PDF), exatamente como no GED.
const SYNCKEY_PORTAL: Record<string, string> = {
  cnd_federal: 'federal',
  cndt_trabalhista: 'cndt',
  crf_fgts: 'caixa',
  cnd_estadual: 'sefaz_am',
  cnd_municipal: 'prefeitura',
};
const PORTAIS_AUTO = ['sefaz_am', 'cndt', 'prefeitura'];
const PORTAIS_MANUAIS = ['federal', 'caixa'];
const DOCTYPE_PORTAL: Record<string, string> = {
  federal: 'certidao_negativa_federal',
  caixa: 'certidao_negativa_fgts',
};
// estados que o robô grava em gedeon:cnd:status: enfileirado → running → done
const ESTADOS_OCUPADO = new Set(['enfileirado', 'running', 'iniciando', 'processando']);

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; Icon: LucideIcon }> = {
  valida:         { label: 'Válida',     color: 'text-green-700',  bg: 'bg-green-100',  Icon: CheckCircle },
  a_vencer:       { label: 'Vencendo',   color: 'text-yellow-700', bg: 'bg-yellow-100', Icon: AlertTriangle },
  vencida:        { label: 'Vencida',    color: 'text-red-700',    bg: 'bg-red-100',    Icon: XCircle },
  sem_vencimento: { label: 'Sem Prazo',  color: 'text-blue-700',   bg: 'bg-blue-100',   Icon: Clock },
  pendente:       { label: 'Pendente',   color: 'text-gray-700',   bg: 'bg-gray-100',   Icon: Clock },
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

// Datas ISO só-data (YYYY-MM-DD) são meia-noite UTC; em fuso negativo (Manaus/Brasília)
// new Date() as renderiza no dia anterior. Parse como data LOCAL para evitar o off-by-one.
function parseLocalDate(dateStr: string): Date {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr.slice(0, 10));
  if (m) return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return new Date(dateStr);
}

function calcularStatus(certidao: Certidao): string {
  if (certidao.status) return certidao.status;
  if (!certidao.expiry_date) return 'sem_vencimento';
  const validade = parseLocalDate(certidao.expiry_date);
  const hoje = new Date();
  const diff = Math.ceil((validade.getTime() - hoje.getTime()) / (1000 * 60 * 60 * 24));
  if (diff < 0) return 'vencida';
  if (diff <= 30) return 'a_vencer';
  return 'valida';
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  return parseLocalDate(dateStr).toLocaleDateString('pt-BR', {
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
  const [manuais, setManuais] = useState<Record<string, PortalManual>>({});
  const [progresso, setProgresso] = useState<string>('');

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

  // carrega as URLs dos portais oficiais (Federal/FGTS = manual-assistido) uma vez
  useEffect(() => {
    statusCnd().then((s) => setManuais(s.manuais ?? {})).catch(() => {});
  }, []);

  // ── Acompanha o robô GEDEON até concluir (enfileirado → running → done) ──
  const aguardarRobo = useCallback(async (rotulo: string): Promise<void> => {
    for (let i = 0; i < 50; i++) {       // ~3,5 min de teto (50 × 4s)
      await sleep(4000);
      let st;
      try { st = await statusCnd(); } catch { continue; }
      const state = st.emissao?.state ?? 'idle';
      if (ESTADOS_OCUPADO.has(state)) {
        const atual = st.emissao?.atual ? ` (${st.emissao.atual})` : '';
        setProgresso(`${rotulo}: robô trabalhando${atual}…`);
        continue;
      }
      return;                            // 'done' / 'idle' → terminou
    }
  }, []);

  // ── Sincronizar todas (robô GEDEON: SEFAZ/CNDT/Prefeitura automáticos) ──
  const sincronizarTodas = useCallback(async () => {
    setSincronizandoTodas(true);
    setProgresso('Disparando o robô de CND (SEFAZ-AM, CNDT, Prefeitura)…');
    try {
      await emitirCnd(PORTAIS_AUTO);
      await aguardarRobo('Certidões');
      await fetchCertidoes();
      showToast('success', 'Robô concluído. Federal e FGTS são manual-assistidos — use "Buscar" no card.');
    } catch (e: unknown) {
      showToast('error', `Erro ao acionar o robô: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSincronizandoTodas(false);
      setProgresso('');
    }
  }, [aguardarRobo, fetchCertidoes, showToast]);

  // ── Buscar por tipo (mesmo modelo do GED) ──
  const sincronizarTipo = useCallback(async (tipoKey: string) => {
    const portal = SYNCKEY_PORTAL[tipoKey];
    // Federal / FGTS: manual-assistido — abre o portal oficial e leva ao upload
    if (PORTAIS_MANUAIS.includes(portal)) {
      const m = manuais[DOCTYPE_PORTAL[portal]];
      if (m?.url) window.open(m.url, '_blank', 'noopener');
      showToast('success', `${m?.nome ?? portal}: emita no portal oficial e suba o PDF em "Emitir CNDs".`);
      window.location.href = '/modulos/fiscal/certidoes/emitir';
      return;
    }
    // SEFAZ-AM / CNDT / Prefeitura: robô automático
    setSincronizandoTipo(tipoKey);
    setProgresso(`Disparando o robô para ${tipoKey}…`);
    try {
      await emitirCnd([portal]);
      await aguardarRobo(tipoKey);
      await fetchCertidoes();
      showToast('success', `${tipoKey}: robô concluído.`);
    } catch (e: unknown) {
      showToast('error', `Erro ao buscar ${tipoKey}: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSincronizandoTipo('');
      setProgresso('');
    }
  }, [aguardarRobo, fetchCertidoes, manuais, showToast]);

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
      <PageHeader
        eyebrow="FISCAL"
        title="Certidões"
        subtitle="Gestão de certidões negativas e regularidade fiscal"
        icon={<Award className="h-5 w-5" />}
        actions={
          <>
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
          </>
        }
      />

      {/* Progresso do robô GEDEON */}
      {progresso && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-blue-50 border border-blue-200 text-sm text-blue-700">
          <RefreshCw className="w-4 h-4 animate-spin shrink-0" />
          {progresso}
        </div>
      )}

      {/* Cards de resumo */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard
          label="Total"
          value={isLoading ? '…' : total}
          icon={<Award className="w-5 h-5" />}
          color="#3b82f6"
        />
        <StatCard
          label="Válidas"
          value={isLoading ? '…' : resumo.validas}
          icon={<CheckCircle className="w-5 h-5" />}
          color="#16a34a"
        />
        <StatCard
          label="Vencendo 30d"
          value={isLoading ? '…' : resumo.a_vencer_30d}
          icon={<AlertCircle className="w-5 h-5" />}
          color="#ca8a04"
        />
        <StatCard
          label="Vencidas"
          value={isLoading ? '…' : resumo.vencidas}
          icon={<XCircle className="w-5 h-5" />}
          color="#dc2626"
        />
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
                            <span title="Alerta ativo — renovação urgente" className="inline-flex shrink-0">
                              <AlertCircle className="w-3.5 h-3.5 text-red-500" />
                            </span>
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
                ...(detalhe.alerta_ativo ? [{ label: 'Alerta', value: <span className="inline-flex items-center gap-1 text-red-600 font-semibold text-xs"><AlertTriangle className="w-3.5 h-3.5" /> Renovação urgente</span> }] : []),
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
