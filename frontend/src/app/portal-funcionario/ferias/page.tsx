'use client';

// PORTAL DO FUNCIONARIO ANTIGO — DESCONTINUADO.
// A experiencia oficial agora e o "Meu Espaco" (login Google).
// Esta pagina apenas redireciona para /modulos/meu-espaco.
// (Se nao autenticado, o middleware envia para /login automaticamente.)

import { useEffect } from 'react';
import { Loader2, ShieldCheck } from 'lucide-react';

export default function PortalFuncionarioRedirect() {
  useEffect(() => {
    window.location.replace('/modulos/meu-espaco');
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-6">
      <div className="text-center max-w-md">
        <ShieldCheck className="w-12 h-12 text-[#0A2540] mx-auto mb-4" />
        <h2 className="font-display text-2xl font-bold text-gray-900 mb-2">Portal atualizado</h2>
        <p className="text-gray-500 mb-4">
          Sua area agora e o Meu Espaco. Redirecionando...
        </p>
        <Loader2 className="w-5 h-5 animate-spin text-[#0A2540] mx-auto" />
      </div>
    </div>
  );
}
