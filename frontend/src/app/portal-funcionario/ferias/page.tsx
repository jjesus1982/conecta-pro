'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Palmtree, ArrowLeft, ShieldCheck, LogOut, Loader2, AlertCircle, Calendar } from 'lucide-react';

const API_BASE = '/api/v1/people-management/portal';

function getPortalHeaders(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('portal_token') : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

interface VacationBalance {
  dias_direito: number;
  dias_gozados: number;
  dias_saldo: number;
  total_bruto_ferias: number;
  periodo_aquisitivo_inicio: string | null;
  periodo_aquisitivo_fim: string | null;
}

interface VacationRequest {
  id: string;
  data_inicio: string | null;
  data_fim: string | null;
  dias: number | null;
  status: string | null;
  tipo: string | null;
  created_at: string | null;
}

const statusColors: Record<string, string> = {
  aprovada: 'bg-green-100 text-green-700',
  pendente: 'bg-yellow-100 text-yellow-700',
  rejeitada: 'bg-red-100 text-red-600',
  cancelada: 'bg-gray-100 text-gray-600',
};

const fmt = (v: number) => `R$ ${(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;
const fmtDate = (d: string | null) => d ? new Date(d).toLocaleDateString('pt-BR') : '—';

export default function FeriasPage() {
  const router = useRouter();
  const [employeeName, setEmployeeName] = useState('');
  const [balance, setBalance] = useState<VacationBalance | null>(null);
  const [requests, setRequests] = useState<VacationRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const token = localStorage.getItem('portal_token');
    if (!token) { router.push('/portal-funcionario/login'); return; }
    setEmployeeName(localStorage.getItem('portal_employee_name') || 'Funcionário');

    async function load() {
      setLoading(true);
      setError('');
      try {
        const [balRes, reqRes] = await Promise.all([
          fetch(`${API_BASE}/my-vacations/balance`, { headers: getPortalHeaders() }),
          fetch(`${API_BASE}/my-vacations/requests`, { headers: getPortalHeaders() }),
        ]);
        if (balRes.ok) setBalance(await balRes.json());
        if (reqRes.ok) {
          const data = await reqRes.json();
          setRequests(Array.isArray(data) ? data : (data.items || []));
        }
      } catch {
        setError('Erro ao carregar dados de férias.');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [router]);

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
            <Palmtree className="w-5 h-5 text-green-600" /> Férias
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
        ) : (
          <>
            {/* Saldo */}
            {balance && (
              <div className="bg-white rounded-xl shadow-sm p-5 mb-4">
                <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">Saldo de Férias</h3>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="bg-blue-50 rounded-xl p-4 text-center">
                    <p className="text-xs text-gray-500 mb-1">Direito</p>
                    <p className="font-data text-2xl font-semibold tabular-nums text-blue-700">{balance.dias_direito}</p>
                    <p className="text-xs text-gray-400">dias</p>
                  </div>
                  <div className="bg-orange-50 rounded-xl p-4 text-center">
                    <p className="text-xs text-gray-500 mb-1">Gozados</p>
                    <p className="font-data text-2xl font-semibold tabular-nums text-orange-600">{balance.dias_gozados}</p>
                    <p className="text-xs text-gray-400">dias</p>
                  </div>
                  <div className="bg-green-50 rounded-xl p-4 text-center">
                    <p className="text-xs text-gray-500 mb-1">Saldo</p>
                    <p className="font-data text-2xl font-semibold tabular-nums text-green-700">{balance.dias_saldo}</p>
                    <p className="text-xs text-gray-400">dias</p>
                  </div>
                  <div className="bg-purple-50 rounded-xl p-4 text-center">
                    <p className="text-xs text-gray-500 mb-1">Bruto</p>
                    <p className="text-sm font-bold text-purple-700">{fmt(balance.total_bruto_ferias)}</p>
                  </div>
                </div>
                {balance.periodo_aquisitivo_inicio && (
                  <div className="mt-4 flex items-center gap-2 text-xs text-gray-500 bg-gray-50 rounded-lg p-3">
                    <Calendar className="w-4 h-4 flex-shrink-0" />
                    Período aquisitivo: {fmtDate(balance.periodo_aquisitivo_inicio)} a {fmtDate(balance.periodo_aquisitivo_fim)}
                  </div>
                )}
              </div>
            )}

            {/* Histórico */}
            <div className="bg-white rounded-xl shadow-sm p-5">
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">Solicitações</h3>
              {requests.length === 0 ? (
                <div className="text-center py-8 text-gray-400">
                  <Palmtree className="w-8 h-8 mx-auto mb-2 opacity-30" />
                  <p className="text-sm">Nenhuma solicitação de férias registrada.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {requests.map((r) => (
                    <div key={r.id} className="border border-gray-100 rounded-xl p-4">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-medium text-gray-900">{r.tipo || 'Férias'}</span>
                        <span className={`text-xs px-2 py-1 rounded-full font-medium ${statusColors[r.status || ''] || 'bg-gray-100 text-gray-600'}`}>
                          {r.status || 'pendente'}
                        </span>
                      </div>
                      <div className="flex items-center gap-4 text-sm text-gray-500">
                        <span>De {fmtDate(r.data_inicio)} até {fmtDate(r.data_fim)}</span>
                        {r.dias && <span className="font-medium text-blue-600">{r.dias} dias</span>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
