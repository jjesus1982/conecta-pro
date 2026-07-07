'use client'

import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Users, CheckCircle2, Ban } from 'lucide-react'

interface Supplier {
  id: string
  code: string | null
  name: string
  trade_name: string | null
  supplier_type: string | null
  category: string | null
  status: string
  cpf_cnpj: string | null
  email: string | null
  phone: string | null
  is_qualified: boolean
  is_blocked: boolean
  rating: number | null
}

interface SupplierStats {
  total: number
  ativos: number
  bloqueados: number
  qualificados: number
}

const fetchAuth = (url: string) =>
  fetch(url, {
    headers: {
      Authorization: `Bearer ${typeof window !== 'undefined'
        ? (localStorage.getItem('access_token') ?? localStorage.getItem('token') ?? '') : ''}`,
    },
  }).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })

const STATUS_STYLE: Record<string, string> = {
  ativo:    'bg-green-100 text-green-700',
  active:   'bg-green-100 text-green-700',
  inativo:  'bg-gray-100 text-gray-600',
  inactive: 'bg-gray-100 text-gray-600',
  bloqueado:'bg-red-100 text-red-700',
  blocked:  'bg-red-100 text-red-700',
}

const STATUS_LABEL: Record<string, string> = {
  ativo: 'Ativo', active: 'Ativo',
  inativo: 'Inativo', inactive: 'Inativo',
  bloqueado: 'Bloqueado', blocked: 'Bloqueado',
}

export default function FornecedoresPage() {
  const [search, setSearch]           = useState('')
  const [statusFilter, setStatusFilter] = useState<'todos' | 'ativo' | 'bloqueado'>('todos')
  const [abaAtiva, setAbaAtiva]       = useState<'todos' | 'ativos' | 'bloqueados'>('todos')

  // Usa /financial/suppliers diretamente — 200 com 13 registros reais
  const { data: suppliers = [], isLoading, error, refetch } = useQuery<Supplier[]>({
    queryKey: ['suppliers-list'],
    queryFn: () => fetchAuth('/api/v1/financial/suppliers'),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  })

  // Stats opcionais — não bloqueia a página se falhar
  const { data: stats } = useQuery<SupplierStats>({
    queryKey: ['suppliers-stats'],
    queryFn: () => fetchAuth('/api/v1/financial/suppliers/stats'),
    staleTime: 5 * 60 * 1000,
    retry: 0,
  })

  // Cálculo de stats a partir da lista (fallback caso /stats falhe)
  const total    = stats?.total    ?? suppliers.length
  const ativos   = stats?.ativos   ?? suppliers.filter(s => s.status === 'ativo' || s.status === 'active').length
  const bloqueados = stats?.bloqueados ?? suppliers.filter(s => s.is_blocked || s.status === 'bloqueado').length

  const filtered = suppliers.filter(s => {
    const matchSearch = !search ||
      (s.name ?? '').toLowerCase().includes(search.toLowerCase()) ||
      (s.cpf_cnpj ?? '').includes(search) ||
      (s.email ?? '').toLowerCase().includes(search.toLowerCase())

    const matchStatus = abaAtiva === 'todos' ||
      (abaAtiva === 'ativos'    && (s.status === 'ativo' || s.status === 'active')) ||
      (abaAtiva === 'bloqueados' && (s.is_blocked || s.status === 'bloqueado'))

    return matchSearch && matchStatus
  })

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Fornecedores</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {isLoading ? 'Carregando...' : `${total} fornecedores cadastrados`}
          </p>
        </div>
        <button onClick={() => refetch()}
          className="flex items-center gap-1.5 px-4 py-2 text-sm border border-gray-200
            rounded-lg hover:bg-gray-50 transition-colors text-gray-600">
          ↺ Atualizar
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Total',     value: total,     icon: Users,        color: 'text-blue-600' },
          { label: 'Ativos',    value: ativos,    icon: CheckCircle2, color: 'text-emerald-600' },
          { label: 'Bloqueados',value: bloqueados, icon: Ban,         color: 'text-red-600' },
        ].map(k => (
          <div key={k.label} className="bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-4">
            <k.icon className={`w-7 h-7 ${k.color}`} />
            <div>
              <p className="text-xs text-gray-500">{k.label}</p>
              <p className={`text-3xl font-semibold ${k.color}`}>
                {isLoading ? '–' : k.value}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Busca + Abas */}
      <div className="flex gap-3">
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Buscar por nome, CNPJ/CPF ou email..."
          className="flex-1 px-4 py-2 text-sm border border-gray-200 rounded-lg
            focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <div className="flex gap-1 bg-gray-100 p-1 rounded-xl">
          {(['todos', 'ativos', 'bloqueados'] as const).map(aba => (
            <button key={aba} onClick={() => setAbaAtiva(aba)}
              className={`px-3 py-1.5 text-sm rounded-lg capitalize transition-all ${
                abaAtiva === aba
                  ? 'bg-white text-gray-900 font-medium shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}>
              {aba}
            </button>
          ))}
        </div>
      </div>

      {/* Lista */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center">
            <div className="animate-spin w-6 h-6 border-2 border-blue-500
              border-t-transparent rounded-full mx-auto mb-2" />
            <p className="text-sm text-gray-500">Carregando fornecedores...</p>
          </div>
        ) : error ? (
          <div className="p-8 text-center">
            <p className="text-sm text-red-600 mb-2">Erro: {String(error)}</p>
            <button onClick={() => refetch()}
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg">
              Tentar novamente
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center">
            <p className="text-sm text-gray-500">Nenhum fornecedor encontrado</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                {['Nome', 'CNPJ/CPF', 'Email', 'Categoria', 'Status', 'Rating'].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-medium text-gray-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((s, i) => (
                <tr key={s.id ?? i}
                  className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3">
                    <p className="font-medium text-gray-900">{s.name}</p>
                    {s.trade_name && <p className="text-xs text-gray-400">{s.trade_name}</p>}
                  </td>
                  <td className="px-4 py-3 text-gray-600 font-mono text-xs">
                    {s.cpf_cnpj ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-600">{s.email ?? '—'}</td>
                  <td className="px-4 py-3 text-gray-500 capitalize">
                    {(s.category ?? s.supplier_type ?? '—').replace(/_/g, ' ')}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium
                      ${STATUS_STYLE[s.status] ?? 'bg-gray-100 text-gray-600'}`}>
                      {STATUS_LABEL[s.status] ?? s.status ?? '—'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {s.rating != null ? (
                      <span className="flex items-center gap-0.5 text-amber-500 text-xs">
                        {'★'.repeat(Math.round(s.rating))}{'☆'.repeat(5 - Math.round(s.rating))}
                      </span>
                    ) : <span className="text-gray-300">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {filtered.length > 0 && (
        <p className="text-xs text-gray-400 text-right">
          {filtered.length} de {suppliers.length} fornecedores exibidos
        </p>
      )}
    </div>
  )
}
