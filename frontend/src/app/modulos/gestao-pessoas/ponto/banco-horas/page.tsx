'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';
import { Hourglass, TrendingUp, TrendingDown, Search, Download, Minus, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface Employee {
  id: string;
  name?: string;
  nome?: string;
  full_name?: string;
}

interface BancoHorasData {
  employee_id: string;
  employee_name?: string;
  saldo_horas?: number;
  saldo?: string;
  creditos?: string;
  debitos?: string;
  total_credito?: number;
  total_debito?: number;
  ultima_atualizacao?: string;
  registros?: BancoHorasEntry[];
  items?: BancoHorasEntry[];
}

interface BancoHorasEntry {
  id?: string | number;
  colaborador?: string;
  employee_name?: string;
  creditos?: string;
  debitos?: string;
  saldo?: string;
  saldo_minutos?: number;
  saldoMinutos?: number;
  ultima_atualizacao?: string;
}

export default function BancoHorasPage() {
  const [busca, setBusca] = useState('');
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<string | null>(null);
  const [selectedEmployeeName, setSelectedEmployeeName] = useState<string | null>(null);

  const { data: employees, isLoading: loadingEmployees } = useQuery<Employee[]>({
    queryKey: ['ponto', 'employees'],
    queryFn: async () => {
      const res = await customInstance({ url: '/api/v1/people-management/hr/employees', params: { page_size: 100 } }) as unknown as { items?: Employee[] } | Employee[];
      return Array.isArray(res) ? res : res?.items ?? [];
    },
    staleTime: 60000,
    retry: 2,
  });

  const { data: bancoHoras, isLoading: loadingBanco, error: bancoError } = useQuery<BancoHorasData>({
    queryKey: ['ponto', 'banco-horas', selectedEmployeeId],
    queryFn: () => customInstance({
      url: `/api/v1/people-management/ponto/banco-horas/${selectedEmployeeId}`,
    }) as Promise<BancoHorasData>,
    enabled: !!selectedEmployeeId,
    staleTime: 30000,
    retry: 2,
  });

  const entries: BancoHorasEntry[] = bancoHoras?.registros ?? bancoHoras?.items ?? [];

  const filteredEntries = busca
    ? entries.filter((d) => {
        const nome = d.colaborador || d.employee_name || '';
        return nome.toLowerCase().includes(busca.toLowerCase());
      })
    : entries;

  function formatMinutes(horas: number | undefined): string {
    // o backend manda HORAS (float) — exibe como ±HHhMM
    if (horas === undefined || horas === null || isNaN(horas)) return '--';
    const sign = horas >= 0 ? '+' : '-';
    const abs = Math.abs(horas);
    const h = Math.floor(abs);
    const m = Math.round((abs - h) * 60);
    return `${sign}${h}h${String(m).padStart(2, '0')}`;
  }

  const resumo = [
    { label: 'Total Creditos', value: bancoHoras?.creditos ?? (bancoHoras?.total_credito ? `${bancoHoras.total_credito}h` : '--'), icon: TrendingUp, color: 'text-emerald-500', bg: 'bg-emerald-500/10' },
    { label: 'Total Debitos', value: bancoHoras?.debitos ?? (bancoHoras?.total_debito ? `${bancoHoras.total_debito}h` : '--'), icon: TrendingDown, color: 'text-red-500', bg: 'bg-red-500/10' },
    { label: 'Saldo', value: bancoHoras?.saldo ?? (bancoHoras?.saldo_horas !== undefined ? formatMinutes(bancoHoras.saldo_horas) : '--'), icon: Hourglass, color: 'text-blue-500', bg: 'bg-blue-500/10' },
    { label: 'Colaborador', value: bancoHoras?.employee_name ?? selectedEmployeeName ?? (selectedEmployeeId ? `#${selectedEmployeeId.slice(0,8)}` : '--'), icon: Minus, color: 'text-[hsl(var(--muted-foreground))]', bg: 'bg-[hsl(var(--secondary))]' },
  ];

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Hourglass className="w-6 h-6 text-emerald-500" />
          <div>
            <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Banco de Horas</h1>
            <p className="text-[hsl(var(--muted-foreground))] mt-1">Saldos acumulados</p>
          </div>
        </div>
        <button type="button" className="flex items-center gap-2 px-4 py-2 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg text-sm font-medium hover:bg-[hsl(var(--secondary))] transition-colors">
          <Download className="h-4 w-4" />
          Exportar
        </button>
      </div>

      {bancoError && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-500 px-4 py-3 rounded-lg text-sm">
          Erro ao carregar banco de horas: {(bancoError as Error).message}
        </div>
      )}

      <div className="flex items-center gap-4">
        <label className="text-sm text-[hsl(var(--muted-foreground))]">Colaborador:</label>
        {loadingEmployees ? (
          <Loader2 className="h-4 w-4 animate-spin text-[hsl(var(--muted-foreground))]" />
        ) : (
          <select
            value={selectedEmployeeId ?? ''}
            onChange={(e) => { setSelectedEmployeeId(e.target.value || null); setSelectedEmployeeName(e.target.selectedOptions?.[0]?.text || null); }}
            className="px-3 py-2 border border-[hsl(var(--border))] rounded-lg text-sm bg-[hsl(var(--card))] focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">Selecionar colaborador...</option>
            {(employees ?? []).map((emp) => (
              <option key={emp.id} value={emp.id}>
                {emp.full_name || emp.nome || emp.name || `Funcionario #${emp.id}`}
              </option>
            ))}
          </select>
        )}
      </div>

      {selectedEmployeeId && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {resumo.map((r) => {
            const Icon = r.icon;
            return (
              <Card key={r.label} className="border border-[hsl(var(--border))]">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-[hsl(var(--muted-foreground))]">{r.label}</p>
                      {loadingBanco ? (
                        <Loader2 className="h-5 w-5 animate-spin text-[hsl(var(--muted-foreground))] mt-2" />
                      ) : (
                        <p className="font-data text-2xl font-semibold tabular-nums mt-1">{r.value}</p>
                      )}
                    </div>
                    <div className={`p-3 rounded-lg ${r.bg}`}>
                      <Icon className={`h-5 w-5 ${r.color}`} />
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {!selectedEmployeeId && (
        <div className="text-center py-12 text-[hsl(var(--muted-foreground))]">
          Selecione um colaborador para visualizar o banco de horas.
        </div>
      )}

      {selectedEmployeeId && entries.length > 0 && (
        <>
          <div className="relative max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[hsl(var(--muted-foreground))]" />
            <input
              type="text"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar nos registros..."
              className="w-full pl-10 pr-4 py-2 border border-[hsl(var(--border))] rounded-lg text-sm bg-[hsl(var(--card))] focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          <Card className="border border-[hsl(var(--border))]">
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--secondary))]">
                      <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Colaborador</th>
                      <th className="text-center py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Creditos</th>
                      <th className="text-center py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Debitos</th>
                      <th className="text-center py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Saldo</th>
                      <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Última Atualização</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredEntries.map((d, idx) => {
                      const saldoMins = d.saldo_minutos ?? d.saldoMinutos ?? 0;
                      return (
                        <tr key={d.id ?? idx} className="border-b border-[hsl(var(--border))] hover:bg-[hsl(var(--secondary))]">
                          <td className="py-3 px-4 font-medium text-[hsl(var(--foreground))]">{d.colaborador || d.employee_name || '--'}</td>
                          <td className="py-3 px-4 text-center font-data tabular-nums text-emerald-500">{d.creditos || '--'}</td>
                          <td className="py-3 px-4 text-center font-data tabular-nums text-red-500">{d.debitos || '--'}</td>
                          <td className="py-3 px-4 text-center">
                            <span className={`inline-flex px-2 py-1 text-xs font-bold rounded-full font-data tabular-nums ${
                              saldoMins > 0 ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30' :
                              saldoMins < 0 ? 'bg-red-500/10 text-red-500 border border-red-500/30' :
                              'bg-[hsl(var(--secondary))] text-[hsl(var(--muted-foreground))]'
                            }`}>
                              {d.saldo || formatMinutes(saldoMins)}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-[hsl(var(--muted-foreground))]">{d.ultima_atualizacao || '--'}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {selectedEmployeeId && !loadingBanco && entries.length === 0 && !bancoError && (
        <div className="text-center py-8 text-[hsl(var(--muted-foreground))]">
          Nenhum registro de banco de horas encontrado para este colaborador.
        </div>
      )}
    </div>
  );
}
