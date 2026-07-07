'use client';

import { Lock, ArrowLeft, AlertCircle, CheckCircle2 } from 'lucide-react';
import { Suspense, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import api, { getErrorMessage } from '@/lib/api';

function ResetPasswordContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get('token');

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password.length < 8) {
      setError('A senha deve ter no mínimo 8 caracteres');
      return;
    }

    if (password !== confirmPassword) {
      setError('As senhas não coincidem');
      return;
    }

    setIsLoading(true);

    try {
      await api.post('/api/v1/auth/reset-password', {
        token,
        new_password: password,
      });
      setSuccess(true);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-[hsl(var(--background))]">
        <div className="w-full max-w-md text-center space-y-6">
          <div className="flex items-start gap-3 p-4 rounded-lg bg-[hsl(var(--destructive))]/10 border border-[hsl(var(--destructive))]/30 text-[hsl(var(--destructive))]">
            <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-left">
              <p className="font-medium">Link inválido</p>
              <p className="mt-1 opacity-80">
                O link de redefinição de senha é inválido ou expirou.
                Solicite um novo link.
              </p>
            </div>
          </div>
          <Link
            href="/forgot-password"
            className="flex items-center justify-center gap-2 w-full py-3 rounded-lg border border-[hsl(var(--border))] text-[hsl(var(--foreground))] hover:bg-[hsl(var(--accent))] transition-colors text-sm font-medium"
          >
            Solicitar novo link
          </Link>
        </div>
      </div>
    );
  }

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
            Redefinir senha
          </h2>
          <p className="text-[hsl(var(--muted-foreground))] mt-1">
            Escolha uma nova senha para sua conta
          </p>
        </div>

        {success ? (
          <div className="space-y-6">
            <div className="flex items-start gap-3 p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="w-5 h-5 flex-shrink-0 mt-0.5" />
              <div className="text-sm">
                <p className="font-medium">Senha redefinida!</p>
                <p className="mt-1 opacity-80">
                  Sua senha foi alterada com sucesso. Faça login com a nova senha.
                </p>
              </div>
            </div>
            <Link
              href="/login"
              className="flex items-center justify-center gap-2 w-full py-3 rounded-lg btn-brand text-sm font-medium"
            >
              Ir para o login
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
              type="password"
              label="Nova senha"
              placeholder="Mínimo 8 caracteres"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              icon={<Lock className="w-4 h-4" />}
              required
              autoFocus
            />

            <Input
              type="password"
              label="Confirmar nova senha"
              placeholder="Digite a senha novamente"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              icon={<Lock className="w-4 h-4" />}
              required
            />

            <Button
              type="submit"
              className="w-full btn-brand"
              size="lg"
              isLoading={isLoading}
            >
              Redefinir senha
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

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
      </div>
    }>
      <ResetPasswordContent />
    </Suspense>
  );
}
