'use client';

import { Users, ArrowLeft, Calendar, Check, CheckCircle, XCircle, Clock, DollarSign, RefreshCw, AlertTriangle } from 'lucide-react';
import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { useAuth } from '@/hooks/useAuth';
import { useCondominio } from '@/contexts/CondominioContext';
import { useActiveDiarists, useCreateBatchSchedules } from '@/hooks/operacional/useDiarists';
import type { DiaristResponse, BatchScheduleItem, BatchScheduleResponse } from '@/types/generated/operacional/conectaPROMóduloOPERACIONAL.schemas';
import {
  DIARIST_TYPE_LABELS,
  type DiaristType,
} from '@/lib/services/diarists';

export default function EscalaDiariaPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();
  const { condominioId } = useCondominio();

  // Data selecionada (default = amanha)
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const [selectedDate, setSelectedDate] = useState<string>(
    tomorrow.toISOString().split('T')[0] ?? ''
  );

  const { data: diarists = [], isLoading, error: queryError, refetch } = useActiveDiarists({ data: selectedDate });
  const createBatchMutation = useCreateBatchSchedules();
  const [selected, setSelected] = useState<Map<string, BatchScheduleItem>>(new Map());
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (queryError) {
      setError(String(queryError));
    }
  }, [queryError]);

  const toggleDiarist = (diarist: DiaristResponse) => {
    const newSelected = new Map(selected);
    if (newSelected.has(diarist.id)) {
      newSelected.delete(diarist.id);
    } else {
      newSelected.set(diarist.id, {
        diarist_id: diarist.id,
        horario_inicio: '08:00',
        horario_fim: '17:00',
        servico_tipo: diarist.tipos_servico?.[0] || 'limpeza',
      });
    }
    setSelected(newSelected);
  };

  const updateItem = (diaristId: string, field: keyof BatchScheduleItem, value: string) => {
    const newSelected = new Map(selected);
    const item = newSelected.get(diaristId);
    if (item) {
      newSelected.set(diaristId, { ...item, [field]: value });
      setSelected(newSelected);
    }
  };

  const totalValor = Array.from(selected.keys()).reduce((acc, id) => {
    const d = diarists.find(d => d.id === id);
    return acc + (d ? parseFloat(d.valor_diaria) || 0 : 0);
  }, 0);

  const handleConfirm = async () => {
    if (selected.size === 0) return;

    setIsSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const result: BatchScheduleResponse = await createBatchMutation.mutateAsync({
        data: {
          condominio_id: condominioId,
          data: selectedDate,
          items: Array.from(selected.values()),
        },
      });

      const totalErros = result.total_erros ?? 0;
      const totalCriados = result.total_criados ?? 0;
      const erros = result.erros ?? [];

      if (totalErros > 0) {
        setError(`${totalCriados} criados, ${totalErros} erros: ${erros.join('; ')}`);
      }

      if (totalCriados > 0) {
        setSuccess(`Escala criada com sucesso! ${totalCriados} diaristas escalados para ${selectedDate}.`);
        setSelected(new Map());
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Erro desconhecido';
      setError(`Erro ao criar escala: ${message}`);
      void err;
    } finally {
      setIsSaving(false);
    }
  };

  const formatCurrency = (value: number) =>
    new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <Calendar className="w-12 h-12" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-grid">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <PageHeader
          eyebrow="OPERACIONAL · DIARISTAS"
          title="Escala Diaria"
          subtitle="Monte a escala do dia"
          icon={<Calendar className="w-5 h-5" />}
          actions={
            <>
              <Link href="/modulos/operacional/diaristas">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Diaristas
                </Button>
              </Link>
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => refetch()}
                disabled={isLoading}
              >
                <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
              </Button>
            </>
          }
        />

        {/* Stats Cards */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center">
                <Users className="w-5 h-5 text-cyan-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{diarists.length}</p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Disponiveis</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                <CheckCircle className="w-5 h-5 text-green-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{selected.size}</p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Escalados</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                <DollarSign className="w-5 h-5 text-emerald-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-green-500">{formatCurrency(totalValor)}</p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Valor Total</p>
              </div>
            </div>
          </div>
        </div>

        {/* Messages */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 mb-6 flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-red-500 flex-shrink-0" />
            <p className="text-red-500 text-sm">{error}</p>
          </div>
        )}

        {success && (
          <div className="bg-green-500/10 border border-green-500/20 rounded-xl p-4 mb-6 flex items-center gap-3">
            <CheckCircle className="w-5 h-5 text-green-500 flex-shrink-0" />
            <p className="text-green-500 text-sm">{success}</p>
          </div>
        )}

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-pulse-slow text-[hsl(var(--primary))]">
              <Users className="w-8 h-8" />
            </div>
          </div>
        )}

        {/* Lista de Diaristas */}
        {!isLoading && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Coluna: Diaristas Disponiveis */}
            <div>
              <h2 className="text-sm font-semibold text-[hsl(var(--muted-foreground))] uppercase tracking-wider mb-3">
                Diaristas Ativos ({diarists.length})
              </h2>
              <div className="space-y-2 max-h-[600px] overflow-y-auto pr-2">
                {diarists.map((d) => {
                  const isSelected = selected.has(d.id);
                  return (
                    <div
                      key={d.id}
                      onClick={() => toggleDiarist(d)}
                      className={`p-3 rounded-lg border cursor-pointer transition-all ${
                        isSelected
                          ? 'bg-green-500/10 border-green-500/50'
                          : 'bg-[hsl(var(--card))] border-[hsl(var(--border))] hover:border-[hsl(var(--primary))]/30'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                          isSelected
                            ? 'bg-green-500 text-white'
                            : 'bg-gradient-to-br from-cyan-500 to-blue-600 text-white'
                        }`}>
                          {isSelected ? <Check className="w-4 h-4" /> : d.nome.charAt(0)}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-sm text-[hsl(var(--foreground))] truncate">
                            {d.nome}
                          </p>
                          <p className="text-xs text-[hsl(var(--muted-foreground))]">
                            {DIARIST_TYPE_LABELS[d.tipos_servico?.[0] as DiaristType] || d.tipos_servico?.[0] || 'outros'} - {formatCurrency(parseFloat(d.valor_diaria) || 0)}
                          </p>
                        </div>
                        {isSelected && (
                          <span className="text-xs text-green-500 font-medium">Escalado</span>
                        )}
                      </div>
                    </div>
                  );
                })}

                {diarists.length === 0 && (
                  <div className="text-center py-8 text-[hsl(var(--muted-foreground))]">
                    <Users className="w-8 h-8 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">Nenhum diarista ativo encontrado</p>
                  </div>
                )}
              </div>
            </div>

            {/* Coluna: Escalados */}
            <div>
              <h2 className="text-sm font-semibold text-[hsl(var(--muted-foreground))] uppercase tracking-wider mb-3">
                Escalados ({selected.size})
              </h2>

              {selected.size === 0 ? (
                <div className="bg-[hsl(var(--card))] border border-dashed border-[hsl(var(--border))] rounded-xl p-8 text-center">
                  <Calendar className="w-8 h-8 mx-auto mb-2 text-[hsl(var(--muted-foreground))] opacity-50" />
                  <p className="text-sm text-[hsl(var(--muted-foreground))]">
                    Selecione diaristas na lista ao lado
                  </p>
                </div>
              ) : (
                <div className="space-y-3 max-h-[500px] overflow-y-auto pr-2">
                  {Array.from(selected.entries()).map(([id, item]) => {
                    const d = diarists.find(d => d.id === id);
                    if (!d) return null;
                    return (
                      <div
                        key={id}
                        className="bg-[hsl(var(--card))] border border-green-500/30 rounded-xl p-4"
                      >
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-2">
                            <div className="w-8 h-8 rounded-full bg-green-500 flex items-center justify-center text-white text-sm font-medium">
                              {d.nome.charAt(0)}
                            </div>
                            <div>
                              <p className="font-medium text-sm">{d.nome}</p>
                              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                                {formatCurrency(parseFloat(d.valor_diaria) || 0)}/dia
                              </p>
                            </div>
                          </div>
                          <button
                            onClick={() => toggleDiarist(d)}
                            className="text-red-400 hover:text-red-500 transition-colors"
                          >
                            <XCircle className="w-5 h-5" />
                          </button>
                        </div>

                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <label className="text-xs text-[hsl(var(--muted-foreground))] block mb-1">
                              <Clock className="w-3 h-3 inline mr-1" />Inicio
                            </label>
                            <input
                              type="time"
                              value={item.horario_inicio || '08:00'}
                              onChange={(e) => updateItem(id, 'horario_inicio', e.target.value)}
                              className="w-full px-2 py-1 rounded border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
                            />
                          </div>
                          <div>
                            <label className="text-xs text-[hsl(var(--muted-foreground))] block mb-1">
                              <Clock className="w-3 h-3 inline mr-1" />Fim
                            </label>
                            <input
                              type="time"
                              value={item.horario_fim || '17:00'}
                              onChange={(e) => updateItem(id, 'horario_fim', e.target.value)}
                              className="w-full px-2 py-1 rounded border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
                            />
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Botao Confirmar */}
              {selected.size > 0 && (
                <div className="mt-4 pt-4 border-t border-[hsl(var(--border))]">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-sm text-[hsl(var(--muted-foreground))]">
                      {selected.size} diarista{selected.size > 1 ? 's' : ''} - {selectedDate}
                    </span>
                    <span className="text-lg font-bold text-green-500">
                      {formatCurrency(totalValor)}
                    </span>
                  </div>
                  <Button
                    variant="primary"
                    className="w-full"
                    onClick={handleConfirm}
                    disabled={isSaving}
                  >
                    {isSaving ? (
                      <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                    ) : (
                      <CheckCircle className="w-4 h-4 mr-2" />
                    )}
                    Confirmar Escala
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
