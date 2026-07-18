'use client';

import { useState } from 'react';
import {
  Building2,
  CheckCircle,
  Clock,
  ChevronRight,
  Calculator,
  ArrowRight,
  AlertCircle,
  Lightbulb,
  Scale,
  TrendingUp,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import Link from 'next/link';

// ─── Calculadoras ──────────────────────────────────────────────────────────

function calcularSimples(
  receita: number,
  rbt12: number,
  liminares: string[]
): { aliqEfetiva: string; das: string; economia: string } {
  const faixas = [
    { limite: 180000, aliq: 0.06, ded: 0 },
    { limite: 360000, aliq: 0.112, ded: 9360 },
    { limite: 720000, aliq: 0.135, ded: 17640 },
    { limite: 1800000, aliq: 0.16, ded: 35640 },
    { limite: 3600000, aliq: 0.21, ded: 125640 },
    { limite: 4800000, aliq: 0.33, ded: 648000 },
  ];
  const faixa = faixas.find((f) => rbt12 <= f.limite) ?? { limite: 4800000, aliq: 0.33, ded: 648000 };
  const aliqEfetiva =
    rbt12 > 0 ? (rbt12 * faixa.aliq - faixa.ded) / rbt12 : faixa.aliq;
  let das = receita * aliqEfetiva;
  let economia = 0;
  if (liminares.includes('pis_cofins_zero')) {
    const pct = 0.0278 + 0.1282;
    economia = das * pct;
    das -= economia;
  }
  return {
    aliqEfetiva: (aliqEfetiva * 100).toFixed(2),
    das: das.toFixed(2),
    economia: economia.toFixed(2),
  };
}

function calcularLucroReal(receita: number, receitaTrimestre: number) {
  const lucroPresumido = receita * 0.32;
  const irpj = lucroPresumido * 0.15;
  const lucroTrimestre = receitaTrimestre * 0.32;
  const excedente = Math.max(0, lucroTrimestre - 60000);
  const irpjAdicional = (excedente * 0.1) / 3;
  const csll = lucroPresumido * 0.09;
  const pis = receita * 0.0165;
  const cofins = receita * 0.076;
  const iss = receita * 0.05;
  const total = irpj + irpjAdicional + csll + pis + cofins + iss;
  return {
    irpj,
    irpjAdicional,
    csll,
    pis,
    cofins,
    iss,
    total,
    pct: ((total / receita) * 100).toFixed(2),
  };
}

const fmt = (v: number) =>
  v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

// ─── Tipos de Serviço para Sugestão ────────────────────────────────────────

const SERVICO_EMPRESA: Record<string, { empresa: string; motivo: string }> = {
  vigilancia: {
    empresa: 'Conecta Mais Patrimonial',
    motivo: 'Vigilância é atividade-fim da Patrimonial (Simples Nacional + liminares)',
  },
  portaria: {
    empresa: 'Conecta Mais Patrimonial',
    motivo: 'Portaria presencial é core da Patrimonial',
  },
  portaria_remota: {
    empresa: 'Conecta Mais Eletrônica',
    motivo: 'Portaria Remota é serviço de tecnologia — melhor na Eletrônica',
  },
  cftv: {
    empresa: 'Conecta Mais Eletrônica',
    motivo: 'CFTV é serviço eletrônico — tributação mais vantajosa na Eletrônica',
  },
  alarmes: {
    empresa: 'Conecta Mais Eletrônica',
    motivo: 'Alarmes e monitoramento são serviços eletrônicos',
  },
  monitoramento: {
    empresa: 'Conecta Mais Eletrônica',
    motivo: 'Monitoramento remoto é serviço de tecnologia da Eletrônica',
  },
  limpeza: {
    empresa: 'Conecta Mais Patrimonial',
    motivo: 'Limpeza e conservação são serviços da Patrimonial',
  },
  jardinagem: {
    empresa: 'Conecta Mais Patrimonial',
    motivo: 'Jardinagem é serviço da Patrimonial',
  },
};

// ─── Componente Principal ──────────────────────────────────────────────────

type CalcTab = 'simples' | 'lucro_real' | 'comparativo';

export default function EmpresasPage() {
  // Calculator state
  const [calcTab, setCalcTab] = useState<CalcTab>('simples');

  // Simples Nacional
  const [sReceita, setSReceita] = useState('');
  const [sRbt12, setSRbt12] = useState('');
  const [sLiminares, setSLiminares] = useState<string[]>([]);
  const [sResult, setSResult] = useState<ReturnType<typeof calcularSimples> | null>(null);

  // Lucro Real
  const [lReceita, setLReceita] = useState('');
  const [lTrimestre, setLTrimestre] = useState('');
  const [lResult, setLResult] = useState<ReturnType<typeof calcularLucroReal> | null>(null);

  // Comparativo
  const [cReceita, setCReceita] = useState('');
  const [cRbt12, setCRbt12] = useState('');
  const [cResult, setCResult] = useState<{
    simples: ReturnType<typeof calcularSimples>;
    lucro: ReturnType<typeof calcularLucroReal>;
  } | null>(null);

  // Sugestão de empresa
  const [tipoServico, setTipoServico] = useState('');
  const [sugestao, setSugestao] = useState<{ empresa: string; motivo: string } | null>(null);

  const toggleLiminar = (val: string) => {
    setSLiminares((prev) =>
      prev.includes(val) ? prev.filter((x) => x !== val) : [...prev, val]
    );
  };

  const handleCalcSimples = () => {
    const r = parseFloat(sReceita.replace(',', '.')) || 0;
    const rbt = parseFloat(sRbt12.replace(',', '.')) || 0;
    setSResult(calcularSimples(r, rbt, sLiminares));
  };

  const handleCalcLucro = () => {
    const r = parseFloat(lReceita.replace(',', '.')) || 0;
    const t = parseFloat(lTrimestre.replace(',', '.')) || 0;
    setLResult(calcularLucroReal(r, t));
  };

  const handleCalcComparativo = () => {
    const r = parseFloat(cReceita.replace(',', '.')) / 12 || 0;
    const rbt = parseFloat(cRbt12.replace(',', '.')) || 0;
    const t = parseFloat(cReceita.replace(',', '.')) / 4 || 0;
    setCResult({
      simples: calcularSimples(r, rbt, []),
      lucro: calcularLucroReal(r, t),
    });
  };

  const handleSugestao = () => {
    const result = SERVICO_EMPRESA[tipoServico];
    setSugestao(result || { empresa: 'Análise necessária', motivo: 'Consulte um contador para este tipo de serviço' });
  };

  return (
    <div className="min-h-screen bg-gray-50 p-4 md:p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold text-[hsl(var(--foreground))] flex items-center gap-3">
          <Building2 className="h-8 w-8 text-[#f97707]" />
          Gestão Multi-Empresa
        </h1>
        <p className="text-gray-500 mt-1">
          Gerencie as empresas do grupo, regimes tributários e liminares judiciais
        </p>
      </div>

      {/* Company Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-10">
        {/* Card Eletrônica */}
        <Card className="border border-gray-200 shadow-sm hover:shadow-md transition-shadow">
          <CardContent className="p-6">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-xl bg-[#111b57] flex items-center justify-center">
                  <Building2 className="h-6 w-6 text-white" />
                </div>
                <div>
                  <h2 className="font-bold text-[#111b57] text-lg leading-tight">
                    Conecta Mais Eletrônica
                  </h2>
                  <span className="text-xs font-semibold bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
                    CNPJ Principal
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-green-500" />
                <span className="text-xs text-green-600 font-medium">Ativa</span>
              </div>
            </div>

            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">CNPJ</span>
                <span className="font-mono font-medium text-gray-800">35.710.481/0001-03</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500">Regime Atual</span>
                <span className="text-xs font-semibold bg-red-100 text-red-700 px-2 py-0.5 rounded-full">
                  Lucro Real
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500">Regime Futuro</span>
                <div className="flex items-center gap-1 text-blue-600 font-medium text-xs">
                  <ArrowRight className="h-3.5 w-3.5" />
                  Simples Nacional
                </div>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">IM</span>
                <span className="font-mono text-gray-800">45177801</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">SUFRAMA</span>
                <span className="font-mono text-gray-800">210140500</span>
              </div>
              <div className="pt-2 border-t border-gray-100">
                <span className="text-gray-500 block mb-2">Serviços</span>
                <div className="flex flex-wrap gap-1.5">
                  {['Portaria Remota', 'CFTV', 'Alarmes', 'Monitoramento'].map((s) => (
                    <span
                      key={s}
                      className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full border border-blue-100"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <Link href="/modulos/empresas/rentabilidade">
              <button type="button" className="mt-5 w-full flex items-center justify-center gap-2 bg-[#111b57] hover:bg-[#1a47f5] text-white text-sm font-semibold py-2.5 rounded-lg transition-colors">
                Ver Detalhes
                <ChevronRight className="h-4 w-4" />
              </button>
            </Link>
          </CardContent>
        </Card>

        {/* Card Patrimonial */}
        <Card className="border border-yellow-200 shadow-sm hover:shadow-md transition-shadow">
          <CardContent className="p-6">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-xl bg-[#f97707] flex items-center justify-center">
                  <Building2 className="h-6 w-6 text-white" />
                </div>
                <div>
                  <h2 className="font-bold text-[#111b57] text-lg leading-tight">
                    Conecta Mais Patrimonial
                  </h2>
                  <span className="text-xs font-semibold bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded-full">
                    Em Abertura
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-yellow-400" />
                <span className="text-xs text-yellow-600 font-medium">Em Abertura</span>
              </div>
            </div>

            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">CNPJ</span>
                <span className="font-mono font-medium text-gray-800">66.014.833/0001-10</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500">Regime</span>
                <span className="text-xs font-semibold bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
                  Simples Nacional Anexo III
                </span>
              </div>
              <div className="pt-2 border-t border-gray-100">
                <span className="text-gray-500 block mb-2">Serviços</span>
                <div className="flex flex-wrap gap-1.5">
                  {['Vigilância', 'Portaria', 'Limpeza', 'Jardinagem'].map((s) => (
                    <span
                      key={s}
                      className="text-xs bg-orange-50 text-orange-700 px-2 py-0.5 rounded-full border border-orange-100"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
              <div className="pt-2 border-t border-gray-100">
                <div className="flex items-center gap-2 mb-2">
                  <Scale className="h-3.5 w-3.5 text-purple-600" />
                  <span className="text-gray-500 font-medium">Liminares</span>
                </div>
                <div className="space-y-1.5">
                  {[
                    { label: 'PIS/COFINS = 0', status: 'A Solicitar' },
                    { label: 'INSS Não Retido', status: 'A Solicitar' },
                  ].map((lim) => (
                    <div key={lim.label} className="flex justify-between items-center bg-yellow-50 rounded-lg px-3 py-1.5">
                      <span className="text-xs font-medium text-gray-700">{lim.label}</span>
                      <span className="text-xs font-semibold bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded-full">
                        {lim.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <Link href="/modulos/empresas/liminares">
              <button type="button" className="mt-5 w-full flex items-center justify-center gap-2 bg-[#f97707] hover:bg-orange-600 text-white text-sm font-semibold py-2.5 rounded-lg transition-colors">
                Ver Detalhes
                <ChevronRight className="h-4 w-4" />
              </button>
            </Link>
          </CardContent>
        </Card>
      </div>

      {/* Quick Nav */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-10">
        {[
          { href: '/modulos/empresas/liminares', icon: Scale, label: 'Liminares Judiciais', desc: '2 em andamento', color: 'text-purple-600', bg: 'bg-purple-50' },
          { href: '/modulos/empresas/rentabilidade', icon: TrendingUp, label: 'Rentabilidade', desc: 'Calcule por contrato', color: 'text-green-600', bg: 'bg-green-50' },
          { href: '#calculator', icon: Calculator, label: 'Calculadora Fiscal', desc: 'Simules impostos', color: 'text-blue-600', bg: 'bg-blue-50' },
        ].map((item) => (
          <Link key={item.href} href={item.href}>
            <Card className="border border-gray-200 hover:border-blue-300 hover:shadow-md transition-all cursor-pointer">
              <CardContent className="p-4 flex items-center gap-4">
                <div className={cn('w-10 h-10 rounded-lg flex items-center justify-center', item.bg)}>
                  <item.icon className={cn('h-5 w-5', item.color)} />
                </div>
                <div>
                  <p className="font-semibold text-gray-800 text-sm">{item.label}</p>
                  <p className="text-xs text-gray-500">{item.desc}</p>
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      {/* Calculadora de Impostos */}
      <div id="calculator" className="mb-10">
        <h2 className="text-xl font-bold text-[#111b57] flex items-center gap-2 mb-5">
          <Calculator className="h-6 w-6 text-[#f97707]" />
          Calculadora de Impostos
        </h2>

        {/* Tabs */}
        <div className="flex gap-1 bg-gray-100 rounded-xl p-1 mb-6 w-full max-w-lg">
          {(
            [
              { key: 'simples', label: 'Simples Nacional' },
              { key: 'lucro_real', label: 'Lucro Real' },
              { key: 'comparativo', label: 'Comparativo' },
            ] as { key: CalcTab; label: string }[]
          ).map((tab) => (
            <button
              key={tab.key}
              onClick={() => setCalcTab(tab.key)}
              className={cn(
                'flex-1 text-xs font-semibold py-2 rounded-lg transition-all',
                calcTab === tab.key
                  ? 'bg-white text-[#111b57] shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab: Simples Nacional */}
        {calcTab === 'simples' && (
          <Card className="border border-gray-200 shadow-sm">
            <CardContent className="p-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Receita do Mês (R$)
                  </label>
                  <input
                    type="number"
                    value={sReceita}
                    onChange={(e) => setSReceita(e.target.value)}
                    placeholder="Ex: 50000"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a47f5]"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    RBT12 — Receita Bruta 12 meses (R$)
                  </label>
                  <input
                    type="number"
                    value={sRbt12}
                    onChange={(e) => setSRbt12(e.target.value)}
                    placeholder="Ex: 600000"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a47f5]"
                  />
                </div>
              </div>
              <div className="mb-5">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Liminares Ativas (Patrimonial)
                </label>
                <div className="flex flex-wrap gap-3">
                  {[
                    { val: 'pis_cofins_zero', label: 'PIS/COFINS = 0' },
                    { val: 'inss_nao_retido', label: 'INSS Não Retido' },
                  ].map((lim) => (
                    <label key={lim.val} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={sLiminares.includes(lim.val)}
                        onChange={() => toggleLiminar(lim.val)}
                        className="w-4 h-4 rounded border-gray-300 accent-[#1a47f5]"
                      />
                      <span className="text-sm text-gray-700">{lim.label}</span>
                    </label>
                  ))}
                </div>
              </div>
              <button
                onClick={handleCalcSimples}
                className="bg-[#111b57] hover:bg-[#1a47f5] text-white font-semibold px-6 py-2.5 rounded-lg text-sm transition-colors"
              >
                Calcular DAS
              </button>

              {sResult && (
                <div className="mt-5 grid grid-cols-1 sm:grid-cols-3 gap-4">
                  {[
                    { label: 'Alíquota Efetiva', value: `${sResult.aliqEfetiva}%`, color: 'text-blue-600', bg: 'bg-blue-50' },
                    { label: 'DAS a Recolher', value: `R$ ${parseFloat(sResult.das).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`, color: 'text-red-600', bg: 'bg-red-50' },
                    { label: 'Economia c/ Liminares', value: `R$ ${parseFloat(sResult.economia).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`, color: 'text-green-600', bg: 'bg-green-50' },
                  ].map((card) => (
                    <div key={card.label} className={cn('rounded-xl p-4', card.bg)}>
                      <p className="text-xs text-gray-500 mb-1">{card.label}</p>
                      <p className={cn('text-xl font-bold', card.color)}>{card.value}</p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Tab: Lucro Real */}
        {calcTab === 'lucro_real' && (
          <Card className="border border-gray-200 shadow-sm">
            <CardContent className="p-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-5">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Receita do Mês (R$)
                  </label>
                  <input
                    type="number"
                    value={lReceita}
                    onChange={(e) => setLReceita(e.target.value)}
                    placeholder="Ex: 80000"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a47f5]"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Receita do Trimestre (R$)
                  </label>
                  <input
                    type="number"
                    value={lTrimestre}
                    onChange={(e) => setLTrimestre(e.target.value)}
                    placeholder="Ex: 240000"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a47f5]"
                  />
                </div>
              </div>
              <button
                onClick={handleCalcLucro}
                className="bg-[#111b57] hover:bg-[#1a47f5] text-white font-semibold px-6 py-2.5 rounded-lg text-sm transition-colors"
              >
                Calcular Impostos
              </button>

              {lResult && (
                <div className="mt-5">
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-3">
                    {[
                      { label: 'IRPJ', value: lResult.irpj },
                      { label: 'IRPJ Adicional', value: lResult.irpjAdicional },
                      { label: 'CSLL', value: lResult.csll },
                      { label: 'PIS', value: lResult.pis },
                      { label: 'COFINS', value: lResult.cofins },
                      { label: 'ISS (5%)', value: lResult.iss },
                    ].map((item) => (
                      <div key={item.label} className="bg-gray-50 rounded-lg p-3">
                        <p className="text-xs text-gray-500">{item.label}</p>
                        <p className="font-semibold text-gray-800 text-sm">{fmt(item.value)}</p>
                      </div>
                    ))}
                  </div>
                  <div className="bg-red-50 rounded-xl p-4 flex justify-between items-center">
                    <div>
                      <p className="text-sm text-gray-500">Total de Impostos</p>
                      <p className="font-data text-2xl font-semibold tabular-nums text-red-600">{fmt(lResult.total)}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-gray-500">Carga Tributária</p>
                      <p className="font-data text-2xl font-semibold tabular-nums text-red-700">{lResult.pct}%</p>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Tab: Comparativo */}
        {calcTab === 'comparativo' && (
          <Card className="border border-gray-200 shadow-sm">
            <CardContent className="p-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-5">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Receita Anual (R$)
                  </label>
                  <input
                    type="number"
                    value={cReceita}
                    onChange={(e) => setCReceita(e.target.value)}
                    placeholder="Ex: 960000"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a47f5]"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    RBT12 para Simples (R$)
                  </label>
                  <input
                    type="number"
                    value={cRbt12}
                    onChange={(e) => setCRbt12(e.target.value)}
                    placeholder="Ex: 960000"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a47f5]"
                  />
                </div>
              </div>
              <button
                onClick={handleCalcComparativo}
                className="bg-[#111b57] hover:bg-[#1a47f5] text-white font-semibold px-6 py-2.5 rounded-lg text-sm transition-colors"
              >
                Comparar Regimes
              </button>

              {cResult && (
                <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {[
                    {
                      label: 'Simples Nacional',
                      das: fmt(parseFloat(cResult.simples.das)),
                      pct: `${cResult.simples.aliqEfetiva}%`,
                      color: 'border-green-300 bg-green-50',
                      badge: 'Recomendado',
                      badgeColor: 'bg-green-100 text-green-700',
                    },
                    {
                      label: 'Lucro Real',
                      das: fmt(cResult.lucro.total),
                      pct: `${cResult.lucro.pct}%`,
                      color: 'border-red-200 bg-red-50',
                      badge: 'Atual',
                      badgeColor: 'bg-red-100 text-red-700',
                    },
                  ].map((regime) => (
                    <div key={regime.label} className={cn('rounded-xl p-5 border-2', regime.color)}>
                      <div className="flex justify-between items-center mb-3">
                        <p className="font-bold text-gray-800">{regime.label}</p>
                        <span className={cn('text-xs font-semibold px-2 py-0.5 rounded-full', regime.badgeColor)}>
                          {regime.badge}
                        </span>
                      </div>
                      <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{regime.das}</p>
                      <p className="text-sm text-gray-500 mt-1">Carga: {regime.pct}</p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* Sugerir Empresa */}
      <div>
        <h2 className="text-xl font-bold text-[#111b57] flex items-center gap-2 mb-5">
          <Lightbulb className="h-6 w-6 text-[#f97707]" />
          Sugerir Empresa para Faturar
        </h2>
        <Card className="border border-gray-200 shadow-sm">
          <CardContent className="p-6">
            <div className="flex flex-col sm:flex-row gap-3 mb-4">
              <select
                value={tipoServico}
                onChange={(e) => setTipoServico(e.target.value)}
                className="flex-1 border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a47f5] bg-white"
              >
                <option value="">Selecione o tipo de serviço...</option>
                <option value="vigilancia">Vigilância</option>
                <option value="portaria">Portaria Presencial</option>
                <option value="portaria_remota">Portaria Remota</option>
                <option value="cftv">CFTV</option>
                <option value="alarmes">Alarmes</option>
                <option value="monitoramento">Monitoramento</option>
                <option value="limpeza">Limpeza e Conservação</option>
                <option value="jardinagem">Jardinagem</option>
              </select>
              <button
                onClick={handleSugestao}
                disabled={!tipoServico}
                className="bg-[#f97707] hover:bg-orange-600 disabled:opacity-50 text-white font-semibold px-6 py-2.5 rounded-lg text-sm transition-colors"
              >
                Sugerir Empresa
              </button>
            </div>

            {sugestao && (
              <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 flex gap-3">
                <CheckCircle className="h-5 w-5 text-blue-600 mt-0.5 shrink-0" />
                <div>
                  <p className="font-bold text-blue-800">{sugestao.empresa}</p>
                  <p className="text-sm text-blue-600 mt-0.5">{sugestao.motivo}</p>
                </div>
              </div>
            )}

            <div className="mt-4 bg-yellow-50 border border-yellow-200 rounded-xl p-4 flex gap-3">
              <AlertCircle className="h-5 w-5 text-yellow-600 mt-0.5 shrink-0" />
              <p className="text-sm text-yellow-700">
                A sugestão é baseada nas regras tributárias e atividades de cada empresa.
                Consulte seu contador para confirmação antes de emitir notas.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
