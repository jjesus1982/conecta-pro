'use client'

import { useState, useEffect } from 'react'
import { FileText, Palmtree, GraduationCap, Bell, DollarSign } from 'lucide-react'
import Link from 'next/link'

const API_BASE = '/api/v1/people-management/portal'

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') || localStorage.getItem('token') : null
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

export default function PortalDashboardPage() {
  const [loading, setLoading] = useState(true)
  const [notifications, setNotifications] = useState<any[]>([])
  const [stats, setStats] = useState({ ferias_saldo: 0, contracheques: 0, treinamentos: 0 })

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch(`${API_BASE}/dashboard`, { headers: getAuthHeaders() })
        if (res.ok) {
          const data = await res.json()
          setStats(data.stats || stats)
          setNotifications(data.notifications || [])
        }
      } catch {
        // Fallback to empty state
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const cards = [
    { title: 'Último Contracheque', value: 'Ver detalhes', icon: DollarSign, href: '/modulos/portal/contracheque', color: 'bg-green-500' },
    { title: 'Saldo de Férias', value: `${stats.ferias_saldo} dias`, icon: Palmtree, href: '/modulos/portal/ferias', color: 'bg-blue-500' },
    { title: 'Treinamentos', value: `${stats.treinamentos} certificados`, icon: GraduationCap, href: '/modulos/portal/treinamentos', color: 'bg-purple-500' },
    { title: 'Notificações', value: `${notifications.length} novas`, icon: Bell, href: '/modulos/portal/notificacoes', color: 'bg-orange-500' },
  ]

  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="bg-white rounded-xl p-6 shadow-sm animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-3/4 mb-4" />
            <div className="h-8 bg-gray-200 rounded w-1/2" />
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((card) => {
          const Icon = card.icon
          return (
            <Link key={card.href} href={card.href}>
              <div className="bg-white rounded-xl p-6 shadow-sm hover:shadow-md transition-shadow cursor-pointer">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-sm font-medium text-gray-600">{card.title}</span>
                  <div className={`${card.color} p-2 rounded-lg`}>
                    <Icon className="w-5 h-5 text-white" />
                  </div>
                </div>
                <p className="text-lg font-semibold text-gray-900">{card.value}</p>
              </div>
            </Link>
          )
        })}
      </div>

      {notifications.length > 0 && (
        <div className="bg-white rounded-xl p-6 shadow-sm">
          <h2 className="font-display text-lg mb-4">Notificações Recentes</h2>
          <div className="space-y-3">
            {notifications.slice(0, 5).map((n: any, i: number) => (
              <div key={i} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
                <Bell className="w-5 h-5 text-blue-500 mt-0.5" />
                <div>
                  <p className="font-medium text-sm">{n.title}</p>
                  <p className="text-xs text-gray-500">{n.message}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
