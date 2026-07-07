'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  TrendingUp,
  Calculator,
  AlertCircle,
  CheckCircle,
  BarChart2,
  Scale,
  Building2,
  ChevronDown,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

// ─── Tipos ──────────────────────────────────────────────────────────────────

interface CalcForm {
  receita: string;
  custo_direto: string;
  custo_indireto: string;
  tipo_servico: string;
  empresa: string;
  liminares: string[];
}

interface CalcResult {
  receita: number;
  impostos: number;
  pct_impostos: number;
  regime: string;
  receita_liquida: number;
  custo_direto: number;
  custo_indireto: number;
  lucro: number;
  margem: number;
  situacao: string;
  empresa: string;
}

// ─── Calculadoras ──────────────────────────────────────────────────────────

function calcularImpostos(
  receita: number,
  empresa: string,
  tipoServico: string,
  liminares: string[]
): { impostos: number; regime: string } {
  if (empresa === 'eletronica') {
    // Lucro Real (atual) — estimativa
    const irpj = receita * 0.32 * 0.15;
    const csll = receita * 0.32 * 0.09;
    const pis = receita * 0.0165;
    const cofins = receita * 0.076;
    const iss = receita * 0.05;
    return { impostos: irpj + csll + pis + cofins + iss, regime: 'Lucro Real' };
  } else {
    // Simples Nacional Anexo III
    // RBT12 estimado = receita * 12 (simplificado)
    const rbt12 = receita * 12;
    const faixas = [
      { limite: 180000, aliq: 0.06, ded: 0 },
      { limite: 360000, aliq: 0.112, ded: 9360 },
      { limite: 720000, aliq: 0.135, ded: 17640 },
      { limite: 1800000, aliq: 0.16, ded: 35640 },
      { limite: 3600000, aliq: 0.21, ded: 125640 },
      { limite: 4800000, aliq: 0.33, ded: 648000 },
    ];
    const faixa = faixas.find((f) => rbt12 <= f.limite) || faixas[faixas.length - 1];
    const aliqEfetiva = rbt12 > 0 ? (rbt12 * faixa!.aliq - faixa!.ded) / rbt12 : faixa!.aliq;
    let das = receita * aliqEfetiva;
    if (liminares.includes('pis_cofins_zero')) {
      das -= das * (0.0278 + 0.1282);
    }
    return { impostos: das, regime: 'Simples Nacional' };
  }
}

function calcularResultado(form: CalcForm): CalcResult | null {
  const receita = parseFloat(form.receita.replace(',', '.')) || 0;
  const custoDireto = parseFloat(form.custo_direto.replace(',', '.')) || 0;
  const custoIndireto = parseFloat(form.custo_indireto.replace(',', '.')) || 0;
  if (receita <= 0) return null;

  const { impostos, regime } = calcularImpostos(receita, form.empresa, form.tipo_servico, form.liminares);
  const receitaLiquida = receita - impostos;
  const lucro = receitaLiquida - custoDireto - custoIndireto;
  const margem = receita > 0 ? (lucro / receita) * 100 : 0;

  let situacao = '';
  if (margem >= 25) situacao = 'Excelente';
  else if (margem >= 20) situacao = 'Bom';
  else if (margem >= 10) situacao = 'Aceitável';
  else if (margem >= 0) situacao = 'Atenção';
  else situacao = 'Deficitário';

  return {
    receita,
    impostos,
    pct_impostos: receita > 0 ? (impostos / receita) * 100 : 0,
    regime,
    receita_liquida: receitaLiquida,
    custo_direto: custoDireto,
    custo_indireto: custoIndireto,
    lucro,
    margem,
    situacao,
    empresa: form.empresa === 'eletronica' ? 'Conecta Mais Eletrônica' : 'Conecta Mais Patrimonial',
  };
}

const fmt = (v: number) =>
  v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

const FORM_EMPTY: CalcForm = {
  receita: '',
  custo_direto: '',
  custo_indireto: '',
  tipo_servico: '',
  empresa: '',
  liminares: [],
};

// ─── Componente Principal ──────────────────────────────────────────────────

