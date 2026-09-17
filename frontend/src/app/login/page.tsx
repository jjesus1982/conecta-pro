'use client';

import { AlertCircle, ScanFace, X, Loader2, Mail, Lock, Check } from 'lucide-react';
import { Suspense, useState, useMemo, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/hooks/useAuth';
import { fetchRetry } from '@/lib/api';
import { FacialCapture, type FacialCaptureResult } from '@/components/ponto/FacialCapture';
import { destinoPosLogin, guardarDestino } from '@/lib/destino-pos-login';
import { Btn } from '@/components/redesign/shell';
// O design system do redesign é escopado em `.rd-root`; esta tela veste o mesmo.
// Origem: 17/09/2026 — o dono viu a tela ANTIGA no link de assinatura que mandamos
// para o funcionário: «é a antiga, do clássico, não é do redesign».
import '../redesign/redesign.css';

//: Só aparece no trilho navy. Mesmo texto do protótipo de login do redesign.
const FEATS = [
  'Portaria remota e monitoramento',
  'Escalas, rondas e ponto',
  'Gestão de pessoas e DP',
  'Financeiro, fiscal e jurídico',
];

function Campo({ icone, ...p }: { icone: React.ReactNode } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
      <span style={{ position: 'absolute', left: 12, color: 'var(--placeholder)', display: 'flex' }}>{icone}</span>
      <input className="rd-input" style={{ paddingLeft: 38, width: '100%' }} {...p} />
    </div>
  );
}

