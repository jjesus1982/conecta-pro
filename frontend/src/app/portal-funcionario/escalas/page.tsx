'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { CalendarClock, ArrowLeft, ShieldCheck, LogOut, Loader2, AlertCircle, Clock, MapPin } from 'lucide-react';

const API_BASE = '/api/v1/people-management/portal';

function getPortalHeaders(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('portal_token') : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

// Contrato REAL do backend: MyScheduleResponse (my_schedules_controller.get_my_schedules)
interface Schedule {
  employee_name: string;
  month: number;
  year: number;
  total_hours: number;
  escala_padrao?: string | null;
  turno_padrao?: string | null;
  carga_horaria_semanal?: number | null;
  jornada_trabalho?: string | null;
  cargo?: string | null;
  posto_atual_nome?: string | null;
  shifts: { date: string; start_time: string; end_time: string; workplace: string | null; status: string }[];
}

const MESES = ['', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];

export default function EscalasPage() {
  const router = useRouter();
  const [employeeName, setEmployeeName] = useState('');
  const [schedule, setSchedule] = useState<Schedule | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const token = localStorage.getItem('portal_token');
    if (!token) { router.push('/portal-funcionario/login'); return; }
    setEmployeeName(localStorage.getItem('portal_employee_name') || 'Funcionário');
    loadSchedule();
  }, [router]);

  async function loadSchedule() {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API_BASE}/my-schedules`, { headers: getPortalHeaders() });
      if (res.ok) {
        setSchedule(await res.json());
      } else {
        setError('Não foi possível carregar sua escala.');
      }
    } catch {
      setError('Erro ao carregar escala.');
    } finally {
      setLoading(false);
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('portal_token');
    localStorage.removeItem('portal_refresh_token');
    localStorage.removeItem('portal_employee_name');
    router.push('/portal-funcionario/login');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-[#0A2540] text-white">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ShieldCheck className="w-6 h-6 text-blue-300" />
            <div>
              <h1 className="text-base font-bold leading-none">CONECTA PRO</h1>
              <p className="text-xs text-blue-300">Portal do Funcionário</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-blue-200 hidden sm:block">{employeeName}</span>
            <button onClick={handleLogout} className="text-blue-300 hover:text-white" title="Sair">
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-6">
        <div className="flex items-center gap-3 mb-6">
          <Link href="/portal-funcionario/dashboard" className="text-gray-500 hover:text-gray-700">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <CalendarClock className="w-5 h-5 text-indigo-600" /> Minha Escala
          </h2>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-4 flex items-center gap-2 text-red-700 text-sm">
            <AlertCircle className="w-4 h-4 flex-shrink-0" /> {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
          </div>
        ) : schedule ? (
          <div className="space-y-5">
            <div className="bg-white rounded-xl shadow-sm p-5">
              <p className="text-sm text-gray-500">Referência</p>
              <p className="text-lg font-bold text-gray-900">{MESES[schedule.month] || ''} {schedule.year}</p>
              <div className="grid grid-cols-2 gap-4 mt-4">
                <div>
                  <p className="text-xs text-gray-400 uppercase tracking-wide">Escala</p>
                  <p className="font-medium text-gray-900">{schedule.escala_padrao || '—'}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 uppercase tracking-wide">Turno</p>
                  <p className="font-medium text-gray-900">{schedule.turno_padrao || '—'}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 uppercase tracking-wide">Carga semanal</p>
                  <p className="font-medium text-gray-900">{schedule.carga_horaria_semanal ? `${schedule.carga_horaria_semanal}h` : '—'}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 uppercase tracking-wide flex items-center gap-1"><Clock className="w-3 h-3" /> Horas no mês</p>
                  <p className="font-medium text-gray-900">{schedule.total_hours ? `${schedule.total_hours.toFixed(2)}h` : '—'}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 uppercase tracking-wide">Jornada</p>
                  <p className="font-medium text-gray-900">{schedule.jornada_trabalho || '—'}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 uppercase tracking-wide flex items-center gap-1"><MapPin className="w-3 h-3" /> Posto</p>
                  <p className="font-medium text-gray-900">{schedule.posto_atual_nome || '—'}</p>
                </div>
              </div>
            </div>

            {schedule.shifts && schedule.shifts.length > 0 && (
              <section>
                <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Turnos</h3>
                <div className="space-y-2">
                  {schedule.shifts.map((s, i) => (
                    <div key={i} className="bg-white rounded-xl shadow-sm p-4 flex items-center justify-between">
                      <div>
                        <p className="font-medium text-gray-900">{new Date(s.date).toLocaleDateString('pt-BR')}</p>
                        <p className="text-xs text-gray-500">{s.start_time} — {s.end_time} · {s.workplace || 'Posto'}</p>
                      </div>
                      <span className="text-xs px-2 py-1 rounded-full bg-blue-50 text-blue-600">{s.status}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm p-8 text-center text-gray-400">
            <CalendarClock className="w-10 h-10 mx-auto mb-2 opacity-30" />
            <p>Nenhuma escala disponível.</p>
          </div>
        )}
      </main>
    </div>
  );
}
