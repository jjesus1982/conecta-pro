'use client';

import { useState, useEffect, useCallback } from 'react';
import { Award, AlertTriangle, CheckCircle, XCircle, Loader2, Search, ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { PageHeader } from '@/components/ui/page-header';
import { toast } from 'sonner';

const API_BASE = '/api/v1/people-management/human-resources';

function getAuthHeaders() {
  let token: string | null = null;
  if (typeof window !== 'undefined') {
    try {
      token = localStorage.getItem('access_token') || localStorage.getItem('token');
    } catch {
      token = null;
    }
  }
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const tabs = ['Validos', 'Vencendo', 'Vencidos'] as const;
const tabFilter: Record<string, string[]> = {
  'Validos': ['valid', 'Valido'],
  'Vencendo': ['expiring', 'Vencendo'],
  'Vencidos': ['expired', 'Vencido'],
};

const statusCores: Record<string, string> = {
  'valid': 'text-green-400', 'Valido': 'text-green-400',
  'expiring': 'text-yellow-400', 'Vencendo': 'text-yellow-400',
  'expired': 'text-red-400', 'Vencido': 'text-red-400',
};

const statusLabels: Record<string, string> = {
  valid: 'Valido', expiring: 'Vencendo', expired: 'Vencido',
};

const fmtDate = (v?: string | null) => {
  if (!v) return '—';
  try { return new Date(v).toLocaleDateString('pt-BR'); } catch { return v; }
};

const StatusIcon = ({ status }: { status: string }) => {
  if (status === 'valid' || status === 'Valido') return <CheckCircle className="h-4 w-4 text-green-400" />;
  if (status === 'expiring' || status === 'Vencendo') return <AlertTriangle className="h-4 w-4 text-yellow-400" />;
  return <XCircle className="h-4 w-4 text-red-400" />;
};

export default function CertificadosPage() {
  const [activeTab, setActiveTab] = useState<string>('Validos');
  const [certificados, setCertificados] = useState<any[]>([]);
  const [expiring, setExpiring] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [enrRes, expRes] = await Promise.all([
        fetch(`${API_BASE}/training/certificates?page_size=200`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/training/certificates/expiring`, { headers: getAuthHeaders() }),
      ]);
      if (enrRes.ok) {
        const data = await enrRes.json();
        setCertificados(data.items || data || []);
      } else {
        toast.error('Erro ao carregar certificados', { duration: 5000 });
      }
      if (expRes.ok) {
        const data = await expRes.json();
        setExpiring(data.items || data || []);
      }
    } catch {
      toast.error('Erro de conexao ao carregar certificados', { duration: 5000 });
      setCertificados([]);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const tabFiltered = certificados.filter((c: any) => tabFilter[activeTab]?.includes(c.status));

  const filtered = tabFiltered.filter((c: any) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (c.employee_name || c.colaborador || '').toLowerCase().includes(s) ||
           (c.course_name || c.curso || '').toLowerCase().includes(s) ||
           (c.certificate_number || c.numero || '').toLowerCase().includes(s);
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paginatedData = filtered.slice((page - 1) * pageSize, page * pageSize);

  return (
    <div className="space-y-6 pb-28">
      <PageHeader
        icon={<Award className="h-5 w-5" />}
        title="Certificados"
        subtitle="Controle de certificados dos colaboradores"
      />

      {loading ? (
        <div className="flex items-center justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
      ) : (
        <>
          {expiring.length > 0 && (
            <Card className="border-yellow-800 bg-yellow-900/10">
              <CardContent className="pt-4">
                <div className="flex items-center gap-2 text-yellow-400">
                  <AlertTriangle className="h-5 w-5" />
                  <span className="font-medium">{expiring.length} certificado(s) vencendo nos proximos 30 dias</span>
                </div>
                <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                  {expiring.slice(0, 5).map((c: any, i: number) => <li key={i}>{c.employee_name || c.colaborador} - {c.course_name || c.curso} (validade: {fmtDate(c.expires_at || c.validade)})</li>)}
                </ul>
              </CardContent>
            </Card>
          )}

          <div className="flex gap-2 border-b border-gray-800 pb-0">
            {tabs.map(tab => (
              <button type="button" key={tab} onClick={() => { setActiveTab(tab); setPage(1); }}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === tab ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-white'}`}>
                {tab} ({certificados.filter((c: any) => tabFilter[tab]?.includes(c.status)).length})
              </button>
            ))}
          </div>

          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Buscar por colaborador, curso ou numero..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm"
            />
          </div>

          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-800">
                      <th className="text-left p-4 text-muted-foreground font-medium">Colaborador</th>
                      <th className="text-left p-4 text-muted-foreground font-medium">Curso</th>
                      <th className="text-left p-4 text-muted-foreground font-medium">Numero</th>
                      <th className="text-left p-4 text-muted-foreground font-medium">Emissao</th>
                      <th className="text-left p-4 text-muted-foreground font-medium">Validade</th>
                      <th className="text-center p-4 text-muted-foreground font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedData.length === 0 ? (
                      <tr><td colSpan={6} className="p-8 text-center text-muted-foreground">Nenhum certificado nesta categoria</td></tr>
                    ) : paginatedData.map((c: any, i: number) => {
                      const label = statusLabels[c.status] || c.status;
                      return (
                        <tr key={c.id || i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                          <td className="p-4 font-medium">{c.employee_name || c.colaborador}</td>
                          <td className="p-4 text-muted-foreground">{c.course_name || c.curso}</td>
                          <td className="p-4 text-muted-foreground font-mono text-xs">{c.certificate_number || c.numero}</td>
                          <td className="p-4 text-muted-foreground">{fmtDate(c.issued_at || c.emissao)}</td>
                          <td className="p-4 text-muted-foreground">{fmtDate(c.expires_at || c.validade)}</td>
                          <td className="p-4 text-center"><div className="flex items-center justify-center gap-1"><StatusIcon status={c.status} /><span className={statusCores[c.status] || 'text-gray-400'}>{label}</span></div></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Mostrando {((page - 1) * pageSize) + 1}-{Math.min(page * pageSize, filtered.length)} de {filtered.length}
              </p>
              <div className="flex items-center gap-2">
                <button type="button" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="p-2 rounded hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed">
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <span className="text-sm">Pagina {page} de {totalPages}</span>
                <button type="button" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} className="p-2 rounded hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed">
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
