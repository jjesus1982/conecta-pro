'use client'

import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { AlertTriangle } from 'lucide-react'

// ─── Tipos exatos do endpoint /financial/custeio/abc ──────────────────────
interface CustoComposicao {
  custo_direto: number
  overhead_rateado: number
  custo_total: number
}

interface MargemTipo {
  mc_valor: number
  mc_pct: number
  margem_liquida_valor: number
  margem_liquida_pct: number
  meta_mc_pct: number
  gap_meta: number
  margem: number
  custo_medio: number
  cor: string
}

interface TipoAnalise {
  tipo: string
  contratos: number
  receita_mensal: number
  pct_mrr: number
  custeio: CustoComposicao
  margens: MargemTipo
  classificacao: 'estrela' | 'atencao' | 'abacaxi'
  recomendacao: string
}

interface CategoriaGasto {
  categoria: string
  total: number
  qtd: number
}

interface CusteioABC {
  timestamp: string
  periodo_referencia: string
  mrr_total: number
  custo_total_mes: number
  resultado_estimado: number
  margem_global_pct: number
  cct_2026: { piso_base_cct: number; custo_all_in_posto: number; encargos_pct: number }
  custo_por_categoria: CategoriaGasto[]
  analise_por_tipo: TipoAnalise[]
  alertas: string[]
}

// ─── Helpers ──────────────────────────────────────────────────────────────
const fetchAuth = (url: string) =>
  fetch(url, {
    headers: {
      Authorization: `Bearer ${typeof window !== 'undefined'
        ? (localStorage.getItem('access_token') ?? localStorage.getItem('token') ?? '')
        : ''}`,
    },
  }).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })

