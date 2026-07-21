'use client';

/**
 * Meu Espaço — Área self-service do funcionário (login Google, role='funcionario').
 *
 * Só LEITURA do que é DELE + ASSINAR o que é DELE. Nenhum módulo de gestão.
 * Fonte: users.employee_id (resolvido no backend a partir do JWT principal).
 *
 * Abas:
 *  - Documentos a assinar (GET /signatures/meus-pendentes → {a_assinar_agora, historico_opcional};
 *    POST /signatures/{id}/sign; POST /signatures/assinar-lote) — ESSENCIAL
 *  - Holerite  (GET /portal/self-service/meus-holerites[/{m}/{a}][/pdf])
 *  - Férias    (GET /portal/self-service/minhas-ferias/*)
 *  - Ponto     (GET /portal/self-service/meu-ponto)
 *  - Benefícios(GET /portal/self-service/meus-beneficios)
 */

import { useCallback, useEffect, useState } from 'react';
import { msgFromDetail } from '@/lib/string';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import {
  FileSignature, FileText, CalendarDays, Clock, Gift, LogOut,
  CheckCircle2, Loader2, ShieldCheck, AlertTriangle,
  GraduationCap, User as UserIcon, FolderOpen, Download, Award,
  CalendarClock, Bell, MapPin, Camera, Fingerprint, X,
  Receipt, Wallet, Paperclip, Send,
  ChevronDown, ChevronRight, ChevronLeft, History,
  Megaphone, Upload, Lock, EyeOff,
} from 'lucide-react';
import api from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/ui/button';
import { FacialCapture, type FacialCaptureResult } from '@/components/ponto/FacialCapture';

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
  /** M2: true = histórico/opcional (competência antiga ou lote retroativo). */
  opcional?: boolean;
}

interface MeusDados {
  nome?: string | null; cpf?: string | null; cargo?: string | null;
  data_admissao?: string | null; telefone?: string | null; celular?: string | null; email?: string | null;
  endereco?: string | null;
  cep?: string | null; logradouro?: string | null; numero?: string | null; complemento?: string | null;
  bairro?: string | null; cidade?: string | null; uf?: string | null;
  nome_mae?: string | null; nome_pai?: string | null;
  naturalidade?: string | null; nacionalidade?: string | null;
  rg?: string | null; rg_orgao?: string | null; rg_uf?: string | null;
  estado_civil?: string | null; pis?: string | null;
  contato_emergencia?: string | null; telefone_emergencia?: string | null;
}

interface CampoFaltante { campo: string; label: string; }
interface OnboardingStatus {
  pendente: boolean; bloqueante?: boolean; modo_transicao?: boolean;
  total_obrigatorios: number; total_ok: number;
  campos_ok: string[]; campos_faltantes: CampoFaltante[];
}

/** Máscaras BR (contingência client-side; a fonte da verdade é o backend). */
function maskTelefone(v: string): string {
  const d = v.replace(/\D/g, '').slice(0, 11);
  if (d.length <= 10) return d.replace(/(\d{2})(\d{4})(\d{0,4})/, '($1) $2-$3').replace(/[-\s()]+$/, '');
  return d.replace(/(\d{2})(\d{5})(\d{0,4})/, '($1) $2-$3').replace(/[-\s()]+$/, '');
}
function maskCep(v: string): string {
  const d = v.replace(/\D/g, '').slice(0, 8);
  return d.replace(/(\d{5})(\d{0,3})/, '$1-$2').replace(/-$/, '');
}
function maskPis(v: string): string {
  const d = v.replace(/\D/g, '').slice(0, 11);
  return d.replace(/(\d{3})(\d{5})(\d{2})(\d{0,1})/, '$1.$2.$3-$4').replace(/[.\-]+$/, '');
}
const ESTADO_CIVIL_OPTS = [
  { v: 'solteiro', l: 'Solteiro(a)' }, { v: 'casado', l: 'Casado(a)' },
  { v: 'divorciado', l: 'Divorciado(a)' }, { v: 'viuvo', l: 'Viúvo(a)' },
  { v: 'uniao_estavel', l: 'União estável' },
];
const SS_BASE = '/api/v1/people-management/portal/self-service';

type Tab =
  | 'assinar' | 'holerite' | 'ferias' | 'ponto' | 'beneficios'
  | 'documentos' | 'treinamentos' | 'dados'
  | 'escala' | 'comunicados' | 'reembolso' | 'ouvidoria';

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: 'assinar', label: 'Documentos a assinar', icon: FileSignature },
  { id: 'comunicados', label: 'Comunicados', icon: Bell },
  { id: 'escala', label: 'Minha escala', icon: CalendarClock },
  { id: 'holerite', label: 'Holerite', icon: FileText },
  { id: 'documentos', label: 'Documentos', icon: FolderOpen },
  { id: 'ferias', label: 'Férias', icon: CalendarDays },
  { id: 'ponto', label: 'Ponto', icon: Clock },
  { id: 'beneficios', label: 'Benefícios', icon: Gift },
  { id: 'reembolso', label: 'Reembolso', icon: Receipt },
  { id: 'treinamentos', label: 'Treinamentos', icon: GraduationCap },
  { id: 'ouvidoria', label: 'Ouvidoria', icon: Megaphone },
  { id: 'dados', label: 'Meus dados', icon: UserIcon },
];

export default function MeuEspacoPage() {
  const router = useRouter();
  const { user, isLoading, isAuthenticated, logout } = useAuth();
  const [tab, setTab] = useState<Tab | null>(null);  // null = home (grid de cards)
  const [onbStatus, setOnbStatus] = useState<OnboardingStatus | null>(null);
  const [onbLoading, setOnbLoading] = useState(true);
  const [completarAberto, setCompletarAberto] = useState(false);  // modo transição: abre o form sob demanda

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace('/login');
  }, [isLoading, isAuthenticated, router]);

  // Verifica o onboarding obrigatório no 1º acesso (funcionário/líder).
  useEffect(() => {
    if (isLoading || !isAuthenticated) return;
    (async () => {
      try {
        const res = await api.get(`${SS_BASE}/onboarding-status`);
        setOnbStatus(res.data);
      } catch {
        // Se a conta não é funcionário (sem employee_id) → não bloqueia.
        setOnbStatus({ pendente: false, total_obrigatorios: 0, total_ok: 0, campos_ok: [], campos_faltantes: [] });
      } finally {
        setOnbLoading(false);
      }
    })();
  }, [isLoading, isAuthenticated]);

  if (isLoading || onbLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-[hsl(var(--primary))]" />
      </div>
    );
  }

  // GATE: só BLOQUEIA quando bloqueante=true (enforce). No modo transição (rollout
  // 01/08), o funcionário entra e bate ponto — o cadastro pendente vira um banner.
  if (onbStatus?.bloqueante) {
    return (
      <OnboardingGate
        status={onbStatus}
        userName={user?.name}
        onLogout={logout}
        onDone={(novo) => setOnbStatus(novo)}
      />
    );
  }

  // Modo transição + cadastro pendente + o funcionário clicou em "Completar agora":
  // mostra o MESMO formulário, mas com opção de voltar (não bloqueia).
  if (completarAberto && onbStatus?.pendente) {
    return (
      <OnboardingGate
        status={onbStatus}
        userName={user?.name}
        onLogout={logout}
        onDone={(novo) => { setOnbStatus(novo); if (!novo.pendente) setCompletarAberto(false); }}
        onVoltar={() => setCompletarAberto(false)}
      />
    );
  }

  return (
    <div className="light min-h-screen bg-[hsl(var(--background))]">
      {/* Faixa laranja da marca (padrão-ouro Conecta Mais) */}
      <div className="h-1.5 bg-[#F97316]" />
      {/* Header — logo da marca CENTRALIZADA e em destaque (Sair fixo à direita) */}
      <header className="relative h-24 flex items-center justify-center px-4 lg:px-6 bg-white border-b border-[hsl(var(--border))]">
        <div className="flex items-center gap-3">
          <Image src="/images/logo-marca-v2.png" alt="Conecta PRO" width={282} height={197} priority className="h-16 sm:h-20 w-auto" />
          <span className="hidden md:inline text-lg font-semibold text-[#1E3A5F] border-l border-[hsl(var(--border))] pl-3">
            Meu&nbsp;<span style={{ color: '#F97316' }}>Espaço</span>
          </span>
        </div>
        <div className="absolute right-4 lg:right-6 flex items-center gap-3">
          <span className="text-sm text-[hsl(var(--muted-foreground))] hidden lg:inline">
            {user?.name}
          </span>
          <Button variant="outline" size="sm" onClick={logout}>
            <LogOut className="w-4 h-4 mr-1.5" /> Sair
          </Button>
        </div>
      </header>

      <div className="max-w-3xl mx-auto p-4 lg:p-6">
        {/* Modo transição: cadastro pendente NÃO bloqueia, mas lembra sempre. */}
        {onbStatus?.pendente && (
          <div className="mb-5 rounded-xl border border-amber-300 bg-amber-100 px-4 py-3 flex items-start gap-3">
            <Clock className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-amber-800">
                Complete seu cadastro ({onbStatus.total_ok}/{onbStatus.total_obrigatorios} campos)
              </p>
              <p className="text-xs text-amber-700 mt-0.5">
                Você já pode bater ponto normalmente. Falta preencher {onbStatus.campos_faltantes.length} dado(s)
                obrigatório(s) do eSocial — leva 2 minutos.
              </p>
            </div>
            <Button size="sm" onClick={() => setCompletarAberto(true)} className="shrink-0">
              Completar agora
            </Button>
          </div>
        )}
        {/* Boas-vindas */}
        <div className="mb-5">
          <h1 className="font-display text-xl font-bold text-[hsl(var(--foreground))]">
            Olá, {user?.name?.split(' ')[0] || 'colaborador'}
          </h1>
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            Aqui você assina e baixa seus documentos e consulta holerite, férias, ponto,
            benefícios, treinamentos e seus dados.
          </p>
        </div>

        {/* HOME: grid de cards (mais intuitivo). Ponto em destaque. */}
        {tab === null ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {TABS.map((t) => {
              const Icon = t.icon;
              const isPonto = t.id === 'ponto';
              return (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={[
                    'flex flex-col items-center justify-center gap-2.5 rounded-2xl p-4 min-h-[108px] border text-center transition-colors',
                    isPonto
                      ? 'bg-[#1E3A5F] border-[#1E3A5F] text-white shadow-sm active:bg-[#16304F]'
                      : 'bg-white border-[hsl(var(--border))] text-[#1E3A5F] hover:border-[#2D5F8B] hover:bg-blue-50 active:bg-blue-50 active:border-[#2D5F8B]',
                  ].join(' ')}
                >
                  <Icon className={isPonto ? 'w-7 h-7 text-white' : 'w-7 h-7 text-[#2D5F8B]'} />
                  <span className="text-xs font-semibold leading-tight">{t.label}</span>
                </button>
              );
            })}
          </div>
        ) : (
          <div>
            <button
              onClick={() => setTab(null)}
              className="mb-4 inline-flex items-center gap-1.5 text-sm font-semibold text-[#2D5F8B]"
            >
              <ChevronLeft className="w-4 h-4" /> Voltar
            </button>
            <h2 className="font-display text-lg font-bold mb-4 text-[#1E3A5F]">
              {TABS.find((t) => t.id === tab)?.label}
            </h2>
            {tab === 'assinar' && <AssinarTab />}
            {tab === 'comunicados' && <ComunicadosTab />}
            {tab === 'escala' && <EscalaTab />}
            {tab === 'holerite' && <HoleriteTab />}
            {tab === 'documentos' && <DocumentosTab onIrAssinar={() => setTab('assinar')} />}
            {tab === 'ferias' && <FeriasTab />}
            {tab === 'ponto' && <PontoTab />}
            {tab === 'beneficios' && <BeneficiosTab />}
            {tab === 'reembolso' && <ReembolsoTab />}
            {tab === 'treinamentos' && <TreinamentosTab />}
            {tab === 'ouvidoria' && <OuvidoriaTab />}
            {tab === 'dados' && <DadosTab />}
          </div>
        )}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Onboarding obrigatório (1º acesso) — completar cadastro
