'use client';

import { ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface PageHeaderProps {
  /** Título da página (renderizado em Space Grotesk / font-display) */
  title: string;
  /** Subtítulo/descrição curta abaixo do título */
  subtitle?: string;
  /** Rótulo pequeno acima do título (ex.: "FINANCEIRO · CONTAS A PAGAR") */
  eyebrow?: string;
  /** Ícone opcional à esquerda do título */
  icon?: ReactNode;
  /** Ações à direita (botões, filtros) */
  actions?: ReactNode;
  className?: string;
}

/**
 * Cabeçalho de página padronizado do Conecta PRO.
 * Título em font-display, rótulo (eyebrow) em font-data — mesma identidade da home.
 * Substitui os <h1 className="text-2xl font-bold"> inline espalhados pelas telas.
 */
export function PageHeader({ title, subtitle, eyebrow, icon, actions, className }: PageHeaderProps) {
  return (
    <div className={cn('flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5', className)}>
      <div className="flex items-center gap-3 min-w-0">
        {icon && (
          <div className="w-9 h-9 rounded-lg bg-brand-500/10 flex items-center justify-center flex-shrink-0 text-brand-500">
            {icon}
          </div>
        )}
        <div className="min-w-0">
          {eyebrow && (
            <p className="font-data text-[10px] uppercase tracking-[0.18em] text-[hsl(var(--muted-foreground))]/70 mb-0.5">
              {eyebrow}
            </p>
          )}
          <h1 className="font-display text-xl sm:text-2xl font-semibold text-[hsl(var(--foreground))] tracking-tight leading-tight truncate">
            {title}
          </h1>
          {subtitle && (
            <p className="text-sm text-[hsl(var(--muted-foreground))] mt-0.5 line-clamp-1">{subtitle}</p>
          )}
        </div>
      </div>
      {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
    </div>
  );
}

export default PageHeader;
