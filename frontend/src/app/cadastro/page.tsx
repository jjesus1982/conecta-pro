'use client';

import { AlertCircle, CheckCircle2, Circle, Clock } from 'lucide-react';
import { useMemo, useState } from 'react';
import Link from 'next/link';

// Regras de senha — espelham o validador do backend (core/security/password_validator.py)
const SPECIAL_CHARACTERS = '!@#$%^&*()_+-=[]{}|;:,.<>?/~`';

interface PasswordRule {
  id: string;
  label: string;
  test: (pw: string) => boolean;
}

const PASSWORD_RULES: PasswordRule[] = [
  { id: 'len', label: 'Pelo menos 12 caracteres', test: (pw) => pw.length >= 12 },
  { id: 'upper', label: 'Uma letra maiúscula', test: (pw) => /[A-Z]/.test(pw) },
  { id: 'lower', label: 'Uma letra minúscula', test: (pw) => /[a-z]/.test(pw) },
  { id: 'digit', label: 'Um número', test: (pw) => /\d/.test(pw) },
  {
    id: 'special',
    label: 'Um caractere especial (!@#$%…)',
    test: (pw) => [...pw].some((c) => SPECIAL_CHARACTERS.includes(c)),
  },
];

const inputStyle: React.CSSProperties = {
  width: '100%',
  height: 44,
  border: '1.5px solid #E9ECEF',
  borderRadius: 10,
  padding: '0 14px',
  fontSize: 13.5,
  color: '#111827',
  background: '#F8F9FB',
  outline: 'none',
  fontFamily: 'inherit',
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 12.5,
  fontWeight: 600,
  color: '#374151',
  marginBottom: 7,
};

// Extrai mensagem legível de erro do backend (detail string ou lista pydantic)
function parseApiError(data: unknown): string {
  const detail = (data as { detail?: unknown })?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (typeof d?.msg === 'string' ? d.msg.replace(/^Value error,\s*/i, '') : null))
      .filter(Boolean);
    if (msgs.length > 0) return msgs.join('; ');
  }
  return 'Erro ao criar conta. Tente novamente.';
}

