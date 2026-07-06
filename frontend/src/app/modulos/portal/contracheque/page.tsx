'use client';

import { useState, useEffect } from 'react';
import { FileText, Calendar, Download, Loader2, ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

const API_HR = '/api/v1/people-management/hr';
const API_PORTAL = '/api/v1/people-management/portal';

function getAuthHeaders(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const fmt = (v: number) => `R$ ${(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;

interface PayslipSummary {
  employee_id: string;
  employee_name: string;
  reference: string;
  salario_base: number;
  total_proventos: number;
  total_descontos: number;
  salario_liquido: number;
  fgts_8_pct: number;
  proventos: Array<{ codigo: string; descricao: string; ref: string; valor: number }>;
  descontos: Array<{ codigo: string; descricao: string; ref: string; valor: number }>;
}

export default function ContrachequePortalPage() {
  const now = new Date();
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [year, setYear] = useState(now.getFullYear());
  const [payslip, setPayslip] = useState<PayslipSummary | null>(null);
  const [employees, setEmployees] = useState<Array<{ id: string; nome: string }>>([]);
  const [selectedEmp, setSelectedEmp] = useState('');
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState('');

  // Load employees once
  useEffect(() => {
    async function loadEmployees() {
      try {
        const res = await fetch(`${API_HR}/employees?page_size=100`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          const items = data.items || [];
          setEmployees(items);
          if (items.length > 0 && !selectedEmp) {
            setSelectedEmp(items[0].id);
          }
        }
      } catch {
        /* fallback */
      } finally {
        setLoading(false);
      }
    }
    loadEmployees();
  }, []);

  // Load payslip when employee or period changes
  useEffect(() => {
    if (!selectedEmp) return;
    async function loadPayslip() {
      setLoading(true);
      setError('');
      setPayslip(null);
      try {
        const res = await fetch(
          `${API_HR}/payroll/employee/${selectedEmp}/calculate?month=${month}&year=${year}`,
          { headers: getAuthHeaders() }
        );
        if (res.ok) {
          setPayslip(await res.json());
        } else {
          setError('Erro ao carregar contracheque');
        }
      } catch {
        setError('Erro de conexao');
      } finally {
        setLoading(false);
      }
    }
    loadPayslip();
  }, [selectedEmp, month, year]);

  function prevMonth() {
    if (month === 1) { setMonth(12); setYear(year - 1); }
    else { setMonth(month - 1); }
  }

  function nextMonth() {
    if (month === 12) { setMonth(1); setYear(year + 1); }
    else { setMonth(month + 1); }
  }

  async function handleDownloadPDF() {
    if (!selectedEmp) return;
    setDownloading(true);
    try {
      const token = localStorage.getItem('access_token') || '';
      const res = await fetch(
        `${API_HR}/payroll/employee/${selectedEmp}/payslip-pdf?month=${month}&year=${year}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `contracheque-${month.toString().padStart(2, '0')}-${year}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch {
      /* fallback */
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card>
        <CardContent className="p-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <FileText className="w-6 h-6 text-blue-600" />
              <div>
                <h2 className="font-display text-lg">Contracheque</h2>
                <p className="text-sm text-gray-500">Visualize e baixe seus contracheques</p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {/* Employee selector */}
              <select
                value={selectedEmp}
                onChange={(e) => setSelectedEmp(e.target.value)}
                className="px-3 py-2 rounded-lg border border-gray-200 text-sm bg-white"
              >
                {employees.map((e) => (
                  <option key={e.id} value={e.id}>{e.nome}</option>
                ))}
              </select>

              {/* Period nav */}
              <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
                <Button type="button" variant="ghost" size="sm" onClick={prevMonth}>
                  <ChevronLeft className="w-4 h-4" />
                </Button>
                <span className="px-3 py-1 text-sm font-medium min-w-[100px] text-center">
                  {month.toString().padStart(2, '0')}/{year}
                </span>
                <Button type="button" variant="ghost" size="sm" onClick={nextMonth}>
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </div>

              {/* Download */}
              <Button type="button" onClick={handleDownloadPDF} disabled={downloading || !payslip} variant="outline" size="sm">
                {downloading ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Download className="w-4 h-4 mr-1" />}
                PDF
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">{error}</div>
      )}

      {/* Payslip data */}
      {payslip && !loading && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
            <Card>
              <CardContent className="p-4">
                <p className="text-sm text-gray-500">Salario Base</p>
                <p className="font-data text-xl font-semibold tabular-nums">{fmt(payslip.salario_base)}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <p className="text-sm text-gray-500">Total Proventos</p>
                <p className="font-data text-xl font-semibold tabular-nums text-green-700">{fmt(payslip.total_proventos)}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <p className="text-sm text-gray-500">Total Descontos</p>
                <p className="font-data text-xl font-semibold tabular-nums text-red-700">{fmt(payslip.total_descontos)}</p>
              </CardContent>
            </Card>
            <Card className="bg-blue-50 border-blue-200">
              <CardContent className="p-4">
                <p className="text-sm text-blue-600">Salario Liquido</p>
                <p className="font-data text-2xl font-semibold tabular-nums text-blue-700">{fmt(payslip.salario_liquido)}</p>
              </CardContent>
            </Card>
          </div>

          {/* Proventos table */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-green-700">Proventos</CardTitle>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 border-b">
                    <th className="pb-2 w-16">Cod</th>
                    <th className="pb-2">Descricao</th>
                    <th className="pb-2 w-20">Ref</th>
                    <th className="pb-2 text-right w-28">Valor</th>
                  </tr>
                </thead>
                <tbody>
                  {payslip.proventos.map((p, i) => (
                    <tr key={i} className="border-t">
                      <td className="py-1.5 text-gray-400">{p.codigo}</td>
                      <td className="py-1.5">{p.descricao}</td>
                      <td className="py-1.5 text-gray-400">{p.ref}</td>
                      <td className="py-1.5 text-right font-medium">{fmt(p.valor)}</td>
                    </tr>
                  ))}
                  <tr className="border-t-2 border-green-200 bg-green-50">
                    <td colSpan={3} className="py-2 font-semibold text-green-700">TOTAL PROVENTOS</td>
                    <td className="py-2 text-right font-bold text-green-700">{fmt(payslip.total_proventos)}</td>
                  </tr>
                </tbody>
              </table>
            </CardContent>
          </Card>

          {/* Descontos table */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-red-700">Descontos</CardTitle>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 border-b">
                    <th className="pb-2 w-16">Cod</th>
                    <th className="pb-2">Descricao</th>
                    <th className="pb-2 text-right w-28">Valor</th>
                  </tr>
                </thead>
                <tbody>
                  {payslip.descontos.map((d, i) => (
                    <tr key={i} className="border-t">
                      <td className="py-1.5 text-gray-400">{d.codigo}</td>
                      <td className="py-1.5">{d.descricao}</td>
                      <td className="py-1.5 text-right font-medium text-red-600">{fmt(d.valor)}</td>
                    </tr>
                  ))}
                  <tr className="border-t-2 border-red-200 bg-red-50">
                    <td colSpan={2} className="py-2 font-semibold text-red-700">TOTAL DESCONTOS</td>
                    <td className="py-2 text-right font-bold text-red-700">{fmt(payslip.total_descontos)}</td>
                  </tr>
                </tbody>
              </table>
            </CardContent>
          </Card>

          {/* FGTS info */}
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-500">FGTS 8% (encargo patronal — nao desconta)</span>
                <span className="font-medium text-cyan-700">{fmt(payslip.fgts_8_pct)}</span>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
