'use client';

import { useEffect, useState } from 'react';
import {
  Users, ShieldCheck, TrendingUp, Stethoscope, Trophy, CalendarClock,
  AlertTriangle, Loader2, MapPin, Clock, Award, ArrowUpRight, ArrowDownRight,
} from 'lucide-react';
import { operacao, type OperacaoResumo, type Funcionario, type RankingItem, type Aso, type Movimentacao } from '@/services/portal/portalApi';

function iniciais(nome: string) {
  const p = nome.trim().split(/\s+/);
  return ((p[0]?.[0] || '') + (p[p.length - 1]?.[0] || '')).toUpperCase();
}
function corAvatar(nome: string) {
  const cores = ['bg-indigo-500', 'bg-emerald-500', 'bg-amber-500', 'bg-rose-500', 'bg-sky-500', 'bg-violet-500'];
  let h = 0; for (const c of nome) h = (h * 31 + c.charCodeAt(0)) % cores.length;
  return cores[h];
}
function tempoCasa(meses: number | null) {
  if (meses == null) return '—';
  if (meses < 12) return `${meses} ${meses === 1 ? 'mês' : 'meses'}`;
  const a = Math.floor(meses / 12), m = meses % 12;
  return m ? `${a}a ${m}m` : `${a} ${a === 1 ? 'ano' : 'anos'}`;
}

