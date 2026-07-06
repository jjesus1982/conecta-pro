'use client';

import { useRouter } from 'next/navigation';
import { cn } from '@/lib/utils';
import { ElementType } from 'react';

export interface ModuleCardProps {
  id: string;
  title: string;
  description: string;
  icon: ElementType;
  href: string;
  color: 'cyan' | 'green' | 'orange' | 'purple' | 'red' | 'blue' | 'yellow' | 'pink' | 'teal' | 'amber';
  badge?: string | number;
  disabled?: boolean;
  external?: boolean;
}

const colorMap = {
  cyan: {
    bg: 'bg-cyan-500/10',
    border: 'border-cyan-500/30',
    text: 'text-cyan-400',
    glow: 'hover:shadow-cyan-500/20',
    iconBg: 'bg-cyan-500/20',
  },
  green: {
    bg: 'bg-emerald-500/10',
    border: 'border-emerald-500/30',
    text: 'text-emerald-400',
    glow: 'hover:shadow-emerald-500/20',
    iconBg: 'bg-emerald-500/20',
  },
  orange: {
    bg: 'bg-orange-500/10',
    border: 'border-orange-500/30',
    text: 'text-orange-400',
    glow: 'hover:shadow-orange-500/20',
    iconBg: 'bg-orange-500/20',
  },
  purple: {
    bg: 'bg-purple-500/10',
    border: 'border-purple-500/30',
    text: 'text-purple-400',
    glow: 'hover:shadow-purple-500/20',
    iconBg: 'bg-purple-500/20',
  },
  red: {
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
    text: 'text-red-400',
    glow: 'hover:shadow-red-500/20',
    iconBg: 'bg-red-500/20',
  },
  blue: {
    bg: 'bg-blue-500/10',
    border: 'border-blue-500/30',
    text: 'text-blue-400',
    glow: 'hover:shadow-blue-500/20',
    iconBg: 'bg-blue-500/20',
  },
  yellow: {
    bg: 'bg-yellow-500/10',
    border: 'border-yellow-500/30',
    text: 'text-yellow-400',
    glow: 'hover:shadow-yellow-500/20',
    iconBg: 'bg-yellow-500/20',
  },
  pink: {
    bg: 'bg-pink-500/10',
    border: 'border-pink-500/30',
    text: 'text-pink-400',
    glow: 'hover:shadow-pink-500/20',
    iconBg: 'bg-pink-500/20',
  },
  teal: {
    bg: 'bg-teal-500/10',
    border: 'border-teal-500/30',
    text: 'text-teal-400',
    glow: 'hover:shadow-teal-500/20',
    iconBg: 'bg-teal-500/20',
  },
  amber: {
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/30',
    text: 'text-amber-400',
    glow: 'hover:shadow-amber-500/20',
    iconBg: 'bg-amber-500/20',
  },
};

export function ModuleCard({
  title,
  description,
  icon: Icon,
  href,
  color,
  badge,
  disabled,
  external,
}: ModuleCardProps) {
  const router = useRouter();
  const colors = colorMap[color] || colorMap.cyan;

  const handleClick = () => {
    if (!disabled) {
      if (external) {
        window.open(href, '_blank', 'noopener,noreferrer');
      } else {
        router.push(href);
      }
    }
  };

  return (
    <div
      onClick={handleClick}
      className={cn(
        `group relative overflow-hidden rounded-xl border p-4
        transition-all duration-200 cursor-pointer
        bg-[hsl(var(--card))]`,
        colors.border,
        !disabled && 'hover:shadow-md hover:border-opacity-60',
        disabled && 'opacity-50 cursor-not-allowed'
      )}
    >
      {/* Background gradient on hover */}
      <div
        className={cn(
          'absolute inset-0 opacity-0 transition-opacity duration-300',
          colors.bg,
          !disabled && 'group-hover:opacity-100'
        )}
      />

      {/* Content */}
      <div className="relative z-10">
        {/* Header com ícone e badge */}
        <div className="flex items-start justify-between mb-4">
          <div
            className={cn(
              'w-10 h-10 rounded-lg flex items-center justify-center',
              colors.iconBg
            )}
          >
            <Icon className={cn('w-5 h-5', colors.text)} />
          </div>

          {badge !== undefined && (
            <span
              className={cn(
                'px-2 py-0.5 text-xs font-medium rounded-full',
                colors.bg,
                colors.text
              )}
            >
              {badge}
            </span>
          )}
        </div>

        {/* Título e descrição */}
        <h3 className="font-display text-[15px] font-semibold text-[hsl(var(--foreground))] mb-1">
          {title}
        </h3>
        <p className="text-sm text-[hsl(var(--muted-foreground))] line-clamp-2">
          {description}
        </p>

        {/* Arrow indicator */}
        <div
          className={cn(
            'absolute bottom-5 right-5 opacity-0 transform translate-x-2',
            'transition-all duration-300',
            !disabled && 'group-hover:opacity-100 group-hover:translate-x-0',
            colors.text
          )}
        >
          <svg
            className="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M17 8l4 4m0 0l-4 4m4-4H3"
            />
          </svg>
        </div>
      </div>
    </div>
  );
}
