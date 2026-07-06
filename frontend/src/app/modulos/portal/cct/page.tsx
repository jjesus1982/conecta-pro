'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Shield,
  RefreshCw,
  BookOpen,
  Calculator,
  CalendarDays,
  Moon,
  DollarSign,
  Info,
  ChevronDown,
  ChevronUp,
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

interface DireitosCCT {
  cct?: string
  cargo?: string
  salario_base?: number
  piso_salarial?: number
  adicional_noturno_percentual?: number
  adicional_periculosidade?: number
  adicional_insalubridade?: number
  vale_transporte_diario?: number
  vale_alimentacao_mensal?: number
  seguro_vida?: boolean
  plano_saude?: boolean
  jornada_semanal?: number
  horas_extras_percentual?: number
  horas_extras_noturnas_percentual?: number
}

interface CalculadoraResult {
  salario_bruto?: number
  fgts?: number
  inss?: number
  irrf?: number
  aviso_previo_dias?: number
  ferias_proporcional?: number
  decimo_terceiro_proporcional?: number
  multa_fgts?: number
  total_rescisao?: number
  detalhes?: Record<string, number>
}

interface Feriado {
  data?: string
  nome?: string
  tipo?: string
}

interface AdicionalNoturno {
  percentual?: number
  hora_inicio?: string
  hora_fim?: string
  exemplo_calculo?: string
  base_calculo?: number
  valor_adicional?: number
}

type Tab = 'direitos' | 'calculadora' | 'feriados' | 'noturno'