const brl = (v: number) =>
  (v ?? 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

const pct = (v: number) => `${(v ?? 0).toFixed(1)}%`

const LABEL: Record<string, string> = {
  portaria: 'Portaria',
  seguranca_eletronica: 'Seg. Eletrônica',
  limpeza: 'Limpeza',
  portaria_remota: 'Portaria Remota',
  manutencao_cftv: 'Manutenção CFTV',
}

const CLASS_STYLE: Record<string, { bg: string; text: string; border: string; icon: string }> = {
  estrela: { bg: 'bg-green-50',  text: 'text-green-700',  border: 'border-green-200',  icon: '⭐' },
  atencao: { bg: 'bg-yellow-50', text: 'text-yellow-700', border: 'border-yellow-200', icon: '⚠️' },
  abacaxi: { bg: 'bg-red-50',    text: 'text-red-700',    border: 'border-red-200',    icon: '❌' },
}

const mcColor = (v: number) =>
  v >= 35 ? 'text-green-600' : v >= 20 ? 'text-yellow-600' : 'text-red-600'

type AbaId = 'por_tipo' | 'direcionadores' | 'atividades' | 'pools' | 'objetos'

// ─── Componente ───────────────────────────────────────────────────────────
export default function CusteioPage() {
  const [abaAtiva, setAbaAtiva] = useState<AbaId>('por_tipo')

  const { data, isLoading, error, refetch } = useQuery<CusteioABC>({
    queryKey: ['custeio-abc-v2'],
    queryFn: () => fetchAuth('/api/v1/financial/custeio/abc'),
    staleTime: 10 * 60 * 1000,
    retry: 2,
  })

  if (isLoading) return (
    <div className="p-6 max-w-7xl mx-auto animate-pulse space-y-4">
      <div className="h-8 bg-gray-100 rounded w-64" />
      <div className="grid grid-cols-4 gap-4">
        {[1, 2, 3, 4].map(i => <div key={i} className="h-24 bg-gray-100 rounded-xl" />)}
      </div>
      <div className="h-48 bg-gray-100 rounded-xl" />
    </div>
  )

  if (error || !data) return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="bg-red-50 border border-red-200 rounded-xl p-6 flex items-start gap-4">
        <AlertTriangle className="w-6 h-6 text-red-500 flex-shrink-0" />
        <div>
          <p className="font-medium text-red-900">Erro ao carregar Custeio ABC</p>
          <p className="text-sm text-red-700 mt-1">{error ? String(error) : 'Dados indisponíveis'}</p>
          <button
            onClick={() => refetch()}
            className="mt-3 px-4 py-1.5 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700"
          >
            Tentar novamente
          </button>
        </div>
      </div>
    </div>
  )

  const tipos = data.analise_por_tipo ?? []
  const categorias = data.custo_por_categoria ?? []
  const alertas = data.alertas ?? []
  const cct = data.cct_2026

  const ABAS: { id: AbaId; label: string; n: number }[] = [
    { id: 'por_tipo',       label: 'Por Tipo',       n: tipos.length },
    { id: 'direcionadores', label: 'Direcionadores',  n: tipos.length },
    { id: 'atividades',     label: 'Atividades',      n: tipos.filter(t => t.contratos > 0).length },
    { id: 'pools',          label: 'Pools de Custo',  n: tipos.filter(t => (t.custeio?.custo_direto ?? 0) > 0).length },
    { id: 'objetos',        label: 'Objetos',         n: categorias.length },
  ]

  const tiposFiltrados = tipos.filter(tipo => {
    if (abaAtiva === 'por_tipo' || abaAtiva === 'direcionadores') return true
    if (abaAtiva === 'atividades') return tipo.contratos > 0
    if (abaAtiva === 'pools') return (tipo.custeio?.custo_direto ?? 0) > 0
    return true
  })

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Custeio ABC</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Activity-Based Costing · {data.periodo_referencia} · CCT SINDECOMPRESTS 2026
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
        >
          ↺
        </button>
      </div>

      {/* Alertas */}
      {alertas.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 space-y-1">
          {alertas.map((a, i) => (
            <p key={i} className="text-sm text-amber-800">{a}</p>
          ))}
        </div>
      )}

      {/* KPIs globais */}
      <div className="grid grid-cols-4 gap-4">
        {[
          {
            label: 'MRR Total',
            value: brl(data.mrr_total),
            sub: `${tipos.length} tipos de serviço`,
            color: 'text-gray-900',
          },
          {
            label: 'Custo Total/Mês',
            value: brl(data.custo_total_mes),
            sub: 'extrato Inter real',
            color: 'text-gray-900',
          },
          {
            label: 'Resultado Estimado',
            value: brl(data.resultado_estimado),
            sub: 'MRR − custo',
            color: (data.resultado_estimado ?? 0) >= 0 ? 'text-green-600' : 'text-red-600',
          },
          {
            label: 'Margem Global',
            value: pct(data.margem_global_pct),
            sub: 'meta: 35%',
            color: mcColor(data.margem_global_pct),
          },
        ].map(k => (
          <div key={k.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <p className="text-xs text-gray-500">{k.label}</p>
            <p className={`text-xl font-semibold mt-1 ${k.color}`}>{k.value}</p>
            <p className="text-xs text-gray-400 mt-0.5">{k.sub}</p>
          </div>
        ))}
      </div>

      {/* CCT 2026 */}
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
        <p className="text-xs font-semibold text-blue-800 uppercase tracking-wide mb-3">
          CCT SINDECOMPRESTS 2026
        </p>
        <div className="grid grid-cols-3 gap-6 text-sm">
          <div>
            <span className="text-blue-600">Piso base CCT: </span>
            <strong>{brl(cct?.piso_base_cct ?? 0)}</strong>
          </div>
          <div>
            <span className="text-blue-600">Encargos: </span>
            <strong>{cct?.encargos_pct ?? 42}%</strong>
          </div>
          <div>
            <span className="text-blue-600">Custo all-in/posto: </span>
            <strong>{brl(cct?.custo_all_in_posto ?? 0)}</strong>
          </div>
        </div>
      </div>

      {/* Abas */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl w-fit">
        {ABAS.map(aba => (
          <button
            key={aba.id}
            onClick={() => setAbaAtiva(aba.id)}
            className={`px-4 py-1.5 text-sm rounded-lg transition-all ${
              abaAtiva === aba.id
                ? 'bg-white text-gray-900 font-medium shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {aba.label}
            <span className={`ml-1.5 text-xs px-1.5 py-0.5 rounded-full ${
              abaAtiva === aba.id ? 'bg-blue-100 text-blue-700' : 'bg-gray-200 text-gray-500'
            }`}>{aba.n}</span>
          </button>
        ))}
      </div>

      {/* Cards por tipo (todas as abas exceto objetos) */}
      {abaAtiva !== 'objetos' && (
        <div className="space-y-3">
          {tiposFiltrados.map((tipo, idx) => {
            const cs = CLASS_STYLE[tipo.classificacao] ?? CLASS_STYLE['atencao']!
            return (
              <div key={idx} className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                {/* Cabeçalho */}
                <div className="flex items-center justify-between p-4 border-b border-gray-50">
                  <div className="flex items-center gap-3">
                    <span className={`px-2.5 py-1 rounded-full text-xs font-medium border ${cs.bg} ${cs.text} ${cs.border}`}>
                      {cs.icon} {tipo.classificacao.charAt(0).toUpperCase() + tipo.classificacao.slice(1)}
                    </span>
                    <div>
                      <h3 className="font-medium text-gray-900">
                        {LABEL[tipo.tipo] ?? tipo.tipo.replace(/_/g, ' ')}
                      </h3>
                      <p className="text-xs text-gray-500">
                        {tipo.contratos} contrato(s) · {pct(tipo.pct_mrr ?? 0)} do MRR
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold text-gray-900">{brl(tipo.receita_mensal)}</p>
                    <p className="text-xs text-gray-400">receita/mês</p>
                  </div>
                </div>

                {/* Métricas */}
                <div className="grid grid-cols-4 gap-px bg-gray-100">
                  {[
                    { label: 'Custo Direto', value: brl(tipo.custeio?.custo_direto ?? 0), color: '', big: false },
                    { label: 'Overhead',     value: brl(tipo.custeio?.overhead_rateado ?? 0), color: '', big: false },
                    { label: 'MC %',         value: pct(tipo.margens?.mc_pct ?? 0), color: mcColor(tipo.margens?.mc_pct ?? 0), big: true },
                    {
                      label: 'Gap da meta',
                      value: (tipo.margens?.gap_meta ?? 0) <= 0
                        ? `+${Math.abs(tipo.margens?.gap_meta ?? 0).toFixed(1)}pp`
                        : `-${(tipo.margens?.gap_meta ?? 0).toFixed(1)}pp`,
                      color: (tipo.margens?.gap_meta ?? 0) <= 0 ? 'text-green-600' : 'text-orange-600',
                      big: false,
                    },
                  ].map(m => (
                    <div key={m.label} className="bg-white p-3">
                      <p className="text-xs text-gray-400">{m.label}</p>
                      <p className={`font-semibold mt-0.5 ${m.big ? 'text-lg' : 'text-sm'} ${m.color || 'text-gray-900'}`}>
                        {m.value}
                      </p>
                    </div>
                  ))}
                </div>

                {/* Recomendação */}
                {tipo.recomendacao && tipo.classificacao !== 'estrela' && (
                  <div className="px-4 py-2.5 bg-amber-50 border-t border-amber-100">
                    <p className="text-xs text-amber-700">💡 {tipo.recomendacao}</p>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Objetos de custo = categorias do extrato */}
      {abaAtiva === 'objetos' && (
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <p className="text-sm font-medium text-gray-900 mb-3">
            Gastos por Categoria — Extrato Inter
          </p>
          {categorias.length === 0 ? (
            <p className="text-sm text-gray-500">Nenhuma categoria disponível</p>
          ) : (
            <div className="grid grid-cols-3 gap-3">
              {categorias.map((cat, i) => (
                <div key={i} className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs text-gray-500 capitalize">
                    {(cat.categoria ?? '').replace(/_/g, ' ')}
                  </p>
                  <p className="font-semibold text-gray-900 mt-0.5">{brl(cat.total)}</p>
                  <p className="text-xs text-gray-400">{cat.qtd} lançamentos</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
