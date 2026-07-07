'use client';

import { Mail, ArrowLeft, AlertCircle, CheckCircle2 } from 'lucide-react';
import { useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import api, { getErrorMessage } from '@/lib/api';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await api.post('/api/v1/auth/forgot-password', { email });
      setSuccess(true);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-[hsl(var(--background))]">
      <div className="w-full max-w-md animate-fade-in">
        {/* Logo */}
        <div className="text-center mb-8">
          <Image
            src="/images/logo-original.png"
            alt="Conecta Mais"
            width={140}
            height={140}
            className="mx-auto"
            priority
          />
        </div>

        {/* Header */}
        <div className="text-center mb-8">
          <h2 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">
            Esqueceu a senha?
          </h2>
          <p className="text-[hsl(var(--muted-foreground))] mt-1">
            Informe seu e-mail e enviaremos instruções para redefinir sua senha
          </p>
        </div>

        {success ? (
          <div className="space-y-6">
            <div className="flex items-start gap-3 p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="w-5 h-5 flex-shrink-0 mt-0.5" />
              <div className="text-sm">
                <p className="font-medium">E-mail enviado!</p>
                <p className="mt-1 opacity-80">
                  Se o e-mail <strong>{email}</strong> estiver cadastrado, você receberá
                  as instruções de recuperação em alguns minutos.
                </p>
              </div>
            </div>
            <Link
              href="/login"
              className="flex items-center justify-center gap-2 w-full py-3 rounded-lg border border-[hsl(var(--border))] text-[hsl(var(--foreground))] hover:bg-[hsl(var(--accent))] transition-colors text-sm font-medium"
            >
              <ArrowLeft className="w-4 h-4" />
              Voltar para o login
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5">
            {error && (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-[hsl(var(--destructive))]/10 border border-[hsl(var(--destructive))]/30 text-[hsl(var(--destructive))] animate-slide-up">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span className="text-sm">{error}</span>
              </div>
            )}

            <Input
              type="email"
              label="E-mail"
              placeholder="seu@email.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              icon={<Mail className="w-4 h-4" />}
              required
              autoFocus
            />

            <Button
              type="submit"
              className="w-full btn-brand"
              size="lg"
              isLoading={isLoading}
            >
              Enviar instruções
            </Button>

            <Link
              href="/login"
              className="flex items-center justify-center gap-2 w-full py-3 rounded-lg text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] transition-colors text-sm"
            >
              <ArrowLeft className="w-4 h-4" />
              Voltar para o login
            </Link>
          </form>
        )}
      </div>
    </div>
  );
}
