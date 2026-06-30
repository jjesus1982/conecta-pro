'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  FolderOpen, CheckCircle2, Clock, BarChart3, Loader2, Wand2,
  ChevronDown, ChevronRight, ExternalLink, XCircle, RefreshCw, ShieldCheck,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { api } from '@/lib/api';

interface ChecklistItem {
  key: string; label: string; subpasta: string;
  presente: boolean; encontrados: number; esperado: number; arquivos: string[];
}
interface SubpastaArquivo { name: string; link: string | null }
interface Subpasta { nome: string; docs: number; arquivos: SubpastaArquivo[] }
interface Kit {
  condominio: string; total: number; drive_link: string | null;
  completion_percentage: number; status: string;
  checklist: ChecklistItem[]; subpastas: Subpasta[];
}
interface Completude {
  competencia: string; mes_kit: string; total_kits: number;
  kits_completos: number; kits_pendentes: number; media_completude: number;
  blocos_por_kit: number; kits: Kit[];
}

const statusColors: Record<string, string> = {
  pendente: 'bg-gray-100 text-gray-700',
  em_montagem: 'bg-yellow-100 text-yellow-800',
  completo: 'bg-emerald-100 text-emerald-800',
};
const statusLabels: Record<string, string> = {
  pendente: 'Pendente', em_montagem: 'Em montagem', completo: 'Completo',
};

function barColor(pct: number) {
  if (pct >= 100) return 'bg-emerald-600';
  if (pct >= 70) return 'bg-blue-600';
  if (pct >= 40) return 'bg-yellow-500';
  return 'bg-red-500';
}

