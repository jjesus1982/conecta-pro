'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState, type ReactNode } from 'react';

// Rotas públicas do redesign (não exigem token)
const PUBLIC = ['/redesign/login', '/redesign/splash'];

/**
 * Guard de autenticação do redesign (client-side).
 * Sem token → redireciona para /redesign/login. Torna o /redesign um app gated de verdade,
 * sem depender do middleware server (que segue protegendo só /modulos e /dashboard).
 */
export default function RedesignGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ok, setOk] = useState(false);

  useEffect(() => {
    if (PUBLIC.some((p) => pathname === p || pathname.startsWith(p + '/'))) {
      setOk(true);
      return;
    }
    let tok: string | null = null;
    try { tok = localStorage.getItem('access_token'); } catch { /* */ }
    if (!tok) {
      router.replace(`/redesign/login?redirect=${encodeURIComponent(pathname)}`);
      return;
    }
    setOk(true);
  }, [pathname, router]);

  if (!ok) return null;
  return <>{children}</>;
}