// Destino pós-login: ver lib/destino-pos-login.ts — é o único lugar que decide.

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
  const searchParams = useSearchParams();
  const { login, isLoading, isAuthenticated, user } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [facialOpen, setFacialOpen] = useState(false);
  const [facialLoading, setFacialLoading] = useState(false);

  // Login por reconhecimento facial (1:N) — funcionário que já cadastrou o rosto.
  const handleFacialLogin = async (res: FacialCaptureResult) => {
    if (!res?.descriptor?.length) { setError('Não deu pra ler o rosto. Tente de novo.'); return; }
    setFacialLoading(true); setError('');
    try {
      const r = await fetchRetry('/api/v1/people-management/portal/login-facial', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ descriptor: res.descriptor }),
      });
      const d = await r.json();
      if (!r.ok || !d.access_token) { setError(d.detail || 'Rosto não reconhecido. Use e-mail e CPF.'); setFacialLoading(false); setFacialOpen(false); return; }
      localStorage.setItem('access_token', d.access_token);
      if (d.refresh_token) localStorage.setItem('refresh_token', d.refresh_token);
      const isSecure = window.location.protocol === 'https:';
      document.cookie = `auth_token=${d.access_token}; path=/; max-age=${30 * 60}; SameSite=Lax${isSecure ? '; Secure' : ''}`;
      window.location.href = destinoPosLogin(searchParams.get('redirect'), 'funcionario');
    } catch { setError('Falha na conexão. Tente de novo.'); setFacialLoading(false); setFacialOpen(false); }
  };

  // Redirecionar para dashboard se já autenticado
  // Usa window.location.href (hard redirect) para garantir que o cookie
  // auth_token chegue ao middleware — router.push() pode não enviar o cookie
  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      window.location.href = destinoPosLogin(searchParams.get('redirect'), user?.role);
    }
  }, [isLoading, isAuthenticated, searchParams, user]);

  const oauthError = useMemo(() => {
    const code = searchParams.get('error');
    if (!code) return '';
    return OAUTH_ERROR_MESSAGES[code] ?? 'Erro na autenticacao';
  }, [searchParams]);

  const displayError = error || oauthError;

  const notice = useMemo(() => {
    if (searchParams.get('notice') === 'portal') {
      return 'Portal atualizado — entre com sua conta Google.';
    }
    return '';
  }, [searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    const result = await login({ email, password });
    if (result.success) {
      window.location.href = destinoPosLogin(searchParams.get('redirect'), result.role);
    } else {
      setError(result.error || 'Erro ao fazer login');
    }
  };

  return (
    <div className="rd-root" style={{ display: 'flex', minHeight: '100vh' }}>
      {/* ── TRILHO DA MARCA ── mesmo do redesign: quadrante, navy e a lista de frentes. */}
      <div
        className="rd-hide-mobile"
        style={{
          width: '42%', background: 'var(--navy)', color: '#fff', display: 'flex',
          flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
          gap: 20, padding: 40, textAlign: 'center',
        }}
      >
        <img src="/images/quadrante.png" alt="Conecta PRO" style={{ height: 84, filter: 'brightness(0) invert(1)' }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 28, fontWeight: 700, letterSpacing: '-0.02em' }}>CONECTA</span>
          <span style={{ fontSize: 15, fontWeight: 800, background: 'var(--orange)', padding: '4px 9px', borderRadius: 8 }}>PRO</span>
        </div>
        <div style={{ fontSize: 10.5, fontWeight: 500, letterSpacing: '0.24em', color: 'rgba(255,255,255,0.55)' }}>
          BY CONECTA MAIS<sup style={{ fontSize: 8 }}>®</sup>
        </div>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'rgba(255,255,255,0.82)', lineHeight: 1.5 }}>
          Sistema de gestão para<br />segurança patrimonial
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 9, marginTop: 6 }}>
          {FEATS.map((f) => (
            <div key={f} style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <Check size={14} color="#F9A97A" strokeWidth={2.4} style={{ flex: 'none' }} />
              <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.7)' }}>{f}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── FORMULÁRIO ── */}
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, background: 'var(--surface)' }}>
        <div style={{ width: '100%', maxWidth: 380, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Logo no celular, onde o trilho não aparece */}
          <div className="rd-so-mobile">
            <img src="/images/quadrante.png" alt="" style={{ height: 30 }} />
            <span style={{ fontWeight: 800, color: 'var(--navy)' }}>
              CONECTA <span style={{ color: 'var(--orange)' }}>PRO</span>
            </span>
          </div>

          <div>
            <div className="rd-page-title" style={{ fontSize: 24 }}>Acessar o sistema</div>
            <div className="rd-page-sub">Entre com suas credenciais</div>
          </div>

          {notice && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--info-bg)', color: 'var(--info)', border: '1px solid #C7D7FE', borderRadius: 10, padding: '10px 12px', fontSize: 12.5, fontWeight: 600 }}>
              <AlertCircle size={16} style={{ flex: 'none' }} /> {notice}
            </div>
          )}

          {displayError && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--error-bg)', color: 'var(--error-strong)', border: '1px solid #FBD5D5', borderRadius: 10, padding: '10px 12px', fontSize: 12.5, fontWeight: 600 }}>
              <AlertCircle size={16} style={{ flex: 'none' }} /> {displayError}
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <Campo
              icone={<Mail size={16} />}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="voce@empresa.com"
              autoComplete="username"
              required
              autoFocus
            />
            <Campo
              icone={<Lock size={16} />}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
            />
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12.5 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 7, color: 'var(--ink-weak)', cursor: 'pointer' }}>
                <input type="checkbox" style={{ accentColor: 'var(--orange)' }} aria-label="Lembrar de mim" /> Lembrar de mim
              </label>
              <Link href="/forgot-password" style={{ fontWeight: 600, color: 'var(--orange-txt)' }}>
                Esqueci minha senha
              </Link>
            </div>
            <Btn variant="primary" type="submit" disabled={isLoading} style={{ width: '100%', height: 44 }}>
              {isLoading ? 'Entrando…' : 'Entrar'}
            </Btn>
          </form>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
            <span style={{ fontSize: 12, color: 'var(--placeholder)', whiteSpace: 'nowrap' }}>ou continue com</span>
            <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
          </div>

          {/* Google — `guardarDestino` segura o destino do link de assinatura na ida ao Google. */}
          <a
            href="/api/v1/auth/google"
            onClick={() => guardarDestino(searchParams.get('redirect'))}
            className="rd-btn rd-btn-outline"
            style={{ width: '100%', height: 44, textDecoration: 'none' }}
          >
            <svg width="18" height="18" viewBox="0 0 18 18">
              <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" />
              <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" />
              <path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" />
              <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" />
            </svg>
            Entrar com Google
          </a>

          {/* Entrar com o rosto — porteiro e ASG entram por aqui, sem digitar nada. */}
          <Btn
            variant="navy"
            type="button"
            onClick={() => { setError(''); setFacialOpen(true); }}
            style={{ width: '100%', height: 44 }}
          >
            <ScanFace size={18} /> Entrar com o rosto
          </Btn>

          <p style={{ textAlign: 'center', fontSize: 12.5, color: 'var(--ink-weak)' }}>
            Funcionário no 1º acesso?{' '}
            <Link href="/primeiro-acesso" style={{ color: 'var(--orange-txt)', fontWeight: 600 }}>
              Cadastre-se aqui
            </Link>
          </p>

          <p style={{ textAlign: 'center', fontSize: 11.5, color: 'var(--placeholder)', lineHeight: 1.6 }}>
            Ao entrar, você concorda com os{' '}
            <a href="/termos" style={{ color: 'var(--orange-txt)', fontWeight: 600 }}>Termos de Uso</a>{' '}
            e{' '}
            <a href="/privacidade" style={{ color: 'var(--orange-txt)', fontWeight: 600 }}>Política de Privacidade</a>
          </p>
        </div>
      </div>

      {/* Modal: login por rosto */}
      {facialOpen && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,.6)', zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
          <div style={{ background: 'var(--surface)', borderRadius: 'var(--r-card)', padding: 20, width: '100%', maxWidth: 400 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--navy)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <ScanFace size={18} /> Entrar com o rosto
              </span>
              <button onClick={() => { setFacialOpen(false); setFacialLoading(false); }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--placeholder)' }} aria-label="Fechar"><X size={20} /></button>
            </div>
            <p style={{ fontSize: 13, color: 'var(--ink-weak)', marginBottom: 12 }}>Olhe pra câmera num lugar iluminado.</p>
            {facialLoading ? (
              <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--ink-weak)' }}>
                <Loader2 size={28} style={{ animation: 'spin 1s linear infinite', margin: '0 auto 8px' }} /> Reconhecendo…
              </div>
            ) : (
              <FacialCapture onCapture={handleFacialLogin} onError={(e) => setError(e)} />
            )}
          </div>
        </div>
      )}

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        .rd-so-mobile { display: none; }
        @media (max-width: 820px) {
          .rd-so-mobile { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
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
