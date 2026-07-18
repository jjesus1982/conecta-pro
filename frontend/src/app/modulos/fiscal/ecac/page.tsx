'use client'

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Landmark, ShieldCheck, ShieldAlert, Lock, CheckCircle2, AlertTriangle, Eye, Download, CreditCard, KeyRound, Loader2, X } from 'lucide-react'
import { PageHeader } from '@/components/ui/page-header'

const brl = (v: number | string | null | undefined) =>
  new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(v) || 0)

const bearer = () => (typeof window !== 'undefined'
  ? (localStorage.getItem('access_token') ?? localStorage.getItem('token') ?? '') : '')

const apiPost = async (path: string, body?: any) => {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${bearer()}` },
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `HTTP ${res.status}`)
  return data
}

// Baixa/abre um PDF protegido por token (o <a href> não carrega o Bearer → usa blob).
async function abrirGuiaPdf(pdfUrl: string, download: boolean) {
  const token = typeof window !== 'undefined'
    ? (localStorage.getItem('access_token') ?? localStorage.getItem('token') ?? '') : ''
  const res = await fetch(pdfUrl + (download ? '?download=1' : ''), { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) { alert('Não foi possível abrir o PDF da guia.'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  if (download) {
    const a = document.createElement('a'); a.href = url; a.download = ''
    document.body.appendChild(a); a.click(); a.remove()
  } else {
    window.open(url, '_blank', 'noopener')
  }
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}

const api = async (path: string) => {
  const token = typeof window !== 'undefined'
    ? (localStorage.getItem('access_token') ?? localStorage.getItem('token') ?? '') : ''
  const res = await fetch(`/api/v1/government/ecac${path}`, {
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
const unwrap = (r: any) => r?.data ?? r

export default function EcacPage() {
  const { data: statusR } = useQuery({ queryKey: ['ecac-status'], queryFn: () => api('/status'), retry: 1 })
  const { data: sfR } = useQuery({ queryKey: ['ecac-sf'], queryFn: () => api('/situacao-fiscal'), retry: 1 })
  const { data: debR } = useQuery({ queryKey: ['ecac-deb'], queryFn: () => api('/debitos'), retry: 1 })
  const { data: parcR } = useQuery({ queryKey: ['ecac-parc'], queryFn: () => api('/parcelamentos'), retry: 1 })

  const status = unwrap(statusR)
  const sf = unwrap(sfR)
  const deb = unwrap(debR)
  const parc = unwrap(parcR)

  const login = status?.login_ecac
  const pull = status?.pull_direto_rfb || sf?.pull_direto_rfb
  const comPendencia = sf?.situacao === 'com_pendencias'
  const debitos: any[] = deb?.debitos || []
  const parcelamentos: any[] = parc?.parcelamentos || []

  // ── Pagamento com gate OTP (reusa o fluxo Inter: preparar→gerar-otp→aprovar→executar) ──
  const qc = useQueryClient()
  const [pay, setPay] = useState<any>(null)
  const [step, setStep] = useState<'confirmar' | 'otp' | 'processando' | 'ok' | 'erro'>('confirmar')
  const [otp, setOtp] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  async function iniciarPagamento(d: any) {
    setBusy(true); setMsg('')
    try {
      const r = await apiPost(`/api/v1/fiscal/guias-drive/${d.id}/preparar-pagamento`)
      setPay({ paymentId: r.id || r.payment_id, valor: r.valor ?? d.valor_total, descricao: r.descricao || d.descricao, tipo: r.payment_type })
      setStep('confirmar'); setOtp('')
    } catch (e: any) { setPay({ paymentId: null }); setStep('erro'); setMsg(e.message) }
    finally { setBusy(false) }
  }
  async function enviarOtp() {
    setBusy(true); setMsg('')
    try { await apiPost(`/api/v1/financeiro/inter/payments/${pay.paymentId}/gerar-otp`); setStep('otp') }
    catch (e: any) { setMsg(e.message) }
    finally { setBusy(false) }
  }
  async function confirmarPagar() {
    if (otp.length !== 6) { setMsg('Digite o código de 6 dígitos.'); return }
    setBusy(true); setMsg(''); setStep('processando')
    try {
      await apiPost(`/api/v1/financeiro/inter/payments/${pay.paymentId}/aprovar`, { otp_code: otp })
      await apiPost(`/api/v1/financeiro/inter/payments/${pay.paymentId}/executar`)
      setStep('ok'); setMsg('Pagamento enviado ao Banco Inter.')
      qc.invalidateQueries({ queryKey: ['ecac-deb'] })
    } catch (e: any) { setStep('otp'); setMsg(e.message) }
    finally { setBusy(false) }
  }
  function fecharModal() {
    if (pay?.paymentId && step !== 'ok') {
      apiPost(`/api/v1/financeiro/inter/payments/${pay.paymentId}/cancelar`, { motivo: 'cancelado na tela e-CAC' }).catch(() => {})
    }
    setPay(null); setStep('confirmar'); setOtp(''); setMsg('')
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <PageHeader
        title="e-CAC — Receita Federal"
        subtitle="Situação fiscal, débitos e parcelamentos do CNPJ. Login por certificado digital A1."
        icon={<Landmark className="h-5 w-5" />}
      />

      {/* Conexão */}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border bg-white dark:bg-neutral-900 p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-500 mb-2">
            <ShieldCheck className="h-4 w-4 text-emerald-600" /> Conexão e-CAC
          </div>
          {login ? (
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                <span className="font-semibold text-emerald-700 dark:text-emerald-400 capitalize">{login.status}</span>
                <span className="text-xs text-neutral-400">· {login.metodo}</span>
              </div>
              <div className="text-sm text-neutral-700 dark:text-neutral-300">{login.titular}</div>
              <div className="text-xs text-neutral-500">Responsável legal: {login.responsavel_legal}</div>
            </div>
          ) : (
            <div className="text-sm text-neutral-400">Carregando status…</div>
          )}
        </div>

        {/* Situação fiscal */}
        <div className="rounded-xl border bg-white dark:bg-neutral-900 p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-500 mb-2">
            {comPendencia ? <ShieldAlert className="h-4 w-4 text-amber-600" /> : <ShieldCheck className="h-4 w-4 text-emerald-600" />}
            Situação Fiscal
          </div>
          {sf ? (
            <div className="space-y-1">
              <div className={`font-semibold ${comPendencia ? 'text-amber-700 dark:text-amber-400' : 'text-emerald-700 dark:text-emerald-400'}`}>
                {comPendencia ? 'Com pendências' : 'Regular'}
              </div>
              <div className="text-sm text-neutral-700 dark:text-neutral-300">
                Certidão disponível: <span className="font-medium">{sf.tipo_certidao_disponivel}</span>
                {sf.tipo_certidao_disponivel === 'CND' ? ' (Negativa)' : ' (Positiva c/ efeito negativa)'}
              </div>
              <div className="text-sm">Total em aberto: <span className="font-semibold">{brl(sf.valor_total_debitos)}</span></div>
            </div>
          ) : (
            <div className="text-sm text-neutral-400">Carregando…</div>
          )}
        </div>
      </div>

      {/* Aviso honesto sobre o pull direto */}
      {pull && pull.situacao === 'bloqueado_antibot' && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-800 p-4 flex gap-3">
          <Lock className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
          <div className="text-sm text-amber-800 dark:text-amber-300">
            <span className="font-semibold">Fonte dos dados:</span> {pull.detalhe}
          </div>
        </div>
      )}

      {/* Débitos */}
      <div className="rounded-xl border bg-white dark:bg-neutral-900 overflow-hidden">
        <div className="px-5 py-3 border-b flex items-center justify-between">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4 text-amber-600" /> Débitos em aberto
          </div>
          <span className="text-sm font-semibold">{brl(deb?.valor_total)}</span>
        </div>
        {debitos.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-neutral-50 dark:bg-neutral-800/50 text-neutral-500">
                <tr>
                  <th className="text-left px-5 py-2 font-medium">Competência</th>
                  <th className="text-left px-5 py-2 font-medium">Tributo</th>
                  <th className="text-left px-5 py-2 font-medium">Vencimento</th>
                  <th className="text-right px-5 py-2 font-medium">Valor</th>
                  <th className="text-right px-5 py-2 font-medium">Guia</th>
                </tr>
              </thead>
              <tbody>
                {debitos.map((d, i) => (
                  <tr key={i} className="border-t">
                    <td className="px-5 py-2">{d.competencia}</td>
                    <td className="px-5 py-2 font-medium">{d.descricao}</td>
                    <td className="px-5 py-2 text-neutral-500">{d.data_vencimento || '—'}</td>
                    <td className="px-5 py-2 text-right font-semibold">{brl(d.valor_total)}</td>
                    <td className="px-5 py-2 text-right whitespace-nowrap">
                      {d.pdf_disponivel ? (
                        <span className="inline-flex gap-1 justify-end">
                          <button onClick={() => abrirGuiaPdf(d.pdf_url, false)} title="Ver PDF da guia"
                            className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-neutral-100 dark:hover:bg-neutral-800">
                            <Eye className="h-3.5 w-3.5" /> Ver
                          </button>
                          <button onClick={() => abrirGuiaPdf(d.pdf_url, true)} title="Baixar PDF da guia"
                            className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-neutral-100 dark:hover:bg-neutral-800">
                            <Download className="h-3.5 w-3.5" />
                          </button>
                          {d.pagavel && (
                            <button onClick={() => iniciarPagamento(d)} disabled={busy}
                              title="Pagar via Banco Inter (com código de segurança)"
                              className="inline-flex items-center gap-1 rounded-md border border-emerald-600/40 text-emerald-700 dark:text-emerald-400 px-2 py-1 text-xs hover:bg-emerald-50 dark:hover:bg-emerald-950/40 disabled:opacity-50">
                              <CreditCard className="h-3.5 w-3.5" /> Pagar
                            </button>
                          )}
                        </span>
                      ) : (
                        <span className="text-xs text-neutral-400" title="Guia sem PDF (valor da folha, não do Drive)">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="px-5 py-8 text-center text-sm text-neutral-400">Sem débitos em aberto.</div>
        )}
      </div>

      {/* Parcelamentos */}
      <div className="rounded-xl border bg-white dark:bg-neutral-900 overflow-hidden">
        <div className="px-5 py-3 border-b flex items-center gap-2 font-medium">
          <Landmark className="h-4 w-4 text-blue-600" /> Parcelamentos
        </div>
        {parcelamentos.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-neutral-50 dark:bg-neutral-800/50 text-neutral-500">
                <tr>
                  <th className="text-left px-5 py-2 font-medium">Órgão</th>
                  <th className="text-left px-5 py-2 font-medium">Acordo</th>
                  <th className="text-left px-5 py-2 font-medium">Parcelas</th>
                  <th className="text-right px-5 py-2 font-medium">Valor total</th>
                </tr>
              </thead>
              <tbody>
                {parcelamentos.map((p, i) => (
                  <tr key={i} className="border-t">
                    <td className="px-5 py-2 font-medium">{p.orgao}</td>
                    <td className="px-5 py-2">{p.numero_acordo || p.descricao || '—'}</td>
                    <td className="px-5 py-2">{p.parcelas_pagas || 0}/{p.num_parcelas || '—'}</td>
                    <td className="px-5 py-2 text-right font-semibold">{brl(p.valor_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="px-5 py-8 text-center text-sm text-neutral-400">
            Nenhum parcelamento ativo. Cadastre em <span className="font-medium">Fiscal → Guias &amp; Parcelamentos</span>.
          </div>
        )}
      </div>

      {/* Modal de pagamento com gate OTP */}
      {pay && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={fecharModal}>
          <div className="w-full max-w-md rounded-2xl bg-white dark:bg-neutral-900 shadow-xl border" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <div className="flex items-center gap-2 font-semibold">
                <CreditCard className="h-4 w-4 text-emerald-600" /> Pagar guia via Banco Inter
              </div>
              <button onClick={fecharModal} className="text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200"><X className="h-4 w-4" /></button>
            </div>
            <div className="px-5 py-5 space-y-4">
              <div className="rounded-lg bg-neutral-50 dark:bg-neutral-800/60 p-4">
                <div className="text-xs text-neutral-500">{pay.descricao} · imposto{pay.tipo ? ` · ${String(pay.tipo).toUpperCase()}` : ''}</div>
                <div className="text-2xl font-bold tabular-nums mt-1">{brl(pay.valor)}</div>
              </div>

              {step === 'confirmar' && (
                <>
                  <p className="text-sm text-neutral-600 dark:text-neutral-300">Por segurança, um código de 6 dígitos será enviado ao e-mail do responsável antes de mover qualquer valor. <span className="font-medium">Nada é pago sem o código.</span></p>
                  <button onClick={enviarOtp} disabled={busy}
                    className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 text-white py-2.5 font-medium hover:bg-emerald-700 disabled:opacity-50">
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />} Enviar código de segurança
                  </button>
                </>
              )}
              {step === 'otp' && (
                <>
                  <p className="text-sm text-neutral-600 dark:text-neutral-300">Digite o código de 6 dígitos enviado ao e-mail do responsável.</p>
                  <input value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    inputMode="numeric" maxLength={6} placeholder="000000" autoFocus
                    className="w-full text-center tracking-[0.5em] text-2xl font-mono rounded-lg border py-3 bg-transparent" />
                  <button onClick={confirmarPagar} disabled={busy || otp.length !== 6}
                    className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 text-white py-2.5 font-medium hover:bg-emerald-700 disabled:opacity-50">
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />} Aprovar e pagar {brl(pay.valor)}
                  </button>
                  {msg && <div className="text-sm text-red-500 text-center">{msg}</div>}
                </>
              )}
              {step === 'processando' && (
                <div className="flex items-center justify-center gap-2 text-sm text-neutral-600 dark:text-neutral-300 py-4"><Loader2 className="h-4 w-4 animate-spin" /> Processando no Banco Inter…</div>
              )}
              {step === 'ok' && (
                <div className="flex flex-col items-center gap-2 py-2 text-center">
                  <CheckCircle2 className="h-10 w-10 text-emerald-600" />
                  <div className="font-semibold">Pagamento enviado ao Banco Inter</div>
                  <div className="text-sm text-neutral-500">{msg}</div>
                  <button onClick={fecharModal} className="mt-2 rounded-lg border px-4 py-2 text-sm">Fechar</button>
                </div>
              )}
              {step === 'erro' && (
                <div className="flex flex-col items-center gap-2 py-2 text-center">
                  <AlertTriangle className="h-10 w-10 text-red-500" />
                  <div className="font-semibold">Não foi possível preparar o pagamento</div>
                  <div className="text-sm text-neutral-500">{msg}</div>
                  <button onClick={fecharModal} className="mt-2 rounded-lg border px-4 py-2 text-sm">Fechar</button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
