'use client'

import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { abrirPdf } from '@/lib/pdf'

interface ContaPagar {
  id: string
  descricao?: string
  description?: string
  fornecedor?: string
  supplier?: string
  supplier_name?: string
  valor?: number
  amount?: number
  net_value?: number
  balance?: number | string
  is_overdue?: boolean
  days_overdue?: number
  vencimento?: string
  due_date?: string
  status?: string
  categoria?: string
  category?: string
}

interface PayablesResponse {
  data?: ContaPagar[]
  items?: ContaPagar[]
  total?: number
  total_amount?: number
  vencendo_hoje?: number
  atrasadas?: number
  pagas?: number
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

const statusLabel: Record<string, string> = {
  pendente: 'Pendente', pending: 'Pendente',
  pago: 'Pago', paid: 'Pago',
  vencido: 'Vencido', overdue: 'Vencido',
  cancelado: 'Cancelado',
}

const statusColor: Record<string, string> = {
  pendente: 'bg-yellow-100 text-yellow-700',
  pending: 'bg-yellow-100 text-yellow-700',
  pago: 'bg-green-100 text-green-700',
  paid: 'bg-green-100 text-green-700',
  vencido: 'bg-red-100 text-red-700',
  overdue: 'bg-red-100 text-red-700',
}

// CondomÃ­nio matriz (ESCRITÃRIO) â todas as contas a pagar da empresa usam este.
const CONDOMINIO_MATRIZ = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'

export default function ContasPagarPage() {
  const [statusFilter, setStatusFilter] = useState('todos')
  const [search, setSearch] = useState('')
  const [showNew, setShowNew] = useState(false)
  const [saving, setSaving] = useState(false)
  const [formErr, setFormErr] = useState('')
  const [form, setForm] = useState({ description: '', supplier_name: '', gross_value: '', due_date: new Date().toISOString().slice(0, 10), category: '' })

  const { data, isLoading, error, refetch } = useQuery<PayablesResponse>({
    queryKey: ['payables'],
    // busca TODAS as contas; o filtro de status Ã© aplicado no cliente (o status do backend
    // tem casing/valores prÃ³prios â 'vencido' Ã© derivado de is_overdue, nÃ£o Ã© status salvo).
    queryFn: () => fetchWithAuth('/api/v1/financial/payables?page_size=500'),
    staleTime: 2 * 60 * 1000,
    retry: 1,
  })

  const { data: aging } = useQuery({
    queryKey: ['payables-aging'],
    queryFn: () => fetchWithAuth('/api/v1/financial/payables/aging'),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  })

  void aging

  const items: ContaPagar[] = data?.data ?? data?.items ?? []

  // valores vÃªm como STRING do backend (Decimal serializado) â coagir SEMPRE p/ nÃºmero,
  // senÃ£o `0 + "2890.00"` concatena ("02890.00689.00...") e toLocaleString nÃ£o formata.
  const num = (v: unknown) => { const n = Number(v ?? 0); return Number.isFinite(n) ? n : 0 }
  const brl = (v: unknown) => num(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
  const valorDe = (i: ContaPagar) => num(i.net_value ?? i.valor ?? i.amount ?? i.balance ?? 0)
  const hoje = new Date().toISOString().slice(0, 10)
  const isPago = (s?: string) => ['pago', 'paid'].includes((s ?? '').toLowerCase())
  const isVencido = (i: ContaPagar) => Boolean(i.is_overdue) && !isPago(i.status)

  // KPIs calculados dos prÃ³prios itens (o backend nÃ£o manda esses campos no topo).
  const total = items.length
  const vencendoHoje = items.filter(i => (i.vencimento ?? i.due_date)?.slice(0, 10) === hoje && !isPago(i.status)).length
  const atrasadas = items.filter(isVencido).length
  const pagas = items.filter(i => isPago(i.status)).length

  const filtered = items.filter(item => {
    const desc = (item.descricao ?? item.description ?? '').toLowerCase()
    const forn = (item.supplier_name ?? item.fornecedor ?? item.supplier ?? '').toLowerCase()
    const buscaOk = desc.includes(search.toLowerCase()) || forn.includes(search.toLowerCase())
    if (!buscaOk) return false
    if (statusFilter === 'todos') return true
    if (statusFilter === 'pago') return isPago(item.status)
    if (statusFilter === 'vencido') return isVencido(item)
    if (statusFilter === 'pendente') return !isPago(item.status) && !isVencido(item)
    return (item.status ?? '').toLowerCase() === statusFilter
  })

  // total exibido = soma dos itens FILTRADOS (bate com o que estÃ¡ na tela)
  const totalAmount = filtered.reduce((s, i) => s + valorDe(i), 0)

  const criarConta = async () => {
    setFormErr('')
    if (!form.description.trim() || !form.gross_value || !form.due_date) {
      setFormErr('Preencha descriÃ§Ã£o, valor e vencimento.'); return
    }
    if (Number(form.gross_value) <= 0) {  // FIN-05: valor > 0 (espelha a trava gt=0 do backend)
      setFormErr('O valor deve ser maior que zero.'); return
    }
    setSaving(true)
    try {
      const token = localStorage.getItem('access_token') ?? localStorage.getItem('token') ?? ''
      const res = await fetch('/api/v1/financial/payables', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          description: form.description.trim(),
          supplier_name: form.supplier_name.trim() || undefined,
          gross_value: Number(form.gross_value),
          due_date: form.due_date,
          category: form.category.trim() || undefined,
          condominio_id: CONDOMINIO_MATRIZ,
        }),
      })
      if (!res.ok) {
        const e = await res.json().catch(() => ({}))
        setFormErr(typeof e.detail === 'string' ? e.detail : 'NÃ£o foi possÃ­vel criar a conta.'); return
      }
      setShowNew(false)
      setForm({ description: '', supplier_name: '', gross_value: '', due_date: new Date().toISOString().slice(0, 10), category: '' })
      refetch()
    } catch { setFormErr('Falha ao salvar.') } finally { setSaving(false) }
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 flex items-center gap-2">
            <span>â</span> Contas a Pagar
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Gerencie todas as contas a pagar e pagamentos pendentes
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => abrirPdf('/api/v1/financial/payables/aging/pdf', { download: true, nome: 'aging_contas_pagar.pdf' })}
            className="flex items-center gap-1.5 px-4 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            ⭳ Aging PDF
          </button>
          <button
            onClick={() => refetch()}
            className="flex items-center gap-1.5 px-4 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            âº Atualizar
          </button>
          <button
            onClick={() => { setFormErr(''); setShowNew(true) }}
            className="flex items-center gap-1.5 px-4 py-2 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
          >
            + Nova Conta
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Total', value: total, color: 'text-gray-900' },
          { label: 'Vencendo Hoje', value: vencendoHoje, color: 'text-yellow-600' },
          { label: 'Atrasadas', value: atrasadas, color: 'text-red-600' },
          { label: 'Pagas', value: pagas, color: 'text-green-600' },
        ].map(card => (
          <div key={card.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <p className="text-sm text-gray-500">{card.label}</p>
            <p className={`text-3xl font-semibold mt-1 ${card.color}`}>
              {isLoading ? 'â' : card.value}
            </p>
          </div>
        ))}
      </div>

      {/* Filtros */}
      <div className="flex gap-3">
        <input
          type="text"
          placeholder="Buscar por descriÃ§Ã£o, fornecedor..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="flex-1 px-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="todos">Todos os status</option>
          <option value="pendente">Pendente</option>
          <option value="vencido">Vencido</option>
          <option value="pago">Pago</option>
        </select>
      </div>

      {/* Lista */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center">
            <div className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-2" />
            <p className="text-sm text-gray-500">Carregando contas...</p>
          </div>
        ) : error ? (
          <div className="p-8 text-center">
            <p className="text-sm text-red-600 mb-3">
              Erro ao carregar contas: {String(error)}
            </p>
            <button
              onClick={() => refetch()}
              className="px-4 py-2 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-700"
            >
              Tentar novamente
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center">
            <p className="text-2xl mb-2">â</p>
            <p className="text-sm text-gray-500">Nenhuma conta a pagar encontrada</p>
            <p className="text-xs text-gray-400 mt-1">
              Tente ajustar os filtros ou crie uma nova conta
            </p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500">DescriÃ§Ã£o</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500">Fornecedor</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500">Vencimento</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-gray-500">Valor</th>
                <th className="text-center px-4 py-3 text-xs font-medium text-gray-500">Status</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item, idx) => (
                <tr key={item.id ?? idx} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-gray-900">{item.descricao ?? item.description ?? 'â'}</td>
                  <td className="px-4 py-3 text-gray-600">{item.supplier_name ?? item.fornecedor ?? item.supplier ?? 'â'}</td>
                  <td className="px-4 py-3 text-gray-600">
                    {(item.vencimento ?? item.due_date)
                      ? new Date(`${(item.vencimento ?? item.due_date ?? '').slice(0, 10)}T00:00:00`).toLocaleDateString('pt-BR')
                      : 'â'}
                  </td>
                  <td className="px-4 py-3 text-right font-medium text-gray-900">
                    {brl(valorDe(item))}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusColor[item.status ?? ''] ?? 'bg-gray-100 text-gray-600'}`}>
                      {statusLabel[item.status ?? ''] ?? item.status ?? 'â'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Total */}
      {filtered.length > 0 && (
        <div className="flex justify-between items-center text-sm text-gray-500">
          <span>{filtered.length} conta(s) exibida(s)</span>
          <span className="font-medium text-gray-900">
            Total:{' '}
            {brl(totalAmount)}
          </span>
        </div>
      )}

      {/* Modal Nova Conta */}
      {showNew && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => setShowNew(false)}>
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-5" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Nova Conta a Pagar</h3>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">DescriÃ§Ã£o *</label>
                <input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Ex.: Energia â julho" />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">Fornecedor</label>
                <input value={form.supplier_name} onChange={e => setForm({ ...form, supplier_name: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Opcional" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Valor (R$) *</label>
                  <input type="number" step="0.01" min="0" value={form.gross_value} onChange={e => setForm({ ...form, gross_value: e.target.value })}
                    className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="0,00" />
                </div>
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Vencimento *</label>
                  <input type="date" value={form.due_date} onChange={e => setForm({ ...form, due_date: e.target.value })}
                    className="w-full border rounded-lg px-3 py-2 text-sm" />
                </div>
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">Categoria</label>
                <input value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Opcional" />
              </div>
              {formErr && <p className="text-sm text-red-600">{formErr}</p>}
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <button onClick={() => setShowNew(false)} className="px-4 py-2 text-sm border rounded-lg text-gray-700 hover:bg-gray-50">Cancelar</button>
              <button onClick={criarConta} disabled={saving}
                className="px-4 py-2 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50">
                {saving ? 'Salvandoâ¦' : 'Criar conta'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