export default function GEDDashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<Completude | null>(null);
  const [loading, setLoading] = useState(true);
  const [aberto, setAberto] = useState<string | null>(null);

  const fetchData = useCallback(async (force = false) => {
    setLoading(true);
    try {
      const { data } = await api.get('/api/v1/gedeon/kits/completude', { params: force ? { refresh: true } : {} });
      setData(data);
    } catch (e) {
      console.error('completude:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const stats = data ? [
    { label: 'Total de Kits', value: data.total_kits, icon: FolderOpen, color: 'text-blue-600', bg: 'bg-blue-50' },
    { label: 'Kits Completos', value: data.kits_completos, icon: CheckCircle2, color: 'text-emerald-600', bg: 'bg-emerald-50' },
    { label: 'Kits Pendentes', value: data.kits_pendentes, icon: Clock, color: 'text-yellow-600', bg: 'bg-yellow-50' },
    { label: 'Média de Conclusão', value: `${data.media_completude}%`, icon: BarChart3, color: 'text-purple-600', bg: 'bg-purple-50' },
  ] : [];

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Kits por Condomínio</h1>
          <p className="text-gray-500 mt-1">
            Completude real (Google Drive){data ? ` — kit de ${data.mes_kit} (competência ${data.competencia})` : ''}.
            Clique no condomínio para abrir a <strong>ficha individualizada</strong> (checklist + anexos).
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={() => fetchData(true)} title="Relê o Drive agora (ignora o cache de 90s)" className="flex items-center gap-2 px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50">
            <RefreshCw className="h-4 w-4" /> Atualizar
          </button>
          <button onClick={() => router.push('/modulos/gestao-pessoas/ged/montar-kit')} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
            <Wand2 className="h-4 w-4" /> Montar / Cronograma
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-96">
          <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
          <span className="ml-2 text-gray-500">Lendo os kits no Drive…</span>
        </div>
      ) : !data ? (
        <div className="text-center text-gray-400 py-20">Não foi possível carregar os kits.</div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {stats.map((s) => {
              const Icon = s.icon;
              return (
                <Card key={s.label} className="border border-gray-200">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-gray-500">{s.label}</p>
                        <p className="text-2xl font-bold mt-1">{s.value}</p>
                      </div>
                      <div className={`p-3 rounded-lg ${s.bg}`}><Icon className={`h-5 w-5 ${s.color}`} /></div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          <Card className="border border-gray-200">
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 text-left text-gray-500">
                      <th className="py-3 px-4 font-medium w-8"></th>
                      <th className="py-3 px-4 font-medium">Condomínio</th>
                      <th className="py-3 px-4 font-medium">Status</th>
                      <th className="py-3 px-4 font-medium">Conclusão</th>
                      <th className="py-3 px-4 font-medium">Docs</th>
                      <th className="py-3 px-4 font-medium">Drive</th>
                      <th className="py-3 px-4 font-medium">Montar</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.kits.map((kit) => {
                      const open = aberto === kit.condominio;
                      return (
                        <>
                          <tr key={kit.condominio} className="border-b border-gray-100 hover:bg-gray-50 cursor-pointer"
                            onClick={() => setAberto(open ? null : kit.condominio)}>
                            <td className="py-3 px-4">
                              {open ? <ChevronDown className="h-4 w-4 text-gray-400" /> : <ChevronRight className="h-4 w-4 text-gray-400" />}
                            </td>
                            <td className="py-3 px-4 font-medium">
                              <button
                                onClick={(e) => { e.stopPropagation(); router.push(`/modulos/gestao-pessoas/ged/kit?cond=${encodeURIComponent(kit.condominio)}&comp=${encodeURIComponent(data.competencia)}`); }}
                                className="text-blue-700 hover:underline text-left"
                                title="Abrir a ficha individualizada deste condomínio"
                              >
                                {kit.condominio}
                              </button>
                            </td>
                            <td className="py-3 px-4">
                              <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${statusColors[kit.status]}`}>
                                {statusLabels[kit.status] || kit.status}
                              </span>
                            </td>
                            <td className="py-3 px-4">
                              <div className="flex items-center gap-2">
                                <div className="w-28 bg-gray-200 rounded-full h-2">
                                  <div className={`${barColor(kit.completion_percentage)} h-2 rounded-full`} style={{ width: `${kit.completion_percentage}%` }} />
                                </div>
                                <span className="text-xs text-gray-600 w-9">{kit.completion_percentage}%</span>
                              </div>
                            </td>
                            <td className="py-3 px-4 text-gray-600">{kit.total}</td>
                            <td className="py-3 px-4">
                              {kit.drive_link && (
                                <a href={kit.drive_link} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}
                                  className="inline-flex items-center gap-1 text-blue-600 hover:underline text-xs">
                                  <ExternalLink className="h-3.5 w-3.5" /> Abrir
                                </a>
                              )}
                            </td>
                            <td className="py-3 px-4">
                              <button
                                onClick={(e) => { e.stopPropagation(); router.push(`/modulos/gestao-pessoas/ged/kit?cond=${encodeURIComponent(kit.condominio)}&comp=${encodeURIComponent(data.competencia)}`); }}
                                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-semibold hover:bg-blue-700 shadow-sm"
                              >
                                Abrir ficha →
                              </button>
                            </td>
                          </tr>
                          {open && (
                            <tr key={`${kit.condominio}-det`} className="bg-gray-50/60">
                              <td colSpan={7} className="px-4 pb-5 pt-1">
                                <div className="grid md:grid-cols-2 gap-6">
                                  {/* Checklist */}
                                  <div>
                                    <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Checklist do kit ({data.blocos_por_kit} blocos)</p>
                                    <ul className="space-y-1.5">
                                      {kit.checklist.map((it) => (
                                        <li key={it.key} className="flex items-center gap-2 text-sm">
                                          {it.presente
                                            ? <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                                            : <XCircle className="h-4 w-4 text-red-400 shrink-0" />}
                                          <span className={it.presente ? '' : 'text-gray-500'}>{it.label}</span>
                                          <span className="text-xs text-gray-400 ml-auto">
                                            {it.esperado > 1 ? `${it.encontrados}/${it.esperado}` : (it.encontrados > 1 ? `${it.encontrados}` : '')}
                                          </span>
                                        </li>
                                      ))}
                                    </ul>
                                  </div>
                                  {/* Arquivos por subpasta */}
                                  <div>
                                    <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Arquivos no Drive</p>
                                    <div className="space-y-3">
                                      {kit.subpastas.map((sp) => (
                                        <div key={sp.nome}>
                                          <p className="text-xs font-medium text-gray-700 flex items-center gap-1">
                                            <FolderOpen className="h-3.5 w-3.5 text-gray-400" /> {sp.nome}
                                            <span className="text-gray-400">({sp.docs})</span>
                                          </p>
                                          {sp.arquivos.length > 0 ? (
                                            <ul className="ml-5 mt-1 space-y-0.5">
                                              {sp.arquivos.map((a, i) => (
                                                <li key={i} className="text-xs text-gray-600 truncate">
                                                  {a.link
                                                    ? <a href={a.link} target="_blank" rel="noopener noreferrer" className="hover:text-blue-600 hover:underline">• {a.name}</a>
                                                    : <span>• {a.name}</span>}
                                                </li>
                                              ))}
                                            </ul>
                                          ) : (
                                            <p className="ml-5 text-xs text-gray-400 italic">vazio</p>
                                          )}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          <p className="text-xs text-gray-400 flex items-center gap-1">
            <ShieldCheck className="h-3.5 w-3.5" />
            Percentuais calculados da estrutura real do Google Drive (montagem GEDEON). O bloco
            "Vale Transporte / Alimentação" entra quando o VA/VT do Sólides for atribuído por condomínio.
          </p>
        </>
      )}
    </div>
  );
}
