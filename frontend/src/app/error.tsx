'use client';

import { useEffect } from 'react';
import { AlertCircle, RotateCcw, Home } from 'lucide-react';

const isChunkError = (err: Error) =>
  err.name === 'ChunkLoadError' ||
  err.message?.includes('Loading chunk') ||
  err.message?.includes('Failed to load chunk') ||
  err.message?.includes('ChunkLoadError');

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    if (process.env.NODE_ENV === 'production') {
      console.error('[ErrorBoundary]', error);
    }
    // ChunkLoadError: chunk do build anterior — recarregar UMA VEZ para buscar novo HTML
    // Proteção anti-loop: só recarrega se ainda não tentou nos últimos 10s
    if (isChunkError(error)) {
      const RELOAD_KEY = 'chunk_error_reload_ts';
      const last = parseInt(sessionStorage.getItem(RELOAD_KEY) || '0', 10);
      if (Date.now() - last > 10000) {
        sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
        window.location.reload();
      }
      // Se já recarregou recentemente, deixa mostrar a mensagem de erro
    }
  }, [error]);

  const handleRetry = () => {
    if (isChunkError(error)) {
      sessionStorage.removeItem('chunk_error_reload_ts');
      window.location.reload();
    } else {
      reset();
    }
  };

  return (
    <div className="min-h-[60vh] flex items-center justify-center p-6">
      <div className="max-w-md w-full text-center space-y-6">
        <div className="mx-auto w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center">
          <AlertCircle className="w-8 h-8 text-red-500" />
        </div>

        <div className="space-y-2">
          <h2 className="text-xl font-semibold text-[hsl(var(--foreground))]">
            Algo deu errado
          </h2>
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            {isChunkError(error)
              ? 'Nova versao detectada. Recarregando...'
              : 'Ocorreu um erro inesperado. Tente novamente ou volte para o inicio.'}
          </p>
          {error.digest && (
            <p className="text-xs text-[hsl(var(--muted-foreground))] font-mono">
              Codigo: {error.digest}
            </p>
          )}
        </div>

        <div className="flex items-center justify-center gap-3">
          <button
            onClick={handleRetry}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 transition-opacity"
          >
            <RotateCcw className="w-4 h-4" />
            Tentar novamente
          </button>
          <a
            href="/redesign"
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border border-[hsl(var(--border))] text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))] transition-colors"
          >
            <Home className="w-4 h-4" />
            Ir para o inicio
          </a>
        </div>
      </div>
    </div>
  );
}