// --------------------------------------------------------------------------- //
function OnboardingGate({
  status, userName, onLogout, onDone, onVoltar,
}: {
  status: OnboardingStatus;
  userName?: string | null;
  onLogout: () => void;
  onDone: (novo: OnboardingStatus) => void;
  onVoltar?: () => void;  // modo transição: volta ao Meu Espaço sem completar
}) {
  const faltantes = new Set(status.campos_faltantes.map((f) => f.campo));
  const [form, setForm] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [fieldErr, setFieldErr] = useState<Record<string, string>>({});

  const set = (k: string, v: string) => setForm((p) => ({ ...p, [k]: v }));

  // Campos obrigatórios que ainda faltam (só exibimos os que faltam).
  const obrig = status.campos_faltantes.map((f) => f.campo);

  const validar = (): boolean => {
    const errs: Record<string, string> = {};
    for (const c of obrig) {
      const val = (form[c] || '').trim();
      if (!val) { errs[c] = 'Campo obrigatório'; continue; }
      if (c === 'telefone' && val.replace(/\D/g, '').length < 10) errs[c] = 'Telefone incompleto';
      if (c === 'cep' && val.replace(/\D/g, '').length !== 8) errs[c] = 'CEP deve ter 8 dígitos';
      if (c === 'pis' && val.replace(/\D/g, '').length !== 11) errs[c] = 'PIS deve ter 11 dígitos';
    }
    setFieldErr(errs);
    return Object.keys(errs).length === 0;
  };

  const salvar = async () => {
    if (!validar()) return;
    setSaving(true); setError('');
    try {
      // Envia apenas os campos preenchidos (todos gravam DIRETO em employees).
      const payload: Record<string, string> = {};
      for (const [k, v] of Object.entries(form)) if (v && v.trim()) payload[k] = v.trim();
      const res = await api.put(`${SS_BASE}/meus-dados`, payload);
      const novo: OnboardingStatus | undefined = res.data?.onboarding;
      if (novo && !novo.pendente) { onDone(novo); return; }
      if (novo) {
        // Ainda faltam campos — atualiza a lista e avisa.
        onDone(novo);
        setError('Ainda há campos obrigatórios pendentes.');
      } else {
        // Sem status no retorno: recarrega para confirmar.
        const st = await api.get(`${SS_BASE}/onboarding-status`);
        onDone(st.data);
      }
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Não foi possível salvar. Confira os campos e tente de novo.');
    } finally {
      setSaving(false);
    }
  };

  const inputCls = (c: string) =>
    [
      'w-full rounded-lg border bg-[hsl(var(--background))] px-3 py-2 text-sm outline-none',
      fieldErr[c] ? 'border-red-500 focus:border-red-500' : 'border-[hsl(var(--border))] focus:border-[#F97316]',
    ].join(' ');

  const Field = ({ campo, label, children }: { campo: string; label: string; children: React.ReactNode }) => (
    <div>
      <label className="text-xs text-[hsl(var(--muted-foreground))]">
        {label} <span className="text-red-500">*</span>
      </label>
      {children}
      {fieldErr[campo] && <p className="text-[11px] text-red-500 mt-0.5">{fieldErr[campo]}</p>}
    </div>
  );

  const grupoEndereco = ['cep', 'logradouro', 'numero', 'bairro', 'cidade', 'uf'].filter((c) => faltantes.has(c));
  const grupoContato = ['telefone'].filter((c) => faltantes.has(c));
  const grupoDoc = ['nome_mae', 'nome_pai', 'naturalidade', 'nacionalidade', 'rg', 'estado_civil', 'pis'].filter((c) => faltantes.has(c));

  return (
    <div className="light min-h-screen bg-[hsl(var(--background))]">
      <header className="h-14 flex items-center justify-between px-4 lg:px-6 bg-[hsl(var(--card))] border-b border-[hsl(var(--border))]">
        <div className="flex items-center gap-2.5">
          <Image src="/images/logo-marca-v2.png" alt="Conecta PRO" width={282} height={197} className="h-14 w-auto" />
          <span className="font-display text-sm font-semibold tracking-tight">
            Meu&nbsp;<span style={{ color: '#F97316' }}>Espaço</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          {onVoltar && (
            <Button variant="ghost" size="sm" onClick={onVoltar}>
              ← Depois
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={onLogout}>
            <LogOut className="w-4 h-4 mr-1.5" /> Sair
          </Button>
        </div>
      </header>

      <div className="max-w-2xl mx-auto p-4 lg:p-6">
        <div className="mb-5 flex items-start gap-3">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#F97316]/10">
            <ShieldCheck className="h-5 w-5 text-[#F97316]" />
          </div>
          <div>
            <h1 className="font-display text-xl font-bold">
              Bem-vindo{userName ? `, ${userName.split(' ')[0]}` : ''}! Complete seu cadastro
            </h1>
            <p className="text-sm text-[hsl(var(--muted-foreground))] mt-0.5">
              Para liberar o Meu Espaço, precisamos de alguns dados obrigatórios (exigidos pelo
              eSocial). Você preenche <b>uma vez</b> e essas informações passam a valer em todos os
              módulos, sem duplicidade.
            </p>
          </div>
        </div>

        <div className="mb-4 h-1.5 w-full rounded-full bg-[hsl(var(--muted))]/40">
          <div
            className="h-1.5 rounded-full bg-[#F97316] transition-all"
            style={{ width: `${Math.round((status.total_ok / Math.max(status.total_obrigatorios, 1)) * 100)}%` }}
          />
        </div>

        <div className="space-y-6 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-2xl p-4 lg:p-5">
          {grupoContato.length > 0 && (
            <section className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70">Contato</p>
              <Field campo="telefone" label="Telefone / celular">
                <input className={inputCls('telefone')} inputMode="tel" placeholder="(92) 90000-0000"
                  value={form.telefone || ''} onChange={(e) => set('telefone', maskTelefone(e.target.value))} />
              </Field>
            </section>
          )}

          {grupoEndereco.length > 0 && (
            <section className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70">Endereço</p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {faltantes.has('cep') && (
                  <Field campo="cep" label="CEP">
                    <input className={inputCls('cep')} inputMode="numeric" placeholder="69000-000"
                      value={form.cep || ''} onChange={(e) => set('cep', maskCep(e.target.value))} />
                  </Field>
                )}
                {faltantes.has('logradouro') && (
                  <div className="sm:col-span-2">
                    <Field campo="logradouro" label="Endereço (rua/avenida)">
                      <input className={inputCls('logradouro')} value={form.logradouro || ''}
                        onChange={(e) => set('logradouro', e.target.value)} />
                    </Field>
                  </div>
                )}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {faltantes.has('numero') && (
                  <Field campo="numero" label="Número">
                    <input className={inputCls('numero')} value={form.numero || ''}
                      onChange={(e) => set('numero', e.target.value)} />
                  </Field>
                )}
                {faltantes.has('bairro') && (
                  <Field campo="bairro" label="Bairro">
                    <input className={inputCls('bairro')} value={form.bairro || ''}
                      onChange={(e) => set('bairro', e.target.value)} />
                  </Field>
                )}
                {faltantes.has('cidade') && (
                  <Field campo="cidade" label="Cidade">
                    <input className={inputCls('cidade')} value={form.cidade || ''}
                      onChange={(e) => set('cidade', e.target.value)} />
                  </Field>
                )}
                {faltantes.has('uf') && (
                  <Field campo="uf" label="UF">
                    <input className={inputCls('uf')} maxLength={2} placeholder="AM"
                      value={form.uf || ''} onChange={(e) => set('uf', e.target.value.toUpperCase().slice(0, 2))} />
                  </Field>
                )}
              </div>
            </section>
          )}

          {grupoDoc.length > 0 && (
            <section className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70">Documentos e filiação</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {faltantes.has('nome_mae') && (
                  <div className="sm:col-span-2">
                    <Field campo="nome_mae" label="Nome da mãe">
                      <input className={inputCls('nome_mae')} value={form.nome_mae || ''}
                        onChange={(e) => set('nome_mae', e.target.value)} />
                    </Field>
                  </div>
                )}
                {faltantes.has('nome_pai') && (
                  <div className="sm:col-span-2">
                    <Field campo="nome_pai" label="Nome do pai">
                      <input className={inputCls('nome_pai')} value={form.nome_pai || ''}
                        onChange={(e) => set('nome_pai', e.target.value)} />
                    </Field>
                  </div>
                )}
                {faltantes.has('naturalidade') && (
                  <Field campo="naturalidade" label="Naturalidade (cidade de nascimento)">
                    <input className={inputCls('naturalidade')} value={form.naturalidade || ''}
                      onChange={(e) => set('naturalidade', e.target.value)} />
                  </Field>
                )}
                {faltantes.has('nacionalidade') && (
                  <Field campo="nacionalidade" label="Nacionalidade">
                    <input className={inputCls('nacionalidade')} placeholder="Brasileira"
                      value={form.nacionalidade || ''} onChange={(e) => set('nacionalidade', e.target.value)} />
                  </Field>
                )}
                {faltantes.has('rg') && (
                  <Field campo="rg" label="RG">
                    <input className={inputCls('rg')} value={form.rg || ''}
                      onChange={(e) => set('rg', e.target.value)} />
                  </Field>
                )}
                {faltantes.has('estado_civil') && (
                  <Field campo="estado_civil" label="Estado civil">
                    <select className={inputCls('estado_civil')} value={form.estado_civil || ''}
                      onChange={(e) => set('estado_civil', e.target.value)}>
                      <option value="">Selecione...</option>
                      {ESTADO_CIVIL_OPTS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
                    </select>
                  </Field>
                )}
                {faltantes.has('pis') && (
                  <Field campo="pis" label="PIS/PASEP">
                    <input className={inputCls('pis')} inputMode="numeric" placeholder="000.00000.00-0"
                      value={form.pis || ''} onChange={(e) => set('pis', maskPis(e.target.value))} />
                  </Field>
                )}
              </div>
            </section>
          )}

          {error && <ErrorBox msg={error} />}

          <div className="flex items-center justify-between pt-1">
            <p className="text-[11px] text-[hsl(var(--muted-foreground))]/70">
              Campos com <span className="text-red-500">*</span> são obrigatórios.
            </p>
            <Button size="sm" disabled={saving} onClick={salvar}>
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Salvar e continuar'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Documentos a assinar (ESSENCIAL)
// --------------------------------------------------------------------------- //
function AssinarTab() {
  // M2: separa CORRENTE (a assinar agora, obrigatório) de HISTÓRICO (opcional).
  const [aAssinar, setAAssinar] = useState<PendingDoc[]>([]);
  const [historico, setHistorico] = useState<PendingDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [signingId, setSigningId] = useState<string | null>(null);
  const [loteLoading, setLoteLoading] = useState(false);
  const [histAberto, setHistAberto] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/api/v1/signatures/meus-pendentes');
      // Novo formato separado; fallback ao antigo `pendentes` por segurança.
      const ag: PendingDoc[] = res.data.a_assinar_agora
        ?? (res.data.pendentes || []).filter((d: PendingDoc) => !d.opcional);
      const hist: PendingDoc[] = res.data.historico_opcional
        ?? (res.data.pendentes || []).filter((d: PendingDoc) => d.opcional);
      setAAssinar(ag);
      setHistorico(hist);
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

  // Assina em lote uma lista de solicitações (histórico e/ou corrente).
  const assinarLote = async (docs: PendingDoc[]) => {
    const ids = docs.filter((d) => !d.is_expired).map((d) => d.request_id);
    if (ids.length === 0) return;
    const ok = window.confirm(
      `Você está assinando ${ids.length} documento(s) de uma vez. ` +
      'Cada um recebe uma assinatura eletrônica com data/hora e hash (validade legal). Confirmar?'
    );
    if (!ok) return;
    setLoteLoading(true);
    setError('');
    try {
      await api.post('/api/v1/signatures/assinar-lote', {
        request_ids: ids,
        evidence: { device: 'meu-espaco-web', extra: { origem: 'assinar-lote' } },
      });
      await load();
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg || 'Não foi possível assinar os documentos em lote.');
    } finally {
      setLoteLoading(false);
    }
  };

  if (loading) return <Spinner />;

  const histAssinaveis = historico.filter((d) => !d.is_expired).length;

  const DocCard = (d: PendingDoc, opcional: boolean) => (
    <div
      key={d.request_id}
      className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 flex items-start justify-between gap-4"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <FileSignature className={`w-4 h-4 flex-shrink-0 ${opcional ? 'text-[hsl(var(--muted-foreground))]' : 'text-[#F97316]'}`} />
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
        variant={opcional ? 'outline' : 'primary'}
        disabled={d.is_expired || signingId === d.request_id || loteLoading}
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
  );

  return (
    <div className="space-y-5">
      {error && <ErrorBox msg={error} />}

      {/* SEÇÃO 1 — A ASSINAR (corrente, destaque) */}
      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-[hsl(var(--foreground))]">
            <FileSignature className="w-4 h-4 text-[#F97316]" />
            A assinar
            {aAssinar.length > 0 && (
              <span className="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1.5 rounded-full bg-[#F97316] text-white text-[11px] font-semibold">
                {aAssinar.length}
              </span>
            )}
          </h2>
          {aAssinar.filter((d) => !d.is_expired).length > 1 && (
            <Button
              size="sm"
              disabled={loteLoading || signingId !== null}
              onClick={() => assinarLote(aAssinar)}
            >
              {loteLoading ? <Loader2 className="w-4 h-4 animate-spin" />
                : <><ShieldCheck className="w-4 h-4 mr-1.5" /> Assinar todos</>}
            </Button>
          )}
        </div>
        {aAssinar.length === 0 ? (
          <EmptyState
            icon={CheckCircle2}
            title="Nenhum documento a assinar agora"
            desc="Você está em dia. Quando houver um documento novo para assinar, ele aparece aqui em destaque."
          />
        ) : (
          <div className="space-y-3">
            {aAssinar.map((d) => DocCard(d, false))}
          </div>
        )}
      </section>

      {/* SEÇÃO 2 — HISTÓRICO (opcional, recolhido) */}
      {historico.length > 0 && (
        <section className="border border-[hsl(var(--border))] rounded-xl overflow-hidden">
          <button
            type="button"
            onClick={() => setHistAberto((v) => !v)}
            className="w-full flex items-center justify-between gap-3 px-4 py-3 bg-[hsl(var(--muted))]/40 hover:bg-[hsl(var(--muted))]/60 transition-colors text-left"
          >
            <span className="flex items-center gap-2 text-sm font-medium text-[hsl(var(--foreground))]">
              {histAberto ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
              <History className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              Histórico (opcional)
              <span className="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1.5 rounded-full bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))] text-[11px] font-semibold">
                {historico.length}
              </span>
            </span>
          </button>

          {histAberto && (
            <div className="p-4 space-y-3 border-t border-[hsl(var(--border))]">
              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                Documentos de competências anteriores (contracheques, folhas de ponto e comprovantes
                de meses passados). Não é obrigatório assinar agora — você pode assinar quando quiser,
                um a um ou todos de uma vez.
              </p>
              {histAssinaveis > 0 && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={loteLoading || signingId !== null}
                  onClick={() => assinarLote(historico)}
                >
                  {loteLoading ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <><ShieldCheck className="w-4 h-4 mr-1.5" /> Assinar todos do histórico ({histAssinaveis})</>}
                </Button>
              )}
              <div className="space-y-3">
                {historico.map((d) => DocCard(d, true))}
              </div>
            </div>
          )}
        </section>
      )}

      <p className="text-[11px] text-[hsl(var(--muted-foreground))]/70 pt-2">
        Assinatura eletrônica com carimbo de data/hora e hash SHA-256 (MP 2.200-2/ICP-Brasil).
        Assinar em lote gera uma assinatura individual (com hash próprio) para cada documento.
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
// Ponto — BATER (GPS + selfie) + histórico do dia + histórico mensal
// --------------------------------------------------------------------------- //
const PONTO_BASE = '/api/v1/people-management/portal/self-service';

interface PontoHojeBatida {
  tipo?: string | null;
  hora?: string | null;
  data_hora?: string | null;
  posto?: string | null;
  dentro_geofence?: boolean | null;
}
interface PontoHoje {
  proxima_batida?: 'entrada' | 'saida' | 'saida_almoco' | 'retorno_almoco' | 'concluido' | string | null;
  proxima_label?: string | null;
  num_batidas_dia?: number | null;
  jornada_concluida?: boolean | null;
  batidas?: PontoHojeBatida[];
  horas_trabalhadas?: string | number | null;
  posto?: string | null;
  posto_nome?: string | null;
  data?: string | null;
}
interface BaterResultado {
  ok: boolean;
  tipo?: string | null;
  hora?: string | null;
  posto?: string | null;
  posto_nome?: string | null;
  dentro_geofence?: boolean | null;
  posto_sem_localizacao?: boolean | null;
  mensagem?: string | null;
}

/** Captura a posição GPS com alta precisão. Rejeita com mensagem amigável. */
function obterLocalizacao(): Promise<{ latitude: number; longitude: number; accuracy: number }> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      reject(new Error('Este dispositivo não suporta geolocalização. O ponto exige localização.'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        }),
      (err) => {
        if (err.code === err.PERMISSION_DENIED) {
          reject(new Error('Localização negada. O ponto exige sua localização — ative o GPS e permita o acesso.'));
        } else if (err.code === err.POSITION_UNAVAILABLE) {
          reject(new Error('Não foi possível obter sua localização. Verifique o GPS e tente de novo.'));
        } else if (err.code === err.TIMEOUT) {
          reject(new Error('A localização demorou demais. Tente novamente em local aberto.'));
        } else {
          reject(new Error('Falha ao obter localização.'));
        }
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  });
}

