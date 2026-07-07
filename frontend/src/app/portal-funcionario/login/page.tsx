'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Eye, EyeOff, FileText, Calendar, FolderOpen, Loader2, ShieldCheck } from 'lucide-react';

function formatCPF(value: string): string {
  const digits = value.replace(/\D/g, '').slice(0, 11);
  if (digits.length <= 3) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 3)}.${digits.slice(3)}`;
  if (digits.length <= 9) return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6)}`;
  return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}`;
}

export default function PortalLoginPage() {
  const router = useRouter();
  const [cpf, setCpf] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [shake, setShake] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await fetch('/api/v1/people-management/portal/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cpf: cpf.replace(/\D/g, ''), password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'CPF ou senha incorretos');
      }

      const data = await res.json();
      localStorage.setItem('portal_token', data.access_token);
      if (data.refresh_token) localStorage.setItem('portal_refresh_token', data.refresh_token);
      if (data.employee_name) localStorage.setItem('portal_employee_name', data.employee_name);
      router.push('/portal-funcionario/dashboard');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Erro ao fazer login';
      setError(msg);
      setShake(true);
      setTimeout(() => setShake(false), 600);
    } finally {
      setLoading(false);
    }
  };

  const features = [
    { icon: FileText, label: 'Contracheques', desc: 'Acesse seus holerites a qualquer momento' },
    { icon: Calendar, label: 'Férias e Licenças', desc: 'Consulte saldo e faca solicitacoes' },
    { icon: FolderOpen, label: 'Documentos', desc: 'Baixe declaracoes e comprovantes' },
  ];

  return (
    <div className="min-h-screen flex flex-col lg:flex-row">
      {/* Lado esquerdo — branding */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-[#0A2540] to-[#1E3A5F] text-white flex-col justify-center px-16 relative overflow-hidden min-h-0">
        <div className="absolute inset-0 opacity-5">
          <div className="absolute top-20 left-10 w-72 h-72 bg-white rounded-full blur-3xl" />
          <div className="absolute bottom-20 right-10 w-96 h-96 bg-blue-300 rounded-full blur-3xl" />
        </div>
        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-2">
            <ShieldCheck className="w-10 h-10 text-blue-300" />
            <h1 className="text-4xl font-bold tracking-tight">CONECTA PRO</h1>
          </div>
          <p className="text-blue-200 text-lg mb-12">Seu espaco de trabalho digital</p>
          <div className="space-y-6">
            {features.map((f) => (
              <div key={f.label} className="flex items-start gap-4">
                <div className="p-2.5 bg-white/10 rounded-lg backdrop-blur">
                  <f.icon className="w-5 h-5 text-blue-200" />
                </div>
                <div>
                  <h3 className="font-semibold text-white">{f.label}</h3>
                  <p className="text-blue-300 text-sm">{f.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Lado direito — formulario */}
      <div className="flex-1 flex items-center justify-center bg-gray-50 px-6 py-12">
        <div className={`w-full max-w-md ${shake ? 'animate-[shake_0.5s_ease-in-out]' : ''}`}>
          {/* Mobile header */}
          <div className="lg:hidden text-center mb-8">
            <div className="flex items-center justify-center gap-2 mb-1">
              <ShieldCheck className="w-7 h-7 text-[#0A2540]" />
              <h1 className="font-display text-2xl font-bold text-[#0A2540]">CONECTA PRO</h1>
            </div>
            <p className="text-gray-500 text-sm">Portal do Funcionario</p>
          </div>

          <div className="bg-white rounded-2xl shadow-xl border border-gray-100 p-8">
            <h2 className="font-display text-2xl font-bold text-gray-900 mb-1">Bem-vindo</h2>
            <p className="text-gray-500 text-sm mb-6">Acesse com seu CPF e senha</p>

            {error && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="cpf" className="block text-sm font-medium text-gray-700 mb-1">CPF</label>
                <input
                  id="cpf"
                  type="text"
                  value={cpf}
                  onChange={(e) => setCpf(formatCPF(e.target.value))}
                  placeholder="000.000.000-00"
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:ring-2 focus:ring-[#0A2540] focus:border-transparent outline-none transition"
                  required
                  maxLength={14}
                  inputMode="numeric"
                  autoComplete="username"
                />
              </div>

              <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">Senha</label>
                <div className="relative">
                  <input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Digite sua senha"
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:ring-2 focus:ring-[#0A2540] focus:border-transparent outline-none transition pr-12"
                    required
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    tabIndex={-1}
                  >
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading || cpf.replace(/\D/g, '').length < 11}
                className="w-full py-3 bg-[#0A2540] hover:bg-[#1E3A5F] text-white font-semibold rounded-xl transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                {loading ? 'Entrando...' : 'Entrar'}
              </button>
            </form>

            <div className="mt-6 flex items-center justify-between text-sm">
              <Link href="/portal-funcionario/primeiro-acesso" className="text-[#0A2540] hover:underline font-medium">
                Primeiro Acesso
              </Link>
              <Link href="/portal-funcionario/reset-senha" className="text-gray-500 hover:text-gray-700">
                Esqueci minha senha
              </Link>
            </div>
          </div>

          <p className="text-center text-xs text-gray-400 mt-6">
            Conecta Mais &copy; {new Date().getFullYear()} &mdash; Seguranca e Tecnologia
          </p>
        </div>
      </div>
    </div>
  );
}
