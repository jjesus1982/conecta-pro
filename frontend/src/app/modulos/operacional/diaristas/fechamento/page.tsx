'use client';

import { ArrowLeft, FileText, DollarSign, Users, Calendar, RefreshCw, CheckCircle, AlertTriangle, CreditCard } from 'lucide-react';
import { useEffect, useState } from 'react';
import Link from 'next/link';
;
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { useAuth } from '@/hooks/useAuth';
import { useCondominio } from '@/contexts/CondominioContext';
import { usePayrollReport, useGeneratePayments } from '@/hooks/operacional/useDiarists';
import type {
  PayrollDiaristItem,
} from '@/lib/services/diarists';

export default function FechamentoFolhaPage() {
  const { isLoading: authLoading } = useAuth();
  const { condominioId } = useCondominio();

  // Datas divergem entre SSR e client (React #418) — renderizar só após mount
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // Default = mes anterior
  const now = new Date();
  const lastMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const defaultCompetencia = `${lastMonth.getFullYear()}-${String(lastMonth.getMonth() + 1).padStart(2, '0')}`;

  const [competencia, setCompetencia] = useState(defaultCompetencia);
  const [showReport, setShowReport] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);

  // Hook para relatório de folha
  const {
    data: report,
    isLoading,
    refetch,
  } = usePayrollReport(
    { competencia },
    { query: { enabled: showReport } },
  );

  // Hook para gerar pagamentos
  const generatePaymentsMutation = useGeneratePayments();

  const handleGenerateReport = () => {
    setError(null);
    setSuccess(null);
    setShowReport(true);
    refetch();
  };

  const handleGeneratePayments = async () => {
    if (!report) return;

    setIsGenerating(true);
    setError(null);
    setSuccess(null);
    setShowConfirm(false);

    try {
      const result = await generatePaymentsMutation.mutateAsync({
        params: {
          condominio_id: condominioId,
          competencia,
          forma_pagamento: 'pix',
        } as any,
      } as any);

      const data = result as any;
      if (data.total_erros > 0) {
        setError(`${data.total_gerados} gerados, ${data.total_erros} erros: ${data.erros.join('; ')}`);
      }

      if (data.total_gerados > 0) {
        setSuccess(`${data.total_gerados} pagamentos gerados com sucesso para ${competencia}!`);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Erro desconhecido';
      setError(`Erro ao gerar pagamentos: ${message}`);
      void err;
    } finally {
      setIsGenerating(false);
    }
  };

  const formatCurrency = (value: number | string) => {
    const num = typeof value === 'string' ? parseFloat(value) : value;
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(num);
  };

  const formatCPF = (cpf: string) => {
    const clean = cpf.replace(/\D/g, '');
    if (clean.length === 11) {
      return `${clean.slice(0, 3)}.${clean.slice(3, 6)}.${clean.slice(6, 9)}-${clean.slice(9)}`;
    }
    return cpf;
  };

  if (authLoading || !mounted) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <FileText className="w-12 h-12" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-grid">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <PageHeader
          eyebrow="OPERACIONAL · DIARISTAS"
          title="Fechamento de Folha"
          subtitle="Relatorio mensal de diaristas"
          icon={<FileText className="w-5 h-5" />}
          actions={
            <Link href="/modulos/operacional/diaristas">
              <Button variant="ghost" size="sm">
                <ArrowLeft className="w-4 h-4 mr-2" />
                Diaristas
              </Button>
            </Link>
          }
        />

        {/* Seletor de Competência */}
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 mb-6">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <Calendar className="w-5 h-5 text-[hsl(var(--muted-foreground))]" />
              <label className="text-sm font-medium text-[hsl(var(--foreground))]">
                Competência:
              </label>
            </div>
            <input
              type="month"
              value={competencia}
              onChange={(e) => setCompetencia(e.target.value)}
              className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
            />
            <Button
              variant="primary"
              size="sm"
              onClick={handleGenerateReport}
              disabled={isLoading}
            >
              {isLoading ? (
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <FileText className="w-4 h-4 mr-2" />
              )}
              Gerar Relatorio
            </Button>
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
              <FileText className="w-8 h-8" />
            </div>
          </div>
        )}

        {/* Relatorio */}
        {report && !isLoading && (
          <>
            {/* Stats Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center">
                    <Users className="w-5 h-5 text-cyan-500" />
                  </div>
                  <div>
                    <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{report.total_diaristas}</p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Diaristas</p>
                  </div>
                </div>
              </div>

              <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center">
                    <Calendar className="w-5 h-5 text-purple-500" />
                  </div>
                  <div>
                    <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{report.total_diarias}</p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Total Diarias</p>
                  </div>
                </div>
              </div>

              <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                    <DollarSign className="w-5 h-5 text-blue-500" />
                  </div>
                  <div>
                    <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                      {formatCurrency(report.valor_bruto_total ?? 0)}
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Valor Bruto</p>
                  </div>
                </div>
              </div>

              <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                    <DollarSign className="w-5 h-5 text-green-500" />
                  </div>
                  <div>
                    <p className="font-data text-2xl font-semibold tabular-nums text-green-500">
                      {formatCurrency(report.valor_liquido_total ?? 0)}
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Valor Liquido</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Tabela */}
            <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden mb-6">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--muted))]/30">
                      <th className="text-left px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Nome</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">CPF</th>
                      <th className="text-center px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Diarias</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Bruto</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">INSS 11%</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Liquido</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">PIX/Banco</th>
                    </tr>
                  </thead>
                  <tbody>
                    {((report.items ?? []) as unknown as PayrollDiaristItem[]).map((item: PayrollDiaristItem, index: number) => (
                      <tr
                        key={item.diarist_id}
                        className={`border-b border-[hsl(var(--border))]/50 ${
                          index % 2 === 0 ? '' : 'bg-[hsl(var(--muted))]/10'
                        }`}
                      >
                        <td className="px-4 py-3 text-sm font-medium text-[hsl(var(--foreground))]">
                          {item.diarist_nome}
                        </td>
                        <td className="px-4 py-3 text-sm text-[hsl(var(--muted-foreground))]">
                          {formatCPF(item.cpf)}
                        </td>
                        <td className="px-4 py-3 text-sm text-center text-[hsl(var(--foreground))]">
                          {item.quantidade_diarias}
                        </td>
                        <td className="px-4 py-3 text-sm text-right text-[hsl(var(--foreground))]">
                          {formatCurrency(item.valor_bruto ?? 0)}
                        </td>
                        <td className="px-4 py-3 text-sm text-right text-red-400">
                          -{formatCurrency(item.inss_retido ?? 0)}
                        </td>
                        <td className="px-4 py-3 text-sm text-right font-semibold text-green-500">
                          {formatCurrency(item.valor_liquido ?? 0)}
                        </td>
                        <td className="px-4 py-3 text-xs text-[hsl(var(--muted-foreground))]">
                          {item.pix || (item.banco ? `${item.banco} Ag:${item.agencia} Cc:${item.conta}` : '-')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="bg-[hsl(var(--muted))]/30 font-semibold">
                      <td className="px-4 py-3 text-sm" colSpan={2}>TOTAIS</td>
                      <td className="px-4 py-3 text-sm text-center">{report.total_diarias}</td>
                      <td className="px-4 py-3 text-sm text-right">{formatCurrency(report.valor_bruto_total ?? 0)}</td>
                      <td className="px-4 py-3 text-sm text-right text-red-400">-{formatCurrency(report.inss_total ?? 0)}</td>
                      <td className="px-4 py-3 text-sm text-right text-green-500">{formatCurrency(report.valor_liquido_total ?? 0)}</td>
                      <td></td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>

            {/* Empty state */}
            {(report.items ?? []).length === 0 && (
              <div className="text-center py-12 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl mb-6">
                <FileText className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhuma diaria concluida
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1">
                  Nao ha diarias concluidas na competencia {competencia}
                </p>
              </div>
            )}

            {/* Botao Gerar Pagamentos */}
            {(report.items ?? []).length > 0 && (
              <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
                {!showConfirm ? (
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-[hsl(var(--foreground))]">
                        <strong>{report.total_diaristas}</strong> diaristas - <strong>{report.total_diarias}</strong> diarias
                      </p>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">
                        Valor liquido total: {formatCurrency(report.valor_liquido_total ?? 0)}
                      </p>
                    </div>
                    <Button
                      variant="primary"
                      onClick={() => setShowConfirm(true)}
                    >
                      <CreditCard className="w-4 h-4 mr-2" />
                      Gerar Pagamentos
                    </Button>
                  </div>
                ) : (
                  <div>
                    <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-3 mb-4">
                      <div className="flex items-center gap-2 mb-1">
                        <AlertTriangle className="w-4 h-4 text-yellow-500" />
                        <p className="text-sm font-medium text-yellow-500">Confirmar geracao de pagamentos</p>
                      </div>
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">
                        Serao gerados <strong>{report.total_diaristas}</strong> pagamentos no valor total de{' '}
                        <strong className="text-green-500">{formatCurrency(report.valor_liquido_total ?? 0)}</strong>.
                        Esta acao nao pode ser desfeita.
                      </p>
                    </div>
                    <div className="flex items-center gap-2 justify-end">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setShowConfirm(false)}
                      >
                        Cancelar
                      </Button>
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={handleGeneratePayments}
                        disabled={isGenerating}
                      >
                        {isGenerating ? (
                          <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                        ) : (
                          <CheckCircle className="w-4 h-4 mr-2" />
                        )}
                        Confirmar e Gerar
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
