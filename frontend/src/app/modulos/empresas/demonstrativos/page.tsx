'use client';

import { useState } from 'react';
import { msgFromDetail } from '@/lib/string';
import {
  BarChart2,
  BookOpen,
  TrendingUp,
  Layers,
  Download,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Building2,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';

// ─── Formatters ───────────────────────────────────────────────────────────────
const fmt = (v: number | null | undefined) => {
  if (v == null) return 'R$ 0';
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
};
const fmtPct = (v: number | null | undefined) => `${(v ?? 0).toFixed(2)}%`;

// ─── Tab Component ────────────────────────────────────────────────────────────
function Tab({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'px-4 py-2.5 text-sm font-semibold rounded-t-lg border-b-2 transition-colors whitespace-nowrap',
        active
          ? 'border-blue-600 text-blue-700 bg-white'
          : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
      )}
    >
      {children}
    </button>
  );
}

// ─── Result Row ───────────────────────────────────────────────────────────────
function ResultRow({ label, value, bold, negative, indent }: {
  label: string; value?: number | string; bold?: boolean; negative?: boolean; indent?: boolean;
}) {
  const isNum = typeof value === 'number';
  return (
    <div className={cn('flex justify-between py-2 border-b border-gray-100', bold && 'font-semibold bg-gray-50 px-2 rounded')}>
      <span className={cn('text-sm text-gray-600', indent && 'pl-4', bold && 'text-gray-800')}>{label}</span>
      <span className={cn(
        'text-sm font-medium',
        bold ? 'text-gray-900' : '',
        negative && isNum && (value as number) < 0 ? 'text-red-600' : '',
      )}>
        {isNum ? fmt(value as number) : (value ?? '—')}
      </span>
    </div>
  );
}

// ─── Badge ────────────────────────────────────────────────────────────────────
function Badge({ label }: { label: string }) {
  const color =
    label === 'EXCELENTE' ? 'bg-green-100 text-green-700' :
    label === 'BOM' ? 'bg-blue-100 text-blue-700' :
    label === 'REGULAR' ? 'bg-yellow-100 text-yellow-700' :
    label === 'CRÍTICO' ? 'bg-orange-100 text-orange-700' :
    label === 'PREJUÍZO' ? 'bg-red-100 text-red-700' :
    'bg-gray-100 text-gray-700';
  return (
    <span className={cn('inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold', color)}>
      {label}
    </span>
  );
}

