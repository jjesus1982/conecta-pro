'use client'

import { useState, useEffect, useCallback } from 'react'
import { Landmark, CheckCircle2, Clock, XCircle, Wallet, List, Receipt, Zap, CreditCard, RefreshCw, Lightbulb, type LucideIcon } from 'lucide-react'

const API = '/api/v1/integrations/banking'
const PAYMENT_API = '/api/v1/banking/payment'

interface Saldo {
  balance: number
  available_balance: number
  blocked_balance: number
  account: string
}

interface Transacao {
  id: string
  transaction_date: string
  transaction_type: string
  amount: number
  description: string
  counterparty_name?: string
  reconciliado?: boolean
}

type Tab = 'saldo' | 'extrato' | 'boleto' | 'pix' | 'pagar' | 'darf'

export default function BankingPage() {
  const [tab, setTab] = useState<Tab>('saldo')
  const [saldo, setSaldo] = useState<Saldo | null>(null)
  const [extrato, setExtrato] = useState<Transacao[]>([])
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [token, setToken] = useState('')

  // Boleto form
  const [boletoForm, setBoletoForm] = useState({
    payer_name: '', payer_document: '',
    amount: '', due_date: '',
    description: 'Servico de seguranca',
    payer_address: '', payer_city: 'Manaus',
    payer_state: 'AM', payer_zip: '69000000',
    payer_number: 'S/N', payer_neighborhood: 'Centro'
  })

  // PIX form
  const [pixForm, setPixForm] = useState({
    pix_key: '', amount: '',
    description: '', payer_name: '',
    payer_document: ''
  })

  // Pagar form
  const [pagarForm, setPagarForm] = useState({
    codigo_barras: '', valor: '',
    data_pagamento: new Date().toISOString().split('T')[0],
    descricao: ''
  })

  // DARF form
  const [darfForm, setDarfForm] = useState({
    periodo_apuracao: '',
    numero_referencia: '',
    valor_principal: '',
    codigo_receita: '2100',
    descricao: 'INSS Patronal'
  })

  const getToken = useCallback(async () => {
    try {
      const r = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: 'username=jjesus@conectamais.pro&password=Jordan0612'
      })
      const d = await r.json()
      setToken(d.access_token || '')
      return d.access_token || ''
    } catch { return '' }
  }, [])

  const authHeader = useCallback((t?: string) => ({
    'Authorization': `Bearer ${t || token}`,
    'Content-Type': 'application/json'
  }), [token])

  const loadSaldo = useCallback(async () => {
    setLoading(true)
    try {
      const t = await getToken()
      const r = await fetch(`${API}/balances`,
        { headers: authHeader(t) })
      const d = await r.json()
      const interBank = Array.isArray(d.banks)
        ? d.banks.find((b: { bank_code: string }) => b.bank_code === '077')
        : d
      setSaldo(interBank || d)
    } catch {
      setMsg({ ok: false, text: 'Erro ao carregar saldo' })
    } finally { setLoading(false) }
  }, [getToken, authHeader])

  const loadExtrato = useCallback(async () => {
    setLoading(true)
    try {
      const t = await getToken()
      const r = await fetch(`${API}/statement/full`,
        { headers: authHeader(t) })
      const d = await r.json()
      setExtrato(d.transactions || d.items || [])
    } catch { setMsg({ ok: false, text: 'Erro ao carregar extrato' }) }
    finally { setLoading(false) }
  }, [getToken, authHeader])

  useEffect(() => {
    loadSaldo()
  }, [loadSaldo])

  useEffect(() => {
    if (tab === 'extrato') loadExtrato()
  }, [tab, loadExtrato])

  const emitirBoleto = async () => {
    setLoading(true); setMsg(null)
    try {
      const t = await getToken()
      const r = await fetch(`${API}/boleto/generate`, {
        method: 'POST',
        headers: authHeader(t),
        body: JSON.stringify({
          ...boletoForm,
          amount: parseFloat(boletoForm.amount)
        })
      })
      const d = await r.json()
      if (d.success || d.boleto_id) {
        setMsg({ ok: true, text: `Boleto emitido! ID: ${d.boleto_id}` })
        // Buscar barcode
        if (d.boleto_id) {
          const r2 = await fetch(
            `${API}/boleto/${d.boleto_id}`,
            { headers: authHeader(t) })
          const d2 = await r2.json()
          if (d2.barcode || d2.linha_digitavel) {
            setMsg({ ok: true, text: `Boleto: ${d2.linha_digitavel || d2.barcode}` })
          }
        }
      } else {
        setMsg({ ok: false, text: `Erro: ${d.detail || JSON.stringify(d)}` })
      }
    } catch (e) {
      setMsg({ ok: false, text: `Erro: ${e}` })
    } finally { setLoading(false) }
  }

  const enviarPix = async () => {
    setLoading(true); setMsg(null)
    try {
      const t = await getToken()
      const r = await fetch(`${API}/pix/generate`, {
        method: 'POST',
        headers: authHeader(t),
        body: JSON.stringify({
          ...pixForm,
          amount: parseFloat(pixForm.amount)
        })
      })
      const d = await r.json()
      if (d.success || d.charge_id) {
        setMsg({ ok: true, text: `PIX gerado! Copia e cola: ${
          (d.pix_copy_paste || '').substring(0, 50)}...` })
      } else {
        setMsg({ ok: false, text: `${d.detail || JSON.stringify(d)}` })
      }
    } catch (e) {
      setMsg({ ok: false, text: `${e}` })
    } finally { setLoading(false) }
  }

  const pagarBoleto = async () => {
    setLoading(true); setMsg(null)
    try {
      const t = await getToken()
      const r = await fetch(`${PAYMENT_API}/barcode`, {
        method: 'POST',
        headers: authHeader(t),
        body: JSON.stringify({
          ...pagarForm,
          valor: pagarForm.valor
            ? parseFloat(pagarForm.valor) : undefined
        })
      })
      const d = await r.json()
      if (d.success) {
        setMsg({ ok: true, text: `Pagamento realizado! ID: ${d.payment_id}` })
      } else {
        setMsg({ ok: false, text: `${d.detail || JSON.stringify(d)}` })
      }
    } catch (e) {
      setMsg({ ok: false, text: `${e}` })
    } finally { setLoading(false) }
  }

  const pagarDarf = async () => {
    setLoading(true); setMsg(null)
    try {
      const t = await getToken()
      const r = await fetch(`${PAYMENT_API}/darf`, {
        method: 'POST',
        headers: authHeader(t),
        body: JSON.stringify({
          ...darfForm,
          valor_principal: parseFloat(darfForm.valor_principal)
        })
      })
      const d = await r.json()
      if (d.success) {
        setMsg({ ok: true, text: `DARF pago! ID: ${d.payment_id}` })
      } else {
        setMsg({ ok: false, text: `${d.detail || JSON.stringify(d)}` })
      }
    } catch (e) {
      setMsg({ ok: false, text: `${e}` })
    } finally { setLoading(false) }
  }

  const tabs: {id: Tab, label: string, icon: LucideIcon}[] = [
    {id: 'saldo', label: 'Saldo', icon: Wallet},
    {id: 'extrato', label: 'Extrato', icon: List},
    {id: 'boleto', label: 'Emitir Boleto', icon: Receipt},
    {id: 'pix', label: 'Cobrar PIX', icon: Zap},
    {id: 'pagar', label: 'Pagar Boleto', icon: CreditCard},
    {id: 'darf', label: 'Pagar DARF', icon: Landmark},
  ]

  const inputClass = `w-full border border-gray-300 rounded-lg px-3 py-2
    text-sm focus:outline-none focus:ring-2 focus:ring-blue-500`
  const btnClass = `px-4 py-2 rounded-lg text-sm font-medium
    transition-colors disabled:opacity-50`

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-5xl mx-auto">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="font-display text-2xl font-semibold text-gray-900 flex items-center gap-2">
              <Landmark className="w-6 h-6" /> Banco Inter
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Conta 370990072-2 • Agência 0001
            </p>
          </div>
          {saldo && (
            <div className="text-right">
              <p className="text-sm text-gray-500">Saldo disponível</p>
              <p className="font-data text-2xl font-semibold tabular-nums text-green-600">
                {new Intl.NumberFormat('pt-BR', {
                  style: 'currency', currency: 'BRL'
                }).format(saldo.available_balance || saldo.balance || 0)}
              </p>
            </div>
          )}
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-6 flex-wrap">
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => { setTab(t.id); setMsg(null) }}
              className={`${btnClass} inline-flex items-center gap-2 ${
                tab === t.id
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-gray-700 border border-gray-200 hover:bg-gray-50'
              }`}
            >
              <t.icon className="w-4 h-4" /> {t.label}
            </button>
          ))}
        </div>

        {/* Mensagem */}
        {msg && (
          <div className={`p-3 rounded-lg mb-4 text-sm flex items-center gap-2 ${
            msg.ok
              ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
              : 'bg-red-500/10 text-red-500 border border-red-500/20'
          }`}>
            {msg.ok
              ? <CheckCircle2 className="w-4 h-4 shrink-0" />
              : <XCircle className="w-4 h-4 shrink-0" />}
            <span className="break-all">{msg.text}</span>
          </div>
        )}

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">

          {/* SALDO */}
          {tab === 'saldo' && (
            <div>
              <h2 className="text-lg font-semibold mb-4">
                Posição da Conta
              </h2>
              {loading ? (
                <div className="text-center py-8 text-gray-400">
                  Carregando...
                </div>
              ) : saldo ? (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {[
                    {label: 'Saldo Total', value: saldo.balance,
                     color: 'blue'},
                    {label: 'Disponível', value: saldo.available_balance,
                     color: 'green'},
                    {label: 'Bloqueado', value: saldo.blocked_balance,
                     color: 'red'},
                  ].map(item => (
                    <div key={item.label}
                      className="bg-gray-50 rounded-lg p-4">
                      <p className="text-sm text-gray-500">{item.label}</p>
                      <p className={`font-data text-2xl font-semibold tabular-nums text-${
                        item.color}-600 mt-1`}>
                        {new Intl.NumberFormat('pt-BR', {
                          style: 'currency', currency: 'BRL'
                        }).format(item.value || 0)}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-gray-400">Sem dados</p>
              )}
              <button
                onClick={loadSaldo}
                className={`${btnClass} bg-blue-600 text-white mt-4 inline-flex items-center gap-2`}
                disabled={loading}
              >
                <RefreshCw className="w-4 h-4" /> Atualizar
              </button>
            </div>
          )}

          {/* EXTRATO */}
          {tab === 'extrato' && (
            <div>
              <h2 className="text-lg font-semibold mb-4">
                Extrato — Últimos 30 dias
              </h2>
              {loading ? (
                <div className="text-center py-8">Carregando...</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left border-b border-gray-200">
                        <th className="pb-2 text-gray-500 font-medium">
                          Data</th>
                        <th className="pb-2 text-gray-500 font-medium">
                          Descrição</th>
                        <th className="pb-2 text-gray-500 font-medium">
                          Tipo</th>
                        <th className="pb-2 text-gray-500 font-medium text-right">
                          Valor</th>
                        <th className="pb-2 text-gray-500 font-medium">
                          Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {extrato.slice(0, 50).map((tx, i) => {
                        const isCredit = ['credit', 'CREDITO',
                          'PIX_RECEBIDO'].includes(
                          tx.transaction_type || '')
                        return (
                          <tr key={i}
                            className="border-b border-gray-50 hover:bg-gray-50">
                            <td className="py-2 text-gray-500">
                              {new Date(tx.transaction_date
                                ).toLocaleDateString('pt-BR')}
                            </td>
                            <td className="py-2 text-gray-700 max-w-xs truncate">
                              {tx.description}
                            </td>
                            <td className="py-2">
                              <span className={`px-2 py-0.5 rounded-full
                                text-xs font-medium ${
                                isCredit
                                  ? 'bg-green-100 text-green-700'
                                  : 'bg-red-100 text-red-700'
                              }`}>
                                {isCredit ? 'Entrada' : 'Saída'}
                              </span>
                            </td>
                            <td className={`py-2 text-right font-medium ${
                              isCredit ? 'text-green-600' : 'text-red-600'
                            }`}>
                              {isCredit ? '+' : '-'}
                              {new Intl.NumberFormat('pt-BR', {
                                style: 'currency', currency: 'BRL'
                              }).format(Math.abs(tx.amount || 0))}
                            </td>
                            <td className="py-2">
                              {tx.reconciliado ? (
                                <span className="text-xs text-green-600 inline-flex items-center gap-1">
                                  <CheckCircle2 className="w-3 h-3" /> Conciliado</span>
                              ) : (
                                <span className="text-xs text-yellow-600 inline-flex items-center gap-1">
                                  <Clock className="w-3 h-3" /> Pendente</span>
                              )}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                  {extrato.length === 0 && (
                    <div className="text-center py-8 text-gray-400">
                      Nenhuma transação encontrada
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* EMITIR BOLETO */}
          {tab === 'boleto' && (
            <div>
              <h2 className="text-lg font-semibold mb-4">
                Emitir Boleto de Cobrança
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {[
                  {key: 'payer_name', label: 'Nome do Pagador'},
                  {key: 'payer_document', label: 'CPF/CNPJ'},
                  {key: 'amount', label: 'Valor (R$)', type: 'number'},
                  {key: 'due_date', label: 'Vencimento', type: 'date'},
                  {key: 'description', label: 'Descrição'},
                  {key: 'payer_address', label: 'Endereço'},
                  {key: 'payer_city', label: 'Cidade'},
                  {key: 'payer_zip', label: 'CEP'},
                ].map(field => (
                  <div key={field.key}>
                    <label className="block text-sm text-gray-600 mb-1">
                      {field.label}
                    </label>
                    <input
                      type={field.type || 'text'}
                      value={(boletoForm as Record<string, string>)[field.key]}
                      onChange={e => setBoletoForm(f => ({
                        ...f, [field.key]: e.target.value}))}
                      className={inputClass}
                    />
                  </div>
                ))}
              </div>
              <button
                onClick={emitirBoleto}
                disabled={loading || !boletoForm.payer_name
                  || !boletoForm.amount}
                className={`${btnClass} bg-orange-500
                  text-white mt-4 hover:bg-orange-600`}
              >
                {loading ? 'Emitindo...' : <span className="inline-flex items-center gap-2"><Receipt className="w-4 h-4" /> Emitir Boleto</span>}
              </button>
            </div>
          )}

          {/* COBRAR PIX */}
          {tab === 'pix' && (
            <div>
              <h2 className="text-lg font-semibold mb-4">
                Gerar Cobrança PIX
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {[
                  {key: 'payer_name', label: 'Nome'},
                  {key: 'payer_document', label: 'CPF/CNPJ'},
                  {key: 'amount', label: 'Valor (R$)', type: 'number'},
                  {key: 'description', label: 'Descrição'},
                ].map(field => (
                  <div key={field.key}>
                    <label className="block text-sm text-gray-600 mb-1">
                      {field.label}
                    </label>
                    <input
                      type={field.type || 'text'}
                      value={(pixForm as Record<string, string>)[field.key]}
                      onChange={e => setPixForm(f => ({
                        ...f, [field.key]: e.target.value}))}
                      className={inputClass}
                    />
                  </div>
                ))}
              </div>
              <button
                onClick={enviarPix}
                disabled={loading || !pixForm.amount}
                className={`${btnClass} bg-green-500
                  text-white mt-4 hover:bg-green-600`}
              >
                {loading ? 'Gerando...' : <span className="inline-flex items-center gap-2"><Zap className="w-4 h-4" /> Gerar PIX</span>}
              </button>
            </div>
          )}

          {/* PAGAR BOLETO */}
          {tab === 'pagar' && (
            <div>
              <h2 className="text-lg font-semibold mb-4">
                Pagar Boleto / Convênio / Tributo
              </h2>
              <div className="grid grid-cols-1 gap-4">
                <div>
                  <label className="block text-sm text-gray-600 mb-1">
                    Código de Barras
                  </label>
                  <input
                    value={pagarForm.codigo_barras}
                    onChange={e => setPagarForm(f => ({
                      ...f, codigo_barras: e.target.value}))}
                    placeholder="Digite ou cole o código de barras"
                    className={inputClass}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-gray-600 mb-1">
                      Valor (R$)
                    </label>
                    <input
                      type="number"
                      value={pagarForm.valor}
                      onChange={e => setPagarForm(f => ({
                        ...f, valor: e.target.value}))}
                      placeholder="Opcional"
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-600 mb-1">
                      Data de Pagamento
                    </label>
                    <input
                      type="date"
                      value={pagarForm.data_pagamento}
                      onChange={e => setPagarForm(f => ({
                        ...f, data_pagamento: e.target.value}))}
                      className={inputClass}
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-sm text-gray-600 mb-1">
                    Descrição
                  </label>
                  <input
                    value={pagarForm.descricao}
                    onChange={e => setPagarForm(f => ({
                      ...f, descricao: e.target.value}))}
                    className={inputClass}
                  />
                </div>
              </div>
              <button
                onClick={pagarBoleto}
                disabled={loading || !pagarForm.codigo_barras}
                className={`${btnClass} bg-blue-600
                  text-white mt-4 hover:bg-blue-700`}
              >
                {loading ? 'Pagando...' : <span className="inline-flex items-center gap-2"><CreditCard className="w-4 h-4" /> Pagar</span>}
              </button>
            </div>
          )}

          {/* PAGAR DARF */}
          {tab === 'darf' && (
            <div>
              <h2 className="text-lg font-semibold mb-4">
                Pagar DARF
              </h2>
              <div className="bg-blue-50 rounded-lg p-3 mb-4 text-sm text-blue-800 flex items-start gap-2">
                <Lightbulb className="w-4 h-4 shrink-0 mt-0.5" />
                <span>Códigos mais usados: 2100=INSS | 6015=IRPJ |
                2372=CSLL | 0561=COFINS | 8109=PIS</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-600 mb-1">
                    Código de Receita
                  </label>
                  <select
                    value={darfForm.codigo_receita}
                    onChange={e => setDarfForm(f => ({
                      ...f, codigo_receita: e.target.value}))}
                    className={inputClass}
                  >
                    <option value="2100">2100 — INSS Patronal</option>
                    <option value="6015">6015 — IRPJ</option>
                    <option value="2372">2372 — CSLL</option>
                    <option value="0561">0561 — COFINS</option>
                    <option value="8109">8109 — PIS/PASEP</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-600 mb-1">
                    Período (AAAA-MM)
                  </label>
                  <input
                    value={darfForm.periodo_apuracao}
                    onChange={e => setDarfForm(f => ({
                      ...f, periodo_apuracao: e.target.value}))}
                    placeholder="2026-03"
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-600 mb-1">
                    Número de Referência
                  </label>
                  <input
                    value={darfForm.numero_referencia}
                    onChange={e => setDarfForm(f => ({
                      ...f, numero_referencia: e.target.value}))}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-600 mb-1">
                    Valor Principal (R$)
                  </label>
                  <input
                    type="number"
                    value={darfForm.valor_principal}
                    onChange={e => setDarfForm(f => ({
                      ...f, valor_principal: e.target.value}))}
                    className={inputClass}
                  />
                </div>
              </div>
              <button
                onClick={pagarDarf}
                disabled={loading || !darfForm.valor_principal
                  || !darfForm.periodo_apuracao}
                className={`${btnClass} bg-red-600
                  text-white mt-4 hover:bg-red-700`}
              >
                {loading ? 'Pagando...' : <span className="inline-flex items-center gap-2"><Landmark className="w-4 h-4" /> Pagar DARF</span>}
              </button>
            </div>
          )}

        </div>
      </div>
    </div>
  )
}
