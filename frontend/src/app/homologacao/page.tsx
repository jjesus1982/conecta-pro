'use client';

/**
 * Autocadastro de HOMOLOGAÇÃO (base de teste, posto "Conecta Base"), em UMA jornada:
 *   1) dados (rigor eSocial)  →  2) cadastro do ROSTO na mesma tela  →  3) pronto.
 * Sem senha (a senha é o CPF) e sem passar por login: o autocadastro já devolve um
 * token (auto-login) que é usado pra cadastrar o rosto. Isolado da folha real.
 */
import { Suspense, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { FacialCapture, type FacialCaptureResult } from '@/components/ponto/FacialCapture';
import { Loader2, CheckCircle2, ShieldCheck, Camera } from 'lucide-react';

const API = '/api/v1/people-management/portal/homologacao/autocadastro';
const FACIAL = '/api/v1/people-management/portal/self-service/facial/cadastrar';

type Campo = { key: string; label: string; type?: string; placeholder?: string; obrig?: boolean; full?: boolean };

const CAMPOS: Campo[] = [
  { key: 'nome', label: 'Nome completo', obrig: true, full: true },
  { key: 'email', label: 'E-mail (será seu login)', type: 'email', obrig: true, full: true },
  { key: 'cpf', label: 'CPF (será sua senha)', obrig: true },
  { key: 'data_nascimento', label: 'Nascimento', type: 'date', obrig: true },
  { key: 'telefone', label: 'Telefone/WhatsApp', obrig: true },
  { key: 'rg', label: 'RG', obrig: true },
  { key: 'pis', label: 'PIS/PASEP', obrig: true },
  { key: 'estado_civil', label: 'Estado civil', obrig: true, placeholder: 'solteiro / casado…' },
  { key: 'nacionalidade', label: 'Nacionalidade', obrig: true, placeholder: 'Brasileira' },
  { key: 'naturalidade', label: 'Naturalidade (cidade natal)', obrig: true },
  { key: 'nome_mae', label: 'Nome da mãe', obrig: true, full: true },
  { key: 'cep', label: 'CEP', obrig: true },
  { key: 'logradouro', label: 'Rua/Av.', obrig: true, full: true },
  { key: 'numero', label: 'Número' },
  { key: 'bairro', label: 'Bairro', obrig: true },
  { key: 'cidade', label: 'Cidade', obrig: true },
  { key: 'uf', label: 'UF', placeholder: 'AM' },
];

interface Resultado {
  matricula: string; cargo: string; escala: string; turno: string;
  horario: string; posto: string; login_email: string; access_token: string;
}

function Fluxo() {
  const params = useSearchParams();
  const token = params.get('token') || '';
  const [step, setStep] = useState<'form' | 'facial' | 'done'>('form');
  const [form, setForm] = useState<Record<string, string>>({});
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState('');
  const [res, setRes] = useState<Resultado | null>(null);

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));
  const [cepLoading, setCepLoading] = useState(false);

  // CEP → Brasil API (fallback ViaCEP): preenche endereço, sobra só número/complemento.
  const buscarCep = async (cepRaw?: string) => {
    const cep = (cepRaw || '').replace(/\D/g, '');
    if (cep.length !== 8) return;
    setCepLoading(true);
    try {
      let d: { logradouro?: string; bairro?: string; cidade?: string; uf?: string } | null = null;
      try {
        const r = await fetch(`https://brasilapi.com.br/api/cep/v1/${cep}`);
        if (r.ok) {
          const j = await r.json();
          d = { logradouro: j.street, bairro: j.neighborhood, cidade: j.city, uf: j.state };
        }
      } catch { /* tenta viacep */ }
      if (!d?.cidade) {
        try {
          const r2 = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
          if (r2.ok) {
            const j = await r2.json();
            if (!j.erro) d = { logradouro: j.logradouro, bairro: j.bairro, cidade: j.localidade, uf: j.uf };
          }
        } catch { /* silencioso */ }
      }
      if (d) {
        setForm((f) => ({
          ...f,
          logradouro: d!.logradouro || f.logradouro,
          bairro: d!.bairro || f.bairro,
          cidade: d!.cidade || f.cidade,
          uf: d!.uf || f.uf,
        }));
      }
    } finally {
      setCepLoading(false);
    }
  };

  const enviarDados = async () => {
    setErro('');
    const faltando = CAMPOS.filter((c) => c.obrig && !(form[c.key] || '').trim());
    if (faltando.length) { setErro(`Preencha: ${faltando.map((c) => c.label).join(', ')}`); return; }
    if (!token) { setErro('Link inválido (sem token). Peça o link correto.'); return; }
    setEnviando(true);
    try {
      const r = await api.post(API, { token, ...form });
      const data = r.data as Resultado;
      // auto-login: guarda o token pra cadastrar o rosto na mesma tela, sem passar por login
      if (typeof window !== 'undefined' && data.access_token) {
        localStorage.setItem('access_token', data.access_token);
      }
      setRes(data);
      setStep('facial');
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErro(typeof msg === 'string' ? msg : 'Não foi possível cadastrar. Verifique os dados.');
    } finally {
      setEnviando(false);
    }
  };

  const cadastrarRosto = async (r: FacialCaptureResult) => {
    if (!r.descriptor?.length) { setErro('Não consegui ler seu rosto. Tente em local iluminado.'); return; }
    setEnviando(true); setErro('');
    try {
      await api.post(FACIAL, { descriptor: r.descriptor });
      setStep('done');
    } catch {
      setErro('Falha ao salvar o rosto. Toque em tentar de novo.');
    } finally {
      setEnviando(false);
    }
  };

  // ---- Passo 3: concluído ----
  if (step === 'done' && res) {
    return (
      <div className="max-w-md mx-auto p-6 text-center">
        <CheckCircle2 className="w-16 h-16 text-emerald-500 mx-auto mb-4" />
        <h1 className="text-xl font-bold mb-1">Tudo pronto, {res.login_email.split('@')[0]}!</h1>
        <p className="text-sm text-gray-500 mb-4">Cadastro e rosto concluídos. Você já pode bater o ponto.</p>
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-left text-sm space-y-1 mb-4">
          <p><b>Matrícula:</b> {res.matricula}</p>
          <p><b>Função:</b> {res.cargo}</p>
          <p><b>Escala:</b> {res.escala} — {res.turno} ({res.horario})</p>
          <p><b>Login:</b> {res.login_email}</p>
          <p><b>Senha:</b> seu CPF (só números)</p>
        </div>
        <a href="/modulos/meu-espaco" className="block w-full rounded-xl py-3 font-semibold text-white bg-[#F97316] hover:bg-[#EA6A0A]">
          Ir bater o ponto
        </a>
      </div>
    );
  }

  // ---- Passo 2: cadastro do rosto (mesma tela, logo após os dados) ----
  if (step === 'facial') {
    return (
      <div className="max-w-md mx-auto p-5 text-center">
        <div className="flex items-center justify-center gap-2 mb-1">
          <Camera className="w-6 h-6 text-[#F97316]" />
          <h1 className="text-xl font-bold">Cadastre seu rosto</h1>
        </div>
        <p className="text-sm text-gray-500 mb-5">
          Centralize o rosto no círculo — a captura é automática. É com ele que você bate o ponto.
        </p>
        {erro && <div className="mb-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm p-3">{erro}</div>}
        <FacialCapture onCapture={cadastrarRosto} onError={(m) => setErro(m)} />
        {enviando && <p className="mt-3 text-sm text-gray-500 flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Salvando rosto…</p>}
      </div>
    );
  }

  // ---- Passo 1: dados (rigor eSocial) ----
  return (
    <div className="max-w-md mx-auto p-5">
      <div className="flex items-center gap-2 mb-1">
        <ShieldCheck className="w-6 h-6 text-[#F97316]" />
        <h1 className="text-xl font-bold">Cadastro — Homologação</h1>
      </div>
      <p className="text-sm text-gray-500 mb-5">
        Preencha com <b>os mesmos dados que o eSocial exige</b>. Sua <b>senha é o seu CPF</b>.
        Depois você cadastra o rosto e já bate o ponto.
      </p>

      {erro && <div className="mb-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm p-3">{erro}</div>}

      <div className="grid grid-cols-2 gap-3">
        {CAMPOS.map((c) => (
          <div key={c.key} className={c.full ? 'col-span-2' : 'col-span-1'}>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">
              {c.label}{c.obrig && <span className="text-red-500"> *</span>}
              {c.key === 'cep' && cepLoading && <span className="ml-1 text-[#F97316]">buscando…</span>}
            </label>
            <input
              type={c.type || 'text'}
              value={form[c.key] || ''}
              placeholder={c.placeholder}
              onChange={(e) => {
                set(c.key, e.target.value);
                if (c.key === 'cep' && e.target.value.replace(/\D/g, '').length === 8) buscarCep(e.target.value);
              }}
              onBlur={c.key === 'cep' ? () => buscarCep(form.cep) : undefined}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-transparent px-3 py-2 text-sm focus:border-[#F97316] focus:outline-none"
            />
          </div>
        ))}
      </div>

      <button
        onClick={enviarDados}
        disabled={enviando}
        className="mt-5 w-full rounded-xl py-3 font-semibold text-white bg-[#F97316] hover:bg-[#EA6A0A] disabled:bg-[#F97316]/60 flex items-center justify-center gap-2"
      >
        {enviando ? <><Loader2 className="w-5 h-5 animate-spin" /> Enviando…</> : 'Continuar para o rosto'}
      </button>
    </div>
  );
}

export default function HomologacaoPage() {
  return (
    <main className="min-h-screen py-6">
      <Suspense fallback={<div className="p-8 text-center text-gray-400">Carregando…</div>}>
        <Fluxo />
      </Suspense>
    </main>
  );
}
