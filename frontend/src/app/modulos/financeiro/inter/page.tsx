'use client'

import { useState, useEffect, useCallback } from 'react'

const API = '/api/v1/financeiro/inter'

type Tab = 'extrato' | 'folha' | 'cobrancas' | 'pix'

interface Saldo {
  disponivel: number
  bloqueado: number
  total: number
  conta: string
  updated_at: string
}

interface Tx {
  id: string
  data_lancamento: string
  tipo_operacao: string
  tipo_transacao: string
  valor: number
  descricao: string
  created_at: string
}

interface Pagamento {
  id: string
  nome: string
  cpf: string
  status: string
  match_tipo: string | null
  valor_liquido: number
  data_prevista: string | null
  data_paga: string | null
  competencia: string
}

interface Cobranca {
  id: string
  cobranca_id_inter: string
  valor: number
  vencimento: string
  status: string
  pagador: Record<string, string>
  url_boleto: string | null
  barcode: string | null
  descricao: string
  created_at: string
}

interface Pix {
  id: string
  end_to_end_id: string
  txid: string | null
  valor: number
  pagador: Record<string, string>
  data_horario: string | null
  created_at: string
}

function fmt(v: number) {
  // Guarda: valor ausente/inválido não pode derrubar o render (error boundary).
  if (typeof v !== 'number' || !isFinite(v)) return '—'
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function fmtDate(s: string | null) {
  if (!s) return '—'
  return new Date(s).toLocaleDateString('pt-BR')
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    pago: 'bg-green-100 text-green-700',
    previsto: 'bg-blue-100 text-blue-700',
    em_conciliacao: 'bg-yellow-100 text-yellow-700',
    divergente: 'bg-red-100 text-red-700',
    A_RECEBER: 'bg-blue-100 text-blue-700',
    PAGO: 'bg-green-100 text-green-700',
    CANCELADO: 'bg-gray-100 text-gray-500',
    C: 'bg-green-100 text-green-700',
    D: 'bg-red-100 text-red-700',
  }
  const cls = map[status] ?? 'bg-gray-100 text-gray-600'
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {status}
    </span>
  )
}

