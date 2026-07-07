'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';
import { Lock, Unlock, CheckCircle2, AlertTriangle, Calendar, Users, Download, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface PontoDashboardData {
  total_colaboradores: number;
  inconsistencias_periodo: number;
  pontos_em_aberto: number;
}

interface FechamentoPayload {
  mes: number;
  ano: number;
}

interface FechamentoResponse {
  message?: string;
  status?: string;
}

const statusConfig: Record<string, { label: string; classes: string; icon: typeof Lock }> = {
  aberto: { label: 'Aberto', classes: 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30', icon: Unlock },
  em_revisao: { label: 'Em Revisao', classes: 'bg-amber-500/10 text-amber-500 border border-amber-500/30', icon: AlertTriangle },
  fechado: { label: 'Fechado', classes: 'bg-[hsl(var(--secondary))] text-[hsl(var(--muted-foreground))]', icon: Lock },
};

export default function FechamentoPage() {
  const queryClient = useQueryClient();
  const now = new Date();
  const [selectedMonth, setSelectedMonth] = useState(now.getMonth() + 1);
  const [selectedYear, setSelectedYear] = useState(now.getFullYear());
  const [confirmando, setConfirmando] = useState(false);

  const monthNames = ['Janeiro', 'Fevereiro', 'Marco', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];

  const { data: dashboard, isLoading: loadingDashboard } = useQuery<PontoDashboardData>({
    queryKey: ['ponto', 'dashboard'],
    queryFn: () => customInstance({ url: '/api/v1/people-management/ponto/dashboard' }) as Promise<PontoDashboardData>,
    staleTime: 30000,
    retry: 2,
  });

  const fechamentoMutation = useMutation<FechamentoResponse, Error, FechamentoPayload>({
    mutationFn: (body) => customInstance({
      url: '/api/v1/people-management/ponto/fechamento',
      method: 'POST',
      data: body,
    }) as Promise<FechamentoResponse>,
    onSuccess: () => {
      setConfirmando(false);
      queryClient.invalidateQueries({ queryKey: ['ponto'] });
    },
  });

  function handleConfirmFechamento() {
    fechamentoMutation.mutate({ mes: selectedMonth, ano: selectedYear });
  }

  const pendencias = dashboard?.inconsistencias_periodo ?? 0;
  const colaboradores = dashboard?.total_colaboradores ?? 0;
  const pontosAbertos = dashboard?.pontos_em_aberto ?? 0;

  // Build period cards: current month (open) + 2 previous (assumed closed)
  const meses = [
    {
      mes: `${monthNames[selectedMonth - 1]} ${selectedYear}`,
      periodo: `01/${String(selectedMonth).padStart(2, '0')} - ${new Date(selectedYear, selectedMonth, 0).getDate()}/${String(selectedMonth).padStart(2, '0')}`,
      status: 'aberto' as const,
      colaboradores,
      pendencias,
    },
    (() => {
      const pm = selectedMonth === 1 ? 12 : selectedMonth - 1;
      const py = selectedMonth === 1 ? selectedYear - 1 : selectedYear;
      return {
        mes: `${monthNames[pm - 1]} ${py}`,
        periodo: `01/${String(pm).padStart(2, '0')} - ${new Date(py, pm, 0).getDate()}/${String(pm).padStart(2, '0')}`,
        status: 'fechado' as const,
        colaboradores,
        pendencias: 0,
      };
    })(),
    (() => {
      const pm2 = selectedMonth <= 2 ? (selectedMonth === 1 ? 11 : 12) : selectedMonth - 2;
      const py2 = selectedMonth <= 2 ? selectedYear - 1 : selectedYear;
      return {
        mes: `${monthNames[pm2 - 1]} ${py2}`,
        periodo: `01/${String(pm2).padStart(2, '0')} - ${new Date(py2, pm2, 0).getDate()}/${String(pm2).padStart(2, '0')}`,
        status: 'fechado' as const,
        colaboradores,
        pendencias: 0,
      };
    })(),
  ];

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Lock className="w-6 h-6 text-[hsl(var(--muted-foreground))]" />
          <div>
            <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Fechamento Mensal</h1>
            <p className="text-[hsl(var(--muted-foreground))] mt-1">Controle de fechamento do ponto por competencia</p>
          </div>
        </div>
        <button type="button" className="flex items-center gap-2 px-4 py-2 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg text-sm font-medium hover:bg-[hsl(var(--secondary))] transition-colors">
          <Download className="h-4 w-4" />
          Relatorio Geral
        </button>
      </div>

      {fechamentoMutation.isError && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-500 px-4 py-3 rounded-lg text-sm">
          Erro ao fechar competencia: {fechamentoMutation.error.message}
        </div>
      )}

      {fechamentoMutation.isSuccess && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-500 px-4 py-3 rounded-lg text-sm">
          Competência fechada com sucesso!
        </div>
      )}

      <div className="flex items-center gap-4">
        <label className="text-sm text-[hsl(var(--muted-foreground))]">Competência:</label>
        <select
          value={selectedMonth}
          onChange={(e) => setSelectedMonth(Number(e.target.value))}
          className="px-3 py-2 border border-[hsl(var(--border))] rounded-lg text-sm bg-[hsl(var(--card))] focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {monthNames.map((name, idx) => (
            <option key={idx} value={idx + 1}>{name}</option>
          ))}
        </select>
        <select
          value={selectedYear}
          onChange={(e) => setSelectedYear(Number(e.target.value))}
          className="px-3 py-2 border border-[hsl(var(--border))] rounded-lg text-sm bg-[hsl(var(--card))] focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {[2024, 2025, 2026, 2027].map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {meses.map((m) => {
          const config = statusConfig[m.status]!;
          const StatusIcon = config.icon;
          return (
            <Card key={m.mes} className={`border ${m.status === 'aberto' ? 'border-blue-500/40 ring-1 ring-blue-500/20' : 'border-[hsl(var(--border))]'}`}>
              <CardContent className="p-5">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-[hsl(var(--foreground))]">{m.mes}</h3>
                  <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full ${config.classes}`}>
                    <StatusIcon className="h-3 w-3" />
                    {config.label}
                  </span>
                </div>
                <div className="space-y-2 text-sm text-[hsl(var(--muted-foreground))]">
                  <div className="flex justify-between">
                    <span>Periodo</span>
                    <span className="font-medium text-[hsl(var(--foreground))]">{m.periodo}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Colaboradores</span>
                    {loadingDashboard ? (
                      <Loader2 className="h-4 w-4 animate-spin text-[hsl(var(--muted-foreground))]" />
                    ) : (
                      <span className="font-data text-sm font-semibold tabular-nums text-[hsl(var(--foreground))]">{m.colaboradores}</span>
                    )}
                  </div>
                  <div className="flex justify-between">
                    <span>Pendencias</span>
                    <span className={`font-data font-semibold tabular-nums ${m.pendencias > 0 ? 'text-red-500' : 'text-emerald-500'}`}>
                      {m.pendencias}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card className="border border-[hsl(var(--border))]">
        <CardHeader className="pb-2">
          <CardTitle className="text-lg font-semibold flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-500" />
            Pendencias — {monthNames[selectedMonth - 1]} {selectedYear}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loadingDashboard ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-[hsl(var(--muted-foreground))]" />
            </div>
          ) : pendencias === 0 ? (
            <div className="text-center py-8 text-[hsl(var(--muted-foreground))]">
              Nenhuma pendencia encontrada para este periodo.
            </div>
          ) : (
            <div className="text-sm text-[hsl(var(--muted-foreground))] py-4">
              <p>Existem <strong className="text-red-500">{pendencias}</strong> inconsistencias e <strong className="text-amber-500">{pontosAbertos}</strong> pontos em aberto neste periodo.</p>
              <p className="mt-2 text-[hsl(var(--muted-foreground))]">Resolva as pendencias antes de fechar a competencia.</p>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-end gap-3">
        <button type="button" className="px-4 py-2 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg text-sm font-medium hover:bg-[hsl(var(--secondary))] transition-colors">
          Revisar Pendencias
        </button>
        <button
          onClick={() => setConfirmando(true)}
          className="px-6 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 transition-colors flex items-center gap-2"
        >
          <Lock className="h-4 w-4" />
          Fechar Competência
        </button>
      </div>

      {confirmando && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-md border border-[hsl(var(--border))]">
            <CardContent className="p-6">
              <h3 className="text-lg font-bold text-[hsl(var(--foreground))] mb-2">Confirmar Fechamento</h3>
              <p className="text-sm text-[hsl(var(--muted-foreground))] mb-4">
                Tem certeza que deseja fechar a competencia {monthNames[selectedMonth - 1]} {selectedYear}?
                {pendencias > 0 && ` Existem ${pendencias} pendencias nao resolvidas.`} Apos o fechamento, nao sera possivel alterar batidas.
              </p>
              {fechamentoMutation.isError && (
                <div className="bg-red-500/10 border border-red-500/30 text-red-500 px-3 py-2 rounded-lg text-sm mb-4">
                  {fechamentoMutation.error.message}
                </div>
              )}
              <div className="flex justify-end gap-3">
                <button
                  onClick={() => setConfirmando(false)}
                  disabled={fechamentoMutation.isPending}
                  className="px-4 py-2 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg text-sm font-medium hover:bg-[hsl(var(--secondary))]"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleConfirmFechamento}
                  disabled={fechamentoMutation.isPending}
                  className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 flex items-center gap-2"
                >
                  {fechamentoMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                  Confirmar Fechamento
                </button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
