'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Fingerprint, ArrowLeft, ShieldCheck, LogOut, Loader2, AlertCircle, LogIn, LogOut as LogOutIcon, Timer } from 'lucide-react';

const API_BASE = '/api/v1/people-management/portal';

function getPortalHeaders(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('portal_token') : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

// Contrato REAL: my_ponto_controller
interface Registro {
  id: string;
  tipo: string;
  data_hora: string;
  localizacao?: string | null;
  observacao?: string | null;
  horas?: number;
}
interface HistoricoResponse {
  employee_id: string;
  mes: number;
  ano: number;
  total_registros: number;
  registros: Registro[];
}
interface BancoHorasResponse {
  employee_id: string;
  saldo_horas: number;
  total_entradas: number;
  ultimas_entradas: { data: string; tipo: string; horas: number; descricao: string | null }[];
}

const fmtDateTime = (d: string) => {
  const dt = new Date(d.replace(' ', 'T'));
  return isNaN(dt.getTime()) ? d : dt.toLocaleString('pt-BR');
};

export default function PontoPage() {
  const router = useRouter();
  const [employeeName, setEmployeeName] = useState('');
  const [historico, setHistorico] = useState<HistoricoResponse | null>(null);
  const [banco, setBanco] = useState<BancoHorasResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const token = localStorage.getItem('portal_token');
    if (!token) { router.push('/portal-funcionario/login'); return; }
    setEmployeeName(localStorage.getItem('portal_employee_name') || 'Funcionário');
    load();
  }, [router]);

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [hRes, bRes] = await Promise.all([
        fetch(`${API_BASE}/ponto/historico`, { headers: getPortalHeaders() }),
        fetch(`${API_BASE}/banco-horas`, { headers: getPortalHeaders() }),
      ]);
      if (hRes.ok) setHistorico(await hRes.json());
      if (bRes.ok) setBanco(await bRes.json());
      if (!hRes.ok && !bRes.ok) setError('Não foi possível carregar ponto e banco de horas.');
    } catch {
      setError('Erro ao carregar ponto.');
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

  const isEntrada = (t: string) => /entrada|entry|in/i.test(t);

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
            <Fingerprint className="w-5 h-5 text-cyan-600" /> Ponto e Banco de Horas
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
          <div className="space-y-5">
            {banco && (
              <div className="bg-white rounded-xl shadow-sm p-5 flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-500 flex items-center gap-1"><Timer className="w-4 h-4" /> Saldo do banco de horas</p>
                  <p className={`text-2xl font-bold ${banco.saldo_horas >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                    {banco.saldo_horas >= 0 ? '+' : ''}{banco.saldo_horas.toFixed(2)}h
                  </p>
                </div>
                <span className="text-xs text-gray-400">{banco.total_entradas} lançamentos</span>
              </div>
            )}

            <section>
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
                Registros de ponto {historico ? `(${historico.mes}/${historico.ano})` : ''}
              </h3>
              {historico && historico.registros.length > 0 ? (
                <div className="space-y-2">
                  {historico.registros.map((r) => (
                    <div key={r.id} className="bg-white rounded-xl shadow-sm p-4 flex items-center gap-3">
                      <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${isEntrada(r.tipo) ? 'bg-green-50 text-green-600' : 'bg-orange-50 text-orange-600'}`}>
                        {isEntrada(r.tipo) ? <LogIn className="w-4 h-4" /> : <LogOutIcon className="w-4 h-4" />}
                      </div>
                      <div className="flex-1">
                        <p className="font-medium text-gray-900 capitalize">{r.tipo}</p>
                        <p className="text-xs text-gray-500">{fmtDateTime(r.data_hora)}{r.localizacao ? ` · ${r.localizacao}` : ''}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="bg-white rounded-xl shadow-sm p-8 text-center text-gray-400">
                  <Fingerprint className="w-10 h-10 mx-auto mb-2 opacity-30" />
                  <p>Nenhum registro de ponto neste mês.</p>
                </div>
              )}
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
