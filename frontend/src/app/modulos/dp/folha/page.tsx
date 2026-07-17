'use client';

import { useState, useEffect, useMemo } from 'react';
import { msgFromDetail } from '@/lib/string';
import { DollarSign, ArrowLeft, Inbox, Loader2, Search, ChevronLeft, ChevronRight as ChevronRightIcon, Calculator, RefreshCw, Banknote, X, AlertTriangle, FileText, FileDown } from 'lucide-react';
import { toast } from 'sonner';
import { baixarArquivoAutenticado } from '@/utils/baixarArquivoAutenticado';
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
  published: { label: 'Calculada', className: 'bg-green-500 text-white' },
  paid: { label: 'Pago', className: 'bg-emerald-600 text-white' },
  sem_folha: { label: 'Sem folha', className: 'bg-slate-400 text-white' },
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

  // Mapa employee_id -> payslip_id (contracheque publicado) do período, para o botão de download por linha.
  const [payslipMap, setPayslipMap] = useState<Record<string, string>>({});
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [exportandoFolha, setExportandoFolha] = useState(false);

  // PIX Lote
  const [pixModalOpen, setPixModalOpen] = useState(false);
  const [pixLoading, setPixLoading] = useState(false);
  const [pixConfirming, setPixConfirming] = useState(false);
  const [pixSimulacao, setPixSimulacao] = useState<{
    total_funcionarios: number;
    total_valor: number;
    prontos_para_pagar: number;
    sem_chave_pix: string[];
    excluidos?: { nome: string; valor_liquido: number; motivo: string }[];
    total_excluidos_qtd?: number;
    total_excluidos_valor?: number;
    total_folha_qtd?: number;
    total_folha_valor?: number;
    reconcilia?: boolean;
  } | null>(null);

  const [mes, ano] = useMemo(() => {
    const [y, m] = periodo.split('-');
    return [parseInt(m || '1'), parseInt(y || '2026')];
  }, [periodo]);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [dashRes, rubRes, resumoRes, payslipsRes] = await Promise.all([
          fetch(`${API_BASE}/folha/dashboard?mes=${mes}&ano=${ano}`, { headers: getAuthHeaders() }).catch(() => null),
          fetch(`${API_BASE}/folha/rubricas`, { headers: getAuthHeaders() }).catch(() => null),
          fetch(`${API_BASE}/folha/resumo/${mes}/${ano}`, { headers: getAuthHeaders() }).catch(() => null),
          // Lista de contracheques do período → mapa employee_id -> payslip_id (botão Contracheque por linha).
          fetch(`${API_BASE}/dp/payslips/?mes=${mes}&ano=${ano}&page_size=100`, { headers: getAuthHeaders() }).catch(() => null),
        ]);

        // Constrói o mapa employee_id -> payslip_id (último contracheque do período por colaborador).
        if (payslipsRes?.ok) {
          try {
            const pd = await payslipsRes.json();
            const list: any[] = pd.payslips || pd.items || (Array.isArray(pd) ? pd : []);
            const map: Record<string, string> = {};
            for (const p of list) {
              const eid = p.employee_id;
              if (eid && p.id && !map[eid]) map[eid] = p.id;
            }
            setPayslipMap(map);
          } catch {
            setPayslipMap({});
          }
        } else {
          setPayslipMap({});
        }

        // A tabela de "Detalhamento por Colaborador" DEVE ler os holerites reais
        // (dashboard/resumo.funcionarios trazem inss_value/fgts_value/total_descontos/
        // salario_liquido por pessoa). Só cai no fallback /hr/employees (cadastro, SEM
        // valores de folha) quando NÃO existe folha para o período — nunca sobrescrevendo
        // os holerites reais por 50 linhas zeradas (bug da reconciliação cabeçalho×tabela).
        let payrollEmployees: any[] = [];

        if (dashRes?.ok) {
          const d = await dashRes.json();
          setDashboard(d);
          const emps = d.funcionarios || d.employees || d.items || [];
          if (Array.isArray(emps) && emps.length > 0) {
            payrollEmployees = emps;
          }
        }

        if (rubRes?.ok) {
          const r = await rubRes.json();
          setRubricas(Array.isArray(r) ? r : r.items || r.rubricas || []);
        }

        if (resumoRes?.ok) {
          const s = await resumoRes.json();
          setResumo(s);
          // Resumo é a fonte canônica dos cards; usa suas linhas se o dashboard não trouxe.
          const resumoEmps = s.funcionarios || s.employees || s.detalhes || s.items || [];
          if (payrollEmployees.length === 0 && Array.isArray(resumoEmps) && resumoEmps.length > 0) {
            payrollEmployees = resumoEmps;
          }
        }

        if (payrollEmployees.length > 0) {
          // Folha real do período → tabela reconcilia com os cards.
          setEmployees(payrollEmployees);
        } else {
          // Sem folha no período: fallback ao cadastro (SEM valores de folha).
          // Marcado com _sem_folha para a tabela rotular honestamente ("aguardando folha").
          const empRes = await fetch(`${API_BASE}/hr/employees?page_size=100`, { headers: getAuthHeaders() }).catch(() => null);
          if (empRes?.ok) {
            const empData = await empRes.json();
            const emps = (empData.items || empData || []).map((e: any) => ({ ...e, _sem_folha: true }));
            setEmployees(Array.isArray(emps) ? emps : []);
          } else {
            setEmployees([]);
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
        // NÃO diz "pago/agendado" — o lote só fica PENDENTE. O dinheiro só sai no passo de
        // pagamento via Inter, que exige OTP. Deixar claro pra ninguém achar que já pagou.
        toast.success(`Lote registrado como PENDENTE: ${funcs} funcionários · ${fmt(total)}. Nenhum PIX foi enviado — o pagamento exige aprovação com OTP.`, { duration: 8000 });
        setPixModalOpen(false);
        setRefreshKey(k => k + 1);
      } else {
        const err = await res.json().catch(() => null);
        toast.error(msgFromDetail(err?.detail) || 'Erro ao processar pagamento PIX', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexão ao processar PIX', { duration: 5000 });
    } finally {
      setPixConfirming(false);
    }
  };

  const handleBaixarContracheque = async (payslipId: string, nome: string) => {
    setDownloadingId(payslipId);
    try {
      await baixarArquivoAutenticado(
        `/api/v1/people-management/dp/payslips/${payslipId}/pdf`,
        `contracheque_${((nome || 'colaborador').split(' ')[0] || 'colaborador').toLowerCase()}_${String(mes).padStart(2, '0')}_${ano}.pdf`,
      );
      toast.success('Contracheque baixado', { duration: 3000 });
    } catch (e: any) {
      toast.error(e?.message || 'Erro ao baixar contracheque', { duration: 5000 });
    } finally {
      setDownloadingId(null);
    }
  };

  const handleBaixarVtVr = async (empId: string, nome: string) => {
    try {
      await baixarArquivoAutenticado(
        `/api/v1/people-management/folha/recibo-vt-vr/${empId}/${mes}/${ano}/pdf`,
        `vt-vr_${((nome || 'colaborador').split(' ')[0] || 'colaborador').toLowerCase()}_${String(mes).padStart(2, '0')}_${ano}.pdf`,
      );
      toast.success('Recibo VT/VR baixado', { duration: 3000 });
    } catch (e: any) {
      toast.error(e?.message || 'Erro ao baixar recibo VT/VR', { duration: 5000 });
    }
  };

  const handleExportarFolha = async () => {
    setExportandoFolha(true);
    try {
      await baixarArquivoAutenticado(
        `/api/v1/people-management/folha/${mes}/${ano}/pdf`,
        `folha_${ano}_${String(mes).padStart(2, '0')}.pdf`,
      );
      toast.success('Folha exportada em PDF', { duration: 3000 });
    } catch (e: any) {
      toast.error(e?.message || 'Erro ao exportar folha', { duration: 5000 });
    } finally {
      setExportandoFolha(false);
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
        toast.error(msgFromDetail(err?.detail) || 'Erro ao calcular folha', { duration: 5000 });
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

  // Fonte da folha (dashboard/resumo): distingue REAL importada × ESTIMATIVA da engine.
  // portte_contabil / dominio_sistemas / importada = REAL (hr_payslips);
  // folha_propria_cct_a_conciliar = ESTIMATIVA (motor CCT interno).
  const fonteFolha: string = resumo?.fonte || dashboard?.fonte || '';
  const fonteInfo = useMemo(() => {
    const f = (fonteFolha || '').toLowerCase();
    if (!f) return null;
    if (f.includes('portte')) return { real: true, label: 'REAL · Portte Contábil', className: 'bg-green-600 text-white' };
    if (f.includes('dominio')) return { real: true, label: 'REAL · Domínio Sistemas', className: 'bg-green-600 text-white' };
    if (f === 'importada') return { real: true, label: 'REAL · Folha importada', className: 'bg-green-600 text-white' };
    if (f.includes('propria') || f.includes('cct') || f.includes('estimativa'))
      return { real: false, label: 'ESTIMATIVA · Motor CCT (a conciliar)', className: 'bg-amber-500 text-white' };
    return { real: true, label: `Fonte: ${fonteFolha}`, className: 'bg-slate-600 text-white' };
  }, [fonteFolha]);

  // Mostrar botão PIX apenas quando há holerites REAIS published (não estimativa).
  const hasPublishedPayslips = (fonteInfo?.real ?? false) && employees.some(e =>
    e.payslip_status === 'published' ||
    e.status === 'published' ||
    e.status_folha === 'calculada' ||
    e.payroll_status === 'calculated' ||
    e.net_salary != null ||
    e.salario_liquido != null
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
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={exportandoFolha || loading}
              onClick={handleExportarFolha}
              title="Exportar a folha inteira do período em PDF"
            >
              {exportandoFolha ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <FileDown className="h-4 w-4 mr-1" />}
              {exportandoFolha ? 'Exportando...' : 'Exportar folha (PDF)'}
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
          {/* Badge de fonte: REAL (Portte/hr_payslips) × ESTIMATIVA (motor CCT) */}
          {fonteInfo && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Fonte da folha:</span>
              <Badge className={fonteInfo.className}>{fonteInfo.label}</Badge>
              {!fonteInfo.real && (
                <span className="text-xs text-amber-600">
                  Valores calculados pela engine — ainda não conciliados com a contabilidade.
                </span>
              )}
            </div>
          )}

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
                        <TableHead className="text-right">Contracheque</TableHead>
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
                        // ?? (não ||): net_salary = 0,00 é VALOR legítimo (ex.: suspenso com
                        // descontos = proventos). Com || o zero caía no fallback salBase−desc
                        // e virava líquido NEGATIVO (-R$68,99). E clamp: nunca exibir < 0.
                        const liqRaw = item.salario_liquido ?? item.net_salary ?? (salBase - descVal);
                        const liqVal = Math.max(0, Number(liqRaw) || 0);
                        // Linha de fallback (cadastro, sem folha do período) → rótulo honesto.
                        const status = item._sem_folha
                          ? 'sem_folha'
                          : (item.status_folha || item.payroll_status || item.status || (liqVal ? 'calculada' : 'pendente'));
                        const st = statusConfig[status] || { label: status || 'N/A', className: 'bg-gray-500 text-white' };
                        const empId = item.employee_id || item.id || '';
                        const payslipId = payslipMap[empId];
                        return (
                          <TableRow key={item.id || empId || i}>
                            <TableCell className="font-medium">{nome}</TableCell>
                            <TableCell>{cargo}</TableCell>
                            <TableCell>{fmt(salBase)}</TableCell>
                            <TableCell className="text-red-500">{fmt(inssVal)}</TableCell>
                            <TableCell className="text-cyan-600">{fmt(fgtsVal)}</TableCell>
                            <TableCell className="text-red-500">{fmt(descVal)}</TableCell>
                            <TableCell className="font-bold">{fmt(liqVal)}</TableCell>
                            <TableCell><Badge className={st.className}>{st.label}</Badge></TableCell>
                            <TableCell className="text-right">
                              <div className="inline-flex gap-1 justify-end">
                                {payslipId ? (
                                  <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    disabled={downloadingId === payslipId}
                                    onClick={() => handleBaixarContracheque(payslipId, nome)}
                                    title="Baixar contracheque em PDF"
                                  >
                                    {downloadingId === payslipId
                                      ? <Loader2 className="h-4 w-4 animate-spin" />
                                      : <FileText className="h-4 w-4" />}
                                    <span className="ml-1 hidden sm:inline">Contracheque</span>
                                  </Button>
                                ) : (
                                  <span className="text-xs text-muted-foreground self-center">—</span>
                                )}
                                {empId ? (
                                  <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleBaixarVtVr(empId, nome)}
                                    title="Baixar recibo VT/VR em PDF"
                                  >
                                    <FileDown className="h-4 w-4" />
                                    <span className="ml-1 hidden sm:inline">VT/VR</span>
                                  </Button>
                                ) : null}
                              </div>
                            </TableCell>
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
          <div className="bg-background rounded-xl shadow-xl w-full max-w-lg mx-4 p-6 max-h-[90vh] overflow-y-auto">
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

                {/* Excluídos do lote — NUNCA silencioso: lista nome, valor e motivo */}
                {pixSimulacao.excluidos && pixSimulacao.excluidos.length > 0 && (
                  <div className="bg-yellow-50 dark:bg-yellow-950/30 border border-yellow-200 rounded-lg p-3 mb-4">
                    <div className="flex items-center gap-2 mb-2">
                      <AlertTriangle className="h-4 w-4 text-yellow-600 flex-shrink-0" />
                      <p className="text-sm font-medium text-yellow-700 dark:text-yellow-400">
                        {pixSimulacao.excluidos.length} fora do lote — {fmt(pixSimulacao.total_excluidos_valor || 0)}
                      </p>
                    </div>
                    <ul className="space-y-1 max-h-40 overflow-y-auto">
                      {pixSimulacao.excluidos.map((e, i) => (
                        <li key={i} className="flex items-center justify-between text-xs gap-2 border-b border-yellow-200/50 dark:border-yellow-900/30 pb-1 last:border-0">
                          <span className="truncate flex-1">{e.nome}</span>
                          <span className="tabular-nums text-muted-foreground">{fmt(e.valor_liquido)}</span>
                          <Badge variant="outline" className="text-[10px] whitespace-nowrap">{e.motivo}</Badge>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Reconciliação: lote + excluídos = folha integral do período */}
                {typeof pixSimulacao.total_folha_valor === 'number' && (
                  <div className={`rounded-lg p-3 mb-4 text-xs border ${pixSimulacao.reconcilia === false ? 'bg-red-50 border-red-200 text-red-700' : 'bg-slate-50 dark:bg-slate-900/30 border-slate-200'}`}>
                    <div className="flex justify-between"><span>Lote PIX ({pixSimulacao.prontos_para_pagar})</span><span className="tabular-nums font-medium">{fmt(pixSimulacao.total_valor)}</span></div>
                    <div className="flex justify-between"><span>Excluídos ({pixSimulacao.total_excluidos_qtd ?? 0})</span><span className="tabular-nums font-medium">{fmt(pixSimulacao.total_excluidos_valor || 0)}</span></div>
                    <div className="flex justify-between border-t border-slate-300 dark:border-slate-700 mt-1 pt-1 font-semibold">
                      <span>Folha do período ({pixSimulacao.total_folha_qtd ?? 0})</span>
                      <span className="tabular-nums">{fmt(pixSimulacao.total_folha_valor)}</span>
                    </div>
                    {pixSimulacao.reconcilia === false && (
                      <p className="mt-1 font-medium">Atenção: lote + excluídos não fecha com a folha.</p>
                    )}
                  </div>
                )}

                <p className="text-xs text-muted-foreground mb-4">
                  Ao confirmar, os pagamentos PIX serão registrados como pendente_pagamento (aguardando aprovação manual) para os funcionários ativos, com holerite publicado, chave PIX e líquido maior que zero.
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
