'use client';
import { Calendar, ArrowLeft, ChevronLeft, ChevronRight, RefreshCw, Plus, Users, Clock, CheckCircle, AlertCircle, Eye } from 'lucide-react';
import { useState, useMemo, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { useAuth } from '@/hooks/useAuth';
import { usePosts } from '@/hooks/operacional/usePosts';
import { useShifts } from '@/hooks/operacional/useShifts';

/**
 * Datas vindas do backend como 'YYYY-MM-DD' precisam ser interpretadas no
 * fuso LOCAL. `new Date('YYYY-MM-DD')` parseia como UTC-meia-noite e, em
 * Manaus (UTC-4), o turno cai no dia ANTERIOR (grade errada/vazia).
 */
function parseShiftDate(value: string): Date {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value);
}

export default function EscalasVisualPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();

  // Toda a grade depende de new Date()/toLocaleDateString, que divergem entre
  // SSR e client (React #418 — hydration mismatch). Renderizamos o conteúdo
  // datado só depois do mount (client-only).
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const [currentWeekStart, setCurrentWeekStart] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - d.getDay() + 1); // Segunda-feira desta semana
    d.setHours(0, 0, 0, 0);
    return d;
  });

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  const weekDays = useMemo(() => {
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(currentWeekStart);
      d.setDate(d.getDate() + i);
      return d;
    });
  }, [currentWeekStart]);

  const weekLabel = useMemo(() => {
    const start = weekDays[0]?.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }) ?? '';
    const end = weekDays[6]?.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' }) ?? '';
    return `${start} — ${end}`;
  }, [weekDays]);

  const goToPreviousWeek = () => {
    setCurrentWeekStart(prev => {
      const d = new Date(prev);
      d.setDate(d.getDate() - 7);
      return d;
    });
  };

  const goToNextWeek = () => {
    setCurrentWeekStart(prev => {
      const d = new Date(prev);
      d.setDate(d.getDate() + 7);
      return d;
    });
  };

  const goToCurrentWeek = () => {
    const d = new Date();
    d.setDate(d.getDate() - d.getDay() + 1);
    d.setHours(0, 0, 0, 0);
    setCurrentWeekStart(d);
  };

  const weekStartStr = weekDays[0]?.toISOString().split('T')[0];
  const weekEndStr = weekDays[6]?.toISOString().split('T')[0];

  const { data: postsData } = usePosts({ page: 1, page_size: 100 });
  const posts = useMemo(() => (postsData as any)?.items ?? [], [postsData]);

  // Backend aceita page_size até 500 (semana inteira numa página)
  const { data: shiftsData, isLoading, isError, error, refetch } = useShifts({
    date_from: weekStartStr,
    date_to: weekEndStr,
    page_size: 500,
  } as any);
  const shifts = useMemo(() => (shiftsData as any)?.items ?? (Array.isArray(shiftsData) ? shiftsData : []), [shiftsData]);

  // Map: postId -> dayIndex (0-6) -> shifts[]
  const shiftsGrid = useMemo(() => {
    const grid: Record<string, Record<number, any[]>> = {};
    shifts.forEach((shift: any) => {
      const postId = shift.post_id || 'unknown';
      if (!grid[postId]) grid[postId] = {};
      const shiftDate = parseShiftDate(shift.date || shift.start_time || shift.scheduled_date || '');
      const dayIdx = weekDays.findIndex(d =>
        d.toDateString() === shiftDate.toDateString()
      );
      if (dayIdx >= 0) {
        if (!grid[postId][dayIdx]) grid[postId][dayIdx] = [];
        grid[postId][dayIdx].push(shift);
      }
    });
    return grid;
  }, [shifts, weekDays]);

  // Compute summary stats
  const totalShifts = shifts.length;
  const totalPostsCovered = useMemo(() => {
    const covered = new Set<string>();
    shifts.forEach((s: any) => { if (s.post_id) covered.add(s.post_id); });
    return covered.size;
  }, [shifts]);

  const totalHours = useMemo(() => {
    let hours = 0;
    shifts.forEach((s: any) => {
      if (s.start_time && s.end_time) {
        const start = new Date(s.start_time);
        const end = new Date(s.end_time);
        const diff = (end.getTime() - start.getTime()) / (1000 * 60 * 60);
        if (diff > 0 && diff < 24) hours += diff;
      } else if (s.duration_hours) {
        hours += s.duration_hours;
      }
    });
    return Math.round(hours);
  }, [shifts]);

  // !mounted: mesmo placeholder no SSR e no 1º render do client → sem #418
  if (authLoading || !mounted) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <Calendar className="w-12 h-12" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-grid">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <PageHeader
          eyebrow="OPERACIONAL · ESCALAS"
          title="Editor Visual de Escalas"
          subtitle="Grade semanal por posto"
          icon={<Calendar className="w-5 h-5" />}
          actions={
            <>
              <Link href="/modulos/operacional/escalas">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Escalas
                </Button>
              </Link>
              <Button variant="outline" size="sm" onClick={goToPreviousWeek}>
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="text-sm font-medium text-[hsl(var(--foreground))] hidden sm:block whitespace-nowrap min-w-[180px] text-center">
                {weekLabel}
              </span>
              <Button variant="outline" size="sm" onClick={goToNextWeek}>
                <ChevronRight className="w-4 h-4" />
              </Button>
              <Button variant="outline" size="sm" onClick={goToCurrentWeek}>
                Hoje
              </Button>
              <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isLoading}>
                <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
              </Button>
            </>
          }
        />

        {/* Week label (mobile) */}
        <p className="text-sm font-medium text-center text-[hsl(var(--foreground))] mb-4 sm:hidden">
          {weekLabel}
        </p>

        {/* Erro honesto ao buscar turnos — nunca deixar a grade "vazia em silêncio" */}
        {isError && (
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-300 bg-red-500/10 px-4 py-3">
            <div className="flex items-center gap-2 text-sm text-red-700 dark:text-red-400">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>
                Erro ao carregar os turnos da semana:{' '}
                {(error as any)?.response?.data?.detail
                  ? String((error as any).response.data.detail)
                  : (error as Error | undefined)?.message || 'falha de conexão com o servidor'}
              </span>
            </div>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              <RefreshCw className="w-4 h-4 mr-2" />
              Tentar novamente
            </Button>
          </div>
        )}

        {/* Legenda */}
        <div className="flex flex-wrap items-center gap-3 mb-6">
          <span className="text-xs text-[hsl(var(--muted-foreground))] font-medium">Legenda:</span>
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-blue-500/10 border border-blue-300 text-xs text-blue-700">
            <span className="w-2 h-2 rounded-full bg-blue-500" />
            Agendado
          </span>
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-green-500/10 border border-green-300 text-xs text-green-700">
            <span className="w-2 h-2 rounded-full bg-green-500" />
            Em andamento
          </span>
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-gray-500/10 border border-gray-300 text-xs text-gray-600">
            <span className="w-2 h-2 rounded-full bg-gray-500" />
            Concluído
          </span>
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-red-500/10 border border-red-300 text-xs text-red-700">
            <span className="w-2 h-2 rounded-full bg-red-500" />
            Falta
          </span>
        </div>

        {/* Grid */}
        <div className="overflow-x-auto rounded-xl border border-[hsl(var(--border))]">
          <div className="min-w-[800px]">
            {/* Header da grid: dias da semana */}
            <div className="grid grid-cols-[200px_repeat(7,1fr)] gap-px bg-[hsl(var(--border))] rounded-t-xl overflow-hidden">
              <div className="bg-[hsl(var(--muted))] px-3 py-2 text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                Posto
              </div>
              {weekDays.map((day, i) => {
                const isToday = day.toDateString() === new Date().toDateString();
                return (
                  <div
                    key={i}
                    className={`px-2 py-2 text-center text-xs font-medium ${
                      isToday
                        ? 'bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))]'
                        : 'bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))]'
                    }`}
                  >
                    <div>{day.toLocaleDateString('pt-BR', { weekday: 'short' }).toUpperCase()}</div>
                    <div className={`text-sm font-bold ${isToday ? 'text-[hsl(var(--primary))]' : ''}`}>
                      {day.getDate()}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Linhas por posto */}
            {posts.slice(0, 20).map((post: any) => (
              <div key={post.id} className="grid grid-cols-[200px_repeat(7,1fr)] gap-px bg-[hsl(var(--border))]">
                {/* Nome do posto */}
                <div className="bg-[hsl(var(--card))] px-3 py-3 flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-[hsl(var(--primary))] flex-shrink-0" />
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-[hsl(var(--foreground))] truncate max-w-[160px]">{post.name}</p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">{post.code}</p>
                  </div>
                </div>
                {/* Células por dia */}
                {weekDays.map((_, dayIdx) => {
                  const dayShifts = shiftsGrid[post.id]?.[dayIdx] || [];
                  return (
                    <div key={dayIdx} className="bg-[hsl(var(--card))] p-1 min-h-[70px] relative group">
                      {dayShifts.map((shift: any, si: number) => {
                        const statusColor =
                          shift.status === 'completed'
                            ? 'bg-gray-500/20 text-gray-600 border-gray-300'
                            : shift.status === 'in_progress'
                            ? 'bg-green-500/20 text-green-700 border-green-300'
                            : shift.status === 'absent'
                            ? 'bg-red-500/20 text-red-700 border-red-300'
                            : 'bg-blue-500/20 text-blue-700 border-blue-300';
                        return (
                          <div
                            key={si}
                            className={`mb-1 px-1.5 py-1 rounded text-xs border ${statusColor} truncate`}
                            title={shift.employee_name || shift.start_time || 'Turno'}
                          >
                            {shift.employee_name || shift.start_time?.slice(11, 16) || 'Turno'}
                          </div>
                        );
                      })}
                      {dayShifts.length === 0 && (
                        <div className="h-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                          <Plus className="w-3 h-3 text-[hsl(var(--muted-foreground))]" />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}

            {/* Estado vazio */}
            {posts.length === 0 && !isLoading && (
              <div className="bg-[hsl(var(--card))] text-center py-12 rounded-b-xl">
                <Calendar className="w-8 h-8 text-[hsl(var(--muted-foreground))] mx-auto mb-2" />
                <p className="text-sm text-[hsl(var(--muted-foreground))]">Nenhum posto cadastrado</p>
              </div>
            )}

            {/* Loading state */}
            {isLoading && (
              <div className="bg-[hsl(var(--card))] text-center py-12 rounded-b-xl">
                <RefreshCw className="w-6 h-6 text-[hsl(var(--primary))] mx-auto mb-2 animate-spin" />
                <p className="text-sm text-[hsl(var(--muted-foreground))]">Carregando turnos...</p>
              </div>
            )}
          </div>
        </div>

        {/* Rodapé — resumo da semana */}
        <div className="mt-6 grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center flex-shrink-0">
              <Calendar className="w-5 h-5 text-blue-500" />
            </div>
            <div>
              <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{totalShifts}</p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Turnos na semana</p>
            </div>
          </div>
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center flex-shrink-0">
              <Clock className="w-5 h-5 text-green-500" />
            </div>
            <div>
              <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{totalHours}h</p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Total de horas</p>
            </div>
          </div>
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-[hsl(var(--primary))]/10 flex items-center justify-center flex-shrink-0">
              <Users className="w-5 h-5 text-[hsl(var(--primary))]" />
            </div>
            <div>
              <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{totalPostsCovered}</p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Postos cobertos</p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
