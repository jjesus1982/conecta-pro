'use client'

import { useQuery } from '@tanstack/react-query'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { AlertTriangle } from 'lucide-react'

// ── helpers ──────────────────────────────────────────────────────────────────
const brl = (v: number | null | undefined) =>
  new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v || 0)

const fetchAuth = async (path: string) => {
  const token = typeof window !== 'undefined'
    ? (localStorage.getItem('access_token') ?? localStorage.getItem('token') ?? '') : ''
  const res = await fetch(`/api/v1${path}`, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

const FAIXA_META: Record<string, { label: string; barra: string }> = {
  a_vencer: { label: 'A vencer', barra: 'bg-gray-300' },
  ate_30_dias: { label: '0–30 dias', barra: 'bg-orange-400' },
  '31_a_60_dias': { label: '31–60 dias', barra: 'bg-orange-500' },
  '61_a_90_dias': { label: '61–90 dias', barra: 'bg-red-500' },
  acima_90_dias: { label: '+90 dias', barra: 'bg-red-700' },
}

interface Faixa { faixa: string; quantidade: number; valor_total: number }

function AgingBars({ faixas }: { faixas: Faixa[] }) {
  const max = Math.max(1, ...faixas.map(f => f.valor_total))
  if (!faixas.length) return <p className="text-xs text-gray-400">Sem valores em aberto.</p>
  return (
    <div className="space-y-1.5 mt-2">
      {faixas.map(f => {
        const meta = FAIXA_META[f.faixa] ?? { label: f.faixa, barra: 'bg-gray-400' }
        const pct = Math.round((f.valor_total / max) * 100)
        return (
          <div key={f.faixa} className="flex items-center gap-2">
            <span className="text-[11px] w-20 shrink-0 text-gray-600">{meta.label}</span>
            <div className="flex-1 bg-gray-100 rounded h-5 overflow-hidden relative">
              <div className={`h-full ${meta.barra}`} style={{ width: `${Math.max(pct, 3)}%` }} />
              <span className="absolute inset-0 flex items-center px-2 text-[11px] font-medium text-gray-800">
                {brl(f.valor_total)} · {f.quantidade}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default function RaioXPage() {
  const { data: p, isLoading, error, refetch } = useQuery({
    queryKey: ['cfo-panorama'],
    queryFn: () => fetchAuth('/financial/cfo/panorama'),
    staleTime: 60_000, retry: 1,
  })
  const { data: proj } = useQuery({
    queryKey: ['cfo-projecao'],
    queryFn: () => fetchAuth('/financial/cfo/projecao-caixa?meses=6'),
    staleTime: 60_000, retry: 1,
  })
  const { data: trib } = useQuery({
    queryKey: ['tributos', 2026],
    queryFn: () => fetchAuth('/financial/relatorios/tributos?ano=2026'),
    staleTime: 300_000, retry: 1,
  })
  const { data: receb } = useQuery({
    queryKey: ['recebido-cliente'],
    queryFn: () => fetchAuth('/financial/cfo/recebido-por-cliente'),
    staleTime: 120_000, retry: 1,
  })
  const { data: adim } = useQuery({
    queryKey: ['adimplencia'],
    queryFn: () => fetchAuth('/financial/cfo/adimplencia-clientes'),
    staleTime: 120_000, retry: 1,
  })

  if (isLoading) return <div className="p-8 text-gray-500">Carregando raio-x financeiro…</div>
  if (error || !p) return (
    <div className="p-8">
      <p className="text-red-600 font-medium">Não foi possível carregar o raio-x financeiro.</p>
      <button onClick={() => refetch()} className="mt-2 text-sm bg-gray-800 text-white px-4 py-2 rounded-lg">Tentar novamente</button>
    </div>
  )

  const prev = p.previsao_custos ?? {}
  const custoItens: { categoria: string; valor: number; grupo: string }[] = (prev.itens ?? []).filter((i: any) => i.valor > 0)
  const grupoCor: Record<string, string> = {
    folha: 'bg-blue-500', tributo: 'bg-amber-500', provisao: 'bg-purple-500',
    diaristas: 'bg-teal-500', fornecedor: 'bg-gray-500', parcelamento: 'bg-rose-500', acordo: 'bg-rose-400', fixo: 'bg-slate-500',
  }
  const runwayBaixo = (p.runway_meses ?? 99) < 3
  const projPontos = (proj?.pontos ?? []).map((x: any) => ({ mes: x.competencia, saldo: x.saldo_projetado }))

  const kpis = [
    { label: 'Saldo em conta', valor: brl(p.saldo_banco), sub: p.saldo_fonte, cor: 'text-[#0A2540]' },
    { label: 'Runway (caixa ÷ folha)', valor: p.runway_meses != null ? `${p.runway_meses} meses` : '—', sub: runwayBaixo ? '⚠️ caixa curto' : 'saudável', cor: runwayBaixo ? 'text-red-600' : 'text-green-600' },
    { label: 'MRR contratado', valor: brl(p.mrr_contratado), sub: `${p.contratos ?? 0} contratos`, cor: 'text-emerald-600' },
    { label: 'Resultado mensal', valor: brl(p.resultado_mensal), sub: `receita − custos (inclui provisões)`, cor: (p.resultado_mensal ?? 0) >= 0 ? 'text-green-600' : 'text-red-600' },
  ]

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-[#0A2540]">📊 Raio-X Financeiro</h1>
          <p className="text-sm text-gray-500 mt-0.5">Fotografia real do caixa, recebíveis, pagáveis e custos — tudo ao vivo, nada estimado sem aviso.</p>
        </div>
        <button onClick={() => refetch()} className="text-sm text-gray-600 border border-gray-200 rounded-lg px-4 py-2 hover:bg-gray-50">↺ Atualizar</button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map(k => (
          <div key={k.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <p className="text-xs text-gray-500">{k.label}</p>
            <p className={`font-data text-2xl font-semibold tabular-nums mt-1 ${k.cor}`}>{k.valor}</p>
            <p className="text-[11px] text-gray-400 mt-0.5">{k.sub}</p>
          </div>
        ))}
      </div>

      {/* Receber / Pagar com aging */}
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-900">A receber</h2>
            <span className="text-lg font-bold text-emerald-600">{brl(p.receber_pendente)}</span>
          </div>
          <p className="text-xs text-red-600">{brl(p.receber_vencido)} vencido · {p.receber_qtd ?? 0} títulos</p>
          <AgingBars faixas={p.aging_receber ?? []} />
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-900">A pagar</h2>
            <span className="text-lg font-bold text-red-600">{brl(p.pagar_pendente)}</span>
          </div>
          <p className="text-xs text-red-600">{brl(p.pagar_vencido)} vencido · {p.pagar_qtd ?? 0} contas</p>
          <AgingBars faixas={p.aging_pagar ?? []} />
        </div>
      </div>

      {/* Custo mensal + Projeção */}
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold text-gray-900">Custo mensal previsto</h2>
            <span className="text-lg font-bold text-gray-900">{brl(p.custo_mensal_total)}</span>
          </div>
          <p className="text-[11px] text-gray-400 mb-3">Provisões 13º/férias: {brl(p.provisoes_mensais)}/mês (invisíveis antes)</p>
          <div className="space-y-1.5 max-h-64 overflow-auto">
            {custoItens.map((i, idx) => (
              <div key={idx} className="flex items-center gap-2 text-sm">
                <span className={`w-2 h-2 rounded-full shrink-0 ${grupoCor[i.grupo] ?? 'bg-gray-400'}`} />
                <span className="flex-1 text-gray-700">{i.categoria}</span>
                <span className="font-mono text-gray-900">{brl(i.valor)}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-900 mb-1">Projeção de caixa (6 meses)</h2>
          <p className="text-[11px] text-gray-400 mb-2">Recorrente: MRR − custos mensais reais. Recebendo os atrasados, melhora.</p>
          {projPontos.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={projPontos} margin={{ top: 4, right: 8, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="cx" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis dataKey="mes" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
                <Tooltip formatter={(v: any) => brl(v)} />
                <Area type="monotone" dataKey="saldo" stroke="#10b981" fill="url(#cx)" strokeWidth={2} name="Saldo projetado" />
              </AreaChart>
            </ResponsiveContainer>
          ) : <p className="text-xs text-gray-400 py-8 text-center">Sem projeção disponível.</p>}
          {proj?.primeiro_mes_negativo && (
            <p className="text-xs text-red-700 mt-2 flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" /> Caixa fica negativo em {proj.primeiro_mes_negativo} se nada mudar.</p>
          )}
        </div>
      </div>

      {/* Tributos + Recebido por cliente */}
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold text-gray-900">Tributos por competência (2026)</h2>
            <span className="text-sm font-bold text-amber-600">{brl(trib?.totais?.total)}</span>
          </div>
          {(trib?.meses ?? []).filter((m: any) => !m.sem_dado).length > 0 ? (
            <table className="w-full text-xs">
              <thead className="text-gray-500 border-b">
                <tr><th className="text-left py-1">Mês</th><th className="text-right">ISS</th><th className="text-right">FGTS</th><th className="text-right">INSS</th><th className="text-right">Total</th></tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {(trib?.meses ?? []).filter((m: any) => !m.sem_dado).map((m: any) => (
                  <tr key={m.mes}>
                    <td className="py-1">{m.competencia}</td>
                    <td className="text-right font-mono">{brl(m.iss)}</td>
                    <td className="text-right font-mono">{brl(m.fgts)}</td>
                    <td className="text-right font-mono">{brl(m.inss)}</td>
                    <td className="text-right font-mono font-semibold">{brl(m.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="text-xs text-gray-400">Sem tributos apurados ainda.</p>}
          <p className="text-[11px] text-gray-400 mt-2">ISS = NFS-e emitidas · FGTS/INSS = folha real · PIS/COFINS zerados (liminar)</p>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold text-gray-900">Recebido por cliente (banco)</h2>
            <span className="text-sm font-bold text-emerald-600">{brl(receb?.total_recebido)}</span>
          </div>
          <div className="space-y-1.5 max-h-64 overflow-auto">
            {(receb?.clientes ?? []).slice(0, 12).map((c: any, i: number) => (
              <div key={i} className="flex items-center justify-between text-sm">
                <span className="text-gray-700 truncate flex-1">{c.cliente}</span>
                <span className="font-mono text-gray-900 ml-2">{brl(c.total)}</span>
                <span className="text-[11px] text-gray-400 ml-2 w-8 text-right">{c.qtd}x</span>
              </div>
            ))}
            {(!receb?.clientes || receb.clientes.length === 0) && <p className="text-xs text-gray-400">Sem recebimentos identificados.</p>}
          </div>
          <p className="text-[11px] text-gray-400 mt-2">Dinheiro que entrou de verdade, identificado pelo nome no PIX/boleto.</p>
        </div>
      </div>

      {/* Adimplência por cliente (MRR contratado x recebido no banco) */}
      {Array.isArray(adim?.clientes) && adim.clientes.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Saúde de pagamento por cliente</h2>
              <p className="text-xs text-gray-500">MRR contratado x quanto entrou de verdade no banco (PIX identificado)</p>
            </div>
          </div>
          <table className="w-full text-sm">
            <thead className="text-gray-500 border-b text-xs">
              <tr>
                <th className="text-left py-1">Cliente</th>
                <th className="text-right">MRR/mês</th>
                <th className="text-right">Recebido (total)</th>
                <th className="text-right">Meses pagos</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {adim.clientes.map((c: any, i: number) => {
                const m = c.meses_equivalentes
                const cor = m == null ? 'text-gray-400' : m < 1 ? 'text-red-600' : m < 2 ? 'text-amber-600' : 'text-green-600'
                return (
                  <tr key={i}>
                    <td className="py-1.5 text-gray-700 truncate max-w-[240px]">{c.cliente}</td>
                    <td className="text-right font-mono">{brl(c.mrr_mensal)}</td>
                    <td className="text-right font-mono">{brl(c.recebido_banco)}</td>
                    <td className={`text-right font-mono font-semibold ${cor}`}>{m != null ? `${m}m` : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <p className="text-[11px] text-gray-400 mt-2">
            Meses pagos = total recebido ÷ MRR mensal. <span className="text-red-600">&lt;1</span> atenção · <span className="text-green-600">≥2</span> em dia. Boletos sem nome não entram.
          </p>
        </div>
      )}

      {/* Pendências acionáveis */}
      {Array.isArray(p.pendencias) && p.pendencias.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-900 mb-2">Pendências acionáveis</h2>
          <ul className="space-y-1.5">
            {p.pendencias.slice(0, 8).map((x: any, i: number) => (
              <li key={i} className="text-sm text-gray-700 flex items-start gap-2">
                <span className="text-amber-500">•</span>
                <span>{typeof x === 'string' ? x : (x.descricao ?? x.titulo ?? JSON.stringify(x))}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
