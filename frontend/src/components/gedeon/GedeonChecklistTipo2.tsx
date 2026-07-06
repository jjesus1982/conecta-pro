'use client'

import { useState, useEffect } from 'react'
import { CheckCircle2, XCircle, AlertTriangle, Clock } from 'lucide-react'

interface ChecklistTipo2Data {
  score_prontidao: number
  checklist: {
    nfs_e: { ok: boolean; dados?: Record<string, unknown> }
    boleto: { ok: boolean; dados?: Record<string, unknown> }
  }
  pode_enviar: boolean
  pendencias: string[]
}

interface Props {
  clienteId: string
  competencia: string
  clienteNome: string
  onConfirmar: (dados: Record<string, unknown>) => void
  onCancelar: () => void
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

export default function GedeonChecklistTipo2({
  clienteId,
  competencia,
  clienteNome,
  onConfirmar,
  onCancelar,
}: Props) {
  const [ctx, setCtx] = useState<ChecklistTipo2Data | null>(null)
  const [loading, setLoading] = useState(true)
  const [observacoes, setObservacoes] = useState('')

  useEffect(() => {
    fetch(`/api/v1/gedeon/context/${clienteId}/${competencia}/tipo2`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then((r) => r.json())
      .then(setCtx)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [clienteId, competencia])

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center">
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-2xl p-8 text-center">
          <div className="w-8 h-8 border-4 border-blue-500 border-t-orange-500 rounded-full animate-spin mx-auto mb-3" />
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            GEDEON verificando {clienteNome}...
          </p>
        </div>
      </div>
    )
  }

  const score = ctx?.score_prontidao ?? 0
  const nfseOk = ctx?.checklist.nfs_e.ok ?? false
  const boletoOk = ctx?.checklist.boleto.ok ?? false

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
      <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-2xl shadow-2xl w-full max-w-md">
        {/* Header */}
        <div className="bg-[hsl(var(--secondary))] border-b border-[hsl(var(--border))] rounded-t-2xl px-6 py-4">
          <p className="text-[hsl(var(--muted-foreground))] text-xs uppercase tracking-wider">
            GEDEON — Kit Segurança Eletrônica
          </p>
          <h2 className="text-[hsl(var(--foreground))] font-bold text-lg">{clienteNome}</h2>
          <p className="text-[hsl(var(--muted-foreground))] text-sm">Competência: {competencia}</p>
        </div>

        <div className="p-6 space-y-4">
          {/* NFS-e */}
          <div
            className={`border rounded-xl p-4 ${
              nfseOk
                ? 'border-emerald-500/30 bg-emerald-500/10'
                : 'border-red-500/30 bg-red-500/10'
            }`}
          >
            <div className="flex items-center gap-3">
              {nfseOk
                ? <CheckCircle2 className="w-6 h-6 text-emerald-500 flex-shrink-0" />
                : <XCircle className="w-6 h-6 text-red-500 flex-shrink-0" />}
              <div>
                <p className="font-semibold text-[hsl(var(--foreground))]">
                  Nota Fiscal de Serviço (NFS-e)
                </p>
                <p className="text-sm text-[hsl(var(--muted-foreground))]">
                  {nfseOk
                    ? 'Emitida — pronta para o kit'
                    : 'Não emitida — necessária para envio'}
                </p>
                {nfseOk && ctx?.checklist.nfs_e.dados && (
                  <p className="text-xs text-emerald-500 mt-1">
                    Nº{' '}
                    {
                      (ctx.checklist.nfs_e.dados as Record<string, unknown>)
                        .numero as string
                    }{' '}
                    · R${' '}
                    {Number(
                      (ctx.checklist.nfs_e.dados as Record<string, unknown>)
                        .valor,
                    ).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Boleto */}
          <div
            className={`border rounded-xl p-4 ${
              boletoOk
                ? 'border-emerald-500/30 bg-emerald-500/10'
                : 'border-amber-500/30 bg-amber-500/10'
            }`}
          >
            <div className="flex items-center gap-3">
              {boletoOk
                ? <CheckCircle2 className="w-6 h-6 text-emerald-500 flex-shrink-0" />
                : <AlertTriangle className="w-6 h-6 text-amber-500 flex-shrink-0" />}
              <div>
                <p className="font-semibold text-[hsl(var(--foreground))]">
                  Boleto de Cobrança
                </p>
                <p className="text-sm text-[hsl(var(--muted-foreground))]">
                  {boletoOk
                    ? 'Gerado — pronto para o kit'
                    : 'Não gerado — verificar financeiro'}
                </p>
              </div>
            </div>
          </div>

          {/* Pendências */}
          {(ctx?.pendencias.length ?? 0) > 0 && (
            <div className="border border-amber-500/30 bg-amber-500/10 rounded-xl p-3">
              <p className="text-xs font-semibold text-amber-500 mb-1">
                Pendências:
              </p>
              <ul className="space-y-0.5">
                {ctx?.pendencias.map((p, i) => (
                  <li key={i} className="text-xs text-amber-500">
                    • {p}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Score */}
          <div className="bg-[hsl(var(--secondary))] rounded-xl p-4 flex items-center justify-between">
            <span className="text-sm text-[hsl(var(--muted-foreground))] font-medium">
              Prontidão do kit
            </span>
            <span
              className={`font-data text-2xl font-semibold tabular-nums ${
                score === 100
                  ? 'text-emerald-500'
                  : score >= 50
                    ? 'text-amber-500'
                    : 'text-red-500'
              }`}
            >
              {score}%
            </span>
          </div>

          {/* Observações */}
          <div>
            <p className="text-xs text-[hsl(var(--muted-foreground))] mb-1">
              Observações (opcional):
            </p>
            <textarea
              value={observacoes}
              onChange={(e) => setObservacoes(e.target.value)}
              placeholder="ex: Reajuste de 5% a partir deste mês..."
              rows={2}
              className="w-full border border-[hsl(var(--border))] bg-[hsl(var(--card))] text-[hsl(var(--foreground))] rounded-lg p-2 text-sm resize-none focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-[hsl(var(--border))] px-6 py-4 flex justify-between bg-[hsl(var(--secondary))] rounded-b-2xl">
          <button
            onClick={onCancelar}
            className="text-[hsl(var(--muted-foreground))] text-sm px-4 py-2 hover:text-[hsl(var(--foreground))]"
          >
            Cancelar
          </button>
          <button
            onClick={() =>
              onConfirmar({
                cliente_id: clienteId,
                competencia,
                tipo_kit: 'seguranca_eletronica',
                score,
                observacoes,
              })
            }
            disabled={!ctx?.pode_enviar}
            className={`inline-flex items-center gap-2 px-6 py-2 rounded-lg text-sm font-medium text-white transition-colors ${
              ctx?.pode_enviar
                ? 'bg-orange-500 hover:bg-orange-600'
                : 'bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))] cursor-not-allowed'
            }`}
          >
            {ctx?.pode_enviar
              ? <><CheckCircle2 className="w-4 h-4" /> Montar Kit</>
              : <><Clock className="w-4 h-4" /> Aguardando documentos</>}
          </button>
        </div>
      </div>
    </div>
  )
}