export default function InterPage() {
  const [tab, setTab] = useState<Tab>('extrato')
  const [saldo, setSaldo] = useState<Saldo | null>(null)
  const [txs, setTxs] = useState<Tx[]>([])
  const [pagamentos, setPagamentos] = useState<Pagamento[]>([])
  const [cobrancas, setCobrancas] = useState<Cobranca[]>([])
  const [pix, setPix] = useState<Pix[]>([])
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState('')
  const [competencia, setCompetencia] = useState('2026-03')
  const [syncDias, setSyncDias] = useState(7)
  const [ultimaSync, setUltimaSync] = useState<Date | null>(null)
  const [token, setToken] = useState('')

  // Usa o token da sessão que o usuário JÁ possui (mesmo padrão da tela de
  // pagamentos). NUNCA relogar com credencial no bundle — vaza senha e falha
  // se a senha muda. Se não houver token, as chamadas caem no catch e a tela
  // mostra "erro ao carregar" — sem quebrar o render.
  const getToken = useCallback(async () => {
    const t =
      (typeof window !== 'undefined' && localStorage.getItem('access_token')) || ''
    setToken(t)
    return t
  }, [])

  const auth = useCallback(
    (t?: string) => ({ Authorization: `Bearer ${t || token}`, 'Content-Type': 'application/json' }),
    [token],
  )

  const loadSaldo = useCallback(async () => {
    try {
      const t = await getToken()
      const r = await fetch(`${API}/saldo`, { headers: auth(t) })
      const d = await r.json()
      // Só aceita resposta com formato de saldo; erro (ex.: {detail}) vira null
      // e o card simplesmente não renderiza (em vez de quebrar a página).
      setSaldo(d && typeof d.disponivel === 'number' ? d : null)
      if (!d || typeof d.disponivel !== 'number') setMsg('Erro ao carregar saldo')
    } catch {
      setMsg('Erro ao carregar saldo')
    }
  }, [getToken, auth])

  const loadTxs = useCallback(async () => {
    setLoading(true)
    try {
      const t = await getToken()
      const r = await fetch(`${API}/transactions?limit=100`, { headers: auth(t) })
      const d = await r.json()
      setTxs(d.transactions || [])
    } catch {
      setMsg('Erro ao carregar transações')
    } finally {
      setLoading(false)
    }
  }, [getToken, auth])

  const loadPagamentos = useCallback(async () => {
    setLoading(true)
    try {
      const t = await getToken()
      const r = await fetch(`${API}/payroll/pagamentos?competencia=${competencia}`, { headers: auth(t) })
      const d = await r.json()
      setPagamentos(d.pagamentos || [])
    } catch {
      setMsg('Erro ao carregar pagamentos')
    } finally {
      setLoading(false)
    }
  }, [getToken, auth, competencia])

  const loadCobrancas = useCallback(async () => {
    setLoading(true)
    try {
      const t = await getToken()
      const r = await fetch(`${API}/cobrancas?limit=100`, { headers: auth(t) })
      const d = await r.json()
      setCobrancas(d.cobrancas || [])
    } catch {
      setMsg('Erro ao carregar cobranças')
    } finally {
      setLoading(false)
    }
  }, [getToken, auth])

  const loadPix = useCallback(async () => {
    setLoading(true)
    try {
      const t = await getToken()
      const r = await fetch(`${API}/pix/recebidos?limit=100`, { headers: auth(t) })
      const d = await r.json()
      setPix(d.pix || [])
    } catch {
      setMsg('Erro ao carregar PIX')
    } finally {
      setLoading(false)
    }
  }, [getToken, auth])

  const syncExtrato = async () => {
    setMsg('')
    try {
      const t = await getToken()
      await fetch(`${API}/sync-extrato?dias=${syncDias}`, { method: 'POST', headers: auth(t) })
      setUltimaSync(new Date())
      setMsg(`Sync iniciado para os últimos ${syncDias} dias.`)
      setTimeout(loadTxs, 3000)
    } catch {
      setMsg('Erro ao sincronizar extrato')
    }
  }

  const conciliar = async () => {
    setLoading(true)
    setMsg('')
    try {
      const t = await getToken()
      const r = await fetch(`${API}/conciliar/${competencia}`, { method: 'POST', headers: auth(t) })
      const d = await r.json()
      setMsg(
        `Conciliado: ${d.matches_fortes} fortes, ${d.matches_medios} médios, ${d.em_conciliacao} em revisão`,
      )
      loadPagamentos()
    } catch {
      setMsg('Erro ao conciliar folha')
    } finally {
      setLoading(false)
    }
  }

  const syncPix = async () => {
    setMsg('')
    try {
      const t = await getToken()
      await fetch(`${API}/pix/sync-recebidos?dias=30`, { method: 'POST', headers: auth(t) })
      setMsg('Sync PIX iniciado.')
      setTimeout(loadPix, 8000)
    } catch {
      setMsg('Erro ao sincronizar PIX')
    }
  }

  useEffect(() => {
    loadSaldo()
  }, [loadSaldo])

  useEffect(() => {
    if (tab === 'extrato') loadTxs()
    else if (tab === 'folha') loadPagamentos()
    else if (tab === 'cobrancas') loadCobrancas()
    else if (tab === 'pix') loadPix()
  }, [tab, loadTxs, loadPagamentos, loadCobrancas, loadPix])

  const tabs: { id: Tab; label: string }[] = [
    { id: 'extrato', label: 'Extrato' },
    { id: 'folha', label: 'Pagamentos Folha' },
    { id: 'cobrancas', label: 'Cobranças' },
    { id: 'pix', label: 'PIX Recebidos' },
  ]

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      {/* Header Inter */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div
            className="flex h-10 w-10 items-center justify-center rounded-lg text-white font-bold text-sm"
            style={{ backgroundColor: '#0A2540' }}
          >
            IN
          </div>
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Banco Inter</h1>
            <p className="text-xs text-gray-500">Open Banking · conta {saldo?.conta || '—'}</p>
          </div>
        </div>
        {msg && (
          <span className="rounded-lg bg-blue-50 px-4 py-2 text-sm text-blue-700 border border-blue-200">
            {msg}
          </span>
        )}
      </div>

      {/* Saldo Card */}
      {saldo && (
        <div
          className="mb-6 rounded-xl p-6 text-white"
          style={{ background: 'linear-gradient(135deg, #0A2540 0%, #1a3a5c 100%)' }}
        >
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm opacity-70">Saldo Disponível</p>
              <p className="mt-1 font-data text-2xl font-semibold tabular-nums">{fmt(saldo.disponivel)}</p>
              {saldo.bloqueado > 0 && (
                <p className="mt-1 text-sm opacity-60">Bloqueado: {fmt(saldo.bloqueado)}</p>
              )}
            </div>
            <div className="text-right">
              <p className="text-xs opacity-50">Atualizado</p>
              <p className="text-sm opacity-80">{fmtDate(saldo.updated_at)}</p>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="mb-4 flex gap-1 rounded-xl bg-white p-1 shadow-sm border border-gray-200">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              tab === t.id
                ? 'text-white'
                : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
            }`}
            style={tab === t.id ? { backgroundColor: '#FF6B35' } : {}}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="rounded-xl bg-white shadow-sm border border-gray-200">
        {/* ── Extrato ── */}
        {tab === 'extrato' && (
          <div>
            <div className="flex items-center justify-between border-b border-gray-100 p-4">
              <h2 className="font-medium text-gray-700">Transações Sincronizadas</h2>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={syncDias}
                  onChange={(e) => setSyncDias(Number(e.target.value))}
                  className="w-20 rounded-lg border border-gray-200 px-2 py-1.5 text-sm"
                  min={1}
                  max={90}
                />
                <span className="text-xs text-gray-500">dias</span>
                <button
                  onClick={syncExtrato}
                  className="rounded-lg px-4 py-1.5 text-sm text-white transition-opacity hover:opacity-90"
                  style={{ backgroundColor: '#FF6B35' }}
                >
                  Sincronizar
                </button>
              </div>
            </div>
            {loading ? (
              <p className="p-8 text-center text-gray-400">Carregando...</p>
            ) : (
              <div className="divide-y divide-gray-50">
                {txs.length === 0 && (
                  <p className="p-8 text-center text-gray-400">
                    Nenhuma transação. Clique em Sincronizar.
                  </p>
                )}
                {txs.map((tx) => (
                  <div key={tx.id} className="flex items-center justify-between px-4 py-3">
                    <div className="flex items-center gap-3">
                      <StatusBadge status={tx.tipo_operacao} />
                      <div>
                        <p className="text-sm font-medium text-gray-800">{tx.descricao}</p>
                        <p className="text-xs text-gray-400">
                          {fmtDate(tx.data_lancamento)} · {tx.tipo_transacao || '—'}
                        </p>
                      </div>
                    </div>
                    <span
                      className={`text-sm font-semibold ${tx.tipo_operacao === 'C' ? 'text-green-600' : 'text-red-500'}`}
                    >
                      {tx.tipo_operacao === 'C' ? '+' : '-'}
                      {fmt(tx.valor)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Pagamentos Folha ── */}
        {tab === 'folha' && (
          <div>
            <div className="flex items-center justify-between border-b border-gray-100 p-4">
              <h2 className="font-medium text-gray-700">Conciliação Folha de Pagamento</h2>
              <div className="flex items-center gap-2">
                <input
                  type="month"
                  value={competencia}
                  onChange={(e) => setCompetencia(e.target.value)}
                  className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm"
                />
                <button
                  onClick={conciliar}
                  disabled={loading}
                  className="rounded-lg px-4 py-1.5 text-sm text-white disabled:opacity-50 transition-opacity hover:opacity-90"
                  style={{ backgroundColor: '#0A2540' }}
                >
                  Conciliar
                </button>
                <button
                  onClick={loadPagamentos}
                  className="rounded-lg border border-gray-200 px-4 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
                >
                  Atualizar
                </button>
              </div>
            </div>
            {loading ? (
              <p className="p-8 text-center text-gray-400">Carregando...</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50 text-xs text-gray-500 uppercase">
                    <th className="px-4 py-3 text-left">Funcionário</th>
                    <th className="px-4 py-3 text-left">CPF</th>
                    <th className="px-4 py-3 text-right">Valor Líquido</th>
                    <th className="px-4 py-3 text-center">Status</th>
                    <th className="px-4 py-3 text-center">Match</th>
                    <th className="px-4 py-3 text-center">Data Paga</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {pagamentos.length === 0 && (
                    <tr>
                      <td colSpan={6} className="p-8 text-center text-gray-400">
                        Nenhum registro para {competencia}. Clique em Conciliar.
                      </td>
                    </tr>
                  )}
                  {pagamentos.map((p) => (
                    <tr key={p.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium text-gray-800">{p.nome || '—'}</td>
                      <td className="px-4 py-3 text-gray-500">{p.cpf || '—'}</td>
                      <td className="px-4 py-3 text-right font-semibold text-gray-700">
                        {fmt(p.valor_liquido)}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <StatusBadge status={p.status} />
                      </td>
                      <td className="px-4 py-3 text-center text-xs text-gray-500">
                        {p.match_tipo || '—'}
                      </td>
                      <td className="px-4 py-3 text-center text-xs text-gray-500">
                        {fmtDate(p.data_paga)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* ── Cobranças ── */}
        {tab === 'cobrancas' && (
          <div>
            <div className="flex items-center justify-between border-b border-gray-100 p-4">
              <h2 className="font-medium text-gray-700">Cobranças / Boletos</h2>
              <button
                onClick={loadCobrancas}
                className="rounded-lg border border-gray-200 px-4 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
              >
                Atualizar
              </button>
            </div>
            {loading ? (
              <p className="p-8 text-center text-gray-400">Carregando...</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50 text-xs text-gray-500 uppercase">
                    <th className="px-4 py-3 text-left">Descrição</th>
                    <th className="px-4 py-3 text-right">Valor</th>
                    <th className="px-4 py-3 text-center">Vencimento</th>
                    <th className="px-4 py-3 text-center">Status</th>
                    <th className="px-4 py-3 text-center">Boleto</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {cobrancas.length === 0 && (
                    <tr>
                      <td colSpan={5} className="p-8 text-center text-gray-400">
                        Nenhuma cobrança emitida ainda.
                      </td>
                    </tr>
                  )}
                  {cobrancas.map((c) => (
                    <tr key={c.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-gray-800">{c.descricao}</td>
                      <td className="px-4 py-3 text-right font-semibold">{fmt(c.valor)}</td>
                      <td className="px-4 py-3 text-center text-gray-500">
                        {fmtDate(c.vencimento)}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <StatusBadge status={c.status} />
                      </td>
                      <td className="px-4 py-3 text-center">
                        {c.url_boleto ? (
                          <a
                            href={c.url_boleto}
                            target="_blank"
                            rel="noreferrer"
                            className="text-xs text-blue-600 hover:underline"
                          >
                            PDF
                          </a>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* ── PIX Recebidos ── */}
        {tab === 'pix' && (
          <div>
            <div className="flex items-center justify-between border-b border-gray-100 p-4">
              <h2 className="font-medium text-gray-700">PIX Recebidos</h2>
              <button
                onClick={syncPix}
                className="rounded-lg px-4 py-1.5 text-sm text-white transition-opacity hover:opacity-90"
                style={{ backgroundColor: '#FF6B35' }}
              >
                Sincronizar PIX
              </button>
            </div>
            {loading ? (
              <p className="p-8 text-center text-gray-400">Carregando...</p>
            ) : (
              <div className="divide-y divide-gray-50">
                {pix.length === 0 && (
                  <p className="p-8 text-center text-gray-400">
                    Nenhum PIX recebido. Clique em Sincronizar PIX.
                  </p>
                )}
                {pix.map((p) => (
                  <div key={p.id} className="flex items-center justify-between px-4 py-3">
                    <div>
                      <p className="text-sm font-medium text-gray-800">
                        {p.pagador?.nome || p.pagador?.cpf || 'PIX Recebido'}
                      </p>
                      <p className="text-xs text-gray-400">
                        {fmtDate(p.data_horario)} · e2e: {(p.end_to_end_id || '').slice(-12)}
                      </p>
                    </div>
                    <span className="text-sm font-semibold text-green-600">+{fmt(p.valor)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer — última sincronização + link pagamentos */}
      <div className="mt-4 flex items-center justify-between text-xs text-gray-400">
        <span>
          {ultimaSync
            ? `Última sincronização: ${Math.round((Date.now() - ultimaSync.getTime()) / 60000)} min atrás`
            : 'Nenhuma sincronização nesta sessão'}
        </span>
        <div className="flex items-center gap-4">
          <a
            href="/modulos/financeiro/inter/pagamentos"
            className="text-xs font-medium px-3 py-1 rounded-full"
            style={{ background: '#FF6B35', color: '#fff' }}
          >
            💳 Pagamentos (D7)
          </a>
          <span style={{ color: '#FF6B35' }}>Banco Inter · Open Banking</span>
        </div>
      </div>
    </div>
  )
}
