'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Megaphone, ArrowLeft, ShieldCheck, LogOut, Loader2, AlertCircle } from 'lucide-react';

const API_BASE = '/api/v1/people-management/portal';

function getPortalHeaders(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('portal_token') : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

// Contrato REAL: my_comunicados_controller
interface Comunicado {
  id: string;
  titulo: string;
  mensagem: string;
  lido: boolean;
  data: string;
}

const fmtDate = (d: string) => {
  const dt = new Date(d);
  return isNaN(dt.getTime()) ? d : dt.toLocaleDateString('pt-BR');
};

export default function ComunicadosPage() {
  const router = useRouter();
  const [employeeName, setEmployeeName] = useState('');
  const [comunicados, setComunicados] = useState<Comunicado[]>([]);
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
      const res = await fetch(`${API_BASE}/comunicados`, { headers: getPortalHeaders() });
      if (res.ok) {
        const data = await res.json();
        setComunicados(Array.isArray(data.comunicados) ? data.comunicados : []);
      } else {
        setError('Não foi possível carregar os comunicados.');
      }
    } catch {
      setError('Erro ao carregar comunicados.');
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
            <Megaphone className="w-5 h-5 text-rose-600" /> Comunicados
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
        ) : comunicados.length === 0 ? (
          <div className="bg-white rounded-xl shadow-sm p-8 text-center text-gray-400">
            <Megaphone className="w-10 h-10 mx-auto mb-2 opacity-30" />
            <p>Nenhum comunicado no momento.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {comunicados.map((c) => (
              <div key={c.id} className={`bg-white rounded-xl shadow-sm p-4 border-l-4 ${c.lido ? 'border-gray-200' : 'border-rose-400'}`}>
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-gray-900">{c.titulo}</p>
                  {!c.lido && <span className="text-xs px-2 py-0.5 rounded-full bg-rose-50 text-rose-600 whitespace-nowrap">Novo</span>}
                </div>
                <p className="text-sm text-gray-600 mt-1">{c.mensagem}</p>
                <p className="text-xs text-gray-400 mt-2">{fmtDate(c.data)}</p>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
