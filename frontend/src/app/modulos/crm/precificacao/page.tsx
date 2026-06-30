'use client'

// ─────────────────────────────────────────────────────────────────────────
// Precificação — Comercial · CCT 2026 (Lucro Real)
// Consome a engine nova: /crm/pricing/* (alinhada à Planilha_Formacao_Preco_CCT2026).
// PREÇO = custo ÷ (1 − tributos − margem) · margem 15% líquida · encargos ~61,24%.
// Termos oficiais: AGP / ASG — NUNCA porteiro/vigia/faxineiro.
// ─────────────────────────────────────────────────────────────────────────

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

// ─── Tipos dos endpoints /crm/pricing/* ───────────────────────────────────
interface FuncaoPreco {
  funcao: string
  adicionais: string
  salario_base: number
  custo_total: number
  preco: number
  markup_pct: number
  lucro_liquido: number
}
interface FuncoesResp { regime: string; funcoes: FuncaoPreco[] }

interface Parametro { chave: string; valor: number; label: string; grupo: string }
interface ParametrosResp { regime: string; parametros: Parametro[] }

interface SimuladorResult {
  salario_base: number
  adic_noturno: number
  adic_hora_reduzida: number
  adic_ronda: number
  adic_risco: number
  salario_bruto: number
  encargos: number
  encargos_pct: number
  vt: number
  vr: number
  beneficios: number
  custo_total: number
  tributos_pct: number
  margem: number
  divisor: number
  preco: number
  markup_pct: number
  lucro_liquido: number
  postos: number
  preco_total_postos: number
}

// ─── Helpers ──────────────────────────────────────────────────────────────
const token = () =>
  typeof window !== 'undefined'
    ? (localStorage.getItem('access_token') ?? localStorage.getItem('token') ?? '')
    : ''

const fetchAuth = (url: string) =>
  fetch(url, { headers: { Authorization: `Bearer ${token()}` } })
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })

