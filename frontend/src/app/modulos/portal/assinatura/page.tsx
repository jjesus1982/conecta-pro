'use client'

import { useState, useCallback, useEffect } from 'react'
import { msgFromDetail } from '@/lib/string';
import {
  PenLine,
  ShieldCheck,
  ShieldX,
  Search,
  RefreshCw,
  FileText,
  CheckCircle2,
  Clock,
  AlertCircle,
  Eye,
  Hash,
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

interface DocumentItem {
  document_id: number | string
  document_type: string
  signed: boolean
  signed_at?: string
  signature_valid?: boolean
}

interface VerifyResult {
  is_valid: boolean
  document_id?: number
  document_type?: string
  employee_id?: string
  signed_at?: string
  invalidation_reason?: string
}

const DOC_TYPE_LABELS: Record<string, string> = {
  warning: 'Advertência',
  suspension: 'Suspensão',
  payslip: 'Contracheque',
  contract: 'Contrato',
  vacation: 'Férias',
  policy: 'Política',
  training_certificate: 'Certificado de Treinamento',
  other: 'Outro',
}

export default function AssinaturaPortalPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [signingId, setSigningId] = useState<number | string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [verifyHash, setVerifyHash] = useState('')
  const [verifyResult, setVerifyResult] = useState<VerifyResult | null>(null)
  const [verifying, setVerifying] = useState(false)
  const [activeTab, setActiveTab] = useState<'pendentes' | 'assinados' | 'verificar'>('pendentes')
  const [toast, setToast] = useState<{ msg: string; type: 'success' | 'error' } | null>(null)

  const showToast = (msg: string, type: 'success' | 'error' = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 4000)
  }

  const loadDocuments = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/my-documents`, { headers: getAuthHeaders() })
      if (res.ok) {
        const data = await res.json()
        setDocuments(Array.isArray(data) ? data : data.items || [])
      }
    } catch {
      /* silencioso */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadDocuments()
  }, [loadDocuments])

  const handleSign = async (doc: DocumentItem) => {
    setSigningId(doc.document_id)
    try {
      const res = await fetch(`${API_BASE}/my-documents/${doc.document_id}/sign`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          document_id: doc.document_id,
          document_type: doc.document_type || 'other',
        }),
      })

      if (res.ok) {
        showToast('Documento assinado com sucesso!')
        loadDocuments()
      } else {
        const err = await res.json().catch(() => ({}))
        showToast(msgFromDetail(err.detail) || 'Erro ao assinar documento.', 'error')
      }
    } catch {
      showToast('Erro de conexão ao assinar.', 'error')
    } finally {
      setSigningId(null)
    }
  }

  const handleVerify = async () => {
    if (!verifyHash.trim()) return
    setVerifying(true)
    setVerifyResult(null)
    try {
      const res = await fetch(
        `${API_BASE}/my-documents/0/verify-signature?signature_hash=${encodeURIComponent(verifyHash.trim())}`,
        { headers: getAuthHeaders() }
      )
      if (res.ok) {
        setVerifyResult(await res.json())
      } else {
        const err = await res.json().catch(() => ({}))
        showToast(msgFromDetail(err.detail) || 'Erro ao verificar assinatura.', 'error')
      }
    } catch {
      showToast('Erro de conexão ao verificar.', 'error')
    } finally {
      setVerifying(false)
    }
  }

  const pendentes = documents.filter((d) => !d.signed)
  const assinados = documents.filter((d) => d.signed)

  const filteredPendentes = pendentes.filter((d) => {
    if (!searchQuery) return true
    const label = DOC_TYPE_LABELS[d.document_type] || d.document_type
    return label.toLowerCase().includes(searchQuery.toLowerCase())
  })

  const filteredAssinados = assinados.filter((d) => {
    if (!searchQuery) return true
    const label = DOC_TYPE_LABELS[d.document_type] || d.document_type
    return label.toLowerCase().includes(searchQuery.toLowerCase())
  })

  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-xl p-6 shadow-sm animate-pulse">
            <div className="h-5 bg-gray-100 rounded w-1/3 mb-3" />
            <div className="h-16 bg-gray-50 rounded" />
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Toast */}
      {toast && (
        <div
          className={`fixed top-4 right-4 z-50 flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg text-white text-sm font-medium transition-all ${
            toast.type === 'success' ? 'bg-green-600' : 'bg-red-600'
          }`}
        >
          {toast.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4" />
          ) : (
            <AlertCircle className="w-4 h-4" />
          )}
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <div className="bg-white rounded-xl p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-bold flex items-center gap-2">
            <PenLine className="w-6 h-6 text-blue-600" />
            Assinatura Digital
          </h1>
          <button
            onClick={loadDocuments}
            className="flex items-center gap-1 px-3 py-1.5 text-sm bg-gray-50 text-gray-600 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <RefreshCw className="w-4 h-4" /> Atualizar
          </button>
        </div>

        {/* Estatísticas */}
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-amber-50 rounded-lg p-3 text-center">
            <p className="font-data text-2xl font-semibold tabular-nums text-amber-600">{pendentes.length}</p>
            <p className="text-xs text-amber-500">Pendentes de Assinatura</p>
          </div>
          <div className="bg-green-50 rounded-lg p-3 text-center">
            <p className="font-data text-2xl font-semibold tabular-nums text-green-600">{assinados.length}</p>
            <p className="text-xs text-green-500">Documentos Assinados</p>
          </div>
          <div className="bg-blue-50 rounded-lg p-3 text-center">
            <p className="font-data text-2xl font-semibold tabular-nums text-blue-600">{documents.length}</p>
            <p className="text-xs text-blue-500">Total de Documentos</p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="bg-white rounded-xl shadow-sm">
        <div className="flex items-center justify-between border-b px-4 pt-3">
          <div className="flex gap-1">
            {([
              { key: 'pendentes', label: 'Pendentes', icon: Clock },
              { key: 'assinados', label: 'Assinados', icon: ShieldCheck },
              { key: 'verificar', label: 'Verificar Hash', icon: Hash },
            ] as const).map((tab) => (
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
                {tab.key === 'pendentes' && pendentes.length > 0 && (
                  <span className="ml-1 bg-amber-500 text-white text-xs rounded-full px-1.5 py-0.5 leading-none">
                    {pendentes.length}
                  </span>
                )}
              </button>
            ))}
          </div>

          {activeTab !== 'verificar' && (
            <div className="relative pb-2">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400" />
              <input
                type="text"
                placeholder="Filtrar tipo..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-3 py-2 text-sm border rounded-lg w-44 focus:ring-2 focus:ring-blue-200 focus:border-blue-400 outline-none"
              />
            </div>
          )}
        </div>

        <div className="p-4">
          {/* Tab: Pendentes */}
          {activeTab === 'pendentes' && (
            <div className="space-y-2">
              {filteredPendentes.length === 0 ? (
                <div className="text-center py-12">
                  <CheckCircle2 className="w-12 h-12 text-green-300 mx-auto mb-3" />
                  <p className="text-gray-500 font-medium">Nenhum documento pendente</p>
                  <p className="text-sm text-gray-400 mt-1">
                    Todos os documentos foram assinados ou nenhum foi disponibilizado ainda.
                  </p>
                </div>
              ) : (
                filteredPendentes.map((doc) => (
                  <div
                    key={doc.document_id}
                    className="flex items-center justify-between p-4 bg-amber-50 rounded-lg border border-amber-100"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
                        <FileText className="w-5 h-5 text-amber-600" />
                      </div>
                      <div>
                        <p className="font-medium text-sm text-gray-800">
                          {DOC_TYPE_LABELS[doc.document_type] || doc.document_type}
                        </p>
                        <p className="text-xs text-gray-500 flex items-center gap-1 mt-0.5">
                          <Clock className="w-3 h-3" /> Aguardando assinatura
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={() => handleSign(doc)}
                      disabled={signingId === doc.document_id}
                      className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
                    >
                      <PenLine className="w-4 h-4" />
                      {signingId === doc.document_id ? 'Assinando...' : 'Assinar'}
                    </button>
                  </div>
                ))
              )}
            </div>
          )}

          {/* Tab: Assinados */}
          {activeTab === 'assinados' && (
            <div className="space-y-2">
              {filteredAssinados.length === 0 ? (
                <div className="text-center py-12">
                  <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                  <p className="text-gray-500">Nenhum documento assinado ainda</p>
                </div>
              ) : (
                filteredAssinados.map((doc) => (
                  <div
                    key={doc.document_id}
                    className="flex items-center justify-between p-4 bg-green-50 rounded-lg border border-green-100"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                        <ShieldCheck className="w-5 h-5 text-green-600" />
                      </div>
                      <div>
                        <p className="font-medium text-sm text-gray-800">
                          {DOC_TYPE_LABELS[doc.document_type] || doc.document_type}
                        </p>
                        <div className="flex items-center gap-3 mt-0.5">
                          {doc.signed_at && (
                            <p className="text-xs text-gray-500">
                              Assinado em{' '}
                              {new Date(doc.signed_at).toLocaleDateString('pt-BR', {
                                day: '2-digit',
                                month: '2-digit',
                                year: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </p>
                          )}
                          {doc.signature_valid === false && (
                            <span className="text-xs text-red-600 flex items-center gap-1">
                              <ShieldX className="w-3 h-3" /> Assinatura inválida
                            </span>
                          )}
                          {doc.signature_valid === true && (
                            <span className="text-xs text-green-600 flex items-center gap-1">
                              <ShieldCheck className="w-3 h-3" /> Válida
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <span className="flex items-center gap-1 text-xs text-green-700 bg-green-100 px-3 py-1.5 rounded-lg">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Assinado
                    </span>
                  </div>
                ))
              )}
            </div>
          )}

          {/* Tab: Verificar Hash */}
          {activeTab === 'verificar' && (
            <div className="space-y-4 max-w-xl">
              <p className="text-sm text-gray-600">
                Insira o hash SHA-256 de uma assinatura digital para verificar sua autenticidade.
              </p>

              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Hash className="w-4 h-4 absolute left-3 top-3 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Cole o hash da assinatura aqui..."
                    value={verifyHash}
                    onChange={(e) => setVerifyHash(e.target.value)}
                    className="w-full pl-9 pr-3 py-2.5 text-sm border rounded-lg focus:ring-2 focus:ring-blue-200 focus:border-blue-400 outline-none font-mono"
                  />
                </div>
                <button
                  onClick={handleVerify}
                  disabled={verifying || !verifyHash.trim()}
                  className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
                >
                  <Eye className="w-4 h-4" />
                  {verifying ? 'Verificando...' : 'Verificar'}
                </button>
              </div>

              {verifyResult && (
                <div
                  className={`p-4 rounded-lg border ${
                    verifyResult.is_valid
                      ? 'bg-green-50 border-green-200'
                      : 'bg-red-50 border-red-200'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-3">
                    {verifyResult.is_valid ? (
                      <ShieldCheck className="w-5 h-5 text-green-600" />
                    ) : (
                      <ShieldX className="w-5 h-5 text-red-600" />
                    )}
                    <span
                      className={`font-semibold ${
                        verifyResult.is_valid ? 'text-green-800' : 'text-red-800'
                      }`}
                    >
                      {verifyResult.is_valid ? 'Assinatura Válida' : 'Assinatura Inválida'}
                    </span>
                  </div>

                  <div className="space-y-1 text-sm">
                    {verifyResult.document_type && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">Tipo do documento:</span>
                        <span className="font-medium">
                          {DOC_TYPE_LABELS[verifyResult.document_type] || verifyResult.document_type}
                        </span>
                      </div>
                    )}
                    {verifyResult.signed_at && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">Data da assinatura:</span>
                        <span className="font-medium">
                          {new Date(verifyResult.signed_at).toLocaleString('pt-BR')}
                        </span>
                      </div>
                    )}
                    {verifyResult.employee_id && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">Assinado por (ID):</span>
                        <span className="font-mono text-xs">{verifyResult.employee_id}</span>
                      </div>
                    )}
                    {verifyResult.invalidation_reason && (
                      <div className="mt-2 p-2 bg-red-100 rounded text-red-700 text-xs">
                        Motivo: {verifyResult.invalidation_reason}
                      </div>
                    )}
                  </div>
                </div>
              )}

              <div className="mt-4 p-3 bg-blue-50 rounded-lg border border-blue-100">
                <p className="text-xs text-blue-700 flex items-start gap-2">
                  <ShieldCheck className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  As assinaturas digitais do Conecta PRO utilizam hash SHA-256 e são geradas com
                  timestamp único, identificação do funcionário e chave segura do servidor, garantindo
                  integridade e não-repúdio.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
