'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Heart,
  RefreshCw,
  Shield,
  Check,
  Info,
  DollarSign,
  Car,
  Utensils,
  Activity,
  Package,
} from 'lucide-react'

const API_BASE = '/api/v1/people-management/portal'

function getAuthHeaders() {
  const token =
    typeof window !== 'undefined'
      ? localStorage.getItem('access_token') || localStorage.getItem('token')
      : null
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

interface BeneficioCCT {
  tipo?: string
  obrigatorio?: boolean
  valor_minimo_cct?: number | null
  valor_empresa_cct?: number | null
  desconto_maximo_cct?: number | null
  desconto_percentual_cct?: number | null
  desconto_calculado?: number | null
  observacao?: string | null
}

interface BeneficioAtivo {
  tipo?: string
  operadora?: string
  plano?: string
  desconto_funcionario?: number
  contribuicao_empresa?: number
  status?: string
}

interface BeneficiosData {
  employee_id?: string
  cargo?: string
  salario_base?: number
  beneficios_ativos?: BeneficioAtivo[]
  beneficios_cct?: BeneficioCCT[]
  cct?: string
}

const TIPO_ICONS: Record<string, React.ElementType> = {
  vale_transporte: Car,
  vale_alimentacao: Utensils,
  vale_refeicao: Utensils,
  plano_saude: Activity,
  plano_odontologico: Heart,
  seguro_vida: Shield,
}

function getBeneficioIcon(tipo?: string) {
  if (!tipo) return Package
  const key = tipo.toLowerCase().replace(/ /g, '_')
  return TIPO_ICONS[key] || Package
}

function formatCurrency(v?: number | null) {
  if (v === null || v === undefined) return '—'
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

export default function BeneficiosPortalPage() {
  const [data, setData] = useState<BeneficiosData | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'ativos' | 'cct'>('ativos')

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/my-benefits`, { headers: getAuthHeaders() })
      if (res.ok) setData(await res.json())
    } catch {
      /* silencioso */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-xl p-6 shadow-sm animate-pulse">
            <div className="h-5 bg-gray-100 rounded w-1/3 mb-3" />
            <div className="h-20 bg-gray-50 rounded" />
          </div>
        ))}
      </div>
    )
  }

  const ativos = data?.beneficios_ativos ?? []
  const cct = data?.beneficios_cct ?? []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-xl p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h1 className="font-display text-xl flex items-center gap-2">
            <Heart className="w-6 h-6 text-red-500" />
            Meus Benefícios
          </h1>
          <button
            onClick={loadData}
            className="flex items-center gap-1 px-3 py-1.5 text-sm bg-gray-50 text-gray-600 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <RefreshCw className="w-4 h-4" /> Atualizar
          </button>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div className="bg-green-50 rounded-lg p-3 text-center">
            <p className="font-data text-2xl font-semibold tabular-nums text-green-600">{ativos.length}</p>
            <p className="text-xs text-green-500">Benefícios Ativos</p>
          </div>
          <div className="bg-blue-50 rounded-lg p-3 text-center">
            <p className="font-data text-2xl font-semibold tabular-nums text-blue-600">{cct.filter((b) => b.obrigatorio).length}</p>
            <p className="text-xs text-blue-500">Garantidos pela CCT</p>
          </div>
          <div className="bg-amber-50 rounded-lg p-3 text-center">
            <p className="font-data text-2xl font-semibold tabular-nums text-amber-600">
              {formatCurrency(data?.salario_base)}
            </p>
            <p className="text-xs text-amber-500">Salário Base</p>
          </div>
        </div>

        {data?.cct && (
          <div className="mt-3 flex items-center gap-2 text-xs text-gray-500 bg-blue-50 px-3 py-2 rounded-lg">
            <Shield className="w-3.5 h-3.5 text-blue-500" />
            <span>Referência: <strong className="text-blue-700">{data.cct}</strong></span>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="bg-white rounded-xl shadow-sm">
        <div className="flex border-b px-4 pt-3">
          {([
            { key: 'ativos', label: 'Benefícios Ativos', icon: Check },
            { key: 'cct', label: 'Garantidos pela CCT', icon: Shield },
          ] as const).map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        <div className="p-4">
          {/* Tab: Ativos */}
          {activeTab === 'ativos' && (
            <>
              {ativos.length === 0 ? (
                <div className="text-center py-12">
                  <Heart className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                  <p className="text-gray-500">Nenhum benefício cadastrado</p>
                  <p className="text-sm text-gray-400 mt-1">
                    Entre em contato com o DP para verificar seus benefícios.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {ativos.map((b, i) => {
                    const Icon = getBeneficioIcon(b.tipo)
                    return (
                      <div key={i} className="flex items-center justify-between p-4 bg-gray-50 rounded-xl border border-gray-100">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-xl bg-blue-100 flex items-center justify-center">
                            <Icon className="w-5 h-5 text-blue-600" />
                          </div>
                          <div>
                            <p className="font-medium text-sm text-gray-800">
                              {(b.tipo || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                            </p>
                            {b.operadora && <p className="text-xs text-gray-500">{b.operadora}{b.plano ? ` — ${b.plano}` : ''}</p>}
                          </div>
                        </div>
                        <div className="text-right text-sm">
                          {b.desconto_funcionario !== undefined && b.desconto_funcionario > 0 && (
                            <p className="text-red-600">-{formatCurrency(b.desconto_funcionario)}/mês</p>
                          )}
                          {b.contribuicao_empresa !== undefined && b.contribuicao_empresa > 0 && (
                            <p className="text-green-600 text-xs">Empresa: {formatCurrency(b.contribuicao_empresa)}</p>
                          )}
                          <span className={`text-xs px-2 py-0.5 rounded-full ${
                            b.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
                          }`}>
                            {b.status === 'active' ? 'Ativo' : b.status}
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </>
          )}

          {/* Tab: CCT */}
          {activeTab === 'cct' && (
            <div className="space-y-2">
              {cct.filter((b) => b.obrigatorio).length === 0 ? (
                <div className="text-center py-8">
                  <Info className="w-10 h-10 text-gray-300 mx-auto mb-2" />
                  <p className="text-gray-500 text-sm">Nenhum benefício CCT disponível</p>
                </div>
              ) : (
                cct.filter((b) => b.obrigatorio).map((b, i) => {
                  const Icon = getBeneficioIcon(b.tipo)
                  return (
                    <div key={i} className="p-4 bg-blue-50 rounded-xl border border-blue-100">
                      <div className="flex items-start gap-3">
                        <div className="w-9 h-9 rounded-lg bg-blue-100 flex items-center justify-center flex-shrink-0">
                          <Icon className="w-4 h-4 text-blue-600" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-sm text-blue-900">
                            {(b.tipo || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                          </p>
                          {b.observacao && (
                            <p className="text-xs text-blue-600 mt-0.5">{b.observacao}</p>
                          )}
                          <div className="flex flex-wrap gap-3 mt-2 text-xs">
                            {b.valor_minimo_cct !== null && b.valor_minimo_cct !== undefined && (
                              <span className="flex items-center gap-1 text-blue-700">
                                <DollarSign className="w-3 h-3" />
                                Valor mínimo: <strong>{formatCurrency(b.valor_minimo_cct)}</strong>
                              </span>
                            )}
                            {b.desconto_calculado !== null && b.desconto_calculado !== undefined && (
                              <span className="flex items-center gap-1 text-blue-700">
                                Desconto sobre seu salário: <strong>{formatCurrency(b.desconto_calculado)}</strong>
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })
              )}

              <div className="mt-4 p-3 bg-gray-50 rounded-lg text-xs text-gray-500 flex items-start gap-2">
                <Info className="w-4 h-4 flex-shrink-0 mt-0.5 text-gray-400" />
                Os valores acima são definidos pela CCT vigente. Para detalhes sobre sua situação específica, acesse{' '}
                <a href="/modulos/portal/cct" className="text-blue-600 hover:underline font-medium">
                  Direitos CCT
                </a>.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
