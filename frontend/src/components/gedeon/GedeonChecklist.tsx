'use client'

import { useState, useEffect } from 'react'
import { Loader2, X, CheckCircle, AlertTriangle, XCircle, CheckCircle2, Clock, Info, Circle, Users, Paperclip, ShieldCheck, Bot, StickyNote } from 'lucide-react'

interface MovimentacaoItem {
  tipo: string
  funcionario?: string
  doc_pendente?: string
  requer_decisao?: boolean
  mensagem?: string
}

interface OcorrenciaItem {
  tipo: string
  data?: string
  requer_doc?: boolean
  mensagem?: string
}

interface PendenciaItem {
  requer_decisao?: boolean
  mensagem?: string
}

interface Certidoes {
  ok: number
  alerta: number
  critico: number
}

interface GedeonContextData {
  score_prontidao: number
  movimentacao_pessoal: MovimentacaoItem[]
  ocorrencias: OcorrenciaItem[]
  certidoes: Certidoes
  pendencias: PendenciaItem[]
  tipo_kit: string | null
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
    return localStorage.getItem('access_token') || localStorage.getItem('token') || ''
  } catch { return '' }
}

export default function GedeonChecklist({ clienteId, competencia, clienteNome, onConfirmar, onCancelar }: Props) {
  const [ctx, setCtx] = useState<GedeonContextData | null>(null)
  const [loading, setLoading] = useState(true)
  const [observacoes, setObservacoes] = useState('')
  const [confirmacoesExtra, setConfirmacoesExtra] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (!clienteId) { setLoading(false); return }
    const load = async () => {
      try {
        const res = await fetch(`/api/v1/gedeon/context/${clienteId}/${competencia}`, {
          headers: { Authorization: `Bearer ${getToken()}` },
        })
        if (res.ok) setCtx(await res.json())
      } catch (e) {
        console.error('GEDEON context error:', e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [clienteId, competencia])

  const score = ctx?.score_prontidao ?? 100
  const scoreColor = score >= 90 ? 'text-emerald-500' : score >= 70 ? 'text-amber-500' : 'text-red-500'

  const handleConfirmar = () => {
    onConfirmar({ cliente_id: clienteId, competencia, observacoes, confirmacoes: confirmacoesExtra, score_gedeon: score, tipo_kit: ctx?.tipo_kit || 'maos_de_obra' })
  }

  const setDecisao = (key: string, val: boolean) => setConfirmacoesExtra(p => ({ ...p, [key]: val }))

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center">
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-2xl p-8 flex flex-col items-center gap-3 shadow-2xl">
          <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
          <p className="text-sm text-[hsl(var(--muted-foreground))]">GEDEON analisando <strong>{clienteNome}</strong>...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-[hsl(var(--card))] rounded-2xl shadow-2xl border border-[hsl(var(--border))] w-full max-w-2xl my-4">
        <div className="bg-[hsl(var(--secondary))] border-b border-[hsl(var(--border))] rounded-t-2xl px-6 py-4 flex items-start justify-between">
          <div>
            <p className="text-[hsl(var(--muted-foreground))] text-xs uppercase tracking-wider mb-0.5">GEDEON — Checklist de Montagem</p>
            <h2 className="text-[hsl(var(--foreground))] font-bold text-lg">{clienteNome}</h2>
            <p className="text-[hsl(var(--muted-foreground))] text-xs mt-0.5">Competência: {competencia}</p>
          </div>
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl px-3 py-1.5 mt-1">
            <span className={`font-data text-2xl font-semibold tabular-nums ${scoreColor}`}>{score}%</span>
          </div>
        </div>

        <div className="p-6 space-y-4 max-h-[60vh] overflow-y-auto">
          {!ctx && (
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4 text-sm text-blue-500 flex items-start gap-2">
              <Info className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>GEDEON sem dados acumulados para esta competência. A montagem prosseguirá normalmente.</span>
            </div>
          )}

          {ctx && (
            <div className="border border-[hsl(var(--border))] rounded-xl p-4">
              <h3 className="font-semibold text-[hsl(var(--foreground))] mb-3 text-sm flex items-center gap-2"><ShieldCheck className="w-4 h-4" /> Certidões da Empresa</h3>
              {(ctx.certidoes?.critico ?? 0) > 0 ? (
                <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 space-y-2">
                  <div className="flex items-center gap-2 text-red-500 text-sm font-medium">
                    <XCircle className="w-4 h-4 flex-shrink-0" />
                    {ctx.certidoes.critico} certidão(ões) vencida(s)
                  </div>
                  <label className="flex items-center gap-2 text-sm text-[hsl(var(--muted-foreground))] cursor-pointer">
                    <input type="checkbox" className="rounded" checked={!!confirmacoesExtra.montar_com_certidao_vencida}
                      onChange={e => setDecisao('montar_com_certidao_vencida', e.target.checked)} />
                    Montar kit mesmo com certidão vencida
                  </label>
                </div>
              ) : (ctx.certidoes?.alerta ?? 0) > 0 ? (
                <div className="flex items-center gap-2 text-amber-500 text-sm">
                  <AlertTriangle className="w-4 h-4" />
                  {ctx.certidoes.alerta} certidão(ões) próximas do vencimento
                </div>
              ) : (
                <div className="flex items-center gap-2 text-emerald-500 text-sm">
                  <CheckCircle className="w-4 h-4" />
                  {ctx.certidoes?.ok ?? 0} certidões válidas
                </div>
              )}
            </div>
          )}

          {ctx && ctx.movimentacao_pessoal?.length > 0 && (
            <div className="border border-[hsl(var(--border))] rounded-xl p-4">
              <h3 className="font-semibold text-[hsl(var(--foreground))] mb-3 text-sm flex items-center gap-2">
                <Users className="w-4 h-4" /> Movimentação de Pessoal
                <span className="bg-blue-500/10 text-blue-500 text-xs px-2 py-0.5 rounded-full">{ctx.movimentacao_pessoal.length}</span>
              </h3>
              <div className="space-y-2">
                {ctx.movimentacao_pessoal.map((item, i) => (
                  <div key={i} className="flex items-start gap-2 bg-[hsl(var(--secondary))] rounded-lg p-2">
                    <span className="flex-shrink-0 mt-0.5">
                      {item.tipo === 'admissao' ? <CheckCircle2 className="w-4 h-4 text-emerald-500" /> : item.tipo === 'demissao' ? <XCircle className="w-4 h-4 text-red-500" /> : item.tipo === 'atestado' ? <AlertTriangle className="w-4 h-4 text-amber-500" /> : item.tipo === 'ferias' ? <Info className="w-4 h-4 text-blue-500" /> : <Circle className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />}
                    </span>
                    <div className="flex-1">
                      <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                        {item.tipo?.charAt(0).toUpperCase() + item.tipo?.slice(1)}{item.funcionario ? ` — ${item.funcionario}` : ''}
                      </p>
                      {item.doc_pendente && <p className="text-xs text-amber-500 mt-0.5 flex items-center gap-1"><Paperclip className="w-3 h-3" /> {item.doc_pendente}</p>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {ctx && ctx.ocorrencias?.length > 0 && (
            <div className="border border-[hsl(var(--border))] rounded-xl p-4">
              <h3 className="font-semibold text-[hsl(var(--foreground))] mb-3 text-sm flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-500" /> Ocorrências
                <span className="bg-amber-500/10 text-amber-500 text-xs px-2 py-0.5 rounded-full">{ctx.ocorrencias.length}</span>
              </h3>
              <div className="space-y-2">
                {ctx.ocorrencias.map((item, i) => (
                  <div key={i} className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-2 text-sm">
                    <p className="font-medium text-[hsl(var(--foreground))]">{item.tipo}{item.data ? ` — ${item.data}` : ''}</p>
                    {item.requer_doc && <p className="text-xs text-amber-500 mt-0.5 flex items-center gap-1"><Paperclip className="w-3 h-3" /> Documento necessário</p>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {ctx && ctx.pendencias?.some(p => p.requer_decisao) && (
            <div className="border border-amber-500/30 rounded-xl p-4 bg-amber-500/10">
              <h3 className="font-semibold text-amber-500 mb-3 text-sm flex items-center gap-2"><Bot className="w-4 h-4" /> GEDEON precisa da sua decisão</h3>
              <div className="space-y-3">
                {ctx.pendencias.filter(p => p.requer_decisao).map((item, i) => (
                  <div key={i} className="bg-[hsl(var(--card))] rounded-lg border border-amber-500/30 p-3">
                    <p className="text-sm text-[hsl(var(--foreground))] mb-2">{item.mensagem}</p>
                    <div className="flex gap-2">
                      <button onClick={() => setDecisao(`decisao_${i}`, true)}
                        className={`px-3 py-1 rounded text-sm font-medium ${confirmacoesExtra[`decisao_${i}`] === true ? 'bg-orange-500 text-white' : 'bg-[hsl(var(--secondary))] text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))]'}`}>
                        Sim, continuar
                      </button>
                      <button onClick={() => setDecisao(`decisao_${i}`, false)}
                        className={`px-3 py-1 rounded text-sm font-medium ${confirmacoesExtra[`decisao_${i}`] === false ? 'bg-red-500 text-white' : 'bg-[hsl(var(--secondary))] text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))]'}`}>
                        Não, aguardar
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {ctx && score >= 90 && !ctx.movimentacao_pessoal?.length && !ctx.ocorrencias?.length && !(ctx.certidoes?.critico) && (
            <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-4 flex items-center gap-3">
              <CheckCircle className="w-5 h-5 text-emerald-500 flex-shrink-0" />
              <p className="text-sm text-emerald-500 font-medium">GEDEON não identificou pendências. Kit pronto para montagem.</p>
            </div>
          )}

          <div className="border border-[hsl(var(--border))] rounded-xl p-4">
            <h3 className="font-semibold text-[hsl(var(--foreground))] mb-1 text-sm flex items-center gap-2"><StickyNote className="w-4 h-4" /> Observações</h3>
            <p className="text-xs text-[hsl(var(--muted-foreground))] mb-2">Informações que os sistemas não capturam automaticamente:</p>
            <textarea value={observacoes} onChange={e => setObservacoes(e.target.value)}
              placeholder="ex: Funcionário apresentou atestado mas ainda não está no sistema..." rows={3}
              className="w-full border border-[hsl(var(--border))] bg-[hsl(var(--card))] text-[hsl(var(--foreground))] rounded-lg p-3 text-sm resize-none focus:outline-none focus:border-blue-500" />
          </div>
        </div>

        <div className="border-t border-[hsl(var(--border))] px-6 py-4 flex justify-between items-center bg-[hsl(var(--secondary))] rounded-b-2xl">
          <button onClick={onCancelar} className="flex items-center gap-1 px-3 py-2 text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] text-sm">
            <X className="w-4 h-4" /> Cancelar
          </button>
          <button onClick={handleConfirmar} disabled={score < 50}
            className={`inline-flex items-center gap-2 px-6 py-2 rounded-lg text-sm font-medium text-white ${score >= 50 ? 'bg-orange-500 hover:bg-orange-600' : 'bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))] cursor-not-allowed'}`}>
            {score >= 90 ? <><CheckCircle2 className="w-4 h-4" /> Confirmar e Montar</> : score >= 70 ? <><AlertTriangle className="w-4 h-4" /> Montar com alertas</> : <><XCircle className="w-4 h-4" /> Score insuficiente</>}
          </button>
        </div>
      </div>
    </div>
  )
}
