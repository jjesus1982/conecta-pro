'use client';

import { useState } from 'react';
import { Mail, Lock, User, ArrowLeft, Shield } from 'lucide-react';
import { Btn } from '@/components/redesign/shell';

type Mode = 'login' | 'cadastro' | 'recuperar';

const rail: React.CSSProperties = {
  width: '42%', background: 'var(--navy)', color: '#fff', display: 'flex',
  flexDirection: 'column', justifyContent: 'center', gap: 18, padding: '0 56px',
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

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* Painel navy da marca */}
      <div style={rail} className="rd-hide-mobile">
        <div className="rd-brand-mark" style={{ width: 52, height: 52, borderRadius: 14, fontSize: 22 }}>C</div>
        <div>
          <div style={{ fontSize: 30, fontWeight: 800, letterSpacing: '-0.02em' }}>CONECTA PRO</div>
          <div style={{ fontSize: 12, color: '#9DB0D9', fontWeight: 600, letterSpacing: '0.08em' }}>BY CONECTA MAIS ®</div>
        </div>
        <div style={{ fontSize: 15, color: '#C7D2EC', lineHeight: 1.5, maxWidth: 320 }}>
          Sistema de gestão para segurança patrimonial — operacional, RH, financeiro e fiscal num só lugar.
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#9DB0D9', fontSize: 12.5, marginTop: 6 }}>
          <Shield size={16} /> Vigilância · Portaria · Compliance
        </div>
      </div>

      {/* Formulário */}
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
        <div style={{ width: '100%', maxWidth: 380, display: 'flex', flexDirection: 'column', gap: 18 }}>
          {mode === 'login' && (
            <>
              <div>
                <div className="rd-page-title" style={{ fontSize: 24 }}>Acessar o sistema</div>
                <div className="rd-page-sub">Entre com suas credenciais</div>
              </div>
              <Field icon={<Mail size={16} />} type="email" placeholder="voce@empresa.com" />
              <Field icon={<Lock size={16} />} type="password" placeholder="••••••••" />
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12.5 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 7, color: 'var(--ink-weak)', cursor: 'pointer' }}>
                  <input type="checkbox" style={{ accentColor: 'var(--orange)' }} /> Lembrar de mim
                </label>
                <a href="#" onClick={(e) => { e.preventDefault(); setMode('recuperar'); }}>Esqueci minha senha</a>
              </div>
              <Btn variant="primary" style={{ width: '100%', height: 44 }}>Entrar</Btn>
              <div style={{ textAlign: 'center', fontSize: 12.5, color: 'var(--ink-weak)' }}>
                Não tem conta? <a href="#" onClick={(e) => { e.preventDefault(); setMode('cadastro'); }}>Cadastre-se</a>
              </div>
            </>
          )}

          {mode === 'cadastro' && (
            <>
              <div>
                <div className="rd-page-title" style={{ fontSize: 24 }}>Criar conta</div>
                <div className="rd-page-sub">Preencha seus dados para começar</div>
              </div>
              <Field icon={<User size={16} />} placeholder="Nome completo" />
              <Field icon={<Mail size={16} />} type="email" placeholder="E-mail corporativo" />
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <Field icon={<Lock size={16} />} type="password" placeholder="Senha" />
                <Field icon={<Lock size={16} />} type="password" placeholder="Confirmar" />
              </div>
              <Btn variant="primary" style={{ width: '100%', height: 44 }}>Criar conta</Btn>
              <div style={{ textAlign: 'center', fontSize: 12.5, color: 'var(--ink-weak)' }}>
                Já tem conta? <a href="#" onClick={(e) => { e.preventDefault(); setMode('login'); }}>Entrar</a>
              </div>
            </>
          )}

          {mode === 'recuperar' && (
            <>
              <div>
                <div className="rd-page-title" style={{ fontSize: 24 }}>Recuperar senha</div>
                <div className="rd-page-sub">Enviaremos um link de redefinição para seu e-mail</div>
              </div>
              <Field icon={<Mail size={16} />} type="email" placeholder="voce@empresa.com" />
              <Btn variant="primary" style={{ width: '100%', height: 44 }}>Enviar link</Btn>
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