export default function CadastroPage() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  const ruleResults = useMemo(
    () => PASSWORD_RULES.map((r) => ({ ...r, ok: r.test(password) })),
    [password],
  );
  const passwordValid = ruleResults.every((r) => r.ok);
  const confirmValid = confirm.length > 0 && confirm === password;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (name.trim().length < 2) {
      setError('Informe seu nome completo.');
      return;
    }
    if (!passwordValid) {
      setError('A senha não atende aos requisitos mínimos.');
      return;
    }
    if (!confirmValid) {
      setError('As senhas não conferem.');
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch('/api/v1/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          email: email.trim().toLowerCase(),
          password,
          role: 'pending', // backend força 'pending' de qualquer forma
        }),
      });

      if (res.status === 201) {
        setSuccess(true);
        return;
      }

      if (res.status === 429) {
        setError('Muitas tentativas. Aguarde um minuto e tente novamente.');
        return;
      }

      let data: unknown = null;
      try {
        data = await res.json();
      } catch {
        // resposta sem corpo JSON
      }
      setError(parseApiError(data));
    } catch {
      setError('Não foi possível conectar ao servidor. Tente novamente.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: '#1E3A5F', padding: 24 }}>
      <div
        className="w-full bg-white"
        style={{ maxWidth: 460, borderRadius: 18, padding: '40px 42px', boxShadow: '0 24px 60px rgba(0,0,0,0.25)' }}
      >
        {/* Logo / título */}
        <div style={{ marginBottom: 24 }}>
          <div className="flex items-baseline gap-1.5" style={{ fontSize: 18, fontWeight: 800, letterSpacing: '-0.3px' }}>
            <span style={{ color: '#1E3A5F' }}>CONECTA</span>
            <span style={{ color: '#F97316' }}>PRO</span>
          </div>
          {!success && (
            <>
              <h1 style={{ fontSize: 24, fontWeight: 700, color: '#1E3A5F', letterSpacing: '-0.5px', marginTop: 14, marginBottom: 5, lineHeight: 1.2 }}>
                Criar conta
              </h1>
              <p style={{ fontSize: 13.5, color: '#6B7280', lineHeight: 1.5 }}>
                Seu cadastro passa por aprovação de um administrador antes do acesso ser liberado.
              </p>
            </>
          )}
        </div>

        {success ? (
          /* ── Estado de sucesso: aguarde aprovação ── */
          <div className="text-center" style={{ padding: '12px 0 4px' }}>
            <div
              className="mx-auto flex items-center justify-center"
              style={{ width: 64, height: 64, borderRadius: 18, background: 'rgba(245,158,11,0.12)', marginBottom: 18 }}
            >
              <Clock className="w-8 h-8" style={{ color: '#D97706' }} />
            </div>
            <h2 style={{ fontSize: 20, fontWeight: 700, color: '#1E3A5F', marginBottom: 8 }}>
              Cadastro recebido!
            </h2>
            <p style={{ fontSize: 13.5, color: '#6B7280', lineHeight: 1.6, marginBottom: 22 }}>
              Sua conta aguarda aprovação de um administrador. Você poderá entrar assim que o
              acesso for aprovado.
            </p>
            <Link
              href="/login"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '100%',
                height: 46,
                background: '#1E3A5F',
                color: '#fff',
                borderRadius: 10,
                fontSize: 15,
                fontWeight: 600,
                textDecoration: 'none',
              }}
            >
              Ir para o login
            </Link>
          </div>
        ) : (
          <>
            {/* Erro */}
            {error && (
              <div
                className="flex items-center gap-2 p-3 rounded-xl mb-4"
                style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}
              >
                <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-500" />
                <span className="text-sm text-red-600">{error}</span>
              </div>
            )}

            <form onSubmit={handleSubmit}>
              <div style={{ marginBottom: 15 }}>
                <label style={labelStyle}>Nome completo</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Seu nome"
                  required
                  autoFocus
                  minLength={2}
                  maxLength={100}
                  style={inputStyle}
                />
              </div>

              <div style={{ marginBottom: 15 }}>
                <label style={labelStyle}>E-mail</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="seu@email.com"
                  required
                  style={inputStyle}
                />
              </div>

              <div style={{ marginBottom: 10 }}>
                <label style={labelStyle}>Senha</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  required
                  minLength={12}
                  style={inputStyle}
                />
                {/* Checklist de requisitos (espelha o backend) */}
                {password.length > 0 && (
                  <ul style={{ marginTop: 8, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '3px 10px' }}>
                    {ruleResults.map((r) => (
                      <li key={r.id} className="flex items-center gap-1.5" style={{ fontSize: 11.5, color: r.ok ? '#059669' : '#9CA3AF' }}>
                        {r.ok ? (
                          <CheckCircle2 className="w-3 h-3 flex-shrink-0" />
                        ) : (
                          <Circle className="w-3 h-3 flex-shrink-0" />
                        )}
                        {r.label}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div style={{ marginBottom: 18 }}>
                <label style={labelStyle}>Confirmar senha</label>
                <input
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  placeholder="••••••••••••"
                  required
                  style={{
                    ...inputStyle,
                    borderColor: confirm.length > 0 && !confirmValid ? '#FCA5A5' : '#E9ECEF',
                  }}
                />
                {confirm.length > 0 && !confirmValid && (
                  <p style={{ fontSize: 11.5, color: '#DC2626', marginTop: 5 }}>As senhas não conferem</p>
                )}
              </div>

              <button
                type="submit"
                disabled={submitting}
                style={{
                  width: '100%',
                  height: 46,
                  background: submitting ? '#2d5a8f' : '#1E3A5F',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 10,
                  fontSize: 15,
                  fontWeight: 600,
                  cursor: submitting ? 'wait' : 'pointer',
                  fontFamily: 'inherit',
                  transition: 'background .15s',
                }}
              >
                {submitting ? 'Enviando…' : 'Criar conta'}
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
              Cadastrar com Google
            </a>

            {/* Voltar ao login */}
            <p style={{ marginTop: 18, textAlign: 'center', fontSize: 13, color: '#6B7280' }}>
              Já tem conta?{' '}
              <Link href="/login" style={{ color: '#F97316', fontWeight: 600, textDecoration: 'none' }}>
                Entrar
              </Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
