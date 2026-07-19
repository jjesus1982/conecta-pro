'use client';

import { useState } from 'react';
import { Mail, Lock, User, ArrowLeft, Check, AlertCircle } from 'lucide-react';
import { Btn } from '@/components/redesign/shell';

type Mode = 'login' | 'cadastro' | 'recuperar';

const FEATS = [
  'Portaria remota e monitoramento',
  'Escalas, rondas e ponto',
  'Gestão de pessoas e DP',
  'Financeiro, fiscal e jurídico',
];

const rail: React.CSSProperties = {
  width: '42%', background: 'var(--navy)', color: '#fff', display: 'flex',
  flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
  gap: 20, padding: 40, textAlign: 'center',
};
const fieldWrap: React.CSSProperties = { position: 'relative', display: 'flex', alignItems: 'center' };
const iconStyle: React.CSSProperties = { position: 'absolute', left: 12, color: 'var(--placeholder)' };

function Field({ icon, ...p }: { icon: React.ReactNode } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div style={fieldWrap}>
      <span style={iconStyle}>{icon}</span>
      <input className="rd-input" style={{ paddingLeft: 38, width: '100%' }} {...p} />
    </div>
  );
}

export default function RedesignLogin() {
  const [mode, setMode] = useState<Mode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState('');

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setErro('');
    setLoading(true);
    try {
      const body = new URLSearchParams({ username: email.trim(), password });
      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || (res.status === 401 ? 'E-mail ou senha inválidos.' : 'Não foi possível entrar.'));
      }
      const data = await res.json();
      if (!data.access_token) throw new Error('Resposta de login inesperada.');
      localStorage.setItem('access_token', data.access_token);
      if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token);
      const isSecure = window.location.protocol === 'https:';
      document.cookie = `auth_token=${data.access_token}; path=/; max-age=${30 * 60}; SameSite=Lax${isSecure ? '; Secure' : ''}`;
      const redirect = new URLSearchParams(window.location.search).get('redirect') || '/redesign';
      // href (não router.push) garante que o cookie chegue nas próximas requisições
      window.location.href = redirect.startsWith('/redesign') ? redirect : '/redesign';
    } catch (err) {
      setErro(err instanceof Error ? err.message : 'Erro ao entrar.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* Painel navy da marca — fiel ao Telas de Login.dc.html (centralizado) */}
      <div style={rail} className="rd-hide-mobile">
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

      {/* Formulário */}
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
        <div style={{ width: '100%', maxWidth: 380, display: 'flex', flexDirection: 'column', gap: 18 }}>
          {mode === 'login' && (
            <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              <div>
                <div className="rd-page-title" style={{ fontSize: 24 }}>Acessar o sistema</div>
                <div className="rd-page-sub">Entre com suas credenciais</div>
              </div>
              {erro && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--error-bg)', color: 'var(--error-strong)', border: '1px solid #FBD5D5', borderRadius: 10, padding: '10px 12px', fontSize: 12.5, fontWeight: 600 }}>
                  <AlertCircle size={16} /> {erro}
                </div>
              )}
              <Field icon={<Mail size={16} />} type="email" placeholder="voce@empresa.com" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required />
              <Field icon={<Lock size={16} />} type="password" placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12.5 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 7, color: 'var(--ink-weak)', cursor: 'pointer' }}>
                  <input type="checkbox" style={{ accentColor: 'var(--orange)' }} /> Lembrar de mim
                </label>
                <a href="#" onClick={(e) => { e.preventDefault(); setMode('recuperar'); }}>Esqueci minha senha</a>
              </div>
              <Btn variant="primary" type="submit" disabled={loading} style={{ width: '100%', height: 44 }}>
                {loading ? 'Entrando…' : 'Entrar'}
              </Btn>
              <div style={{ textAlign: 'center', fontSize: 12.5, color: 'var(--ink-weak)' }}>
                <a href="/modulos" style={{ color: 'var(--ink-weak)' }}>Voltar ao sistema clássico</a>
              </div>
            </form>
          )}

          {mode === 'cadastro' && (
            <>
              <div>
                <div className="rd-page-title" style={{ fontSize: 24 }}>Criar conta</div>
                <div className="rd-page-sub">O cadastro é feito pelo administrador do sistema.</div>
              </div>
              <Field icon={<User size={16} />} placeholder="Nome completo" />
              <Field icon={<Mail size={16} />} type="email" placeholder="E-mail corporativo" />
              <div style={{ textAlign: 'center', fontSize: 12.5, color: 'var(--ink-weak)' }}>
                Já tem conta? <a href="#" onClick={(e) => { e.preventDefault(); setMode('login'); }}>Entrar</a>
              </div>
            </>
          )}

          {mode === 'recuperar' && (
            <>
              <div>
                <div className="rd-page-title" style={{ fontSize: 24 }}>Recuperar senha</div>
                <div className="rd-page-sub">Fale com o administrador para redefinir sua senha.</div>
              </div>
              <Field icon={<Mail size={16} />} type="email" placeholder="voce@empresa.com" />
              <div style={{ textAlign: 'center' }}>
                <a href="#" onClick={(e) => { e.preventDefault(); setMode('login'); }}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5 }}>
                  <ArrowLeft size={14} /> Voltar ao login
                </a>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
