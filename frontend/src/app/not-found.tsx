import { ShieldOff } from 'lucide-react';
import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))] p-6">
      <div className="max-w-md w-full text-center space-y-8">
        {/* Logo / Brand */}
        <div className="space-y-2">
          <div className="mx-auto w-20 h-20 rounded-2xl bg-[hsl(var(--primary))]/10 flex items-center justify-center">
            <ShieldOff className="w-10 h-10 text-[hsl(var(--primary))]" />
          </div>
          <p className="text-sm font-medium text-[hsl(var(--primary))] tracking-wider uppercase">
            Conecta PRO
          </p>
        </div>

        {/* 404 */}
        <div className="space-y-3">
          <h1 className="text-7xl font-bold text-[hsl(var(--foreground))]">404</h1>
          <h2 className="text-xl font-semibold text-[hsl(var(--foreground))]">
            Página não encontrada
          </h2>
          <p className="text-sm text-[hsl(var(--muted-foreground))] leading-relaxed">
            A página que você está procurando não existe, foi movida ou você não tem permissão
            para acessá-la.
          </p>
        </div>

        {/* Actions */}
        {/* A raiz `/` redireciona para /redesign — a casa do sistema é o redesign.
            Este botão mandava para /dashboard (clássico), então quem caía num 404
            era jogado na geração antiga sem pedir. Duas portas dizendo casas
            diferentes é a inconsistência; a raiz decide. */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <Link
            href="/redesign"
            className="inline-flex items-center gap-2 px-6 py-2.5 text-sm font-medium rounded-lg bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 transition-opacity"
          >
            Ir para o início
          </Link>
          <Link
            href="/login"
            className="inline-flex items-center gap-2 px-6 py-2.5 text-sm font-medium rounded-lg border border-[hsl(var(--border))] text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))] transition-colors"
          >
            Fazer Login
          </Link>
        </div>

        {/* Footer */}
        <p className="text-xs text-[hsl(var(--muted-foreground))]">
          Sistema ERP para Gestão de Vigilância e Segurança Patrimonial
        </p>
      </div>
    </div>
  );
}