export default function RaioXPage() {
  const [loading, setLoading] = useState(true);
  const [resumo, setResumo] = useState<OperacaoResumo | null>(null);
  const [equipe, setEquipe] = useState<Funcionario[]>([]);
  const [ranking, setRanking] = useState<RankingItem[]>([]);
  const [asos, setAsos] = useState<Aso[]>([]);
  const [mov, setMov] = useState<Movimentacao[]>([]);
  const [advTotal, setAdvTotal] = useState(0);

  useEffect(() => {
    (async () => {
      try {
        const [r, e, rk, at, tv, ad] = await Promise.all([
          operacao.resumo(), operacao.equipe(), operacao.ranking(),
          operacao.atestados(), operacao.turnover(), operacao.advertencias(),
        ]);
        setResumo(r); setEquipe(e.equipe); setRanking(rk.ranking);
        setAsos(at.asos); setMov(tv.movimentacoes); setAdvTotal(ad.total);
      } catch { /* portalFetch trata 401 */ } finally { setLoading(false); }
    })();
  }, []);

  if (loading) return (
    <div className="flex items-center justify-center h-96 text-gray-500">
      <Loader2 className="w-6 h-6 animate-spin mr-2" /> Carregando o raio-x da sua operação…
    </div>
  );

  const cards = [
    { label: 'Equipe alocada', value: resumo?.equipe_total ?? 0, icon: Users, cor: 'text-indigo-600', bg: 'bg-indigo-50' },
    { label: 'Presença no local', value: `${resumo?.assiduidade_local_pct ?? 0}%`, icon: MapPin, cor: 'text-emerald-600', bg: 'bg-emerald-50' },
    { label: 'Turnover (12m)', value: `${resumo?.turnover_pct ?? 0}%`, icon: TrendingUp, cor: 'text-amber-600', bg: 'bg-amber-50' },
    { label: 'ASOs vencidos', value: resumo?.asos_vencidos ?? 0, icon: Stethoscope, cor: (resumo?.asos_vencidos ?? 0) > 0 ? 'text-rose-600' : 'text-emerald-600', bg: (resumo?.asos_vencidos ?? 0) > 0 ? 'bg-rose-50' : 'bg-emerald-50' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <ShieldCheck className="w-7 h-7 text-indigo-600" /> Raio-X da Operação
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Transparência total da equipe e da operação da Conecta Mais no <strong>{resumo?.condominio}</strong>.
        </p>
      </div>

      {/* Cards de resumo */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((c) => (
          <div key={c.label} className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-gray-500">{c.label}</span>
              <span className={`w-9 h-9 rounded-lg ${c.bg} flex items-center justify-center`}><c.icon className={`w-5 h-5 ${c.cor}`} /></span>
            </div>
            <div className={`text-2xl font-bold mt-2 ${c.cor}`}>{c.value}</div>
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Equipe */}
        <section className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h2 className="font-semibold text-gray-900 flex items-center gap-2 mb-4"><Users className="w-5 h-5 text-indigo-600" /> Equipe alocada ({equipe.length})</h2>
          <div className="space-y-3">
            {equipe.map((f) => (
              <div key={f.id} className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-full ${corAvatar(f.nome)} text-white flex items-center justify-center text-sm font-semibold shrink-0`}>{iniciais(f.nome)}</div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-gray-900 truncate">{f.nome}</p>
                  <p className="text-xs text-gray-500">{f.funcao}</p>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-xs text-gray-400">na equipe há</p>
                  <p className="text-xs font-medium text-gray-700">{tempoCasa(f.tempo_casa_meses)}</p>
                </div>
              </div>
            ))}
            {equipe.length === 0 && <p className="text-sm text-gray-400">Nenhum funcionário alocado encontrado.</p>}
          </div>
        </section>

        {/* Ranking */}
        <section className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h2 className="font-semibold text-gray-900 flex items-center gap-2 mb-1"><Trophy className="w-5 h-5 text-amber-500" /> Ranking da equipe</h2>
          <p className="text-xs text-gray-400 mb-4">Por assiduidade, presença no local e reconhecimento facial</p>
          <div className="space-y-2">
            {ranking.map((p) => (
              <div key={p.nome} className={`flex items-center gap-3 p-2 rounded-lg ${p.posicao <= 3 ? 'bg-amber-50' : ''}`}>
                <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                  p.posicao === 1 ? 'bg-amber-400 text-white' : p.posicao === 2 ? 'bg-gray-300 text-white' : p.posicao === 3 ? 'bg-amber-700 text-white' : 'bg-gray-100 text-gray-500'}`}>
                  {p.posicao}
                </span>
                <div className="flex-1 min-w-0"><p className="text-sm font-medium text-gray-900 truncate">{p.nome}</p>
                  <p className="text-xs text-gray-400">{p.dias_presentes} dias presentes</p></div>
                {p.posicao === 1 && <Award className="w-4 h-4 text-amber-500" />}
                <span className="text-sm font-bold text-gray-700">{p.score}</span>
              </div>
            ))}
            {ranking.length === 0 && <p className="text-sm text-gray-400">Sem dados de ponto neste mês.</p>}
          </div>
        </section>

        {/* Atestados / ASO */}
        <section className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h2 className="font-semibold text-gray-900 flex items-center gap-2 mb-4"><Stethoscope className="w-5 h-5 text-rose-500" /> Saúde ocupacional (ASO)</h2>
          <div className="space-y-2 max-h-72 overflow-y-auto">
            {asos.map((a, i) => (
              <div key={i} className="flex items-center gap-2 text-sm">
                <span className={`w-2 h-2 rounded-full ${a.vencido ? 'bg-rose-500' : a.apto ? 'bg-emerald-500' : 'bg-amber-500'}`} />
                <span className="flex-1 min-w-0 truncate text-gray-900">{a.funcionario}</span>
                <span className="text-xs text-gray-400">{a.tipo}</span>
                <span className={`text-xs font-medium ${a.vencido ? 'text-rose-600' : 'text-gray-600'}`}>{a.validade ? `val. ${new Date(a.validade).toLocaleDateString('pt-BR')}` : '—'}</span>
              </div>
            ))}
            {asos.length === 0 && <p className="text-sm text-gray-400">Sem ASOs registrados.</p>}
          </div>
        </section>

        {/* Turnover / movimentações */}
        <section className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h2 className="font-semibold text-gray-900 flex items-center gap-2 mb-1"><TrendingUp className="w-5 h-5 text-amber-600" /> Rotatividade (12 meses)</h2>
          <p className="text-xs text-gray-400 mb-4">{resumo?.admissoes_12m ?? 0} admissões · {resumo?.demissoes_12m ?? 0} desligamentos</p>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {mov.map((m, i) => (
              <div key={i} className="flex items-center gap-2 text-sm">
                {m.demissao ? <ArrowDownRight className="w-4 h-4 text-rose-500" /> : <ArrowUpRight className="w-4 h-4 text-emerald-500" />}
                <span className="flex-1 min-w-0 truncate text-gray-900">{m.nome}</span>
                <span className="text-xs text-gray-400">{m.cargo}</span>
                <span className="text-xs text-gray-500">{m.demissao ? `saiu ${new Date(m.demissao).toLocaleDateString('pt-BR')}` : m.admissao ? `entrou ${new Date(m.admissao).toLocaleDateString('pt-BR')}` : ''}</span>
              </div>
            ))}
            {mov.length === 0 && <p className="text-sm text-gray-400">Sem movimentações no período. Equipe estável. 👍</p>}
          </div>
        </section>
      </div>

      {/* Advertências (transparência) */}
      <section className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
        <h2 className="font-semibold text-gray-900 flex items-center gap-2 mb-2"><AlertTriangle className="w-5 h-5 text-amber-500" /> Medidas disciplinares</h2>
        {advTotal === 0 ? (
          <div className="flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 rounded-lg p-3">
            <ShieldCheck className="w-5 h-5" /> Nenhuma medida disciplinar aplicada à equipe deste condomínio. Operação em conformidade.
          </div>
        ) : (
          <p className="text-sm text-gray-600">{advTotal} medida(s) registrada(s).</p>
        )}
      </section>

      <p className="text-xs text-gray-400 text-center flex items-center justify-center gap-1">
        <Clock className="w-3 h-3" /> Dados em tempo real da operação Conecta Mais — atualizados automaticamente.
      </p>
    </div>
  );
}
