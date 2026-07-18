'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Receipt, Eye, Download } from 'lucide-react'
import { PageHeader } from '@/components/ui/page-header'
import { abrirPdf } from '@/lib/pdf'

const brl = (v: number | null | undefined) =>
  new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v || 0)

const api = async (path: string, opts?: RequestInit) => {
  const token = typeof window !== 'undefined'
    ? (localStorage.getItem('access_token') ?? localStorage.getItem('token') ?? '') : ''
  const res = await fetch(`/api/v1/financial/relatorios${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, ...(opts?.headers || {}) },
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

const ORGAOS = [
  { v: 'RFB', l: 'Receita Federal' }, { v: 'PGFN', l: 'PGFN (Dívida Ativa)' },
  { v: 'SEFAZ_AM', l: 'SEFAZ-AM (ICMS)' }, { v: 'PREFEITURA_MANAUS', l: 'Prefeitura de Manaus (ISS)' },
  { v: 'INSS', l: 'INSS/Previdência' }, { v: 'FGTS', l: 'FGTS (Caixa)' }, { v: 'OUTRO', l: 'Outro órgão' },
]

function nowComp() {
  const d = new Date()
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`
}

export default function GuiasParcelamentosPage() {
  const qc = useQueryClient()
  const [comp, setComp] = useState(nowComp())
  const [form, setForm] = useState({ orgao: 'RFB', descricao: '', num_parcelas: '', parcela_valor: '', competencia_inicio: nowComp(), dia_vencimento: '20', numero_acordo: '', parcelas_pagas: '0' })
  const [showForm, setShowForm] = useState(false)

  const { data: guias } = useQuery({
    queryKey: ['guias-mes', comp],
    queryFn: () => api(`/guias-do-mes?competencia=${encodeURIComponent(comp)}`),
    retry: 1,
  })
  const { data: parc } = useQuery({
    queryKey: ['parcelamentos'],
    queryFn: () => api('/parcelamentos'),
    retry: 1,
  })

  const criar = useMutation({
    mutationFn: () => api('/parcelamentos', {
      method: 'POST',
      body: JSON.stringify({
        orgao: form.orgao, descricao: form.descricao,
        num_parcelas: Number(form.num_parcelas), parcela_valor: Number(form.parcela_valor),
        competencia_inicio: form.competencia_inicio, dia_vencimento: Number(form.dia_vencimento),
        numero_acordo: form.numero_acordo || null, parcelas_pagas: Number(form.parcelas_pagas) || 0,
      }),
    }),
    onSuccess: () => {
      setShowForm(false)
      setForm({ ...form, descricao: '', num_parcelas: '', parcela_valor: '', numero_acordo: '' })
      qc.invalidateQueries({ queryKey: ['parcelamentos'] })
      qc.invalidateQueries({ queryKey: ['guias-mes'] })
    },
  })

  const remover = useMutation({
    mutationFn: (id: number) => api(`/parcelamentos/${id}`, { method: 'DELETE' }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['parcelamentos'] }); qc.invalidateQueries({ queryKey: ['guias-mes'] }) },
  })

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <PageHeader
        eyebrow="FISCAL"
        title="Guias & Parcelamentos"
        subtitle="Guias a pagar do mês (parcelamentos + tributos) — nativo, sem Onvio."
        icon={<Receipt className="h-5 w-5" />}
      />

      {/* Guias do mês */}
      <div className="bg-white border border-gray-200 rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-semibold text-gray-900">Guias a pagar</h2>
            <input value={comp} onChange={(e) => setComp(e.target.value)} placeholder="MM/AAAA"
              className="border rounded-lg px-3 py-1.5 text-sm w-28" />
          </div>
          <div className="text-right">
            <p className="text-xs text-gray-500">Total a pagar em {comp}</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-red-700">{brl(guias?.total_a_pagar)}</p>
          </div>
        </div>
        {(guias?.guias ?? []).length > 0 ? (
          <table className="w-full text-sm">
            <thead className="text-gray-500 border-b text-xs">
              <tr><th className="text-left py-1">Guia</th><th className="text-left">Tipo</th><th className="text-left">Vence</th><th className="text-right">Valor</th><th className="text-right">Status</th><th className="text-right">PDF</th></tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {(guias?.guias ?? []).map((g: any, i: number) => (
                <tr key={i}>
                  <td className="py-1.5 text-gray-700">{g.descricao}</td>
                  <td><span className={`text-[10px] px-1.5 py-0.5 rounded ${g.tipo === 'parcelamento' ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700'}`}>{g.tipo}</span></td>
                  <td className="text-gray-500">{g.vencimento ? g.vencimento.slice(0, 10).split('-').reverse().join('/') : '—'}</td>
                  <td className="text-right font-mono">{brl(g.valor)}</td>
                  <td className="text-right"><span className={`text-[10px] px-1.5 py-0.5 rounded ${g.status === 'pago' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'}`}>{g.status}</span></td>
                  <td className="text-right whitespace-nowrap">
                    {g.pdf_disponivel ? (
                      <span className="inline-flex gap-1 justify-end">
                        <button onClick={() => abrirPdf(g.pdf_url)} title="Ver PDF da guia"
                          className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] hover:bg-gray-100"><Eye className="h-3 w-3" /></button>
                        <button onClick={() => abrirPdf(g.pdf_url, { download: true, nome: `guia_${g.orgao}_${comp}.pdf` })} title="Baixar PDF da guia"
                          className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] hover:bg-gray-100"><Download className="h-3 w-3" /></button>
                      </span>
                    ) : (
                      <span className="text-[11px] text-gray-300">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="text-sm text-gray-400 py-4">Nenhuma guia para esta competência (cadastre parcelamentos abaixo ou verifique o mês).</p>}
      </div>

      {/* Parcelamentos */}
      <div className="bg-white border border-gray-200 rounded-xl p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Parcelamentos / acordos</h2>
            <p className="text-xs text-gray-500">Saldo devedor total: <span className="font-semibold">{brl(parc?.saldo_devedor_total)}</span> · parcela mensal: {brl(parc?.total_parcela_mensal)}</p>
          </div>
          <button onClick={() => setShowForm(v => !v)} className="text-sm bg-[#0A2540] text-white px-4 py-2 rounded-lg hover:bg-[#0d3050]">
            {showForm ? 'Fechar' : '+ Novo parcelamento'}
          </button>
        </div>

        {showForm && (
          <div className="bg-gray-50 rounded-lg p-4 mb-4 grid grid-cols-2 md:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">Órgão</label>
              <select value={form.orgao} onChange={(e) => setForm({ ...form, orgao: e.target.value })} className="w-full border rounded px-2 py-1.5 text-sm bg-white">
                {ORGAOS.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
              </select>
            </div>
            <div className="col-span-2 md:col-span-1">
              <label className="block text-xs text-gray-600 mb-1">Descrição</label>
              <input value={form.descricao} onChange={(e) => setForm({ ...form, descricao: e.target.value })} className="w-full border rounded px-2 py-1.5 text-sm" placeholder="Ex.: Parcelamento ISS 2025" />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">Nº do acordo</label>
              <input value={form.numero_acordo} onChange={(e) => setForm({ ...form, numero_acordo: e.target.value })} className="w-full border rounded px-2 py-1.5 text-sm" />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">Nº de parcelas</label>
              <input type="number" value={form.num_parcelas} onChange={(e) => setForm({ ...form, num_parcelas: e.target.value })} className="w-full border rounded px-2 py-1.5 text-sm" />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">Valor da parcela</label>
              <input type="number" step="0.01" value={form.parcela_valor} onChange={(e) => setForm({ ...form, parcela_valor: e.target.value })} className="w-full border rounded px-2 py-1.5 text-sm" />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">1ª competência (MM/AAAA)</label>
              <input value={form.competencia_inicio} onChange={(e) => setForm({ ...form, competencia_inicio: e.target.value })} className="w-full border rounded px-2 py-1.5 text-sm" />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">Dia de vencimento</label>
              <input type="number" value={form.dia_vencimento} onChange={(e) => setForm({ ...form, dia_vencimento: e.target.value })} className="w-full border rounded px-2 py-1.5 text-sm" />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">Parcelas já pagas</label>
              <input type="number" value={form.parcelas_pagas} onChange={(e) => setForm({ ...form, parcelas_pagas: e.target.value })} className="w-full border rounded px-2 py-1.5 text-sm" />
            </div>
            <div className="col-span-2 md:col-span-3 flex justify-end">
              <button onClick={() => criar.mutate()} disabled={criar.isPending || !form.descricao || !form.num_parcelas || !form.parcela_valor}
                className="text-sm bg-emerald-600 text-white px-4 py-2 rounded-lg hover:bg-emerald-700 disabled:opacity-50">
                {criar.isPending ? 'Salvando…' : 'Salvar parcelamento'}
              </button>
            </div>
          </div>
        )}

        {(parc?.parcelamentos ?? []).length > 0 ? (
          <div className="space-y-2">
            {(parc?.parcelamentos ?? []).map((p: any) => (
              <div key={p.id} className="flex items-center justify-between border border-gray-100 rounded-lg p-3">
                <div>
                  <p className="text-sm font-medium text-gray-800">{p.orgao_label} — {p.descricao}</p>
                  <p className="text-[11px] text-gray-400">
                    {p.parcelas_pagas}/{p.num_parcelas} pagas · parcela {brl(p.parcela_valor)} · saldo {brl(p.saldo_devedor)}
                    {p.numero_acordo && ` · acordo ${p.numero_acordo}`}
                  </p>
                </div>
                <button onClick={() => remover.mutate(p.id)} className="text-xs text-red-600 hover:underline">remover</button>
              </div>
            ))}
          </div>
        ) : <p className="text-sm text-gray-400">Nenhum parcelamento cadastrado. Adicione seus acordos com Receita, SEFAZ, prefeitura, INSS e FGTS.</p>}
        <p className="text-[11px] text-gray-400 mt-3">Futuramente um robô puxará esses acordos direto do e-CAC/SEFAZ/prefeitura. Por ora, cadastre uma vez e o sistema traz a guia todo mês.</p>
      </div>
    </div>
  )
}
