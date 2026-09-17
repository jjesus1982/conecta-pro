'use client';

import { Suspense, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { destinoPosLogin, resgatarDestino } from '@/lib/destino-pos-login';

function AuthCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const accessToken = searchParams.get('access_token');
    const refreshToken = searchParams.get('refresh_token');

    if (!accessToken || !refreshToken) {
      router.replace('/login?error=no_tokens');
      return;
    }

    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('refresh_token', refreshToken);
    // Sincronizar cookie p/ o middleware (antes só salvava no localStorage)
    const isSecure = window.location.protocol === 'https:';
    document.cookie = `auth_token=${accessToken}; path=/; max-age=${30 * 60}; SameSite=Lax${isSecure ? '; Secure' : ''}`;

    // Este era o furo: até 17/09/2026 esta linha era `router.replace('/redesign')` fixo.
    // O link de assinatura chegava aqui como ?redirect= no /login, a pessoa clicava em
    // "Entrar com Google" — o caminho que o próprio aviso manda usar — e o destino era
    // jogado fora. O destino guardado antes da ida vence; sem ele, manda pelo papel.
    const guardado = resgatarDestino();
    if (guardado) {
      router.replace(guardado);
      return;
    }

    let vivo = true;
    fetch('/api/v1/auth/me', { headers: { Authorization: `Bearer ${accessToken}` } })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then((u) => {
        if (vivo) router.replace(destinoPosLogin(null, u?.role));
      });
    return () => {
      vivo = false;
    };
  }, [searchParams, router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
      <div className="text-center space-y-4">
        <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-[hsl(var(--muted-foreground))] text-sm">
          Autenticando...
        </p>
      </div>
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
      </div>
    }>
      <AuthCallbackContent />
    </Suspense>
  );
}
