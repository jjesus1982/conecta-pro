'use client';

/**
 * Autocadastro de HOMOLOGAÇÃO (base de teste, posto "Conecta Base").
 * Link tokenizado: /homologacao?token=... — coleta dados com rigor eSocial, cria o
 * funcionário de teste + login + escala, e manda pro Meu Espaço (cadastro facial + ponto).
 * Público (pré-login). Isolado da folha/eSocial reais (is_homologacao).
 */
import { Suspense, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { Loader2, CheckCircle2, ShieldCheck, Camera } from 'lucide-react';

const API = '/api/v1/people-management/portal/homologacao/autocadastro';

type Campo = { key: string; label: string; type?: string; placeholder?: string; obrig?: boolean; full?: boolean };

const CAMPOS: Campo[] = [
  { key: 'nome', label: 'Nome completo', obrig: true, full: true },
  { key: 'email', label: 'E-mail (será seu login)', type: 'email', obrig: true, full: true },
  { key: 'senha', label: 'Senha (mín. 6)', type: 'password', obrig: true },
  { key: 'cpf', label: 'CPF', obrig: true },
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
  horario: string; posto: string; login_email: string; proximo_passo: string;
}

function Form() {
  const params = useSearchParams();
  const token = params.get('token') || '';
  const [form, setForm] = useState<Record<string, string>>({});
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState('');
  const [ok, setOk] = useState<Resultado | null>(null);

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    setErro('');
    const faltando = CAMPOS.filter((c) => c.obrig && !(form[c.key] || '').trim());
    if (faltando.length) { setErro(`Preencha: ${faltando.map((c) => c.label).join(', ')}`); return; }
    if (!token) { setErro('Link inválido (sem token). Peça o link correto.'); return; }
    setEnviando(true);
    try {
      const res = await api.post(API, { token, ...form });
      setOk(res.data as Resultado);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErro(typeof msg === 'string' ? msg : 'Não foi possível cadastrar. Verifique os dados e tente de novo.');
    } finally {
      setEnviando(false);
    }
  };

  if (ok) {
    return (
      <div className="max-w-md mx-auto p-6 text-center">
        <CheckCircle2 className="w-16 h-16 text-emerald-500 mx-auto mb-4" />
        <h1 className="text-xl font-bold mb-1">Cadastro de homologação criado!</h1>
        <p className="text-sm text-gray-500 mb-4">Bem-vindo(a) à Conecta Base.</p>
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-left text-sm space-y-1 mb-4">
          <p><b>Matrícula:</b> {ok.matricula}</p>
          <p><b>Função:</b> {ok.cargo}</p>
          <p><b>Escala:</b> {ok.escala} — {ok.turno} ({ok.horario})</p>
          <p><b>Posto:</b> {ok.posto}</p>
          <p><b>Login:</b> {ok.login_email}</p>
        </div>
        <div className="rounded-xl bg-[#f97707]/10 border border-[#f97707]/25 p-3 text-sm text-left mb-4 flex gap-2">
          <Camera className="w-5 h-5 text-[#f97707] flex-shrink-0" />
          <span>Próximo passo: entre no <b>Meu Espaço</b>, <b>cadastre seu rosto</b> (obrigatório) e bata o ponto.</span>
        </div>
        <a href="/login" className="block w-full rounded-xl py-3 font-semibold text-white bg-[#f97707] hover:bg-[#e06a00]">
          Ir para o login
        </a>
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto p-5">
      <div className="flex items-center gap-2 mb-1">
        <ShieldCheck className="w-6 h-6 text-[#f97707]" />
        <h1 className="text-xl font-bold">Cadastro — Homologação</h1>
      </div>
      <p className="text-sm text-gray-500 mb-5">
        Preencha com <b>os mesmos dados que o eSocial exige</b> (é assim na produção real).
        Sua função e escala são atribuídas automaticamente.
      </p>

      {erro && <div className="mb-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm p-3">{erro}</div>}

      <div className="grid grid-cols-2 gap-3">
        {CAMPOS.map((c) => (
          <div key={c.key} className={c.full ? 'col-span-2' : 'col-span-1'}>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">
              {c.label}{c.obrig && <span className="text-red-500"> *</span>}
            </label>
            <input
              type={c.type || 'text'}
              value={form[c.key] || ''}
              placeholder={c.placeholder}
              onChange={(e) => set(c.key, e.target.value)}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-transparent px-3 py-2 text-sm focus:border-[#f97707] focus:outline-none"
            />
          </div>
        ))}
      </div>

      <button
        onClick={submit}
        disabled={enviando}
        className="mt-5 w-full rounded-xl py-3 font-semibold text-white bg-[#f97707] hover:bg-[#e06a00] disabled:bg-[#f97707]/60 flex items-center justify-center gap-2"
      >
        {enviando ? <><Loader2 className="w-5 h-5 animate-spin" /> Enviando…</> : 'Criar meu cadastro de teste'}
      </button>
    </div>
  );
}

export default function HomologacaoPage() {
  return (
    <main className="min-h-screen py-6">
      <Suspense fallback={<div className="p-8 text-center text-gray-400">Carregando…</div>}>
        <Form />
      </Suspense>
    </main>
  );
}
