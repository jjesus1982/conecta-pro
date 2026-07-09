'use client';

import { AlertCircle } from 'lucide-react';
import { Suspense, useState, useMemo, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/hooks/useAuth';

const OAUTH_ERROR_MESSAGES: Record<string, string> = {
  google_auth_failed: 'Falha na autenticacao com Google',
  no_code: 'Codigo de autorizacao nao recebido',
  missing_state: 'Parametro de seguranca ausente',
  invalid_state: 'Sessao expirada. Tente novamente',
  oauth_not_configured: 'Login com Google nao configurado',
  token_exchange_failed: 'Falha ao processar autenticacao',
  userinfo_failed: 'Falha ao obter dados do Google',
  no_email: 'Conta Google sem email associado',
  user_inactive: 'Usuario inativo. Contate o administrador',
  internal_error: 'Erro interno. Tente novamente',
  no_tokens: 'Falha ao receber tokens de autenticacao',
};

function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, isLoading, isAuthenticated } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  // Redirecionar para dashboard se já autenticado
  // Usa window.location.href (hard redirect) para garantir que o cookie
  // auth_token chegue ao middleware — router.push() pode não enviar o cookie
  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      const redirect = searchParams.get('redirect') || '/dashboard';
      window.location.href = redirect;
    }
  }, [isLoading, isAuthenticated, searchParams]);

  const oauthError = useMemo(() => {
    const code = searchParams.get('error');
    if (!code) return '';
    return OAUTH_ERROR_MESSAGES[code] ?? 'Erro na autenticacao';
  }, [searchParams]);

  const displayError = error || oauthError;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    const result = await login({ email, password });
    if (result.success) {
      router.push('/dashboard');
    } else {
      setError(result.error || 'Erro ao fazer login');
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* ── PAINEL ESQUERDO ── */}
      <div
        className="hidden lg:flex flex-col justify-between relative overflow-hidden min-h-0"
        style={{ flex: '1.25', background: '#1E3A5F', padding: '44px 52px' }}
      >
        {/* Circles */}
        <div
          className="absolute pointer-events-none"
          style={{ top: -100, right: -100, width: 360, height: 360, borderRadius: '50%', background: 'rgba(249,115,22,0.06)' }}
        />
        <div
          className="absolute pointer-events-none"
          style={{ bottom: -80, left: -80, width: 280, height: 280, borderRadius: '50%', background: 'rgba(249,115,22,0.04)' }}
        />

        {/* LOGO */}
        <div className="flex items-center relative z-10">
          <svg width="54" height="54" viewBox="0 0 56 56" fill="none">
            <circle cx="28" cy="28" r="8" stroke="#F97316" strokeWidth="2.2" fill="none" />
            <circle cx="28" cy="28" r="3.5" fill="#F97316" />
            <line x1="28" y1="5" x2="28" y2="18" stroke="#5B9BD5" strokeWidth="2.2" strokeLinecap="round" />
            <line x1="28" y1="38" x2="28" y2="51" stroke="#5B9BD5" strokeWidth="2.2" strokeLinecap="round" />
            <line x1="5" y1="28" x2="18" y2="28" stroke="#5B9BD5" strokeWidth="2.2" strokeLinecap="round" />
            <line x1="38" y1="28" x2="51" y2="28" stroke="#5B9BD5" strokeWidth="2.2" strokeLinecap="round" />
            <circle cx="28" cy="7" r="3" stroke="white" strokeWidth="1.8" fill="rgba(255,255,255,0.1)" />
            <circle cx="28" cy="49" r="3" stroke="white" strokeWidth="1.8" fill="rgba(255,255,255,0.1)" />
            <circle cx="7" cy="28" r="3" stroke="white" strokeWidth="1.8" fill="rgba(255,255,255,0.1)" />
            <circle cx="49" cy="28" r="3" stroke="white" strokeWidth="1.8" fill="rgba(255,255,255,0.1)" />
            <line x1="12" y1="12" x2="20.5" y2="20.5" stroke="#F97316" strokeWidth="2" strokeLinecap="round" />
            <line x1="35.5" y1="35.5" x2="44" y2="44" stroke="#F97316" strokeWidth="2" strokeLinecap="round" />
            <line x1="44" y1="12" x2="35.5" y2="20.5" stroke="#F97316" strokeWidth="2" strokeLinecap="round" />
            <line x1="20.5" y1="35.5" x2="12" y2="44" stroke="#F97316" strokeWidth="2" strokeLinecap="round" />
            <circle cx="11" cy="11" r="2.8" fill="#F97316" />
            <circle cx="45" cy="45" r="2.8" fill="#F97316" />
            <circle cx="45" cy="11" r="2.8" fill="#F97316" />
            <circle cx="11" cy="45" r="2.8" fill="#F97316" />
            <rect x="24" y="2" width="8" height="4" rx="1.5" fill="rgba(255,255,255,0.6)" />
            <rect x="24" y="50" width="8" height="4" rx="1.5" fill="rgba(255,255,255,0.6)" />
            <rect x="2" y="24" width="4" height="8" rx="1.5" fill="rgba(255,255,255,0.6)" />
            <rect x="50" y="24" width="4" height="8" rx="1.5" fill="rgba(255,255,255,0.6)" />
            <polygon points="13,7 7,7 7,13" fill="#F97316" opacity="0.85" />
            <polygon points="43,49 49,49 49,43" fill="#F97316" opacity="0.85" />
          </svg>
          <div className="ml-3.5">
            <div className="flex items-baseline gap-1.5 text-xl font-bold tracking-tight">
              <span className="text-white">CONECTA</span>
              <span style={{ color: '#F97316' }}>PRO</span>
            </div>
            <div className="mt-1" style={{ fontSize: '10.5px', color: 'rgba(255,255,255,0.38)' }}>
              by <span style={{ color: 'rgba(249,115,22,0.65)', fontWeight: 500 }}>Conecta Mais</span>
            </div>
          </div>
        </div>

        {/* HERO */}
        <div className="relative z-10 text-center flex flex-col items-center">
          <div
            className="inline-flex items-center gap-2 rounded-full mb-8"
            style={{
              background: 'rgba(249,115,22,0.12)',
              border: '1px solid rgba(249,115,22,0.25)',
              padding: '5px 16px 5px 12px',
              fontSize: '10.5px',
              fontWeight: 600,
              color: '#FB923C',
              letterSpacing: '0.5px',
              textTransform: 'uppercase',
            }}
          >
            <span
              className="inline-block flex-shrink-0 rounded-full"
              style={{ width: 6, height: 6, background: '#F97316', animation: 'login-pulse 2s infinite' }}
            />
            Seguranca Patrimonial & Eletronica
          </div>

          <div style={{ fontSize: 13, fontWeight: 400, color: 'rgba(255,255,255,0.45)', letterSpacing: '0.8px', textTransform: 'uppercase', marginBottom: 12 }}>
            Sistema de Gestao Empresarial
          </div>

          <div className="flex items-center gap-3 w-full mb-3.5">
            <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.1)' }} />
            <div style={{ width: 8, height: 8, background: '#F97316', transform: 'rotate(45deg)', opacity: 0.8, flexShrink: 0 }} />
            <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.1)' }} />
          </div>

          <div style={{ fontSize: 44, fontWeight: 800, letterSpacing: '-1.5px', lineHeight: 1, marginBottom: 10 }}>
            <span className="text-white">Conecta</span>{' '}
            <span style={{ color: '#F97316' }}>Mais</span>
          </div>

          <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.35)', letterSpacing: '1.5px', textTransform: 'uppercase', fontWeight: 400 }}>
            Tecnologia para quem protege
          </div>
        </div>

        {/* MODULOS */}
        <div className="relative z-10">
          <div
            style={{
              fontSize: 10,
              color: 'rgba(255,255,255,0.28)',
              textTransform: 'uppercase',
              letterSpacing: '1px',
              marginBottom: 12,
              borderTop: '1px solid rgba(255,255,255,0.07)',
              paddingTop: 20,
              textAlign: 'center',
            }}
          >
            Modulos disponiveis
          </div>

          <div className="flex flex-wrap gap-2 mb-3.5 justify-center">
            {['Operacional', 'Financeiro', 'GED & Fiscal', 'DP & Folha', 'CFTV & Eletronica'].map((m) => (
              <div
                key={m}
                className="flex items-center gap-1.5"
                style={{
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px solid rgba(255,255,255,0.08)',
                  borderRadius: 8,
                  padding: '7px 13px',
                  fontSize: 11.5,
                  color: 'rgba(255,255,255,0.68)',
                }}
              >
                <span className="inline-block flex-shrink-0 rounded-full" style={{ width: 5, height: 5, background: '#F97316', opacity: 0.8 }} />
                {m}
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2.5">
            <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.06)' }} />
            <div
              className="inline-flex items-center gap-1.5"
              style={{
                background: 'rgba(249,115,22,0.14)',
                border: '1px solid rgba(249,115,22,0.32)',
                borderRadius: 100,
                padding: '6px 20px',
                fontSize: 12,
                fontWeight: 700,
                color: '#FB923C',
                letterSpacing: '0.3px',
              }}
            >
              &#10022; E muito mais
            </div>
            <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.06)' }} />
          </div>
        </div>
      </div>

      {/* ── PAINEL DIREITO ── */}
      <div className="flex-1 bg-white flex flex-col justify-center" style={{ padding: '52px 50px' }}>
        <div className="max-w-md mx-auto w-full">
          <div style={{ marginBottom: 28 }}>
            {/* Mobile logo */}
            <div className="lg:hidden flex items-center gap-2 mb-6">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: '#1E3A5F' }}>
                <span className="text-white font-bold text-xs">C</span>
              </div>
              <span className="font-bold" style={{ color: '#1E3A5F' }}>
                CONECTA <span style={{ color: '#F97316' }}>PRO</span>
              </span>
            </div>

            <span style={{ display: 'inline-block', fontSize: 11, fontWeight: 600, color: '#F97316', textTransform: 'uppercase', letterSpacing: '.8px', marginBottom: 10 }}>
              Conecta PRO v2.0.0
            </span>
            <h2 style={{ fontSize: 26, fontWeight: 700, color: '#1E3A5F', letterSpacing: '-0.5px', marginBottom: 5, lineHeight: 1.2 }}>
              Bem-vindo de volta
            </h2>
            <p style={{ fontSize: 13.5, color: '#6B7280', lineHeight: 1.5 }}>Entre com suas credenciais para acessar o sistema</p>
          </div>

          {/* Erro */}
          {displayError && (
            <div className="flex items-center gap-2 p-3 rounded-xl mb-4" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
              <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-500" />
              <span className="text-sm text-red-600">{displayError}</span>
            </div>
          )}

          <form onSubmit={handleSubmit}>
            {/* E-mail */}
            <div style={{ marginBottom: 15 }}>
              <label style={{ display: 'block', fontSize: 12.5, fontWeight: 600, color: '#374151', marginBottom: 7 }}>E-mail</label>
              <div style={{ position: 'relative' }}>
                <svg
                  style={{ position: 'absolute', left: 13, top: '50%', transform: 'translateY(-50%)', width: 15, height: 15, color: '#9CA3AF', pointerEvents: 'none' }}
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                >
                  <rect x="2" y="4" width="20" height="16" rx="2.5" />
                  <path d="M2 7.5l10 7 10-7" />
                </svg>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="seu@email.com"
                  required
                  autoFocus
                  style={{
                    width: '100%',
                    height: 44,
                    border: '1.5px solid #E9ECEF',
                    borderRadius: 10,
                    padding: '0 14px 0 40px',
                    fontSize: 13.5,
                    color: '#111827',
                    background: '#F8F9FB',
                    outline: 'none',
                    fontFamily: 'inherit',
                  }}
                />
              </div>
            </div>

            {/* Senha */}
            <div style={{ marginBottom: 8 }}>
              <label style={{ display: 'block', fontSize: 12.5, fontWeight: 600, color: '#374151', marginBottom: 7 }}>Senha</label>
              <div style={{ position: 'relative' }}>
                <svg
                  style={{ position: 'absolute', left: 13, top: '50%', transform: 'translateY(-50%)', width: 15, height: 15, color: '#9CA3AF', pointerEvents: 'none' }}
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                >
                  <rect x="3" y="11" width="18" height="11" rx="2.5" />
                  <path d="M7 11V7a5 5 0 0110 0v4" />
                </svg>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  style={{
                    width: '100%',
                    height: 44,
                    border: '1.5px solid #E9ECEF',
                    borderRadius: 10,
                    padding: '0 14px 0 40px',
                    fontSize: 13.5,
                    color: '#111827',
                    background: '#F8F9FB',
                    outline: 'none',
                    fontFamily: 'inherit',
                  }}
                />
              </div>
              <div className="flex items-center justify-between mt-2.5">
                <label className="flex items-center gap-2 cursor-pointer" style={{ fontSize: 13, color: '#6B7280' }}>
                  <input type="checkbox" style={{ accentColor: '#F97316' }}  aria-label="Checkbox" />
                  Lembrar-me
                </label>
                <Link href="/forgot-password" style={{ fontSize: 13, fontWeight: 600, color: '#F97316' }}>
                  Esqueci a senha
                </Link>
              </div>
            </div>

            {/* Botao Entrar */}
            <button
              type="submit"
              disabled={isLoading}
              style={{
                width: '100%',
                height: 46,
                background: isLoading ? '#2d5a8f' : '#1E3A5F',
                color: '#fff',
                border: 'none',
                borderRadius: 10,
                fontSize: 15,
                fontWeight: 600,
                cursor: isLoading ? 'wait' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 9,
                marginTop: 8,
                letterSpacing: '-0.1px',
                fontFamily: 'inherit',
                transition: 'background .15s',
              }}
            >
              {isLoading ? 'Entrando...' : 'Entrar'}
              {!isLoading && (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              )}
            </button>
          </form>

          {/* Divisor */}
          <div className="flex items-center gap-3" style={{ margin: '17px 0' }}>
            <div style={{ flex: 1, height: 1, background: '#E9ECEF' }} />
            <span style={{ fontSize: 12, color: '#9CA3AF', whiteSpace: 'nowrap' }}>ou continue com</span>
            <div style={{ flex: 1, height: 1, background: '#E9ECEF' }} />
          </div>

          {/* Google */}
          <a
            href="/api/v1/auth/google"
            style={{
              width: '100%',
              height: 44,
              background: '#fff',
              border: '1.5px solid #E9ECEF',
              borderRadius: 10,
              fontSize: 13.5,
              fontWeight: 500,
              color: '#374151',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 10,
              fontFamily: 'inherit',
              textDecoration: 'none',
              transition: 'border-color .15s, background .15s',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 18 18">
              <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" />
              <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" />
              <path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" />
              <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" />
            </svg>
            Entrar com Google
          </a>

          {/* Criar conta */}
          <p style={{ marginTop: 16, textAlign: 'center', fontSize: 13, color: '#6B7280' }}>
            Ainda não tem conta?{' '}
            <Link href="/cadastro" style={{ color: '#F97316', fontWeight: 600, textDecoration: 'none' }}>
              Criar conta
            </Link>
          </p>

          {/* Footer */}
          <p style={{ marginTop: 18, textAlign: 'center', fontSize: 11.5, color: '#9CA3AF', lineHeight: 1.6 }}>
            Ao entrar, voce concorda com os{' '}
            <a href="/termos" style={{ color: '#F97316', textDecoration: 'none', fontWeight: 600 }}>
              Termos de Uso
            </a>{' '}
            e{' '}
            <a href="/privacidade" style={{ color: '#F97316', textDecoration: 'none', fontWeight: 600 }}>
              Politica de Privacidade
            </a>
          </p>
        </div>
      </div>

      {/* CSS pulse */}
      <style>{`
        @keyframes login-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(0.8); }
        }
      `}</style>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginContent />
    </Suspense>
  );
}
