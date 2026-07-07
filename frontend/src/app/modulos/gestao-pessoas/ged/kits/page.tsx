'use client';

// A antiga "Kits Documentais" (completude via banco, mostrava 0.0%) foi substituída pela
// dashboard real de completude (lê o Google Drive). Redireciona pra evitar confusão.
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';

export default function KitsRedirectPage() {
  const router = useRouter();
  useEffect(() => { router.replace('/modulos/gestao-pessoas/ged'); }, [router]);
  return (
    <div className="flex items-center justify-center h-96 text-[hsl(var(--muted-foreground))]">
      <Loader2 className="w-5 h-5 animate-spin mr-2" /> Abrindo os kits…
    </div>
  );
}