function PontoTab() {
  const { user } = useAuth();
  const now = new Date();
  const [mes, setMes] = useState(now.getMonth() + 1);
  const [ano, setAno] = useState(now.getFullYear());
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Estado do dia (para saber se a próxima batida é entrada ou saída).
  const [hoje, setHoje] = useState<PontoHoje | null>(null);
  const [hojeLoading, setHojeLoading] = useState(true);

  // Fluxo de bater: idle → gps → facial → sending → done/error. 'enroll' = cadastro do rosto.
  const [fase, setFase] = useState<'idle' | 'gps' | 'facial' | 'enroll' | 'sending'>('idle');
  const [baterErro, setBaterErro] = useState('');
  const [resultado, setResultado] = useState<BaterResultado | null>(null);
  const [geo, setGeo] = useState<{ latitude: number; longitude: number } | null>(null);

  // Reconhecimento facial: rosto de referência cadastrado (obrigatório antes de bater).
  const [faceEnrolled, setFaceEnrolled] = useState<boolean | null>(null); // null = carregando
  const [faceRef, setFaceRef] = useState<Float32Array | null>(null);

  const carregarFace = useCallback(async () => {
    try {
      const res = await api.get(`${PONTO_BASE}/facial/referencia`);
      const enrolled = Boolean(res.data?.enrolled);
      setFaceEnrolled(enrolled);
      setFaceRef(enrolled && Array.isArray(res.data?.descriptor)
        ? new Float32Array(res.data.descriptor as number[]) : null);
    } catch {
      setFaceEnrolled(false);
      setFaceRef(null);
    }
  }, []);
  useEffect(() => { carregarFace(); }, [carregarFace]);

  // Cadastro do rosto de referência (enrollment) — captura o descriptor e envia.
  const onEnrollCapture = async (r: FacialCaptureResult) => {
    if (!r.descriptor?.length) {
      setBaterErro('Não foi possível ler seu rosto. Tente em local iluminado, rosto centralizado.');
      setFase('idle');
      return;
    }
    setFase('sending');
    setBaterErro('');
    try {
      await api.post(`${PONTO_BASE}/facial/cadastrar`, { descriptor: r.descriptor });
      await carregarFace();
      setResultado(null);
    } catch {
      setBaterErro('Falha ao cadastrar o rosto. Tente novamente.');
    } finally {
      setFase('idle');
    }
  };

  // Batida com match facial: só envia se o rosto bateu com a referência.
  const onFacialCapture = async (r: FacialCaptureResult) => {
    if (!r.matched) {
      setBaterErro('Rosto não reconhecido. A batida só é confirmada com reconhecimento facial. Tente novamente.');
      setFase('idle');
      setGeo(null);
      return;
    }
    if (!geo) { setBaterErro('Localização perdida. Toque em bater ponto novamente.'); setFase('idle'); return; }
    setFase('sending');
    setBaterErro('');
    try {
      // Retry resiliente: a batida é IDEMPOTENTE no backend (janela de 90s não duplica),
      // então repetir em soluço (rede/backend reiniciando) é seguro e evita "falha ao salvar".
      const payload = {
        match: true,
        confidence: r.confidence,
        liveness_check: true,
        foto_base64: r.imageData,
        location: { latitude: geo.latitude, longitude: geo.longitude, accuracy: 0 },
        punch_type: proximoTipo,
      };
      let res;
      for (let i = 0; i < 3; i++) {
        try { res = await api.post(`${PONTO_BASE}/facial/batida`, payload); break; }
        catch (e: unknown) {
          const st = (e as { response?: { status?: number } })?.response?.status;
          if ((!st || st >= 500) && i < 2) { await new Promise((rs) => setTimeout(rs, 600 * (i + 1))); continue; }
          throw e;
        }
      }
      setResultado({ ok: true, ...(res?.data || {}) });
      await carregarHoje();
      if (mes === now.getMonth() + 1 && ano === now.getFullYear()) await carregarMes();
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setBaterErro(typeof msg === 'string' ? msg : 'Não foi possível registrar o ponto. Tente novamente.');
    } finally {
      setFase('idle');
      setGeo(null);
    }
  };

  // Contingência: não conseguiu bater pelo rosto (câmera/celular) → registra p/ o DP validar.
  const baterContingencia = async () => {
    if (!window.confirm('Não conseguiu bater pelo rosto? Vamos registrar sua batida para o DP validar — você não perde o ponto. Continuar?')) return;
    setFase('sending'); setBaterErro('');
    try {
      const res = await api.post(`${PONTO_BASE}/batida-contingencia`, {});
      setResultado({ ok: true, contingencia: true, ...(res.data || {}) });
      await carregarHoje();
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setBaterErro(typeof msg === 'string' ? msg : 'Não foi possível registrar a contingência.');
    } finally { setFase('idle'); setGeo(null); }
  };

  const isLider = ['lider', 'líder', 'supervisor', 'gerente', 'gestor', 'coordenador', 'admin', 'all']
    .some((r) => (user?.role || '').toLowerCase().includes(r));

  const carregarHoje = useCallback(async () => {
    setHojeLoading(true);
    try {
      const res = await api.get(`${PONTO_BASE}/ponto-hoje`);
      setHoje(res.data);
    } catch {
      // Endpoint pode não existir ainda / conta sem employee — não bloqueia o histórico.
      setHoje(null);
    } finally {
      setHojeLoading(false);
    }
  }, []);

  const carregarMes = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get(`${PONTO_BASE}/meu-ponto?mes=${mes}&ano=${ano}`);
      setData(res.data);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg || 'Não foi possível carregar seu ponto.');
    } finally {
      setLoading(false);
    }
  }, [mes, ano]);

  useEffect(() => { carregarHoje(); }, [carregarHoje]);
  useEffect(() => { carregarMes(); }, [carregarMes]);

  // Próxima batida: o backend decide o tipo real (2 ou 4 batidas/dia conforme a
  // intrajornada do posto). proximoTipo = tipo exato; proximoLabel = texto do botão.
  const proximoTipo: string = hoje?.proxima_batida || 'entrada';
  const jornadaConcluida = Boolean(hoje?.jornada_concluida) || proximoTipo === 'concluido';
  const proximoLabel: string =
    hoje?.proxima_label ||
    (proximoTipo === 'saida' ? 'Saída'
      : proximoTipo === 'saida_almoco' ? 'Saída para o almoço'
      : proximoTipo === 'retorno_almoco' ? 'Volta do almoço'
      : 'Entrada');

  // Passo 1: pedir GPS e abrir a câmera para o reconhecimento facial.
  const iniciarBatida = async () => {
    setBaterErro('');
    setResultado(null);
    if (!faceEnrolled) {
      setBaterErro('Cadastre seu reconhecimento facial antes de bater o ponto.');
      return;
    }
    setFase('gps');
    try {
      const pos = await obterLocalizacao();
      setGeo({ latitude: pos.latitude, longitude: pos.longitude });
      setFase('facial');
    } catch (e: unknown) {
      setBaterErro((e as Error)?.message || 'Não foi possível obter sua localização.');
      setFase('idle');
    }
  };

  // Backend retorna registros de BATIDA individuais: {tipo, data_hora, localizacao}
  const registros = (data?.registros || []) as Record<string, unknown>[];

  const fmt = (dh: string): { dia: string; hora: string } => {
    // data_hora vem como "2026-07-10 06:00:00"
    const [d, h] = String(dh).split(' ');
    const [y, m, day] = (d || '').split('-');
    return { dia: y ? `${day}/${m}/${y}` : d || '', hora: (h || '').slice(0, 5) };
  };

  const batidasHoje = hoje?.batidas || [];
  const bloqueado = fase === 'gps' || fase === 'sending';
  const postoHoje = hoje?.posto_nome || hoje?.posto || null;

  return (
    <div className="space-y-4">
      {/* ---- BATER PONTO (celular-first) ---- */}
      <div className="rounded-2xl border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Fingerprint className="w-5 h-5 text-[#F97316]" />
            <span className="font-display text-sm font-semibold">Bater ponto</span>
          </div>
          {postoHoje && (
            <span className="text-[11px] text-[hsl(var(--muted-foreground))] flex items-center gap-1 truncate max-w-[55%]">
              <MapPin className="w-3 h-3 flex-shrink-0" /> {postoHoje}
            </span>
          )}
        </div>

        {/* Resultado da última batida */}
        {resultado?.ok && (
          <div className="mb-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3">
            <p className="text-sm font-medium text-emerald-700 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4" />
              {(resultado.tipo === 'saida' ? 'Saída' : 'Entrada')} registrada
              {resultado.hora ? ` às ${String(resultado.hora).slice(0, 5)}` : ''}
            </p>
            <div className="mt-1 text-xs text-[hsl(var(--muted-foreground))] space-y-0.5">
              {(resultado.posto_nome || resultado.posto) && (
                <p className="flex items-center gap-1">
                  <MapPin className="w-3 h-3" /> {resultado.posto_nome || resultado.posto}
                </p>
              )}
              {resultado.posto_sem_localizacao ? (
                <p className="text-amber-600 flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" /> Localização do posto não configurada — registrado mesmo assim.
                </p>
              ) : resultado.dentro_geofence === true ? (
                <p className="text-emerald-700 flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> Dentro do posto
                </p>
              ) : resultado.dentro_geofence === false ? (
                <p className="text-amber-600 flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" /> Fora do raio do posto — registrado para conferência.
                </p>
              ) : null}
            </div>
          </div>
        )}

        {baterErro && <div className="mb-3"><ErrorBox msg={baterErro} /></div>}

        {/* Cadastro obrigatório do rosto antes de liberar a batida */}
        {faceEnrolled === false ? (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
            <p className="text-sm font-medium text-amber-700 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" /> Cadastre seu reconhecimento facial
            </p>
            <p className="mt-1 text-xs text-[hsl(var(--muted-foreground))]">
              Para bater o ponto pelo app, primeiro registre seu rosto. É rápido e só precisa ser feito uma vez.
            </p>
            <button
              onClick={() => { setBaterErro(''); setResultado(null); setFase('enroll'); }}
              disabled={bloqueado}
              className="mt-3 w-full rounded-xl py-3 text-sm font-semibold text-white bg-[#F97316] hover:bg-[#EA6A0A] active:bg-[#C2570A] disabled:bg-orange-500 flex items-center justify-center gap-2"
            >
              <Camera className="w-4 h-4" /> Cadastrar meu rosto
            </button>
          </div>
        ) : jornadaConcluida ? (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-center">
            <p className="text-sm font-medium text-emerald-700 flex items-center justify-center gap-2">
              <CheckCircle2 className="w-4 h-4" /> Jornada de hoje concluída
            </p>
            <p className="mt-1 text-xs text-[hsl(var(--muted-foreground))]">
              Você já registrou todas as batidas do dia ({hoje?.num_batidas_dia ?? 0}).
            </p>
          </div>
        ) : (
          <>
            <button
              onClick={iniciarBatida}
              disabled={bloqueado || hojeLoading || faceEnrolled === null}
              className={[
                'w-full rounded-xl py-4 text-base font-semibold text-white transition-colors',
                'flex items-center justify-center gap-2 shadow-sm',
                bloqueado || hojeLoading || faceEnrolled === null
                  ? 'bg-orange-500 cursor-not-allowed'
                  : 'bg-[#F97316] hover:bg-[#EA6A0A] active:bg-[#C2570A]',
              ].join(' ')}
            >
              {fase === 'gps' ? (
                <><Loader2 className="w-5 h-5 animate-spin" /> Obtendo localização…</>
              ) : fase === 'sending' ? (
                <><Loader2 className="w-5 h-5 animate-spin" /> Registrando…</>
              ) : fase === 'facial' ? (
                <><Loader2 className="w-5 h-5 animate-spin" /> Reconhecendo rosto…</>
              ) : (
                <>
                  <Fingerprint className="w-5 h-5" />
                  BATER {proximoLabel.toUpperCase()}
                </>
              )}
            </button>
            <p className="text-[11px] text-[hsl(var(--muted-foreground))]/80 text-center mt-2">
              Ao bater, pediremos sua localização e o reconhecimento facial (anti-fraude).
            </p>
            {faceEnrolled && fase !== 'sending' && (
              <button onClick={baterContingencia}
                className="w-full text-center text-[12px] text-[hsl(var(--muted-foreground))] underline mt-2 hover:text-[hsl(var(--foreground))]">
                Não consegui bater pelo rosto — registrar para o DP validar
              </button>
            )}
          </>
        )}
      </div>

      {/* ---- Reconhecimento facial (cadastro do rosto ou match na batida) ---- */}
      {(fase === 'facial' || fase === 'enroll') && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
          <div className="w-full max-w-md rounded-2xl bg-[hsl(var(--card))] border border-[hsl(var(--border))] p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="font-display text-sm font-semibold">
                {fase === 'enroll' ? 'Cadastrar meu rosto' : 'Reconhecimento facial'}
              </span>
              <button
                onClick={() => {
                  setFase('idle');
                  setGeo(null);
                  if (fase === 'facial') setBaterErro('Batida cancelada. O reconhecimento facial é obrigatório.');
                }}
                className="text-xs text-[hsl(var(--muted-foreground))] hover:underline"
              >
                Cancelar
              </button>
            </div>
            <FacialCapture
              employeeDescriptor={fase === 'facial' ? (faceRef ?? undefined) : undefined}
              onCapture={fase === 'enroll' ? onEnrollCapture : onFacialCapture}
              onError={(m) => { setBaterErro(m); setFase('idle'); setGeo(null); }}
              threshold={0.68}
              maxAttempts={14}
            />
          </div>
        </div>
      )}

      {/* ---- Hoje: batidas + horas ---- */}
      {!hojeLoading && (batidasHoje.length > 0 || hoje?.horas_trabalhadas != null) && (
        <div className="rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-3">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70">
              Hoje
            </p>
            {hoje?.horas_trabalhadas != null && (
              <span className="text-xs text-[hsl(var(--muted-foreground))] font-mono">
                {String(hoje.horas_trabalhadas)}h
              </span>
            )}
          </div>
          {batidasHoje.length === 0 ? (
            <p className="text-xs text-[hsl(var(--muted-foreground))]">Nenhuma batida hoje ainda.</p>
          ) : (
            <div className="space-y-1.5">
              {batidasHoje.map((b, i) => {
                const tipo = String(b.tipo || '');
                const isEntrada = tipo.toLowerCase().includes('entra');
                return (
                  <div key={i} className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2">
                      <span className={['inline-block w-2 h-2 rounded-full', isEntrada ? 'bg-emerald-500' : 'bg-orange-500'].join(' ')} />
                      <span className="capitalize">{tipo || 'registro'}</span>
                      {b.dentro_geofence === false && (
                        <span className="text-[11px] text-amber-600">fora do posto</span>
                      )}
                    </span>
                    <span className="font-mono text-[hsl(var(--muted-foreground))]">
                      {String(b.hora || b.data_hora || '').slice(-8).slice(0, 5)}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ---- Histórico mensal ---- */}
      <div className="flex items-center gap-2 pt-1">
        <span className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70 mr-1">
          Histórico
        </span>
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

      {/* Baixar o espelho de ponto (mês) — PDF legal, disponível quando o mês foi calculado. */}
      <div className="rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <FileText className="w-4 h-4 text-[#F97316] flex-shrink-0" />
          <p className="text-xs text-[hsl(var(--muted-foreground))] truncate">
            Espelho de ponto de {String(mes).padStart(2, '0')}/{ano} (PDF legal — Portaria 671).
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            const token = localStorage.getItem('access_token');
            const base = process.env.NEXT_PUBLIC_API_URL || 'https://erp.conectamais.pro';
            fetch(`${base}/api/v1/people-management/portal/self-service/meu-espelho/${mes}/${ano}/pdf`, {
              headers: { Authorization: `Bearer ${token}` },
            })
              .then((r) => {
                if (!r.ok) throw new Error('Espelho ainda não disponível para este mês.');
                return r.blob();
              })
              .then((b) => window.open(URL.createObjectURL(b), '_blank'))
              .catch((e) => setError(e?.message || 'Não foi possível baixar o espelho.'));
          }}
        >
          <Download className="w-4 h-4 mr-1.5" /> Espelho PDF
        </Button>
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

      {/* ---- LÍDER/SUPERVISOR: definir localização do posto (geofence) ---- */}
      {isLider && (
        <DefinirLocalizacaoPosto
          postoId={(hoje as Record<string, unknown> | null)?.posto_id as string | undefined}
          postoNome={postoHoje}
          onDone={carregarHoje}
        />
      )}
    </div>
  );
}

/**
 * Só para líder/supervisor/gerente: captura o GPS ATUAL e grava como a
 * localização (geofence) do posto — POST /operacional/posts/{id}/definir-localizacao.
 * Aparece apenas quando há um posto_id resolvido no ponto-hoje.
 */
function DefinirLocalizacaoPosto({
  postoId, postoNome, onDone,
}: {
  postoId?: string;
  postoNome?: string | null;
  onDone: () => void;
}) {
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState('');
  const [erro, setErro] = useState('');

  if (!postoId) return null;

  const definir = async () => {
    setSalvando(true); setMsg(''); setErro('');
    try {
      const pos = await obterLocalizacao();
      await api.post(`/api/v1/operacional/posts/${postoId}/definir-localizacao`, {
        latitude: pos.latitude,
        longitude: pos.longitude,
      });
      setMsg('Localização do posto definida com a sua posição atual.');
      onDone();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErro(detail || (e as Error)?.message || 'Não foi possível definir a localização do posto.');
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="rounded-xl border border-dashed border-[hsl(var(--border))] p-3 mt-1">
      <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70 mb-1">
        Supervisão
      </p>
      <p className="text-xs text-[hsl(var(--muted-foreground))] mb-2">
        Defina o raio (geofence) {postoNome ? `do posto ${postoNome}` : 'deste posto'} usando sua
        posição atual. Faça isso dentro do posto.
      </p>
      {msg && <div className="mb-2 text-xs text-emerald-700 flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" /> {msg}</div>}
      {erro && <div className="mb-2"><ErrorBox msg={erro} /></div>}
      <Button variant="outline" size="sm" disabled={salvando} onClick={definir}>
        {salvando ? <Loader2 className="w-4 h-4 animate-spin" /> : <><MapPin className="w-4 h-4 mr-1.5" /> Definir localização deste posto</>}
      </Button>
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
function BeneficiosTab() {
  const [ativos, setAtivos] = useState<BeneficioAtivo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/api/v1/people-management/portal/self-service/meus-beneficios');
        const d = res.data || {};
        setAtivos(Array.isArray(d.beneficios_ativos) ? d.beneficios_ativos : []);
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
  if (ativos.length === 0)
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
                  <span className="text-[11px] px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-700 font-medium">
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

// Ouvidoria — canal sigiloso (anônimo ou identificado)
function OuvidoriaTab() {
  const [categoria, setCategoria] = useState('');
  const [mensagem, setMensagem] = useState('');
  const [anonimo, setAnonimo] = useState(true);
  const [enviando, setEnviando] = useState(false);
  const [protocolo, setProtocolo] = useState('');
  const [erro, setErro] = useState('');
  const [minhas, setMinhas] = useState<Array<{ protocolo: string; categoria: string | null; mensagem: string; status: string; resposta: string | null }>>([]);

  const carregarMinhas = async () => {
    try { const r = await api.get(`${SS_BASE}/ouvidoria/minhas`); setMinhas(r.data?.manifestacoes || []); } catch { /* noop */ }
  };
  useEffect(() => { carregarMinhas(); }, []);

  const enviar = async () => {
    if (mensagem.trim().length < 5) { setErro('Descreva sua manifestação (mínimo 5 caracteres).'); return; }
    setEnviando(true); setErro(''); setProtocolo('');
    try {
      const r = await api.post(`${SS_BASE}/ouvidoria`, { categoria: categoria || null, mensagem: mensagem.trim(), anonimo });
      setProtocolo(r.data?.protocolo || '');
      setMensagem('');
      if (!anonimo) carregarMinhas();
    } catch { setErro('Não foi possível enviar sua manifestação. Tente de novo.'); }
    finally { setEnviando(false); }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-[#16277D]/5 border border-[#16277D]/20 p-4 flex items-start gap-3">
        <Lock className="w-5 h-5 text-[#16277D] mt-0.5 shrink-0" />
        <p className="text-[13px] text-[hsl(var(--muted-foreground))]">
          Canal <b>sigiloso</b> pra você relatar problemas, denúncias ou sugestões. Você escolhe se quer
          se <b>identificar</b> ou enviar de forma <b>anônima</b> — no anônimo, ninguém fica sabendo que foi você.
        </p>
      </div>

      {erro && <ErrorBox msg={erro} />}
      {protocolo && (
        <div className="rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-[14px] px-4 py-3">
          ✓ Manifestação registrada com sigilo. Seu protocolo: <b>{protocolo}</b> — guarde para acompanhar.
        </div>
      )}

      <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 space-y-3">
        <div>
          <label className="text-[12px] text-[hsl(var(--muted-foreground))]">Assunto</label>
          <select value={categoria} onChange={(e) => setCategoria(e.target.value)}
            className="w-full rounded-xl border-2 border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 py-2.5 text-[15px] outline-none">
            <option value="">Selecione…</option>
            <option value="assedio_moral">Assédio moral</option>
            <option value="assedio_sexual">Assédio sexual</option>
            <option value="sobrecarga">Sobrecarga / jornada excessiva</option>
            <option value="violencia">Violência / agressão no trabalho</option>
            <option value="discriminacao">Discriminação</option>
            <option value="relacao_lideranca">Conflitos / relação com a liderança</option>
            <option value="saude_mental">Saúde mental / estresse</option>
            <option value="sugestao">Sugestão</option>
            <option value="outros">Outros</option>
          </select>
        </div>
        <div>
          <label className="text-[12px] text-[hsl(var(--muted-foreground))]">Sua manifestação</label>
          <textarea value={mensagem} onChange={(e) => setMensagem(e.target.value)} rows={5} placeholder="Descreva o que aconteceu…"
            className="w-full rounded-xl border-2 border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 py-2.5 text-[15px] outline-none resize-y" />
        </div>
        <button type="button" onClick={() => setAnonimo((v) => !v)}
          className="flex items-center gap-2 text-[14px] font-medium text-[hsl(var(--foreground))]">
          <span className={`w-10 h-6 rounded-full transition-colors relative ${anonimo ? 'bg-[#16277D]' : 'bg-slate-300'}`}>
            <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full transition-all ${anonimo ? 'left-[18px]' : 'left-0.5'}`} />
          </span>
          {anonimo ? <><EyeOff className="w-4 h-4" /> Enviar anonimamente</> : <>Enviar identificado (poderei receber resposta)</>}
        </button>
        <button onClick={enviar} disabled={enviando}
          className="rounded-xl bg-[#F97316] text-white text-[15px] font-bold px-5 py-2.5 flex items-center gap-2 disabled:opacity-50">
          {enviando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Enviar manifestação
        </button>
      </div>

      {minhas.length > 0 && (
        <div>
          <p className="text-[13px] font-semibold text-[hsl(var(--muted-foreground))] mb-2 mt-4">Minhas manifestações identificadas</p>
          <div className="space-y-2">
            {minhas.map((m) => (
              <div key={m.protocolo} className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-3.5">
                <div className="flex items-center justify-between">
                  <span className="text-[12px] font-mono text-[hsl(var(--muted-foreground))]">{m.protocolo}</span>
                  <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">{m.status}</span>
                </div>
                <p className="text-[14px] text-[hsl(var(--foreground))] mt-1">{m.mensagem}</p>
                {m.resposta && <p className="text-[13px] text-emerald-700 mt-2 border-t border-[hsl(var(--border))] pt-2"><b>Resposta:</b> {m.resposta}</p>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function DocumentosTab({ onIrAssinar }: { onIrAssinar: () => void }) {
  const [docs, setDocs] = useState<MeuDocumento[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [baixandoId, setBaixandoId] = useState<string | null>(null);
  const [upTipo, setUpTipo] = useState('atestado_medico');
  const [upFile, setUpFile] = useState<File | null>(null);
  const [upIni, setUpIni] = useState('');
  const [upFim, setUpFim] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [okMsg, setOkMsg] = useState('');

  const recarregar = async () => {
    try {
      const res = await api.get('/api/v1/people-management/portal/self-service/meus-documentos');
      setDocs(Array.isArray(res.data?.documentos) ? res.data.documentos : []);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg || 'Não foi possível carregar seus documentos.');
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { recarregar(); }, []);

  const enviarDoc = async () => {
    if (!upFile) { setError('Escolha um arquivo (foto ou PDF).'); return; }
    setEnviando(true); setError(''); setOkMsg('');
    try {
      const token = localStorage.getItem('access_token');
      const base = process.env.NEXT_PUBLIC_API_URL || 'https://erp.conectamais.pro';
      const fd = new FormData();
      fd.append('tipo', upTipo);
      fd.append('arquivo', upFile);
      if (upTipo === 'atestado_medico') { if (upIni) fd.append('data_inicio', upIni); if (upFim) fd.append('data_fim', upFim); }
      const r = await fetch(`${base}/api/v1/people-management/portal/self-service/documentos/upload`, {
        method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: fd,
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(msgFromDetail(j.detail) || 'Não foi possível enviar o documento.');
      setOkMsg(j.mensagem || 'Documento enviado e anexado à sua ficha.');
      setUpFile(null); setUpIni(''); setUpFim('');
      recarregar();
    } catch (e: unknown) {
      setError((e as Error)?.message || 'Falha ao enviar o documento.');
    } finally {
      setEnviando(false);
    }
  };

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
        throw new Error(msgFromDetail(j.detail) || 'Documento indisponível para download.');
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
      {okMsg && (
        <div className="rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-[14px] px-4 py-3">{okMsg}</div>
      )}

      {/* Enviar documento → cai na ficha; atestado abona o ponto (via DP) */}
      <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3">
          <Upload className="w-5 h-5 text-[#F97316]" />
          <p className="text-[15px] font-semibold text-[hsl(var(--foreground))]">Enviar um documento</p>
        </div>
        <div className="grid sm:grid-cols-2 gap-3">
          <div>
            <label className="text-[12px] text-[hsl(var(--muted-foreground))]">Tipo</label>
            <select value={upTipo} onChange={(e) => setUpTipo(e.target.value)}
              className="w-full rounded-xl border-2 border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 py-2.5 text-[15px] outline-none">
              <option value="atestado_medico">Atestado médico</option>
              <option value="comprovante">Comprovante</option>
              <option value="rg">RG / Documento</option>
              <option value="declaracao">Declaração</option>
              <option value="outros">Outros</option>
            </select>
          </div>
          <div>
            <label className="text-[12px] text-[hsl(var(--muted-foreground))]">Arquivo (foto ou PDF)</label>
            <input type="file" accept="image/*,application/pdf" onChange={(e) => setUpFile(e.target.files?.[0] || null)}
              className="w-full rounded-xl border-2 border-[hsl(var(--border))] px-3 py-2 text-[13px] outline-none file:mr-2 file:rounded-lg file:border-0 file:bg-[#F97316]/10 file:text-[#F97316] file:px-3 file:py-1.5 file:text-[13px] file:font-semibold" />
          </div>
          {upTipo === 'atestado_medico' && (
            <>
              <div>
                <label className="text-[12px] text-[hsl(var(--muted-foreground))]">Afastamento — início</label>
                <input type="date" value={upIni} onChange={(e) => setUpIni(e.target.value)}
                  className="w-full rounded-xl border-2 border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 py-2.5 text-[15px] outline-none" />
              </div>
              <div>
                <label className="text-[12px] text-[hsl(var(--muted-foreground))]">Afastamento — fim</label>
                <input type="date" value={upFim} onChange={(e) => setUpFim(e.target.value)}
                  className="w-full rounded-xl border-2 border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 py-2.5 text-[15px] outline-none" />
              </div>
            </>
          )}
        </div>
        {upTipo === 'atestado_medico' && (
          <p className="text-[12px] text-[hsl(var(--muted-foreground))] mt-2">O atestado vai pra sua ficha e é enviado ao DP para abonar seu ponto.</p>
        )}
        <button onClick={enviarDoc} disabled={enviando || !upFile}
          className="mt-3 rounded-xl bg-[#F97316] text-white text-[15px] font-bold px-5 py-2.5 flex items-center gap-2 disabled:opacity-50">
          {enviando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Enviar
        </button>
      </div>

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
                  <FileText className="w-4 h-4 text-[#F97316] flex-shrink-0" />
                  <p className="font-medium text-sm truncate">
                    {d.document_name || String(d.document_type || 'Documento').replace(/_/g, ' ')}
                  </p>
                </div>
                <div className="text-xs text-[hsl(var(--muted-foreground))] flex flex-wrap items-center gap-2">
                  <span className="capitalize">{String(d.document_type || '').replace(/_/g, ' ')}</span>
                  {d.signed ? (
                    <span className="inline-flex items-center gap-1 text-emerald-700">
                      <CheckCircle2 className="w-3 h-3" /> Assinado
                    </span>
                  ) : (
                    <button
                      onClick={onIrAssinar}
                      className="inline-flex items-center gap-1 text-[#F97316] hover:underline"
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
                    <Award className="w-4 h-4 text-[#F97316] flex-shrink-0" />
                    <span className="text-sm font-medium truncate">{c.course_name || 'Certificado'}</span>
                  </div>
                  <p className="mt-0.5 text-xs text-[hsl(var(--muted-foreground))]">
                    {c.certificate_number ? `Nº ${c.certificate_number}` : ''}
                    {c.expires_at ? ` · válido até ${fmtData(c.expires_at)}` : ''}
                  </p>
                </div>
                {c.status && (
                  <span className="text-[11px] px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-700 font-medium capitalize whitespace-nowrap">
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
// Meus dados (leitura + edição de campos permitidos — mesma gravação em employees)
// --------------------------------------------------------------------------- //
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
        const res = await api.get(`${SS_BASE}/meus-dados`);
        setData(res.data);
        setForm({
          telefone: res.data?.telefone || '', celular: res.data?.celular || '',
          email: res.data?.email || '',
          cep: res.data?.cep || '', logradouro: res.data?.logradouro || '',
          numero: res.data?.numero || '', complemento: res.data?.complemento || '',
          bairro: res.data?.bairro || '', cidade: res.data?.cidade || '', uf: res.data?.uf || '',
          nome_mae: res.data?.nome_mae || '', naturalidade: res.data?.naturalidade || '',
          nacionalidade: res.data?.nacionalidade || '', rg: res.data?.rg || '',
          estado_civil: res.data?.estado_civil || '', pis: res.data?.pis || '',
          contato_emergencia: res.data?.contato_emergencia || '',
          telefone_emergencia: res.data?.telefone_emergencia || '',
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
      // Grava DIRETO em employees (fonte única — o DP lê o mesmo registro).
      const payload: Record<string, string | null> = {};
      const campos = [
        'telefone', 'celular', 'email', 'cep', 'logradouro', 'numero', 'complemento',
        'bairro', 'cidade', 'uf', 'nome_mae', 'naturalidade', 'nacionalidade', 'rg',
        'estado_civil', 'pis', 'contato_emergencia', 'telefone_emergencia',
      ] as const;
      for (const c of campos) {
        const v = (form as Record<string, string | undefined>)[c];
        payload[c] = v && v.trim() ? v.trim() : null;
      }
      const res = await api.put(`${SS_BASE}/meus-dados`, payload);
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
    'w-full rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 py-2 text-sm outline-none focus:border-[#F97316]';

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

      {/* Editáveis — mesmos campos do onboarding, gravam em employees (fonte única). */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70 mb-2">Contato</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-[hsl(var(--muted-foreground))]">Telefone / celular</label>
            <input className={inputCls} value={form.telefone || ''} onChange={(e) => setForm({ ...form, telefone: maskTelefone(e.target.value) })} />
          </div>
          <div>
            <label className="text-xs text-[hsl(var(--muted-foreground))]">E-mail</label>
            <input className={inputCls} value={form.email || ''} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
        </div>
      </div>

      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70 mb-2">Endereço</p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label className="text-xs text-[hsl(var(--muted-foreground))]">CEP</label>
            <input className={inputCls} value={form.cep || ''} onChange={(e) => setForm({ ...form, cep: maskCep(e.target.value) })} />
          </div>
          <div className="sm:col-span-2">
            <label className="text-xs text-[hsl(var(--muted-foreground))]">Endereço (rua/avenida)</label>
            <input className={inputCls} value={form.logradouro || ''} onChange={(e) => setForm({ ...form, logradouro: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-[hsl(var(--muted-foreground))]">Número</label>
            <input className={inputCls} value={form.numero || ''} onChange={(e) => setForm({ ...form, numero: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-[hsl(var(--muted-foreground))]">Bairro</label>
            <input className={inputCls} value={form.bairro || ''} onChange={(e) => setForm({ ...form, bairro: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-[hsl(var(--muted-foreground))]">Cidade</label>
            <input className={inputCls} value={form.cidade || ''} onChange={(e) => setForm({ ...form, cidade: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-[hsl(var(--muted-foreground))]">UF</label>
            <input className={inputCls} maxLength={2} value={form.uf || ''} onChange={(e) => setForm({ ...form, uf: e.target.value.toUpperCase().slice(0, 2) })} />
          </div>
        </div>
      </div>

      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70 mb-2">Documentos e filiação</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="sm:col-span-2">
            <label className="text-xs text-[hsl(var(--muted-foreground))]">Nome da mãe</label>
            <input className={inputCls} value={form.nome_mae || ''} onChange={(e) => setForm({ ...form, nome_mae: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-[hsl(var(--muted-foreground))]">Naturalidade</label>
            <input className={inputCls} value={form.naturalidade || ''} onChange={(e) => setForm({ ...form, naturalidade: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-[hsl(var(--muted-foreground))]">Nacionalidade</label>
            <input className={inputCls} value={form.nacionalidade || ''} onChange={(e) => setForm({ ...form, nacionalidade: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-[hsl(var(--muted-foreground))]">RG</label>
            <input className={inputCls} value={form.rg || ''} onChange={(e) => setForm({ ...form, rg: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-[hsl(var(--muted-foreground))]">Estado civil</label>
            <select className={inputCls} value={form.estado_civil || ''} onChange={(e) => setForm({ ...form, estado_civil: e.target.value })}>
              <option value="">Selecione...</option>
              {ESTADO_CIVIL_OPTS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-[hsl(var(--muted-foreground))]">PIS/PASEP</label>
            <input className={inputCls} value={form.pis || ''} onChange={(e) => setForm({ ...form, pis: maskPis(e.target.value) })} />
          </div>
        </div>
      </div>

      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70 mb-2">Contato de emergência</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-[hsl(var(--muted-foreground))]">Nome / parentesco</label>
            <input className={inputCls} value={form.contato_emergencia || ''} onChange={(e) => setForm({ ...form, contato_emergencia: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-[hsl(var(--muted-foreground))]">Telefone de emergência</label>
            <input className={inputCls} value={form.telefone_emergencia || ''} onChange={(e) => setForm({ ...form, telefone_emergencia: maskTelefone(e.target.value) })} />
          </div>
        </div>
      </div>

      {error && <ErrorBox msg={error} />}
      {ok && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-sm text-emerald-700 flex items-center gap-2">
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
        <div className="rounded-xl p-4 bg-orange-50 border border-orange-200">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-[#F97316] mb-1">
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
              : 'bg-orange-50 border-orange-200',
          ].join(' ')}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                {!n.lido && <span className="inline-block w-2 h-2 rounded-full bg-[#F97316]" />}
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
                className="text-xs text-[#F97316] font-medium whitespace-nowrap hover:underline"
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
// Reembolso — solicitar (adiantei a despesa, a empresa devolve) + meus pedidos
// POST /portal/self-service/solicitar-reembolso  → nasce 'pendente' (DP aprova)
// GET  /portal/self-service/meus-reembolsos       → só os DELE (requester_id JWT)
// --------------------------------------------------------------------------- //
const REEMB_BASE = '/api/v1/people-management/portal/self-service';

interface CategoriaReembolso { value: string; label: string; }
interface MeuReembolso {
  id: string;
  code: string;
  status: string;
  valor: number;
  valor_aprovado?: number;
  valor_pago?: number;
  categoria?: string | null;
  categoria_label?: string | null;
  data_despesa?: string | null;
  motivo?: string | null;
  criado_em?: string | null;
  rejeicao_motivo?: string | null;
  anexos?: number;
}

/** Formata número em Real (exibição). */
function brl(v: number): string {
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

/** Cor/rótulo do status do reembolso. */
function reembStatus(s: string): { label: string; cls: string } {
  const map: Record<string, { label: string; cls: string }> = {
    rascunho: { label: 'Rascunho', cls: 'bg-[hsl(var(--secondary))] text-[hsl(var(--muted-foreground))]' },
    pendente: { label: 'Pendente', cls: 'bg-amber-500/15 text-amber-600' },
    em_analise: { label: 'Em análise', cls: 'bg-amber-500/15 text-amber-600' },
    aprovado: { label: 'Aprovado', cls: 'bg-blue-500/15 text-blue-600' },
    processado: { label: 'Pago', cls: 'bg-emerald-100 text-emerald-700' },
    pago: { label: 'Pago', cls: 'bg-emerald-100 text-emerald-700' },
    rejeitado: { label: 'Rejeitado', cls: 'bg-red-500/15 text-red-700' },
    cancelado: { label: 'Cancelado', cls: 'bg-[hsl(var(--secondary))] text-[hsl(var(--muted-foreground))]' },
  };
  return map[s] || { label: s || '—', cls: 'bg-[hsl(var(--secondary))] text-[hsl(var(--muted-foreground))]' };
}

function ReembolsoTab() {
  const [categorias, setCategorias] = useState<CategoriaReembolso[]>([]);
  const [reembolsos, setReembolsos] = useState<MeuReembolso[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Formulário
  const [categoria, setCategoria] = useState('transporte');
  const [valor, setValor] = useState('');            // string com máscara R$
  const [dataDespesa, setDataDespesa] = useState('');
  const [descricao, setDescricao] = useState('');
  const [comprovante, setComprovante] = useState<string | null>(null); // data-URI
  const [comprovanteNome, setComprovanteNome] = useState<string>('');
  const [enviando, setEnviando] = useState(false);
  const [okMsg, setOkMsg] = useState('');
  const [formErr, setFormErr] = useState('');

  const carregar = useCallback(async () => {
    try {
      const [c, r] = await Promise.all([
        api.get(`${REEMB_BASE}/categorias-reembolso`),
        api.get(`${REEMB_BASE}/meus-reembolsos`),
      ]);
      setCategorias(Array.isArray(c.data?.categorias) ? c.data.categorias : []);
      setReembolsos(Array.isArray(r.data?.reembolsos) ? r.data.reembolsos : []);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg || 'Não foi possível carregar seus reembolsos.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  // Valor: mantém só dígitos e exibe em reais (centavos).
  const onValor = (raw: string) => {
    const dig = raw.replace(/\D/g, '');
    if (!dig) { setValor(''); return; }
    const cents = parseInt(dig, 10);
    setValor((cents / 100).toFixed(2));
  };
  const valorFmt = valor ? brl(parseFloat(valor)) : '';

  const onArquivo = (file: File | null) => {
    if (!file) { setComprovante(null); setComprovanteNome(''); return; }
    if (file.size > 10 * 1024 * 1024) {
      setFormErr('O comprovante deve ter no máximo 10MB.');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => { setComprovante(reader.result as string); setComprovanteNome(file.name); };
    reader.onerror = () => setFormErr('Não foi possível ler o arquivo do comprovante.');
    reader.readAsDataURL(file);
  };

  const enviar = async () => {
    setFormErr(''); setOkMsg('');
    const v = parseFloat(valor || '0');
    if (!v || v <= 0) { setFormErr('Informe o valor gasto (maior que zero).'); return; }
    if (!dataDespesa) { setFormErr('Informe a data da despesa.'); return; }
    if (!descricao || descricao.trim().length < 3) { setFormErr('Descreva o motivo da despesa.'); return; }
    setEnviando(true);
    try {
      const res = await api.post(`${REEMB_BASE}/solicitar-reembolso`, {
        categoria,
        valor: v,
        data_despesa: dataDespesa,
        descricao: descricao.trim(),
        comprovante_base64: comprovante,
        comprovante_nome: comprovanteNome || undefined,
      });
      setOkMsg(res.data?.mensagem || 'Reembolso enviado. Aguardando aprovação do DP/financeiro.');
      // limpa o formulário e recarrega a lista
      setValor(''); setDataDespesa(''); setDescricao('');
      setComprovante(null); setComprovanteNome('');
      await carregar();
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setFormErr(typeof msg === 'string' ? msg : 'Não foi possível enviar o reembolso. Tente novamente.');
    } finally {
      setEnviando(false);
    }
  };

  if (loading) return <Spinner />;
  if (error) return <ErrorBox msg={error} />;

  return (
    <div className="space-y-6">
      {/* Formulário de solicitação */}
      <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-2xl p-4">
        <div className="flex items-center gap-2 mb-1">
          <Wallet className="w-4 h-4 text-[#F97316]" />
          <h2 className="font-display text-sm font-semibold">Solicitar reembolso</h2>
        </div>
        <p className="text-xs text-[hsl(var(--muted-foreground))] mb-4">
          Adiantou uma despesa a trabalho? Peça o reembolso. O DP/financeiro analisa e devolve o valor.
        </p>

        <div className="space-y-3">
          {/* Categoria */}
          <div>
            <label className="text-xs font-medium text-[hsl(var(--muted-foreground))]">Categoria</label>
            <select
              value={categoria}
              onChange={(e) => setCategoria(e.target.value)}
              className="mt-1 w-full h-11 rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 text-sm"
            >
              {categorias.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </div>

          {/* Valor + Data */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-[hsl(var(--muted-foreground))]">Valor gasto</label>
              <input
                inputMode="numeric"
                placeholder="R$ 0,00"
                value={valorFmt}
                onChange={(e) => onValor(e.target.value)}
                className="mt-1 w-full h-11 rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 text-sm font-mono"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-[hsl(var(--muted-foreground))]">Data da despesa</label>
              <input
                type="date"
                value={dataDespesa}
                max={new Date().toISOString().slice(0, 10)}
                onChange={(e) => setDataDespesa(e.target.value)}
                className="mt-1 w-full h-11 rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 text-sm"
              />
            </div>
          </div>

          {/* Descrição */}
          <div>
            <label className="text-xs font-medium text-[hsl(var(--muted-foreground))]">Motivo / descrição</label>
            <textarea
              rows={2}
              placeholder="Ex.: Táxi do posto até a base para entrega de equipamento."
              value={descricao}
              onChange={(e) => setDescricao(e.target.value)}
              className="mt-1 w-full rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 py-2 text-sm resize-none"
            />
          </div>

          {/* Comprovante (foto/PDF via câmera ou upload) */}
          <div>
            <label className="text-xs font-medium text-[hsl(var(--muted-foreground))]">Comprovante (foto ou PDF)</label>
            <label className="mt-1 flex items-center gap-2 h-11 rounded-xl border border-dashed border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 text-sm cursor-pointer hover:border-[#F97316] transition-colors">
              {comprovante ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                  <span className="truncate text-[hsl(var(--foreground))]">{comprovanteNome || 'Comprovante anexado'}</span>
                  <button
                    type="button"
                    onClick={(e) => { e.preventDefault(); onArquivo(null); }}
                    className="ml-auto text-[hsl(var(--muted-foreground))] hover:text-red-500"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </>
              ) : (
                <>
                  <Paperclip className="w-4 h-4 text-[hsl(var(--muted-foreground))] flex-shrink-0" />
                  <span className="text-[hsl(var(--muted-foreground))]">Toque para tirar foto ou anexar o recibo</span>
                  <Camera className="w-4 h-4 text-[#F97316] ml-auto flex-shrink-0" />
                </>
              )}
              <input
                type="file"
                accept="image/*,application/pdf"
                capture="environment"
                className="hidden"
                onChange={(e) => onArquivo(e.target.files?.[0] || null)}
              />
            </label>
          </div>

          {formErr && <ErrorBox msg={formErr} />}
          {okMsg && (
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-sm text-emerald-700 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> {okMsg}
            </div>
          )}

          <Button onClick={enviar} disabled={enviando} className="w-full h-11">
            {enviando ? (
              <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Enviando…</>
            ) : (
              <><Send className="w-4 h-4 mr-2" /> Enviar solicitação</>
            )}
          </Button>
        </div>
      </div>

      {/* Meus reembolsos */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70 mb-2">
          Meus reembolsos
        </p>
        {reembolsos.length === 0 ? (
          <EmptyState icon={Receipt} title="Nenhum reembolso" desc="Você ainda não solicitou reembolso." />
        ) : (
          <div className="space-y-2">
            {reembolsos.map((r) => {
              const st = reembStatus(r.status);
              return (
                <div key={r.id} className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-[hsl(var(--foreground))] truncate">
                        {r.categoria_label || r.categoria || 'Despesa'}
                      </p>
                      <p className="text-xs text-[hsl(var(--muted-foreground))] truncate">{r.motivo}</p>
                      <p className="text-[11px] text-[hsl(var(--muted-foreground))] mt-0.5">
                        {r.data_despesa || '—'} · {r.code}
                      </p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="text-sm font-bold font-mono text-[hsl(var(--foreground))]">{brl(r.valor || 0)}</p>
                      <span className={['inline-block mt-1 text-[11px] px-2 py-0.5 rounded-md font-medium', st.cls].join(' ')}>
                        {st.label}
                      </span>
                    </div>
                  </div>
                  {r.status === 'rejeitado' && r.rejeicao_motivo && (
                    <p className="mt-2 text-xs text-red-500 flex items-start gap-1.5">
                      <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" /> {r.rejeicao_motivo}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
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
    <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-500 flex items-center gap-2">
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
      <p className={['text-2xl font-bold font-mono', highlight ? 'text-[#F97316]' : 'text-[hsl(var(--foreground))]'].join(' ')}>
        {value}
      </p>
      <p className="text-[11px] text-[hsl(var(--muted-foreground))] mt-0.5">{label}</p>
    </div>
  );
}
