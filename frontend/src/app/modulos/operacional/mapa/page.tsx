'use client';
import { Map, ArrowLeft, RefreshCw, MapPin, Users, CheckCircle, AlertCircle, Activity } from 'lucide-react';
import { useState, useMemo, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { useAuth } from '@/hooks/useAuth';
import { usePosts } from '@/hooks/operacional/usePosts';
import { useCoverageReport } from '@/hooks/operacional/useReports';

export default function MapaPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();

  const { data: postsData, isLoading: postsLoading, refetch: refetchPosts } = usePosts({ page: 1, page_size: 200 });
  const posts = useMemo(() => (postsData as any)?.items ?? [], [postsData]);

  const now = useMemo(() => new Date(), []);
  const startDate = useMemo(() => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Manaus' }).format(new Date(now.getFullYear(), now.getMonth(), 1)), [now]);
  const endDate = useMemo(() => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Manaus' }).format(now), [now]);

  const { data: coverageData, refetch: refetchCoverage } = useCoverageReport({ start_date: startDate, end_date: endDate });

  const coverageMap = useMemo(() => {
    const map: Record<string, number> = {};
    ((coverageData as any)?.items || []).forEach((item: any) => {
      map[item.post_id] = item.coverage_rate;
    });
    return map;
  }, [coverageData]);

  // Group posts by city/state
  const groupedPosts = useMemo(() => {
    const groups: Record<string, any[]> = {};
    posts.forEach((post: any) => {
      const region = post.city
        ? `${post.city}${post.state ? ` — ${post.state}` : ''}`
        : 'Não Informado';
      if (!groups[region]) groups[region] = [];
      groups[region].push(post);
    });
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [posts]);

  const stats = useMemo(() => {
    const totalPosts = posts.length;
    const postosAtivos = posts.filter((p: any) => p.is_active !== false).length;
    const coverageValues = Object.values(coverageMap);
    const coberturaMedia = coverageValues.length > 0
      ? coverageValues.reduce((a, b) => a + b, 0) / coverageValues.length
      : 0;
    const postosEmRisco = coverageValues.filter(v => v < 50).length;
    return { totalPosts, postosAtivos, coberturaMedia, postosEmRisco };
  }, [posts, coverageMap]);

  // Auto-refresh 30s
  useEffect(() => {
    if (!isAuthenticated) return;
    const interval = setInterval(() => {
      refetchPosts();
      refetchCoverage();
    }, 30_000);
    return () => clearInterval(interval);
  }, [isAuthenticated, refetchPosts, refetchCoverage]);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [isAuthenticated, isLoading, router]);

  const handleRefresh = () => {
    refetchPosts();
    refetchCoverage();
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-6 h-6 animate-spin text-[hsl(var(--primary))]" />
      </div>
    );
  }

  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Header */}
      <PageHeader
        eyebrow="OPERACIONAL"
        title="Mapa ao Vivo"
        subtitle="Cobertura por região — atualiza a cada 30s"
        icon={<Map className="w-5 h-5" />}
        actions={
          <>
            <Link href="/modulos/operacional">
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <ArrowLeft className="w-4 h-4" />
              </Button>
            </Link>
            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-500/10 text-red-500 text-xs font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
              AO VIVO
            </span>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleRefresh}
              className="h-9 w-9"
              title="Atualizar"
            >
              <RefreshCw className={`w-4 h-4 ${postsLoading ? 'animate-spin' : ''}`} />
            </Button>
          </>
        }
      />

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <MapPin className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
            <span className="text-xs text-[hsl(var(--muted-foreground))]">Total Postos</span>
          </div>
          <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{stats.totalPosts}</p>
        </div>
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle className="w-4 h-4 text-green-500" />
            <span className="text-xs text-[hsl(var(--muted-foreground))]">Postos Ativos</span>
          </div>
          <p className="font-data text-2xl font-semibold tabular-nums text-green-500">{stats.postosAtivos}</p>
        </div>
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Activity className="w-4 h-4 text-[hsl(var(--primary))]" />
            <span className="text-xs text-[hsl(var(--muted-foreground))]">Cobertura Média</span>
          </div>
          <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--primary))]">
            {stats.coberturaMedia > 0 ? `${stats.coberturaMedia.toFixed(0)}%` : '—'}
          </p>
        </div>
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertCircle className="w-4 h-4 text-red-500" />
            <span className="text-xs text-[hsl(var(--muted-foreground))]">Em Risco</span>
          </div>
          <p className="font-data text-2xl font-semibold tabular-nums text-red-500">{stats.postosEmRisco}</p>
        </div>
      </div>

      {/* Legenda */}
      <div className="flex flex-wrap items-center gap-4 text-xs text-[hsl(var(--muted-foreground))]">
        <span className="font-medium text-[hsl(var(--foreground))]">Cobertura:</span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-green-500" />
          Boa (≥80%)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-yellow-500" />
          Regular (50-79%)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
          Em risco (&lt;50%)
        </span>
      </div>

      {/* Loading state */}
      {postsLoading && (
        <div className="flex items-center justify-center py-12">
          <div className="flex items-center gap-3 text-[hsl(var(--muted-foreground))]">
            <RefreshCw className="w-5 h-5 animate-spin" />
            <span className="text-sm">Carregando postos...</span>
          </div>
        </div>
      )}

      {/* Mapa por regiões */}
      {!postsLoading && posts.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-[hsl(var(--muted-foreground))]">
          <Map className="w-10 h-10 mb-3 opacity-30" />
          <p className="text-sm font-medium">Nenhum posto encontrado</p>
          <p className="text-xs mt-1">Cadastre postos para visualizá-los no mapa</p>
        </div>
      )}

      {!postsLoading && groupedPosts.map(([region, regionPosts]) => (
        <div key={region} className="space-y-3">
          {/* Cabeçalho da região */}
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5">
              <MapPin className="w-4 h-4 text-[hsl(var(--primary))]" />
              <h2 className="text-sm font-semibold text-[hsl(var(--foreground))]">{region}</h2>
            </div>
            <span className="text-xs text-[hsl(var(--muted-foreground))] px-2 py-0.5 rounded-full bg-[hsl(var(--muted))]/50">
              {regionPosts.length} posto{regionPosts.length !== 1 ? 's' : ''}
            </span>
            <div className="flex-1 h-px bg-[hsl(var(--border))]" />
          </div>

          {/* Grid de postos */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {regionPosts.map((post: any) => {
              const coverage = coverageMap[post.id] ?? 100;
              const borderColor = coverage >= 80 ? 'border-green-500/30' : coverage >= 50 ? 'border-yellow-500/30' : 'border-red-500/30';
              const dotColor = coverage >= 80 ? 'bg-green-500' : coverage >= 50 ? 'bg-yellow-500 animate-pulse' : 'bg-red-500 animate-pulse';
              const coverageColor = coverage >= 80 ? 'text-green-500' : coverage >= 50 ? 'text-yellow-500' : 'text-red-500';

              return (
                <div
                  key={post.id}
                  className={`bg-[hsl(var(--card))] border rounded-xl p-3 hover:shadow-md transition-shadow ${borderColor}`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <MapPin className="w-4 h-4 text-[hsl(var(--primary))]" />
                    <span className={`w-2 h-2 rounded-full ${dotColor}`} />
                  </div>
                  <p className="text-xs font-medium text-[hsl(var(--foreground))] truncate" title={post.name}>
                    {post.name}
                  </p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))] truncate">{post.code}</p>
                  {coverageMap[post.id] !== undefined && (
                    <p className={`text-sm font-bold mt-1 ${coverageColor}`}>
                      {coverageMap[post.id]?.toFixed(0)}%
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
