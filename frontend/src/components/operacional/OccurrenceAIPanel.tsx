'use client';

import { useMemo } from 'react';
import { Sparkles, TrendingUp, AlertTriangle, CheckCircle, Clock, Info } from 'lucide-react';

interface OccurrenceAIPanelProps {
  stats: {
    total?: number;
    pending_resolution?: number;
    resolved_this_month?: number;
    avg_resolution_time_hours?: number;
    by_severity?: Record<string, number>;
    by_category?: Record<string, number>;
    by_type?: Record<string, number>;
  } | null;
  occurrences: Array<{
    category: string;
    severity: string;
    status: string;
  }>;
}

const CATEGORY_LABELS: Record<string, string> = {
  disciplinar: 'Disciplinar',
  seguranca: 'Segurança',
  operacional: 'Operacional',
  administrativa: 'Administrativa',
  tecnica: 'Técnica',
};

const SEVERITY_LABELS: Record<string, string> = {
  leve: 'Leve',
  moderada: 'Moderada',
  grave: 'Grave',
  gravissima: 'Gravíssima',
};

const SEVERITY_DOTS: Record<string, string> = {
  leve: 'bg-blue-500',
  moderada: 'bg-yellow-500',
  grave: 'bg-orange-500',
  gravissima: 'bg-red-500',
};

const CATEGORY_BAR_COLORS: string[] = [
  'bg-purple-500',
  'bg-blue-500',
  'bg-cyan-500',
];

