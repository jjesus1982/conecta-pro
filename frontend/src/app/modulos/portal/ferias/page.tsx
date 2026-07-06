'use client'

import { useState, useEffect } from 'react'
import { Palmtree, Calendar } from 'lucide-react'

const API_BASE = '/api/v1/people-management/portal'

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') || localStorage.getItem('token') : null
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

export default function FeriasPortalPage() {
  const [balance, setBalance] = useState<any>(null)
  const [requests, setRequests] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const [balRes, reqRes] = await Promise.all([
          fetch(`${API_BASE}/my-vacations/balance`, { headers: getAuthHeaders() }),
          fetch(`${API_BASE}/my-vacations/requests`, { headers: getAuthHeaders() }),
        ])
        if (balRes.ok) setBalance(await balRes.json())
        if (reqRes.ok) { const data = await reqRes.json(); setRequests(data.items || data || []) }
      } catch { /* fallback */ } finally { setLoading(false) }
    }
    load()
  }, [])

  if (loading) {
    return <div className="bg-white rounded-xl p-6 shadow-sm animate-pulse"><div className="h-40 bg-gray-100 rounded" /></div>
  }

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl p-6 shadow-sm">
        <h2 className="font-display text-lg mb-4 flex items-center gap-2">
          <Palmtree className="w-5 h-5 text-green-600" />
          Saldo de Férias
        </h2>
        {balance ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-4 bg-blue-50 rounded-lg text-center">
              <p className="text-sm text-gray-600">Dias de Direito</p>
              <p className="font-data text-2xl font-semibold tabular-nums text-blue-700">{balance.dias_direito || 0}</p>
            </div>
            <div className="p-4 bg-green-50 rounded-lg text-center">
              <p className="text-sm text-gray-600">Dias Gozados</p>
              <p className="font-data text-2xl font-semibold tabular-nums text-green-700">{balance.dias_gozados || 0}</p>
            </div>
            <div className="p-4 bg-purple-50 rounded-lg text-center">
              <p className="text-sm text-gray-600">Saldo Disponível</p>
              <p className="font-data text-2xl font-semibold tabular-nums text-purple-700">{balance.dias_saldo || 0}</p>
            </div>
            <div className="p-4 bg-orange-50 rounded-lg text-center">
              <p className="text-sm text-gray-600">Valor Estimado</p>
              <p className="font-data text-2xl font-semibold tabular-nums text-orange-700">R$ {(balance.total_bruto_ferias || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</p>
            </div>
          </div>
        ) : (
          <p className="text-gray-500">Não foi possível carregar o saldo de férias</p>
        )}
      </div>

      <div className="bg-white rounded-xl p-6 shadow-sm">
        <h2 className="font-display text-lg mb-4">Solicitações de Férias</h2>
        {requests.length === 0 ? (
          <p className="text-gray-500 text-center py-4">Nenhuma solicitação de férias</p>
        ) : (
          <div className="space-y-3">
            {requests.map((r: any, i: number) => (
              <div key={i} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                <div className="flex items-center gap-3">
                  <Calendar className="w-5 h-5 text-gray-400" />
                  <div>
                    <p className="font-medium">{r.start_date} a {r.end_date}</p>
                    <p className="text-sm text-gray-500">{r.days_count || 0} dias</p>
                  </div>
                </div>
                <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                  r.status === 'approved' ? 'bg-green-100 text-green-700' :
                  r.status === 'pending' ? 'bg-yellow-100 text-yellow-700' :
                  'bg-red-100 text-red-700'
                }`}>{r.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
