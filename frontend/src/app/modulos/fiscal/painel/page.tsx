'use client'

import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { FolderKanban, AlertTriangle, RefreshCw } from 'lucide-react'
import { PageHeader } from '@/components/ui/page-header'

const brl = (v: number | null | undefined) =>
  new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v || 0)

const fetchAuth = async (path: string) => {
  const token = typeof window !== 'undefined'
    ? (localStorage.getItem('access_token') ?? localStorage.getItem('token') ?? '') : ''
  const res = await fetch(`/api/v1${path}`, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

const fmtData = (s: string | null) => {
  if (!s) return '—'
  const [y, m, d] = s.slice(0, 10).split('-')
  return `${d}/${m}/${y}`
}

export default function PainelFiscalPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['painel-fiscal'],
    queryFn: () => fetchAuth('/financial/relatorios/painel-fiscal'),
    staleTime: 60_000, retry: 1,
  })

  if (isLoading) return <div className="p-8 text-gray-500">Carregando painel fiscal…</div>
  if (error || !data) return (
    <div className="p-8">
      <p className="text-red-600 font-medium">Não foi possível carregar o painel fiscal.</p>
      <button onClick={() => refetch()} className="mt-2 text-sm bg-gray-800 text-white px-4 py-2 rounded-lg">Tentar novamente</button>
    </div>
  )

  const o = data.obrigacoes ?? {}
  const c = data.certidoes ?? {}
  const n = data.notas ?? {}
  const t = data.tributos_ano ?? {}
  const stColor: Record<string, string> = {
    cumprida: 'bg-green-100 text-green-700', pendente: 'bg-yellow-100 text-yellow-700', atrasada: 'bg-red-100 text-red-700',
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <PageHeader
        eyebrow="FISCAL"
        title="Painel Fiscal"
        subtitle="Obrigações, certidões, notas e tributos — tudo real, com prazos e semáforo."
        icon={<FolderKanban className="h-5 w-5" />}
        actions={
          <button onClick={() => refetch()} className="flex items-center gap-1.5 text-sm text-gray-600 border border-gray-200 rounded-lg px-4 py-2 hover:bg-gray-50">
            <RefreshCw className="h-4 w-4" /> Atualizar
          </button>
        }
      />

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <p className="text-xs text-gray-500">Obrigações atrasadas</p>
          <p className={`font-data text-2xl font-semibold tabular-nums mt-1 ${o.atrasadas > 0 ? 'text-red-600' : 'text-green-600'}`}>{o.atrasadas ?? 0}</p>
          <p className="text-[11px] text-gray-400">{brl(o.total_pendente)} pendente</p>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <p className="text-xs text-gray-500">Certidões</p>
          <p className={`font-data text-2xl font-semibold tabular-nums mt-1 ${c.vencidas > 0 ? 'text-red-600' : c.a_vencer > 0 ? 'text-amber-600' : 'text-green-600'}`}>
            {c.vencidas > 0 ? `${c.vencidas} vencida${c.vencidas > 1 ? 's' : ''}` : c.a_vencer > 0 ? `${c.a_vencer} a vencer` : 'todas em dia'}
          </p>
          <p className="text-[11px] text-gray-400">{c.total ?? 0} certidões · {c.a_vencer ?? 0} a vencer (≤30d)</p>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <p className="text-xs text-gray-500">NFS-e emitidas</p>
          <p className="font-data text-2xl font-semibold tabular-nums mt-1 text-emerald-600">{n.emitidas?.qtd ?? 0}</p>
          <p className="text-[11px] text-gray-400">{brl(n.emitidas?.total)}</p>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <p className="text-xs text-gray-500">Tributos no ano</p>
          <p className="font-data text-2xl font-semibold tabular-nums mt-1 text-amber-600">{brl(t.total)}</p>
          <p className="text-[11px] text-gray-400">ISS {brl(t.iss)} · FGTS {brl(t.fgts)} · INSS {brl(t.inss)}</p>
        </div>
      </div>

      {/* Obrigações + Certidões */}
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-900 mb-3">Obrigações fiscais</h2>
          <div className="max-h-80 overflow-auto">
            <table className="w-full text-xs">
              <thead className="text-gray-500 border-b sticky top-0 bg-white">
                <tr><th className="text-left py-1">Obrigação</th><th className="text-left">Comp.</th><th className="text-left">Vence</th><th className="text-right">Valor</th><th className="text-right">Status</th></tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {(o.lista ?? []).map((x: any, i: number) => (
                  <tr key={i}>
                    <td className="py-1.5 font-medium text-gray-700">{x.tipo}</td>
                    <td className="text-gray-500">{x.competencia}</td>
                    <td className="text-gray-500">{fmtData(x.vencimento)}</td>
                    <td className="text-right font-mono">{x.valor > 0 ? brl(x.valor) : '—'}</td>
                    <td className="text-right"><span className={`px-1.5 py-0.5 rounded text-[10px] ${stColor[x.status] ?? 'bg-gray-100 text-gray-600'}`}>{x.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {o.atrasadas > 0 && <p className="flex items-center gap-1 text-xs text-red-700 mt-2"><AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" /> {o.atrasadas} obrigação(ões) atrasada(s) — regularize para evitar multa.</p>}
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-900 mb-3">Certidões e regularidade</h2>
          <div className="space-y-1.5">
            {(c.lista ?? []).map((x: any, i: number) => (
              <div key={i} className="flex items-center justify-between text-sm">
                <span className="text-gray-700">{x.tipo}</span>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-gray-400">{fmtData(x.validade)}</span>
                  <span className={`px-2 py-0.5 rounded-full text-[11px] ${x.status === 'vencida' ? 'bg-red-100 text-red-700' : x.status === 'a_vencer' ? 'bg-amber-100 text-amber-700' : 'bg-green-100 text-green-700'}`}>{x.status === 'a_vencer' ? 'a vencer' : x.status === 'em_dia' ? 'em dia' : x.status}</span>
                </div>
              </div>
            ))}
          </div>
          {c.vencidas > 0 && <p className="flex items-center gap-1 text-xs text-red-700 mt-3"><AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" /> {c.vencidas} certidão(ões) vencida(s) — necessárias para licitações e contratos.</p>}
        </div>
      </div>

      {/* Notas + Empresas */}
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-900 mb-3">Notas fiscais</h2>
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="bg-emerald-50 rounded-lg p-3">
              <p className="text-lg font-bold text-emerald-700">{n.emitidas?.qtd ?? 0}</p>
              <p className="text-[11px] text-gray-500">Emitidas (saída)</p>
              <p className="text-[11px] text-gray-400">{brl(n.emitidas?.total)}</p>
            </div>
            <div className="bg-blue-50 rounded-lg p-3">
              <p className="text-lg font-bold text-blue-700">{n.tomadas_nfse?.qtd ?? 0}</p>
              <p className="text-[11px] text-gray-500">NFS-e tomadas</p>
              <p className="text-[11px] text-gray-400">{brl(n.tomadas_nfse?.total)}</p>
            </div>
            <div className="bg-blue-50 rounded-lg p-3">
              <p className="text-lg font-bold text-blue-700">{n.tomadas_nfe?.qtd ?? 0}</p>
              <p className="text-[11px] text-gray-500">NF-e compras</p>
              <p className="text-[11px] text-gray-400">{brl(n.tomadas_nfe?.total)}</p>
            </div>
          </div>
          <p className="text-[11px] text-gray-400 mt-2">Emitidas: {fmtData(n.emitidas?.de)} a {fmtData(n.emitidas?.ate)}. NF-e de compras puxadas da SEFAZ (DistribuiçãoDFe).</p>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-900 mb-3">Empresas do grupo</h2>
          <div className="space-y-2">
            {(data.empresas ?? []).map((e: any, i: number) => (
              <div key={i} className="flex items-center justify-between border border-gray-100 rounded-lg p-3">
                <div>
                  <p className="text-sm font-medium text-gray-800">{e.razao_social}{e.principal && <span className="ml-2 text-[10px] bg-gray-800 text-white px-1.5 py-0.5 rounded">principal</span>}</p>
                  <p className="text-[11px] text-gray-400">{e.cnpj}</p>
                </div>
                <span className={`text-[11px] px-2 py-1 rounded-full ${e.regime === 'lucro_real' ? 'bg-purple-100 text-purple-700' : 'bg-teal-100 text-teal-700'}`}>{e.regime === 'lucro_real' ? 'Lucro Real' : 'Simples Nacional'}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Apuração IRPJ/CSLL (Lucro Real) — sobre o lucro do razão */}
      <ApuracaoLucroReal />
    </div>
  )
}

// ─── Apuração IRPJ/CSLL real (Lucro Real, sobre o lucro do razão) ─────────────
function ApuracaoLucroReal() {
  const [tri, setTri] = useState(1)
  const { data, isLoading, error } = useQuery({
    queryKey: ['apuracao-lucro-real', tri],
    queryFn: () => fetchAuth(`/financial/relatorios/apuracao-lucro-real?ano=2026&trimestre=${tri}`),
    staleTime: 60_000, retry: 1,
  })

  const base = data?.base ?? {}
  const ap = data?.apuracao ?? {}
  const prejuizo = data?.prejuizo_fiscal_compensavel ?? 0

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-sm font-semibold text-gray-900">Apuração IRPJ/CSLL — Lucro Real</h2>
        <div className="flex gap-1">
          {[1, 2, 3, 4].map(t => (
            <button key={t} onClick={() => setTri(t)}
              className={`text-xs px-2.5 py-1 rounded-lg ${tri === t ? 'bg-[#0A2540] text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
              {t}º tri
            </button>
          ))}
        </div>
      </div>
      <p className="text-[11px] text-gray-400 mb-4">Base = lucro real do razão (não presunção de 32%). CNPJ principal.</p>

      {isLoading ? (
        <p className="text-sm text-gray-400">Apurando…</p>
      ) : error ? (
        <p className="text-sm text-red-600">Não foi possível apurar.</p>
      ) : (
        <div className="grid md:grid-cols-2 gap-5">
          {/* Base */}
          <div className="space-y-1.5 text-sm">
            {[
              ['Receita bruta', base.receita_bruta],
              ['(-) Deduções (ISS)', base.deducoes_iss, true],
              ['(=) Receita líquida', base.receita_liquida, false, true],
              ['(-) Despesa pessoal', base.despesa_pessoal, true],
              ['(-) Encargos (FGTS)', base.despesa_encargos, true],
              ['(-) Custo materiais (COGS)', base.custo_materiais_cogs, true],
              ['(-) Outras despesas dedutíveis', (base.despesas_dedutiveis_total ?? 0) - (base.despesa_pessoal ?? 0) - (base.despesa_encargos ?? 0) - (base.custo_materiais_cogs ?? 0), true],
              ['(=) Lucro antes IRPJ/CSLL', base.lucro_antes_ircsll, false, true],
            ].map(([label, val, neg, bold], i) => (
              <div key={i} className={`flex justify-between ${bold ? 'border-t border-gray-200 pt-1.5 font-semibold text-gray-900' : 'text-gray-600'}`}>
                <span>{label as string}</span>
                <span className={neg ? 'text-red-600' : ''}>{brl(val as number)}</span>
              </div>
            ))}
          </div>

          {/* Apuração */}
          <div className="space-y-1.5 text-sm">
            <div className="flex justify-between text-gray-600"><span>IRPJ (15%)</span><span>{brl(ap.irpj_15)}</span></div>
            <div className="flex justify-between text-gray-600"><span>IRPJ adicional (10% s/ excedente)</span><span>{brl(ap.irpj_adicional_10)}</span></div>
            <div className="flex justify-between text-gray-600"><span>CSLL (9%)</span><span>{brl(ap.csll_9)}</span></div>
            <div className="flex justify-between border-t border-gray-200 pt-1.5 font-semibold text-gray-900">
              <span>Total IRPJ/CSLL</span><span className="text-purple-700">{brl(ap.total_irpj_csll)}</span>
            </div>
            <div className="flex justify-between text-gray-500 text-xs"><span>Carga sobre receita</span><span>{(ap.carga_sobre_receita_pct ?? 0).toFixed(2)}%</span></div>
            {prejuizo > 0 && (
              <div className="mt-2 bg-orange-50 border border-orange-200 rounded-lg p-2.5 text-xs text-orange-700">
                Prejuízo fiscal no período: <b>{brl(prejuizo)}</b> — sem IRPJ/CSLL, compensável em períodos futuros.
              </div>
            )}
          </div>
        </div>
      )}

      <p className="flex items-start gap-1 text-[11px] text-gray-400 mt-4 border-t border-gray-100 pt-2">
        <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0 mt-px" /> {data?.observacao ?? 'Base = lucro do razão: receita só de NFS-e, salários não duplicam a folha, fornecedores em Serviços de Terceiros. Períodos ainda incompletos podem inflar o lucro; LALUR e PIS/COFINS à parte.'}
      </p>
    </div>
  )
}