export function OccurrenceAIPanel({ stats, occurrences }: OccurrenceAIPanelProps) {
  const analysis = useMemo(() => {
    const total = stats?.total ?? occurrences.length ?? 0;

    // --- Top 3 categories ---
    const categoryMap: Record<string, number> = stats?.by_category ?? {};
    if (Object.keys(categoryMap).length === 0) {
      for (const occ of occurrences) {
        categoryMap[occ.category] = (categoryMap[occ.category] ?? 0) + 1;
      }
    }
    const topCategories = Object.entries(categoryMap)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3);
    const maxCategoryCount = topCategories[0]?.[1] ?? 1;

    // --- Severity distribution ---
    const severityMap: Record<string, number> = stats?.by_severity ?? {};
    if (Object.keys(severityMap).length === 0) {
      for (const occ of occurrences) {
        severityMap[occ.severity] = (severityMap[occ.severity] ?? 0) + 1;
      }
    }
    const allSeverities: Array<{ key: string; count: number }> = [
      'leve', 'moderada', 'grave', 'gravissima',
    ].map((key) => ({ key, count: severityMap[key] ?? 0 }));

    // --- Avg resolution time ---
    const avgResolution = stats?.avg_resolution_time_hours ?? null;

    // --- Pending ratio ---
    const pending = stats?.pending_resolution ?? 0;

    // --- AI Insights ---
    const insights: Array<{ icon: 'warning' | 'info' | 'check'; text: string }> = [];

    const graveCount = (severityMap['grave'] ?? 0) + (severityMap['gravissima'] ?? 0);
    if (total > 0 && graveCount / total > 0.3) {
      insights.push({
        icon: 'warning',
        text: 'Alto índice de ocorrências graves: atenção redobrada necessária',
      });
    }

    if (avgResolution !== null && avgResolution > 48) {
      insights.push({
        icon: 'warning',
        text: 'Tempo de resolução acima de 48h: revisar processo de escalação',
      });
    }

    if (topCategories.length > 0 && topCategories[0]?.[0] === 'disciplinar') {
      insights.push({
        icon: 'info',
        text: 'Ocorrências disciplinares lideram: considerar treinamentos preventivos',
      });
    }

    if (total > 0 && pending / total > 0.5) {
      insights.push({
        icon: 'warning',
        text: 'Mais da metade das ocorrências pendentes: priorizar resolução',
      });
    }

    if (insights.length === 0) {
      insights.push({
        icon: 'check',
        text: 'Padrões dentro do esperado: continue monitorando regularmente',
      });
    }

    return { total, topCategories, maxCategoryCount, allSeverities, avgResolution, insights };
  }, [stats, occurrences]);

  return (
    <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-lg bg-purple-500/10 flex items-center justify-center flex-shrink-0">
          <Sparkles className="w-4 h-4 text-purple-500" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-[hsl(var(--foreground))]">Leitura rápida</h3>
          <p className="text-xs text-[hsl(var(--muted-foreground))]">Resumo automático dos números do período</p>
        </div>
      </div>

      {/* Overview */}
      <div className="flex items-center gap-3 bg-[hsl(var(--muted))]/50 rounded-lg p-3">
        <TrendingUp className="w-4 h-4 text-purple-500 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-xs text-[hsl(var(--muted-foreground))]">Total analisado</p>
          <p className="text-lg font-bold text-[hsl(var(--foreground))]">{analysis.total}</p>
        </div>
        {analysis.avgResolution !== null && (
          <div className="text-right flex-shrink-0">
            <p className="text-xs text-[hsl(var(--muted-foreground))]">Tempo médio</p>
            <div className="flex items-center gap-1 justify-end">
              <Clock className="w-3 h-3 text-purple-500" />
              <p className="text-sm font-semibold text-[hsl(var(--foreground))]">
                {Math.round(analysis.avgResolution)}h
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Top Categories */}
      {analysis.topCategories.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide">
            Distribuição por Categoria
          </p>
          <div className="space-y-2">
            {analysis.topCategories.map(([key, count], idx) => {
              const pct = analysis.maxCategoryCount > 0
                ? Math.round((count / analysis.maxCategoryCount) * 100)
                : 0;
              return (
                <div key={key} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-[hsl(var(--foreground))]">
                      {CATEGORY_LABELS[key] ?? key}
                    </span>
                    <span className="text-xs font-semibold text-[hsl(var(--foreground))]">{count}</span>
                  </div>
                  <div className="h-1.5 bg-[hsl(var(--muted))] rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${CATEGORY_BAR_COLORS[idx] ?? 'bg-purple-500'}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Severity Distribution */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide">
          Distribuição por Severidade
        </p>
        <div className="grid grid-cols-2 gap-1.5">
          {analysis.allSeverities.map(({ key, count }) => (
            <div
              key={key}
              className="flex items-center gap-2 bg-[hsl(var(--muted))]/40 rounded-lg px-2 py-1.5"
            >
              <span
                className={`w-2 h-2 rounded-full flex-shrink-0 ${SEVERITY_DOTS[key] ?? 'bg-gray-500'}`}
              />
              <div className="min-w-0">
                <p className="text-xs text-[hsl(var(--muted-foreground))] truncate">
                  {SEVERITY_LABELS[key] ?? key}
                </p>
                <p className="text-xs font-semibold text-[hsl(var(--foreground))]">{count}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Insights */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wide">
          Insights
        </p>
        <ul className="space-y-2">
          {analysis.insights.map((insight, idx) => (
            <li key={idx} className="flex items-start gap-2">
              <span className="flex-shrink-0 mt-0.5">
                {insight.icon === 'warning' && (
                  <AlertTriangle className="w-3.5 h-3.5 text-orange-500" />
                )}
                {insight.icon === 'info' && (
                  <Info className="w-3.5 h-3.5 text-blue-500" />
                )}
                {insight.icon === 'check' && (
                  <CheckCircle className="w-3.5 h-3.5 text-green-500" />
                )}
              </span>
              <p className="text-xs text-[hsl(var(--foreground))] leading-relaxed">{insight.text}</p>
            </li>
          ))}
        </ul>
      </div>

      {/* Footer */}
      <p className="text-[10px] text-[hsl(var(--muted-foreground))] text-center border-t border-[hsl(var(--border))] pt-3">
        Análise baseada nos dados atuais
      </p>
    </div>
  );
}
