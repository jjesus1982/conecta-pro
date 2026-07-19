'use client';

import { Suspense, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

function AuthCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const accessToken = searchParams.get('access_token');
    const refreshToken = searchParams.get('refresh_token');

    if (accessToken && refreshToken) {
      localStorage.setItem('access_token', accessToken);
      localStorage.setItem('refresh_token', refreshToken);
      // Sincronizar cookie p/ o middleware (antes só salvava no localStorage)
      const isSecure = window.location.protocol === 'https:';
      document.cookie = `auth_token=${accessToken}; path=/; max-age=${30 * 60}; SameSite=Lax${isSecure ? '; Secure' : ''}`;
      // Cutover: cai no redesign por padrão (troque por '/dashboard' para reverter)
      router.replace('/redesign');
    } else {
      router.replace('/login?error=no_tokens');
    }
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