export default function RentabilidadePage() {
  const [form, setForm] = useState<CalcForm>(FORM_EMPTY);
  const [result, setResult] = useState<CalcResult | null>(null);
  const [showComparativo, setShowComparativo] = useState(false);
  const [resultComp, setResultComp] = useState<{ eletronica: CalcResult | null; patrimonial: CalcResult | null }>({
    eletronica: null,
    patrimonial: null,
  });

  const toggleLiminar = (val: string) => {
    setForm((f) => ({
      ...f,
      liminares: f.liminares.includes(val) ? f.liminares.filter((x) => x !== val) : [...f.liminares, val],
    }));
  };

  const handleCalc = () => {
    const r = calcularResultado(form);
    setResult(r);
    setShowComparativo(false);
  };

  const handleComparar = () => {
    const baseForm = { ...form, liminares: [] };
    const rEletronica = calcularResultado({ ...baseForm, empresa: 'eletronica' });
    const rPatrimonial = calcularResultado({ ...baseForm, empresa: 'patrimonial', liminares: [] });
    setResultComp({ eletronica: rEletronica, patrimonial: rPatrimonial });
    setShowComparativo(true);
  };

  const margemColor = (m: number) => {
    if (m >= 20) return 'text-green-600';
    if (m >= 10) return 'text-yellow-600';
    return 'text-red-600';
  };

  const margemBg = (m: number) => {
    if (m >= 20) return 'bg-green-50 border-green-200';
    if (m >= 10) return 'bg-yellow-50 border-yellow-200';
    return 'bg-red-50 border-red-200';
  };

  const situacaoColor = (s: string) => {
    if (s === 'Excelente' || s === 'Bom') return 'text-green-600 bg-green-100';
    if (s === 'Aceitável') return 'text-yellow-600 bg-yellow-100';
    if (s === 'Atenção') return 'text-orange-600 bg-orange-100';
    return 'text-red-600 bg-red-100';
  };

  const reginaAuto =
    form.empresa === 'eletronica'
      ? 'Lucro Real (atual)'
      : form.empresa === 'patrimonial'
      ? 'Simples Nacional Anexo III'
      : '—';

  return (
    <div className="min-h-screen bg-gray-50 p-4 md:p-8">
      {/* Header */}
      <div className="mb-6">
        <Link
          href="/modulos/empresas"
          className="flex items-center gap-2 text-sm text-gray-500 hover:text-[#111b57] mb-4 transition-colors w-fit"
        >
          <ArrowLeft className="h-4 w-4" />
          Voltar para Multi-Empresa
        </Link>
        <h1 className="font-display text-2xl md:text-3xl font-bold text-[hsl(var(--foreground))] flex items-center gap-3">
          <TrendingUp className="h-8 w-8 text-[#f97707]" />
          Rentabilidade por Contrato
        </h1>
        <p className="text-gray-500 mt-1">
          Calcule a margem real de cada contrato considerando impostos, regime e liminares
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
        {/* Form */}
        <Card className="xl:col-span-2 border border-gray-200 shadow-sm h-fit">
          <CardContent className="p-6">
            <h2 className="font-bold text-[#111b57] mb-5 flex items-center gap-2">
              <Calculator className="h-5 w-5 text-[#f97707]" />
              Dados do Contrato
            </h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Receita Bruta Mensal (R$) *
                </label>
                <input
                  type="number"
                  value={form.receita}
                  onChange={(e) => setForm((f) => ({ ...f, receita: e.target.value }))}
                  placeholder="Ex: 50000"
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a47f5]"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Custo Direto Mensal (R$)
                </label>
                <input
                  type="number"
                  value={form.custo_direto}
                  onChange={(e) => setForm((f) => ({ ...f, custo_direto: e.target.value }))}
                  placeholder="Mão de obra, uniformes, etc."
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a47f5]"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Custo Indireto Mensal (R$)
                </label>
                <input
                  type="number"
                  value={form.custo_indireto}
                  onChange={(e) => setForm((f) => ({ ...f, custo_indireto: e.target.value }))}
                  placeholder="Overhead, administrativo, etc."
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a47f5]"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Tipo de Serviço
                </label>
                <select
                  value={form.tipo_servico}
                  onChange={(e) => setForm((f) => ({ ...f, tipo_servico: e.target.value }))}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a47f5] bg-white"
                >
                  <option value="">Selecione...</option>
                  <option value="vigilancia">Vigilância</option>
                  <option value="portaria">Portaria Presencial</option>
                  <option value="portaria_remota">Portaria Remota</option>
                  <option value="cftv">CFTV</option>
                  <option value="alarmes">Alarmes</option>
                  <option value="monitoramento">Monitoramento</option>
                  <option value="limpeza">Limpeza e Conservação</option>
                  <option value="jardinagem">Jardinagem</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Empresa *
                </label>
                <select
                  value={form.empresa}
                  onChange={(e) => setForm((f) => ({ ...f, empresa: e.target.value, liminares: [] }))}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a47f5] bg-white"
                >
                  <option value="">Selecione...</option>
                  <option value="eletronica">Conecta Mais Eletrônica</option>
                  <option value="patrimonial">Conecta Mais Patrimonial</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Regime Tributário
                </label>
                <div className="border border-gray-200 rounded-lg px-3 py-2 bg-gray-50 text-sm text-gray-600">
                  {reginaAuto}
                </div>
              </div>

              {form.empresa === 'patrimonial' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Liminares Ativas
                  </label>
                  <div className="space-y-2">
                    {[
                      { val: 'pis_cofins_zero', label: 'PIS/COFINS = 0' },
                      { val: 'inss_nao_retido', label: 'INSS Não Retido' },
                    ].map((lim) => (
                      <label key={lim.val} className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={form.liminares.includes(lim.val)}
                          onChange={() => toggleLiminar(lim.val)}
                          className="w-4 h-4 rounded border-gray-300 accent-[#1a47f5]"
                        />
                        <span className="text-sm text-gray-700">{lim.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex gap-3 pt-2">
                <button
                  onClick={handleCalc}
                  disabled={!form.receita || !form.empresa}
                  className="flex-1 bg-[#111b57] hover:bg-[#1a47f5] disabled:opacity-50 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors"
                >
                  Calcular
                </button>
                <button
                  onClick={handleComparar}
                  disabled={!form.receita}
                  className="flex-1 border-2 border-[#111b57] text-[#111b57] hover:bg-[#111b57] hover:text-white disabled:opacity-50 font-semibold py-2.5 rounded-lg text-sm transition-colors"
                >
                  Comparar
                </button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Results */}
        <div className="xl:col-span-3 space-y-6">
          {!result && !showComparativo && (
            <div className="flex flex-col items-center justify-center h-64 text-gray-400">
              <BarChart2 className="h-16 w-16 mb-4 opacity-30" />
              <p className="text-sm">Preencha os dados e clique em Calcular</p>
            </div>
          )}

          {/* Resultado Individual */}
          {result && !showComparativo && (
            <Card className={cn('border-2 shadow-sm', margemBg(result.margem))}>
              <CardContent className="p-6">
                <div className="flex items-center justify-between mb-5">
                  <h3 className="font-bold text-gray-800 flex items-center gap-2">
                    <Building2 className="h-5 w-5 text-[#f97707]" />
                    {result.empresa}
                  </h3>
                  <div className="flex items-center gap-2">
                    <span className={cn('text-xs font-semibold px-3 py-1 rounded-full', situacaoColor(result.situacao))}>
                      {result.situacao}
                    </span>
                  </div>
                </div>

                {/* DRE simplificado */}
                <div className="space-y-2">
                  {[
                    { label: 'Receita Bruta', value: result.receita, type: 'positive', indent: false },
                    { label: `(-) Impostos — ${result.regime} (${result.pct_impostos.toFixed(1)}%)`, value: -result.impostos, type: 'negative', indent: true },
                    { label: '(=) Receita Líquida', value: result.receita_liquida, type: 'neutral', indent: false, bold: true },
                    { label: '(-) Custo Direto', value: -result.custo_direto, type: 'negative', indent: true },
                    { label: '(-) Custo Indireto', value: -result.custo_indireto, type: 'negative', indent: true },
                    { label: '(=) Lucro Líquido', value: result.lucro, type: result.lucro >= 0 ? 'positive' : 'negative', indent: false, bold: true, large: true },
                  ].map((row) => (
                    <div
                      key={row.label}
                      className={cn(
                        'flex justify-between items-center py-2',
                        row.bold ? 'border-t border-gray-300 pt-3' : '',
                        row.indent ? 'pl-4' : ''
                      )}
                    >
                      <span className={cn('text-sm', row.bold ? 'font-bold text-gray-800' : 'text-gray-600')}>
                        {row.label}
                      </span>
                      <span
                        className={cn(
                          'font-semibold',
                          row.large ? 'text-xl' : 'text-sm',
                          row.type === 'positive' ? 'text-green-700' : row.type === 'negative' ? 'text-red-600' : 'text-gray-800'
                        )}
                      >
                        {row.value < 0
                          ? `(${fmt(Math.abs(row.value))})`
                          : fmt(row.value)}
                      </span>
                    </div>
                  ))}
                </div>

                {/* Margem destaque */}
                <div className="mt-5 flex items-center justify-between bg-white rounded-xl px-5 py-4 border border-gray-200">
                  <div>
                    <p className="text-xs text-gray-500">Margem Líquida</p>
                    <p className={cn('font-data text-3xl font-semibold tabular-nums', margemColor(result.margem))}>
                      {result.margem.toFixed(1)}%
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-gray-500">Situação</p>
                    <p className={cn('text-lg font-bold', margemColor(result.margem))}>
                      {result.situacao}
                    </p>
                  </div>
                </div>

                {result.margem < 10 && (
                  <div className="mt-4 bg-red-50 border border-red-200 rounded-xl p-3 flex gap-2">
                    <AlertCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
                    <p className="text-xs text-red-700">
                      Margem abaixo do mínimo recomendado (10%). Revise os custos ou renegocie o contrato.
                    </p>
                  </div>
                )}
                {result.margem >= 20 && (
                  <div className="mt-4 bg-green-50 border border-green-200 rounded-xl p-3 flex gap-2">
                    <CheckCircle className="h-4 w-4 text-green-500 shrink-0 mt-0.5" />
                    <p className="text-xs text-green-700">
                      Excelente rentabilidade! Este contrato contribui positivamente para o resultado da empresa.
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Comparativo */}
          {showComparativo && (
            <>
              <h3 className="font-bold text-[#111b57] flex items-center gap-2 text-lg">
                <Scale className="h-5 w-5 text-[#f97707]" />
                Comparativo entre Empresas
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {[
                  { key: 'eletronica' as const, label: 'Conecta Mais Eletrônica', color: 'border-[#111b57]' },
                  { key: 'patrimonial' as const, label: 'Conecta Mais Patrimonial', color: 'border-[#f97707]' },
                ].map((col) => {
                  const r = resultComp[col.key];
                  if (!r) return null;
                  return (
                    <Card key={col.key} className={cn('border-2 shadow-sm', col.color)}>
                      <CardContent className="p-5">
                        <p className="font-bold text-gray-800 text-sm mb-4">{col.label}</p>
                        <div className="space-y-2 text-sm">
                          <div className="flex justify-between">
                            <span className="text-gray-500">Regime</span>
                            <span className="font-medium text-gray-800">{r.regime}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-500">Impostos</span>
                            <span className="text-red-600 font-medium">{fmt(r.impostos)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-500">Carga Tributária</span>
                            <span className="font-medium text-gray-800">{r.pct_impostos.toFixed(1)}%</span>
                          </div>
                          <div className="flex justify-between border-t border-gray-200 pt-2">
                            <span className="text-gray-500">Lucro Líquido</span>
                            <span className={cn('font-bold', r.lucro >= 0 ? 'text-green-700' : 'text-red-600')}>
                              {fmt(r.lucro)}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-500">Margem</span>
                            <span className={cn('font-bold text-xl', margemColor(r.margem))}>
                              {r.margem.toFixed(1)}%
                            </span>
                          </div>
                        </div>
                        <div className={cn('mt-3 rounded-lg px-3 py-1.5 text-center text-xs font-semibold', situacaoColor(r.situacao))}>
                          {r.situacao}
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>

              {resultComp.eletronica && resultComp.patrimonial && (
                <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
                  <p className="font-semibold text-blue-800 text-sm mb-1">Análise Comparativa</p>
                  <p className="text-sm text-blue-700">
                    {resultComp.patrimonial.margem > resultComp.eletronica.margem
                      ? `A Patrimonial tem margem ${(resultComp.patrimonial.margem - resultComp.eletronica.margem).toFixed(1)}pp maior — considere faturar por ela para este tipo de serviço.`
                      : `A Eletrônica tem margem ${(resultComp.eletronica.margem - resultComp.patrimonial.margem).toFixed(1)}pp maior — considere faturar por ela para este tipo de serviço.`}
                  </p>
                </div>
              )}
            </>
          )}

          {/* Legenda de margem */}
          <Card className="border border-gray-200">
            <CardContent className="p-4">
              <p className="text-sm font-semibold text-gray-700 mb-3">Referência de Margens</p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {[
                  { label: 'Excelente', range: '≥ 25%', color: 'bg-green-100 text-green-700' },
                  { label: 'Bom', range: '20–25%', color: 'bg-green-50 text-green-600' },
                  { label: 'Aceitável', range: '10–20%', color: 'bg-yellow-100 text-yellow-700' },
                  { label: 'Atenção / Déficit', range: '< 10%', color: 'bg-red-100 text-red-700' },
                ].map((ref) => (
                  <div key={ref.label} className={cn('rounded-lg p-2 text-center text-xs font-semibold', ref.color)}>
                    <p>{ref.label}</p>
                    <p className="opacity-75 font-normal">{ref.range}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
