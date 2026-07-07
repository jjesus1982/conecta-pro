'use client';

import { Banknote, TrendingUp, CheckCircle2, AlertTriangle, RefreshCw } from 'lucide-react';
import { Card } from '@/components/ui/card';
import type { ValoresFiscaisResumo } from '@/hooks/useValoresFiscaisResumo';

const brl = (value: number) =>
  new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);

const pct = (value: number) => `${value.toFixed(1)}%`;

function SkeletonCard() {
  return (
    <div className="bg-gradient-to-br from-[#1E3A5F] to-[#2d5a9e] rounded-2xl p-6 text-white animate-pulse">
      <div className="h-6 w-48 bg-white/20 rounded mb-2" />
      <div className="h-10 w-64 bg-white/20 rounded mb-4" />
      <div className="h-4 w-80 bg-white/20 rounded mb-6" />
      <div className="grid grid-cols-3 gap-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-16 bg-white/10 rounded-xl" />
        ))}
      </div>
    </div>
  );
}

interface Props {
  data: ValoresFiscaisResumo | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}

export function ValoresFiscaisCard({ data, isLoading, isError, onRetry }: Props) {
  if (isLoading) return <SkeletonCard />;

  if (isError || !data) {
    return (
      <Card className="bg-red-500/10 border-red-500/30 p-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <AlertTriangle className="text-red-500" size={20} />
          <p className="text-sm text-red-500 font-medium">
            Não foi possível carregar o resumo fiscal
          </p>
        </div>
        <button
          onClick={onRetry}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-500 rounded-lg transition-colors"
        >
          <RefreshCw size={12} />
          Tentar novamente
        </button>
      </Card>
    );
  }

  const { fgts, inss, consolidado, confianca } = data;

  // Para exibir "valor pago" sem duplicar GUIA+RELATORIO, usar apenas tipos únicos
  const fgtsGuia = fgts.por_tipo.find((t) => t.tipo === 'GUIA');
  const fgtsConsignado = fgts.por_tipo.find((t) => t.tipo === 'CONSIGNADO');

  return (
    <div className="bg-gradient-to-br from-[#1E3A5F] to-[#2d5a9e] rounded-2xl p-6 text-white shadow-lg">
      {/* Header */}
      <div className="flex items-start justify-between mb-1">
        <div className="flex items-center gap-2 text-blue-200 text-sm font-medium">
          <Banknote size={16} />
          Total fiscal extraído automaticamente
        </div>
        <div className="flex items-center gap-1.5 text-xs text-green-300 bg-green-900/30 px-2 py-1 rounded-full">
          <CheckCircle2 size={11} />
          IA verificada
        </div>
      </div>

      {/* Big number */}
      <p className="text-4xl font-bold tracking-tight mb-1">
        {brl(consolidado.valor_total_fiscal_brl)}
      </p>

      {/* Breakdown */}
      <p className="text-blue-200 text-sm mb-5">
        FGTS {brl(fgts.total_brl)}{' '}
        <span className="text-blue-300 text-xs">({fgts.total_registros} guias)</span>
        {' · '}
        INSS {brl(inss.total_brl)}{' '}
        <span className="text-blue-300 text-xs">({inss.total_registros} guias)</span>
      </p>

      {/* Stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <StatBox
          label="GFD FGTS"
          value={brl(fgtsGuia?.soma ?? 0)}
          sub={`${fgtsGuia?.count ?? 0} guias`}
        />
        <StatBox
          label="FGTS Consignado"
          value={brl(fgtsConsignado?.soma ?? 0)}
          sub={`${fgtsConsignado?.count ?? 0} guias`}
        />
        <StatBox label="INSS DARF" value={brl(inss.total_brl)} sub={`${inss.total_registros} guias`} />
        <StatBox
          label="Taxa extração"
          value={pct(consolidado.taxa_extracao_pct)}
          sub={`${consolidado.docs_extraidos}/${consolidado.total_docs_fiscais} docs`}
          highlight
        />
      </div>

      {/* Barra de progresso */}
      <div className="mb-4">
        <div className="flex justify-between text-xs text-blue-200 mb-1">
          <span>Docs fiscais processados</span>
          <span>
            {consolidado.docs_extraidos}/{consolidado.total_docs_fiscais}
          </span>
        </div>
        <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-green-400 to-emerald-300 rounded-full transition-all duration-700"
            style={{
              width: `${Math.min(consolidado.taxa_extracao_pct, 100)}%`,
            }}
          />
        </div>
      </div>

      {/* Tags de confiança */}
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="flex items-center gap-1 bg-green-900/40 text-green-300 px-2 py-1 rounded-full">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block" />
          {confianca.alta_auto_save} auto-salvos
        </span>
        {confianca.media_revisao_manual > 0 && (
          <span className="flex items-center gap-1 bg-yellow-900/40 text-yellow-300 px-2 py-1 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 inline-block" />
            {confianca.media_revisao_manual} revisão manual
          </span>
        )}
        {confianca.baixa_rejeitado > 0 && (
          <span className="flex items-center gap-1 bg-red-900/40 text-red-300 px-2 py-1 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-red-400 inline-block" />
            {confianca.baixa_rejeitado} rejeitados
          </span>
        )}
        <span className="flex items-center gap-1 text-blue-300">
          <TrendingUp size={11} />
          {consolidado.total_docs_sistema} docs no sistema
        </span>
      </div>
    </div>
  );
}

function StatBox({
  label,
  value,
  sub,
  highlight = false,
}: {
  label: string;
  value: string;
  sub: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`rounded-xl p-3 ${
        highlight ? 'bg-white/20' : 'bg-white/10'
      }`}
    >
      <p className="text-blue-200 text-xs mb-1 truncate">{label}</p>
      <p className={`font-bold ${highlight ? 'text-lg' : 'text-sm'}`}>{value}</p>
      <p className="text-blue-300 text-xs">{sub}</p>
    </div>
  );
}
