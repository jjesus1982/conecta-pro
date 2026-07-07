'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, CheckCircle2, Loader2, ShieldCheck, Eye, EyeOff } from 'lucide-react';

function formatCPF(value: string): string {
  const d = value.replace(/\D/g, '').slice(0, 11);
  if (d.length <= 3) return d;
  if (d.length <= 6) return `${d.slice(0, 3)}.${d.slice(3)}`;
  if (d.length <= 9) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6)}`;
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
}

function passwordStrength(pw: string): { level: number; label: string; color: string } {
  let score = 0;
  if (pw.length >= 8) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  if (score <= 1) return { level: 1, label: 'Fraca', color: 'bg-red-500' };
  if (score <= 2) return { level: 2, label: 'Media', color: 'bg-yellow-500' };
  if (score <= 3) return { level: 3, label: 'Boa', color: 'bg-blue-500' };
  return { level: 4, label: 'Forte', color: 'bg-green-500' };
}

export default function PrimeiroAcessoPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [cpf, setCpf] = useState('');
  const [dataNasc, setDataNasc] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const strength = passwordStrength(password);
  const passwordValid = password.length >= 8 && /[A-Z]/.test(password) && /[0-9]/.test(password) && /[^A-Za-z0-9]/.test(password);
  const passwordsMatch = password === confirmPassword && confirmPassword.length > 0;

  const handleStep1 = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setStep(2);
  };

  const handleStep2 = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!passwordValid) { setError('Senha nao atende aos requisitos'); return; }
    if (!passwordsMatch) { setError('Senhas nao conferem'); return; }

    setError('');
    setLoading(true);
    try {
      const res = await fetch('/api/v1/people-management/portal/auth/primeiro-acesso', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cpf: cpf.replace(/\D/g, ''),
          data_nascimento: dataNasc,
          nova_senha: password,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Erro ao criar acesso');
      }
      setSuccess(true);
      setTimeout(() => router.push('/portal-funcionario/login'), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro inesperado');
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <CheckCircle2 className="w-16 h-16 text-green-500 mx-auto mb-4" />
          <h2 className="font-display text-2xl font-bold text-gray-900 mb-2">Acesso criado com sucesso!</h2>
          <p className="text-gray-500">Redirecionando para o login...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col lg:flex-row">
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-[#0A2540] to-[#1E3A5F] text-white flex-col justify-center px-16">
        <ShieldCheck className="w-10 h-10 text-blue-300 mb-4" />
        <h1 className="font-display text-3xl font-bold mb-2">Primeiro Acesso</h1>
        <p className="text-blue-200">Configure sua senha para acessar o portal.</p>
        <div className="mt-8 space-y-3">
          {[1, 2].map((s) => (
            <div key={s} className={`flex items-center gap-3 ${step >= s ? 'text-white' : 'text-blue-400'}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${step > s ? 'bg-green-500' : step === s ? 'bg-white text-[#0A2540]' : 'bg-white/20'}`}>
                {step > s ? '✓' : s}
              </div>
              <span className="text-sm">{s === 1 ? 'Identificacao' : 'Criar Senha'}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center bg-gray-50 px-6 py-12">
        <div className="w-full max-w-md">
          <Link href="/portal-funcionario/login" className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 mb-6">
            <ArrowLeft className="w-4 h-4" /> Voltar ao login
          </Link>

          {/* Stepper mobile */}
          <div className="flex items-center justify-center mb-6 lg:hidden">
            <div className={`flex items-center gap-2 ${step >= 1 ? 'text-blue-600' : 'text-gray-400'}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${step > 1 ? 'bg-green-500 text-white' : step === 1 ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-500'}`}>{step > 1 ? '✓' : '1'}</div>
              <span className="text-sm font-medium">Identificacao</span>
            </div>
            <div className={`w-12 h-0.5 mx-2 ${step >= 2 ? 'bg-blue-600' : 'bg-gray-200'}`} />
            <div className={`flex items-center gap-2 ${step >= 2 ? 'text-blue-600' : 'text-gray-400'}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${step >= 2 ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-500'}`}>2</div>
              <span className="text-sm font-medium">Nova Senha</span>
            </div>
          </div>

          <div className="bg-white rounded-2xl shadow-xl border border-gray-100 p-8">
            <h2 className="text-xl font-bold text-gray-900 mb-1">
              {step === 1 ? 'Primeiro Acesso — Identificacao' : 'Primeiro Acesso — Criar Senha'}
            </h2>
            <p className="text-gray-500 text-sm mb-6">
              {step === 1 ? 'Informe seu CPF e data de nascimento' : 'Escolha uma senha segura'}
            </p>

            {error && <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">{error}</div>}

            {step === 1 ? (
              <form onSubmit={handleStep1} className="space-y-4">
                <div>
                  <label htmlFor="cpf-pa" className="block text-sm font-medium text-gray-700 mb-1">CPF</label>
                  <input id="cpf-pa" type="text" value={cpf} onChange={(e) => setCpf(formatCPF(e.target.value))} placeholder="000.000.000-00" className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-[#0A2540] outline-none" required maxLength={14} inputMode="numeric" />
                </div>
                <div>
                  <label htmlFor="nasc" className="block text-sm font-medium text-gray-700 mb-1">Data de Nascimento</label>
                  <input id="nasc" type="date" value={dataNasc} onChange={(e) => setDataNasc(e.target.value)} className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-[#0A2540] outline-none" required />
                </div>
                <button type="submit" disabled={cpf.replace(/\D/g, '').length < 11 || !dataNasc} className="w-full py-3 bg-[#0A2540] hover:bg-[#1E3A5F] text-white font-semibold rounded-xl transition disabled:opacity-50">Continuar</button>
              </form>
            ) : (
              <form onSubmit={handleStep2} className="space-y-4">
                <div>
                  <label htmlFor="pw-new" className="block text-sm font-medium text-gray-700 mb-1">Nova Senha</label>
                  <div className="relative">
                    <input id="pw-new" type={showPw ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Minimo 8 caracteres" className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-[#0A2540] outline-none pr-12" required />
                    <button type="button" onClick={() => setShowPw(!showPw)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400" tabIndex={-1}>
                      {showPw ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                  {password && (
                    <div className="mt-2">
                      <div className="flex gap-1 mb-1">{[1, 2, 3, 4].map((i) => (<div key={i} className={`h-1.5 flex-1 rounded-full ${i <= strength.level ? strength.color : 'bg-gray-200'}`} />))}</div>
                      <p className={`text-xs ${strength.level <= 1 ? 'text-red-500' : strength.level <= 2 ? 'text-yellow-600' : 'text-green-600'}`}>Senha {strength.label}</p>
                    </div>
                  )}
                </div>
                <div>
                  <label htmlFor="pw-confirm" className="block text-sm font-medium text-gray-700 mb-1">Confirmar Senha</label>
                  <input id="pw-confirm" type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="Repita a senha" className={`w-full px-4 py-3 border rounded-xl focus:ring-2 focus:ring-[#0A2540] outline-none ${confirmPassword && !passwordsMatch ? 'border-red-300' : 'border-gray-300'}`} required />
                  {confirmPassword && !passwordsMatch && <p className="text-xs text-red-500 mt-1">Senhas nao conferem</p>}
                </div>
                <ul className="text-xs text-gray-500 space-y-0.5">
                  <li className={password.length >= 8 ? 'text-green-600' : ''}>✓ Minimo 8 caracteres</li>
                  <li className={/[A-Z]/.test(password) ? 'text-green-600' : ''}>✓ Uma letra maiuscula</li>
                  <li className={/[0-9]/.test(password) ? 'text-green-600' : ''}>✓ Um numero</li>
                  <li className={/[^A-Za-z0-9]/.test(password) ? 'text-green-600' : ''}>✓ Um caractere especial</li>
                </ul>
                <button type="submit" disabled={loading || !passwordValid || !passwordsMatch} className="w-full py-3 bg-[#0A2540] hover:bg-[#1E3A5F] text-white font-semibold rounded-xl transition disabled:opacity-50 flex items-center justify-center gap-2">
                  {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                  {loading ? 'Criando...' : 'Criar Acesso'}
                </button>
              </form>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