function formatCurrency(v?: number | null) {
  if (v === null || v === undefined) return '—'
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function formatDate(s?: string) {
  if (!s) return '—'
  try {
    return new Date(s).toLocaleDateString('pt-BR', { day: '2-digit', month: 'long', year: 'numeric' })
  } catch {
    return s
  }
}

export default function CCTPortalPage() {
  const [activeTab, setActiveTab] = useState<Tab>('direitos')
  const [direitos, setDireitos] = useState<DireitosCCT | null>(null)
  const [feriados, setFeriados] = useState<Feriado[]>([])
  const [noturno, setNoturno] = useState<AdicionalNoturno | null>(null)
  const [loading, setLoading] = useState(true)

  // Calculadora
  const [mesesTrabalhados, setMesesTrabalhados] = useState(12)
  const [tipoRescisao, setTipoRescisao] = useState('sem_justa_causa')
  const [calcResult, setCalcResult] = useState<CalculadoraResult | null>(null)
  const [calculando, setCalculando] = useState(false)
  const [calcError, setCalcError] = useState<string | null>(null)
  const [showDetalhes, setShowDetalhes] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [dirRes, ferRes, notRes] = await Promise.allSettled([
        fetch(`${API_BASE}/cct/direitos`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/cct/feriados`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/cct/adicional-noturno`, { headers: getAuthHeaders() }),
      ])
      if (dirRes.status === 'fulfilled' && dirRes.value.ok) setDireitos(await dirRes.value.json())
      if (ferRes.status === 'fulfilled' && ferRes.value.ok) {
        const d = await ferRes.value.json()
        setFeriados(Array.isArray(d) ? d : d.feriados ?? [])
      }
      if (notRes.status === 'fulfilled' && notRes.value.ok) setNoturno(await notRes.value.json())
    } catch {
      /* silencioso */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const calcularRescisao = async () => {
    setCalculando(true)
    setCalcError(null)
    try {
      const res = await fetch(`${API_BASE}/cct/calculadora`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ meses_trabalhados: mesesTrabalhados, tipo_rescisao: tipoRescisao }),
      })
      if (res.ok) {
        setCalcResult(await res.json())
      } else {
        setCalcError('Não foi possível calcular. Tente novamente.')
      }
    } catch {
      setCalcError('Erro de conexão.')
    } finally {
      setCalculando(false)
    }
  }

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

  const tabs: { key: Tab; label: string; icon: React.ElementType }[] = [
    { key: 'direitos', label: 'Direitos CCT', icon: BookOpen },
    { key: 'calculadora', label: 'Calculadora', icon: Calculator },
    { key: 'feriados', label: 'Feriados', icon: CalendarDays },
    { key: 'noturno', label: 'Adicional Noturno', icon: Moon },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-xl p-6 shadow-sm">
        <div className="flex items-center justify-between mb-2">
          <h1 className="font-display text-xl flex items-center gap-2">
            <Shield className="w-6 h-6 text-blue-600" />
            Convenção Coletiva de Trabalho
          </h1>
          <button
            onClick={loadData}
            className="flex items-center gap-1 px-3 py-1.5 text-sm bg-gray-50 text-gray-600 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <RefreshCw className="w-4 h-4" /> Atualizar
          </button>
        </div>
        {direitos?.cct && (
          <p className="text-sm text-blue-700 bg-blue-50 px-3 py-2 rounded-lg">
            Referência: <strong>{direitos.cct}</strong>
          </p>
        )}
      </div>

      {/* Tabs */}
      <div className="bg-white rounded-xl shadow-sm">
        <div className="flex flex-wrap border-b px-4 pt-3 gap-1">
          {tabs.map((tab) => (
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

        <div className="p-5">
          {/* DIREITOS */}
          {activeTab === 'direitos' && (
            <div className="space-y-4">
              {!direitos ? (
                <div className="text-center py-10">
                  <Shield className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                  <p className="text-gray-500">Informações CCT não disponíveis</p>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <DireitoCard icon={DollarSign} label="Piso Salarial (CCT)" value={formatCurrency(direitos.piso_salarial)} color="blue" />
                    <DireitoCard icon={DollarSign} label="Seu Salário Base" value={formatCurrency(direitos.salario_base)} color="green" />
                    <DireitoCard icon={Moon} label="Adicional Noturno" value={direitos.adicional_noturno_percentual ? `${direitos.adicional_noturno_percentual}%` : '—'} color="purple" />
                    <DireitoCard icon={Shield} label="Adicional Periculosidade" value={direitos.adicional_periculosidade ? `${direitos.adicional_periculosidade}%` : '—'} color="amber" />
                    <DireitoCard icon={Info} label="Vale Transporte (diário)" value={formatCurrency(direitos.vale_transporte_diario)} color="blue" />
                    <DireitoCard icon={Info} label="Vale Alimentação (mensal)" value={formatCurrency(direitos.vale_alimentacao_mensal)} color="green" />
                    <DireitoCard icon={Info} label="Jornada Semanal" value={direitos.jornada_semanal ? `${direitos.jornada_semanal}h` : '—'} color="gray" />
                    <DireitoCard icon={Info} label="Hora Extra" value={direitos.horas_extras_percentual ? `${direitos.horas_extras_percentual}%` : '—'} color="gray" />
                  </div>

                  <div className="flex flex-wrap gap-3 mt-2">
                    {direitos.seguro_vida && (
                      <span className="flex items-center gap-1.5 px-3 py-1.5 bg-green-50 text-green-700 rounded-lg text-sm font-medium">
                        <Shield className="w-4 h-4" /> Seguro de Vida
                      </span>
                    )}
                    {direitos.plano_saude && (
                      <span className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 text-blue-700 rounded-lg text-sm font-medium">
                        <Shield className="w-4 h-4" /> Plano de Saúde
                      </span>
                    )}
                  </div>

                  <div className="mt-2 p-3 bg-gray-50 rounded-lg text-xs text-gray-500 flex items-start gap-2">
                    <Info className="w-4 h-4 flex-shrink-0 mt-0.5 text-gray-400" />
                    Os direitos acima são garantidos pela CCT vigente. Em caso de dúvidas, entre em contato com o Departamento Pessoal.
                  </div>
                </>
              )}
            </div>
          )}

          {/* CALCULADORA */}
          {activeTab === 'calculadora' && (
            <div className="space-y-5">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Meses trabalhados
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={360}
                    value={mesesTrabalhados}
                    onChange={(e) => setMesesTrabalhados(Number(e.target.value))}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Tipo de rescisão
                  </label>
                  <select
                    value={tipoRescisao}
                    onChange={(e) => setTipoRescisao(e.target.value)}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="sem_justa_causa">Sem justa causa</option>
                    <option value="justa_causa">Justa causa</option>
                    <option value="pedido_demissao">Pedido de demissão</option>
                    <option value="acordo_mutuo">Acordo mútuo (art. 484-A CLT)</option>
                  </select>
                </div>
              </div>

              <button
                onClick={calcularRescisao}
                disabled={calculando}
                className="w-full py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60 transition-colors flex items-center justify-center gap-2"
              >
                <Calculator className="w-4 h-4" />
                {calculando ? 'Calculando...' : 'Calcular Rescisão'}
              </button>

              {calcError && (
                <p className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">{calcError}</p>
              )}

              {calcResult && (
                <div className="space-y-3">
                  <h3 className="font-semibold text-gray-800">Resultado estimado</h3>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { label: 'Salário Bruto', value: calcResult.salario_bruto, color: 'blue' },
                      { label: 'FGTS', value: calcResult.fgts, color: 'green' },
                      { label: 'INSS', value: calcResult.inss, color: 'amber' },
                      { label: 'IRRF', value: calcResult.irrf, color: 'red' },
                      { label: 'Aviso Prévio', value: calcResult.aviso_previo_dias ? `${calcResult.aviso_previo_dias} dias` : undefined, color: 'gray' },
                      { label: 'Férias Prop.', value: calcResult.ferias_proporcional, color: 'green' },
                      { label: '13º Prop.', value: calcResult.decimo_terceiro_proporcional, color: 'green' },
                      { label: 'Multa FGTS (40%)', value: calcResult.multa_fgts, color: 'red' },
                    ].map((item) => (
                      item.value !== undefined && (
                        <div key={item.label} className="bg-gray-50 rounded-lg p-3">
                          <p className="text-xs text-gray-500">{item.label}</p>
                          <p className="text-sm font-semibold text-gray-900">
                            {typeof item.value === 'number' ? formatCurrency(item.value) : item.value}
                          </p>
                        </div>
                      )
                    ))}
                  </div>

                  {calcResult.total_rescisao !== undefined && (
                    <div className="p-4 bg-blue-50 rounded-xl border border-blue-100">
                      <p className="text-sm text-blue-700">Total estimado da rescisão</p>
                      <p className="font-data text-2xl font-semibold tabular-nums text-blue-900">{formatCurrency(calcResult.total_rescisao)}</p>
                    </div>
                  )}

                  {calcResult.detalhes && Object.keys(calcResult.detalhes).length > 0 && (
                    <div>
                      <button
                        onClick={() => setShowDetalhes(!showDetalhes)}
                        className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
                      >
                        {showDetalhes ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        {showDetalhes ? 'Ocultar detalhes' : 'Ver detalhes'}
                      </button>
                      {showDetalhes && (
                        <div className="mt-2 space-y-1">
                          {Object.entries(calcResult.detalhes).map(([k, v]) => (
                            <div key={k} className="flex justify-between text-xs text-gray-600 px-2 py-1 bg-gray-50 rounded">
                              <span>{k.replace(/_/g, ' ')}</span>
                              <span className="font-medium">{formatCurrency(v)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  <p className="text-xs text-gray-400">
                    * Cálculo estimado com base na CCT vigente e salário registrado. Valores sujeitos a variações.
                    Para cálculo oficial, consulte o Departamento Pessoal.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* FERIADOS */}
          {activeTab === 'feriados' && (
            <div className="space-y-2">
              {feriados.length === 0 ? (
                <div className="text-center py-10">
                  <CalendarDays className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                  <p className="text-gray-500">Nenhum feriado disponível</p>
                </div>
              ) : (
                <>
                  <p className="text-xs text-gray-500 mb-3">{feriados.length} feriados encontrados</p>
                  {feriados.map((f, i) => (
                    <div key={i} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-transparent hover:border-blue-100 transition-colors">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center text-blue-700 text-xs font-bold text-center leading-tight">
                          {f.data ? new Date(f.data).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }) : '—'}
                        </div>
                        <div>
                          <p className="text-sm font-medium text-gray-800">{f.nome || '—'}</p>
                          {f.data && (
                            <p className="text-xs text-gray-500">
                              {new Date(f.data).toLocaleDateString('pt-BR', { weekday: 'long' })}
                            </p>
                          )}
                        </div>
                      </div>
                      {f.tipo && (
                        <span className={`text-xs px-2 py-0.5 rounded-full ${
                          f.tipo === 'nacional' ? 'bg-blue-100 text-blue-700'
                          : f.tipo === 'estadual' ? 'bg-green-100 text-green-700'
                          : 'bg-amber-100 text-amber-700'
                        }`}>
                          {f.tipo}
                        </span>
                      )}
                    </div>
                  ))}
                </>
              )}
            </div>
          )}

          {/* ADICIONAL NOTURNO */}
          {activeTab === 'noturno' && (
            <div className="space-y-4">
              {!noturno ? (
                <div className="text-center py-10">
                  <Moon className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                  <p className="text-gray-500">Informações não disponíveis</p>
                </div>
              ) : (
                <>
                  <div className="p-5 bg-purple-50 rounded-xl border border-purple-100">
                    <div className="flex items-center gap-2 mb-3">
                      <Moon className="w-5 h-5 text-purple-600" />
                      <span className="font-semibold text-purple-800">Adicional Noturno (CCT)</span>
                    </div>

                    <div className="grid grid-cols-2 gap-3 mb-3">
                      <div className="bg-white rounded-lg p-3">
                        <p className="text-xs text-gray-500">Percentual</p>
                        <p className="font-data text-xl font-semibold tabular-nums text-purple-700">
                          {noturno.percentual ? `${noturno.percentual}%` : '—'}
                        </p>
                      </div>
                      <div className="bg-white rounded-lg p-3">
                        <p className="text-xs text-gray-500">Período</p>
                        <p className="text-sm font-bold text-gray-800">
                          {noturno.hora_inicio || '22:00'} → {noturno.hora_fim || '05:00'}
                        </p>
                      </div>
                    </div>

                    {noturno.base_calculo !== undefined && (
                      <div className="grid grid-cols-2 gap-3 mb-3">
                        <div className="bg-white rounded-lg p-3">
                          <p className="text-xs text-gray-500">Base de cálculo</p>
                          <p className="text-sm font-semibold text-gray-800">{formatCurrency(noturno.base_calculo)}</p>
                        </div>
                        {noturno.valor_adicional !== undefined && (
                          <div className="bg-white rounded-lg p-3">
                            <p className="text-xs text-gray-500">Valor do adicional</p>
                            <p className="text-sm font-semibold text-green-700">{formatCurrency(noturno.valor_adicional)}</p>
                          </div>
                        )}
                      </div>
                    )}

                    {noturno.exemplo_calculo && (
                      <div className="mt-2 text-xs text-purple-700 bg-purple-100 px-3 py-2 rounded-lg">
                        <strong>Exemplo:</strong> {noturno.exemplo_calculo}
                      </div>
                    )}
                  </div>

                  <div className="p-3 bg-gray-50 rounded-lg text-xs text-gray-500 flex items-start gap-2">
                    <Info className="w-4 h-4 flex-shrink-0 mt-0.5 text-gray-400" />
                    O adicional noturno é pago para horas trabalhadas entre 22h e 5h, conforme a CLT e a CCT vigente.
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function DireitoCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ElementType
  label: string
  value: string
  color: 'blue' | 'green' | 'amber' | 'purple' | 'red' | 'gray'
}) {
  const colorMap = {
    blue: 'bg-blue-50 text-blue-700',
    green: 'bg-green-50 text-green-700',
    amber: 'bg-amber-50 text-amber-700',
    purple: 'bg-purple-50 text-purple-700',
    red: 'bg-red-50 text-red-700',
    gray: 'bg-gray-50 text-gray-700',
  }
  const iconMap = {
    blue: 'bg-blue-100 text-blue-600',
    green: 'bg-green-100 text-green-600',
    amber: 'bg-amber-100 text-amber-600',
    purple: 'bg-purple-100 text-purple-600',
    red: 'bg-red-100 text-red-600',
    gray: 'bg-gray-100 text-gray-500',
  }
  return (
    <div className={`flex items-center gap-3 p-3 rounded-xl ${colorMap[color]}`}>
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${iconMap[color]}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div>
        <p className="text-xs opacity-70">{label}</p>
        <p className="text-sm font-semibold">{value}</p>
      </div>
    </div>
  )
}
