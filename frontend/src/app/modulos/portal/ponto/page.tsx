'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Clock,
  Calendar,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Minus,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  CheckCircle2,
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

interface PontoRegistro {
  data?: string
  entrada?: string
  saida?: string
  horas_trabalhadas?: number
  status?: string
  justificativa?: string
}

interface PontoHistorico {
  employee_id?: string
  mes?: number
  ano?: number
  total_registros?: number
  registros?: PontoRegistro[]
}

interface BancoHoras {
  employee_id?: string
  saldo_horas?: number
  total_entradas?: number
  ultimas_entradas?: Array<{
    data?: string
    horas?: number
    tipo?: string
    descricao?: string
  }>
}

const MESES = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
]

export default function PontoPortalPage() {
  const now = new Date()
  const [mes, setMes] = useState(now.getMonth() + 1)
  const [ano, setAno] = useState(now.getFullYear())
  const [historico, setHistorico] = useState<PontoHistorico | null>(null)
  const [bancoHoras, setBancoHoras] = useState<BancoHoras | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'historico' | 'banco'>('historico')

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [pontoRes, bancoRes] = await Promise.allSettled([
        fetch(`${API_BASE}/ponto/historico?mes=${mes}&ano=${ano}`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/banco-horas`, { headers: getAuthHeaders() }),
      ])

      if (pontoRes.status === 'fulfilled' && pontoRes.value.ok) {
        setHistorico(await pontoRes.value.json())
      }
      if (bancoRes.status === 'fulfilled' && bancoRes.value.ok) {
        setBancoHoras(await bancoRes.value.json())
      }
    } catch {
      /* silencioso */
    } finally {
      setLoading(false)
    }
  }, [mes, ano])

  useEffect(() => { loadData() }, [loadData])

  const navMes = (dir: -1 | 1) => {
    let newMes = mes + dir
    let newAno = ano
    if (newMes < 1) { newMes = 12; newAno -= 1 }
    if (newMes > 12) { newMes = 1; newAno += 1 }
    if (newAno < 2020 || newAno > 2030) return
    setMes(newMes)
    setAno(newAno)
  }

  const saldo = bancoHoras?.saldo_horas ?? 0

  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2].map((i) => (
          <div key={i} className="bg-white rounded-xl p-6 shadow-sm animate-pulse">
            <div className="h-5 bg-gray-100 rounded w-1/3 mb-4" />
            <div className="h-32 bg-gray-50 rounded" />
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header com saldo do banco de horas */}
      <div className="bg-white rounded-xl p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Clock className="w-6 h-6 text-blue-600" />
            Ponto Eletrônico
          </h1>
          <button
            onClick={loadData}
            className="flex items-center gap-1 px-3 py-1.5 text-sm bg-gray-50 text-gray-600 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <RefreshCw className="w-4 h-4" /> Atualizar
          </button>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div className={`rounded-lg p-4 text-center ${
            saldo > 0 ? 'bg-green-50' : saldo < 0 ? 'bg-red-50' : 'bg-gray-50'
          }`}>
            <div className="flex justify-center mb-1">
              {saldo > 0
                ? <TrendingUp className="w-5 h-5 text-green-600" />
                : saldo < 0
                  ? <TrendingDown className="w-5 h-5 text-red-600" />
                  : <Minus className="w-5 h-5 text-gray-500" />}
            </div>
            <p className={`font-data text-2xl font-semibold tabular-nums ${
              saldo > 0 ? 'text-green-600' : saldo < 0 ? 'text-red-600' : 'text-gray-600'
            }`}>
              {saldo >= 0 ? '+' : ''}{saldo.toFixed(1)}h
            </p>
            <p className={`text-xs mt-0.5 ${
              saldo > 0 ? 'text-green-500' : saldo < 0 ? 'text-red-500' : 'text-gray-500'
            }`}>
              Saldo Banco de Horas
            </p>
          </div>
          <div className="bg-blue-50 rounded-lg p-4 text-center">
            <p className="font-data text-2xl font-semibold tabular-nums text-blue-600">{historico?.total_registros ?? 0}</p>
            <p className="text-xs text-blue-500 mt-0.5">Registros no Mês</p>
          </div>
          <div className="bg-purple-50 rounded-lg p-4 text-center">
            <p className="font-data text-2xl font-semibold tabular-nums text-purple-600">{bancoHoras?.total_entradas ?? 0}</p>
            <p className="text-xs text-purple-500 mt-0.5">Total Lançamentos</p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="bg-white rounded-xl shadow-sm">
        <div className="flex border-b px-4 pt-3">
          {([
            { key: 'historico', label: 'Histórico de Ponto', icon: Calendar },
            { key: 'banco', label: 'Banco de Horas', icon: Clock },
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
          {/* Tab: Histórico */}
          {activeTab === 'historico' && (
            <>
              {/* Navegação mes/ano */}
              <div className="flex items-center justify-between mb-4">
                <button
                  onClick={() => navMes(-1)}
                  className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  <ChevronLeft className="w-5 h-5 text-gray-600" />
                </button>
                <span className="font-semibold text-gray-800">
                  {MESES[mes - 1]} {ano}
                </span>
                <button
                  onClick={() => navMes(1)}
                  disabled={mes === now.getMonth() + 1 && ano === now.getFullYear()}
                  className="p-1.5 rounded-lg hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronRight className="w-5 h-5 text-gray-600" />
                </button>
              </div>

              {!historico || (historico.registros?.length ?? 0) === 0 ? (
                <div className="text-center py-12">
                  <Clock className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                  <p className="text-gray-500">Nenhum registro de ponto neste mês</p>
                  <p className="text-sm text-gray-400 mt-1">
                    Os registros aparecerão aqui conforme forem lançados.
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {historico.registros!.map((reg, i) => (
                    <div key={i} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                      <div className="flex items-center gap-3">
                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                          reg.status === 'ok' || reg.status === 'normal'
                            ? 'bg-green-100'
                            : 'bg-amber-100'
                        }`}>
                          {reg.status === 'ok' || reg.status === 'normal'
                            ? <CheckCircle2 className="w-4 h-4 text-green-600" />
                            : <AlertCircle className="w-4 h-4 text-amber-600" />}
                        </div>
                        <div>
                          <p className="text-sm font-medium text-gray-800">
                            {reg.data ? new Date(reg.data).toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit' }) : '—'}
                          </p>
                          {reg.justificativa && (
                            <p className="text-xs text-amber-600">{reg.justificativa}</p>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-sm text-right">
                        <span className="text-gray-500">
                          {reg.entrada || '—'} → {reg.saida || '—'}
                        </span>
                        {reg.horas_trabalhadas !== undefined && (
                          <span className="font-semibold text-gray-800 w-14 text-right">
                            {reg.horas_trabalhadas.toFixed(1)}h
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {/* Tab: Banco de Horas */}
          {activeTab === 'banco' && (
            <div className="space-y-4">
              <div className={`p-4 rounded-xl border ${
                saldo > 0
                  ? 'bg-green-50 border-green-200'
                  : saldo < 0
                    ? 'bg-red-50 border-red-200'
                    : 'bg-gray-50 border-gray-200'
              }`}>
                <p className="text-sm text-gray-600 mb-1">Saldo atual do banco de horas</p>
                <p className={`font-data text-3xl font-semibold tabular-nums ${
                  saldo > 0 ? 'text-green-700' : saldo < 0 ? 'text-red-700' : 'text-gray-700'
                }`}>
                  {saldo >= 0 ? '+' : ''}{saldo.toFixed(2)}h
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  {saldo > 0
                    ? 'Você tem horas a favor — podem ser compensadas ou pagas'
                    : saldo < 0
                      ? 'Você tem horas a recuperar'
                      : 'Banco de horas zerado'}
                </p>
              </div>

              {(bancoHoras?.ultimas_entradas?.length ?? 0) > 0 ? (
                <div>
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">Últimos lançamentos</h3>
                  <div className="space-y-2">
                    {bancoHoras!.ultimas_entradas!.map((entrada, i) => (
                      <div key={i} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                        <div>
                          <p className="text-sm font-medium text-gray-800">
                            {entrada.descricao || entrada.tipo || 'Lançamento'}
                          </p>
                          {entrada.data && (
                            <p className="text-xs text-gray-500">
                              {new Date(entrada.data).toLocaleDateString('pt-BR')}
                            </p>
                          )}
                        </div>
                        <span className={`font-semibold text-sm ${
                          (entrada.horas ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'
                        }`}>
                          {(entrada.horas ?? 0) >= 0 ? '+' : ''}{(entrada.horas ?? 0).toFixed(1)}h
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="text-center py-8">
                  <Clock className="w-10 h-10 text-gray-300 mx-auto mb-2" />
                  <p className="text-gray-500 text-sm">Nenhum lançamento no banco de horas</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
