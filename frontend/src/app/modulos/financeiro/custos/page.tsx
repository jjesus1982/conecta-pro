'use client'

import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, XCircle, Star } from 'lucide-react'

interface TipoCusteio {
  tipo: string
  contratos: number
  receita_mensal: number
  pct_mrr: number
  custeio: {
    custo_direto: number
    overhead_rateado: number
    custo_total: number
  }
  margens: {
    mc_valor: number
    mc_pct: number
    meta_mc_pct: number
    gap_meta: number
  }
  classificacao: string
  recomendacao: string
}

interface CusteioABC {
  mrr_total: number
  custo_total_mes: number
  resultado_estimado: number
  margem_global_pct: number
  cct_2026: {
    piso_base_cct: number
    custo_all_in_posto: number
    encargos_pct: number
  }
  custo_por_categoria: Array<{
    categoria: string
    total: number
    qtd: number
  }>
  analise_por_tipo: TipoCusteio[]
  alertas: string[]
}

const fetchWithAuth = async (url: string) => {
  const token = typeof window !== 'undefined'
    ? (localStorage.getItem('access_token') ?? localStorage.getItem('token') ?? '')
    : ''
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` }
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

const classColor: Record<string, string> = {
  estrela: 'bg-green-50 text-green-700 border border-green-200',
  atencao: 'bg-yellow-50 text-yellow-700 border border-yellow-200',
  abacaxi: 'bg-red-50 text-red-700 border border-red-200',
}

const mcColor = (pct: number) =>
  pct >= 35 ? 'text-green-600' : pct >= 20 ? 'text-yellow-600' : 'text-red-600'

export default function CustosPage() {
  const { data, isLoading, error } = useQuery<CusteioABC>({
    queryKey: ['custeio-abc'],
    queryFn: () => fetchWithAuth('/api/v1/financial/custeio/abc'),
    staleTime: 10 * 60 * 1000,
    retry: 2,
  })

  if (isLoading) {
    return (
      <div className="p-6 max-w-7xl mx-auto">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-gray-200 rounded w-64" />
          <div className="grid grid-cols-4 gap-4">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="h-24 bg-gray-200 rounded-xl" />
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="p-6 max-w-7xl mx-auto">
        <h1 className="text-2xl font-semibold text-gray-900 mb-4">
          Custo por Tipo de Serviço
        </h1>
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4">
          <p className="text-yellow-800">
            Erro ao carregar dados de custeio. Verifique se o backend está acessível.
          </p>
          {error && (
            <p className="text-sm text-yellow-600 mt-1">{String(error)}</p>
          )}
        </div>
      </div>
    )
  }

  const tipos = data.analise_por_tipo ?? []
  const categorias = data.custo_por_categoria ?? []
  const alertas = data.alertas ?? []
  const cct = data.cct_2026

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Custo por Tipo de Serviço</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Análise detalhada de custos e margens por modalidade de serviço
          </p>
        </div>
        <span className="text-xs text-gray-400 bg-gray-100 px-3 py-1 rounded-full">
          CCT SINDECOMPRESTS 2026
        </span>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {[
          {
            label: 'MRR Total',
            sub: `${tipos.length} tipos de serviço`,
            value: `R$ ${(data.mrr_total ?? 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`,
            color: 'text-gray-900',
          },
          {
            label: 'Custo Total Mês',
            sub: 'extrato Inter real',
            value: `R$ ${(data.custo_total_mes ?? 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`,
            color: 'text-gray-900',
          },
          {
            label: 'Resultado Estimado',
            sub: 'MRR − custo total',
            value: `R$ ${(data.resultado_estimado ?? 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`,
            color: (data.resultado_estimado ?? 0) >= 0 ? 'text-green-600' : 'text-red-600',
          },
          {
            label: 'Margem Global',
            sub: 'meta: 35%',
            value: `${data.margem_global_pct ?? 0}%`,
            color: mcColor(data.margem_global_pct ?? 0),
          },
        ].map(kpi => (
          <div key={kpi.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <p className="text-xs text-gray-500">{kpi.label}</p>
            <p className={`text-xl font-semibold mt-1 ${kpi.color}`}>{kpi.value}</p>
            <p className="text-xs text-gray-400 mt-0.5">{kpi.sub}</p>
          </div>
        ))}
      </div>

      {cct && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
          <p className="text-sm font-medium text-blue-900 mb-2">CCT SINDECOMPRESTS 2026</p>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-blue-600">Piso base CCT:</span>{' '}
              <strong>
                R$ {(cct.piso_base_cct ?? 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
              </strong>
            </div>
            <div>
              <span className="text-blue-600">Encargos:</span>{' '}
              <strong>{cct.encargos_pct ?? 42}%</strong>
            </div>
            <div>
              <span className="text-blue-600">Custo all-in/posto:</span>{' '}
              <strong>
                R$ {(cct.custo_all_in_posto ?? 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
              </strong>
            </div>
          </div>
        </div>
      )}

      {tipos.length > 0 ? (
        <div>
          <h2 className="text-base font-medium text-gray-900 mb-3">Análise por Tipo de Serviço</h2>
          <div className="space-y-3">
            {tipos.map((tipo, idx) => (
              <div key={idx} className="bg-white border border-gray-200 rounded-xl p-4">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium text-gray-900 capitalize">
                        {(tipo.tipo ?? '').replace(/_/g, ' ')}
                      </h3>
                      <span
                        className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${classColor[tipo.classificacao] ?? classColor.atencao}`}
                      >
                        {tipo.classificacao === 'estrela' ? (
                          <><Star className="w-3 h-3" /> Estrela</>
                        ) : tipo.classificacao === 'abacaxi' ? (
                          <><XCircle className="w-3 h-3 text-red-600" /> Abacaxi</>
                        ) : (
                          <><AlertTriangle className="w-3 h-3 text-amber-500" /> Atenção</>
                        )}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {tipo.contratos ?? 0} contrato(s) · {tipo.pct_mrr ?? 0}% do MRR
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold text-gray-900">
                      R${' '}
                      {(tipo.receita_mensal ?? 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                    </p>
                    <p className="text-xs text-gray-500">receita/mês</p>
                  </div>
                </div>
                <div className="grid grid-cols-4 gap-3 text-sm">
                  {[
                    {
                      label: 'Custo direto',
                      value: `R$ ${(tipo.custeio?.custo_direto ?? 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`,
                    },
                    {
                      label: 'MC valor',
                      value: `R$ ${(tipo.margens?.mc_valor ?? 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`,
                      color: mcColor(tipo.margens?.mc_pct ?? 0),
                    },
                    {
                      label: 'MC %',
                      value: `${tipo.margens?.mc_pct ?? 0}%`,
                      color: mcColor(tipo.margens?.mc_pct ?? 0),
                      big: true,
                    },
                    {
                      label: 'Gap da meta',
                      value:
                        (tipo.margens?.gap_meta ?? 0) > 0
                          ? `-${tipo.margens?.gap_meta}pp`
                          : `+${Math.abs(tipo.margens?.gap_meta ?? 0)}pp`,
                      color: (tipo.margens?.gap_meta ?? 0) <= 0 ? 'text-green-600' : 'text-orange-600',
                    },
                  ].map(cell => (
                    <div key={cell.label} className="bg-gray-50 rounded-lg p-2">
                      <p className="text-xs text-gray-500">{cell.label}</p>
                      <p
                        className={`${cell.big ? 'text-lg font-semibold' : 'font-medium'} ${cell.color ?? 'text-gray-900'}`}
                      >
                        {cell.value}
                      </p>
                    </div>
                  ))}
                </div>
                {tipo.recomendacao && tipo.classificacao !== 'estrela' && (
                  <p className="mt-2 text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-1.5">
                    {tipo.recomendacao}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="bg-gray-50 rounded-xl p-8 text-center">
          <p className="text-gray-500">Nenhum tipo de serviço encontrado.</p>
        </div>
      )}

      {alertas.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <p className="text-sm font-medium text-red-900 mb-2 flex items-center gap-1"><AlertTriangle className="w-4 h-4" /> Alertas de custeio</p>
          {alertas.map((alerta, i) => (
            <p key={i} className="text-sm text-red-700">
              {alerta}
            </p>
          ))}
        </div>
      )}

      {categorias.length > 0 && (
        <div>
          <h2 className="text-base font-medium text-gray-900 mb-3">
            Custos por Categoria (extrato Inter)
          </h2>
          <div className="grid grid-cols-3 gap-3">
            {categorias.slice(0, 9).map(cat => (
              <div key={cat.categoria} className="bg-white border border-gray-200 rounded-xl p-3">
                <p className="text-xs text-gray-500 capitalize">
                  {(cat.categoria ?? '').replace(/_/g, ' ')}
                </p>
                <p className="font-semibold text-gray-900 mt-0.5">
                  R$ {(cat.total ?? 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                </p>
                <p className="text-xs text-gray-400">{cat.qtd ?? 0} lançamentos</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
