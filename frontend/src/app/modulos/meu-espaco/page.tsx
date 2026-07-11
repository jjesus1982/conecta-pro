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

type Tab = 'assinar' | 'holerite' | 'ferias' | 'ponto' | 'beneficios';

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: 'assinar', label: 'Documentos a assinar', icon: FileSignature },
  { id: 'holerite', label: 'Holerite', icon: FileText },
  { id: 'ferias', label: 'Férias', icon: CalendarDays },
  { id: 'ponto', label: 'Ponto', icon: Clock },
  { id: 'beneficios', label: 'Benefícios', icon: Gift },
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
            Aqui você assina seus documentos e consulta seu holerite, férias, ponto e benefícios.
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
        {tab === 'holerite' && <HoleriteTab />}
        {tab === 'ferias' && <FeriasTab />}
        {tab === 'ponto' && <PontoTab />}
        {tab === 'beneficios' && <BeneficiosTab />}
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
        const res = await api.get('/api/v1/portal/self-service/meus-holerites');
        const data = res.data;
        setItems(Array.isArray(data) ? data : data?.holerites || data?.items || []);
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
    const url = `${base}/api/v1/portal/self-service/meus-holerites/${mes}/${ano}/pdf`;
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
        const liquido = h.liquido ?? h.net ?? h.valor_liquido;
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
          api.get('/api/v1/portal/self-service/minhas-ferias/saldo'),
          api.get('/api/v1/portal/self-service/minhas-ferias/solicitacoes'),
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
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/api/v1/portal/self-service/meu-ponto');
        setData(res.data);
      } catch (e: unknown) {
        const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setError(msg || 'Não foi possível carregar seu ponto.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <Spinner />;
  if (error) return <ErrorBox msg={error} />;

  const registros = (data?.registros || data?.batidas || data?.historico || []) as Record<string, unknown>[];

  if (!Array.isArray(registros) || registros.length === 0)
    return <EmptyState icon={Clock} title="Sem registros" desc="Nenhuma batida de ponto no período." />;

  return (
    <div className="space-y-2">
      {registros.map((r, i) => (
        <div key={i} className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-3 flex items-center justify-between text-sm">
          <span>{String(r.data || r.date || r.dia || '')}</span>
          <span className="text-[hsl(var(--muted-foreground))]">
            {String(r.entrada || r.check_in || '')} {r.saida || r.check_out ? `— ${String(r.saida || r.check_out)}` : ''}
          </span>
        </div>
      ))}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Benefícios
// --------------------------------------------------------------------------- //
function BeneficiosTab() {
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/api/v1/portal/self-service/meus-beneficios');
        const d = res.data;
        setItems(Array.isArray(d) ? d : d?.beneficios || d?.benefits || d?.items || []);
      } catch (e: unknown) {
        const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setError(msg || 'Não foi possível carregar seus benefícios.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <Spinner />;
  if (error) return <ErrorBox msg={error} />;
  if (items.length === 0)
    return <EmptyState icon={Gift} title="Sem benefícios" desc="Nenhum benefício cadastrado." />;

  return (
    <div className="space-y-2">
      {items.map((b, i) => (
        <div key={i} className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 flex items-center justify-between">
          <span className="text-sm font-medium">{String(b.nome || b.name || b.tipo || b.type || 'Benefício')}</span>
          {(b.valor ?? b.value) != null && (
            <span className="text-sm text-[hsl(var(--muted-foreground))]">
              {typeof (b.valor ?? b.value) === 'number'
                ? `R$ ${Number(b.valor ?? b.value).toFixed(2)}`
                : String(b.valor ?? b.value)}
            </span>
          )}
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
