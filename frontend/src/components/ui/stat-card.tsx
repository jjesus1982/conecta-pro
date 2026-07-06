'use client';

import { ReactNode } from 'react';
import { ChevronRight, TrendingUp, TrendingDown } from 'lucide-react';
import { cn } from '@/lib/utils';

interface StatCardProps {
  /** Ícone (elemento lucide, ex.: <Users className="w-4 h-4" />) */
  icon?: ReactNode;
  /** Rótulo do indicador */
  label: string;
  /** Valor principal — renderizado em IBM Plex Mono / font-data, tabular */
  value: ReactNode;
  /** Texto de apoio abaixo do valor */
  sub?: string;
  /** Cor de destaque (hex) do ícone/quadrinho */
  color?: string;
  /** Variação percentual (opcional): positivo = verde, negativo = vermelho */
  change?: number;
  /** Torna o card clicável e mostra a seta */
  onClick?: () => void;
  /** Estado de carregamento */
  loading?: boolean;
  className?: string;
}

/**
 * Card de estatística padrão do Conecta PRO — número em fonte mono (cara de central),
 * card compacto (rounded-xl p-3.5), sem o clichê "número gigante com gradiente".
 * Substitui os <p className="text-2xl/3xl font-bold"> inline dos stat cards.
 */
export function StatCard({
  icon, label, value, sub, color = '#f97707', change, onClick, loading, className,
}: StatCardProps) {
  const clickable = typeof onClick === 'function';
  const Tag: 'button' | 'div' = clickable ? 'button' : 'div';
  const changeColor = change === undefined ? '' : change >= 0 ? 'text-emerald-500' : 'text-red-500';
  const TrendIcon = change !== undefined && change >= 0 ? TrendingUp : TrendingDown;

  return (
    <Tag
      onClick={onClick}
      className={cn(
        'group text-left w-full bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-3.5 transition-colors duration-200',
        clickable && 'cursor-pointer hover:border-[hsl(var(--primary))]/40 hover:shadow-md',
        className
      )}
    >
      <div className="flex items-start justify-between">
        {icon ? (
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${color}1a`, color }}>
            {icon}
          </div>
        ) : <span />}
        {change !== undefined ? (
          <span className={cn('flex items-center gap-0.5 text-xs font-medium', changeColor)}>
            <TrendIcon className="w-3.5 h-3.5" />{Math.abs(change)}%
          </span>
        ) : clickable ? (
          <ChevronRight className="w-4 h-4 text-[hsl(var(--muted-foreground))]/40 group-hover:translate-x-0.5 transition-transform" />
        ) : null}
      </div>
      {loading ? (
        <div className="mt-3 h-7 w-14 rounded animate-shimmer" />
      ) : (
        <p className="mt-2.5 font-data text-2xl font-semibold text-[hsl(var(--foreground))] leading-none tabular-nums">
          {value}
        </p>
      )}
      <p className="mt-1.5 text-xs font-medium text-[hsl(var(--foreground))]/80">{label}</p>
      {sub && <p className="text-[11px] text-[hsl(var(--muted-foreground))]">{sub}</p>}
    </Tag>
  );
}

export default StatCard;
