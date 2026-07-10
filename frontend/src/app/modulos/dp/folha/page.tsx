'use client';

import { useState, useEffect, useMemo } from 'react';
import { DollarSign, ArrowLeft, Inbox, Loader2, Search, ChevronLeft, ChevronRight as ChevronRightIcon, Calculator, RefreshCw, Banknote, X, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';

const API_BASE = '/api/v1/people-management';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const fmt = (v: number) => `R$ ${(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;

const statusConfig: Record<string, { label: string; className: string }> = {
  calculada: { label: 'Calculada', className: 'bg-green-500 text-white' },
  pendente: { label: 'Pendente', className: 'bg-yellow-500 text-white' },
  processando: { label: 'Processando', className: 'bg-blue-500 text-white' },
  erro: { label: 'Erro', className: 'bg-red-500 text-white' },
  calculated: { label: 'Calculada', className: 'bg-green-500 text-white' },
  pending: { label: 'Pendente', className: 'bg-yellow-500 text-white' },
  processing: { label: 'Processando', className: 'bg-blue-500 text-white' },
  error: { label: 'Erro', className: 'bg-red-500 text-white' },
};

const PAGE_SIZE = 12;

export default function FolhaPage() {
  const router = useRouter();
  const now = new Date();
  const prevMonth = now.getMonth() === 0 ? 12 : now.getMonth();
  const prevYear = now.getMonth() === 0 ? now.getFullYear() - 1 : now.getFullYear();
  const [periodo, setPeriodo] = useState(`${prevYear}-${String(prevMonth).padStart(2, '0')}`);
  const [dashboard, setDashboard] = useState<any>(null);
  const [rubricas, setRubricas] = useState<any[]>([]);
  const [resumo, setResumo] = useState<any>(null);
  const [employees, setEmployees] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [calculating, setCalculating] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [sortField, setSortField] = useState<string>('');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [refreshKey, setRefreshKey] = useState(0);

  // PIX Lote
  const [pixModalOpen, setPixModalOpen] = useState(false);
  const [pixLoading, setPixLoading] = useState(false);
  const [pixConfirming, setPixConfirming] = useState(false);
  const [pixSimulacao, setPixSimulacao] = useState<{ total_funcionarios: number; total_valor: number; prontos_para_pagar: number; sem_chave_pix: string[] } | null>(null);

  const [mes, ano] = useMemo(() => {
    const [y, m] = periodo.split('-');
    return [parseInt(m || '1'), parseInt(y || '2026')];
  }, [periodo]);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [dashRes, rubRes, resumoRes] = await Promise.all([
          fetch(`${API_BASE}/folha/dashboard?mes=${mes}&ano=${ano}`, { headers: getAuthHeaders() }).catch(() => null),
          fetch(`${API_BASE}/folha/rubricas`, { headers: getAuthHeaders() }).catch(() => null),
          fetch(`${API_BASE}/folha/resumo/${mes}/${ano}`, { headers: getAuthHeaders() }).catch(() => null),
        ]);

        if (dashRes?.ok) {
          const d = await dashRes.json();
          setDashboard(d);
          // Extract employees from dashboard if available
          const emps = d.funcionarios || d.employees || d.items || [];
          if (Array.isArray(emps) && emps.length > 0) {
            setEmployees(emps);
          }
        }

        if (rubRes?.ok) {
          const r = await rubRes.json();
          setRubricas(Array.isArray(r) ? r : r.items || r.rubricas || []);
        }

        if (resumoRes?.ok) {
          const s = await resumoRes.json();
          setResumo(s);
          // If employees came from resumo
          const resumoEmps = s.funcionarios || s.employees || s.detalhes || s.items || [];
          if (Array.isArray(resumoEmps) && resumoEmps.length > 0) {
            setEmployees(resumoEmps);
          }
        }

        // If no employees yet, try employees endpoint as fallback
        if (employees.length === 0) {
          const empRes = await fetch(`${API_BASE}/hr/employees?page_size=100`, { headers: getAuthHeaders() }).catch(() => null);
          if (empRes?.ok) {
            const empData = await empRes.json();
            const emps = empData.items || empData || [];
            setEmployees(emps);
          }
        }
      } catch {
        toast.error('Erro ao carregar dados da folha', { duration: 5000 });
      } finally {
        setLoading(false);
      }
    }
    load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [periodo, refreshKey]);

  useEffect(() => { setCurrentPage(1); }, [searchTerm]);

  const handleOpenPixModal = async () => {
    setPixModalOpen(true);
    setPixSimulacao(null);
    setPixLoading(true);
    try {
      const res = await fetch(`${API_BASE}/dp/payroll/pay-batch`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ mes_referencia: periodo, modo: 'simulacao' }),
      });
      if (res.ok) {
        const d = await res.json();
        setPixSimulacao(d);
      } else {
        toast.error('Erro ao buscar simulação PIX', { duration: 4000 });
        setPixModalOpen(false);
      }
    } catch {
      toast.error('Erro de conexão', { duration: 4000 });
      setPixModalOpen(false);
    } finally {
      setPixLoading(false);
    }
  };

  const handleConfirmPixPagamento = async () => {
    setPixConfirming(true);
    try {
      const res = await fetch(`${API_BASE}/dp/payroll/pay-batch`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ mes_referencia: periodo, modo: 'execucao' }),
      });
      if (res.ok) {
        const d = await res.json();
        const total = d.total_valor ?? pixSimulacao?.total_valor ?? 0;
        const funcs = d.total_funcionarios ?? pixSimulacao?.total_funcionarios ?? 0;
        toast.success(`PIX agendado: ${funcs} funcionários · ${fmt(total)}`, { duration: 6000 });
        setPixModalOpen(false);
        setRefreshKey(k => k + 1);
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao processar pagamento PIX', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexão ao processar PIX', { duration: 5000 });
    } finally {
      setPixConfirming(false);
    }
  };

  const handleCalculatePayroll = async () => {
    setCalculating(true);
    try {
      const res = await fetch(`${API_BASE}/folha/calcular/todos/${mes}/${ano}`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        toast.success(`Folha de ${String(mes).padStart(2, '0')}/${ano} calculada com sucesso!`, { duration: 4000 });
        setRefreshKey(k => k + 1);
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao calcular folha', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexão ao calcular folha', { duration: 5000 });
    } finally {
      setCalculating(false);
    }
  };

  // Filtered + searched + sorted
  const filteredData = useMemo(() => {
    let items = [...employees];
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      items = items.filter(e =>
        (e.nome || e.name || e.candidate_name || e.employee_name || '').toLowerCase().includes(term) ||
        (e.cargo || e.position || '').toLowerCase().includes(term) ||
        (e.cpf || '').includes(term)
      );
    }
    if (sortField) {
      items = [...items].sort((a, b) => {
        const va = typeof a[sortField] === 'number' ? a[sortField] : String(a[sortField] || '').toLowerCase();
        const vb = typeof b[sortField] === 'number' ? b[sortField] : String(b[sortField] || '').toLowerCase();
        if (typeof va === 'number' && typeof vb === 'number') return sortDir === 'asc' ? va - vb : vb - va;
        return sortDir === 'asc' ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
      });
    }
    return items;
  }, [employees, searchTerm, sortField, sortDir]);

  // Mostrar botão PIX apenas quando há holerites published
  const hasPublishedPayslips = employees.some(e =>
    e.payslip_status === 'published' ||
    e.status_folha === 'calculada' ||
    e.payroll_status === 'calculated'
  );

  const totalPages = Math.max(1, Math.ceil(filteredData.length / PAGE_SIZE));
  const paginatedData = filteredData.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const handleSort = (field: string) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  };

  const sortIcon = (field: string) => {
    if (sortField !== field) return ' ↕';
    return sortDir === 'asc' ? ' ↑' : ' ↓';
  };

  // Summary values from dashboard/resumo or computed
  // BUG-02 fix: backend retorna total_proventos, não total_bruto
  // [Veracidade] Sem resumo/dashboard da folha, o total é 0 ("aguardando dado") —
  // NUNCA somar salario_base do cadastro como se fosse folha (dado incompleto, não é folha).
  const totalBruto = resumo?.total_proventos ?? dashboard?.total_proventos ?? resumo?.total_bruto ?? dashboard?.total_bruto ?? employees.reduce((a, e) => a + (e.total_proventos || e.salario_bruto || 0), 0);
  const totalDescontos = resumo?.total_descontos || dashboard?.total_descontos || employees.reduce((a, e) => a + (e.total_descontos || 0), 0);
  const totalLiquido = resumo?.total_liquido || dashboard?.total_liquido || (totalBruto - totalDescontos);
  const totalInss = resumo?.total_inss || dashboard?.total_inss || 0;
  const totalFgts = resumo?.total_fgts || dashboard?.total_fgts || 0;
  const totalIrrf = resumo?.total_irrf || dashboard?.total_irrf || 0;

  const summaryCards = [
    { title: 'Total Bruto (Proventos)', value: fmt(totalBruto), color: 'text-blue-600' },
    { title: 'Total Descontos', value: fmt(totalDescontos), color: 'text-red-600' },
    { title: 'Total Líquido (A Pagar)', value: fmt(totalLiquido), color: 'text-green-600' },
    { title: 'Total INSS', value: fmt(totalInss), color: 'text-purple-600' },
    { title: 'Total FGTS 8%', value: fmt(totalFgts), color: 'text-cyan-600' },
    { title: 'Total IRRF', value: fmt(totalIrrf), color: 'text-orange-600' },
  ];

  return (
    <div className="space-y-6 pb-28">
      <PageHeader
        icon={<DollarSign className="h-5 w-5" />}
        title="Folha de Pagamento"
        subtitle="Folha salarial e encargos trabalhistas"
        actions={(
          <>
            <Button type="button" variant="ghost" size="sm" onClick={() => router.push('/modulos/dp')}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <input
              type="month"
              value={periodo}
              onChange={(e) => setPeriodo(e.target.value)}
              className="rounded-md border px-3 py-2 text-sm bg-background"
            />
            <Button
              type="button"
              size="sm"
              disabled={calculating}
              onClick={handleCalculatePayroll}
            >
              {calculating ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Calculator className="h-4 w-4 mr-1" />}
              {calculating ? 'Calculando...' : 'Calcular Folha'}
            </Button>
            {hasPublishedPayslips && (
              <Button
                type="button"
                size="sm"
                className="bg-blue-600 hover:bg-blue-700 text-white"
                disabled={loading}
                onClick={handleOpenPixModal}
              >
                <Banknote className="h-4 w-4 mr-1" />
                💸 Pagar em Lote (PIX)
              </Button>
            )}
            <Button type="button" variant="outline" size="sm" onClick={() => setRefreshKey(k => k + 1)}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </>
        )}
      />

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <>
          {/* Summary Cards */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            {summaryCards.map((card) => (
              <Card key={card.title}>
                <CardContent className="pt-6">
                  <p className="text-sm text-muted-foreground">{card.title}</p>
                  <p className={`font-data text-2xl font-semibold tabular-nums ${card.color}`}>{card.value}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Rubricas summary */}
          {rubricas.length > 0 && (
            <Card>
              <CardHeader><CardTitle>Rubricas</CardTitle></CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {rubricas.slice(0, 10).map((r: any, i: number) => (
                    <Badge key={i} variant="outline" className="text-xs">
                      {r.codigo || r.code || `R${i + 1}`} - {r.descricao || r.description || r.nome || r.name || 'N/A'}
                    </Badge>
                  ))}
                  {rubricas.length > 10 && (
                    <Badge variant="secondary" className="text-xs">+{rubricas.length - 10} rubricas</Badge>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Employee Payroll Table */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Detalhamento por Colaborador</CardTitle>
                <div className="relative w-64">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <input
                    type="text"
                    value={searchTerm}
                    onChange={e => setSearchTerm(e.target.value)}
                    placeholder="Buscar por nome, cargo ou CPF..."
                    className="w-full pl-9 pr-3 py-2 border rounded-md text-sm"
                  />
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {filteredData.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                  <Inbox className="h-12 w-12 mb-3" />
                  <p className="font-medium">Nenhum registro na folha para este periodo</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    {searchTerm ? 'Tente outra busca.' : 'Clique em "Calcular Folha" para processar o periodo.'}
                  </p>
                </div>
              ) : (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="cursor-pointer select-none" onClick={() => handleSort('nome')}>Colaborador{sortIcon('nome')}</TableHead>
                        <TableHead className="cursor-pointer select-none" onClick={() => handleSort('cargo')}>Cargo{sortIcon('cargo')}</TableHead>
                        <TableHead className="cursor-pointer select-none" onClick={() => handleSort('salario_base')}>Salário Base{sortIcon('salario_base')}</TableHead>
                        <TableHead>INSS</TableHead>
                        <TableHead>FGTS 8%</TableHead>
                        <TableHead className="cursor-pointer select-none" onClick={() => handleSort('total_descontos')}>Descontos{sortIcon('total_descontos')}</TableHead>
                        <TableHead className="cursor-pointer select-none" onClick={() => handleSort('salario_liquido')}>Liquido{sortIcon('salario_liquido')}</TableHead>
                        <TableHead>Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {paginatedData.map((item, i) => {
                        const nome = item.nome || item.name || item.employee_name || item.candidate_name || '-';
                        const cargo = item.cargo || item.position || '-';
                        const salBase = item.salario_base || item.salary || item.salary_proposed || 0;
                        const inssVal = item.inss_value ?? item.inss ?? (item.descontos || []).find?.((d: any) => d.descricao?.includes('INSS'))?.valor ?? 0;
                        const fgtsVal = item.fgts_value ?? item.fgts_8_pct ?? item.fgts ?? 0;
                        const descVal = item.total_descontos || 0;
                        const liqVal = item.salario_liquido || item.net_salary || (salBase - descVal);
                        const status = item.status_folha || item.payroll_status || (item.salario_liquido ? 'calculada' : 'pendente');
                        const st = statusConfig[status] || { label: status || 'N/A', className: 'bg-gray-500 text-white' };
                        return (
                          <TableRow key={item.id || i}>
                            <TableCell className="font-medium">{nome}</TableCell>
                            <TableCell>{cargo}</TableCell>
                            <TableCell>{fmt(salBase)}</TableCell>
                            <TableCell className="text-red-500">{fmt(inssVal)}</TableCell>
                            <TableCell className="text-cyan-600">{fmt(fgtsVal)}</TableCell>
                            <TableCell className="text-red-500">{fmt(descVal)}</TableCell>
                            <TableCell className="font-bold">{fmt(liqVal)}</TableCell>
                            <TableCell><Badge className={st.className}>{st.label}</Badge></TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>

                  {/* Pagination */}
                  <div className="flex items-center justify-between mt-4 text-sm">
                    <span className="text-muted-foreground">
                      {filteredData.length} registro{filteredData.length !== 1 ? 's' : ''} — Pagina {currentPage} de {totalPages}
                    </span>
                    <div className="flex gap-1">
                      <Button variant="outline" size="sm" disabled={currentPage <= 1} onClick={() => setCurrentPage(p => p - 1)}>
                        <ChevronLeft className="h-4 w-4" />
                      </Button>
                      {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                        const page = totalPages <= 5 ? i + 1 : Math.max(1, Math.min(currentPage - 2, totalPages - 4)) + i;
                        return (
                          <Button key={page} variant={currentPage === page ? 'default' : 'outline'} size="sm" onClick={() => setCurrentPage(page)}>
                            {page}
                          </Button>
                        );
                      })}
                      <Button variant="outline" size="sm" disabled={currentPage >= totalPages} onClick={() => setCurrentPage(p => p + 1)}>
                        <ChevronRightIcon className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {/* Modal PIX Lote */}
      {pixModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <Banknote className="h-5 w-5 text-blue-600" />
                Pagar em Lote via PIX
              </h2>
              <button
                type="button"
                onClick={() => setPixModalOpen(false)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="mb-4">
              <p className="text-sm text-muted-foreground mb-1">Mês de referência</p>
              <p className="font-medium">{periodo}</p>
            </div>

            {pixLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
                <span className="ml-2 text-sm text-muted-foreground">Buscando simulação...</span>
              </div>
            ) : pixSimulacao ? (
              <>
                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div className="bg-blue-50 dark:bg-blue-950/30 rounded-lg p-3 text-center">
                    <p className="font-data text-2xl font-semibold tabular-nums text-blue-600">{pixSimulacao.prontos_para_pagar}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">Funcionários prontos</p>
                  </div>
                  <div className="bg-green-50 dark:bg-green-950/30 rounded-lg p-3 text-center">
                    <p className="font-data text-2xl font-semibold tabular-nums text-green-600">{fmt(pixSimulacao.total_valor)}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">Total a pagar</p>
                  </div>
                </div>

                {pixSimulacao.sem_chave_pix && pixSimulacao.sem_chave_pix.length > 0 && (
                  <div className="flex items-start gap-2 bg-yellow-50 dark:bg-yellow-950/30 border border-yellow-200 rounded-lg p-3 mb-4">
                    <AlertTriangle className="h-4 w-4 text-yellow-600 mt-0.5 flex-shrink-0" />
                    <p className="text-xs text-yellow-700 dark:text-yellow-400">
                      {pixSimulacao.sem_chave_pix.length} funcionário(s) sem chave PIX serão ignorados.
                    </p>
                  </div>
                )}

                <p className="text-xs text-muted-foreground mb-4">
                  Ao confirmar, os pagamentos PIX serão agendados para todos os funcionários com holerite publicado e chave PIX cadastrada.
                </p>

                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    className="flex-1"
                    onClick={() => setPixModalOpen(false)}
                    disabled={pixConfirming}
                  >
                    Cancelar
                  </Button>
                  <Button
                    type="button"
                    className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
                    onClick={handleConfirmPixPagamento}
                    disabled={pixConfirming}
                  >
                    {pixConfirming ? (
                      <><Loader2 className="h-4 w-4 animate-spin mr-1" /> Processando...</>
                    ) : (
                      <><Banknote className="h-4 w-4 mr-1" /> Confirmar Pagamento</>
                    )}
                  </Button>
                </div>
              </>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
