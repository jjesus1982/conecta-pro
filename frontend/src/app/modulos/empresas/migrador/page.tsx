'use client';

import { useState } from 'react';
import { msgFromDetail } from '@/lib/string';
import {
  ArrowRightLeft,
  ArrowLeft,
  Building2,
  TrendingUp,
  AlertCircle,
  CheckCircle2,
  FileText,
  Zap,
  Info,
  ChevronDown,
  ChevronUp,
  Loader2,
  Package,
} from 'lucide-react';
import Link from 'next/link';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://erp.conectamais.pro';

function getToken(): string {
  if (typeof window === 'undefined') return '';
  return localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
}

async function apiPost(path: string, body: object) {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erro desconhecido' }));
    throw new Error(msgFromDetail(err.detail) || `HTTP ${res.status}`);
  }
  return res.json();
}

const TIPOS_SERVICO = [
  { value: 'vigilancia', label: 'Vigilância Patrimonial', grupo: 'Humanizados → Patrimonial' },
  { value: 'portaria_presencial', label: 'Portaria Presencial', grupo: 'Humanizados → Patrimonial' },
  { value: 'portaria_24h', label: 'Portaria 24h', grupo: 'Humanizados → Patrimonial' },
  { value: 'portaria_12x36', label: 'Portaria 12x36', grupo: 'Humanizados → Patrimonial' },
  { value: 'limpeza', label: 'Limpeza e Conservação', grupo: 'Humanizados → Patrimonial' },
  { value: 'jardinagem', label: 'Jardinagem', grupo: 'Humanizados → Patrimonial' },
  { value: 'facilities', label: 'Facilities', grupo: 'Humanizados → Patrimonial' },
  { value: 'recepcao', label: 'Recepção', grupo: 'Humanizados → Patrimonial' },
  { value: 'zeladoria', label: 'Zeladoria', grupo: 'Humanizados → Patrimonial' },
  { value: 'portaria_remota', label: 'Portaria Remota', grupo: 'Eletrônicos → Eletrônica' },
  { value: 'monitoramento', label: 'Monitoramento 24h', grupo: 'Eletrônicos → Eletrônica' },
  { value: 'cftv', label: 'CFTV', grupo: 'Eletrônicos → Eletrônica' },
  { value: 'alarmes', label: 'Alarmes', grupo: 'Eletrônicos → Eletrônica' },
  { value: 'controle_acesso', label: 'Controle de Acesso', grupo: 'Eletrônicos → Eletrônica' },
  { value: 'automacao', label: 'Automação', grupo: 'Eletrônicos → Eletrônica' },
  { value: 'seguranca_eletronica', label: 'Segurança Eletrônica', grupo: 'Eletrônicos → Eletrônica' },
];