// ─── DRE Tab ─────────────────────────────────────────────────────────────────
function DRETab() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [form, setForm] = useState({
    empresa_slug: 'conecta_eletronica',
    periodo: '2026-03',
    regime: 'lucro_real',
    receita_bruta: '350000',
    deducoes: '31500',
    folha: '200000',
    encargos: '60000',
    aluguel: '5000',
    admin: '15000',
    despesas_financeiras: '2000',
  });

  const handleSubmit = async () => {
    setLoading(true);
    try {
      const dados = {
        receita_bruta: Number(form.receita_bruta),
        deducoes: Number(form.deducoes),
        custos: {
          folha_pagamento: Number(form.folha),
          encargos_sociais: Number(form.encargos),
        },
        despesas: {
          aluguel: Number(form.aluguel),
          administrativo: Number(form.admin),
        },
        outros: {
          receitas_financeiras: 0,
          despesas_financeiras: Number(form.despesas_financeiras),
        },
      };
      const res = await api.post('/api/v1/empresas/demonstrativos/dre', {
        empresa_slug: form.empresa_slug,
        periodo: form.periodo,
        dados,
        regime: form.regime,
      });
      setResult(res.data);
    } catch (e: any) {
      setResult({ sucesso: false, erro: msgFromDetail(e?.response?.data?.detail) || String(e) });
    } finally {
      setLoading(false);
    }
  };

  const dre = result?.dre;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Formulário */}
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-gray-700">Parâmetros</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500">Empresa</label>
              <select
                value={form.empresa_slug}
                onChange={e => setForm(f => ({ ...f, empresa_slug: e.target.value }))}
                className="w-full mt-1 rounded-lg border border-gray-200 px-3 py-2 text-sm"
              >
                <option value="conecta_eletronica">Conecta Eletrônica</option>
                <option value="conecta_patrimonial">Conecta Patrimonial</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500">Período (YYYY-MM)</label>
              <input
                type="month"
                value={form.periodo}
                onChange={e => setForm(f => ({ ...f, periodo: e.target.value }))}
                className="w-full mt-1 rounded-lg border border-gray-200 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500">Regime</label>
              <select
                value={form.regime}
                onChange={e => setForm(f => ({ ...f, regime: e.target.value }))}
                className="w-full mt-1 rounded-lg border border-gray-200 px-3 py-2 text-sm"
              >
                <option value="lucro_real">Lucro Real</option>
                <option value="simples_nacional">Simples Nacional</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500">Receita Bruta (R$)</label>
              <input
                type="number"
                value={form.receita_bruta}
                onChange={e => setForm(f => ({ ...f, receita_bruta: e.target.value }))}
                className="w-full mt-1 rounded-lg border border-gray-200 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500">Deduções ISS/PIS/COFINS (R$)</label>
              <input
                type="number"
                value={form.deducoes}
                onChange={e => setForm(f => ({ ...f, deducoes: e.target.value }))}
                className="w-full mt-1 rounded-lg border border-gray-200 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500">Folha de Pagamento (R$)</label>
              <input
                type="number"
                value={form.folha}
                onChange={e => setForm(f => ({ ...f, folha: e.target.value }))}
                className="w-full mt-1 rounded-lg border border-gray-200 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500">Encargos Sociais (R$)</label>
              <input
                type="number"
                value={form.encargos}
                onChange={e => setForm(f => ({ ...f, encargos: e.target.value }))}
                className="w-full mt-1 rounded-lg border border-gray-200 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500">Despesas Admin (R$)</label>
              <input
                type="number"
                value={form.admin}
                onChange={e => setForm(f => ({ ...f, admin: e.target.value }))}
                className="w-full mt-1 rounded-lg border border-gray-200 px-3 py-2 text-sm"
              />
            </div>
          </div>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="flex items-center gap-2 px-5 py-2.5 bg-[#111b57] hover:bg-[#1a47f5] text-white text-sm rounded-lg transition-colors"
          >
            <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
            Gerar DRE
          </button>
        </div>

        {/* Resultado */}
        {result && (
          <div>
            {!result.sucesso ? (
              <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">{result.erro}</div>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-gray-700">DRE — {result.periodo}</h3>
                  <Badge label={result.indicadores?.classificacao ?? ''} />
                </div>
                <ResultRow label="Receita Bruta" value={dre?.receita_bruta} />
                <ResultRow label="(-) Deduções" value={-dre?.deducoes} indent negative />
                <ResultRow label="Receita Líquida" value={dre?.receita_liquida} bold />
                <ResultRow label="(-) Custos Totais" value={-dre?.total_custos} indent negative />
                <ResultRow label="Lucro Bruto" value={dre?.lucro_bruto} bold />
                <ResultRow label={`Margem Bruta`} value={fmtPct(dre?.margem_bruta_pct)} />
                <ResultRow label="(-) Despesas Operacionais" value={-dre?.total_despesas} indent negative />
                <ResultRow label="EBIT (LAJIR)" value={dre?.ebit_lajir} bold />
                <ResultRow label="Resultado Financeiro" value={dre?.resultado_financeiro} indent />
                <ResultRow label="LAIR" value={dre?.lair} bold />
                <ResultRow label="(-) Impostos s/ Lucro" value={-dre?.impostos_sobre_lucro} indent negative />
                <ResultRow label="Lucro Líquido" value={dre?.lucro_liquido} bold />
                <ResultRow label="Margem Líquida" value={fmtPct(dre?.margem_liquida_pct)} bold />
                {(result.indicadores?.ponto_equilibrio ?? 0) > 0 && (
                  <ResultRow label="Ponto de Equilíbrio" value={result.indicadores.ponto_equilibrio} />
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Balanço Tab ──────────────────────────────────────────────────────────────
function BalancoTab() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [form, setForm] = useState({
    empresa_slug: 'conecta_eletronica',
    data_base: '2026-03-31',
    caixa: '50000',
    clientes: '120000',
    imobilizado: '80000',
    fornecedores: '30000',
    obrigacoes_trab: '45000',
    obrigacoes_trib: '20000',
    capital: '155000',
  });

  const handleSubmit = async () => {
    setLoading(true);
    try {
      const dados = {
        ativo_circulante: {
          caixa_bancos: Number(form.caixa),
          clientes_receber: Number(form.clientes),
        },
        ativo_nao_circulante: {
          imobilizado: Number(form.imobilizado),
        },
        passivo_circulante: {
          fornecedores: Number(form.fornecedores),
          obrigacoes_trabalhistas: Number(form.obrigacoes_trab),
          obrigacoes_tributarias: Number(form.obrigacoes_trib),
        },
        passivo_nao_circulante: {},
        patrimonio_liquido: {
          capital_social: Number(form.capital),
        },
      };
      const res = await api.post('/api/v1/empresas/demonstrativos/balanco', {
        empresa_slug: form.empresa_slug,
        data_base: form.data_base,
        dados,
      });
      setResult(res.data);
    } catch (e: any) {
      setResult({ sucesso: false, erro: msgFromDetail(e?.response?.data?.detail) || String(e) });
    } finally {
      setLoading(false);
    }
  };

  const bal = result?.balanco;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-gray-700">Parâmetros</h3>
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: 'Empresa', key: 'empresa_slug', type: 'select' },
              { label: 'Data Base', key: 'data_base', type: 'date' },
              { label: 'Caixa e Bancos (R$)', key: 'caixa', type: 'number' },
              { label: 'Clientes a Receber (R$)', key: 'clientes', type: 'number' },
              { label: 'Imobilizado (R$)', key: 'imobilizado', type: 'number' },
              { label: 'Fornecedores (R$)', key: 'fornecedores', type: 'number' },
              { label: 'Obrig. Trabalhistas (R$)', key: 'obrigacoes_trab', type: 'number' },
              { label: 'Obrig. Tributárias (R$)', key: 'obrigacoes_trib', type: 'number' },
              { label: 'Capital Social (R$)', key: 'capital', type: 'number' },
            ].map(field => (
              <div key={field.key}>
                <label className="text-xs text-gray-500">{field.label}</label>
                {field.type === 'select' ? (
                  <select
                    value={(form as any)[field.key]}
                    onChange={e => setForm(f => ({ ...f, [field.key]: e.target.value }))}
                    className="w-full mt-1 rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  >
                    <option value="conecta_eletronica">Conecta Eletrônica</option>
                    <option value="conecta_patrimonial">Conecta Patrimonial</option>
                  </select>
                ) : (
                  <input
                    type={field.type}
                    value={(form as any)[field.key]}
                    onChange={e => setForm(f => ({ ...f, [field.key]: e.target.value }))}
                    className="w-full mt-1 rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                )}
              </div>
            ))}
          </div>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="flex items-center gap-2 px-5 py-2.5 bg-[#111b57] hover:bg-[#1a47f5] text-white text-sm rounded-lg transition-colors"
          >
            <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
            Gerar Balanço
          </button>
        </div>

        {result && (
          <div>
            {!result.sucesso ? (
              <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">{result.erro}</div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center gap-2 mb-2">
                  <h3 className="text-sm font-semibold text-gray-700">Balanço Patrimonial — {result.data_base}</h3>
                  {result.balanceado
                    ? <span className="text-xs text-green-700 bg-green-50 border border-green-200 px-2 py-0.5 rounded-full">Balanceado</span>
                    : <span className="text-xs text-red-700 bg-red-50 border border-red-200 px-2 py-0.5 rounded-full">Desbalanceado</span>}
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs font-semibold text-blue-700 mb-1">ATIVO</p>
                    <ResultRow label="Circulante" value={bal?.ativo?.total_circulante} />
                    <ResultRow label="Não Circulante" value={bal?.ativo?.total_nao_circulante} />
                    <ResultRow label="Total Ativo" value={bal?.ativo?.total_ativo} bold />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-orange-700 mb-1">PASSIVO</p>
                    <ResultRow label="Circulante" value={bal?.passivo?.total_circulante} />
                    <ResultRow label="Não Circulante" value={bal?.passivo?.total_nao_circulante} />
                    <ResultRow label="Patrimônio Líquido" value={bal?.passivo?.total_pl} />
                    <ResultRow label="Total Passivo" value={bal?.passivo?.total_passivo} bold />
                  </div>
                </div>
                <div className="mt-3 p-3 bg-gray-50 rounded-lg">
                  <p className="text-xs font-semibold text-gray-600 mb-2">Indicadores</p>
                  <ResultRow label="Liquidez Corrente" value={`${result.indicadores?.liquidez_corrente?.toFixed(2)}x`} />
                  <ResultRow label="Endividamento" value={fmtPct(result.indicadores?.endividamento_pct)} />
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── DFC Tab ──────────────────────────────────────────────────────────────────
function DFCTab() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [form, setForm] = useState({
    empresa_slug: 'conecta_eletronica',
    periodo: '2026-03',
    lucro_liquido: '35000',
    depreciacao: '3000',
    variacao_contas_receber: '10000',
    variacao_fornecedores: '5000',
    saldo_inicial: '80000',
  });

  const handleSubmit = async () => {
    setLoading(true);
    try {
      const res = await api.post('/api/v1/empresas/demonstrativos/dfc', {
        empresa_slug: form.empresa_slug,
        periodo: form.periodo,
        dados: {
          lucro_liquido: Number(form.lucro_liquido),
          depreciacao: Number(form.depreciacao),
          amortizacao: 0,
          variacao_contas_receber: Number(form.variacao_contas_receber),
          variacao_fornecedores: Number(form.variacao_fornecedores),
          variacao_obrigacoes_trabalhistas: 2000,
          variacao_impostos: 1500,
          aquisicao_imobilizado: 0,
          emprestimos_obtidos: 0,
          amortizacao_emprestimos: 0,
          distribuicao_lucros: 0,
          saldo_caixa_inicial: Number(form.saldo_inicial),
        },
      });
      setResult(res.data);
    } catch (e: any) {
      setResult({ sucesso: false, erro: msgFromDetail(e?.response?.data?.detail) || String(e) });
    } finally {
      setLoading(false);
    }
  };

  const dfc = result?.dfc;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-gray-700">Parâmetros (Método Indireto)</h3>
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: 'Empresa', key: 'empresa_slug', type: 'select' },
              { label: 'Período', key: 'periodo', type: 'month' },
              { label: 'Lucro Líquido (R$)', key: 'lucro_liquido', type: 'number' },
              { label: 'Depreciação (R$)', key: 'depreciacao', type: 'number' },
              { label: 'Variação Clientes (R$)', key: 'variacao_contas_receber', type: 'number' },
              { label: 'Variação Fornecedores (R$)', key: 'variacao_fornecedores', type: 'number' },
              { label: 'Saldo Inicial Caixa (R$)', key: 'saldo_inicial', type: 'number' },
            ].map(field => (
              <div key={field.key}>
                <label className="text-xs text-gray-500">{field.label}</label>
                {field.type === 'select' ? (
                  <select
                    value={(form as any)[field.key]}
                    onChange={e => setForm(f => ({ ...f, [field.key]: e.target.value }))}
                    className="w-full mt-1 rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  >
                    <option value="conecta_eletronica">Conecta Eletrônica</option>
                    <option value="conecta_patrimonial">Conecta Patrimonial</option>
                  </select>
                ) : (
                  <input
                    type={field.type}
                    value={(form as any)[field.key]}
                    onChange={e => setForm(f => ({ ...f, [field.key]: e.target.value }))}
                    className="w-full mt-1 rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                )}
              </div>
            ))}
          </div>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="flex items-center gap-2 px-5 py-2.5 bg-[#111b57] hover:bg-[#1a47f5] text-white text-sm rounded-lg transition-colors"
          >
            <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
            Gerar DFC
          </button>
        </div>

        {result && (
          <div>
            {!result.sucesso ? (
              <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">{result.erro}</div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center gap-2 mb-2">
                  <h3 className="text-sm font-semibold text-gray-700">DFC — {result.periodo}</h3>
                  <span className={cn(
                    'text-xs font-semibold px-2 py-0.5 rounded-full',
                    result.saude_caixa === 'POSITIVO' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                  )}>
                    {result.saude_caixa}
                  </span>
                </div>
                <div className="space-y-1">
                  <p className="text-xs font-semibold text-gray-500 mt-2">Atividades Operacionais</p>
                  <ResultRow label="Lucro Líquido" value={dfc?.atividades_operacionais?.lucro_liquido} indent />
                  <ResultRow label="Depreciação/Amortização" value={dfc?.atividades_operacionais?.ajustes?.depreciacao_amortizacao} indent />
                  <ResultRow label="Total Operacional" value={dfc?.atividades_operacionais?.total} bold />
                  <p className="text-xs font-semibold text-gray-500 mt-2">Atividades de Investimento</p>
                  <ResultRow label="Total Investimento" value={dfc?.atividades_investimento?.total} bold />
                  <p className="text-xs font-semibold text-gray-500 mt-2">Atividades de Financiamento</p>
                  <ResultRow label="Total Financiamento" value={dfc?.atividades_financiamento?.total} bold />
                  <div className="border-t border-gray-200 pt-2 mt-2">
                    <ResultRow label="Variação de Caixa" value={dfc?.variacao_caixa} bold />
                    <ResultRow label="Saldo Inicial" value={dfc?.saldo_inicial} />
                    <ResultRow label="Saldo Final" value={dfc?.saldo_final} bold />
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Consolidado Tab ──────────────────────────────────────────────────────────
function ConsolidadoTab() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [periodo, setPeriodo] = useState('2026-03');

  const handleSubmit = async () => {
    setLoading(true);
    try {
      const res = await api.post('/api/v1/empresas/demonstrativos/consolidado-grupo', {
        periodo,
        empresas: [
          {
            empresa: 'Conecta Eletrônica',
            receita_bruta: 200000,
            total_custos: 130000,
            total_despesas: 20000,
            impostos: 25000,
            lucro_liquido: 25000,
          },
          {
            empresa: 'Conecta Patrimonial',
            receita_bruta: 150000,
            total_custos: 110000,
            total_despesas: 15000,
            impostos: 8000,
            lucro_liquido: 17000,
          },
        ],
      });
      setResult(res.data);
    } catch (e: any) {
      setResult({ sucesso: false, erro: msgFromDetail(e?.response?.data?.detail) || String(e) });
    } finally {
      setLoading(false);
    }
  };

  const cons = result?.consolidado;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <div>
          <label className="text-xs text-gray-500">Período</label>
          <input
            type="month"
            value={periodo}
            onChange={e => setPeriodo(e.target.value)}
            className="ml-2 rounded-lg border border-gray-200 px-3 py-2 text-sm"
          />
        </div>
        <button
          onClick={handleSubmit}
          disabled={loading}
          className="flex items-center gap-2 px-5 py-2.5 bg-[#111b57] hover:bg-[#1a47f5] text-white text-sm rounded-lg transition-colors"
        >
          <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
          Consolidar Grupo
        </button>
      </div>

      {result && (
        !result.sucesso ? (
          <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">{result.erro}</div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              {[
                { label: 'Receita Total', value: cons?.receita_total, color: 'text-blue-700' },
                { label: 'Custos + Despesas', value: cons?.custos_total + cons?.despesas_total, color: 'text-red-600' },
                { label: 'Impostos Totais', value: cons?.impostos_total, color: 'text-orange-600' },
                { label: 'Lucro Líquido', value: cons?.lucro_liquido_total, color: 'text-green-700' },
                { label: 'Margem do Grupo', value: fmtPct(cons?.margem_liquida_grupo_pct), color: 'text-purple-700' },
                { label: 'Maior Contribuidor', value: result.maior_contribuidor, color: 'text-gray-800' },
              ].map((item, i) => (
                <div key={i} className="p-4 bg-gray-50 rounded-xl border border-gray-100">
                  <p className="text-xs text-gray-500 mb-1">{item.label}</p>
                  <p className={cn('text-lg font-bold', item.color)}>
                    {typeof item.value === 'number' ? fmt(item.value) : item.value}
                  </p>
                </div>
              ))}
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-2">Por Empresa</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-2 text-gray-500 font-medium">Empresa</th>
                      <th className="text-right py-2 text-gray-500 font-medium">Receita</th>
                      <th className="text-right py-2 text-gray-500 font-medium">Impostos</th>
                      <th className="text-right py-2 text-gray-500 font-medium">Lucro Líquido</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(result.por_empresa ?? []).map((e: any, i: number) => (
                      <tr key={i} className="border-b border-gray-100">
                        <td className="py-2 font-medium text-gray-800">{e.empresa}</td>
                        <td className="py-2 text-right text-gray-700">{fmt(e.receita_bruta)}</td>
                        <td className="py-2 text-right text-red-600">{fmt(e.impostos)}</td>
                        <td className="py-2 text-right text-green-700 font-semibold">{fmt(e.lucro_liquido)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )
      )}
    </div>
  );
}

// ─── Exportar Domínio TOTVS Tab ────────────────────────────────────────────────
function ExportarDominioTab() {
  const [loading, setLoading] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, any>>({});
  const [empresaSlug, setEmpresaSlug] = useState('conecta_eletronica');
  const [periodo, setPeriodo] = useState('2026-03');

  const exportarPlanoContas = async () => {
    setLoading('plano');
    try {
      const res = await api.get(`/api/v1/empresas/dominio/plano-contas/${empresaSlug}`);
      setResults(r => ({ ...r, plano: res.data }));
    } catch (e: any) {
      setResults(r => ({ ...r, plano: { sucesso: false, erro: String(e) } }));
    } finally {
      setLoading(null);
    }
  };

  const exportarLancamentos = async () => {
    setLoading('lancamentos');
    try {
      const res = await api.post('/api/v1/empresas/dominio/lancamentos', {
        empresa_slug: empresaSlug,
        periodo,
        lancamentos: [
          {
            data: '01/03/2026',
            historico: 'Receita de Serviços — março',
            conta_debito: '1.1.2.01',
            conta_credito: '3.1.1.03',
            valor: 200000,
            tipo: 'D',
          },
        ],
      });
      setResults(r => ({ ...r, lancamentos: res.data }));
    } catch (e: any) {
      setResults(r => ({ ...r, lancamentos: { sucesso: false, erro: String(e) } }));
    } finally {
      setLoading(null);
    }
  };

  const exportarNfse = async () => {
    setLoading('nfse');
    try {
      const res = await api.post('/api/v1/empresas/dominio/nfse', {
        empresa_slug: empresaSlug,
        periodo,
        notas: [
          {
            numero: 'NF-001',
            tomador: 'Cliente Exemplo Ltda',
            tipo_servico: 'eletronica',
            valor_servico: 50000,
            iss: 2500,
            pis: 825,
            cofins: 3800,
            data_emissao: '05/03/2026',
          },
        ],
      });
      setResults(r => ({ ...r, nfse: res.data }));
    } catch (e: any) {
      setResults(r => ({ ...r, nfse: { sucesso: false, erro: String(e) } }));
    } finally {
      setLoading(null);
    }
  };

  const downloadTxt = (conteudo: string, nomeArquivo: string) => {
    const blob = new Blob([conteudo], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = nomeArquivo;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      {/* Controles */}
      <div className="flex flex-wrap items-center gap-4 p-4 bg-gray-50 rounded-xl border border-gray-200">
        <div>
          <label className="text-xs text-gray-500 block mb-1">Empresa</label>
          <select
            value={empresaSlug}
            onChange={e => setEmpresaSlug(e.target.value)}
            className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
          >
            <option value="conecta_eletronica">Conecta Eletrônica</option>
            <option value="conecta_patrimonial">Conecta Patrimonial</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Período</label>
          <input
            type="month"
            value={periodo}
            onChange={e => setPeriodo(e.target.value)}
            className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
          />
        </div>
      </div>

      {/* Cards de exportação */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Plano de Contas */}
        <div className="border border-gray-200 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-3">
            <BookOpen className="w-5 h-5 text-blue-600" />
            <h3 className="font-semibold text-gray-800">Plano de Contas</h3>
          </div>
          <p className="text-xs text-gray-500 mb-4">Exporta o plano de contas padronizado para segurança patrimonial no formato Domínio TOTVS V12.</p>
          <button
            onClick={exportarPlanoContas}
            disabled={loading === 'plano'}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg transition-colors"
          >
            <RefreshCw className={cn('w-4 h-4', loading === 'plano' && 'animate-spin')} />
            Gerar
          </button>
          {results.plano && (
            <div className="mt-3">
              {results.plano.sucesso ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-1 text-xs text-green-700">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    {results.plano.total_contas} contas geradas
                  </div>
                  <button
                    onClick={() => downloadTxt(results.plano.conteudo, results.plano.nome_arquivo)}
                    className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800"
                  >
                    <Download className="w-3.5 h-3.5" />
                    {results.plano.nome_arquivo}
                  </button>
                </div>
              ) : (
                <p className="text-xs text-red-600">{results.plano.erro}</p>
              )}
            </div>
          )}
        </div>

        {/* Lançamentos */}
        <div className="border border-gray-200 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-3">
            <FileText className="w-5 h-5 text-purple-600" />
            <h3 className="font-semibold text-gray-800">Lançamentos Contábeis</h3>
          </div>
          <p className="text-xs text-gray-500 mb-4">Exporta os lançamentos contábeis do período no layout TXT padrão Domínio TOTVS.</p>
          <button
            onClick={exportarLancamentos}
            disabled={loading === 'lancamentos'}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white text-sm rounded-lg transition-colors"
          >
            <RefreshCw className={cn('w-4 h-4', loading === 'lancamentos' && 'animate-spin')} />
            Gerar Exemplo
          </button>
          {results.lancamentos && (
            <div className="mt-3">
              {results.lancamentos.sucesso ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-1 text-xs text-green-700">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    {results.lancamentos.total_lancamentos} lançamentos
                    {results.lancamentos.balanceado && ' • Balanceado'}
                  </div>
                  <button
                    onClick={() => downloadTxt(results.lancamentos.conteudo, results.lancamentos.nome_arquivo)}
                    className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800"
                  >
                    <Download className="w-3.5 h-3.5" />
                    {results.lancamentos.nome_arquivo}
                  </button>
                </div>
              ) : (
                <p className="text-xs text-red-600">{results.lancamentos.erro}</p>
              )}
            </div>
          )}
        </div>

        {/* NFS-e */}
        <div className="border border-gray-200 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-3">
            <Building2 className="w-5 h-5 text-orange-600" />
            <h3 className="font-semibold text-gray-800">NFS-e para Domínio</h3>
          </div>
          <p className="text-xs text-gray-500 mb-4">Converte as NFS-e emitidas em lançamentos contábeis automáticos para importar no TOTVS.</p>
          <button
            onClick={exportarNfse}
            disabled={loading === 'nfse'}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white text-sm rounded-lg transition-colors"
          >
            <RefreshCw className={cn('w-4 h-4', loading === 'nfse' && 'animate-spin')} />
            Gerar Exemplo
          </button>
          {results.nfse && (
            <div className="mt-3">
              {results.nfse.sucesso ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-1 text-xs text-green-700">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    {results.nfse.total_lancamentos} lançamentos gerados
                  </div>
                  <button
                    onClick={() => downloadTxt(results.nfse.conteudo, results.nfse.nome_arquivo)}
                    className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800"
                  >
                    <Download className="w-3.5 h-3.5" />
                    {results.nfse.nome_arquivo}
                  </button>
                </div>
              ) : (
                <p className="text-xs text-red-600">{results.nfse.erro}</p>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="flex items-start gap-3 p-4 bg-yellow-50 border border-yellow-200 rounded-xl">
        <AlertTriangle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
        <p className="text-sm text-yellow-800">
          Os arquivos gerados seguem o layout <strong>Domínio TOTVS V12</strong>. Envie ao contador (Domínio Sistemas) para importação no sistema. Formato: pipe-delimitado (|), encoding UTF-8, CRLF.
        </p>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
type TabId = 'dre' | 'balanco' | 'dfc' | 'consolidado' | 'dominio';

const TABS: { id: TabId; label: string; icon: React.ElementType }[] = [
  { id: 'dre', label: 'DRE', icon: BarChart2 },
  { id: 'balanco', label: 'Balanço', icon: Layers },
  { id: 'dfc', label: 'DFC', icon: TrendingUp },
  { id: 'consolidado', label: 'Consolidado Grupo', icon: Building2 },
  { id: 'dominio', label: 'Exportar Domínio TOTVS', icon: Download },
];

export default function DemonstrativosPage() {
  const [activeTab, setActiveTab] = useState<TabId>('dre');

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-gradient-to-br from-[#111b57] to-[#1a47f5] px-6 py-8">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-white/10 rounded-xl">
              <BarChart2 className="w-7 h-7 text-white" />
            </div>
            <div>
              <h1 className="font-display text-2xl font-bold text-white">Demonstrativos Financeiros</h1>
              <p className="text-blue-200 text-sm mt-0.5">DRE · Balanço · DFC · Consolidado · Exportação Domínio TOTVS</p>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6">
        <Card className="shadow-sm">
          <div className="border-b border-gray-200 px-4 flex gap-1 overflow-x-auto" data-testid="tabs-demonstrativos">
            {TABS.map(tab => (
              <Tab key={tab.id} active={activeTab === tab.id} onClick={() => setActiveTab(tab.id)}>
                {tab.label}
              </Tab>
            ))}
          </div>
          <CardContent className="p-6">
            {activeTab === 'dre' && <DRETab />}
            {activeTab === 'balanco' && <BalancoTab />}
            {activeTab === 'dfc' && <DFCTab />}
            {activeTab === 'consolidado' && <ConsolidadoTab />}
            {activeTab === 'dominio' && <ExportarDominioTab />}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
