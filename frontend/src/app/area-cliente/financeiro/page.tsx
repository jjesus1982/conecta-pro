'use client';

import { useEffect, useState } from 'react';
import { Receipt, FileText, Wallet, ExternalLink, Loader2, CheckCircle2, BadgeDollarSign } from 'lucide-react';
import { financeiro, type NotaFiscal, type Contrato, type Boleto } from '@/services/portal/portalApi';

const fmt = (v: number) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

export default function FinanceiroPage() {
  const [loading, setLoading] = useState(true);
  const [notas, setNotas] = useState<NotaFiscal[]>([]);
  const [contrato, setContrato] = useState<Contrato | null>(null);
  const [boletos, setBoletos] = useState<Boleto[]>([]);
  const [faturado, setFaturado] = useState(0);

  useEffect(() => {
    (async () => {
      try {
        const [n, c, b] = await Promise.all([financeiro.notas(), financeiro.contrato(), financeiro.boletos()]);
        setNotas(n.notas); setFaturado(n.valor_total); setContrato(c.contrato); setBoletos(b.boletos);
      } catch { /* 401 tratado */ } finally { setLoading(false); }
    })();
  }, []);

  if (loading) return (
    <div className="flex items-center justify-center h-96 text-gray-500">
      <Loader2 className="w-6 h-6 animate-spin mr-2" /> Carregando seu financeiro…
    </div>
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))] flex items-center gap-2"><BadgeDollarSign className="w-7 h-7 text-emerald-600" /> Financeiro</h1>
        <p className="text-sm text-gray-500 mt-1">Suas notas fiscais, contrato e cobranças com a Conecta Mais.</p>
      </div>

      {/* Resumo */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <div className="flex items-center justify-between"><span className="text-xs font-medium text-gray-500">Notas fiscais</span><Receipt className="w-5 h-5 text-indigo-500" /></div>
          <div className="font-data text-2xl font-semibold tabular-nums mt-2 text-[hsl(var(--foreground))]">{notas.length}</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <div className="flex items-center justify-between"><span className="text-xs font-medium text-gray-500">Total faturado</span><Wallet className="w-5 h-5 text-emerald-500" /></div>
          <div className="font-data text-2xl font-semibold tabular-nums mt-2 text-emerald-600">{fmt(faturado)}</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <div className="flex items-center justify-between"><span className="text-xs font-medium text-gray-500">Contrato mensal</span><FileText className="w-5 h-5 text-amber-500" /></div>
          <div className="font-data text-2xl font-semibold tabular-nums mt-2 text-[hsl(var(--foreground))]">{contrato ? fmt(contrato.valor_mensal) : '—'}</div>
        </div>
      </div>

      {/* Contrato */}
      {contrato && (
        <div className="bg-gradient-to-r from-indigo-600 to-indigo-700 rounded-xl p-5 text-white shadow-sm">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <p className="text-indigo-200 text-xs">Contrato vigente</p>
              <p className="text-lg font-semibold">{contrato.numero || 'Contrato de prestação de serviços'}</p>
              <p className="text-indigo-100 text-sm mt-1">{fmt(contrato.valor_mensal)}/mês{contrato.renovacao_meses ? ` · renovação a cada ${contrato.renovacao_meses} meses` : ''}</p>
            </div>
            <span className={`px-3 py-1 rounded-full text-xs font-medium ${contrato.assinado ? 'bg-emerald-400/30 text-emerald-50' : 'bg-white/20'}`}>
              {contrato.assinado ? '✓ Assinado' : 'Ativo'}
            </span>
          </div>
        </div>
      )}

      {/* Boletos */}
      {boletos.length > 0 && (
        <section className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h2 className="font-semibold text-gray-900 mb-3">Boletos</h2>
          <div className="space-y-2">
            {boletos.map((b, i) => (
              <div key={i} className="flex items-center gap-3 text-sm">
                <span className="flex-1">{b.numero}</span>
                <span className="text-gray-500">venc. {b.vencimento ? new Date(b.vencimento).toLocaleDateString('pt-BR') : '—'}</span>
                <span className="font-medium">{fmt(b.valor)}</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">{b.status}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Notas fiscais */}
      <section className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
        <h2 className="font-semibold text-gray-900 flex items-center gap-2 mb-4"><Receipt className="w-5 h-5 text-indigo-600" /> Notas fiscais (NFS-e)</h2>
        {notas.length === 0 ? (
          <p className="text-sm text-gray-400">Nenhuma nota fiscal emitida ainda.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-gray-500 border-b border-gray-200">
                <th className="py-2 pr-4 font-medium">Nº</th><th className="py-2 pr-4 font-medium">Emissão</th>
                <th className="py-2 pr-4 font-medium">Competência</th><th className="py-2 pr-4 font-medium">Valor</th>
                <th className="py-2 pr-4 font-medium">Status</th><th className="py-2 font-medium"></th>
              </tr></thead>
              <tbody>
                {notas.map((n, i) => (
                  <tr key={i} className="border-b border-gray-100">
                    <td className="py-2 pr-4 font-medium text-gray-900">{n.numero || '—'}</td>
                    <td className="py-2 pr-4 text-gray-600">{n.emissao ? new Date(n.emissao).toLocaleDateString('pt-BR') : '—'}</td>
                    <td className="py-2 pr-4 text-gray-600">{n.competencia ? new Date(n.competencia).toLocaleDateString('pt-BR', { month: '2-digit', year: 'numeric' }) : '—'}</td>
                    <td className="py-2 pr-4 font-medium text-gray-900">{fmt(n.valor)}</td>
                    <td className="py-2 pr-4">
                      <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${n.status === 'autorizada' ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-600'}`}>
                        {n.status === 'autorizada' && <CheckCircle2 className="w-3 h-3" />}{n.status}
                      </span>
                    </td>
                    <td className="py-2">{n.link && <a href={n.link} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline inline-flex items-center gap-1 text-xs">Ver <ExternalLink className="w-3 h-3" /></a>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
