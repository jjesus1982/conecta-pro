'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';
import { CalendarX, Search, Download, AlertTriangle, Clock, XCircle, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface Inconsistencia {
  id?: string | number;
  colaborador?: string;
  employee_name?: string;
  data?: string;
  date?: string;
  tipo?: string;
  type?: string;
  tempo?: string;
  duration?: string;
  justificado?: boolean;
  justified?: boolean;
}

interface InconsistenciasResponse {
  periodo_inicio?: string;
  periodo_fim?: string;
  items?: Inconsistencia[];
  inconsistencias?: Inconsistencia[];
  total?: number;
  resumo?: {
    atrasos?: number;
    faltas_justificadas?: number;
    faltas_injustificadas?: number;
    saidas_antecipadas?: number;
  };
}

const tipoConfig: Record<string, { label: string; classes: string; icon: typeof Clock }> = {
  atraso: { label: 'Atraso', classes: 'bg-amber-500/10 text-amber-500 border border-amber-500/30', icon: Clock },
  falta_justificada: { label: 'Falta Justificada', classes: 'bg-blue-500/10 text-blue-500 border border-blue-500/30', icon: CalendarX },
  falta_injustificada: { label: 'Falta Injustificada', classes: 'bg-red-500/10 text-red-500 border border-red-500/30', icon: XCircle },
  saida_antecipada: { label: 'Saida Antecipada', classes: 'bg-purple-500/10 text-purple-500 border border-purple-500/30', icon: AlertTriangle },
};

export default function AtrasosPage() {
  const [filtroTipo, setFiltroTipo] = useState('todos');
  const [busca, setBusca] = useState('');

  const { data: response, isLoading, error } = useQuery<InconsistenciasResponse>({
    queryKey: ['ponto', 'inconsistencias'],
    queryFn: () => customInstance({ url: '/api/v1/people-management/ponto/relatorio/inconsistencias' }) as Promise<InconsistenciasResponse>,
    staleTime: 30000,
    retry: 2,
  });

  const ocorrencias: Inconsistencia[] = response?.items ?? response?.inconsistencias ?? (Array.isArray(response) ? response as unknown as Inconsistencia[] : []);

  const filtered = ocorrencias.filter((o) => {
    const tipo = o.tipo || o.type || '';
    const nome = o.colaborador || o.employee_name || '';
    const matchTipo = filtroTipo === 'todos' || tipo === filtroTipo;
    const matchBusca = !busca || nome.toLowerCase().includes(busca.toLowerCase());
    return matchTipo && matchBusca;
  });

  const resumo = [
    { label: 'Atrasos', valor: response?.resumo?.atrasos ?? ocorrencias.filter(o => (o.tipo || o.type) === 'atraso').length, icon: Clock, color: 'text-amber-500', bg: 'bg-amber-500/10' },
    { label: 'Faltas Justificadas', valor: response?.resumo?.faltas_justificadas ?? ocorrencias.filter(o => (o.tipo || o.type) === 'falta_justificada').length, icon: CalendarX, color: 'text-blue-500', bg: 'bg-blue-500/10' },
    { label: 'Faltas Injustificadas', valor: response?.resumo?.faltas_injustificadas ?? ocorrencias.filter(o => (o.tipo || o.type) === 'falta_injustificada').length, icon: XCircle, color: 'text-red-500', bg: 'bg-red-500/10' },
    { label: 'Saidas Antecipadas', valor: response?.resumo?.saidas_antecipadas ?? ocorrencias.filter(o => (o.tipo || o.type) === 'saida_antecipada').length, icon: AlertTriangle, color: 'text-purple-500', bg: 'bg-purple-500/10' },
  ];

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <CalendarX className="w-6 h-6 text-red-500" />
          <div>
            <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Atrasos e Faltas</h1>
            <p className="text-[hsl(var(--muted-foreground))] mt-1">
              {response?.periodo_inicio && response?.periodo_fim
                ? `${response.periodo_inicio} a ${response.periodo_fim}`
                : new Date().toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })}
            </p>
          </div>
        </div>
        <button type="button" className="flex items-center gap-2 px-4 py-2 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg text-sm font-medium hover:bg-[hsl(var(--secondary))] transition-colors">
          <Download className="h-4 w-4" />
          Exportar
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-500 px-4 py-3 rounded-lg text-sm">
          Erro ao carregar inconsistencias: {(error as Error).message}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {resumo.map((r) => {
          const Icon = r.icon;
          return (
            <Card key={r.label} className="border border-[hsl(var(--border))]">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-[hsl(var(--muted-foreground))]">{r.label}</p>
                    {isLoading ? (
                      <Loader2 className="h-5 w-5 animate-spin text-[hsl(var(--muted-foreground))] mt-2" />
                    ) : (
                      <p className="font-data text-2xl font-semibold tabular-nums mt-1">{r.valor}</p>
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

      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[hsl(var(--muted-foreground))]" />
          <input
            type="text"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar colaborador..."
            className="w-full pl-10 pr-4 py-2 border border-[hsl(var(--border))] rounded-lg text-sm bg-[hsl(var(--card))] focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
        <select
          value={filtroTipo}
          onChange={(e) => setFiltroTipo(e.target.value)}
          className="px-3 py-2 border border-[hsl(var(--border))] rounded-lg text-sm bg-[hsl(var(--card))] focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="todos">Todos os tipos</option>
          <option value="atraso">Atrasos</option>
          <option value="falta_justificada">Faltas Justificadas</option>
          <option value="falta_injustificada">Faltas Injustificadas</option>
          <option value="saida_antecipada">Saidas Antecipadas</option>
        </select>
      </div>

      <Card className="border border-[hsl(var(--border))]">
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--secondary))]">
                    <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Colaborador</th>
                    <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Data</th>
                    <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Tipo</th>
                    <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Tempo</th>
                    <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Justificado</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-[hsl(var(--muted-foreground))]">
                        Nenhuma inconsistencia encontrada
                      </td>
                    </tr>
                  ) : (
                    filtered.map((o, idx) => {
                      const tipo = o.tipo || o.type || '';
                      const justified = o.justificado ?? o.justified ?? false;
                      return (
                        <tr key={o.id ?? idx} className="border-b border-[hsl(var(--border))] hover:bg-[hsl(var(--secondary))]">
                          <td className="py-3 px-4 font-medium text-[hsl(var(--foreground))]">{o.colaborador || o.employee_name || '--'}</td>
                          <td className="py-3 px-4 text-[hsl(var(--muted-foreground))]">{o.data || o.date || '--'}</td>
                          <td className="py-3 px-4">
                            <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${tipoConfig[tipo]?.classes ?? 'bg-[hsl(var(--secondary))] text-[hsl(var(--muted-foreground))]'}`}>
                              {tipoConfig[tipo]?.label ?? tipo}
                            </span>
                          </td>
                          <td className="py-3 px-4 font-data tabular-nums text-[hsl(var(--foreground))]">{o.tempo || o.duration || '--'}</td>
                          <td className="py-3 px-4">
                            {justified ? (
                              <span className="inline-flex px-2 py-0.5 text-xs font-medium rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/30">Sim</span>
                            ) : (
                              <span className="inline-flex px-2 py-0.5 text-xs font-medium rounded-full bg-[hsl(var(--secondary))] text-[hsl(var(--muted-foreground))]">Nao</span>
                            )}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
