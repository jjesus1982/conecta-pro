'use client';

import { WifiOff, RefreshCw, Home } from 'lucide-react';
import Link from 'next/link';
;
import { Button } from '@/components/ui/button';

export default function OfflinePage() {
  const handleRetry = () => {
    window.location.reload();
  };

  return (
    <div className="min-h-screen bg-grid flex items-center justify-center p-4">
      <div className="max-w-md w-full text-center">
        <div className="mb-8">
          <div className="w-24 h-24 mx-auto rounded-full bg-orange-500/10 flex items-center justify-center mb-6">
            <WifiOff className="w-12 h-12 text-orange-500" />
          </div>
          <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))] mb-2">
            Voce esta offline
          </h1>
          <p className="text-[hsl(var(--muted-foreground))]">
            Parece que voce perdeu a conexao com a internet.
            Verifique sua conexao e tente novamente.
          </p>
        </div>

        <div className="space-y-3">
          <Button
            onClick={handleRetry}
            className="w-full"
            size="lg"
          >
            <RefreshCw className="w-4 h-4 mr-2" />
            Tentar novamente
          </Button>

          <Link href="/dashboard">
            <Button
              variant="outline"
              className="w-full"
              size="lg"
            >
              <Home className="w-4 h-4 mr-2" />
              Voltar ao Dashboard
            </Button>
          </Link>
        </div>

        <p className="mt-8 text-xs text-[hsl(var(--muted-foreground))]">
          Algumas funcionalidades podem estar disponiveis offline.
        </p>
      </div>
    </div>
  );
}
