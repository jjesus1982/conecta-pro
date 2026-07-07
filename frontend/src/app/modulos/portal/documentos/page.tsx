'use client'

import { useState, useEffect, useCallback } from 'react'
import { FolderOpen, Download, FileText, Search, Filter, Calendar, Shield, FileCheck, AlertCircle, RefreshCw } from 'lucide-react'

const API_BASE = '/api/v1/people-management/portal'
const GED_INTEGRATION = '/api/v1/ged/ged-integration'

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') || localStorage.getItem('token') : null
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

interface DocumentItem {
  id: string | number
  name?: string
  title?: string
  type?: string
  category?: string
  created_at?: string
  download_url?: string
  signed?: boolean
  status?: string
}

type TabKey = 'todos' | 'contracheques' | 'cct' | 'comunicados'

const TABS: { key: TabKey; label: string; icon: typeof FileText }[] = [
  { key: 'todos', label: 'Todos', icon: FolderOpen },
  { key: 'contracheques', label: 'Contracheques', icon: FileCheck },
  { key: 'cct', label: 'CCT 2026', icon: Shield },
  { key: 'comunicados', label: 'Comunicados', icon: AlertCircle },
]

export default function DocumentosPortalPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [cctData, setCctData] = useState<Record<string, unknown> | null>(null)
  const [comunicados, setComunicados] = useState<Record<string, unknown>[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<TabKey>('todos')
  const [searchQuery, setSearchQuery] = useState('')

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [docsRes, cctRes, comRes] = await Promise.allSettled([
        fetch(`${API_BASE}/my-documents`, { headers: getAuthHeaders() }),
        fetch(`${GED_INTEGRATION}/institucional/cct`),
        fetch(`${GED_INTEGRATION}/institucional/comunicados`),
      ])

      if (docsRes.status === 'fulfilled' && docsRes.value.ok) {
        const data = await docsRes.value.json()
        setDocuments(data.items || data || [])
      }
      if (cctRes.status === 'fulfilled' && cctRes.value.ok) {
        setCctData(await cctRes.value.json())
      }
      if (comRes.status === 'fulfilled' && comRes.value.ok) {
        const comData = await comRes.value.json()
        setComunicados(comData.comunicados || comData || [])
      }
    } catch {
      /* silencioso */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const filteredDocs = documents.filter((doc) => {
    if (!searchQuery) return true
    const q = searchQuery.toLowerCase()
    return (doc.name || doc.title || '').toLowerCase().includes(q) ||
           (doc.type || '').toLowerCase().includes(q)
  })

  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-xl p-6 shadow-sm animate-pulse">
            <div className="h-6 bg-gray-100 rounded w-1/3 mb-3" />
            <div className="h-20 bg-gray-50 rounded" />
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-xl p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-bold flex items-center gap-2">
            <FolderOpen className="w-6 h-6 text-blue-600" />
            Meus Documentos
          </h1>
          <button
            onClick={loadData}
            className="flex items-center gap-1 px-3 py-1.5 text-sm bg-gray-50 text-gray-600 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <RefreshCw className="w-4 h-4" /> Atualizar
          </button>
        </div>

        {/* Estatisticas */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="bg-blue-50 rounded-lg p-3 text-center">
            <p className="font-data text-2xl font-semibold tabular-nums text-blue-600">{documents.length}</p>
            <p className="text-xs text-blue-500">Total de Documentos</p>
          </div>
          <div className="bg-green-50 rounded-lg p-3 text-center">
            <p className="font-data text-2xl font-semibold tabular-nums text-green-600">
              {documents.filter((d) => d.signed).length}
            </p>
            <p className="text-xs text-green-500">Assinados</p>
          </div>
          <div className="bg-amber-50 rounded-lg p-3 text-center">
            <p className="font-data text-2xl font-semibold tabular-nums text-amber-600">{comunicados.length}</p>
            <p className="text-xs text-amber-500">Comunicados</p>
          </div>
          <div className="bg-purple-50 rounded-lg p-3 text-center">
            <p className="font-data text-2xl font-semibold tabular-nums text-purple-600">{cctData ? 1 : 0}</p>
            <p className="text-xs text-purple-500">CCT Vigente</p>
          </div>
        </div>
      </div>

      {/* Tabs + Search */}
      <div className="bg-white rounded-xl shadow-sm">
        <div className="flex items-center justify-between border-b px-4 pt-3">
          <div className="flex gap-1">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
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
          <div className="relative pb-2">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400" />
            <input
              type="text"
              placeholder="Buscar documento..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 pr-3 py-2 text-sm border rounded-lg w-48 focus:ring-2 focus:ring-blue-200 focus:border-blue-400 outline-none"
            />
          </div>
        </div>

        <div className="p-4">
          {/* Tab: Todos / Contracheques */}
          {(activeTab === 'todos' || activeTab === 'contracheques') && (
            <>
              {filteredDocs.length === 0 ? (
                <div className="text-center py-12">
                  <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                  <p className="text-gray-500">Nenhum documento disponivel</p>
                  <p className="text-sm text-gray-400 mt-1">
                    Seus contracheques e documentos aparecerao aqui quando estiverem disponiveis
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {filteredDocs.map((doc, i) => (
                    <div
                      key={doc.id || i}
                      className="flex items-center justify-between p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                          doc.signed ? 'bg-green-100' : 'bg-blue-100'
                        }`}>
                          {doc.signed ? (
                            <FileCheck className="w-5 h-5 text-green-600" />
                          ) : (
                            <FileText className="w-5 h-5 text-blue-600" />
                          )}
                        </div>
                        <div>
                          <p className="font-medium text-sm">{doc.name || doc.title}</p>
                          <div className="flex items-center gap-2 mt-0.5">
                            {doc.type && (
                              <span className="text-xs bg-gray-200 text-gray-600 px-2 py-0.5 rounded">
                                {doc.type}
                              </span>
                            )}
                            {doc.created_at && (
                              <span className="text-xs text-gray-400 flex items-center gap-1">
                                <Calendar className="w-3 h-3" />
                                {new Date(doc.created_at).toLocaleDateString('pt-BR')}
                              </span>
                            )}
                            {doc.signed && (
                              <span className="text-xs text-green-600 flex items-center gap-1">
                                <Shield className="w-3 h-3" /> Assinado
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      {doc.download_url && (
                        <a
                          href={doc.download_url}
                          className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-100 transition-colors"
                        >
                          <Download className="w-4 h-4" /> Baixar
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {/* Tab: CCT 2026 */}
          {activeTab === 'cct' && (
            <div className="space-y-4">
              {cctData ? (
                <>
                  <div className="bg-purple-50 rounded-lg p-4">
                    <h3 className="font-semibold text-purple-800 mb-2 flex items-center gap-2">
                      <Shield className="w-5 h-5" />
                      {(cctData as Record<string, unknown>).cct_vigente as string || 'CCT 2026'}
                    </h3>
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <span className="text-gray-500">Sindicato Empregados:</span>
                        <p className="font-medium">{(cctData as Record<string, unknown>).sindicato_empregados as string || '-'}</p>
                      </div>
                      <div>
                        <span className="text-gray-500">Sindicato Patronal:</span>
                        <p className="font-medium">{(cctData as Record<string, unknown>).sindicato_patronal as string || '-'}</p>
                      </div>
                      <div>
                        <span className="text-gray-500">Vigencia:</span>
                        <p className="font-medium">
                          {((cctData as Record<string, unknown>).vigencia as Record<string, string>)?.inicio || '-'} a{' '}
                          {((cctData as Record<string, unknown>).vigencia as Record<string, string>)?.fim || '-'}
                        </p>
                      </div>
                    </div>
                  </div>
                  {Array.isArray((cctData as Record<string, unknown>).cargos) && (
                    <div>
                      <h4 className="font-semibold mb-2 text-sm text-gray-700">Pisos Salariais CCT 2026</h4>
                      <div className="space-y-1">
                        {((cctData as Record<string, unknown>).cargos as Record<string, unknown>[]).map((cargo, i) => (
                          <div key={i} className="flex justify-between items-center p-2 bg-gray-50 rounded text-sm">
                            <span>{(cargo.nome_cargo || cargo.nome) as string}</span>
                            <span className="font-medium">
                              {parseFloat(String(cargo.salario_base || cargo.piso || 0)) > 0
                                ? `R$ ${parseFloat(String(cargo.salario_base || cargo.piso || 0)).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`
                                : '-'}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-center py-8">
                  <Shield className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                  <p className="text-gray-500">CCT 2026 nao disponivel</p>
                </div>
              )}
            </div>
          )}

          {/* Tab: Comunicados */}
          {activeTab === 'comunicados' && (
            <div className="space-y-3">
              {comunicados.length === 0 ? (
                <div className="text-center py-8">
                  <AlertCircle className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                  <p className="text-gray-500">Nenhum comunicado disponivel</p>
                </div>
              ) : (
                comunicados.map((com, i) => (
                  <div key={i} className="p-4 bg-amber-50 rounded-lg border border-amber-100">
                    <div className="flex items-start justify-between">
                      <div>
                        <h4 className="font-medium text-amber-800">{String(com.titulo || '')}</h4>
                        <p className="text-sm text-amber-600 mt-1 flex items-center gap-1">
                          <Calendar className="w-3 h-3" />
                          {String(com.data || '')}
                          {com.tipo ? (
                            <span className="ml-2 px-2 py-0.5 bg-amber-200 text-amber-700 rounded text-xs">
                              {String(com.tipo)}
                            </span>
                          ) : null}
                        </p>
                      </div>
                      {(com.visivel_portal as boolean) && (
                        <span className="text-xs bg-green-100 text-green-600 px-2 py-0.5 rounded">
                          Visivel
                        </span>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
