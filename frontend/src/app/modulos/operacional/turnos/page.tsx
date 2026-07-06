'use client';

import dynamic from 'next/dynamic';
import { Clock, ArrowLeft, Filter, RefreshCw, AlertCircle } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
;
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/hooks/useAuth';
import { useShifts } from '@/hooks/operacional/useShifts';
import { usePosts } from '@/hooks/operacional/usePosts';
import { useEmployees } from '@/hooks/operacional/useEmployees';
import { useScales } from '@/hooks/operacional/useScales';
import { useCheckInShift, useCheckOutShift, useMarkShiftMissed } from '@/hooks/operacional/useShifts';
import { getErrorMessage } from '@/lib/api';
import { ShiftCalendar } from '@/components/operacional/shift-calendar';
import { ShiftDayView } from '@/components/operacional/shift-day-view';
const ShiftCheckModal = dynamic(() => import('@/components/operacional/shift-check-modal').then(m => m.ShiftCheckModal), { ssr: false });
import { ExportButton } from '@/components/ui/export-button';
import { formatDataForExport } from '@/utils/export';
import type { Shift, ShiftFilter } from '@/types/operacional';
import type { PostResponse, EmployeeResponse, ScaleResponse } from '@/types/generated/operacional/conectaPROMóduloOPERACIONAL.schemas';

const TIMEZONE = 'America/Manaus';

const toLocalDateKey = (date: Date) => {
  return new Intl.DateTimeFormat('en-CA', { timeZone: TIMEZONE }).format(date);
};

