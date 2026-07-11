'use client';

// PORTAL DO FUNCIONARIO ANTIGO (login por CPF) — DESCONTINUADO.
// A entrada oficial agora e o login Google -> aprovacao -> Meu Espaco.
// Esta pagina apenas redireciona para o login principal com um aviso.

import { useEffect } from 'react';
import { Loader2, ShieldCheck } from 'lucide-react';

export default function PortalLoginRedirect() {
  useEffect(() => {
    window.location.replace('/login?notice=portal');
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-6">
      <div className="text-center max-w-md">
        <ShieldCheck className="w-12 h-12 text-[#0A2540] mx-auto mb-4" />
        <h2 className="font-display text-2xl font-bold text-gray-900 mb-2">Portal atualizado</h2>
        <p className="text-gray-500 mb-4">
          Entre com sua conta Google. Redirecionando para o login...
        </p>
        <Loader2 className="w-5 h-5 animate-spin text-[#0A2540] mx-auto" />
      </div>
    </div>
  );
}
