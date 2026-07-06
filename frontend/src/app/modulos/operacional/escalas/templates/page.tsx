'use client';

import { ArrowLeft, Calendar, Shield } from 'lucide-react';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
;
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { TemplateManager } from '@/features/escalas/components/TemplateManager';
import { useAuth } from '@/hooks/useAuth';

export default function ScaleTemplatesPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();

  // Auth check
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <Shield className="w-12 h-12" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-grid">
      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <PageHeader
          eyebrow="OPERACIONAL · ESCALAS"
          title="Templates de Escalas"
          subtitle="Gerencie templates reutilizáveis"
          icon={<Calendar className="w-5 h-5" />}
          actions={
            <Link href="/modulos/operacional/escalas">
              <Button variant="ghost" size="sm">
                <ArrowLeft className="w-4 h-4 mr-2" />
                Voltar para Escalas
              </Button>
            </Link>
          }
        />
        <TemplateManager />
      </main>
    </div>
  );
}
