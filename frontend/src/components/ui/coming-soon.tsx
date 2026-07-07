'use client';

;
import { Construction, ArrowLeft } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { Button } from './button';

interface ComingSoonProps {
  title: string;
  description?: string;
  moduleHref?: string;
}

export function ComingSoon({ title, description, moduleHref }: ComingSoonProps) {
  const router = useRouter();

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <div className="w-20 h-20 rounded-2xl bg-brand-500/10 flex items-center justify-center mb-6">
        <Construction className="w-10 h-10 text-brand-500" />
      </div>

      <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))] mb-2">
        {title}
      </h1>

      <p className="text-[hsl(var(--muted-foreground))] max-w-md mb-8">
        {description || 'Este módulo está em desenvolvimento e estará disponível em breve.'}
      </p>

      <div className="flex gap-3">
        {moduleHref && (
          <Button
            variant="outline"
            onClick={() => router.push(moduleHref)}
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Voltar ao Módulo
          </Button>
        )}
        <Button
          variant="primary"
          onClick={() => router.push('/dashboard')}
        >
          Ir para Dashboard
        </Button>
      </div>
    </div>
  );
}