const sendAuth = (url: string, method: string, body: unknown) =>
  fetch(url, {
    method,
    headers: { Authorization: `Bearer ${token()}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })

const brl = (v: number) =>
  (v ?? 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
const pct = (v: number) => `${((v ?? 0) * 100).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}%`

const GRUPO_LABEL: Record<string, string> = {
  encargos: 'Encargos sociais (Lucro Real)',
  tributos: 'Tributos sobre faturamento',
  adicionais: 'Adicionais',
  beneficios: 'Benefícios',
  margem: 'Margem',
  geral: 'Geral',
}

type AbaId = 'tabela' | 'simulador' | 'parametros'

// ─── Componente ───────────────────────────────────────────────────────────
export default function PrecificacaoPage() {
  const qc = useQueryClient()
  const [abaAtiva, setAbaAtiva] = useState<AbaId>('tabela')

  // Tabela de funções
  const { data: funcData, isLoading: funcLoading, error: funcError } =
    useQuery<FuncoesResp>({
      queryKey: ['pricing-funcoes'],
      queryFn: () => fetchAuth('/api/v1/crm/pricing/funcoes'),
      staleTime: 5 * 60 * 1000,
    })
  const funcoes = funcData?.funcoes ?? []

  // Simulador
  const [simFuncao, setSimFuncao] = useState('AGP P1 Diurno')
  const [postos, setPostos] = useState(1)
  const [margem, setMargem] = useState<string>('') // vazio = usa a margem padrão
  const [tg, setTg] = useState({
    noturno: false, hora_reduzida: false, ronda: false,
    periculosidade: false, insalubridade: false,
  })
  const [sim, setSim] = useState<SimuladorResult | null>(null)

  const simular = useMutation({
    mutationFn: () => sendAuth('/api/v1/crm/pricing/simular', 'POST', {
      funcao: simFuncao,
      postos,
      noturno: tg.noturno,
      hora_reduzida: tg.hora_reduzida,
      ronda: tg.ronda,
      periculosidade: tg.periculosidade,
      insalubridade: tg.insalubridade,
      ...(margem ? { margem: Number(margem) / 100 } : {}),
    }),
    onSuccess: (r: SimuladorResult) => setSim(r),
  })

  // Parâmetros
  const { data: paramData, isLoading: paramLoading } = useQuery<ParametrosResp>({
    queryKey: ['pricing-parametros'],
    queryFn: () => fetchAuth('/api/v1/crm/pricing/parametros'),
    staleTime: 5 * 60 * 1000,
  })
  const [edits, setEdits] = useState<Record<string, string>>({})
  const salvar = useMutation({
    mutationFn: (valores: Record<string, number>) =>
      sendAuth('/api/v1/crm/pricing/parametros', 'PUT', { valores }),
    onSuccess: () => {
      setEdits({})
      qc.invalidateQueries({ queryKey: ['pricing-parametros'] })
      qc.invalidateQueries({ queryKey: ['pricing-funcoes'] })
    },
  })
  const aplicarParams = () => {
    const valores: Record<string, number> = {}
    for (const [k, v] of Object.entries(edits)) {
      if (v !== '' && !Number.isNaN(Number(v))) valores[k] = Number(v)
    }
    if (Object.keys(valores).length) salvar.mutate(valores)
  }

  const params = paramData?.parametros ?? []
  const grupos = [...new Set(params.map(p => p.grupo))]

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Precificação — Comercial</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {funcData?.regime ?? 'Lucro Real · Margem 15% · CCT SINDECOMPRESTS 2026'}
          </p>
        </div>
        <div className="flex gap-1 bg-gray-100 p-1 rounded-xl">
          {([['tabela', '📊 Tabela'], ['simulador', '🧮 Simulador'], ['parametros', '⚙️ Parâmetros']] as const).map(([aba, lbl]) => (
            <button
              key={aba}
              onClick={() => setAbaAtiva(aba as AbaId)}
              className={`px-4 py-1.5 text-sm rounded-lg transition-all ${
                abaAtiva === aba ? 'bg-white text-gray-900 font-medium shadow-sm' : 'text-gray-500 hover:text-gray-700'
              }`}
            >{lbl}</button>
          ))}
        </div>
      </div>

      {/* ── ABA: TABELA DE FUNÇÕES ───────────────────────────────────────── */}
      {abaAtiva === 'tabela' && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          {funcLoading && <p className="p-6 text-sm text-gray-500">Carregando…</p>}
          {funcError && <p className="p-6 text-sm text-red-600">Erro ao carregar a tabela.</p>}
          {!funcLoading && !funcError && (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-gray-500 border-b border-gray-200">
                  <th className="px-5 py-3">Função</th>
                  <th className="px-5 py-3">Adicionais</th>
                  <th className="px-5 py-3 text-right">Salário base</th>
                  <th className="px-5 py-3 text-right">Custo</th>
                  <th className="px-5 py-3 text-right">Preço/posto</th>
                  <th className="px-5 py-3 text-right">Markup</th>
                </tr>
              </thead>
              <tbody>
                {funcoes.map(f => (
                  <tr key={f.funcao} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-5 py-3 font-medium text-gray-900">{f.funcao}</td>
                    <td className="px-5 py-3 text-gray-500">{f.adicionais}</td>
                    <td className="px-5 py-3 text-right text-gray-600">{brl(f.salario_base)}</td>
                    <td className="px-5 py-3 text-right text-gray-600">{brl(f.custo_total)}</td>
                    <td className="px-5 py-3 text-right font-semibold text-emerald-700">{brl(f.preco)}</td>
                    <td className="px-5 py-3 text-right text-gray-500">{pct(f.markup_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="px-5 py-3 text-xs text-gray-400 border-t border-gray-100">
            Preço = custo ÷ (1 − tributos − margem). Periculosidade e insalubridade não acumulam (periculosidade prevalece).
          </p>
        </div>
      )}

      {/* ── ABA: SIMULADOR ───────────────────────────────────────────────── */}
      {abaAtiva === 'simulador' && (
        <div className="grid grid-cols-2 gap-6">
          {/* Parâmetros do simulador */}
          <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-5">
            <p className="text-sm font-medium text-gray-900">Parâmetros da simulação</p>

            <div>
              <label className="text-xs font-medium text-gray-500 uppercase tracking-wide block mb-2">Função</label>
              <select
                value={simFuncao}
                onChange={e => setSimFuncao(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              >
                {funcoes.map(f => <option key={f.funcao} value={f.funcao}>{f.funcao}</option>)}
              </select>
            </div>

            <div>
              <label className="text-xs font-medium text-gray-500 uppercase tracking-wide block mb-2">Postos</label>
              <input
                type="number" min={1} value={postos}
                onChange={e => setPostos(Math.max(1, Number(e.target.value)))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-gray-500 uppercase tracking-wide block mb-2">
                Adicionais extras (a função já traz os seus)
              </label>
              <div className="grid grid-cols-2 gap-2">
                {([
                  ['noturno', 'Noturno'], ['hora_reduzida', 'Hora red.'], ['ronda', 'Ronda'],
                  ['periculosidade', 'Periculosidade'], ['insalubridade', 'Insalubridade'],
                ] as const).map(([k, lbl]) => (
                  <label key={k} className="flex items-center gap-2 text-sm text-gray-700">
                    <input
                      type="checkbox"
                      checked={tg[k as keyof typeof tg]}
                      onChange={e => setTg(s => ({ ...s, [k]: e.target.checked }))}
                    />
                    {lbl}
                  </label>
                ))}
              </div>
              <p className="text-xs text-gray-400 mt-2">Peric. × insalub. não acumulam — periculosidade prevalece.</p>
            </div>

            <div>
              <label className="text-xs font-medium text-gray-500 uppercase tracking-wide block mb-2">
                Margem (%) — vazio usa a padrão
              </label>
              <input
                type="number" placeholder="15" value={margem}
                onChange={e => setMargem(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>

            <button
              onClick={() => simular.mutate()}
              disabled={simular.isPending}
              className="w-full bg-gray-900 text-white text-sm font-medium rounded-lg py-2.5 hover:bg-gray-800 disabled:opacity-50"
            >
              {simular.isPending ? 'Calculando…' : 'Simular preço'}
            </button>
          </div>

          {/* Resultado / composição */}
          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <p className="text-sm font-medium text-gray-900 mb-4">Composição do preço</p>
            {!sim && <p className="text-sm text-gray-400">Configure e clique em “Simular preço”.</p>}
            {sim && (
              <div className="space-y-1.5 text-sm">
                <Row label="Salário base" value={brl(sim.salario_base)} />
                {sim.adic_noturno > 0 && <Row label="+ Adic. noturno" value={brl(sim.adic_noturno)} />}
                {sim.adic_hora_reduzida > 0 && <Row label="+ Hora noturna reduzida" value={brl(sim.adic_hora_reduzida)} />}
                {sim.adic_ronda > 0 && <Row label="+ Adic. ronda" value={brl(sim.adic_ronda)} />}
                {sim.adic_risco > 0 && <Row label="+ Peric./insalub." value={brl(sim.adic_risco)} />}
                <Row label="= Salário bruto" value={brl(sim.salario_bruto)} strong />
                <Row label={`+ Encargos (${pct(sim.encargos_pct)})`} value={brl(sim.encargos)} />
                <Row label="+ Benefícios (VT + VR + cesta + EPI + seguro)" value={brl(sim.beneficios)} />
                <div className="border-t border-gray-200 my-2" />
                <Row label="= Custo total" value={brl(sim.custo_total)} strong />
                <Row label={`÷ Divisor (1 − tributos ${pct(sim.tributos_pct)} − margem ${pct(sim.margem)})`} value={sim.divisor.toFixed(4)} />
                <div className="border-t border-gray-200 my-2" />
                <div className="flex justify-between items-center bg-emerald-50 rounded-lg px-3 py-2.5">
                  <span className="font-medium text-emerald-900">Preço / posto</span>
                  <span className="text-lg font-semibold text-emerald-700">{brl(sim.preco)}</span>
                </div>
                {sim.postos > 1 && (
                  <div className="flex justify-between items-center bg-gray-900 rounded-lg px-3 py-2.5 mt-1.5">
                    <span className="font-medium text-white">Total {sim.postos} postos</span>
                    <span className="text-lg font-semibold text-white">{brl(sim.preco_total_postos)}</span>
                  </div>
                )}
                <p className="text-xs text-gray-400 pt-2">
                  Markup {pct(sim.markup_pct)} · lucro líquido/posto {brl(sim.lucro_liquido)}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── ABA: PARÂMETROS ──────────────────────────────────────────────── */}
      {abaAtiva === 'parametros' && (
        <div className="space-y-5">
          {paramLoading && <p className="text-sm text-gray-500">Carregando…</p>}
          {grupos.map(g => (
            <div key={g} className="bg-white border border-gray-200 rounded-xl p-5">
              <p className="text-sm font-medium text-gray-900 mb-4">{GRUPO_LABEL[g] ?? g}</p>
              <div className="grid grid-cols-2 gap-x-6 gap-y-3">
                {params.filter(p => p.grupo === g).map(p => {
                  const monetario = p.grupo === 'beneficios' && Math.abs(p.valor) > 5
                  return (
                    <div key={p.chave} className="flex items-center justify-between gap-3">
                      <label className="text-sm text-gray-600">
                        {p.label}
                        <span className="text-xs text-gray-400 ml-1">
                          ({monetario ? brl(p.valor) : pct(p.valor)})
                        </span>
                      </label>
                      <input
                        type="number" step="any"
                        placeholder={String(p.valor)}
                        value={edits[p.chave] ?? ''}
                        onChange={e => setEdits(s => ({ ...s, [p.chave]: e.target.value }))}
                        className="w-28 border border-gray-300 rounded-lg px-2 py-1.5 text-sm text-right"
                      />
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-400">
              Valores fracionários (0,15 = 15%). Benefícios em reais. Salvar recalcula a tabela e reflete no Cowork (MCP).
            </p>
            <button
              onClick={aplicarParams}
              disabled={salvar.isPending || Object.keys(edits).length === 0}
              className="bg-gray-900 text-white text-sm font-medium rounded-lg px-5 py-2 hover:bg-gray-800 disabled:opacity-40"
            >
              {salvar.isPending ? 'Salvando…' : 'Salvar alterações'}
            </button>
          </div>
          {salvar.isSuccess && <p className="text-sm text-emerald-600">Parâmetros atualizados ✓</p>}
          {salvar.isError && <p className="text-sm text-red-600">Erro ao salvar.</p>}
        </div>
      )}
    </div>
  )
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex justify-between">
      <span className={strong ? 'font-medium text-gray-900' : 'text-gray-500'}>{label}</span>
      <span className={strong ? 'font-medium text-gray-900' : 'text-gray-700'}>{value}</span>
    </div>
  )
}
