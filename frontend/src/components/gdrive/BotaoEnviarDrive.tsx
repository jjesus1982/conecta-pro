'use client'

import { useState } from 'react'
import { FolderOpen, CheckCircle2, XCircle, Mail } from 'lucide-react'

interface Props {
  clienteId: string
  clienteNome: string
  competencia: string
  onConcluido?: (shareLink: string) => void
}

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

type Etapa = 'idle' | 'montando' | 'enviando_email' | 'concluido' | 'erro'

export default function BotaoEnviarDrive({
  clienteId,
  clienteNome,
  competencia,
  onConcluido,
}: Props) {
  const [etapa, setEtapa] = useState<Etapa>('idle')
  const [resultado, setResultado] = useState<{
    share_link?: string
    email?: { sucesso: boolean; destinatario?: string }
    erro?: string
  } | null>(null)

  const executar = async () => {
    setEtapa('montando')
    setResultado(null)

    try {
      const res = await fetch(
        `/api/v1/gdrive/kits/${clienteId}/${competencia}/montar-e-enviar`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${getToken()}`,
            'Content-Type': 'application/json',
          },
        },
      )

      const data = await res.json()

      if (!res.ok || !data.drive?.sucesso) {
        if (data.drive?.acao?.includes('autorizar')) {
          setEtapa('erro')
          setResultado({
            erro:
              'Google Drive não conectado. Vá em Configurações GED → Conectar Google Drive.',
          })
          return
        }
        throw new Error(data.drive?.erro || data.detail || 'Erro ao enviar ao Drive')
      }

      setEtapa('concluido')
      setResultado({ share_link: data.share_link, email: data.email })
      if (data.share_link && onConcluido) onConcluido(data.share_link)
    } catch (e: unknown) {
      setEtapa('erro')
      setResultado({ erro: e instanceof Error ? e.message : 'Erro desconhecido' })
    }
  }

  const resetar = () => {
    setEtapa('idle')
    setResultado(null)
  }

  if (etapa === 'idle')
    return (
      <button
        onClick={executar}
        title={`Enviar kit ${clienteNome} ao Google Drive`}
        className="flex items-center gap-2 border-2 border-[#1E3A5F] bg-white text-[#1E3A5F] px-4 py-2 rounded-lg text-sm font-medium hover:bg-[#1E3A5F] hover:text-white transition-all"
      >
        <FolderOpen className="w-4 h-4" />
        <span>Enviar ao Drive</span>
      </button>
    )

  if (etapa === 'montando')
    return (
      <div className="flex items-center gap-2 text-[#1E3A5F] text-sm">
        <div className="w-4 h-4 border-2 border-[#1E3A5F] border-t-transparent rounded-full animate-spin" />
        <span>Enviando ao Drive...</span>
      </div>
    )

  if (etapa === 'concluido' && resultado)
    return (
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <span className="text-emerald-500 text-sm font-medium inline-flex items-center gap-1">
            <CheckCircle2 className="w-4 h-4" /> Kit no Drive
          </span>
          {resultado.share_link && (
            <a
              href={resultado.share_link}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#F97316] text-sm underline"
            >
              Abrir pasta ↗
            </a>
          )}
        </div>
        {resultado.email?.sucesso && (
          <p className="text-xs text-gray-500 inline-flex items-center gap-1">
            <Mail className="w-3 h-3" /> E-mail enviado para {resultado.email.destinatario}
          </p>
        )}
        <button onClick={resetar} className="text-xs text-gray-400 underline">
          Enviar novamente
        </button>
      </div>
    )

  return (
    <div className="space-y-1">
      <p className="text-red-500 text-sm inline-flex items-center gap-1">
        <XCircle className="w-4 h-4 shrink-0" /> {resultado?.erro}
      </p>
      <button onClick={resetar} className="text-xs text-gray-500 underline">
        Tentar novamente
      </button>
    </div>
  )
}
