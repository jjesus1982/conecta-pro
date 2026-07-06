'use client';

import { LucideIcon, TrendingUp, TrendingDown } from 'lucide-react';
import React from 'react';
;
import { Sparkline } from './sparkline';

interface KPIWidgetProps {
  title: string;
  value: string | number;
  change?: number;
  changeType?: 'positive' | 'negative' | 'neutral';
  icon: LucideIcon;
  iconColor: string;
  iconBgColor: string;
  onClick?: () => void;
  sparklineData?: number[];
  sparklineColor?: string;
  isLoading?: boolean;
}

export function KPIWidget({
  title,
  value,
  change,
  changeType = 'neutral',
  icon: Icon,
  iconColor,
  iconBgColor,
  onClick,
  sparklineData,
  sparklineColor,
  isLoading = false,
}: KPIWidgetProps) {
  const changeColor = {
    positive: 'text-green-500',
    negative: 'text-red-500',
    neutral: 'text-gray-500',
  }[changeType];

  const TrendIcon = changeType === 'positive' ? TrendingUp : TrendingDown;

  if (isLoading) {
    return (
      <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 animate-pulse">
        <div className="flex items-start justify-between mb-2">
          <div className={`w-10 h-10 rounded-lg ${iconBgColor}`} />
        </div>
        <div className="h-8 bg-gray-200 rounded w-20 mb-2" />
        <div className="h-4 bg-gray-200 rounded w-32" />
      </div>
    );
  }

  return (
    <div
      onClick={onClick}
      className={`
        bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4
        transition-all duration-200
        ${onClick ? 'cursor-pointer hover:border-[hsl(var(--primary))]/40 hover:shadow-md' : ''}
      `}
    >
      <div className="flex items-start justify-between mb-2">
        <div className={`w-10 h-10 rounded-lg ${iconBgColor} flex items-center justify-center`}>
          <Icon className={`w-5 h-5 ${iconColor}`} />
        </div>
        {change !== undefined && (
          <div className={`flex items-center gap-1 ${changeColor}`}>
            <TrendIcon className="w-4 h-4" />
            <span className="text-xs font-medium">{Math.abs(change)}%</span>
          </div>
        )}
      </div>

      <p className="font-data text-2xl font-semibold text-[hsl(var(--foreground))] mb-1 tabular-nums">
        {value}
      </p>

      <p className="text-xs text-[hsl(var(--muted-foreground))] mb-2">
        {title}
      </p>

      {sparklineData && sparklineData.length > 0 && (
        <div className="mt-3 -mb-2 -mx-2">
          <Sparkline
            data={sparklineData}
            color={sparklineColor || iconColor.replace('text-', '#')}
            height={30}
          />
        </div>
      )}
    </div>
  );
}

export function KPIWidgetSkeleton() {
  return (
    <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 animate-pulse">
      <div className="flex items-start justify-between mb-2">
        <div className="w-10 h-10 rounded-lg bg-gray-200" />
      </div>
      <div className="h-8 bg-gray-200 rounded w-20 mb-2" />
      <div className="h-4 bg-gray-200 rounded w-32 mb-2" />
      <div className="h-8 bg-gray-200 rounded w-full mt-3" />
    </div>
  );
}
