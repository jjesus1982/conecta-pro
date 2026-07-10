'use client';

import { Shield, RefreshCw, ArrowLeft, AlertCircle, CheckCircle, Activity } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { useAuth } from '@/hooks/useAuth';
import { useCoverageReport } from '@/hooks/operacional/useReports';
import { usePosts } from '@/hooks/operacional/usePosts';
import { PostCoverageCard } from '@/components/operacional/PostCoverageCard';

type FilterType = 'all' | 'risk' | 'partial' | 'full' | 'remote';

// Posto sem quadro presencial (required_headcount=0, ex. portaria remota):
// estado NEUTRO — nunca entra em "Em Risco".
const isRemotePost = (item: any) => (item.required_headcount ?? 0) === 0;

export default function CoberturaPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();
  const [filter, setFilter] = useState<FilterType>('all');

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  const now = useMemo(() => new Date(), []);

  const startDate = useMemo(() => {
    const d = new Date(now.getFullYear(), now.getMonth(), 1);
    return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Manaus' }).format(d);
  }, [now]);

  const endDate = useMemo(() => {
    return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Manaus' }).format(now);
  }, [now]);

  const { data: coverageReport, isLoading, error, refetch } = useCoverageReport({
    start_date: startDate,
    end_date: endDate,
  });

  const { data: postsData } = usePosts();

  const postMap = useMemo(() => {
    const items = (postsData as any)?.items ?? [];
    const map: Record<string, any> = {};
    items.forEach((post: any) => { map[post.id] = post; });
    return map;
  }, [postsData]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    if (!isAuthenticated) return;
    const interval = setInterval(refetch, 30_000);
    return () => clearInterval(interval);
  }, [isAuthenticated, refetch]);

  const allItems = useMemo(() => {
    return (coverageReport as any)?.items ?? [];
  }, [coverageReport]);

  const filteredItems = useMemo(() => {
    if (!allItems.length) return [];
    return allItems.filter((item: any) => {
      if (filter === 'remote') return isRemotePost(item);
      if (filter === 'risk') return !isRemotePost(item) && item.coverage_rate < 80;
      if (filter === 'partial') return !isRemotePost(item) && item.coverage_rate >= 80 && item.coverage_rate < 100;
      if (filter === 'full') return !isRemotePost(item) && item.coverage_rate >= 100;
      return true;
    });
  }, [allItems, filter]);

  // Summary stats — só postos ATIVOS (o backend já filtra status='active')
  const totalPosts = allItems.length;
  const remotePosts = useMemo(
    () => allItems.filter((item: any) => isRemotePost(item)).length,
    [allItems]
  );
  const fullCoveragePosts = useMemo(
    () => allItems.filter((item: any) => !isRemotePost(item) && item.coverage_rate >= 100).length,
    [allItems]
  );
  const atRiskPosts = useMemo(
    () => allItems.filter((item: any) => !isRemotePost(item) && item.coverage_rate < 80).length,
    [allItems]
  );
  // Fórmula padronizada (backend): postos ativos cobertos / postos ativos × 100
  const overallCoverage = useMemo(() => {
    return (coverageReport as any)?.coverage_rate ?? 0;
  }, [coverageReport]);

  const filterButtons: { id: FilterType; label: string; count?: number }[] = [
    { id: 'all', label: 'Todos', count: totalPosts },
    { id: 'risk', label: 'Em Risco', count: atRiskPosts },
    { id: 'partial', label: 'Parcial', count: totalPosts - fullCoveragePosts - atRiskPosts - remotePosts },
    { id: 'full', label: 'Completo', count: fullCoveragePosts },
    { id: 'remote', label: 'Sem quadro presencial', count: remotePosts },
  ];

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse text-[hsl(var(--primary))]">
          <Shield className="w-12 h-12" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-grid">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        <PageHeader
          eyebrow="OPERACIONAL"
          title="Cobertura ao Vivo"
          subtitle="Monitoramento em tempo real dos postos"
          icon={<Shield className="w-5 h-5" />}
          actions={
            <>
              <Link href="/modulos/operacional">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Operacional
                </Button>
              </Link>
              {/* Live badge */}
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-green-500/10 border border-green-500/30">
                <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                <span className="text-xs font-semibold text-green-500 tracking-wide">AO VIVO</span>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => refetch()}
                disabled={isLoading}
              >
                <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
              </Button>
            </>
          }
        />

        {/* Error state */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
            <p className="text-red-500 text-sm">
              {(error as any)?.message || 'Erro ao carregar dados de cobertura'}
            </p>
            <Button variant="outline" size="sm" onClick={() => refetch()} className="ml-auto">
              Tentar novamente
            </Button>
          </div>
        )}

        {/* Summary stats row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-2 mb-1">
              <Activity className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Postos Ativos</p>
            </div>
            <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{totalPosts}</p>
          </div>

          <div className="bg-[hsl(var(--card))] border border-green-500/30 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-1">
              <CheckCircle className="w-4 h-4 text-green-500" />
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Cobertura Completa</p>
            </div>
            <p className="font-data text-2xl font-semibold tabular-nums text-green-500">{fullCoveragePosts}</p>
          </div>

          <div className="bg-[hsl(var(--card))] border border-red-500/30 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-1">
              <AlertCircle className="w-4 h-4 text-red-500" />
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Em Risco</p>
            </div>
            <p className="font-data text-2xl font-semibold tabular-nums text-red-500">{atRiskPosts}</p>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-2 mb-1">
              <Shield className="w-4 h-4 text-[hsl(var(--primary))]" />
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Cobertura Geral</p>
            </div>
            <p className={`font-data text-2xl font-semibold tabular-nums ${
              overallCoverage >= 100
                ? 'text-green-500'
                : overallCoverage >= 80
                ? 'text-yellow-500'
                : 'text-red-500'
            }`}>
              {overallCoverage.toFixed(0)}%
            </p>
          </div>
        </div>

        {/* Filter buttons */}
        <div className="flex flex-wrap gap-2">
          {filterButtons.map((btn) => (
            <button
              key={btn.id}
              onClick={() => setFilter(btn.id)}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all border ${
                filter === btn.id
                  ? 'bg-[hsl(var(--primary))] text-white border-[hsl(var(--primary))]'
                  : 'bg-[hsl(var(--card))] text-[hsl(var(--foreground))] border-[hsl(var(--border))] hover:border-[hsl(var(--primary))]/50'
              }`}
            >
              {btn.label}
              {btn.count !== undefined && (
                <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                  filter === btn.id
                    ? 'bg-white/20 text-white'
                    : 'bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))]'
                }`}>
                  {btn.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Cards grid */}
        {isLoading && !allItems.length ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div
                key={i}
                className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 h-[148px] animate-pulse"
              >
                <div className="h-4 bg-[hsl(var(--muted))] rounded w-3/4 mb-3" />
                <div className="h-8 bg-[hsl(var(--muted))] rounded w-1/2 mb-3" />
                <div className="h-2 bg-[hsl(var(--muted))] rounded w-full mb-2" />
                <div className="h-3 bg-[hsl(var(--muted))] rounded w-2/3" />
              </div>
            ))}
          </div>
        ) : filteredItems.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filteredItems.map((item: any) => {
              const postName =
                item.post_name ||
                postMap[item.post_id]?.name ||
                'Posto ' + String(item.post_id).slice(0, 8);
              const postCode = postMap[item.post_id]?.code;

              if (isRemotePost(item)) {
                // Sem quadro presencial (ex. portaria remota): estado neutro, sem % nem risco
                return (
                  <div
                    key={item.post_id}
                    className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4"
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="w-2.5 h-2.5 rounded-full flex-shrink-0 bg-[hsl(var(--muted-foreground))]" />
                        <div className="min-w-0">
                          <p className="font-semibold text-[hsl(var(--foreground))] text-sm leading-tight truncate">
                            {postName}
                          </p>
                          {postCode && (
                            <p className="text-xs text-[hsl(var(--muted-foreground))] truncate">{postCode}</p>
                          )}
                        </div>
                      </div>
                    </div>
                    <p className="text-lg font-semibold text-[hsl(var(--muted-foreground))] mb-2">
                      Sem quadro presencial
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">
                      Posto sem efetivo presencial requerido (ex. portaria remota) — não entra na conta de risco.
                    </p>
                  </div>
                );
              }

              return (
                <PostCoverageCard
                  key={item.post_id}
                  postName={postName}
                  postCode={postCode}
                  activeAllocations={item.active_allocations}
                  totalAllocations={item.total_allocations}
                  coverageRate={item.coverage_rate}
                />
              );
            })}
          </div>
        ) : (
          /* Empty state */
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-12 text-center">
            <div className="w-16 h-16 rounded-full bg-[hsl(var(--muted))] flex items-center justify-center mx-auto mb-4">
              <Shield className="w-8 h-8 text-[hsl(var(--muted-foreground))]" />
            </div>
            <h3 className="text-base font-semibold text-[hsl(var(--foreground))] mb-2">
              {filter === 'all'
                ? 'Nenhum dado de cobertura encontrado'
                : `Nenhum posto no estado "${filterButtons.find(b => b.id === filter)?.label}"`}
            </h3>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">
              {filter === 'all'
                ? 'Os dados de cobertura aparecerão aqui quando houver alocações registradas.'
                : 'Tente selecionar outro filtro.'}
            </p>
            {filter !== 'all' && (
              <Button
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={() => setFilter('all')}
              >
                Ver todos os postos
              </Button>
            )}
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-center gap-2 py-2 text-xs text-[hsl(var(--muted-foreground))]">
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Atualiza automaticamente a cada 30 segundos</span>
        </div>
      </main>
    </div>
  );
}
