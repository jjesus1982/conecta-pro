'use client';

/**
 * Acompanhamento da candidatura (Funil de candidato — Fase 2).
 * O candidato informa o CPF e vê o status (Em análise / Aprovado / Não aprovado).
 * SEM login e SEM acesso ao portal — o acesso só é liberado após a aprovação.
 */
import { Suspense, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { Loader2, Search, CheckCircle2, Clock, XCircle } from 'lucide-react';

const MARCA = { azul: '#1E3A5F', azulMedio: '#2D5F8B', laranja: '#F97316', fundo: '#F1F5F9' };
const BASE = '/api/v1/people-management/portal/candidato';

interface Status {
  protocolo: string; nome: string; cargo_pleiteado: string;
  status: string; status_label: string; aprovado: boolean; reprovado: boolean;
}

function Moldura({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen w-full" style={{ background: MARCA.fundo }}>
      <div className="max-w-md mx-auto px-4 pb-10">
        <header className="pt-7 pb-5 flex flex-col items-center">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/images/logo-marca-v2.png" alt="Conecta Mais" className="h-14 w-auto" />
          <div className="mt-4 h-1.5 w-24 rounded-full" style={{ background: MARCA.laranja }} />
        </header>
        <div className="rounded-3xl bg-white shadow-sm border border-slate-200 p-5 sm:p-6">{children}</div>
      </div>
    </div>
  );
}

function Consulta() {
  const params = useSearchParams();
  const token = params.get('token') || '';
  const [cpf, setCpf] = useState('');
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState('');
  const [res, setRes] = useState<Status | null>(null);

  const consultar = async () => {
    setErro(''); setRes(null);
    const digs = cpf.replace(/\D/g, '');
    if (digs.length !== 11) { setErro('Digite seu CPF completo (11 números).'); return; }
    setLoading(true);
    try {
      const r = await api.get(`${BASE}/status`, { params: { token, cpf: digs } });
      setRes(r.data as Status);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string }; status?: number } })?.response;
      setErro(msg?.status === 404 ? 'Nenhuma candidatura encontrada para este CPF.'
        : (typeof msg?.data?.detail === 'string' ? msg.data.detail : 'Não foi possível consultar. Tente de novo.'));
    } finally { setLoading(false); }
  };

  const cor = res?.aprovado ? '#059669' : res?.reprovado ? '#DC2626' : MARCA.azulMedio;
  const Icone = res?.aprovado ? CheckCircle2 : res?.reprovado ? XCircle : Clock;

  return (
    <Moldura>
      <h1 className="text-2xl font-extrabold mb-1" style={{ color: MARCA.azul }}>Minha candidatura</h1>
      <p className="text-[15px] leading-relaxed text-slate-500 mb-5">
        Digite seu <b className="text-slate-700">CPF</b> para ver o andamento da sua candidatura.
      </p>

      {erro && <div className="mb-4 rounded-xl bg-red-50 border-2 border-red-200 text-red-700 text-[15px] font-medium p-3.5">{erro}</div>}

      <label className="block text-[15px] font-semibold text-slate-700 mb-1.5">CPF</label>
      <div className="flex gap-2">
        <input
          value={cpf}
          onChange={(e) => setCpf(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') consultar(); }}
          inputMode="numeric"
          placeholder="000.000.000-00"
          className="flex-1 rounded-xl border-2 border-slate-200 bg-white px-3.5 py-3 text-base text-slate-900 placeholder:text-slate-400 focus:border-[#F97316] focus:outline-none"
        />
        <button
          onClick={consultar}
          disabled={loading}
          className="rounded-xl px-5 text-white font-bold disabled:opacity-60 flex items-center gap-2"
          style={{ background: MARCA.laranja }}
        >
          {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Search className="w-5 h-5" />}
        </button>
      </div>

      {res && (
        <div className="mt-6 rounded-2xl border-2 p-5 text-center" style={{ borderColor: cor + '33', background: cor + '0d' }}>
          <Icone className="w-16 h-16 mx-auto mb-3" style={{ color: cor }} />
          <p className="text-xl font-extrabold" style={{ color: cor }}>{res.status_label}</p>
          <div className="mt-3 text-left text-[15px] leading-relaxed text-slate-700 space-y-1">
            <p><b style={{ color: MARCA.azul }}>Candidato:</b> {res.nome}</p>
            <p><b style={{ color: MARCA.azul }}>Vaga:</b> {res.cargo_pleiteado}</p>
            <p><b style={{ color: MARCA.azul }}>Protocolo:</b> {res.protocolo}</p>
          </div>
          {res.aprovado && (
            <p className="mt-4 text-[14px] text-emerald-700 font-medium">
              Parabéns! O RH vai entrar em contato e liberar seu acesso ao sistema.
            </p>
          )}
          {!res.aprovado && !res.reprovado && (
            <p className="mt-4 text-[14px] text-slate-500">Sua candidatura está sendo analisada pelo RH.</p>
          )}
        </div>
      )}
    </Moldura>
  );
}

export default function StatusCandidatoPage() {
  return (
    <main className="min-h-screen" style={{ background: MARCA.fundo }}>
      <Suspense fallback={<div className="p-10 text-center text-slate-400 text-base">Carregando…</div>}>
        <Consulta />
      </Suspense>
    </main>
  );
}
