'use client';

import { Users, TrendingUp, TrendingDown, AlertCircle } from 'lucide-react';

interface PostCoverageCardProps {
  postName: string;
  postCode?: string;
  activeAllocations: number;
  /** @deprecated usar requiredHeadcount — mantido p/ compatibilidade */
  totalAllocations: number;
  /** Quadro ideal do posto (required_headcount do backend) — denominador honesto */
  requiredHeadcount?: number;
  coverageRate: number; // 0-100
  onClick?: () => void;
}

function getCoverageColor(rate: number) {
  if (rate >= 100) return 'green';
  if (rate >= 80) return 'yellow';
  return 'red';
}

export function PostCoverageCard({
  postName,
  postCode,
  activeAllocations,
  totalAllocations,
  requiredHeadcount,
  coverageRate,
  onClick,
}: PostCoverageCardProps) {
  const color = getCoverageColor(coverageRate);

  const colorMap = {
    green: {
      text: 'text-green-500',
      bg: 'bg-green-500',
      border: 'border-green-500/30',
      dot: 'bg-green-500',
      dotPulse: '',
      icon: TrendingUp,
      iconBg: 'bg-green-500/10',
    },
    yellow: {
      text: 'text-yellow-500',
      bg: 'bg-yellow-500',
      border: 'border-yellow-500/30',
      dot: 'bg-yellow-500',
      dotPulse: '',
      icon: TrendingUp,
      iconBg: 'bg-yellow-500/10',
    },
    red: {
      text: 'text-red-500',
      bg: 'bg-red-500',
      border: 'border-red-500/30',
      dot: 'bg-red-500 animate-pulse',
      dotPulse: 'animate-pulse',
      icon: TrendingDown,
      iconBg: 'bg-red-500/10',
    },
  };

  const c = colorMap[color];
  const Icon = c.icon;
  const displayRate = Math.min(coverageRate, 100);

  return (
    <div
      className={`bg-[hsl(var(--card))] border ${c.border} rounded-xl p-4 transition-all hover:shadow-md ${
        onClick ? 'cursor-pointer hover:scale-[1.01]' : ''
      }`}
      onClick={onClick}
    >
      {/* Header row */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${c.dot}`} />
          <div className="min-w-0">
            <p className="font-semibold text-[hsl(var(--foreground))] text-sm leading-tight truncate">
              {postName}
            </p>
            {postCode && (
              <p className="text-xs text-[hsl(var(--muted-foreground))] truncate">
                {postCode}
              </p>
            )}
          </div>
        </div>
        <div className={`flex-shrink-0 w-8 h-8 rounded-lg ${c.iconBg} flex items-center justify-center ml-2`}>
          {color === 'red' ? (
            <AlertCircle className={`w-4 h-4 ${c.text}`} />
          ) : (
            <Icon className={`w-4 h-4 ${c.text}`} />
          )}
        </div>
      </div>

      {/* Coverage percentage */}
      <div className="mb-3">
        <span className={`font-data text-3xl font-semibold tabular-nums ${c.text}`}>
          {coverageRate.toFixed(0)}
          <span className="text-lg font-semibold">%</span>
        </span>
      </div>

      {/* Progress bar */}
      <div className="mb-2">
        <div className="h-2 bg-[hsl(var(--muted))] rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${c.bg}`}
            style={{ width: `${displayRate}%` }}
          />
        </div>
      </div>

      {/* Efetivo vs quadro ideal: ativos/required_headcount (não ativos/alocações) */}
      <div className="flex items-center gap-1.5 text-xs text-[hsl(var(--muted-foreground))]">
        <Users className="w-3.5 h-3.5" />
        <span>
          <span className={`font-medium ${c.text}`}>{activeAllocations}</span>
          <span>
            /{requiredHeadcount ?? totalAllocations}
            {requiredHeadcount != null ? ' do quadro ideal' : ' alocações'}
          </span>
        </span>
      </div>
    </div>
  );
}
