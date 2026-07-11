'use client';

/**
 * Meu Espaço — Área self-service do funcionário (login Google, role='funcionario').
 *
 * Só LEITURA do que é DELE + ASSINAR o que é DELE. Nenhum módulo de gestão.
 * Fonte: users.employee_id (resolvido no backend a partir do JWT principal).
 *
 * Abas:
 *  - Documentos a assinar (GET /signatures/meus-pendentes, POST /signatures/{id}/sign) — ESSENCIAL
 *  - Holerite  (GET /portal/self-service/meus-holerites[/{m}/{a}][/pdf])
 *  - Férias    (GET /portal/self-service/minhas-ferias/*)
 *  - Ponto     (GET /portal/self-service/meu-ponto)
 *  - Benefícios(GET /portal/self-service/meus-beneficios)
 */

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import {
  FileSignature, FileText, CalendarDays, Clock, Gift, LogOut,
  CheckCircle2, Loader2, ShieldCheck, AlertTriangle,
  GraduationCap, User as UserIcon, FolderOpen, Scale, Download, Award,
  CalendarClock, Bell, MapPin,
} from 'lucide-react';
import api from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/ui/button';

interface PendingDoc {
  request_id: string;
  title: string;
  document_type: string | null;
  document_name: string | null;
  reference_code: string | null;
  status: string;
  created_at: string | null;
  expires_at: string | null;
  is_expired: boolean;
}

type Tab =
  | 'assinar' | 'holerite' | 'ferias' | 'ponto' | 'beneficios'
  | 'documentos' | 'treinamentos' | 'dados' | 'cct'
  | 'escala' | 'comunicados';

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: 'assinar', label: 'Documentos a assinar', icon: FileSignature },
  { id: 'comunicados', label: 'Comunicados', icon: Bell },
  { id: 'escala', label: 'Minha escala', icon: CalendarClock },
  { id: 'holerite', label: 'Holerite', icon: FileText },
  { id: 'documentos', label: 'Documentos', icon: FolderOpen },
  { id: 'ferias', label: 'Férias', icon: CalendarDays },
  { id: 'ponto', label: 'Ponto', icon: Clock },
  { id: 'beneficios', label: 'Benefícios', icon: Gift },
  { id: 'treinamentos', label: 'Treinamentos', icon: GraduationCap },
  { id: 'cct', label: 'Meus direitos (CCT)', icon: Scale },
  { id: 'dados', label: 'Meus dados', icon: UserIcon },
];

export default function MeuEspacoPage() {
  const router = useRouter();
  const { user, isLoading, isAuthenticated, logout } = useAuth();
  const [tab, setTab] = useState<Tab>('assinar');

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace('/login');
  }, [isLoading, isAuthenticated, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-[hsl(var(--primary))]" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[hsl(var(--background))]">
      {/* Header */}
      <header className="h-14 flex items-center justify-between px-4 lg:px-6 bg-[hsl(var(--card))] border-b border-[hsl(var(--border))]">
        <div className="flex items-center gap-2.5">
          <Image src="/images/logo-icon.png" alt="Conecta PRO" width={26} height={26} />
          <span className="font-display text-sm font-semibold tracking-tight">
            Meu&nbsp;<span style={{ color: '#f97707' }}>Espaço</span>
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-[hsl(var(--muted-foreground))] hidden sm:inline">
            {user?.name}
          </span>
          <Button variant="outline" size="sm" onClick={logout}>
            <LogOut className="w-4 h-4 mr-1.5" /> Sair
          </Button>
        </div>
      </header>

      <div className="max-w-3xl mx-auto p-4 lg:p-6">
        {/* Boas-vindas */}
        <div className="mb-5">
          <h1 className="font-display text-xl font-bold text-[hsl(var(--foreground))]">
            Olá, {user?.name?.split(' ')[0] || 'colaborador'}
          </h1>
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            Aqui você assina e baixa seus documentos e consulta holerite, férias, ponto,
            benefícios, treinamentos, seus direitos (CCT) e seus dados.
          </p>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 overflow-x-auto mb-5 border-b border-[hsl(var(--border))]">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={[
                  'flex items-center gap-2 px-3 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors',
                  active
                    ? 'border-[#f97707] text-[hsl(var(--foreground))]'
                    : 'border-transparent text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]',
                ].join(' ')}
              >
                <Icon className="w-4 h-4" />
                {t.label}
              </button>
            );
          })}
        </div>

        {tab === 'assinar' && <AssinarTab />}
        {tab === 'comunicados' && <ComunicadosTab />}
        {tab === 'escala' && <EscalaTab />}
        {tab === 'holerite' && <HoleriteTab />}
        {tab === 'documentos' && <DocumentosTab onIrAssinar={() => setTab('assinar')} />}
        {tab === 'ferias' && <FeriasTab />}
        {tab === 'ponto' && <PontoTab />}
        {tab === 'beneficios' && <BeneficiosTab />}
        {tab === 'treinamentos' && <TreinamentosTab />}
        {tab === 'cct' && <CctTab />}
        {tab === 'dados' && <DadosTab />}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Documentos a assinar (ESSENCIAL)
