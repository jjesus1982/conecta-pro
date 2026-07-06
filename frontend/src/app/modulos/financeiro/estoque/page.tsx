'use client'

import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { AlertTriangle } from 'lucide-react'

interface InventoryItem {
  id: string
  product_id: string
  warehouse_id: string
  batch_number: string | null
  status: string
  quantity_on_hand: number
  quantity_available: number
  unit_cost: number
  total_cost: number
  expiry_date: string | null
  full_location: string | null
  is_low_stock: boolean
  is_expired: boolean
  // campos do join com products (podem existir ou não)
  name?: string
  code?: string
  description?: string
  unit?: string
  category?: string
}

interface Warehouse {
  id: string
  code: string
  name: string
  warehouse_type: string
  status: string
  city: string | null
  total_items: number
  total_value: number
  occupancy_rate: number
  is_active: boolean
}

const fetchAuth = (url: string) =>
  fetch(url, {
    headers: {
      Authorization: `Bearer ${typeof window !== 'undefined'
        ? (localStorage.getItem('access_token') ?? localStorage.getItem('token') ?? '') : ''}`,
    },
  }).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })

const brl = (v: number) =>
  (v ?? 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

const STATUS_STYLE: Record<string, string> = {
  disponivel: 'bg-green-100 text-green-700',
  available:  'bg-green-100 text-green-700',
  reservado:  'bg-yellow-100 text-yellow-700',
  reserved:   'bg-yellow-100 text-yellow-700',
  vencido:    'bg-red-100 text-red-700',
  expired:    'bg-red-100 text-red-700',
  baixo:      'bg-orange-100 text-orange-700',
}

export default function EstoquePage() {
  const [abaAtiva, setAbaAtiva] = useState<'itens' | 'armazens' | 'movimentacoes'>('itens')
  const [search, setSearch]     = useState('')

  const { data: items = [], isLoading: itemsLoading, error: itemsError, refetch } =
    useQuery<InventoryItem[]>({
      queryKey: ['inventory-items'],
      queryFn: () => fetchAuth('/api/v1/financial/inventory/items'),
      staleTime: 5 * 60 * 1000,
      retry: 1,
    })

  const { data: warehouses = [], isLoading: whLoading } =
    useQuery<Warehouse[]>({
      queryKey: ['inventory-warehouses'],
      queryFn: () => fetchAuth('/api/v1/financial/inventory/warehouses'),
      staleTime: 5 * 60 * 1000,
      retry: 1,
    })

  // Totais reais
  const totalItems   = items.length
  const totalValue   = items.reduce((s, i) => s + (i.total_cost ?? 0), 0)
  const lowStock     = items.filter(i => i.is_low_stock).length
  const numArmazens  = warehouses.length

  const filteredItems = items.filter(item => {
    const label = (item.name ?? item.product_id ?? '').toLowerCase()
    const code  = (item.code ?? item.batch_number ?? '').toLowerCase()
    return label.includes(search.toLowerCase()) || code.includes(search.toLowerCase())
  })

  const ABAS = [
    { id: 'itens',         label: 'Itens',      n: totalItems },
    { id: 'armazens',      label: 'Armazéns',   n: numArmazens },
    { id: 'movimentacoes', label: 'Movimentações', n: null },
  ] as const

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Estoque</h1>
          <p className="text-sm text-gray-500 mt-0.5">Controle de materiais e movimentações</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => refetch()}
            className="px-3 py-2 text-sm border border-gray-200 rounded-lg
              hover:bg-gray-50 text-gray-600">
            ↺
          </button>
          <button className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700">
            + Nova Movimentação
          </button>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Total Itens',  value: totalItems,  icon: '📦', color: 'text-gray-900' },
          { label: 'Valor Total',  value: brl(totalValue), icon: '💰', color: 'text-gray-900', brl: true },
          { label: 'Abaixo do Mínimo', value: lowStock, icon: '⚠️', color: 'text-orange-600' },
          { label: 'Armazéns',     value: numArmazens,  icon: '🏭', color: 'text-blue-600' },
        ].map(k => (
          <div key={k.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <p className="text-xs text-gray-500 flex items-center gap-1">
              <span>{k.icon}</span>{k.label}
            </p>
            <p className={`text-xl font-semibold mt-1 ${k.color}`}>
              {itemsLoading ? '–' : String(k.value)}
            </p>
          </div>
        ))}
      </div>

      {/* Abas */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl w-fit">
        {ABAS.map(aba => (
          <button key={aba.id} onClick={() => setAbaAtiva(aba.id as typeof abaAtiva)}
            className={`px-4 py-1.5 text-sm rounded-lg transition-all ${
              abaAtiva === aba.id
                ? 'bg-white text-gray-900 font-medium shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}>
            {aba.label}
            {aba.n != null && (
              <span className={`ml-1.5 text-xs px-1.5 py-0.5 rounded-full ${
                abaAtiva === aba.id ? 'bg-blue-100 text-blue-700' : 'bg-gray-200 text-gray-500'
              }`}>{aba.n}</span>
            )}
          </button>
        ))}
      </div>

      {/* Aba Itens */}
      {abaAtiva === 'itens' && (
        <>
          <input type="text" value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Buscar por produto ou lote..."
            className="w-full px-4 py-2 text-sm border border-gray-200 rounded-lg
              focus:outline-none focus:ring-2 focus:ring-blue-500" />

          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            {itemsLoading ? (
              <div className="p-8 text-center">
                <div className="animate-spin w-6 h-6 border-2 border-blue-500
                  border-t-transparent rounded-full mx-auto" />
              </div>
            ) : itemsError ? (
              <div className="p-6 text-center">
                <p className="text-sm text-red-600">{String(itemsError)}</p>
              </div>
            ) : filteredItems.length === 0 ? (
              <div className="p-8 text-center">
                <p className="text-2xl mb-2">📦</p>
                <p className="text-sm text-gray-500">Nenhum item encontrado</p>
                <p className="text-xs text-gray-400 mt-1">Cadastre itens via Nova Movimentação</p>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100">
                    {['Produto', 'Lote', 'Qtd Estoque', 'Qtd Disponível', 'Custo Unit.', 'Total', 'Status'].map(h => (
                      <th key={h} className="text-left px-4 py-3 text-xs font-medium text-gray-500">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredItems.map((item, i) => (
                    <tr key={item.id ?? i}
                      className={`border-b border-gray-50 hover:bg-gray-50 transition-colors ${
                        item.is_low_stock ? 'bg-orange-50/30' : ''
                      }`}>
                      <td className="px-4 py-3">
                        <p className="font-medium text-gray-900">
                          {item.name ?? item.code ?? item.product_id?.slice(0, 8) + '...'}
                        </p>
                        {item.category && (
                          <p className="text-xs text-gray-400 capitalize">
                            {item.category.replace(/_/g, ' ')}
                          </p>
                        )}
                        {item.is_low_stock && (
                          <span className="text-xs text-orange-600 font-medium inline-flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> Abaixo do mínimo</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-gray-600 font-mono text-xs">
                        {item.batch_number ?? '—'}
                      </td>
                      <td className="px-4 py-3 font-medium text-gray-900">
                        {item.quantity_on_hand ?? 0} {item.unit ?? ''}
                      </td>
                      <td className="px-4 py-3 text-gray-600">
                        {item.quantity_available ?? 0}
                      </td>
                      <td className="px-4 py-3 text-gray-900">{brl(item.unit_cost ?? 0)}</td>
                      <td className="px-4 py-3 font-medium text-gray-900">{brl(item.total_cost ?? 0)}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium
                          ${STATUS_STYLE[item.status] ?? 'bg-gray-100 text-gray-600'}`}>
                          {item.status ?? '—'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {/* Aba Armazéns */}
      {abaAtiva === 'armazens' && (
        <div className="grid grid-cols-2 gap-4">
          {whLoading ? (
            [1,2].map(i => <div key={i} className="h-32 bg-gray-100 rounded-xl animate-pulse" />)
          ) : warehouses.length === 0 ? (
            <div className="col-span-2 bg-gray-50 rounded-xl p-8 text-center">
              <p className="text-sm text-gray-500">Nenhum armazém cadastrado</p>
            </div>
          ) : warehouses.map((wh, i) => (
            <div key={wh.id ?? i} className="bg-white border border-gray-200 rounded-xl p-5">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <p className="font-medium text-gray-900">{wh.name}</p>
                  <p className="text-xs text-gray-500">{wh.code} · {wh.warehouse_type ?? 'Geral'}</p>
                </div>
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                  wh.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                }`}>
                  {wh.is_active ? 'Ativo' : 'Inativo'}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-3 text-sm">
                <div>
                  <p className="text-xs text-gray-400">Itens</p>
                  <p className="font-semibold text-gray-900">{wh.total_items ?? 0}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">Valor</p>
                  <p className="font-semibold text-gray-900">{brl(wh.total_value ?? 0)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">Ocupação</p>
                  <p className="font-semibold text-gray-900">{wh.occupancy_rate ?? 0}%</p>
                </div>
              </div>
              {wh.city && (
                <p className="text-xs text-gray-400 mt-2">📍 {wh.city}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Aba Movimentações */}
      {abaAtiva === 'movimentacoes' && (
        <div className="bg-gray-50 rounded-xl p-8 text-center">
          <p className="text-2xl mb-2">📋</p>
          <p className="text-sm text-gray-500">Histórico de movimentações</p>
          <p className="text-xs text-gray-400 mt-1">Use + Nova Movimentação para registrar entradas e saídas</p>
        </div>
      )}
    </div>
  )
}