export default function TurnosPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();
  const { data: postsData } = usePosts();
  const { data: employeesData } = useEmployees();
  const { data: scalesData } = useScales();

  const posts: PostResponse[] = useMemo(() => postsData?.items ?? [], [postsData?.items]);
  const employees: EmployeeResponse[] = useMemo(() => employeesData?.items ?? [], [employeesData?.items]);
  const scales: ScaleResponse[] = useMemo(() => scalesData?.items ?? [], [scalesData?.items]);

  const { mutate: checkIn } = useCheckInShift();
  const { mutate: checkOut } = useCheckOutShift();
  const { mutate: markMissed } = useMarkShiftMissed();

  const [selectedDate, setSelectedDate] = useState(new Date());
  const [view, setView] = useState<'month' | 'week'>('month');
  const [showFilters, setShowFilters] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [checkMode, setCheckMode] = useState<'check-in' | 'check-out' | 'missed'>('check-in');
  const [selectedShift, setSelectedShift] = useState<Shift | null>(null);

  const [filters, setFilters] = useState<ShiftFilter>({});
  const dateRange = useMemo(() => {
    const start = new Date(selectedDate);
    const end = new Date(selectedDate);
    if (view === 'month') {
      start.setDate(1);
      end.setMonth(end.getMonth() + 1);
      end.setDate(0);
    } else {
      start.setDate(start.getDate() - start.getDay());
      end.setDate(start.getDate() + 6);
    }
    return {
      start: toLocalDateKey(start),
      end: toLocalDateKey(end),
    };
  }, [selectedDate, view]);

  const shiftParams = useMemo(() => {
    const hasCustomRange = Boolean(filters.start_date || filters.end_date);
    return {
      ...filters,
      start_date: hasCustomRange ? filters.start_date : dateRange.start,
      end_date: hasCustomRange ? filters.end_date : dateRange.end,
    };
  }, [dateRange, filters]);

  const {
    data: shiftsData,
    isLoading,
    error,
    refetch: refresh,
  } = useShifts(shiftParams);

  const shifts = useMemo(() => (shiftsData?.items ?? []) as unknown as Shift[], [shiftsData?.items]);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  const postMap = useMemo(() => {
    return posts.reduce<Record<string, PostResponse>>((acc, post) => {
      acc[post.id] = post;
      return acc;
    }, {});
  }, [posts]);

  const employeeMap = useMemo(() => {
    return employees.reduce<Record<string, EmployeeResponse>>((acc, employee) => {
      acc[employee.id] = employee;
      return acc;
    }, {});
  }, [employees]);

  const calendarEmployeeMap = useMemo(() => {
    return employees.reduce<Record<string, { full_name?: string | null; name?: string | null; email?: string | null }>>((acc, employee) => {
      acc[employee.id] = {
        full_name: employee.nome,
        name: employee.nome,
        email: employee.email ?? null,
      };
      return acc;
    }, {});
  }, [employees]);

  const getEmployeeLabel = (employeeId: string | null) => {
    if (!employeeId) return 'Sem funcionario';
    const employee = employeeMap[employeeId];
    return (
      employee?.nome ||
      employee?.email ||
      employee?.matricula ||
      employeeId
    );
  };

  const getPostLabel = (postId: string) => {
    const post = postMap[postId];
    return post ? `${post.name} (${post.code})` : postId;
  };

  const shiftsForSelectedDate = useMemo(() => {
    const key = toLocalDateKey(selectedDate);
    return shifts.filter((shift) => shift.shift_date === key);
  }, [shifts, selectedDate]);

  const shiftModalKey = selectedShift
    ? `${selectedShift.id}-${checkMode}`
    : `shift-modal-${checkMode}`;

  const openCheckModal = (shift: Shift, mode: 'check-in' | 'check-out' | 'missed') => {
    setSelectedShift(shift);
    setCheckMode(mode);
    setCheckError(null);
  };

  const handleConfirmCheck = async (payload: {
    datetime?: string;
    breakMinutes?: number;
    reason?: string;
    notes?: string;
  }) => {
    if (!selectedShift) return;

    setIsChecking(true);
    setCheckError(null);

    try {
      if (checkMode === 'check-in') {
        checkIn(
          {
            shiftId: selectedShift.id,
            data: {
              actual_start_time: payload.datetime || new Date().toISOString(),
              notes: payload.notes,
            },
          },
          {
            onSuccess: () => {
              setSelectedShift(null);
              refresh();
            },
            onError: (err) => {
              setCheckError(getErrorMessage(err));
            },
          }
        );
      } else if (checkMode === 'check-out') {
        checkOut(
          {
            shiftId: selectedShift.id,
            data: {
              actual_end_time: payload.datetime || new Date().toISOString(),
              actual_break_minutes: payload.breakMinutes || 0,
              notes: payload.notes,
            },
          },
          {
            onSuccess: () => {
              setSelectedShift(null);
              refresh();
            },
            onError: (err) => {
              setCheckError(getErrorMessage(err));
            },
          }
        );
      } else if (checkMode === 'missed') {
        markMissed(
          {
            shiftId: selectedShift.id,
            params: {
              reason: payload.reason,
            },
          },
          {
            onSuccess: () => {
              setSelectedShift(null);
              refresh();
            },
            onError: (err) => {
              setCheckError(getErrorMessage(err));
            },
          }
        );
      }
    } finally {
      setIsChecking(false);
    }
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <Clock className="w-12 h-12" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-grid">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        <PageHeader
          eyebrow="OPERACIONAL"
          title="Turnos"
          subtitle={`${shifts.length} turnos no periodo selecionado`}
          icon={<Clock className="w-5 h-5" />}
          actions={
            <>
              <Link href="/modulos/operacional">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Operacional
                </Button>
              </Link>
              <Button
                variant="outline"
                onClick={() => setShowFilters(!showFilters)}
                className={showFilters ? 'border-[hsl(var(--primary))]' : ''}
              >
                <Filter className="w-4 h-4 mr-2" />
                Filtros
              </Button>
              <Button variant="outline" onClick={() => refresh()} disabled={isLoading}>
                <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
              </Button>
              <ExportButton
                data={formatDataForExport(shifts, {
                  shift_date: 'Data',
                  start_time: 'Início',
                  end_time: 'Fim',
                  post_name: 'Posto',
                  employee_name: 'Colaborador',
                  status: 'Status',
                  check_in_time: 'Check-in',
                  check_out_time: 'Check-out',
                })}
                filename="turnos"
                pdfTitle="Relatório de Turnos"
                formats={['excel', 'pdf', 'csv']}
              />
            </>
          }
        />

        {showFilters && (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Escala
                </label>
                <select
                  className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm"
                  value={filters.scale_id || ''}
                  onChange={(e) => setFilters({ ...filters, scale_id: e.target.value || undefined })}
                >
                  <option value="">Todas</option>
                  {scales.map((scale) => (
                    <option key={scale.id} value={scale.id}>
                      {scale.name || `${scale.month}/${scale.year}`}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Posto
                </label>
                <select
                  className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm"
                  value={filters.post_id || ''}
                  onChange={(e) => setFilters({ ...filters, post_id: e.target.value || undefined })}
                >
                  <option value="">Todos</option>
                  {posts.map((post) => (
                    <option key={post.id} value={post.id}>
                      {post.name} ({post.code})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Funcionario
                </label>
                <select
                  className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm"
                  value={filters.employee_id || ''}
                  onChange={(e) => setFilters({ ...filters, employee_id: e.target.value || undefined })}
                >
                  <option value="">Todos</option>
                  {employees.map((employee) => (
                    <option key={employee.id} value={employee.id}>
                      {getEmployeeLabel(employee.id)}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Somente nao preenchidos
                </label>
                <div className="flex items-center gap-2 h-10">
                  <input
                    type="checkbox"
                    checked={filters.is_filled === false}
                    onChange={(e) =>
                      setFilters({
                        ...filters,
                        is_filled: e.target.checked ? false : undefined,
                      })
                    }
                    className="rounded border-[hsl(var(--border))]"
                  />
                  <span className="text-sm">Sem funcionario</span>
                </div>
              </div>
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Inicio
                </label>
                <Input
                  type="date"
                  value={filters.start_date || dateRange.start}
                  onChange={(e) => setFilters({ ...filters, start_date: e.target.value || undefined })}
                />
              </div>
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Fim
                </label>
                <Input
                  type="date"
                  value={filters.end_date || dateRange.end}
                  onChange={(e) => setFilters({ ...filters, end_date: e.target.value || undefined })}
                />
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-500" />
            <p className="text-red-500">{error.detail?.[0]?.msg ?? 'Erro ao carregar turnos'}</p>
            <Button variant="outline" size="sm" onClick={() => refresh()} className="ml-auto">
              Tentar novamente
            </Button>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ShiftCalendar
            shifts={shifts}
            selectedDate={selectedDate}
            onSelectDate={setSelectedDate}
            view={view}
            onViewChange={setView}
            employeeMap={calendarEmployeeMap}
          />
          <div className="space-y-4">
            <div>
              <h2 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                Turnos do dia
              </h2>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                {selectedDate.toLocaleDateString('pt-BR')}
              </p>
            </div>
            {isLoading ? (
              <div className="flex items-center justify-center py-10">
                <div className="animate-pulse-slow text-[hsl(var(--primary))]">
                  <Clock className="w-8 h-8" />
                </div>
              </div>
            ) : (
              <ShiftDayView
                shifts={shiftsForSelectedDate}
                getEmployeeLabel={getEmployeeLabel}
                getPostLabel={getPostLabel}
                onCheckIn={(shift) => openCheckModal(shift, 'check-in')}
                onCheckOut={(shift) => openCheckModal(shift, 'check-out')}
                onMarkMissed={(shift) => openCheckModal(shift, 'missed')}
              />
            )}
          </div>
        </div>
      </main>

      <ShiftCheckModal
        key={shiftModalKey}
        isOpen={!!selectedShift}
        onClose={() => setSelectedShift(null)}
        shift={selectedShift}
        mode={checkMode}
        onConfirm={handleConfirmCheck}
        isLoading={isChecking}
        error={checkError}
      />
    </div>
  );
}