// --------------------------------------------------------------------------- //
function AssinarTab() {
  const [docs, setDocs] = useState<PendingDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [signingId, setSigningId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/api/v1/signatures/meus-pendentes');
      setDocs(res.data.pendentes || []);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg || 'Não foi possível carregar seus documentos.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const assinar = async (requestId: string) => {
    setSigningId(requestId);
    setError('');
    try {
      await api.post(`/api/v1/signatures/${requestId}/sign`, {
        evidence: { device: 'meu-espaco-web' },
      });
      await load();
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg || 'Não foi possível assinar o documento.');
    } finally {
      setSigningId(null);
    }
  };

  if (loading) return <Spinner />;

  return (
    <div className="space-y-3">
      {error && <ErrorBox msg={error} />}
      {docs.length === 0 ? (
        <EmptyState
          icon={CheckCircle2}
          title="Nenhum documento pendente"
          desc="Você está em dia. Quando houver um documento para assinar, ele aparece aqui."
        />
      ) : (
        docs.map((d) => (
          <div
            key={d.request_id}
            className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 flex items-start justify-between gap-4"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <FileSignature className="w-4 h-4 text-[#f97707] flex-shrink-0" />
                <p className="font-medium text-sm text-[hsl(var(--foreground))] truncate">{d.title}</p>
              </div>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                {d.document_name || d.document_type || 'Documento'}
                {d.reference_code ? ` · ${d.reference_code}` : ''}
              </p>
              {d.is_expired && (
                <span className="inline-flex items-center gap-1 mt-1 text-xs text-red-500">
                  <AlertTriangle className="w-3 h-3" /> Expirado
                </span>
              )}
            </div>
            <Button
              size="sm"
              disabled={d.is_expired || signingId === d.request_id}
              onClick={() => assinar(d.request_id)}
            >
              {signingId === d.request_id ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <>
                  <ShieldCheck className="w-4 h-4 mr-1.5" /> Assinar
                </>
              )}
            </Button>
          </div>
        ))
      )}
      <p className="text-[11px] text-[hsl(var(--muted-foreground))]/70 pt-2">
        Assinatura eletrônica com carimbo de data/hora e hash SHA-256 (MP 2.200-2/ICP-Brasil).
      </p>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Holerite
// --------------------------------------------------------------------------- //
function HoleriteTab() {
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/api/v1/people-management/portal/self-service/meus-holerites');
        const data = res.data;
        setItems(Array.isArray(data) ? data : data?.holerites || data?.payslips || data?.items || []);
      } catch (e: unknown) {
        const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setError(msg || 'Não foi possível carregar seus holerites.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const baixarPdf = (mes: number, ano: number) => {
    const token = localStorage.getItem('access_token');
    const base = process.env.NEXT_PUBLIC_API_URL || 'https://erp.conectamais.pro';
    const url = `${base}/api/v1/people-management/portal/self-service/meus-holerites/${mes}/${ano}/pdf`;
    // abre com auth via fetch → blob (o endpoint exige Bearer)
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.blob())
      .then((b) => window.open(URL.createObjectURL(b), '_blank'))
      .catch(() => setError('Não foi possível baixar o PDF.'));
  };

  if (loading) return <Spinner />;
  if (error) return <ErrorBox msg={error} />;
  if (items.length === 0)
    return <EmptyState icon={FileText} title="Sem holerites" desc="Nenhum holerite disponível ainda." />;

  return (
    <div className="space-y-2">
      {items.map((h, i) => {
        const mes = Number(h.mes ?? h.month ?? 0);
        const ano = Number(h.ano ?? h.year ?? 0);
        const liquido = h.net_salary ?? h.liquido ?? h.net ?? h.valor_liquido;
        return (
          <div
            key={i}
            className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 flex items-center justify-between"
          >
            <div>
              <p className="font-medium text-sm">{String(mes).padStart(2, '0')}/{ano}</p>
              {liquido != null && (
                <p className="text-xs text-[hsl(var(--muted-foreground))]">
                  Líquido: {typeof liquido === 'number' ? `R$ ${liquido.toFixed(2)}` : String(liquido)}
                </p>
              )}
            </div>
            {mes > 0 && ano > 0 && (
              <Button variant="outline" size="sm" onClick={() => baixarPdf(mes, ano)}>
                <FileText className="w-4 h-4 mr-1.5" /> PDF
              </Button>
            )}
          </div>
        );
      })}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Férias
// --------------------------------------------------------------------------- //
function FeriasTab() {
  const [saldo, setSaldo] = useState<Record<string, unknown> | null>(null);
  const [reqs, setReqs] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const [s, r] = await Promise.all([
          api.get('/api/v1/people-management/portal/self-service/minhas-ferias/saldo'),
          api.get('/api/v1/people-management/portal/self-service/minhas-ferias/solicitacoes'),
        ]);
        setSaldo(s.data);
        setReqs(Array.isArray(r.data) ? r.data : []);
      } catch (e: unknown) {
        const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setError(msg || 'Não foi possível carregar suas férias.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <Spinner />;
  if (error) return <ErrorBox msg={error} />;

  return (
    <div className="space-y-4">
      {saldo && (
        <div className="grid grid-cols-3 gap-3">
          <Stat label="Dias de direito" value={String(saldo.dias_direito ?? '-')} />
          <Stat label="Gozados" value={String(saldo.dias_gozados ?? '-')} />
          <Stat label="Saldo" value={String(saldo.dias_saldo ?? '-')} highlight />
        </div>
      )}
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70 mb-2">
          Minhas solicitações
        </p>
        {reqs.length === 0 ? (
          <EmptyState icon={CalendarDays} title="Nenhuma solicitação" desc="Você ainda não solicitou férias." />
        ) : (
          <div className="space-y-2">
            {reqs.map((v, i) => (
              <div key={i} className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-3 flex items-center justify-between">
                <span className="text-sm">
                  {String(v.data_inicio || '')} → {String(v.data_fim || '')}
                </span>
                <span className="text-xs px-2 py-0.5 rounded-md bg-brand-500/15 text-brand-500 font-medium">
                  {String(v.status || '')}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Ponto
// --------------------------------------------------------------------------- //
function PontoTab() {
  const now = new Date();
  const [mes, setMes] = useState(now.getMonth() + 1);
  const [ano, setAno] = useState(now.getFullYear());
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError('');
      try {
        const res = await api.get(
          `/api/v1/people-management/portal/self-service/meu-ponto?mes=${mes}&ano=${ano}`,
        );
        setData(res.data);
      } catch (e: unknown) {
        const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setError(msg || 'Não foi possível carregar seu ponto.');
      } finally {
        setLoading(false);
      }
    })();
  }, [mes, ano]);

  // Backend retorna registros de BATIDA individuais: {tipo, data_hora, localizacao}
  const registros = (data?.registros || []) as Record<string, unknown>[];

  const fmt = (dh: string): { dia: string; hora: string } => {
    // data_hora vem como "2026-07-10 06:00:00"
    const [d, h] = String(dh).split(' ');
    const [y, m, day] = (d || '').split('-');
    return { dia: y ? `${day}/${m}/${y}` : d || '', hora: (h || '').slice(0, 5) };
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <select
          value={mes}
          onChange={(e) => setMes(Number(e.target.value))}
          className="text-sm rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-2 py-1.5"
        >
          {['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'].map(
            (m, idx) => (
              <option key={idx} value={idx + 1}>{m}</option>
            ),
          )}
        </select>
        <select
          value={ano}
          onChange={(e) => setAno(Number(e.target.value))}
          className="text-sm rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-2 py-1.5"
        >
          {[now.getFullYear(), now.getFullYear() - 1].map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
        {typeof data?.total_registros === 'number' && (
          <span className="text-xs text-[hsl(var(--muted-foreground))] ml-auto">
            {String(data.total_registros)} batida(s)
          </span>
        )}
      </div>

      {loading ? (
        <Spinner />
      ) : error ? (
        <ErrorBox msg={error} />
      ) : registros.length === 0 ? (
        <EmptyState icon={Clock} title="Sem registros" desc="Nenhuma batida de ponto no período selecionado." />
      ) : (
        <div className="space-y-2">
          {registros.map((r, i) => {
            const { dia, hora } = fmt(String(r.data_hora || ''));
            const tipo = String(r.tipo || 'registro');
            const isEntrada = tipo.toLowerCase().includes('entra');
            return (
              <div
                key={i}
                className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-3 flex items-center justify-between text-sm"
              >
                <div className="flex items-center gap-2">
                  <span
                    className={[
                      'inline-block w-2 h-2 rounded-full',
                      isEntrada ? 'bg-emerald-500' : 'bg-orange-500',
                    ].join(' ')}
                  />
                  <span className="font-medium capitalize">{tipo}</span>
                  {r.localizacao ? (
                    <span className="text-xs text-[hsl(var(--muted-foreground))]">
                      · {String(r.localizacao)}
                    </span>
                  ) : null}
                </div>
                <span className="text-[hsl(var(--muted-foreground))] font-mono">
                  {dia} {hora}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Benefícios
// --------------------------------------------------------------------------- //
interface BeneficioAtivo {
  tipo?: string; operadora?: string; plano?: string | null;
  desconto_funcionario?: number; contribuicao_empresa?: number; status?: string;
}
interface BeneficioCct {
  tipo?: string; obrigatorio?: boolean; valor_minimo_cct?: number | null;
  valor_empresa_cct?: number | null; desconto_percentual_cct?: number | null;
  desconto_calculado?: number | null; observacao?: string;
}

function BeneficiosTab() {
  const [ativos, setAtivos] = useState<BeneficioAtivo[]>([]);
  const [cct, setCct] = useState<BeneficioCct[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/api/v1/people-management/portal/self-service/meus-beneficios');
        const d = res.data || {};
        setAtivos(Array.isArray(d.beneficios_ativos) ? d.beneficios_ativos : []);
        setCct(Array.isArray(d.beneficios_cct) ? d.beneficios_cct : []);
      } catch (e: unknown) {
        const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setError(msg || 'Não foi possível carregar seus benefícios.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const brl = (v?: number | null) =>
    v == null ? null : `R$ ${Number(v).toFixed(2).replace('.', ',')}`;

  if (loading) return <Spinner />;
  if (error) return <ErrorBox msg={error} />;
  if (ativos.length === 0 && cct.length === 0)
    return <EmptyState icon={Gift} title="Sem benefícios" desc="Nenhum benefício cadastrado." />;

  return (
    <div className="space-y-5">
      {ativos.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70 mb-2">
            Meus benefícios ativos
          </p>
          <div className="space-y-2">
            {ativos.map((b, i) => (
              <div key={i} className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium capitalize">{b.tipo || 'Benefício'}</span>
                  <span className="text-[11px] px-2 py-0.5 rounded-md bg-emerald-500/15 text-emerald-600 font-medium">
                    {b.status === 'active' ? 'Ativo' : (b.status || '')}
                  </span>
                </div>
                <div className="mt-1 text-xs text-[hsl(var(--muted-foreground))] flex flex-wrap gap-x-4">
                  {b.operadora && <span>Operadora: {b.operadora}</span>}
                  {b.desconto_funcionario != null && b.desconto_funcionario > 0 && (
                    <span>Meu desconto: {brl(b.desconto_funcionario)}</span>
                  )}
                  {b.contribuicao_empresa != null && b.contribuicao_empresa > 0 && (
                    <span>Empresa paga: {brl(b.contribuicao_empresa)}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {cct.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70 mb-2">
            Garantidos pela CCT 2026
          </p>
          <div className="space-y-2">
            {cct.map((b, i) => (
              <div key={i} className="bg-[hsl(var(--secondary))]/40 border border-[hsl(var(--border))] rounded-xl p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium capitalize">
                    {String(b.tipo || '').replace(/_/g, ' ')}
                  </span>
                  {b.desconto_calculado != null && (
                    <span className="text-xs text-[hsl(var(--muted-foreground))]">
                      Desconto est.: {brl(b.desconto_calculado)}
                    </span>
                  )}
                </div>
                {b.observacao && (
                  <p className="mt-1 text-[11px] text-[hsl(var(--muted-foreground))]">{b.observacao}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Documentos (listar + baixar/ver; assinaturas pendentes vão p/ aba Assinar)
// --------------------------------------------------------------------------- //
interface MeuDocumento {
  document_id: string;
  document_type: string | null;
  document_name: string | null;
  signed: boolean;
  signed_at: string | null;
  file_path: string | null;
}

function DocumentosTab({ onIrAssinar }: { onIrAssinar: () => void }) {
  const [docs, setDocs] = useState<MeuDocumento[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [baixandoId, setBaixandoId] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/api/v1/people-management/portal/self-service/meus-documentos');
        setDocs(Array.isArray(res.data?.documentos) ? res.data.documentos : []);
      } catch (e: unknown) {
        const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setError(msg || 'Não foi possível carregar seus documentos.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const baixar = async (id: string) => {
    setBaixandoId(id);
    setError('');
    try {
      const token = localStorage.getItem('access_token');
      const base = process.env.NEXT_PUBLIC_API_URL || 'https://erp.conectamais.pro';
      const url = `${base}/api/v1/people-management/portal/self-service/meus-documentos/${id}/download`;
      const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        throw new Error(j.detail || 'Documento indisponível para download.');
      }
      const b = await r.blob();
      window.open(URL.createObjectURL(b), '_blank');
    } catch (e: unknown) {
      setError((e as Error)?.message || 'Não foi possível baixar o documento.');
    } finally {
      setBaixandoId(null);
    }
  };

  if (loading) return <Spinner />;

  return (
    <div className="space-y-3">
      {error && <ErrorBox msg={error} />}
      {docs.length === 0 ? (
        <EmptyState icon={FolderOpen} title="Sem documentos" desc="Nenhum documento disponível ainda." />
      ) : (
        <>
          {docs.map((d) => (
            <div
              key={d.document_id}
              className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 flex items-start justify-between gap-4"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <FileText className="w-4 h-4 text-[#f97707] flex-shrink-0" />
                  <p className="font-medium text-sm truncate">
                    {d.document_name || String(d.document_type || 'Documento').replace(/_/g, ' ')}
                  </p>
                </div>
                <div className="text-xs text-[hsl(var(--muted-foreground))] flex flex-wrap items-center gap-2">
                  <span className="capitalize">{String(d.document_type || '').replace(/_/g, ' ')}</span>
                  {d.signed ? (
                    <span className="inline-flex items-center gap-1 text-emerald-600">
                      <CheckCircle2 className="w-3 h-3" /> Assinado
                    </span>
                  ) : (
                    <button
                      onClick={onIrAssinar}
                      className="inline-flex items-center gap-1 text-[#f97707] hover:underline"
                    >
                      <FileSignature className="w-3 h-3" /> Assinatura pendente
                    </button>
                  )}
                </div>
              </div>
              {d.file_path && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={baixandoId === d.document_id}
                  onClick={() => baixar(d.document_id)}
                >
                  {baixandoId === d.document_id ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <>
                      <Download className="w-4 h-4 mr-1.5" /> Abrir
                    </>
                  )}
                </Button>
              )}
            </div>
          ))}
          <p className="text-[11px] text-[hsl(var(--muted-foreground))]/70 pt-1">
            Documentos com assinatura pendente aparecem também na aba “Documentos a assinar”.
            Alguns documentos são gerados sob demanda (ex.: contracheque na aba Holerite).
          </p>
        </>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Treinamentos (matrículas + certificados)
// --------------------------------------------------------------------------- //
interface Matricula {
  id?: string; training_title?: string | null; course_name?: string | null;
  status?: string | null; enrolled_at?: string | null;
}
interface Certificado {
  id?: string; certificate_number?: string | null; course_name?: string | null;
  issued_at?: string | null; expires_at?: string | null; status?: string | null;
}

function TreinamentosTab() {
  const [matriculas, setMatriculas] = useState<Matricula[]>([]);
  const [certificados, setCertificados] = useState<Certificado[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/api/v1/people-management/portal/self-service/meus-treinamentos');
        setMatriculas(Array.isArray(res.data?.matriculas) ? res.data.matriculas : []);
        setCertificados(Array.isArray(res.data?.certificados) ? res.data.certificados : []);
      } catch (e: unknown) {
        const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setError(msg || 'Não foi possível carregar seus treinamentos.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const fmtData = (s?: string | null) => (s ? String(s).slice(0, 10).split('-').reverse().join('/') : '');

  if (loading) return <Spinner />;
  if (error) return <ErrorBox msg={error} />;
  if (matriculas.length === 0 && certificados.length === 0)
    return <EmptyState icon={GraduationCap} title="Sem treinamentos" desc="Você ainda não tem treinamentos registrados." />;

  return (
    <div className="space-y-5">
      {matriculas.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70 mb-2">
            Minhas matrículas
          </p>
          <div className="space-y-2">
            {matriculas.map((m, i) => (
              <div key={m.id || i} className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium">{m.training_title || m.course_name || 'Treinamento'}</span>
                  {m.status && (
                    <span className="text-[11px] px-2 py-0.5 rounded-md bg-brand-500/15 text-brand-500 font-medium capitalize">
                      {m.status}
                    </span>
                  )}
                </div>
                {m.course_name && m.training_title && (
                  <p className="mt-0.5 text-xs text-[hsl(var(--muted-foreground))]">{m.course_name}</p>
                )}
                {m.enrolled_at && (
                  <p className="mt-0.5 text-[11px] text-[hsl(var(--muted-foreground))]/80">
                    Inscrição: {fmtData(m.enrolled_at)}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {certificados.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70 mb-2">
            Meus certificados
          </p>
          <div className="space-y-2">
            {certificados.map((c, i) => (
              <div key={c.id || i} className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Award className="w-4 h-4 text-[#f97707] flex-shrink-0" />
                    <span className="text-sm font-medium truncate">{c.course_name || 'Certificado'}</span>
                  </div>
                  <p className="mt-0.5 text-xs text-[hsl(var(--muted-foreground))]">
                    {c.certificate_number ? `Nº ${c.certificate_number}` : ''}
                    {c.expires_at ? ` · válido até ${fmtData(c.expires_at)}` : ''}
                  </p>
                </div>
                {c.status && (
                  <span className="text-[11px] px-2 py-0.5 rounded-md bg-emerald-500/15 text-emerald-600 font-medium capitalize whitespace-nowrap">
                    {c.status === 'valid' ? 'Válido' : c.status}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// CCT — meus direitos e piso
// --------------------------------------------------------------------------- //
function CctTab() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/api/v1/people-management/portal/self-service/minha-cct');
        setData(res.data);
      } catch (e: unknown) {
        const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setError(msg || 'Não foi possível carregar seus direitos.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <Spinner />;
  if (error) return <ErrorBox msg={error} />;
  if (!data) return <EmptyState icon={Scale} title="Sem dados" desc="Direitos indisponíveis no momento." />;

  const salario = (data.salario || {}) as Record<string, unknown>;
  const cct = (data.cct || {}) as Record<string, unknown>;
  const beneficios = (data.beneficios_garantidos || []) as Record<string, unknown>[];
  const adicionais = (data.adicionais || {}) as Record<string, unknown>;
  const estabilidades = (data.estabilidades || []) as string[];
  const brl = (v: unknown) =>
    typeof v === 'number' ? `R$ ${v.toFixed(2).replace('.', ',')}` : String(v ?? '-');
  const conforme = salario.conforme_cct === true;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3">
        <Stat label="Piso do meu cargo" value={brl(salario.piso_cargo)} />
        <Stat
          label="Meu salário base"
          value={brl(salario.salario_atual)}
          highlight={conforme}
        />
      </div>
      <div
        className={[
          'rounded-xl p-3 text-sm flex items-center gap-2 border',
          conforme
            ? 'bg-emerald-500/5 border-emerald-500/20 text-emerald-600'
            : 'bg-amber-500/5 border-amber-500/20 text-amber-600',
        ].join(' ')}
      >
        {conforme ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
        {conforme ? 'Seu salário está conforme o piso da CCT.' : 'Atenção: salário abaixo do piso da CCT — procure o DP.'}
      </div>

      {beneficios.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70 mb-2">
            Benefícios garantidos
          </p>
          <div className="space-y-1.5">
            {beneficios.map((b, i) => (
              <div key={i} className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg p-3">
                <p className="text-sm font-medium">{String(b.beneficio || '')}</p>
                {Boolean(b.garantia_cct) && (
                  <p className="text-[11px] text-[hsl(var(--muted-foreground))] mt-0.5">{String(b.garantia_cct)}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {Object.keys(adicionais).length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70 mb-2">
            Adicionais
          </p>
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg divide-y divide-[hsl(var(--border))]">
            {Object.entries(adicionais).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between px-3 py-2 text-xs">
                <span className="capitalize text-[hsl(var(--muted-foreground))]">{k.replace(/_/g, ' ')}</span>
                <span className="text-right">{String(v)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {estabilidades.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70 mb-2">
            Estabilidades
          </p>
          <ul className="text-xs text-[hsl(var(--muted-foreground))] list-disc pl-4 space-y-1">
            {estabilidades.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </div>
      )}

      <p className="text-[11px] text-[hsl(var(--muted-foreground))]/70">
        {String(cct.nome || 'CCT SINDECOMPRESTS/SINDICOND-AM')}
        {cct.vigencia ? ` · vigência ${String(cct.vigencia)}` : ''}
      </p>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Meus dados (leitura + edição de campos permitidos)
// --------------------------------------------------------------------------- //
interface MeusDados {
  nome?: string | null; cpf?: string | null; cargo?: string | null;
  data_admissao?: string | null; telefone?: string | null; email?: string | null;
  endereco?: string | null; contato_emergencia?: string | null;
}

function DadosTab() {
  const [data, setData] = useState<MeusDados | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<Partial<MeusDados>>({});

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/api/v1/people-management/portal/self-service/meus-dados');
        setData(res.data);
        setForm({
          telefone: res.data?.telefone || '',
          email: res.data?.email || '',
          endereco: res.data?.endereco || '',
          contato_emergencia: res.data?.contato_emergencia || '',
        });
      } catch (e: unknown) {
        const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setError(msg || 'Não foi possível carregar seus dados.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const salvar = async () => {
    setSaving(true); setError(''); setOk('');
    try {
      const res = await api.put('/api/v1/people-management/portal/self-service/meus-dados', {
        telefone: form.telefone || null,
        email: form.email || null,
        endereco: form.endereco || null,
        contato_emergencia: form.contato_emergencia || null,
      });
      setData(res.data);
      setOk('Dados atualizados com sucesso.');
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg || 'Não foi possível salvar. Tente novamente.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <Spinner />;
  if (error && !data) return <ErrorBox msg={error} />;

  const inputCls =
    'w-full rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 py-2 text-sm outline-none focus:border-[#f97707]';

  return (
    <div className="space-y-5">
      {/* Somente leitura */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <ReadField label="Nome" value={data?.nome} />
        <ReadField label="CPF" value={data?.cpf} />
        <ReadField label="Cargo" value={data?.cargo} />
        <ReadField
          label="Admissão"
          value={data?.data_admissao ? String(data.data_admissao).slice(0, 10).split('-').reverse().join('/') : '-'}
        />
      </div>

      {/* Editáveis */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70 mb-2">
          Contato (você pode atualizar)
        </p>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-[hsl(var(--muted-foreground))]">Telefone</label>
            <input className={inputCls} value={form.telefone || ''} onChange={(e) => setForm({ ...form, telefone: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-[hsl(var(--muted-foreground))]">E-mail</label>
            <input className={inputCls} value={form.email || ''} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-[hsl(var(--muted-foreground))]">Endereço</label>
            <input className={inputCls} value={form.endereco || ''} onChange={(e) => setForm({ ...form, endereco: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-[hsl(var(--muted-foreground))]">Contato de emergência</label>
            <input className={inputCls} value={form.contato_emergencia || ''} onChange={(e) => setForm({ ...form, contato_emergencia: e.target.value })} />
          </div>
        </div>
      </div>

      {error && <ErrorBox msg={error} />}
      {ok && (
        <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-3 text-sm text-emerald-600 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" /> {ok}
        </div>
      )}

      <div className="flex justify-end">
        <Button size="sm" disabled={saving} onClick={salvar}>
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Salvar alterações'}
        </Button>
      </div>
      <p className="text-[11px] text-[hsl(var(--muted-foreground))]/70">
        Cargo, salário e CPF não são editáveis por aqui — fale com o DP se estiverem incorretos.
      </p>
    </div>
  );
}

function ReadField({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-3">
      <p className="text-[11px] text-[hsl(var(--muted-foreground))]">{label}</p>
      <p className="text-sm font-medium mt-0.5 break-words">{value || '-'}</p>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Minha escala (turnos reais — tabela shifts)
// --------------------------------------------------------------------------- //
interface EscalaShift {
  date: string;
  start_time: string;
  end_time: string;
  workplace: string | null;
  status: string;
}
interface EscalaData {
  employee_name?: string;
  month?: number;
  year?: number;
  shifts?: EscalaShift[];
  total_hours?: number;
  escala_padrao?: string | null;
  turno_padrao?: string | null;
  cargo?: string | null;
  posto_atual_nome?: string | null;
}
interface ProximoTurno {
  proximo_turno: EscalaShift | null;
}

function EscalaTab() {
  const now = new Date();
  const [mes, setMes] = useState(now.getMonth() + 1);
  const [ano, setAno] = useState(now.getFullYear());
  const [data, setData] = useState<EscalaData | null>(null);
  const [prox, setProx] = useState<EscalaShift | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError('');
      try {
        const [e, p] = await Promise.all([
          api.get(
            `/api/v1/people-management/portal/self-service/minha-escala?mes=${mes}&ano=${ano}`,
          ),
          api.get('/api/v1/people-management/portal/self-service/minha-escala/proximo-turno'),
        ]);
        setData(e.data);
        setProx((p.data as ProximoTurno)?.proximo_turno ?? null);
      } catch (err: unknown) {
        const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setError(msg || 'Não foi possível carregar sua escala.');
      } finally {
        setLoading(false);
      }
    })();
  }, [mes, ano]);

  const fmtDate = (d: string): string => {
    const [y, m, day] = String(d).split('-');
    return y ? `${day}/${m}` : d;
  };
  const hhmm = (t: string | null | undefined): string => (t ? String(t).slice(0, 5) : '');
  const statusLabel: Record<string, string> = {
    scheduled: 'Agendado', agendado: 'Agendado', completed: 'Concluído',
    in_progress: 'Em andamento', confirmed: 'Confirmado',
  };

  const shifts = data?.shifts || [];

  return (
    <div className="space-y-4">
      {/* Próximo turno em destaque */}
      {prox && (
        <div className="rounded-xl p-4 bg-[#f97707]/8 border border-[#f97707]/25">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-[#f97707] mb-1">
            Próximo turno
          </p>
          <p className="text-sm font-medium text-[hsl(var(--foreground))]">
            {fmtDate(prox.date)} · {hhmm(prox.start_time)} às {hhmm(prox.end_time)}
          </p>
          {prox.workplace && (
            <p className="text-xs text-[hsl(var(--muted-foreground))] flex items-center gap-1 mt-0.5">
              <MapPin className="w-3 h-3" /> {prox.workplace}
            </p>
          )}
        </div>
      )}

      <div className="flex items-center gap-2">
        <select
          value={mes}
          onChange={(e) => setMes(Number(e.target.value))}
          className="text-sm rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-2 py-1.5"
        >
          {['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'].map(
            (m, idx) => (
              <option key={idx} value={idx + 1}>{m}</option>
            ),
          )}
        </select>
        <select
          value={ano}
          onChange={(e) => setAno(Number(e.target.value))}
          className="text-sm rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-2 py-1.5"
        >
          {[now.getFullYear(), now.getFullYear() - 1].map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
        {typeof data?.total_hours === 'number' && data.total_hours > 0 && (
          <span className="text-xs text-[hsl(var(--muted-foreground))] ml-auto">
            {data.total_hours}h no mês
          </span>
        )}
      </div>

      {loading ? (
        <Spinner />
      ) : error ? (
        <ErrorBox msg={error} />
      ) : shifts.length === 0 ? (
        <EmptyState
          icon={CalendarClock}
          title="Nenhum turno no período"
          desc={
            data?.escala_padrao
              ? `Sua escala padrão é ${data.escala_padrao}. Nenhum turno publicado para o mês selecionado.`
              : 'Nenhum turno publicado para o mês selecionado.'
          }
        />
      ) : (
        <div className="space-y-2">
          {shifts.map((s, i) => (
            <div
              key={i}
              className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-3 flex items-center justify-between"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium">
                  {fmtDate(s.date)} · {hhmm(s.start_time)}–{hhmm(s.end_time)}
                </p>
                {s.workplace && (
                  <p className="text-xs text-[hsl(var(--muted-foreground))] flex items-center gap-1 truncate">
                    <MapPin className="w-3 h-3 flex-shrink-0" /> {s.workplace}
                  </p>
                )}
              </div>
              <span className="text-xs px-2 py-0.5 rounded-md bg-[hsl(var(--secondary))] text-[hsl(var(--muted-foreground))] font-medium whitespace-nowrap">
                {statusLabel[s.status] || s.status}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Comunicados / Notificações
// --------------------------------------------------------------------------- //
interface Comunicado {
  id: number;
  titulo: string | null;
  mensagem: string | null;
  tipo: string | null;
  lido: boolean;
  data: string | null;
}

function ComunicadosTab() {
  const [itens, setItens] = useState<Comunicado[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/api/v1/people-management/portal/self-service/minhas-notificacoes');
      setItens((res.data?.notificacoes || []) as Comunicado[]);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg || 'Não foi possível carregar seus comunicados.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const marcarLida = async (id: number) => {
    try {
      await api.patch(
        `/api/v1/people-management/portal/self-service/minhas-notificacoes/${id}/lida`,
      );
      setItens((prev) => prev.map((n) => (n.id === id ? { ...n, lido: true } : n)));
    } catch {
      /* silencioso: recarrega no próximo load */
    }
  };

  const fmt = (d: string | null): string => {
    if (!d) return '';
    const [date] = String(d).split(' ');
    const [y, m, day] = (date || '').split('-');
    return y ? `${day}/${m}/${y}` : String(d);
  };

  if (loading) return <Spinner />;
  if (error) return <ErrorBox msg={error} />;
  if (itens.length === 0)
    return (
      <EmptyState
        icon={Bell}
        title="Nenhum comunicado"
        desc="Quando o RH/DP publicar um aviso ou comunicado para você, ele aparece aqui."
      />
    );

  return (
    <div className="space-y-2">
      {itens.map((n) => (
        <div
          key={n.id}
          className={[
            'rounded-xl p-4 border',
            n.lido
              ? 'bg-[hsl(var(--card))] border-[hsl(var(--border))]'
              : 'bg-[#f97707]/6 border-[#f97707]/25',
          ].join(' ')}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                {!n.lido && <span className="inline-block w-2 h-2 rounded-full bg-[#f97707]" />}
                <p className="font-medium text-sm text-[hsl(var(--foreground))]">
                  {n.titulo || 'Comunicado'}
                </p>
              </div>
              {n.mensagem && (
                <p className="text-sm text-[hsl(var(--muted-foreground))]">{n.mensagem}</p>
              )}
              <p className="text-[11px] text-[hsl(var(--muted-foreground))]/70 mt-1">
                {fmt(n.data)}
              </p>
            </div>
            {!n.lido && (
              <button
                onClick={() => marcarLida(n.id)}
                className="text-xs text-[#f97707] font-medium whitespace-nowrap hover:underline"
              >
                Marcar lida
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// UI helpers
// --------------------------------------------------------------------------- //
function Spinner() {
  return (
    <div className="flex justify-center py-10">
      <Loader2 className="w-6 h-6 animate-spin text-[hsl(var(--primary))]" />
    </div>
  );
}

function ErrorBox({ msg }: { msg: string }) {
  return (
    <div className="bg-red-500/5 border border-red-500/20 rounded-xl p-3 text-sm text-red-500 flex items-center gap-2">
      <AlertTriangle className="w-4 h-4 flex-shrink-0" /> {msg}
    </div>
  );
}

function EmptyState({ icon: Icon, title, desc }: { icon: React.ElementType; title: string; desc: string }) {
  return (
    <div className="text-center py-10">
      <div className="w-14 h-14 mx-auto mb-3 rounded-2xl bg-[hsl(var(--secondary))] flex items-center justify-center">
        <Icon className="w-7 h-7 text-[hsl(var(--muted-foreground))]" />
      </div>
      <p className="font-medium text-sm text-[hsl(var(--foreground))]">{title}</p>
      <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">{desc}</p>
    </div>
  );
}

function Stat({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-3 text-center">
      <p className={['text-2xl font-bold font-mono', highlight ? 'text-[#f97707]' : 'text-[hsl(var(--foreground))]'].join(' ')}>
        {value}
      </p>
      <p className="text-[11px] text-[hsl(var(--muted-foreground))] mt-0.5">{label}</p>
    </div>
  );
}
