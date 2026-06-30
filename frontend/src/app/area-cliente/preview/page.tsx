'use client';

import { Suspense, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Loader2 } from 'lucide-react';

function PreviewInner() {
  const router = useRouter();
  const sp = useSearchParams();

  useEffect(() => {
    const t = sp.get('t');
    const n = sp.get('n');
    if (t) {
      localStorage.setItem('portal_token', t);
      if (n) localStorage.setItem('portal_client_name', n);
      localStorage.setItem('portal_preview', '1');
      router.replace('/area-cliente');
    } else {
      router.replace('/area-cliente/login');
    }
  }, [sp, router]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center text-gray-500">
      <Loader2 className="w-8 h-8 animate-spin text-indigo-600 mb-3" />
      <p className="text-sm">Abrindo o portal como cliente (modo administrador)…</p>
    </div>
  );
}

export default function PreviewPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-indigo-600" /></div>}>
      <PreviewInner />
    </Suspense>
  );
}