function fmt(v: number) {
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function EmpresaBadge({ slug }: { slug: string }) {
  const isPatrimonial = slug === 'conecta_patrimonial';
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${
        isPatrimonial
          ? 'bg-green-100 text-green-700'
          : 'bg-blue-100 text-blue-700'
      }`}
    >
      <Building2 className="w-3 h-3" />
      {isPatrimonial ? 'Patrimonial' : 'Eletrônica'}
    </span>
  );
}

// ─── Seção 1: Análise Individual ─────────────────────────────────────────────

function SecaoAnaliseIndividual() {
  const [form, setForm] = useState({
    contrato_id: 1,
    tipo_servico: 'vigilancia',
    empresa_atual_slug: 'conecta_eletronica',
    receita_bruta_mes: 50000,
    custo_direto_mes: 30000,
    rbt12_destino: 600000,
    pis_cofins: false,
    inss: false,
  });
  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<any>(null);
  const [simulacao, setSimulacao] = useState<any>(null);
  const [simLoading, setSimLoading] = useState(false);
  const [aditivo, setAditivo] = useState<string | null>(null);
  const [aditivoLoading, setAditivoLoading] = useState(false);
  const [showSimulacao, setShowSimulacao] = useState(false);
  const [erro, setErro] = useState('');

  const liminares = [
    ...(form.pis_cofins ? ['pis_cofins_zero'] : []),
    ...(form.inss ? ['inss_nao_retido'] : []),
  ];

  async function handleAnalisar() {
    setLoading(true);
    setErro('');
    setResultado(null);
    setSimulacao(null);
    setAditivo(null);
    try {
      const r = await apiPost('/api/v1/empresas/migrador/analisar', {
        contrato_id: form.contrato_id,
        tipo_servico: form.tipo_servico,
        empresa_atual_slug: form.empresa_atual_slug,
        receita_bruta_mes: form.receita_bruta_mes,
        custo_direto_mes: form.custo_direto_mes,
        rbt12_destino: form.rbt12_destino,
        liminares_patrimonial: liminares,
      });
      setResultado(r);
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleSimular() {
    if (!resultado) return;
    setSimLoading(true);
    try {
      const r = await apiPost('/api/v1/empresas/migrador/simular', {
        contrato_id: form.contrato_id,
        tipo_servico: form.tipo_servico,
        empresa_atual_slug: form.empresa_atual_slug,
        empresa_destino_slug: resultado.empresa_destino,
        receita_bruta_mes: form.receita_bruta_mes,
        custo_direto_mes: form.custo_direto_mes,
        custo_indireto_mes: 0,
        rbt12: form.rbt12_destino,
        liminares,
      });
      setSimulacao(r);
      setShowSimulacao(true);
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setSimLoading(false);
    }
  }

  async function handleGerarAditivo() {
    if (!resultado) return;
    setAditivoLoading(true);
    try {
      const r = await apiPost('/api/v1/empresas/migrador/aditivo', {
        contrato_id: form.contrato_id,
        empresa_origem: form.empresa_atual_slug,
        empresa_destino: resultado.empresa_destino,
      });
      setAditivo(r.aditivo_texto);
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setAditivoLoading(false);
    }
  }

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-blue-100 rounded-xl">
          <ArrowRightLeft className="w-5 h-5 text-blue-600" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Analisar Contrato Individual</h2>
          <p className="text-sm text-gray-500">Verifica se o contrato deve migrar e calcula o impacto tributário</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">ID do Contrato</label>
          <input
            type="number"
            value={form.contrato_id}
            onChange={e => setForm(f => ({ ...f, contrato_id: Number(e.target.value) }))}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Tipo de Serviço</label>
          <select
            value={form.tipo_servico}
            onChange={e => setForm(f => ({ ...f, tipo_servico: e.target.value }))}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
          >
            {TIPOS_SERVICO.map(t => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Empresa Atual</label>
          <select
            value={form.empresa_atual_slug}
            onChange={e => setForm(f => ({ ...f, empresa_atual_slug: e.target.value }))}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
          >
            <option value="conecta_eletronica">Conecta Mais Eletrônica</option>
            <option value="conecta_patrimonial">Conecta Mais Patrimonial</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Receita Bruta/Mês (R$)</label>
          <input
            type="number"
            value={form.receita_bruta_mes}
            onChange={e => setForm(f => ({ ...f, receita_bruta_mes: Number(e.target.value) }))}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Custo Direto/Mês (R$)</label>
          <input
            type="number"
            value={form.custo_direto_mes}
            onChange={e => setForm(f => ({ ...f, custo_direto_mes: Number(e.target.value) }))}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">RBT12 Destino (R$)</label>
          <input
            type="number"
            value={form.rbt12_destino}
            onChange={e => setForm(f => ({ ...f, rbt12_destino: Number(e.target.value) }))}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {/* Liminares */}
      <div className="mb-5 p-4 bg-amber-50 border border-amber-200 rounded-xl">
        <p className="text-sm font-medium text-amber-800 mb-2">Liminares Judiciais (Patrimonial)</p>
        <div className="flex gap-6">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.pis_cofins}
              onChange={e => setForm(f => ({ ...f, pis_cofins: e.target.checked }))}
              className="rounded text-blue-600"
            />
            <span className="text-sm text-amber-700">PIS/COFINS = 0</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.inss}
              onChange={e => setForm(f => ({ ...f, inss: e.target.checked }))}
              className="rounded text-blue-600"
            />
            <span className="text-sm text-amber-700">INSS Não Retido</span>
          </label>
        </div>
      </div>

      <button
        onClick={handleAnalisar}
        disabled={loading}
        className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white px-5 py-2.5 rounded-xl font-medium text-sm transition-colors"
      >
        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
        Analisar
      </button>

      {erro && (
        <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {erro}
        </div>
      )}

      {/* Resultado da análise */}
      {resultado && (
        <div className="mt-5 space-y-4">
          <div className={`p-4 rounded-xl border-2 ${resultado.deve_migrar ? 'border-green-300 bg-green-50' : 'border-gray-200 bg-gray-50'}`}>
            <div className="flex items-start justify-between gap-3 mb-3">
              <div className="flex items-center gap-2">
                {resultado.deve_migrar ? (
                  <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0" />
                ) : (
                  <Info className="w-5 h-5 text-gray-500 flex-shrink-0" />
                )}
                <span className={`font-semibold ${resultado.deve_migrar ? 'text-green-800' : 'text-gray-700'}`}>
                  {resultado.deve_migrar ? 'Recomendado Migrar' : 'Sem migração necessária'}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <EmpresaBadge slug={resultado.empresa_atual} />
                <ArrowRightLeft className="w-4 h-4 text-gray-400" />
                <EmpresaBadge slug={resultado.empresa_destino} />
              </div>
            </div>
            <p className="text-sm text-gray-700 mb-4">{resultado.motivo}</p>

            {/* Impacto financeiro */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-white rounded-lg p-3 border border-gray-200">
                <p className="text-xs text-gray-500 mb-1">Imposto Atual/Mês</p>
                <p className="font-bold text-gray-900 text-sm">{fmt(resultado.impacto_financeiro.imposto_atual_mes)}</p>
              </div>
              <div className="bg-white rounded-lg p-3 border border-gray-200">
                <p className="text-xs text-gray-500 mb-1">Imposto Destino/Mês</p>
                <p className="font-bold text-gray-900 text-sm">{fmt(resultado.impacto_financeiro.imposto_destino_mes)}</p>
              </div>
              <div className={`rounded-lg p-3 border ${resultado.impacto_financeiro.economia_mensal > 0 ? 'bg-green-50 border-green-200' : 'bg-gray-50 border-gray-200'}`}>
                <p className="text-xs text-gray-500 mb-1">Economia/Mês</p>
                <p className={`font-bold text-sm ${resultado.impacto_financeiro.economia_mensal > 0 ? 'text-green-700' : 'text-gray-600'}`}>
                  {fmt(resultado.impacto_financeiro.economia_mensal)}
                </p>
              </div>
              <div className={`rounded-lg p-3 border ${resultado.impacto_financeiro.economia_anual > 0 ? 'bg-green-50 border-green-200' : 'bg-gray-50 border-gray-200'}`}>
                <p className="text-xs text-gray-500 mb-1">Economia/Ano</p>
                <p className={`font-bold text-sm ${resultado.impacto_financeiro.economia_anual > 0 ? 'text-green-700' : 'text-gray-600'}`}>
                  {fmt(resultado.impacto_financeiro.economia_anual)}
                </p>
              </div>
            </div>

            {/* Pendências */}
            {resultado.pendencias?.length > 0 && (
              <div className="mt-3 space-y-1.5">
                <p className="text-xs font-medium text-amber-700">Pendências antes de migrar:</p>
                {resultado.pendencias.map((p: string, i: number) => (
                  <p key={i} className="text-xs text-amber-700 pl-2">{p}</p>
                ))}
              </div>
            )}

            {/* Ações */}
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                onClick={handleSimular}
                disabled={simLoading}
                className="flex items-center gap-2 bg-white border border-blue-300 text-blue-700 hover:bg-blue-50 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-60"
              >
                {simLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <TrendingUp className="w-4 h-4" />}
                Simular Completo
              </button>
              <button
                onClick={handleGerarAditivo}
                disabled={aditivoLoading}
                className="flex items-center gap-2 bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-60"
              >
                {aditivoLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
                Gerar Aditivo
              </button>
            </div>
          </div>

          {/* Simulação completa */}
          {simulacao && showSimulacao && (
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <p className="font-semibold text-blue-800">Simulação Completa</p>
                <button type="button" onClick={() => setShowSimulacao(false)} className="text-blue-500 hover:text-blue-700">
                  <ChevronUp className="w-4 h-4" />
                </button>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                <div className="bg-white rounded-lg p-3 border border-blue-200">
                  <p className="text-xs text-gray-500 mb-1">Margem Origem</p>
                  <p className="font-bold text-gray-900">{simulacao.margem.origem_pct.toFixed(1)}%</p>
                </div>
                <div className="bg-white rounded-lg p-3 border border-blue-200">
                  <p className="text-xs text-gray-500 mb-1">Margem Destino</p>
                  <p className="font-bold text-gray-900">{simulacao.margem.destino_pct.toFixed(1)}%</p>
                </div>
                <div className={`rounded-lg p-3 border ${simulacao.margem.ganho_pct > 0 ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
                  <p className="text-xs text-gray-500 mb-1">Ganho de Margem</p>
                  <p className={`font-bold ${simulacao.margem.ganho_pct > 0 ? 'text-green-700' : 'text-red-700'}`}>
                    {simulacao.margem.ganho_pct > 0 ? '+' : ''}{simulacao.margem.ganho_pct.toFixed(1)}%
                  </p>
                </div>
                <div className="bg-white rounded-lg p-3 border border-blue-200">
                  <p className="text-xs text-gray-500 mb-1">Economia Impostos/Ano</p>
                  <p className="font-bold text-green-700">{fmt(simulacao.impostos.economia_anual)}</p>
                </div>
              </div>
              <p className="text-sm text-blue-800">{simulacao.recomendacao}</p>
            </div>
          )}

          {/* Aditivo */}
          {aditivo && (
            <div className="bg-gray-50 border border-gray-200 rounded-xl p-4">
              <p className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
                <FileText className="w-4 h-4" /> Aditivo Contratual Gerado
              </p>
              <textarea
                value={aditivo}
                readOnly
                rows={16}
                className="w-full font-mono text-xs bg-white border border-gray-200 rounded-lg p-3 resize-none"
               aria-label="Aditivo"/>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Seção 2: Análise em Lote ─────────────────────────────────────────────────

function SecaoAnaliseLote() {
  const [empresaAtual, setEmpresaAtual] = useState('conecta_eletronica');
  const [liminares, setLiminares] = useState<string[]>([]);
  const [json, setJson] = useState(
    JSON.stringify(
      [
        { contrato_id: 1, tipo_servico: 'vigilancia', receita_mes: 80000 },
        { contrato_id: 2, tipo_servico: 'portaria_remota', receita_mes: 45000 },
        { contrato_id: 3, tipo_servico: 'limpeza', receita_mes: 30000 },
        { contrato_id: 4, tipo_servico: 'cftv', receita_mes: 25000 },
      ],
      null,
      2
    )
  );
  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<any>(null);
  const [erro, setErro] = useState('');

  function toggleLiminar(l: string) {
    setLiminares(prev => prev.includes(l) ? prev.filter(x => x !== l) : [...prev, l]);
  }

  async function handleAnalisarLote() {
    setLoading(true);
    setErro('');
    setResultado(null);
    try {
      const contratos = JSON.parse(json);
      const r = await apiPost('/api/v1/empresas/migrador/analisar-lote', {
        contratos,
        empresa_atual_slug: empresaAtual,
        liminares_patrimonial: liminares,
      });
      setResultado(r);
    } catch (e: any) {
      setErro(e.message || 'Erro ao processar JSON');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-purple-100 rounded-xl">
          <Package className="w-5 h-5 text-purple-600" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Analisar em Lote</h2>
          <p className="text-sm text-gray-500">Classifique múltiplos contratos de uma só vez</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Empresa Atual (origem)</label>
          <select
            value={empresaAtual}
            onChange={e => setEmpresaAtual(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-purple-500"
          >
            <option value="conecta_eletronica">Conecta Mais Eletrônica</option>
            <option value="conecta_patrimonial">Conecta Mais Patrimonial</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Liminares ativas</label>
          <div className="flex gap-4">
            {['pis_cofins_zero', 'inss_nao_retido'].map(l => (
              <label key={l} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={liminares.includes(l)}
                  onChange={() => toggleLiminar(l)}
                  className="rounded text-purple-600"
                />
                <span className="text-sm text-gray-700">
                  {l === 'pis_cofins_zero' ? 'PIS/COFINS = 0' : 'INSS Não Retido'}
                </span>
              </label>
            ))}
          </div>
        </div>
      </div>

      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-700 mb-1">
          JSON dos contratos <span className="text-gray-400 font-normal">(array com contrato_id, tipo_servico, receita_mes)</span>
        </label>
        <textarea
          value={json}
          onChange={e => setJson(e.target.value)}
          rows={10}
          className="w-full font-mono text-xs border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-purple-500 resize-y"
        />
      </div>

      <button
        onClick={handleAnalisarLote}
        disabled={loading}
        className="flex items-center gap-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-60 text-white px-5 py-2.5 rounded-xl font-medium text-sm transition-colors"
      >
        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Package className="w-4 h-4" />}
        Analisar Lote
      </button>

      {erro && (
        <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {erro}
        </div>
      )}

      {resultado && (
        <div className="mt-5 space-y-4">
          {/* KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: 'Total', value: resultado.total_contratos, color: 'blue' },
              { label: '→ Patrimonial', value: resultado.humanizados, color: 'green' },
              { label: '→ Eletrônica', value: resultado.eletronicos, color: 'blue' },
              { label: 'Indefinidos', value: resultado.indefinidos, color: 'gray' },
            ].map(k => (
              <div key={k.label} className={`rounded-xl p-4 border ${
                k.color === 'green' ? 'bg-green-50 border-green-200' :
                k.color === 'blue' ? 'bg-blue-50 border-blue-200' : 'bg-gray-50 border-gray-200'
              }`}>
                <p className="font-data text-2xl font-semibold tabular-nums text-gray-900">{k.value}</p>
                <p className="text-xs text-gray-600 mt-1">{k.label}</p>
              </div>
            ))}
          </div>

          {/* Economia total */}
          <div className="bg-gradient-to-r from-green-500 to-emerald-600 text-white rounded-xl p-5">
            <p className="text-sm opacity-90 mb-1">Economia anual total estimada</p>
            <p className="font-data text-3xl font-semibold tabular-nums">{fmt(resultado.economia_anual_total)}</p>
            <p className="text-sm opacity-75 mt-1">migrando {resultado.humanizados} contratos para Patrimonial</p>
          </div>

          {/* Detalhes humanizados */}
          {resultado.detalhes_humanizados?.length > 0 && (
            <div>
              <p className="font-medium text-gray-800 mb-2">Contratos → Conecta Patrimonial ({resultado.humanizados})</p>
              <div className="space-y-2">
                {resultado.detalhes_humanizados.map((d: any) => (
                  <div key={d.contrato_id} className="flex items-center justify-between bg-green-50 border border-green-200 rounded-lg px-3 py-2">
                    <div>
                      <span className="text-sm font-medium text-gray-800">Contrato #{d.contrato_id}</span>
                      <span className="ml-2 text-xs text-gray-500">{d.tipo}</span>
                    </div>
                    <span className="text-sm font-semibold text-green-700">{fmt(d.economia_anual)}/ano</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Detalhes eletrônicos */}
          {resultado.detalhes_eletronicos?.length > 0 && (
            <div>
              <p className="font-medium text-gray-800 mb-2">Contratos → Conecta Eletrônica ({resultado.eletronicos})</p>
              <div className="space-y-2">
                {resultado.detalhes_eletronicos.map((d: any) => (
                  <div key={d.contrato_id} className="flex items-center justify-between bg-blue-50 border border-blue-200 rounded-lg px-3 py-2">
                    <div>
                      <span className="text-sm font-medium text-gray-800">Contrato #{d.contrato_id}</span>
                      <span className="ml-2 text-xs text-gray-500">{d.tipo}</span>
                    </div>
                    <EmpresaBadge slug="conecta_eletronica" />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Seção 3: Guia de Migração ────────────────────────────────────────────────

function SecaoGuia() {
  const etapas = [
    {
      num: '1',
      titulo: 'Classificar Serviço',
      desc: 'Use o Analisador para identificar se o contrato é humanizado (Patrimonial) ou eletrônico (Eletrônica).',
      cor: 'blue',
    },
    {
      num: '2',
      titulo: 'Simular Impacto',
      desc: 'Calcule a economia tributária real antes de executar qualquer ação. Verifique margem e liminares.',
      cor: 'purple',
    },
    {
      num: '3',
      titulo: 'Aguardar CNPJ (Patrimonial)',
      desc: 'A Conecta Patrimonial está em abertura. A migração para ela deve aguardar a emissão do CNPJ.',
      cor: 'amber',
    },
    {
      num: '4',
      titulo: 'Gerar Aditivo',
      desc: 'Emita o aditivo contratual informando o novo CNPJ faturador. Mantenha todas as condições comerciais.',
      cor: 'green',
    },
    {
      num: '5',
      titulo: 'Notificar Cliente',
      desc: 'Comunique o cliente com antecedência mínima de 30 dias informando a mudança do CNPJ emissor de NFS-e.',
      cor: 'teal',
    },
    {
      num: '6',
      titulo: 'Registrar Auditoria',
      desc: 'Todo processo fica registrado com data, empresa origem/destino e responsável pela aprovação.',
      cor: 'gray',
    },
  ];

  const corMap: Record<string, string> = {
    blue: 'bg-blue-100 text-blue-700 border-blue-200',
    purple: 'bg-purple-100 text-purple-700 border-purple-200',
    amber: 'bg-amber-100 text-amber-700 border-amber-200',
    green: 'bg-green-100 text-green-700 border-green-200',
    teal: 'bg-teal-100 text-teal-700 border-teal-200',
    gray: 'bg-gray-100 text-gray-700 border-gray-200',
  };

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-green-100 rounded-xl">
          <CheckCircle2 className="w-5 h-5 text-green-600" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Guia de Migração</h2>
          <p className="text-sm text-gray-500">Processo passo a passo para migrar contratos com segurança</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {etapas.map(e => (
          <div key={e.num} className={`rounded-xl border p-4 ${corMap[e.cor]}`}>
            <div className="flex items-center gap-2 mb-2">
              <span className="w-6 h-6 rounded-full bg-white flex items-center justify-center text-xs font-bold">
                {e.num}
              </span>
              <p className="font-semibold text-sm">{e.titulo}</p>
            </div>
            <p className="text-xs leading-relaxed opacity-80">{e.desc}</p>
          </div>
        ))}
      </div>

      {/* Alerta de liminares */}
      <div className="mt-5 p-4 bg-amber-50 border border-amber-300 rounded-xl flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
        <div>
          <p className="font-semibold text-amber-800 text-sm mb-1">Sobre as Liminares Judiciais</p>
          <p className="text-sm text-amber-700">
            As liminares de PIS/COFINS e INSS reduzem significativamente a carga tributária da Patrimonial.
            Quando concedidas, a vantagem do Simples Nacional é ainda maior. Acompanhe o status em{' '}
            <Link href="/modulos/empresas/liminares" className="underline font-medium">
              Liminares Judiciais
            </Link>.
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── Página Principal ─────────────────────────────────────────────────────────

export default function MigradorPage() {
  return (
    <div className="min-h-screen bg-gray-50 p-6">
      {/* Header */}
      <div className="max-w-6xl mx-auto mb-8">
        <Link
          href="/modulos/empresas"
          className="inline-flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 mb-4 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Voltar para Multi-Empresa
        </Link>
        <div className="flex items-start gap-4">
          <div className="p-3 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-2xl shadow-lg">
            <ArrowRightLeft className="w-7 h-7 text-white" />
          </div>
          <div>
            <h1 className="font-display text-2xl font-bold text-gray-900">Migrador de Contratos</h1>
            <p className="text-gray-500 mt-1">
              Classifique e migre contratos entre Eletrônica e Patrimonial com análise tributária completa
            </p>
          </div>
        </div>

        {/* Regra rápida */}
        <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="flex items-center gap-3 bg-white border border-green-200 rounded-xl p-4">
            <div className="w-3 h-3 rounded-full bg-green-500 flex-shrink-0" />
            <div>
              <p className="font-semibold text-gray-800 text-sm">Serviços Humanizados → Patrimonial</p>
              <p className="text-xs text-gray-500">Vigilância, portaria, limpeza, facilities... (Simples Nacional Anexo III)</p>
            </div>
          </div>
          <div className="flex items-center gap-3 bg-white border border-blue-200 rounded-xl p-4">
            <div className="w-3 h-3 rounded-full bg-blue-500 flex-shrink-0" />
            <div>
              <p className="font-semibold text-gray-800 text-sm">Serviços Eletrônicos → Eletrônica</p>
              <p className="text-xs text-gray-500">Portaria remota, CFTV, alarmes, automação... (Lucro Real)</p>
            </div>
          </div>
        </div>
      </div>

      {/* Seções */}
      <div className="max-w-6xl mx-auto space-y-6">
        <SecaoAnaliseIndividual />
        <SecaoAnaliseLote />
        <SecaoGuia />
      </div>
    </div>
  );
}
