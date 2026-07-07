'use client'

import { useState, useEffect } from 'react'
import { FolderOpen, Link2, CheckCircle2 } from 'lucide-react'

function getToken(): string {
  if (typeof window === 'undefined') return ''
  try {
    return (
      localStorage.getItem('access_token') ||
      sessionStorage.getItem('access_token') ||
      ''
    )
  } catch {
    return ''
  }
}

interface DriveStatus {
  conectado: boolean
  email?: string
  nome?: string
  mensagem?: string
}

export default function GoogleDriveConfig() {
  const [status, setStatus] = useState<DriveStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [conectando, setConectando] = useState(false)

  useEffect(() => {
    fetch('/api/v1/gdrive/status', {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then((r) => r.json())
      .then(setStatus)
      .catch(() => setStatus({ conectado: false }))
      .finally(() => setLoading(false))
  }, [])

  const conectar = async () => {
    setConectando(true)
    try {
      const res = await fetch('/api/v1/gdrive/autorizar', {
        method: 'POST',
        headers: { Authorization: `Bearer ${getToken()}` },
      })
      const data = await res.json()
      if (data.ja_autorizado) {
        setStatus({ conectado: true })
      } else if (data.url_autorizacao) {
        window.location.href = data.url_autorizacao
      }
    } finally {
      setConectando(false)
    }
  }

  if (loading)
    return <div className="animate-pulse h-16 bg-gray-100 rounded-xl" />

  return (
    <div className="border rounded-xl p-5 bg-white">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center">
            <FolderOpen className="w-5 h-5 text-[#1E3A5F]" />
          </div>
          <div>
            <p className="font-semibold text-gray-800">Google Drive</p>
            <p className="text-sm text-gray-500">
              {status?.conectado
                ? `Conectado${status.email ? ` como ${status.email}` : ''}`
                : 'Integração para envio de kits'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full ${status?.conectado ? 'bg-green-500' : 'bg-gray-300'}`}
          />
          <span className="text-sm text-gray-500">
            {status?.conectado ? 'Conectado' : 'Desconectado'}
          </span>
        </div>
      </div>

      {!status?.conectado && (
        <button
          onClick={conectar}
          disabled={conectando}
          className="mt-4 w-full bg-[#1E3A5F] text-white py-2.5 rounded-lg text-sm font-medium hover:bg-blue-900 transition disabled:opacity-60"
        >
          {conectando ? 'Verificando...' : (
            <span className="inline-flex items-center justify-center gap-2">
              <Link2 className="w-4 h-4" /> Conectar Google Drive
            </span>
          )}
        </button>
      )}

      {status?.mensagem && (
        <p className="mt-3 text-xs text-gray-400">{status.mensagem}</p>
      )}

      {status?.conectado && (
        <p className="mt-3 text-xs text-emerald-500 inline-flex items-center gap-1">
          <CheckCircle2 className="w-3 h-3" /> Kits enviados automaticamente ao Drive após montagem.
        </p>
      )}
    </div>
  )
}
